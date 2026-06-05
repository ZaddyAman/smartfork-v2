"""Tests for query generator."""

from smartfork.eval.query_generator import QueryGenerator, _build_heuristic_query


class TestHeuristicQuery:
    def test_short_query(self) -> None:
        sess = {"tech_tags": ["OAuth", "JWT"], "domains": ["auth"]}
        q = _build_heuristic_query(sess, "short")
        assert q == "OAuth JWT"

    def test_short_fallback_to_domain(self) -> None:
        sess = {"tech_tags": [], "domains": ["database"]}
        q = _build_heuristic_query(sess, "short")
        assert q == "database"

    def test_vague_error(self) -> None:
        sess = {"task_raw": "Fix bug in auth"}
        q = _build_heuristic_query(sess, "vague")
        assert "error" in q.lower()

    def test_vague_build(self) -> None:
        sess = {"task_raw": "Implement new dashboard"}
        q = _build_heuristic_query(sess, "vague")
        assert "building" in q.lower()

    def test_specific(self) -> None:
        sess = {"task_raw": "Set up OAuth", "tech_tags": ["auth", "JWT"]}
        q = _build_heuristic_query(sess, "specific")
        assert "OAuth" in q


class TestQueryGenerator:
    def test_heuristic_fallback_no_llm(self) -> None:
        gen = QueryGenerator(llm=None)
        sess = {
            "session_id": "test-1",
            "task_raw": "Fix OAuth bug",
            "summary_doc": "Fixed OAuth issue",
            "tech_tags": ["OAuth"],
            "domains": ["auth"],
            "files_edited": ["auth.py"],
        }
        queries = gen.generate(sess)
        assert len(queries) == 3
        types = {q.query_type for q in queries}
        assert types == {"specific", "short", "vague"}
        for q in queries:
            assert q.source_session_id == "test-1"
