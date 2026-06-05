"""Manual evaluation test suite for the rewritten orchestrator (US-025).

Each test case uses a query that does NOT contain keywords matching the
expected session, ensuring deterministic search alone misses it.  A mocked
QueryInterpreter injects an *expanded_query* that contains the matching
keywords, allowing the orchestrator to retrieve the expected session.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.query import QueryInterpretation
from smartfork.models.session import QualityTag, SessionDocument
from smartfork.search.deterministic import DeterministicSearchEngine
from smartfork.search.orchestrator import SearchOrchestrator

# ---------------------------------------------------------------------------
# Session data — 12 realistic sessions with unique, non-overlapping keywords
# ---------------------------------------------------------------------------
_SESSIONS_DATA: list[dict[str, Any]] = [
    {
        "session_id": "sess_jwt_middleware",
        "task_raw": "Implement JWT authentication middleware for FastAPI endpoints",
        "summary_doc": (
            "Created a custom middleware class that validates JWT tokens "
            "on every incoming request. Uses PyJWT library with RS256 algorithm. "
            "Tokens are extracted from Authorization header."
        ),
        "domains": ["backend", "security"],
        "languages": ["python"],
        "tech_tags": ["fastapi", "jwt", "middleware", "pyjwt"],
    },
    {
        "session_id": "sess_alembic_migration",
        "task_raw": "Create Alembic migration for user preferences table in PostgreSQL",
        "summary_doc": (
            "Generated revision file adding columns for theme, notifications, "
            "and timezone preferences. Applied upgrade to staging environment."
        ),
        "domains": ["database"],
        "languages": ["python", "sql"],
        "tech_tags": ["alembic", "postgresql", "migration", "sqlalchemy"],
    },
    {
        "session_id": "sess_react_hooks",
        "task_raw": "Build custom useDebounce hook for React search component",
        "summary_doc": (
            "Implemented a debounce hook that delays state updates until the "
            "user stops entering text for 300ms. Uses useEffect and useRef to "
            "manage timer cleanup."
        ),
        "domains": ["frontend"],
        "languages": ["javascript", "typescript"],
        "tech_tags": ["react", "hooks", "debounce"],
    },
    {
        "session_id": "sess_docker_compose",
        "task_raw": "Configure multi-service Docker Compose with Nginx reverse proxy",
        "summary_doc": (
            "Set up docker-compose.yml with three services: web app, postgres, "
            "and nginx. Configured nginx to route traffic and handle SSL termination."
        ),
        "domains": ["devops"],
        "languages": ["yaml"],
        "tech_tags": ["docker", "nginx", "compose"],
    },
    {
        "session_id": "sess_kubernetes_crd",
        "task_raw": "Define Kubernetes Custom Resource Definition for canary deployments",
        "summary_doc": (
            "Created CRD manifest with OpenAPI v3 schema for canary rollout "
            "parameters. Wrote controller loop to reconcile desired state with "
            "cluster resources."
        ),
        "domains": ["devops"],
        "languages": ["yaml"],
        "tech_tags": ["kubernetes", "crd", "canary"],
    },
    {
        "session_id": "sess_graphql_resolver",
        "task_raw": "Implement nested GraphQL resolver with DataLoader batching",
        "summary_doc": (
            "Built resolver functions for user, posts, and comments types. "
            "Integrated DataLoader to batch N+1 queries into single SQL statements."
        ),
        "domains": ["backend"],
        "languages": ["typescript"],
        "tech_tags": ["graphql", "dataloader", "resolver"],
    },
    {
        "session_id": "sess_cypress_e2e",
        "task_raw": "Write Cypress end-to-end tests for checkout flow",
        "summary_doc": (
            "Created test specs covering cart page, shipping form, payment "
            "selection, and order confirmation. Added custom commands for auth "
            "and checkout helpers."
        ),
        "domains": ["testing"],
        "languages": ["javascript"],
        "tech_tags": ["cypress", "e2e", "checkout"],
    },
    {
        "session_id": "sess_redis_cache",
        "task_raw": "Set up Redis caching layer with TTL for product catalog",
        "summary_doc": (
            "Configured Redis client with connection pooling. Implemented "
            "cache-aside strategy for product lookups. Set TTL to 3600 seconds "
            "for catalog entries."
        ),
        "domains": ["backend"],
        "languages": ["python"],
        "tech_tags": ["redis", "cache", "ttl"],
    },
    {
        "session_id": "sess_terraform_aws",
        "task_raw": "Provision AWS ECS Fargate cluster using Terraform modules",
        "summary_doc": (
            "Wrote Terraform modules for VPC, ECS service, ALB, and IAM roles. "
            "State is stored in S3 backend with DynamoDB locking. Supports "
            "multiple environments via workspaces."
        ),
        "domains": ["devops"],
        "languages": ["hcl"],
        "tech_tags": ["terraform", "aws", "ecs"],
    },
    {
        "session_id": "sess_pandas_etl",
        "task_raw": "Build pandas ETL pipeline for sales data aggregation",
        "summary_doc": (
            "Developed data pipeline that reads CSV exports, performs groupby "
            "operations, calculates monthly revenue, and writes results to parquet "
            "files."
        ),
        "domains": ["data"],
        "languages": ["python"],
        "tech_tags": ["pandas", "etl", "aggregation"],
    },
    {
        "session_id": "sess_flask_oauth",
        "task_raw": "Integrate OAuth2 provider with Flask using Authlib",
        "summary_doc": (
            "Implemented OAuth2 authorization code flow with PKCE. Configured "
            "Flask routes for auth callback and token refresh. Session tokens "
            "stored in httpOnly cookies."
        ),
        "domains": ["backend", "security"],
        "languages": ["python"],
        "tech_tags": ["flask", "oauth2", "authlib"],
    },
    {
        "session_id": "sess_rust_cli",
        "task_raw": "Create Rust CLI tool with Clap for argument parsing",
        "summary_doc": (
            "Built a command-line tool using structopt-style derive macros. "
            "Supports subcommands, options, and positional arguments with "
            "validation and help generation."
        ),
        "domains": ["backend"],
        "languages": ["rust"],
        "tech_tags": ["rust", "cli", "clap"],
    },
]

# ---------------------------------------------------------------------------
# Manual test cases
# ---------------------------------------------------------------------------
@dataclass
class ManualTestCase:
    """A single manual evaluation case.

    The ``query`` uses vocabulary that does NOT overlap with the expected
    session, so deterministic search fails.  The ``mock_variants`` contain
    keywords that DO overlap; the mocked QueryInterpreter returns an
    expanded_query built from them so the orchestrator can succeed.
    """

    query: str
    expected_session_id: str
    description: str
    mock_variants: list[str]
    minimum_expected_rank: int = 1


MANUAL_TEST_CASES: list[ManualTestCase] = [
    ManualTestCase(
        query="how did I secure the API gateway",
        expected_session_id="sess_jwt_middleware",
        description="User remembers securing API but not JWT specifics",
        mock_variants=[
            "jwt authentication middleware",
            "fastapi endpoints token",
            "pyjwt library middleware",
        ],
    ),
    ManualTestCase(
        query="relational schema evolution process",
        expected_session_id="sess_alembic_migration",
        description="User remembers schema changes but not Alembic or PostgreSQL",
        mock_variants=[
            "alembic migration postgresql",
            "user preferences table",
            "sqlalchemy revision file",
        ],
    ),
    ManualTestCase(
        query="typing delay workaround",
        expected_session_id="sess_react_hooks",
        description="User remembers typing delay but not React or debounce",
        mock_variants=[
            "react search component",
            "hook usedebounce",
            "state delays 300ms",
        ],
    ),
    ManualTestCase(
        query="container orchestration setup",
        expected_session_id="sess_docker_compose",
        description="User remembers container setup but not Docker Compose or Nginx",
        mock_variants=[
            "docker compose multi service",
            "nginx reverse proxy",
            "ssl termination",
        ],
    ),
    ManualTestCase(
        query="progressive deployment configuration",
        expected_session_id="sess_kubernetes_crd",
        description="User remembers progressive deployment but not Kubernetes CRD",
        mock_variants=[
            "kubernetes custom resource definition",
            "canary deployments crd",
            "reconcile desired state",
        ],
    ),
    ManualTestCase(
        query="efficient data fetching pattern",
        expected_session_id="sess_graphql_resolver",
        description="User remembers efficient data fetching but not GraphQL or DataLoader",
        mock_variants=[
            "graphql resolver dataloader",
            "nested query batching",
            "sql statements",
        ],
    ),
    ManualTestCase(
        query="automated purchase verification",
        expected_session_id="sess_cypress_e2e",
        description="User remembers automated purchase checks but not Cypress",
        mock_variants=[
            "cypress end to end tests",
            "checkout flow testing",
            "payment selection verification",
        ],
    ),
    ManualTestCase(
        query="ephemeral high speed datastore",
        expected_session_id="sess_redis_cache",
        description="User remembers fast temporary storage but not Redis or TTL",
        mock_variants=[
            "redis caching layer",
            "product catalog",
            "ttl seconds",
        ],
    ),
    ManualTestCase(
        query="infrastructure as code for containers",
        expected_session_id="sess_terraform_aws",
        description="User remembers IaC for containers but not Terraform or AWS ECS",
        mock_variants=[
            "terraform aws ecs",
            "fargate cluster",
            "dynamodb locking",
        ],
    ),
    ManualTestCase(
        query="tabular value transformation process",
        expected_session_id="sess_pandas_etl",
        description="User remembers tabular transformations but not pandas or ETL",
        mock_variants=[
            "pandas etl pipeline",
            "sales data aggregation",
            "csv parquet files",
        ],
    ),
    ManualTestCase(
        query="third party login integration",
        expected_session_id="sess_flask_oauth",
        description="User remembers third-party login but not OAuth2 or Flask",
        mock_variants=[
            "oauth2 provider flask",
            "authlib authorization",
            "token refresh",
        ],
    ),
    ManualTestCase(
        query="terminal utility flags",
        expected_session_id="sess_rust_cli",
        description="User remembers terminal tool with flags but not Rust or Clap",
        mock_variants=[
            "rust cli clap",
            "command-line tool",
            "derive macros",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def manual_store(tmp_path: Path) -> MetadataStore:
    """MetadataStore with 12 realistic sessions pre-loaded."""
    db_path = tmp_path / "manual.db"
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
            languages=data["languages"],
            tech_tags=data["tech_tags"],
        )
        store.upsert_session(doc)
    return store


# ---------------------------------------------------------------------------
# Deterministic search should FAIL to find the expected session
# ---------------------------------------------------------------------------
class TestDeterministicFails:
    @pytest.mark.parametrize("case", MANUAL_TEST_CASES)
    def test_deterministic_fails_to_find_expected_session(
        self, manual_store: MetadataStore, case: ManualTestCase
    ) -> None:
        engine = DeterministicSearchEngine(metadata_store=manual_store)
        results = engine.search(case.query, top_k=5)
        session_ids = [r.session_id for r in results]
        assert case.expected_session_id not in session_ids, (
            f"Deterministic search unexpectedly found {case.expected_session_id} "
            f"for query '{case.query}'. Results: {session_ids}"
        )


# ---------------------------------------------------------------------------
# Orchestrator (with mocked QueryInterpreter) should find the expected session
# ---------------------------------------------------------------------------
class TestOrchestratorFindsSession:
    @pytest.mark.parametrize("case", MANUAL_TEST_CASES)
    def test_orchestrator_finds_expected_session(
        self, manual_store: MetadataStore, case: ManualTestCase
    ) -> None:
        # Build a mock QueryInterpreter that returns an expanded_query
        # containing all the mock variants so BM25 can match.
        mock_interpreter = MagicMock()
        expanded = " OR ".join(case.mock_variants)
        mock_interpreter.interpret.return_value = QueryInterpretation(
            original_query=case.query,
            keywords=[],
            synonyms=[],
            expanded_query=expanded,
            intent="vague_memory",
            needs_deep_mode=False,
        )

        engine = DeterministicSearchEngine(metadata_store=manual_store)
        orchestrator = SearchOrchestrator(
            embedder=None,
            metadata_store=manual_store,
            llm=MagicMock(),
        )
        # Swap in mocked interpreter and real engine
        orchestrator.interpreter = mock_interpreter  # type: ignore[assignment]
        orchestrator.engine = engine  # type: ignore[assignment]

        results = orchestrator.search(case.query, top_k=5)

        # Locate expected session and assert rank
        for idx, card in enumerate(results):
            if card.session_id == case.expected_session_id:
                actual_rank = idx + 1
                assert actual_rank <= case.minimum_expected_rank, (
                    f"Expected session {case.expected_session_id} found at rank "
                    f"{actual_rank}, but minimum expected was "
                    f"{case.minimum_expected_rank}"
                )
                return

        found_ids = [c.session_id for c in results]
        pytest.fail(
            f"Expected session {case.expected_session_id} not found in orchestrator "
            f"results for query '{case.query}'. Found: {found_ids}"
        )


# ---------------------------------------------------------------------------
# Meta-test
# ---------------------------------------------------------------------------
def test_at_least_10_cases() -> None:
    assert len(MANUAL_TEST_CASES) >= 10
