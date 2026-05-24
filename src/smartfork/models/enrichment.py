"""Session enrichment models for SmartFork v2."""

from dataclasses import dataclass, field

from smartfork.models.session import QualityTag


@dataclass
class SessionEnrichment:
    """Enrichment data produced for a session (title, summary, tags, etc.)."""

    title: str = ""
    summary: str = ""
    quality_tag: QualityTag = QualityTag.UNKNOWN
    tech_tags: list[str] = field(default_factory=list)

    _MAX_TITLE_LEN: int = 80
    _MAX_SUMMARY_LEN: int = 500

    def __post_init__(self) -> None:
        if isinstance(self.quality_tag, str):
            try:
                self.quality_tag = QualityTag(self.quality_tag)
            except ValueError as exc:
                valid = [tag.value for tag in QualityTag]
                raise ValueError(
                    f"quality_tag must be one of {valid}, got '{self.quality_tag}'"
                ) from exc
        if len(self.title) > self._MAX_TITLE_LEN:
            self.title = self.title[: self._MAX_TITLE_LEN]
        if len(self.summary) > self._MAX_SUMMARY_LEN:
            self.summary = self.summary[: self._MAX_SUMMARY_LEN]
        self.tech_tags = sorted(set(self.tech_tags))
