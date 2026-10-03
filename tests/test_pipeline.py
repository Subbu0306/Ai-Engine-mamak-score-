from pathlib import Path

import pymupdf
import pytest

from mamakscore.cache import ReplayCache
from mamakscore.errors import ServiceError
from mamakscore.pipeline import EvaluationPipeline
from mamakscore.provider import OfflineProvider, ProviderResponse
from mamakscore.rubric import load_rubric

R = load_rubric(Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml")


def pdf(text):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 520, 700), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def test_deck_only_pipeline_is_complete_and_grounded(tmp_path):
    text = "Problem: Clinics lose 20 hours weekly. We interviewed 120 practice managers and built a working prototype."
    pipe = EvaluationPipeline(
        R,
        OfflineProvider(R, "deck.pdf"),
        cache=ReplayCache(tmp_path / "c.sqlite", enabled=False),
        expose_confidence=True,
    )
    result = pipe.evaluate("app-1", pdf(text), "deck.pdf")
    assert result.mamak_score == 40 and result.band.label == "Needs significant validation"
    assert len(result.criterion_scores) == 9 and len(result.investor_questions) == 5
    assert result.mamak_confidence.status == "PROVISIONAL_NOT_CLIENT_APPROVED"
    assert result.financials.provided is False and "<h1" in result.report_html


def test_cache_replays_without_second_provider_call(tmp_path):
    class Counting:
        model_id = "counting"

        def __init__(self):
            self.calls = 0
            self.inner = OfflineProvider(R, "deck.pdf")

        def assess(self, request):
            self.calls += 1
            r = self.inner.assess(request)
            return ProviderResponse(draft=r.draft, provider="offline", model_id=self.model_id)

    p = Counting()
    pipe = EvaluationPipeline(R, p, cache=ReplayCache(tmp_path / "c.sqlite", enabled=True))
    data = pdf(
        "Substantial source evidence that is long enough to pass extraction and grounding checks."
    )
    assert pipe.evaluate("a", data, "deck.pdf", use_cache=True).provenance.from_cache is False
    assert pipe.evaluate("a", data, "deck.pdf", use_cache=True).provenance.from_cache is True
    assert p.calls == 1


def test_ungrounded_provider_fails_whole_run(tmp_path):
    class Bad:
        model_id = "bad"

        def assess(self, request):
            result = OfflineProvider(R, "deck.pdf").assess(request)
            bad = result.draft.criterion_scores
            bad[0] = bad[0].model_copy(update={"evidence_quote": "invented 999 customers"})
            return ProviderResponse(
                draft=result.draft.model_copy(update={"criterion_scores": bad}),
                provider="bad",
                model_id="bad",
            )

    pipe = EvaluationPipeline(R, Bad(), cache=ReplayCache(tmp_path / "c.sqlite", enabled=False))
    with pytest.raises(ServiceError) as exc:
        pipe.evaluate(
            "a", pdf("Actual evidence line with enough characters for extraction."), "deck.pdf"
        )
    assert exc.value.code == "UNGROUNDED_EVIDENCE"
