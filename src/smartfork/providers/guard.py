"""Embedding model change protection for SmartFork v2."""


class EmbeddingModelGuard:
    """Protects against incompatible embedding model changes."""

    @staticmethod
    def check_compatibility(
        current_model: str,
        current_dims: int,
        new_model: str,
        new_dims: int,
    ) -> bool:
        """Check if two embedding models are compatible (same dimensions).

        Args:
            current_model: Name of the currently configured model.
            current_dims: Dimension count of the current model.
            new_model: Name of the new model being switched to.
            new_dims: Dimension count of the new model.

        Returns:
            True if models are compatible, False otherwise.
        """
        if current_model == new_model:
            return True
        return current_dims == new_dims

    @staticmethod
    def get_warning_message(
        current_model: str,
        new_model: str,
        session_count: int,
    ) -> str:
        """Generate a user-friendly warning about re-index requirements.

        Args:
            current_model: Name of the currently configured model.
            new_model: Name of the new model being switched to.
            session_count: Number of currently indexed sessions.

        Returns:
            A formatted warning message string.
        """
        return (
            f"⚠ Changing embedding model from '{current_model}' to '{new_model}' "
            f"is INCOMPATIBLE.\n"
            f"This requires re-indexing all {session_count:,} sessions. "
            f"Use --reindex to proceed."
        )
