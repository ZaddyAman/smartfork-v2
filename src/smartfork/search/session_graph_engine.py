"""Session graph engine — chain following and relationship traversal."""

from loguru import logger

from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.relationship import Chain, TimelineEntry
from smartfork.models.session import SessionDocument


class SessionGraphEngine:
    """Queries session relationships to follow chains, find branches, build timelines."""

    def __init__(self, store: MetadataStore) -> None:
        self.store = store
        self._chain_cache: dict[str, list[SessionDocument]] = {}

    def _cache_key(self, session_id: str, direction: str) -> str:
        return f"{session_id}:{direction}"

    def _fetch_session(self, session_id: str) -> SessionDocument | None:
        return self.store.get_session_document(session_id)

    def find_chain(
        self, session_id: str, direction: str = "forward"
    ) -> list[SessionDocument]:
        """Follow continuation links from a session.

        Args:
            session_id: Starting session
            direction: 'forward' (follow to_session) or 'backward' (follow from_session)

        Returns:
            Ordered list of SessionDocument in the chain (including starting session)
        """
        key = self._cache_key(session_id, direction)
        if key in self._chain_cache:
            return self._chain_cache[key]

        chain: list[SessionDocument] = []
        visited: set[str] = set()

        if direction == "backward":
            # Walk backward to find the earliest session, then reverse
            backward_chain: list[SessionDocument] = []
            current = session_id
            while current not in visited:
                visited.add(current)
                doc = self._fetch_session(current)
                if doc is None:
                    logger.warning(f"Session not found: {session_id}")
                    return []
                backward_chain.append(doc)
                # Find predecessor: relationships where current is to_session
                rels = self.store.get_relationships(current, direction="to")
                continuations = [
                    r for r in rels if r.relationship_type == "continuation"
                ]
                if continuations:
                    # Follow the first continuation relationship backward
                    current = continuations[0].from_session
                else:
                    break
            # Reverse so oldest is first
            backward_chain.reverse()
            chain = backward_chain
        else:
            # Forward: starting session -> successors
            current = session_id
            while current not in visited:
                visited.add(current)
                doc = self._fetch_session(current)
                if doc is None:
                    logger.warning(f"Session not found: {session_id}")
                    return []
                chain.append(doc)
                # Find successor: relationships where current is from_session
                rels = self.store.get_relationships(current, direction="from")
                continuations = [
                    r for r in rels if r.relationship_type == "continuation"
                ]
                if continuations:
                    current = continuations[0].to_session
                else:
                    break

        self._chain_cache[key] = chain
        return chain

    def find_related_sessions(
        self, session_id: str, project: str | None = None, max_chains: int = 5
    ) -> list[Chain]:
        """Find all sessions related to the given session, grouped into chains."""
        rels = self.store.get_relationships(session_id, direction="both")
        related_ids: set[str] = set()
        for rel in rels:
            if rel.from_session != session_id:
                related_ids.add(rel.from_session)
            if rel.to_session != session_id:
                related_ids.add(rel.to_session)

        chains: list[Chain] = []
        seen_heads: set[str] = set()

        for rid in related_ids:
            session = self._fetch_session(rid)
            if session is None:
                continue
            if project and session.project_name != project:
                continue

            # Find the head of this chain
            backward = self.find_chain(rid, direction="backward")
            if not backward:
                backward = [session]
            head_id = backward[0].session_id

            if head_id in seen_heads:
                continue
            seen_heads.add(head_id)

            # Get full chain forward from head
            forward = self.find_chain(head_id, direction="forward")
            if not forward:
                forward = backward

            chain_type = "linear"
            if len(forward) > 1:
                branches = self.find_branches(head_id)
                if branches:
                    chain_type = "branched"

            chains.append(
                Chain(
                    sessions=forward,
                    chain_type=chain_type,
                    head_session_id=forward[0].session_id,
                    tail_session_id=forward[-1].session_id,
                )
            )

            if len(chains) >= max_chains:
                break

        return chains

    def get_latest_in_chain(self, chain: Chain) -> SessionDocument:
        """Return the most recent session in a chain."""
        return max(chain.sessions, key=lambda s: s.session_start)

    def find_branches(self, session_id: str) -> list[list[SessionDocument]]:
        """Find all divergent paths from a session."""
        branches: list[list[SessionDocument]] = []
        rels = self.store.get_relationships(session_id, direction="from")

        for rel in rels:
            branch_chain = self.find_chain(rel.to_session, direction="forward")
            if branch_chain:
                branches.append(branch_chain)

        return branches

    def build_timeline(self, chain: Chain) -> list[TimelineEntry]:
        """Build structured timeline entries from a chain."""
        timeline: list[TimelineEntry] = []
        sessions = chain.sessions

        for i, session in enumerate(sessions):
            relationship_to_next = None
            if i < len(sessions) - 1:
                relationship_to_next = "continued_in"

            task = session.task_raw
            if len(task) > 80:
                task = task[:77] + "..."

            summary = session.summary_doc
            if len(summary) > 200:
                summary = summary[:197] + "..."

            entry = TimelineEntry(
                session_id=session.session_id,
                timestamp=session.session_start,
                task=task,
                quality_tag=session.quality_tag,
                summary=summary,
                relationship_to_next=relationship_to_next,
            )
            timeline.append(entry)

        return timeline
