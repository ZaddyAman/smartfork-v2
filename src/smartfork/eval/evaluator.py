"""Main evaluation orchestrator.

Sample sessions → generate queries → search (3 modes) → judge → compute metrics → report.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from loguru import logger

from smartfork.eval.cache import EvalCache
from smartfork.eval.judge import RelevanceJudge
from smartfork.eval.metrics import compute_map, compute_mrr, compute_ndcg, compute_precision_at_k
from smartfork.eval.query_generator import QueryGenerator
from smartfork.eval.report import EvalReport
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.evaluation import EvalJudgeOutput, EvalRun, GeneratedQuery, ModeResult
from smartfork.models.search import ResultCard
from smartfork.models.session import SessionDocument
from smartfork.providers import get_llm
from smartfork.search.deterministic import DeterministicSearchEngine
from smartfork.search.orchestrator import SearchOrchestrator


class EvalOrchestrator:
    """Orchestrates the full evaluation pipeline."""

    MODES = ["fast", "default", "deep"]

    def __init__(
        self,
        store: MetadataStore,
        judge_llm: Any | None = None,
        query_gen_llm: Any | None = None,
        search_llm: Any | None = None,
        embedder: Any | None = None,
        cache: EvalCache | None = None,
        sample_size: int = 50,
    ) -> None:
        """Initialize evaluator.

        Args:
            store: MetadataStore with session data.
            judge_llm: LLM for relevance judging.
            query_gen_llm: LLM for query generation.
            search_llm: LLM for default/deep search interpretation and synthesis.
            embedder: Embedding pipeline for vector search.
            cache: EvalCache for idempotency.
            sample_size: Number of sessions to sample.
        """
        self.store = store
        self.judge = RelevanceJudge(llm=judge_llm)
        self.query_gen = QueryGenerator(llm=query_gen_llm)
        self.search_llm = search_llm
        self.embedder = embedder
        self.cache = cache or EvalCache()
        self.sample_size = sample_size

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        """Return a clean string list from JSON text or loose store values."""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                decoded = [value] if value else []
            return [str(item) for item in decoded if item] if isinstance(decoded, list) else []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return []

    @classmethod
    def _normalize_session(cls, session: dict[str, Any] | SessionDocument) -> dict[str, Any]:
        """Convert store rows or SessionDocument objects into eval-friendly dicts."""
        if isinstance(session, SessionDocument):
            data = asdict(session)
            quality_tag: Any = data.get("quality_tag")
            if hasattr(quality_tag, "value"):
                data["quality_tag"] = quality_tag.value
            return data

        data = dict(session)
        for key in (
            "files_edited",
            "files_read",
            "files_mentioned",
            "final_files",
            "domains",
            "languages",
            "layers",
            "tech_tags",
            "reasoning_docs",
        ):
            data[key] = cls._coerce_str_list(data.get(key, []))
        return data

    def _get_all_sessions(self) -> list[dict[str, Any]]:
        """Read sessions from the actual MetadataStore API."""
        legacy_get_all = getattr(self.store, "get_all_sessions", None)
        if callable(legacy_get_all):
            raw_sessions = legacy_get_all()
        else:
            raw_sessions = self.store.get_all_session_documents(limit=10_000)
        return [self._normalize_session(session) for session in raw_sessions]

    def _get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch and normalize one session."""
        session = self.store.get_session(session_id)
        if session is None:
            return None
        return self._normalize_session(session)

    # ------------------------------------------------------------------
    # Session sampling
    # ------------------------------------------------------------------

    def sample_sessions(self) -> list[dict[str, Any]]:
        """Sample sessions stratified by project + domain.

        Returns:
            List of session dicts.
        """
        cached = self.cache.get_sampled_sessions()
        if cached:
            sessions: list[dict[str, Any]] = []
            for sid in cached:
                session = self._get_session(sid)
                if session is not None:
                    sessions.append(session)
            if sessions:
                logger.info(f"Using cached sample of {len(sessions)} sessions.")
                return sessions

        all_sessions = self._get_all_sessions()
        if len(all_sessions) <= self.sample_size:
            self.cache.set_sampled_sessions([s["session_id"] for s in all_sessions])
            return all_sessions

        # Stratify by project_name, then by domain
        buckets: dict[str, list[dict[str, Any]]] = {}
        for s in all_sessions:
            project = s.get("project_name", "unknown")
            domains = s.get("domains", [])
            key = f"{project}:{domains[0] if domains else 'unknown'}"
            buckets.setdefault(key, []).append(s)

        # Sample evenly across buckets
        random.seed(42)
        sampled: list[dict[str, Any]] = []
        bucket_order = list(buckets.keys())
        random.shuffle(bucket_order)

        per_bucket = max(1, self.sample_size // len(buckets))
        for key in bucket_order:
            pool = buckets[key]
            random.shuffle(pool)
            sampled.extend(pool[:per_bucket])

        # Fill remaining slots randomly
        if len(sampled) < self.sample_size:
            remaining = [s for s in all_sessions if s not in sampled]
            random.shuffle(remaining)
            sampled.extend(remaining[: self.sample_size - len(sampled)])

        sampled = sampled[: self.sample_size]
        self.cache.set_sampled_sessions([s["session_id"] for s in sampled])
        logger.info(f"Sampled {len(sampled)} sessions stratified by project/domain.")
        return sampled

    # ------------------------------------------------------------------
    # Query generation
    # ------------------------------------------------------------------

    def generate_queries(
        self, sessions: list[dict[str, Any]]
    ) -> list[GeneratedQuery]:
        """Generate queries for each session, using cache when possible."""
        queries: list[GeneratedQuery] = []
        for sess in sessions:
            sid = sess["session_id"]
            indexed_at = sess.get("indexed_at", 0)

            cached = self.cache.get_generated_queries(sid)
            if cached and self.cache.is_query_cache_valid(sid, indexed_at):
                for q in cached:
                    queries.append(
                        GeneratedQuery(
                            query=q["query"],
                            query_type=q["query_type"],
                            source_session_id=q["source_session_id"],
                        )
                    )
                continue

            generated = self.query_gen.generate(sess)
            self.cache.set_generated_queries(
                sid,
                [q.model_dump() for q in generated],
                indexed_at,
            )
            queries.extend(generated)

        logger.info(f"Generated {len(queries)} queries across {len(sessions)} sessions.")
        return queries

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _run_search(
        self,
        query: str,
        mode: str,
        llm: Any | None = None,
    ) -> tuple[list[ResultCard], float, int]:
        """Run search in one mode and return results + latency + LLM call count.

        Args:
            query: Search query.
            mode: fast, default, or deep.
            llm: LLM provider (needed for default/deep).

        Returns:
            (results, latency_ms, llm_calls)
        """
        start = time.time()
        llm_calls = 0

        if mode == "fast":
            engine = DeterministicSearchEngine(
                embedder=self.embedder, metadata_store=self.store
            )
            results = engine.search(query, top_k=5)
        else:
            if llm is None:
                logger.warning(f"LLM unavailable, falling back to fast mode for '{query}'")
                engine = DeterministicSearchEngine(
                    embedder=self.embedder, metadata_store=self.store
                )
                results = engine.search(query, top_k=5)
            else:
                use_deep = mode == "deep"
                orchestrator = SearchOrchestrator(
                    embedder=self.embedder,
                    metadata_store=self.store,
                    llm=llm,
                    use_fast=False,
                    use_deep=use_deep,
                )
                results = orchestrator.search(query, top_k=5)
                llm_calls = 2 if use_deep else 1

        latency_ms = (time.time() - start) * 1000
        return results, latency_ms, llm_calls

    # ------------------------------------------------------------------
    # Judging
    # ------------------------------------------------------------------

    def _judge_results(
        self,
        query: str,
        results: list[ResultCard],
        mode: str,
    ) -> list[EvalJudgeOutput]:
        """Judge all results for a query+mode, using cache."""
        judgments: list[EvalJudgeOutput | None] = []
        uncached_sessions: list[dict[str, Any]] = []
        uncached_positions: list[int] = []

        for card in results:
            result_id = card.session_id
            cached = self.cache.get_judgment(query, result_id, mode)
            if cached:
                judgments.append(
                    EvalJudgeOutput(
                        score=cached["score"], reason=cached["reason"]
                    )
                )
                continue

            session = self._get_session(result_id)
            if not session:
                judgments.append(EvalJudgeOutput(score=0, reason="Session not found"))
                self.cache.set_judgment(query, result_id, mode, 0, "Session not found")
                continue

            judgments.append(None)
            uncached_positions.append(len(judgments) - 1)
            uncached_sessions.append(session)

        if uncached_sessions:
            fresh_judgments = self.judge.judge_batch(query, uncached_sessions)
            for position, judgment in zip(uncached_positions, fresh_judgments, strict=False):
                result_id = results[position].session_id
                judgments[position] = judgment
                self.cache.set_judgment(
                    query, result_id, mode, judgment.score, judgment.reason
                )

        return [
            judgment if judgment is not None else EvalJudgeOutput(score=0, reason="Judge missing")
            for judgment in judgments
        ]

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        modes: list[str] | None = None,
        query_types: list[str] | None = None,
        progress_callback: Any | None = None,
    ) -> EvalRun:
        """Run the full evaluation.

        Args:
            modes: Which modes to evaluate. Defaults to all.
            query_types: Which query types to include. Defaults to all.
            progress_callback: Optional callable(progress_pct, status_msg).

        Returns:
            EvalRun with all data.
        """
        modes = modes or self.MODES
        query_types = query_types or ["specific", "short", "vague"]
        invalid_modes = sorted(set(modes) - set(self.MODES))
        if invalid_modes:
            raise RuntimeError(f"Unknown eval modes: {', '.join(invalid_modes)}")
        valid_query_types = {"specific", "short", "vague"}
        invalid_query_types = sorted(set(query_types) - valid_query_types)
        if invalid_query_types:
            raise RuntimeError(
                f"Unknown eval query types: {', '.join(invalid_query_types)}"
            )
        start_time = time.time()

        # 1. Sample sessions
        if progress_callback:
            progress_callback(0, "Sampling sessions...")
        sessions = self.sample_sessions()
        if not sessions:
            raise RuntimeError("No indexed sessions found. Run 'smartfork index' first.")

        # 2. Generate queries
        if progress_callback:
            progress_callback(10, "Generating queries...")
        all_queries = self.generate_queries(sessions)
        queries = [q for q in all_queries if q.query_type in query_types]

        # 3. Search + judge for each mode
        mode_results: list[ModeResult] = []
        total = len(queries) * len(modes)
        done = 0

        # Set up LLM for default/deep modes
        llm = self.search_llm
        if ("default" in modes or "deep" in modes) and llm is None:
            try:
                from smartfork.config import get_config

                cfg = get_config()
                llm = get_llm(cfg.llm_provider, cfg.llm_model)
            except Exception as exc:
                logger.warning(f"Could not initialize LLM for search: {exc}")

        for query in queries:
            for mode in modes:
                status = f"Evaluating: '{query.query[:40]}...' ({mode})"
                if progress_callback:
                    pct = 10 + int((done / total) * 80)
                    progress_callback(pct, status)

                results, latency, llm_calls = self._run_search(
                    query.query, mode, llm
                )
                judgments = self._judge_results(query.query, results, mode)

                mode_results.append(
                    ModeResult(
                        mode=mode,
                        query=query.query,
                        query_type=query.query_type,
                        source_session_id=query.source_session_id,
                        result_session_ids=[r.session_id for r in results],
                        judgments=judgments,
                        latency_ms=latency,
                        llm_calls=llm_calls,
                        search_results=results,
                    )
                )
                done += 1

        # 4. Compute metrics
        if progress_callback:
            progress_callback(90, "Computing metrics...")
        eval_run = EvalRun(
            sampled_session_ids=[s["session_id"] for s in sessions],
            queries=queries,
            mode_results=mode_results,
            start_time=start_time,
            end_time=time.time(),
        )
        self._compute_metrics(eval_run)

        if progress_callback:
            progress_callback(100, "Done.")
        return eval_run

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _compute_metrics(self, eval_run: EvalRun) -> None:
        """Compute per-mode and per-query-type metrics."""
        for mode in self.MODES:
            mode_items = [m for m in eval_run.mode_results if m.mode == mode]
            if not mode_items:
                continue

            # Overall per-mode
            all_scores = [
                [float(j.score) for j in item.judgments] for item in mode_items
            ]
            eval_run.overall_metrics[mode] = {
                "precision_at_5": self._avg(
                    compute_precision_at_k(scores, 5) for scores in all_scores
                ),
                "ndcg_at_5": self._avg(
                    compute_ndcg(scores, 5) for scores in all_scores
                ),
                "mrr": self._avg(
                    compute_mrr(scores) for scores in all_scores
                ),
                "map": compute_map(all_scores),
                "avg_latency_ms": self._avg(item.latency_ms for item in mode_items),
                "avg_llm_calls": self._avg(item.llm_calls for item in mode_items),
            }

            # Per query type
            for qt in ["specific", "short", "vague"]:
                qt_items = [m for m in mode_items if m.query_type == qt]
                if not qt_items:
                    continue
                qt_scores = [
                    [float(j.score) for j in item.judgments] for item in qt_items
                ]
                key = f"{mode}_{qt}"
                eval_run.per_query_type_metrics[key] = {
                    "precision_at_5": self._avg(
                        compute_precision_at_k(scores, 5) for scores in qt_scores
                    ),
                    "ndcg_at_5": self._avg(
                        compute_ndcg(scores, 5) for scores in qt_scores
                    ),
                    "mrr": self._avg(
                        compute_mrr(scores) for scores in qt_scores
                    ),
                    "map": compute_map(qt_scores),
                    "avg_latency_ms": self._avg(
                        item.latency_ms for item in qt_items
                    ),
                }

    @staticmethod
    def _avg(gen: Any) -> float:
        """Average a generator of floats, safely handling empty."""
        vals = list(gen)
        if not vals:
            return 0.0
        return float(sum(vals) / len(vals))

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def render_report(self, eval_run: EvalRun, output_dir: Path) -> Path:
        """Render HTML + JSON report to output directory.

        Args:
            eval_run: Completed evaluation run.
            output_dir: Directory to write report files.

        Returns:
            Path to the HTML report file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = EvalReport(eval_run)
        html_path = report.render_html(output_dir)
        report.render_json(output_dir)
        return html_path
