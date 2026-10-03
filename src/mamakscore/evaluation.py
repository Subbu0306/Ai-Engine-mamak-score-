# Honest aggregate evaluation metrics; unavailable inputs are NOT_RUN.
from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any

from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score


def _all(records: list[dict[str, Any]], key: str) -> bool:
    return bool(records) and all(key in row and row[key] is not None for row in records)


def _rounded(value: Any) -> float | str:
    return (
        round(float(value), 6) if value is not None and math.isfinite(float(value)) else "NOT_RUN"
    )


def compute_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"sample_count": len(records)}
    categories = sorted(set().union(*(row.get("human_scores", {}).keys() for row in records)))
    qwk: dict[str, float | str] = {}
    for category in categories:
        pairs = [
            (r.get("human_scores", {}).get(category), r.get("model_scores", {}).get(category))
            for r in records
        ]
        pairs = [p for p in pairs if None not in p]
        qwk[category] = (
            _rounded(
                cohen_kappa_score([p[0] for p in pairs], [p[1] for p in pairs], weights="quadratic")
            )
            if len(pairs) >= 2
            else "NOT_RUN"
        )
    result["per_category_qwk"] = qwk
    if _all(records, "human_total") and _all(records, "model_total") and len(records) >= 2:
        result["spearman"] = _rounded(
            spearmanr(
                [r["human_total"] for r in records], [r["model_total"] for r in records]
            ).statistic
        )
        take = max(1, math.ceil(len(records) * 0.2))
        human = {
            r["application_id"]
            for r in sorted(records, key=lambda r: r["human_total"], reverse=True)[:take]
        }
        model = {
            r["application_id"]
            for r in sorted(records, key=lambda r: r["model_total"], reverse=True)[:take]
        }
        result["shortlist_recall_at_20_percent"] = round(len(human & model) / len(human), 6)
    else:
        result["spearman"] = result["shortlist_recall_at_20_percent"] = "NOT_RUN"
    if (
        _all(records, "grounded_quotes")
        and _all(records, "total_quotes")
        and sum(r["total_quotes"] for r in records)
    ):
        result["groundedness"] = round(
            sum(r["grounded_quotes"] for r in records) / sum(r["total_quotes"] for r in records), 6
        )
    else:
        result["groundedness"] = "NOT_RUN"
    result["fabrication_rate"] = (
        round(sum(r["fabrications"] for r in records) / sum(r["total_quotes"] for r in records), 6)
        if _all(records, "fabrications")
        and _all(records, "total_quotes")
        and sum(r["total_quotes"] for r in records)
        else "NOT_RUN"
    )
    result["mean_stability_stddev"] = (
        round(statistics.mean(statistics.pstdev(r["runs"]) for r in records), 6)
        if _all(records, "runs") and all(len(r["runs"]) >= 2 for r in records)
        else "NOT_RUN"
    )
    result["mean_demographic_sensitivity"] = (
        round(statistics.mean(abs(r["demographic_pair_delta"]) for r in records), 6)
        if _all(records, "demographic_pair_delta")
        else "NOT_RUN"
    )
    if _all(records, "latency_seconds"):
        values = sorted(float(r["latency_seconds"]) for r in records)
        result["p50_latency_seconds"] = statistics.median(values)
        result["p90_latency_seconds"] = values[math.ceil(0.9 * len(values)) - 1]
    else:
        result["p50_latency_seconds"] = result["p90_latency_seconds"] = "NOT_RUN"
    result["mean_cost_usd"] = (
        round(statistics.mean(float(r["cost_usd"]) for r in records), 6)
        if _all(records, "cost_usd")
        else "NOT_RUN"
    )
    result["status_counts"] = dict(
        Counter("complete" if "model_total" in r else "incomplete" for r in records)
    )
    return result
