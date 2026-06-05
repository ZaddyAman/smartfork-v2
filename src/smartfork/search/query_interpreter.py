"""Query interpreter — single LLM call for query understanding."""

import json
import string
from typing import Any

from loguru import logger

from smartfork.models.query import QueryInterpretation
from smartfork.providers.protocols import LLMProvider

# Hardcoded synonym dictionary
SYNONYM_MAP: dict[str, list[str]] = {
    "auth": ["authentication", "login", "oauth", "jwt", "sso", "token"],
    "bug": ["error", "fix", "issue", "crash", "defect", "exception"],
    "db": ["database", "postgresql", "mysql", "sqlite", "mongodb", "sql"],
    "api": ["endpoint", "rest", "graphql", "route", "handler", "controller"],
    "ui": ["frontend", "interface", "component", "page", "view", "screen"],
    "test": ["testing", "unit test", "integration", "coverage", "mock"],
    "deploy": ["deployment", "release", "pipeline", "ci/cd", "ship"],
    "perf": ["performance", "slow", "optimize", "speed", "latency"],
    "config": ["configuration", "settings", "env", "environment", ".env"],
    "security": ["vulnerability", "xss", "csrf", "injection", "encryption"],
}

# Temporal keywords (high multi-session confidence)
TEMPORAL_WORDS: set[str] = {
    "last week",
    "yesterday",
    "across sessions",
    "history",
    "previously",
    "before",
    "earlier",
    "timeline",
    "journey",
}

# Continuation keywords (very high multi-session confidence)
CONTINUATION_WORDS: set[str] = {
    "continue",
    "resume",
    "pick up",
    "carry on",
    "ongoing",
    "next steps",
    "follow up",
    "what happened with",
}

# Specific/technical keywords (low multi-session confidence — single session likely)
SPECIFIC_KEYWORDS: set[str] = {
    "jwt",
    "bug",
    "fix",
    "error",
    "crash",
    "implement",
    "add",
    "create",
    "build",
    "write",
    "change",
    "update",
}

# Intent detection patterns (ordered by specificity)
_INTENT_PATTERNS: dict[str, list[str]] = {
    "continuation": ["continue", "resume", "pick up", "carry on", "ongoing"],
    "temporal_lookup": ["last week", "yesterday", "before", "earlier", "timeline"],
    "decision_hunting": ["why", "decide", "choice", "decision"],
    "error_recall": ["error", "bug", "crash", "exception"],
    "implementation_lookup": ["implement", "build", "create", "how to"],
    "solution_hunting": ["how", "solve", "fix", "solution", "debug"],
}

_STOP_WORDS: set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "can",
    "this",
    "that",
    "these",
    "those",
    "i",
    "me",
    "my",
    "we",
    "our",
    "you",
    "your",
    "he",
    "she",
    "it",
    "they",
    "them",
    "their",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "all",
    "any",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "now",
    "then",
    "here",
    "there",
    "up",
    "down",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "once",
    "also",
    "if",
    "because",
    "until",
    "while",
    "about",
    "against",
    "between",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "am",
    "its",
    "itself",
}


class QueryInterpreter:
    """Interprets natural language queries for the search pipeline.

    Uses 1 structured LLM call for full interpretation, with deterministic
    fallback when LLM is unavailable.
    """

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    def interpret(self, query: str, deep_mode: bool = False) -> QueryInterpretation:
        """Interpret a user query.

        If LLM available: 1 structured call returns all fields.
        If LLM unavailable: deterministic keyword + pattern extraction.
        """
        if self.llm:
            try:
                return self._llm_interpret(query, deep_mode=deep_mode)
            except Exception as e:
                logger.warning(f"LLM interpretation failed: {e}. Using deterministic fallback.")
        return self._deterministic_interpret(query, deep_mode=deep_mode)

    def _llm_interpret(self, query: str, deep_mode: bool = False) -> QueryInterpretation:
        """Use structured LLM call for full interpretation."""
        assert self.llm is not None
        prompt = _build_prompt(query)

        if hasattr(self.llm, "complete_structured"):
            result = self.llm.complete_structured(
                prompt=prompt,
                output_schema=QueryInterpretation,
                max_tokens=500,
                temperature=0.1,
            )
            if isinstance(result, QueryInterpretation):
                result.original_query = query
                result.expanded_query = self._build_expanded_query(
                    result.keywords, result.synonyms
                ) or query
                result.needs_deep_mode = result.multi_session_confidence > 0.75 or deep_mode
                if not result.quality_boost:
                    result.quality_boost = (
                        ["solution_found"] if result.intent == "solution_hunting" else []
                    )
                return result
            if isinstance(result, dict):
                return self._dict_to_interpretation(result, query, deep_mode=deep_mode)

        # Fallback to text parsing if structured unavailable
        text_result = self.llm.complete(prompt, max_tokens=500, temperature=0.1)
        return self._parse_interpretation(str(text_result), query, deep_mode=deep_mode)

    def _parse_interpretation(
        self, text: str, query: str, deep_mode: bool = False
    ) -> QueryInterpretation:
        """Parse text response into QueryInterpretation."""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return self._dict_to_interpretation(data, query, deep_mode=deep_mode)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        return self._deterministic_interpret(query, deep_mode=deep_mode)

    def _dict_to_interpretation(
        self, data: dict[str, Any], query: str, deep_mode: bool = False
    ) -> QueryInterpretation:
        """Convert a dict to QueryInterpretation with sensible defaults."""
        keywords = data.get("keywords", [])
        synonyms = data.get("synonyms", [])
        intent = data.get("intent", "vague_memory")
        confidence = data.get("multi_session_confidence", 0.0)
        return QueryInterpretation(
            original_query=query,
            keywords=keywords,
            synonyms=synonyms,
            expanded_query=self._build_expanded_query(keywords, synonyms) or query,
            intent=intent,
            multi_session_confidence=confidence,
            needs_deep_mode=confidence > 0.75 or deep_mode,
            project_hint=data.get("project_hint"),
            quality_boost=data.get("quality_boost")
            or (["solution_found"] if intent == "solution_hunting" else []),
            temporal_filter=data.get("temporal_filter"),
        )

    def _deterministic_interpret(
        self, query: str, deep_mode: bool = False
    ) -> QueryInterpretation:
        """Deterministic keyword + pattern extraction."""
        query_lower = query.lower()

        keywords = self._extract_keywords(query_lower)
        synonyms = self._expand_synonyms(keywords)
        intent = self._detect_intent(query_lower)
        confidence = self._compute_confidence(query_lower)

        return QueryInterpretation(
            original_query=query,
            keywords=keywords,
            synonyms=synonyms,
            expanded_query=self._build_expanded_query(keywords, synonyms) or query,
            intent=intent,
            multi_session_confidence=confidence,
            needs_deep_mode=confidence > 0.75 or deep_mode,
            project_hint=None,
            quality_boost=["solution_found"] if intent == "solution_hunting" else [],
            temporal_filter=None,
        )

    def _extract_keywords(self, query_lower: str) -> list[str]:
        """Extract lowercase keywords from query."""
        translator = str.maketrans("", "", string.punctuation)
        cleaned = query_lower.translate(translator)
        words = cleaned.split()
        filtered = [w for w in words if w not in _STOP_WORDS and len(w) > 2]
        return filtered[:5]

    def _expand_synonyms(self, keywords: list[str]) -> list[str]:
        """Expand keywords using hardcoded synonym dictionary."""
        seen = set(keywords)
        synonyms: list[str] = []
        for word in keywords:
            if word in SYNONYM_MAP:
                for syn in SYNONYM_MAP[word]:
                    if syn not in seen:
                        seen.add(syn)
                        synonyms.append(syn)
        return synonyms

    def _detect_intent(self, query_lower: str) -> str:
        """Detect intent from query patterns."""
        for intent, patterns in _INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in query_lower:
                    return intent
        return "vague_memory"

    def _compute_confidence(self, query_lower: str) -> float:
        """Compute multi_session_confidence based on query patterns."""
        if any(word in query_lower for word in TEMPORAL_WORDS):
            return 0.80
        if any(word in query_lower for word in CONTINUATION_WORDS):
            return 0.85
        if any(word in query_lower for word in SPECIFIC_KEYWORDS):
            return 0.30
        return 0.50

    def _build_expanded_query(self, keywords: list[str], synonyms: list[str]) -> str:
        """Build expanded query string for FTS5."""
        all_terms = list(dict.fromkeys(keywords + synonyms))
        return " OR ".join(all_terms) if all_terms else ""


def _build_prompt(query: str) -> str:
    """Build the LLM prompt for structured interpretation."""
    synonym_lines = "\n".join(f'  "{k}": {v}' for k, v in SYNONYM_MAP.items())
    return (
        "You are a query interpretation specialist for a developer session "
        "search system.\n\n"
        f'Analyze this search query and return structured JSON:\n\nQuery: "{query}"\n\n'
        "Return JSON with these fields:\n"
        '  keywords: list of 1-5 technical keywords\n'
        '  synonyms: list of related terms (use the synonym dictionary below)\n'
        '  intent: one of [solution_hunting, error_recall, continuation, '
        'temporal_lookup, decision_hunting, implementation_lookup, vague_memory]\n'
        '  multi_session_confidence: float 0.0-1.0\n'
        '  project_hint: project name if mentioned, else null\n'
        '  quality_boost: ["solution_found"] if hunting for solutions, else []\n'
        '  temporal_filter: null or {type: "relative", value: "last_week"}\n\n'
        "Rules for multi_session_confidence:\n"
        "  >0.75 if query contains temporal words (timeline, history, etc.)\n"
        "  >0.80 if query contains continuation words (continue, resume, etc.)\n"
        "  <0.40 if only specific technical keywords (jwt, bug, fix, etc.)\n"
        "  0.40-0.75 otherwise\n\n"
        "Synonym dictionary (use for expansion):\n"
        f"{synonym_lines}\n\n"
        "Return ONLY valid JSON, no markdown formatting."
    )
