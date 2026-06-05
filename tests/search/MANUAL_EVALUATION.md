# Manual Evaluation: Search Quality Improvements

> **Story:** US-034 — "Manual evaluation: verify search quality improvements with real queries"  
> **Last updated:** 2026-05-24

---

## 1. Purpose

This document provides a structured template for running manual evaluations against a **real indexed database** with real session data. The goal is to verify that the new search architecture (QueryInterpreter → DeterministicSearchEngine → optional deep synthesis) meets the quality and performance acceptance criteria.

> ⚠️ **Important:** The test cases below use **placeholder session IDs**. Before running the evaluation against your own database, replace them with actual session IDs. The automated runner (`test_manual_evaluation_runner.py`) creates its own temporary database with realistic sessions and relationships, so it works out of the box for CI.

---

## 2. Evaluation Methodology

### 2.1 Test Environment Setup

1. Ensure your SmartFork database is indexed with real sessions.
2. Verify the database contains sessions with:
   - **Supersession relationships** (e.g., an old session superseded by a newer one).
   - **Continuation relationships** (e.g., a chain of related sessions on the same topic).
   - **Various quality tags**: `solution_found`, `partial`, `dead_end`, `reference`.
3. Run the automated runner with your database path, or manually execute queries via the CLI/TUI.

### 2.2 Latency Measurement

Use `time.perf_counter()` (Python) or equivalent high-resolution timer:

| Mode      | Expected LLM Calls | Latency Budget | Measurement Window |
|-----------|-------------------|----------------|--------------------|
| Fast      | 0                 | `< 500 ms`     | `t1 - t0` from query submission to first result card rendered |
| Default   | 1                 | `< 3 s`        | `t1 - t0` including QueryInterpreter + deterministic search |
| Deep      | 2                 | `< 4 s`        | `t1 - t0` including QueryInterpreter + deterministic search + SessionGraphEngine + MultiSessionSynthesizer |

**How to measure:**
- The automated runner (`test_manual_evaluation_runner.py`) records latency automatically.
- For manual CLI measurement: `python -m smartfork search "<query>" --mode <fast|default|deep>` and observe total wall-clock time.

### 2.3 LLM Call Counting

| Mode      | Expected LLM Calls | How Verified |
|-----------|-------------------|--------------|
| Fast      | 0                 | Mock LLM `call_count` remains 0; no `complete_structured` or `complete` invocations |
| Default   | 1                 | Exactly one `complete_structured` call from `QueryInterpreter.interpret()` |
| Deep      | 2                 | One `complete_structured` from `QueryInterpreter` + one from `MultiSessionSynthesizer.synthesize_timeline()` |

### 2.4 Rank Measurement

For each query, record the **1-based rank** of the expected session in the returned result list:

- `rank = 1` → first result
- `rank = 2` → second result
- `rank = 3` → third result
- `rank = 0` or `not found` → expected session not in top results

---

## 3. Test Case Definitions (15 Cases)

Each test case includes:
- **query**: The natural language search query.
- **expected_session_id**: The session ID that a human evaluator deems correct.
- **test_type**: `specific`, `vague`, `temporal`, `multi_session`.
- **description**: Why this query is interesting and what it tests.
- **minimum_expected_rank**: The worst acceptable rank (lower is better).

### 3.1 Specific Queries (5 cases)

These contain explicit technical keywords and should be found directly by FTS5/BM25.

| # | Query | Expected Session ID | Test Type | Description | Min Rank |
|---|-------|---------------------|-----------|-------------|----------|
| S1 | `jwt auth bug` | `sess_jwt_fix` | specific | Straightforward keyword match on a well-known technical topic | 1 |
| S2 | `PostgreSQL connection pooling issue` | `sess_postgres_pool` | specific | Multi-word technical phrase requiring BM25 ranking | 1 |
| S3 | `Docker deployment pipeline` | `sess_docker_deploy` | specific | DevOps tooling query with compound terms | 1 |
| S4 | `React component testing with Jest` | `sess_react_test` | specific | Frontend framework + testing library combination | 1 |
| S5 | `OAuth2 implementation with PKCE` | `sess_oauth2_pkce` | specific | Security protocol implementation details | 1 |

### 3.2 Vague Queries (3 cases)

These use casual, imprecise language. They test whether QueryInterpreter expands synonyms and intent correctly.

| # | Query | Expected Session ID | Test Type | Description | Min Rank |
|---|-------|---------------------|-----------|-------------|----------|
| V1 | `that database thing` | `sess_postgres_pool` | vague | No explicit tech keywords; relies on synonym expansion | 2 |
| V2 | `the CSS layout problem` | `sess_css_flexbug` | vague | Informal description; tests intent detection (error_recall) | 2 |
| V3 | `that frontend framework issue` | `sess_react_bug` | vague | Highly ambiguous; requires LLM interpretation to narrow down | 3 |

### 3.3 Temporal Queries (3 cases)

These include time references or ask about past work. They test temporal filtering and recency boosting.

| # | Query | Expected Session ID | Test Type | Description | Min Rank |
|---|-------|---------------------|-----------|-------------|----------|
| T1 | `last week auth fix` | `sess_auth_fix_week2` | temporal | Explicit temporal filter + technical keywords | 2 |
| T2 | `the frontend bug from yesterday` | `sess_frontend_bug_yesterday` | temporal | Very recent temporal reference; tests recency boost | 2 |
| T3 | `what was I doing earlier` | `sess_latest_work` | temporal | Open-ended temporal query; tests continuation detection | 3 |

### 3.4 Multi-Session / Chain Queries (4 cases)

These ask about work that spans multiple sessions. They test the SessionGraphEngine and MultiSessionSynthesizer.

| # | Query | Expected Session ID | Test Type | Description | Min Rank |
|---|-------|---------------------|-----------|-------------|----------|
| M1 | `what happened with auth` | `sess_auth_chain_tail` | multi_session | Narrative across auth-related sessions; deep mode surfaces chain | 1 |
| M2 | `continue my API work` | `sess_api_v2` | multi_session | Tests continuation intent detection and chain head→tail traversal | 1 |
| M3 | `how did I fix the middleware` | `sess_middleware_fix` | multi_session | Solution hunting across a chain that started with a debug session | 2 |
| M4 | `why did I choose OAuth over JWT` | `sess_oauth_decision` | multi_session | Decision hunting; may require synthesis of a comparison session | 2 |

---

## 4. Placeholder Result Tables

> Fill these tables after running the evaluation. The automated runner prints a markdown-compatible summary that you can paste directly into this section.

### 4.1 Fast Mode Results (0 LLM Calls, < 500 ms)

| Test # | Query | Expected ID | Actual Rank | Latency (ms) | Pass / Fail | Notes |
|--------|-------|-------------|-------------|--------------|-------------|-------|
| S1 | jwt auth bug | `sess_jwt_fix` | | | | |
| S2 | PostgreSQL connection pooling issue | `sess_postgres_pool` | | | | |
| S3 | Docker deployment pipeline | `sess_docker_deploy` | | | | |
| S4 | React component testing with Jest | `sess_react_test` | | | | |
| S5 | OAuth2 implementation with PKCE | `sess_oauth2_pkce` | | | | |
| V1 | that database thing | `sess_postgres_pool` | | | | |
| V2 | the CSS layout problem | `sess_css_flexbug` | | | | |
| V3 | that frontend framework issue | `sess_react_bug` | | | | |
| T1 | last week auth fix | `sess_auth_fix_week2` | | | | |
| T2 | the frontend bug from yesterday | `sess_frontend_bug_yesterday` | | | | |
| T3 | what was I doing earlier | `sess_latest_work` | | | | |
| M1 | what happened with auth | `sess_auth_chain_tail` | | | | |
| M2 | continue my API work | `sess_api_v2` | | | | |
| M3 | how did I fix the middleware | `sess_middleware_fix` | | | | |
| M4 | why did I choose OAuth over JWT | `sess_oauth_decision` | | | | |

### 4.2 Default Mode Results (1 LLM Call, < 3 s)

| Test # | Query | Expected ID | Actual Rank | Latency (ms) | LLM Calls | Pass / Fail | Notes |
|--------|-------|-------------|-------------|--------------|-----------|-------------|-------|
| S1 | jwt auth bug | `sess_jwt_fix` | | | | | |
| S2 | PostgreSQL connection pooling issue | `sess_postgres_pool` | | | | | |
| S3 | Docker deployment pipeline | `sess_docker_deploy` | | | | | |
| S4 | React component testing with Jest | `sess_react_test` | | | | | |
| S5 | OAuth2 implementation with PKCE | `sess_oauth2_pkce` | | | | | |
| V1 | that database thing | `sess_postgres_pool` | | | | | |
| V2 | the CSS layout problem | `sess_css_flexbug` | | | | | |
| V3 | that frontend framework issue | `sess_react_bug` | | | | | |
| T1 | last week auth fix | `sess_auth_fix_week2` | | | | | |
| T2 | the frontend bug from yesterday | `sess_frontend_bug_yesterday` | | | | | |
| T3 | what was I doing earlier | `sess_latest_work` | | | | | |
| M1 | what happened with auth | `sess_auth_chain_tail` | | | | | |
| M2 | continue my API work | `sess_api_v2` | | | | | |
| M3 | how did I fix the middleware | `sess_middleware_fix` | | | | | |
| M4 | why did I choose OAuth over JWT | `sess_oauth_decision` | | | | | |

### 4.3 Deep Mode Results (2 LLM Calls, < 4 s)

| Test # | Query | Expected ID | Actual Rank | Latency (ms) | LLM Calls | Pass / Fail | Notes |
|--------|-------|-------------|-------------|--------------|-----------|-------------|-------|
| M1 | what happened with auth | `sess_auth_chain_tail` | | | | | |
| M2 | continue my API work | `sess_api_v2` | | | | | |
| M3 | how did I fix the middleware | `sess_middleware_fix` | | | | | |
| M4 | why did I choose OAuth over JWT | `sess_oauth_decision` | | | | | |

### 4.4 Supersession Annotation Accuracy

For each query that returns a superseded or superseding session, record whether the `ResultCard.supersession_note` is **human-verified accurate**.

| Test # | Query | Superseded Session ID | Superseding Session ID | Card Note Text | Accurate? | Notes |
|--------|-------|----------------------|------------------------|----------------|-----------|-------|
| SS1 | debug auth token failures | `sess_auth_debug` | `sess_auth_chain_tail` | | | |
| SS2 | auth system integration | `sess_auth_debug` | `sess_auth_chain_tail` | | | |
| SS3 | API v1 endpoint design | `sess_api_v1` | `sess_api_v2` | | | |

### 4.5 Multi-Session Chain Grouping

For timeline/multi-session queries, verify that related sessions are correctly grouped into chains.

| Test # | Query | Expected Chain Head | Expected Chain Tail | Chain Type | Correctly Grouped? | Notes |
|--------|-------|---------------------|---------------------|------------|--------------------|-------|
| CH1 | what happened with auth | `sess_auth_debug` | `sess_auth_chain_tail` | linear | | |
| CH2 | continue my API work | `sess_api_v1` | `sess_api_v2` | linear | | |
| CH3 | how did I fix the middleware | `sess_middleware_debug` | `sess_middleware_fix` | linear | | |

---

## 5. Quality Metrics Summary

After filling in the result tables, compute the following metrics.

### 5.1 Specific Query Accuracy (Target: ≥ 80% in top 3)

```
specific_pass_rate = (# of specific queries with actual_rank <= 3) / (total specific queries)
```

**Result:** ____ / 5 = ____ %

### 5.2 Vague Query Accuracy (Target: ≥ 60% in top 3)

```
vague_pass_rate = (# of vague queries with actual_rank <= 3) / (total vague queries)
```

**Result:** ____ / 3 = ____ %

### 5.3 Temporal Query Accuracy (Target: ≥ 70% in top 3)

```
temporal_pass_rate = (# of temporal queries with actual_rank <= 3) / (total temporal queries)
```

**Result:** ____ / 3 = ____ %

### 5.4 Multi-Session Chain Grouping (Target: ≥ 70%)

```
chain_grouping_rate = (# of multi-session queries with correctly grouped chains) / (total multi-session queries)
```

**Result:** ____ / 4 = ____ %

### 5.5 Supersession Annotation Accuracy (Target: 100% by human inspection)

```
supersession_accuracy = (# of verified accurate annotations) / (total supersession annotations checked)
```

**Result:** ____ / ____ = ____ %

### 5.6 Latency Compliance

```
fast_latency_pass = (# of fast-mode queries < 500 ms) / (total fast-mode queries)
default_latency_pass = (# of default-mode queries < 3 s) / (total default-mode queries)
deep_latency_pass = (# of deep-mode queries < 4 s) / (total deep-mode queries)
```

| Mode | Result | Target |
|------|--------|--------|
| Fast | ____ / ____ = ____ % | ≥ 95% |
| Default | ____ / ____ = ____ % | ≥ 90% |
| Deep | ____ / ____ = ____ % | ≥ 85% |

### 5.7 LLM Call Budget Compliance

| Mode | Expected | Actual (from runner) | Pass? |
|------|----------|----------------------|-------|
| Fast | 0 | | |
| Default | 1 | | |
| Deep | 2 | | |

---

## 6. Instructions for Running the Automated Evaluation

### 6.1 Using the pytest runner (recommended for CI)

The file `tests/search/test_manual_evaluation_runner.py` contains an automated runner that:
1. Creates a temporary database with 17 realistic sessions.
2. Adds continuation and supersession relationships.
3. Runs all 15 test cases in fast, default, and deep modes.
4. Measures latency with `time.perf_counter()`.
5. Counts LLM calls via a mocked LLM.
6. Checks supersession annotations on result cards.
7. Verifies multi-session chain grouping via `SessionGraphEngine`.

Run it with:

```bash
# Full runner (uses mocked data, safe for CI)
pytest tests/search/test_manual_evaluation_runner.py -v --tb=short

# Just the meta-tests (count, schema, etc.)
pytest tests/search/test_manual_evaluation_runner.py::TestMeta -v
```

### 6.2 Using the runner against a real database

To evaluate against your **real** indexed database, export your database path and run a custom script:

```python
# custom_eval.py
from pathlib import Path
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.search.orchestrator import SearchOrchestrator
from smartfork.search.deterministic import DeterministicSearchEngine

# Replace with your actual DB path
db_path = Path.home() / ".smartfork" / "metadata.db"
store = MetadataStore(db_path)

# Build orchestrator with real providers (or mock LLM for cost control)
orchestrator = SearchOrchestrator(
    embedder=...,      # your embedder
    metadata_store=store,
    llm=...,           # your LLM or a mock
)

# Run queries and record results manually into the tables above.
```

### 6.3 Manual CLI Evaluation

```bash
# Fast mode
python -m smartfork search "jwt auth bug" --fast

# Default mode
python -m smartfork search "jwt auth bug"

# Deep mode
python -m smartfork search "what happened with auth" --deep
```

For each query, note:
1. Does the expected session appear in the top 3?
2. What is the wall-clock latency?
3. Are supersession notes accurate?
4. In deep mode, are related sessions grouped into a chain?

---

## 7. Acceptance Criteria Checklist

- [ ] **AC-1:** 10–20 manual test cases defined (15 provided above).
- [ ] **AC-2:** Query types covered: specific, vague, temporal, multi-session.
- [ ] **AC-3:** Fast mode latency < 500 ms for ≥ 95% of queries.
- [ ] **AC-4:** Default mode latency < 3 s for ≥ 90% of queries.
- [ ] **AC-5:** Deep mode latency < 4 s for ≥ 85% of queries.
- [ ] **AC-6:** Fast mode uses 0 LLM calls per query.
- [ ] **AC-7:** Default mode uses 1 LLM call per query.
- [ ] **AC-8:** Deep mode uses 2 LLM calls per query.
- [ ] **AC-9:** Expected session found in top 3 for ≥ 80% of specific queries.
- [ ] **AC-10:** Multi-session chains correctly grouped for ≥ 70% of timeline queries.
- [ ] **AC-11:** Supersession annotations are accurate (verified by human inspection).
- [ ] **AC-12:** All existing automated tests still pass (`pytest tests/ -x`).

---

## 8. Notes for Evaluators

1. **Database freshness:** If your database is stale (sessions older than the query's temporal filter), temporal queries may fail. Ensure you have recent sessions or adjust temporal expectations.
2. **LLM variability:** When using a real LLM, slight variations in `QueryInterpretation.expanded_query` may cause rank shifts between runs. Run each query 3× and take the median rank for stable results.
3. **Vector search availability:** If `sqlite-vec` is not installed, vector search is skipped and results rely purely on FTS5. This is expected and should still meet accuracy targets for specific queries.
4. **Relationship data:** Multi-session and supersession tests require explicit relationships in the database. If your indexer has not yet created these links, populate them manually via `MetadataStore.add_relationship()` before evaluation.
5. **Placeholder IDs:** The test runner uses the placeholder IDs from Section 3. Replace them with your actual IDs for a meaningful real-world evaluation.
