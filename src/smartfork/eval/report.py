"""HTML and JSON report generation for evaluation results."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from smartfork.eval.metrics import compute_mrr, compute_ndcg, compute_precision_at_k


@dataclass
class EvalReport:
    """Renders evaluation results into HTML and JSON reports."""

    eval_run: Any
    generated_at: str = field(default="")

    def render_json(self, output_dir: Path) -> Path:
        """Save metrics and result details as JSON."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "metrics.json"
        data = {
            "metadata": {
                "sample_size": len(self.eval_run.sampled_session_ids),
                "total_queries": len(self.eval_run.queries),
                "total_judgments": sum(
                    len(m.judgments) for m in self.eval_run.mode_results
                ),
                "duration_seconds": round(
                    self.eval_run.end_time - self.eval_run.start_time, 2
                ),
            },
            "overall": self.eval_run.overall_metrics,
            "by_query_type": self.eval_run.per_query_type_metrics,
            "queries": [q.model_dump() for q in self.eval_run.queries],
            "results": [self._mode_result_json(item) for item in self.eval_run.mode_results],
        }
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return path

    def render_html(self, output_dir: Path) -> Path:
        """Save an HTML report."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "report.html"
        path.write_text(self._build_html(), encoding="utf-8")
        return path

    def _mode_result_json(self, item: Any) -> dict[str, Any]:
        return {
            "mode": item.mode,
            "query": item.query,
            "query_type": item.query_type,
            "source_session_id": item.source_session_id,
            "result_session_ids": item.result_session_ids,
            "judgments": [j.model_dump() for j in item.judgments],
            "latency_ms": item.latency_ms,
            "llm_calls": item.llm_calls,
            "search_results": [asdict(result) for result in item.search_results],
        }

    def _build_html(self) -> str:
        timestamp = self.generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = round(self.eval_run.end_time - self.eval_run.start_time, 2)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SmartFork Search Evaluation Report</title>
<style>
  :root {{
    --bg: #11100f;
    --surface: #191715;
    --surface-2: #211f1c;
    --border: #3a352f;
    --text: #f1ede7;
    --muted: #a69e94;
    --accent: #d97742;
    --blue: #67a6d9;
    --good: #64b879;
    --warn: #d9aa55;
    --bad: #e0635b;
    --font: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
      "Segoe UI", sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    line-height: 1.55;
    margin: 0;
    padding: 32px 20px;
  }}
  main {{ max-width: 1180px; margin: 0 auto; }}
  h1 {{ font-size: 32px; margin: 0 0 4px; letter-spacing: 0; }}
  h2 {{ color: var(--accent); font-size: 20px; margin: 34px 0 12px; }}
  .subtitle {{ color: var(--muted); margin: 0 0 28px; }}
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
  }}
  .meta-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
  }}
  .label {{
    color: var(--muted);
    font-size: 12px;
    letter-spacing: 0;
    text-transform: uppercase;
  }}
  .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }}
  th, td {{ padding: 12px 14px; text-align: left; vertical-align: top; }}
  th {{
    background: var(--surface-2);
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
  }}
  tr + tr td {{ border-top: 1px solid var(--border); }}
  pre {{
    background: #0d0c0b;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--muted);
    margin: 0;
    overflow-x: auto;
    padding: 10px;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .score {{ font-weight: 700; }}
  .score-good {{ color: var(--good); }}
  .score-mid {{ color: var(--warn); }}
  .score-bad {{ color: var(--bad); }}
  .tag {{
    border-radius: 4px;
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
  }}
  .tag-fast {{ background: rgba(100, 184, 121, 0.18); color: var(--good); }}
  .tag-default {{ background: rgba(103, 166, 217, 0.18); color: var(--blue); }}
  .tag-deep {{ background: rgba(217, 170, 85, 0.18); color: var(--warn); }}
  .detail td {{ background: #12100f; }}
</style>
</head>
<body>
<main>
  <h1>SmartFork Search Evaluation</h1>
  <p class="subtitle">Generated {escape(timestamp)}</p>
  <section class="meta-grid">
    {self._meta_card("Sessions Sampled", len(self.eval_run.sampled_session_ids))}
    {self._meta_card("Queries", len(self.eval_run.queries))}
    {self._meta_card("Judgments", self._judgment_count())}
    {self._meta_card("Duration", f"{duration}s")}
  </section>
  <h2>Overall Mode Comparison</h2>
  {self._overall_table()}
  <h2>Metrics by Query Type</h2>
  {self._query_type_table()}
  <h2>Per-Query Results</h2>
  {self._detail_table()}
</main>
</body>
</html>
"""

    def _meta_card(self, label: str, value: object) -> str:
        return (
            '<div class="meta-card">'
            f'<div class="label">{escape(label)}</div>'
            f'<div class="value">{escape(str(value))}</div>'
            "</div>"
        )

    def _judgment_count(self) -> int:
        return int(sum(len(item.judgments) for item in self.eval_run.mode_results))

    def _overall_table(self) -> str:
        rows = []
        for mode in ["fast", "default", "deep"]:
            metrics = self.eval_run.overall_metrics.get(mode, {})
            if not metrics:
                continue
            rows.append(
                "<tr>"
                f"<td>{self._mode_tag(mode)}</td>"
                f"<td class='score {self._score_class(metrics['precision_at_5'])}'>"
                f"{metrics['precision_at_5']:.0%}</td>"
                f"<td class='score {self._score_class(metrics['ndcg_at_5'])}'>"
                f"{metrics['ndcg_at_5']:.2f}</td>"
                f"<td class='score {self._score_class(metrics['mrr'])}'>"
                f"{metrics['mrr']:.2f}</td>"
                f"<td>{metrics['map']:.2f}</td>"
                f"<td>{metrics['avg_latency_ms']:.0f} ms</td>"
                f"<td>{metrics['avg_llm_calls']:.1f}</td>"
                "</tr>"
            )
        return self._table(
            ["Mode", "P@5", "nDCG@5", "MRR", "MAP", "Avg Latency", "LLM Calls"],
            rows,
        )

    def _query_type_table(self) -> str:
        rows = []
        for mode in ["fast", "default", "deep"]:
            for query_type in ["specific", "short", "vague"]:
                key = f"{mode}_{query_type}"
                metrics = self.eval_run.per_query_type_metrics.get(key, {})
                if not metrics:
                    continue
                rows.append(
                    "<tr>"
                    f"<td>{self._mode_tag(mode)}</td>"
                    f"<td>{escape(query_type)}</td>"
                    f"<td class='score {self._score_class(metrics['precision_at_5'])}'>"
                    f"{metrics['precision_at_5']:.0%}</td>"
                    f"<td class='score {self._score_class(metrics['ndcg_at_5'])}'>"
                    f"{metrics['ndcg_at_5']:.2f}</td>"
                    f"<td>{metrics['mrr']:.2f}</td>"
                    f"<td>{metrics['map']:.2f}</td>"
                    f"<td>{metrics['avg_latency_ms']:.0f} ms</td>"
                    "</tr>"
                )
        return self._table(
            ["Mode", "Query Type", "P@5", "nDCG@5", "MRR", "MAP", "Latency"],
            rows,
        )

    def _detail_table(self) -> str:
        rows = []
        for item in self.eval_run.mode_results:
            scores = [float(j.score) for j in item.judgments]
            p5 = compute_precision_at_k(scores, 5)
            ndcg = compute_ndcg(scores, 5)
            mrr = compute_mrr(scores)
            query = item.query[:70] + ("..." if len(item.query) > 70 else "")
            detail = "\n".join(
                f"Rank {index}: score {judgment.score}/3 - {judgment.reason[:120]}"
                for index, judgment in enumerate(item.judgments, start=1)
            )
            rows.append(
                "<tr>"
                f"<td>{escape(query)}</td>"
                f"<td>{escape(item.query_type)}</td>"
                f"<td>{self._mode_tag(item.mode)}</td>"
                f"<td class='score {self._score_class(p5)}'>{p5:.0%}</td>"
                f"<td class='score {self._score_class(ndcg)}'>{ndcg:.2f}</td>"
                f"<td>{mrr:.2f}</td>"
                f"<td>{item.latency_ms:.0f} ms</td>"
                "</tr>"
            )
            rows.append(
                "<tr class='detail'>"
                f"<td colspan='7'><pre>{escape(detail)}</pre></td>"
                "</tr>"
            )
        return self._table(["Query", "Type", "Mode", "P@5", "nDCG@5", "MRR", "Latency"], rows)

    def _table(self, headers: list[str], rows: list[str]) -> str:
        header_cells = "".join(f"<th>{escape(header)}</th>" for header in headers)
        body = "".join(rows) if rows else f"<tr><td colspan='{len(headers)}'>No data</td></tr>"
        return f"<table><thead><tr>{header_cells}</tr></thead><tbody>{body}</tbody></table>"

    def _mode_tag(self, mode: str) -> str:
        mode_text = escape(mode)
        return f'<span class="tag tag-{mode_text}">{mode_text}</span>'

    @staticmethod
    def _score_class(value: float) -> str:
        """Map score to CSS class for coloring."""
        if value >= 0.7:
            return "score-good"
        if value >= 0.4:
            return "score-mid"
        return "score-bad"
