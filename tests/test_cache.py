from mamakscore.cache import ReplayCache
from mamakscore.contracts import AssessmentDraft, CriterionScore, InvestorQuestion


def draft():
    scores = [
        CriterionScore(
            criterion_id=str(i),
            score=1,
            justification="x",
            evidence_quote="q",
            source_file="d.pdf",
            confidence="low",
        )
        for i in range(9)
    ]
    questions = [InvestorQuestion(question=f"q{i}", criterion_ids=[str(i)]) for i in range(5)]
    return AssessmentDraft(criterion_scores=scores, investor_questions=questions)


def test_disabled_cache_creates_no_file(tmp_path):
    path = tmp_path / "cache.sqlite"
    cache = ReplayCache(path, enabled=False)
    cache.put("key", draft())
    assert cache.get("key") is None and not path.exists()


def test_round_trip_and_key_dimensions(tmp_path):
    cache = ReplayCache(tmp_path / "cache.sqlite", enabled=True)
    value = draft()
    cache.put("key", value)
    assert cache.get("key") == value
    assert ReplayCache.make_key("a", "b") != ReplayCache.make_key("a", "c")


def test_malformed_payload_is_evicted(tmp_path):
    cache = ReplayCache(tmp_path / "cache.sqlite", enabled=True)
    cache._put_raw("bad", "not-json")
    assert cache.get("bad") is None and cache.get("bad") is None
