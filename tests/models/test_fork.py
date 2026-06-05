"""Tests for fork models."""

from smartfork.models.fork import ContextReport, ForkIntent


class TestForkIntent:
    def test_enum_values(self) -> None:
        assert ForkIntent.CONTINUE == "continue"
        assert ForkIntent.REFERENCE == "reference"
        assert ForkIntent.DEBUG == "debug"
        assert ForkIntent.SYNTHESIZE == "synthesize"

    def test_is_string_enum(self) -> None:
        assert isinstance(ForkIntent.CONTINUE, str)


class TestContextReport:
    def test_defaults(self) -> None:
        cr = ContextReport(
            session_id="abc",
            fork_intent=ForkIntent.REFERENCE,
        )
        assert cr.key_files == []
        assert cr.is_compacted is False
        assert cr.supersession_warning == ""
        assert cr.summary == ""

    def test_full_instantiation(self) -> None:
        cr = ContextReport(
            session_id="abc",
            fork_intent=ForkIntent.DEBUG,
            summary="Fixed auth bug",
            approach="Traced the issue to JWT validation",
            completed="Fixed the middleware",
            remaining="Need to add tests",
            key_files=["auth.py", "middleware.py"],
            key_decisions=["Used JWT over session tokens"],
            code_snippets=["def validate(): ..."],
            gotchas=["Don't use HS256 in production"],
            supersession_warning="This session was superseded by xyz789",
            is_compacted=True,
            gap_analysis="Recovered 3 reasoning blocks from compaction",
        )
        assert cr.fork_intent == ForkIntent.DEBUG
        assert len(cr.key_files) == 2
        assert len(cr.gotchas) == 1
        assert cr.is_compacted is True
