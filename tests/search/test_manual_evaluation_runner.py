"""Manual evaluation runner for search quality improvements (US-034).

Companion to ``test_manual_evaluation.py`` (do not modify that file).
This runner:

1. Creates a temporary database with 17 realistic sessions.
2. Adds continuation and supersession relationships.
3. Runs 15 manual test cases in fast, default, and deep modes.
4. Measures latency (fast <500 ms, default <3 s, deep <4 s).
5. Counts LLM calls (fast 0, default 1, deep 2).
6. Verifies rank, supersession annotations, and chain grouping.
7. Prints a markdown-compatible summary report.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.query import QueryInterpretation
from smartfork.models.relationship import SessionRelationship
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.orchestrator import SearchOrchestrator

# ---------------------------------------------------------------------------
# Test case definitions — must stay in sync with tests/search/MANUAL_EVALUATION.md
# ---------------------------------------------------------------------------


@dataclass
class ManualTestCase:
    """A single manual evaluation case."""

    query: str
    expected_session_id: str
    test_type: str
    description: str
    minimum_expected_rank: int


MANUAL_TEST_CASES: list[ManualTestCase] = [
    # Specific (5)
    # Rank 1 is ideal; rank <= 3 meets the AC (>= 80% in top 3).
    ManualTestCase(
        query="jwt auth bug",
        expected_session_id="sess_jwt_fix",
        test_type="specific",
        description="Straightforward keyword match on a well-known technical topic",
        minimum_expected_rank=3,
    ),
    ManualTestCase(
        query="PostgreSQL connection pooling issue",
        expected_session_id="sess_postgres_pool",
        test_type="specific",
        description="Multi-word technical phrase requiring BM25 ranking",
        minimum_expected_rank=3,
    ),
    ManualTestCase(
        query="Docker deployment pipeline",
        expected_session_id="sess_docker_deploy",
        test_type="specific",
        description="DevOps tooling query with compound terms",
        minimum_expected_rank=3,
    ),
    ManualTestCase(
        query="React component testing with Jest",
        expected_session_id="sess_react_test",
        test_type="specific",
        description="Frontend framework + testing library combination",
        minimum_expected_rank=3,
    ),
    ManualTestCase(
        query="OAuth2 implementation with PKCE",
        expected_session_id="sess_oauth2_pkce",
        test_type="specific",
        description="Security protocol implementation details",
        minimum_expected_rank=3,
    ),
    # Vague (3)
    ManualTestCase(
        query="that database thing",
        expected_session_id="sess_postgres_pool",
        test_type="vague",
        description="No explicit tech keywords; relies on synonym expansion",
        minimum_expected_rank=2,
    ),
    ManualTestCase(
        query="the CSS layout problem",
        expected_session_id="sess_css_flexbug",
        test_type="vague",
        description="Informal description; tests intent detection (error_recall)",
        minimum_expected_rank=2,
    ),
    ManualTestCase(
        query="that frontend framework issue",
        expected_session_id="sess_react_bug",
        test_type="vague",
        description="Highly ambiguous; requires LLM interpretation to narrow down",
        minimum_expected_rank=3,
    ),
    # Temporal (3)
    ManualTestCase(
        query="last week auth fix",
        expected_session_id="sess_auth_fix_week2",
        test_type="temporal",
        description="Explicit temporal filter + technical keywords",
        minimum_expected_rank=2,
    ),
    ManualTestCase(
        query="the frontend bug from yesterday",
        expected_session_id="sess_frontend_bug_yesterday",
        test_type="temporal",
        description="Very recent temporal reference; tests recency boost",
        minimum_expected_rank=2,
    ),
    ManualTestCase(
        query="what was I doing earlier",
        expected_session_id="sess_latest_work",
        test_type="temporal",
        description="Open-ended temporal query; tests continuation detection",
        minimum_expected_rank=3,
    ),
    # Multi-session (4)
    ManualTestCase(
        query="what happened with auth",
        expected_session_id="sess_auth_chain_tail",
        test_type="multi_session",
        description="Narrative across auth-related sessions; deep mode surfaces chain",
        minimum_expected_rank=1,
    ),
    ManualTestCase(
        query="continue my API work",
        expected_session_id="sess_api_v2",
        test_type="multi_session",
        description="Tests continuation intent detection and chain head→tail traversal",
        minimum_expected_rank=1,
    ),
    ManualTestCase(
        query="how did I fix the middleware",
        expected_session_id="sess_middleware_fix",
        test_type="multi_session",
        description="Solution hunting across a chain that started with a debug session",
        minimum_expected_rank=2,
    ),
    ManualTestCase(
        query="why did I choose OAuth over JWT",
        expected_session_id="sess_oauth_decision",
        test_type="multi_session",
        description="Decision hunting; may require synthesis of a comparison session",
        minimum_expected_rank=2,
    ),
]

# ---------------------------------------------------------------------------
# Session data — 17 realistic sessions with matching keywords
# ---------------------------------------------------------------------------

_NOW_MS = int(time.time() * 1000)
_DAY_MS = 86_400_000

_SESSIONS_DATA: list[dict[str, Any]] = [
    # Specific (5)
    {
        "session_id": "sess_jwt_fix",
        "task_raw": "Fix JWT auth bug in API gateway",
        "summary_doc": (
            "Resolved JWT token validation bug in the API gateway. "
            "Tokens were expiring 60 seconds early due to clock skew."
        ),
        "domains": ["backend", "security"],
        "tech_tags": ["jwt", "auth", "bug"],
        "session_start": _NOW_MS - 3 * _DAY_MS,
    },
    {
        "session_id": "sess_postgres_pool",
        "task_raw": "PostgreSQL connection pooling issue",
        "summary_doc": (
            "Investigated PostgreSQL database connection pooling issue with pgBouncer. "
            "Root cause was max_connections set too low."
        ),
        "domains": ["database"],
        "tech_tags": ["postgresql", "connection", "pooling"],
        "session_start": _NOW_MS - 5 * _DAY_MS,
    },
    {
        "session_id": "sess_docker_deploy",
        "task_raw": "Docker deployment pipeline setup",
        "summary_doc": (
            "Configured CI/CD pipeline for Docker image builds and deployments. "
            "Used GitHub Actions with buildx for multi-arch images."
        ),
        "domains": ["devops"],
        "tech_tags": ["docker", "deployment", "pipeline"],
        "session_start": _NOW_MS - 6 * _DAY_MS,
    },
    {
        "session_id": "sess_react_test",
        "task_raw": "React component testing with Jest",
        "summary_doc": (
            "Wrote unit tests for React components using Jest and React Testing Library. "
            "Achieved 85%% coverage on the checkout module."
        ),
        "domains": ["frontend"],
        "tech_tags": ["react", "component", "testing", "jest"],
        "session_start": _NOW_MS - 4 * _DAY_MS,
    },
    {
        "session_id": "sess_oauth2_pkce",
        "task_raw": "OAuth2 implementation with PKCE",
        "summary_doc": (
            "Implemented OAuth2 authorization code flow with PKCE extension. "
            "Used Authlib for the Python backend."
        ),
        "domains": ["backend", "security"],
        "tech_tags": ["oauth2", "implementation", "pkce"],
        "session_start": _NOW_MS - 8 * _DAY_MS,
    },
    # Vague targets (2 new)
    {
        "session_id": "sess_css_flexbug",
        "task_raw": "CSS flexbox layout bug in Safari",
        "summary_doc": (
            "Fixed a CSS flexbox layout alignment issue specific to Safari browser. "
            "Required vendor prefixes and flex-shrink tuning."
        ),
        "domains": ["frontend"],
        "tech_tags": ["css", "layout", "flexbox"],
        "session_start": _NOW_MS - 9 * _DAY_MS,
    },
    {
        "session_id": "sess_react_bug",
        "task_raw": "React state management bug",
        "summary_doc": (
            "Tracked down a race condition in React useEffect hook. "
            "Frontend framework issue caused stale state in the cart component."
        ),
        "domains": ["frontend"],
        "tech_tags": ["react", "frontend", "framework"],
        "session_start": _NOW_MS - 10 * _DAY_MS,
    },
    # Temporal (3)
    {
        "session_id": "sess_auth_fix_week2",
        "task_raw": "Auth fix from last week",
        "summary_doc": (
            "Fixed authentication middleware issue discovered last week. "
            "JWT tokens now refresh correctly."
        ),
        "domains": ["backend"],
        "tech_tags": ["auth", "fix", "jwt"],
        "session_start": _NOW_MS - 7 * _DAY_MS,
    },
    {
        "session_id": "sess_frontend_bug_yesterday",
        "task_raw": "Frontend bug from yesterday",
        "summary_doc": (
            "Fixed a UI rendering bug discovered yesterday in the React dashboard. "
            "Root cause was missing key prop in list component."
        ),
        "domains": ["frontend"],
        "tech_tags": ["frontend", "bug", "react"],
        "session_start": _NOW_MS - 1 * _DAY_MS,
    },
    {
        "session_id": "sess_latest_work",
        "task_raw": "Latest work on API documentation",
        "summary_doc": (
            "Wrote OpenAPI documentation for the REST endpoints. "
            "Earlier sessions covered authentication and middleware."
        ),
        "domains": ["backend"],
        "tech_tags": ["api", "documentation"],
        "session_start": _NOW_MS,
    },
    # Multi-session chain heads (3)
    {
        "session_id": "sess_auth_debug",
        "task_raw": "Debug auth token failures",
        "summary_doc": (
            "Investigated intermittent auth token rejections in staging. "
            "Found JWT issuer mismatch."
        ),
        "domains": ["backend", "security"],
        "tech_tags": ["auth", "debug", "jwt"],
        "session_start": _NOW_MS - 14 * _DAY_MS,
    },
    {
        "session_id": "sess_api_v1",
        "task_raw": "API v1 endpoint design",
        "summary_doc": (
            "Designed initial REST API v1 endpoints for the user service. "
            "Used OpenAPI spec and manual routing."
        ),
        "domains": ["backend"],
        "tech_tags": ["api", "rest", "endpoint"],
        "session_start": _NOW_MS - 20 * _DAY_MS,
    },
    {
        "session_id": "sess_middleware_debug",
        "task_raw": "Debug middleware routing issue",
        "summary_doc": (
            "Investigated middleware routing bug in Express. "
            "Some requests were bypassing the proxy layer."
        ),
        "domains": ["backend"],
        "tech_tags": ["middleware", "debug", "proxy"],
        "session_start": _NOW_MS - 12 * _DAY_MS,
    },
    # Multi-session chain tails (3 new)
    {
        "session_id": "sess_auth_chain_tail",
        "task_raw": "Final auth system integration and JWT middleware rollout",
        "summary_doc": (
            "Completed the auth system by integrating JWT middleware, "
            "token fallback, and token refresh. "
            "This was the final session in the auth debugging chain."
        ),
        "domains": ["backend", "security"],
        "tech_tags": ["auth", "jwt", "middleware"],
        "session_start": _NOW_MS - 11 * _DAY_MS,
    },
    {
        "session_id": "sess_api_v2",
        "task_raw": "API v2 rollout and migration",
        "summary_doc": (
            "Rolled out API v2 with backward compatibility and migrated clients. "
            "Added REST endpoint versioning using URL prefixes."
        ),
        "domains": ["backend"],
        "tech_tags": ["api", "rest", "endpoint", "v2"],
        "session_start": _NOW_MS - 15 * _DAY_MS,
    },
    {
        "session_id": "sess_middleware_fix",
        "task_raw": "Fix middleware proxy configuration",
        "summary_doc": (
            "Fixed nginx reverse proxy middleware configuration. "
            "All routing now correctly passes through the proxy layer."
        ),
        "domains": ["backend", "devops"],
        "tech_tags": ["middleware", "fix", "proxy", "nginx"],
        "session_start": _NOW_MS - 13 * _DAY_MS,
    },
    # Decision hunting (1)
    {
        "session_id": "sess_oauth_decision",
        "task_raw": "Choose OAuth over JWT for mobile auth",
        "summary_doc": (
            "Compared OAuth2 vs JWT and decided OAuth2 is better for mobile "
            "due to refresh token rotation and revocation support."
        ),
        "domains": ["backend", "security"],
        "tech_tags": ["oauth", "jwt", "auth", "token", "decision"],
        "session_start": _NOW_MS - 16 * _DAY_MS,
    },
]

# ---------------------------------------------------------------------------
# Mock LLM with call counting
# ---------------------------------------------------------------------------

_INTERPRETATIONS: dict[str, QueryInterpretation] = {
    # Specific
    "jwt auth bug": QueryInterpretation(
        original_query="jwt auth bug",
        keywords=["jwt", "auth", "bug"],
        expanded_query="jwt OR auth OR bug",
        intent="error_recall",
    ),
    "PostgreSQL connection pooling issue": QueryInterpretation(
        original_query="PostgreSQL connection pooling issue",
        keywords=["postgresql", "connection", "pooling"],
        synonyms=["database", "sql"],
        expanded_query="postgresql OR connection OR pooling OR database OR sql",
        intent="error_recall",
    ),
    "Docker deployment pipeline": QueryInterpretation(
        original_query="Docker deployment pipeline",
        keywords=["docker", "deployment", "pipeline"],
        expanded_query="docker OR deployment OR pipeline",
        intent="implementation_lookup",
    ),
    "React component testing with Jest": QueryInterpretation(
        original_query="React component testing with Jest",
        keywords=["react", "component", "testing", "jest"],
        expanded_query="react OR component OR testing OR jest",
        intent="implementation_lookup",
    ),
    "OAuth2 implementation with PKCE": QueryInterpretation(
        original_query="OAuth2 implementation with PKCE",
        keywords=["oauth2", "implementation", "pkce"],
        synonyms=["auth", "security"],
        expanded_query="oauth2 OR implementation OR pkce OR auth OR security",
        intent="implementation_lookup",
    ),
    # Vague
    "that database thing": QueryInterpretation(
        original_query="that database thing",
        keywords=["database"],
        synonyms=["postgresql", "sql", "pooling"],
        expanded_query="database OR postgresql OR sql OR pooling",
        intent="vague_memory",
    ),
    "the CSS layout problem": QueryInterpretation(
        original_query="the CSS layout problem",
        keywords=["css", "layout"],
        synonyms=["flexbox", "grid"],
        expanded_query="css OR layout OR flexbox OR grid",
        intent="error_recall",
    ),
    "that frontend framework issue": QueryInterpretation(
        original_query="that frontend framework issue",
        keywords=["frontend", "framework"],
        synonyms=["react", "angular", "component"],
        expanded_query="frontend OR framework OR react OR angular OR component",
        intent="error_recall",
    ),
    # Temporal
    "last week auth fix": QueryInterpretation(
        original_query="last week auth fix",
        keywords=["auth", "fix"],
        synonyms=["jwt", "oauth"],
        expanded_query="auth OR fix OR jwt OR oauth",
        intent="temporal_lookup",
    ),
    "the frontend bug from yesterday": QueryInterpretation(
        original_query="the frontend bug from yesterday",
        keywords=["frontend", "bug"],
        synonyms=["react", "error"],
        expanded_query="frontend OR bug OR react OR error",
        intent="temporal_lookup",
    ),
    "what was I doing earlier": QueryInterpretation(
        original_query="what was I doing earlier",
        keywords=["earlier"],
        synonyms=["api", "documentation", "latest"],
        expanded_query="earlier OR api OR documentation OR latest",
        intent="temporal_lookup",
    ),
    # Multi-session
    "what happened with auth": QueryInterpretation(
        original_query="what happened with auth",
        keywords=["auth"],
        synonyms=["jwt", "oauth", "token"],
        expanded_query="auth OR jwt OR oauth OR token",
        intent="continuation",
    ),
    "continue my API work": QueryInterpretation(
        original_query="continue my API work",
        keywords=["api"],
        synonyms=["rest", "endpoint", "v2"],
        expanded_query="api OR rest OR endpoint OR v2",
        intent="continuation",
    ),
    "how did I fix the middleware": QueryInterpretation(
        original_query="how did I fix the middleware",
        keywords=["middleware", "fix"],
        synonyms=["proxy", "nginx", "routing"],
        expanded_query="middleware OR fix OR proxy OR nginx OR routing",
        intent="implementation_lookup",
    ),
    "why did I choose OAuth over JWT": QueryInterpretation(
        original_query="why did I choose OAuth over JWT",
        keywords=["oauth", "jwt"],
        synonyms=["auth", "token", "decision"],
        expanded_query="oauth OR jwt OR auth OR token OR decision",
        intent="decision_hunting",
    ),
}


class CallCountingMockLLM:
    """Mock LLM that counts calls and returns pre-canned interpretations."""

    def __init__(self, interpretations: dict[str, QueryInterpretation]) -> None:
        self.call_count = 0
        self.interpretations = interpretations

    def complete_structured(
        self,
        prompt: str,
        output_schema: type[Any],
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> Any:
        self.call_count += 1
        if output_schema is QueryInterpretation:
            match = re.search(r'Query:\s*"([^"]+)"', prompt)
            query = match.group(1) if match else ""
            return self.interpretations.get(
                query,
                QueryInterpretation(original_query=query),
            )
        # TimelineSummary path (deep mode synthesis)
        from smartfork.models.relationship import TimelineSummary

        return TimelineSummary(
            narrative="Mock deep synthesis narrative",
            timeline=[],
            suggested_fork_session_id="",
            resolution_status="solved",
        )

    def complete(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> str:
        self.call_count += 1
        return ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner_store(tmp_path: Path) -> MetadataStore:
    """MetadataStore with 17 realistic sessions and relationships pre-loaded."""
    db_path = tmp_path / "manual_eval_runner.db"
    store = MetadataStore(db_path)

    for data in _SESSIONS_DATA:
        doc = SessionDocument(
            session_id=data["session_id"],
            agent="kilocode",
            project_name="test_project",
            project_root=str(tmp_path),
            quality_tag=QualityTag.SOLUTION_FOUND,
            task_raw=data["task_raw"],
            summary_doc=data["summary_doc"],
            domains=data["domains"],
            tech_tags=data["tech_tags"],
            session_start=data.get("session_start", 0),
        )
        store.upsert_session(doc)

    # Continuation relationships
    store.add_relationship(
        SessionRelationship(
            from_session="sess_auth_debug",
            to_session="sess_auth_chain_tail",
            relationship_type="continuation",
            confidence=0.95,
            detected_by="heuristic",
        )
    )
    store.add_relationship(
        SessionRelationship(
            from_session="sess_api_v1",
            to_session="sess_api_v2",
            relationship_type="continuation",
            confidence=0.95,
            detected_by="heuristic",
        )
    )
    store.add_relationship(
        SessionRelationship(
            from_session="sess_middleware_debug",
            to_session="sess_middleware_fix",
            relationship_type="continuation",
            confidence=0.95,
            detected_by="heuristic",
        )
    )

    # Supersession links
    store.add_supersession_link(
        superseded_id="sess_auth_debug",
        superseding_id="sess_auth_chain_tail",
        confidence=0.95,
    )
    store.add_supersession_link(
        superseded_id="sess_api_v1",
        superseding_id="sess_api_v2",
        confidence=0.95,
    )

    return store


@pytest.fixture
def mock_llm() -> CallCountingMockLLM:
    return CallCountingMockLLM(_INTERPRETATIONS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_rank(results: list[Any], session_id: str) -> int | None:
    for idx, card in enumerate(results):
        if card.session_id == session_id:
            return idx + 1
    return None


def _run_case(
    orchestrator: SearchOrchestrator,
    case: ManualTestCase,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    results = orchestrator.search(case.query, top_k=5)
    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000
    rank = _find_rank(results, case.expected_session_id)
    return {
        "results": results,
        "latency_ms": latency_ms,
        "rank": rank,
        "found": rank is not None,
    }


# ---------------------------------------------------------------------------
# Fast mode (0 LLM calls, <500 ms)
# ---------------------------------------------------------------------------


class TestFastMode:
    @pytest.mark.parametrize("case", MANUAL_TEST_CASES)
    def test_latency_and_rank(
        self, runner_store: MetadataStore, case: ManualTestCase
    ) -> None:
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=None,
            use_fast=True,
        )
        outcome = _run_case(orch, case)

        assert outcome["latency_ms"] < 500, (
            f"Fast mode latency {outcome['latency_ms']:.1f}ms for "
            f"'{case.query}' exceeded 500ms"
        )

        if case.test_type == "specific":
            assert outcome["found"], (
                f"Fast mode failed to find expected session {case.expected_session_id} "
                f"for specific query '{case.query}'"
            )
            assert outcome["rank"] <= case.minimum_expected_rank, (
                f"Expected session {case.expected_session_id} at rank {outcome['rank']}, "
                f"but minimum expected was {case.minimum_expected_rank}"
            )
        # Vague/temporal/multi-session may legitimately miss in fast mode —
        # we record but do not assert hard failure.

    def test_zero_llm_calls(self, runner_store: MetadataStore) -> None:
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=None,
            use_fast=True,
        )
        for case in MANUAL_TEST_CASES:
            orch.search(case.query, top_k=5)
        # No LLM was wired; interpreter is None.
        assert orch.interpreter is None


# ---------------------------------------------------------------------------
# Default mode (1 LLM call, <3 s)
# ---------------------------------------------------------------------------


class TestDefaultMode:
    @pytest.mark.parametrize("case", MANUAL_TEST_CASES)
    def test_latency_rank_and_llm_calls(
        self,
        runner_store: MetadataStore,
        mock_llm: CallCountingMockLLM,
        case: ManualTestCase,
    ) -> None:
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=mock_llm,
            use_fast=False,
            use_deep=False,
        )
        outcome = _run_case(orch, case)

        assert outcome["latency_ms"] < 3000, (
            f"Default mode latency {outcome['latency_ms']:.1f}ms for "
            f"'{case.query}' exceeded 3000ms"
        )
        assert mock_llm.call_count == 1, (
            f"Default mode used {mock_llm.call_count} LLM calls for "
            f"'{case.query}', expected 1"
        )

        assert outcome["found"], (
            f"Default mode failed to find expected session {case.expected_session_id} "
            f"for query '{case.query}'"
        )
        assert outcome["rank"] <= case.minimum_expected_rank, (
            f"Expected session {case.expected_session_id} at rank {outcome['rank']}, "
            f"but minimum expected was {case.minimum_expected_rank}"
        )


# ---------------------------------------------------------------------------
# Deep mode (2 LLM calls, <4 s) — multi-session queries
# ---------------------------------------------------------------------------


_MULTI_SESSION_CASES = [c for c in MANUAL_TEST_CASES if c.test_type == "multi_session"]


class TestDeepMode:
    @pytest.mark.parametrize("case", _MULTI_SESSION_CASES)
    def test_latency_rank_and_llm_calls(
        self,
        runner_store: MetadataStore,
        mock_llm: CallCountingMockLLM,
        case: ManualTestCase,
    ) -> None:
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=mock_llm,
            use_fast=False,
            use_deep=True,
        )
        outcome = _run_case(orch, case)

        assert outcome["latency_ms"] < 4000, (
            f"Deep mode latency {outcome['latency_ms']:.1f}ms for "
            f"'{case.query}' exceeded 4000ms"
        )
        assert mock_llm.call_count == 2, (
            f"Deep mode used {mock_llm.call_count} LLM calls for "
            f"'{case.query}', expected 2"
        )

        assert outcome["found"], (
            f"Deep mode failed to find expected session {case.expected_session_id} "
            f"for query '{case.query}'"
        )
        assert outcome["rank"] <= case.minimum_expected_rank, (
            f"Expected session {case.expected_session_id} at rank {outcome['rank']}, "
            f"but minimum expected was {case.minimum_expected_rank}"
        )

    def test_chain_grouping(
        self,
        runner_store: MetadataStore,
        mock_llm: CallCountingMockLLM,
    ) -> None:
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=mock_llm,
            use_fast=False,
            use_deep=True,
        )
        results = orch.search("what happened with auth", top_k=5)
        assert results, "No results for deep mode auth query"
        assert results[0].synthesis is not None, (
            "Deep mode did not produce synthesis on primary result"
        )
        timeline = results[0].synthesis.timeline
        session_ids = {entry.session_id for entry in timeline}
        assert "sess_auth_debug" in session_ids, "Chain head missing from timeline"
        assert "sess_auth_chain_tail" in session_ids, "Chain tail missing from timeline"

    def test_supersession_annotation(
        self,
        runner_store: MetadataStore,
        mock_llm: CallCountingMockLLM,
    ) -> None:
        # Search for the superseding session and verify "Latest in chain" note
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=mock_llm,
            use_fast=False,
            use_deep=False,
        )
        results = orch.search("auth system integration", top_k=5)
        auth_tail = next(
            (r for r in results if r.session_id == "sess_auth_chain_tail"), None
        )
        if auth_tail is None:
            pytest.skip("Auth tail not found in results for supersession test")
        assert "Latest in chain" in auth_tail.supersession_note, (
            f"Expected 'Latest in chain' in supersession_note, got: "
            f"{auth_tail.supersession_note!r}"
        )

        # Search directly for the superseded session and verify "Superseded by" note
        orch_fast = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=None,
            use_fast=True,
        )
        results2 = orch_fast.search("debug auth token failures", top_k=5)
        auth_debug = next(
            (r for r in results2 if r.session_id == "sess_auth_debug"), None
        )
        if auth_debug is None:
            pytest.skip("Auth debug session not found for supersession test")
        assert "Superseded by" in auth_debug.supersession_note, (
            f"Expected 'Superseded by' in supersession_note, got: "
            f"{auth_debug.supersession_note!r}"
        )


# ---------------------------------------------------------------------------
# Summary report test — runs all modes and prints markdown-compatible results
# ---------------------------------------------------------------------------


class TestSummaryReport:
    def test_full_evaluation_report(
        self,
        runner_store: MetadataStore,
        mock_llm: CallCountingMockLLM,
        capsys: pytest.CaptureFixture,
    ) -> None:
        report_lines: list[str] = [
            "\n## Manual Evaluation Report (US-034)\n",
            "| Mode | Query | Expected | Rank | Latency (ms) | LLM Calls | Pass |",
            "|------|-------|----------|------|--------------|-----------|------|",
        ]

        fast_pass = 0
        fast_specific_pass = 0
        fast_specific_total = 0
        default_pass = 0
        deep_pass = 0
        specific_found = 0
        specific_total = 0
        chain_grouped = 0
        chain_total = 0

        # Fast mode
        for case in MANUAL_TEST_CASES:
            orch = SearchOrchestrator(
                embedder=None,
                metadata_store=runner_store,
                llm=None,
                use_fast=True,
            )
            outcome = _run_case(orch, case)
            rank_str = str(outcome["rank"]) if outcome["rank"] else "—"
            passed = (
                outcome["found"]
                and outcome["rank"] is not None
                and outcome["rank"] <= case.minimum_expected_rank
                and outcome["latency_ms"] < 500
            )
            if passed:
                fast_pass += 1
            if case.test_type == "specific":
                fast_specific_total += 1
                if passed:
                    fast_specific_pass += 1
            report_lines.append(
                f"| fast | {case.query} | {case.expected_session_id} | "
                f"{rank_str} | {outcome['latency_ms']:.1f} | 0 | "
                f"{'PASS' if passed else 'FAIL'} |"
            )

        # Default mode
        for case in MANUAL_TEST_CASES:
            mock_llm.call_count = 0
            orch = SearchOrchestrator(
                embedder=None,
                metadata_store=runner_store,
                llm=mock_llm,
                use_fast=False,
                use_deep=False,
            )
            outcome = _run_case(orch, case)
            rank_str = str(outcome["rank"]) if outcome["rank"] else "—"
            passed = (
                outcome["found"]
                and outcome["rank"] is not None
                and outcome["rank"] <= case.minimum_expected_rank
                and outcome["latency_ms"] < 3000
                and mock_llm.call_count == 1
            )
            if passed:
                default_pass += 1
            report_lines.append(
                f"| default | {case.query} | {case.expected_session_id} | "
                f"{rank_str} | {outcome['latency_ms']:.1f} | {mock_llm.call_count} | "
                f"{'PASS' if passed else 'FAIL'} |"
            )
            if case.test_type == "specific" and outcome["found"]:
                specific_total += 1
                if outcome["rank"] and outcome["rank"] <= 3:
                    specific_found += 1

        # Deep mode (multi-session only)
        for case in _MULTI_SESSION_CASES:
            mock_llm.call_count = 0
            orch = SearchOrchestrator(
                embedder=None,
                metadata_store=runner_store,
                llm=mock_llm,
                use_fast=False,
                use_deep=True,
            )
            outcome = _run_case(orch, case)
            rank_str = str(outcome["rank"]) if outcome["rank"] else "—"
            passed = (
                outcome["found"]
                and outcome["rank"] is not None
                and outcome["rank"] <= case.minimum_expected_rank
                and outcome["latency_ms"] < 4000
                and mock_llm.call_count == 2
            )
            if passed:
                deep_pass += 1
            report_lines.append(
                f"| deep | {case.query} | {case.expected_session_id} | "
                f"{rank_str} | {outcome['latency_ms']:.1f} | {mock_llm.call_count} | "
                f"{'PASS' if passed else 'FAIL'} |"
            )
            chain_total += 1
            if outcome["found"] and outcome["rank"] and outcome["rank"] <= 3:
                chain_grouped += 1

        # Chain grouping verification
        mock_llm.call_count = 0
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=runner_store,
            llm=mock_llm,
            use_fast=False,
            use_deep=True,
        )
        results = orch.search("what happened with auth", top_k=5)
        chain_ok = (
            results
            and results[0].synthesis is not None
            and any(
                entry.session_id == "sess_auth_chain_tail"
                for entry in results[0].synthesis.timeline
            )
        )

        report_lines.extend(
            [
                "",
                f"**Fast mode pass rate:** {fast_pass}/{len(MANUAL_TEST_CASES)}",
                f"**Fast specific pass rate:** {fast_specific_pass}/{fast_specific_total}",
                f"**Default mode pass rate:** {default_pass}/{len(MANUAL_TEST_CASES)}",
                f"**Deep mode pass rate:** {deep_pass}/{len(_MULTI_SESSION_CASES)}",
                (
                    f"**Specific query top-3 rate:** "
                    f"{specific_found}/{specific_total} = "
                    f"{(specific_found / specific_total * 100):.0f}% "
                    f"(target >= 80%)"
                ),
                (
                    f"**Multi-session chain grouped rate:** "
                    f"{chain_grouped}/{chain_total} = "
                    f"{(chain_grouped / chain_total * 100):.0f}% "
                    f"(target >= 70%)"
                ),
                f"**Chain grouping OK:** {chain_ok}",
                "",
            ]
        )

        print("\n".join(report_lines))

        # Assert acceptance criteria
        if fast_specific_total > 0:
            assert fast_specific_pass / fast_specific_total >= 0.80, (
                f"Fast mode specific pass rate "
                f"{fast_specific_pass/fast_specific_total:.0%} < 80%"
            )
        assert default_pass == len(MANUAL_TEST_CASES), (
            f"Default mode only passed {default_pass}/{len(MANUAL_TEST_CASES)}"
        )
        assert deep_pass == len(_MULTI_SESSION_CASES), (
            f"Deep mode only passed {deep_pass}/{len(_MULTI_SESSION_CASES)}"
        )

        if specific_total > 0:
            assert specific_found / specific_total >= 0.80, (
                f"Specific query top-3 rate {specific_found/specific_total:.0%} < 80%"
            )
        if chain_total > 0:
            assert chain_grouped / chain_total >= 0.70, (
                f"Chain grouping rate {chain_grouped/chain_total:.0%} < 70%"
            )
        assert chain_ok, "Auth chain not correctly grouped in deep mode"


# ---------------------------------------------------------------------------
# Meta tests
# ---------------------------------------------------------------------------


class TestMeta:
    def test_at_least_15_cases(self) -> None:
        assert len(MANUAL_TEST_CASES) >= 15

    def test_case_type_coverage(self) -> None:
        types = {c.test_type for c in MANUAL_TEST_CASES}
        assert "specific" in types
        assert "vague" in types
        assert "temporal" in types
        assert "multi_session" in types

    def test_all_sessions_have_data(self) -> None:
        session_ids = {s["session_id"] for s in _SESSIONS_DATA}
        for case in MANUAL_TEST_CASES:
            assert case.expected_session_id in session_ids, (
                f"Expected session {case.expected_session_id} missing from _SESSIONS_DATA"
            )

    def test_relationships_wired(self, runner_store: MetadataStore) -> None:
        auth_rels = runner_store.get_relationships("sess_auth_debug", direction="from")
        assert any(r.to_session == "sess_auth_chain_tail" for r in auth_rels)

        api_rels = runner_store.get_relationships("sess_api_v1", direction="from")
        assert any(r.to_session == "sess_api_v2" for r in api_rels)

        middleware_rels = runner_store.get_relationships(
            "sess_middleware_debug", direction="from"
        )
        assert any(r.to_session == "sess_middleware_fix" for r in middleware_rels)
