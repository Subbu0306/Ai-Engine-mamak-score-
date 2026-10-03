from mamakscore.load_testing import nearest_rank, summarize


def test_nearest_rank_and_summary():
    assert nearest_rank(list(range(1, 11)), 0.9) == 9
    result = summarize([0.1, 0.2, 0.3], [200, 200, 429], 1.0)
    assert result["requests"] == 3 and result["status_counts"] == {"200": 2, "429": 1}
    assert result["throughput_per_second"] == 3.0 and result["p90_seconds"] == 0.3
