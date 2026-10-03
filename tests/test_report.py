from pathlib import Path

import pymupdf

from mamakscore.cache import ReplayCache
from mamakscore.pipeline import EvaluationPipeline
from mamakscore.provider import OfflineProvider
from mamakscore.report import render_report
from mamakscore.rubric import load_rubric

R = load_rubric(Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml")


def result(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text(
        (72, 72), "Useful source evidence with 120 customers and enough text for extraction."
    )
    data = doc.tobytes()
    doc.close()
    return EvaluationPipeline(
        R, OfflineProvider(R, "deck.pdf"), cache=ReplayCache(tmp_path / "c", False)
    ).evaluate("a", data, "deck.pdf")


def test_report_escapes_model_content_and_is_accessible(tmp_path):
    value = result(tmp_path).model_copy(
        update={"missing_information": ["<script>alert(1)</script>"]}
    )
    html = render_report(value)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert html.count("<h1") == 1 and "<h2" in html and "<caption>" in html
    assert "PROVISIONAL — NOT CLIENT APPROVED" in html
    assert "http://" not in html and "https://" not in html
