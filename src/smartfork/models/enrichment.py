"""Session enrichment models for SmartFork v2."""

from pydantic import BaseModel, Field, field_validator

from smartfork.models.session import QualityTag


class SessionEnrichment(BaseModel):
    """Enrichment data produced for a session (title, summary, tags, etc.)."""

    title: str = ""
    summary: str = ""
    quality_tag: QualityTag = QualityTag.UNKNOWN
    tech_tags: list[str] = Field(default_factory=list)

    _MAX_TITLE_LEN: int = 80
    _MAX_SUMMARY_LEN: int = 500

    @field_validator("quality_tag", mode="before")
    @classmethod
    def _validate_quality_tag(cls, value: object) -> QualityTag:
        if isinstance(value, QualityTag):
            return value
        if isinstance(value, str):
            try:
                return QualityTag(value)
            except ValueError as exc:
                valid = [tag.value for tag in QualityTag]
                raise ValueError(
                    f"quality_tag must be one of {valid}, got '{value}'"
                ) from exc
        raise ValueError(f"quality_tag must be a string or QualityTag, got {type(value)}")

    @field_validator("title")
    @classmethod
    def _truncate_title(cls, value: str) -> str:
        max_len = 80
        if len(value) > max_len:
            return value[:max_len]
        return value

    @field_validator("summary")
    @classmethod
    def _truncate_summary(cls, value: str) -> str:
        max_len = 500
        if len(value) > max_len:
            return value[:max_len]
        return value

    @field_validator("tech_tags")
    @classmethod
    def _dedup_and_sort_tech_tags(cls, value: list[str]) -> list[str]:
        return sorted(set(value))
