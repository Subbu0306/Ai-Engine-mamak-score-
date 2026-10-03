from mamakscore.evaluation import compute_metrics


def records():
    out = []
    for i in range(1, 11):
        out.append(
            {
                "application_id": str(i),
                "human_total": i * 10,
                "model_total": i * 10,
                "human_scores": {"market": i},
                "model_scores": {"market": i},
                "grounded_quotes": 9,
                "total_quotes": 9,
                "fabrications": 0,
                "runs": [i * 10, i * 10, i * 10],
                "demographic_pair_delta": 0.0,
                "latency_seconds": float(i),
                "cost_usd": 0.01,
            }
        )
    return out


def test_known_answer_metrics():
    result = compute_metrics(records())
    assert result["per_category_qwk"]["market"] == 1.0
    assert result["spearman"] == 1.0 and result["shortlist_recall_at_20_percent"] == 1.0
    assert result["groundedness"] == 1.0 and result["fabrication_rate"] == 0.0
    assert result["mean_stability_stddev"] == 0.0 and result["mean_demographic_sensitivity"] == 0.0
    assert result["p90_latency_seconds"] == 9.0


def test_missing_empirical_fields_are_not_run():
    result = compute_metrics([{"application_id": "a"}])
    assert result["spearman"] == "NOT_RUN" and result["groundedness"] == "NOT_RUN"
