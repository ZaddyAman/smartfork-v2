"""QueryDecomposer agent with structured output for SmartFork v2."""

from loguru import logger

from smartfork.models.search import QueryDecomposition
from smartfork.providers.protocols import LLMProvider

_QUERY_DECOMPOSITION_PROMPT = (
    "You are a query decomposition specialist for a developer session "
    "search system.\n\n"
    "Your task is to analyze the user's search query and break it down "
    "into a structured representation that will help find relevant "
    "coding sessions.\n\n"
    "USER QUERY: {query}\n\n"
    "Generate 3-5 diverse search variants that capture different keyword "
    "and synonym combinations. Each variant should rephrase the query in "
    "a way that might match different session descriptions.\n\n"
    "Examples of GOOD search variants:\n"
    '- Query: "how did I fix the auth bug"\n'
    '  Variants: ["fix authentication bug", "auth error resolution", '
    '"login issue debugging", "authentication failure fix", '
    '"how to fix auth problem"]\n\n'
    '- Query: "implement jwt middleware"\n'
    '  Variants: ["jwt middleware implementation", '
    '"add json web token middleware", '
    '"implement token authentication middleware", '
    '"jwt auth middleware code", "setup jwt middleware"]\n\n'
    "Examples of BAD search variants (too similar or missing key "
    "concepts):\n"
    '- Query: "how did I fix the auth bug"\n'
    '  Bad: ["how did I fix the auth bug", '
    '"how did I fix the auth bug?", "fix the auth bug"]  '
    "(nearly identical)\n\n"
    '- Query: "implement jwt middleware"\n'
    '  Bad: ["implement middleware", "jwt implementation", '
    '"middleware code"]  (missing key concepts)\n\n'
    "Extract entities as a dictionary of relevant technologies, "
    "concepts, and file types mentioned. Determine the search intent, "
    "whether recent results are preferred, and whether code-heavy "
    "sessions should be preferred.\n\n"
    "Return your analysis as the requested structured format."
)


class QueryDecomposer:
    """LLM-based query decomposer that produces structured QueryDecomposition."""

    def __init__(self, llm: LLMProvider) -> None:
        """Initialize with an LLM provider.

        Args:
            llm: An LLMProvider that supports complete_structured().
        """
        self.llm = llm

    def decompose(self, query: str) -> QueryDecomposition:
        """Decompose a user query into structured search parameters.

        Uses the LLM to generate diverse search variants, extract entities,
        and determine search preferences. Falls back gracefully if the LLM
        fails, returning a minimal decomposition with only the original query
        as a search variant.

        Args:
            query: The raw user search query.

        Returns:
            A QueryDecomposition with generated variants and metadata.
        """
        prompt = _QUERY_DECOMPOSITION_PROMPT.format(query=query)
        try:
            result = self.llm.complete_structured(
                prompt=prompt,
                output_schema=QueryDecomposition,
                max_tokens=800,
                temperature=0.1,
            )
            if isinstance(result, QueryDecomposition):
                # Ensure at least the original query is present if no variants
                if not result.search_variants:
                    result.search_variants = [query]
                return result
        except Exception as e:
            logger.warning(f"QueryDecomposer LLM call failed: {e}")

        # Graceful fallback
        return QueryDecomposition(
            core_goal=query,
            search_variants=[query],
        )
