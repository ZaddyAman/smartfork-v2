"""SmartFork v2 — Search Evaluation System."""

from smartfork.eval.cache import EvalCache
from smartfork.eval.evaluator import EvalOrchestrator
from smartfork.eval.judge import JudgeOutput, RelevanceJudge
from smartfork.eval.metrics import compute_map, compute_mrr, compute_ndcg, compute_precision_at_k
from smartfork.eval.query_generator import GeneratedQuery, QueryGenerator
from smartfork.eval.report import EvalReport

__all__ = [
    "EvalCache",
    "EvalOrchestrator",
    "EvalReport",
    "GeneratedQuery",
    "JudgeOutput",
    "QueryGenerator",
    "RelevanceJudge",
    "compute_map",
    "compute_mrr",
    "compute_ndcg",
    "compute_precision_at_k",
]
