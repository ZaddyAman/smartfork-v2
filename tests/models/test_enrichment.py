"""Tests for session enrichment model."""

import pytest

from smartfork.models.enrichment import SessionEnrichment
from smartfork.models.session import QualityTag


class TestSessionEnrichment:
    def test_basic_creation(self) -> None:
        enrichment = SessionEnrichment(
            title="Fix auth bug",
            summary="Resolved authentication issue in login flow.",
            quality_tag=QualityTag.SOLUTION_FOUND,
            tech_tags=["FastAPI", "JWT", "Python"],
        )
        assert enrichment.title == "Fix auth bug"
        assert enrichment.summary == "Resolved authentication issue in login flow."
        assert enrichment.quality_tag == QualityTag.SOLUTION_FOUND
        assert enrichment.tech_tags == ["FastAPI", "JWT", "Python"]

    def test_quality_tag_validation_valid(self) -> None:
        for tag in ("solution_found", "dead_end", "partial", "reference"):
            enrichment = SessionEnrichment(quality_tag=tag)
            assert enrichment.quality_tag == tag

    def test_quality_tag_validation_invalid(self) -> None:
        with pytest.raises(ValueError, match="quality_tag must be one of"):
            SessionEnrichment(quality_tag="invalid_tag")

    def test_title_truncation(self) -> None:
        long_title = "A" * 100
        enrichment = SessionEnrichment(title=long_title)
        assert len(enrichment.title) == 80
        assert enrichment.title == "A" * 80

    def test_summary_truncation(self) -> None:
        long_summary = "B" * 600
        enrichment = SessionEnrichment(summary=long_summary)
        assert len(enrichment.summary) == 500
        assert enrichment.summary == "B" * 500

    def test_tech_tags_deduplication(self) -> None:
        enrichment = SessionEnrichment(tech_tags=["Python", "FastAPI", "Python", "JWT"])
        assert enrichment.tech_tags == ["FastAPI", "JWT", "Python"]

    def test_tech_tags_sorted_alphabetically(self) -> None:
        enrichment = SessionEnrichment(tech_tags=["Zoo", "Alpha", "Beta"])
        assert enrichment.tech_tags == ["Alpha", "Beta", "Zoo"]

    def test_default_values(self) -> None:
        enrichment = SessionEnrichment()
        assert enrichment.title == ""
        assert enrichment.summary == ""
        assert enrichment.quality_tag == QualityTag.UNKNOWN
        assert enrichment.tech_tags == []
