"""Tests for supersession models."""

from smartfork.models.supersession import (
    SIMILARITY_THRESHOLDS,
    ResolutionStatus,
    SupersessionLink,
)


class TestSupersessionLink:
    def test_defaults(self) -> None:
        link = SupersessionLink(
            superseded_id="old",
            superseding_id="new",
            confidence=0.92,
            detected_at=1_000_000,
        )
        assert link.confidence == 0.92
        assert link.reason == ""

    def test_full_instantiation(self) -> None:
        link = SupersessionLink(
            superseded_id="abc123",
            superseding_id="def456",
            confidence=0.95,
            detected_at=1_700_000_000_000,
            reason="Newer session solved the same error with a better approach",
        )
        assert link.superseded_id == "abc123"
        assert link.superseding_id == "def456"
        assert link.confidence == 0.95
        assert "same error" in link.reason


class TestResolutionStatus:
    def test_defaults(self) -> None:
        rs = ResolutionStatus()
        assert rs.status == "unknown"
        assert rs.signals == []
        assert rs.had_errors is False

    def test_solved_status(self) -> None:
        rs = ResolutionStatus(
            status="solved",
            signals=["Fixed", "Resolved"],
            had_errors=True,
        )
        assert rs.status == "solved"
        assert len(rs.signals) == 2
        assert rs.had_errors is True


class TestSimilarityThresholds:
    def test_is_dict(self) -> None:
        assert isinstance(SIMILARITY_THRESHOLDS, dict)
        assert "default" in SIMILARITY_THRESHOLDS
        assert "error_recall" in SIMILARITY_THRESHOLDS

    def test_values_are_floats(self) -> None:
        for value in SIMILARITY_THRESHOLDS.values():
            assert isinstance(value, float)

    def test_specific_values(self) -> None:
        assert SIMILARITY_THRESHOLDS["error_recall"] == 0.82
        assert SIMILARITY_THRESHOLDS["decision_hunting"] == 0.80
        assert SIMILARITY_THRESHOLDS["default"] == 0.85
