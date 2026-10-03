from decimal import Decimal
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from mamakscore.api import create_app
from mamakscore.config import Settings
from mamakscore.contracts import AssessmentSummary, CriterionScore


def pdf():
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_textbox(
        pymupdf.Rect(72, 72, 520, 700),
        "Problem: Clinics lose 20 hours weekly. We interviewed 120 managers and built a working prototype.",
        fontsize=11,
    )
    data = doc.tobytes()
    doc.close()
    return data


def client():
    return TestClient(
        create_app(
            Settings(
                mode="offline",
                rubric_path=Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml",
            )
        )
    )


def test_health_ready_and_evaluate_contract():
    with client() as c:
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/ready").status_code == 200
        response = c.post(
            "/api/evaluate",
            data={"application_id": "app-1"},
            files={"pitch_deck": ("deck.pdf", pdf(), "application/pdf")},
            headers={"X-Request-ID": "request-123"},
        )
    assert response.status_code == 200
    body = response.json()
    assert response.headers["X-Request-ID"] == "request-123"
    assert body["api_version"] == "1.0" and body["assessment"]["mamak_score"] == "40.0"
    assert len(body["assessment"]["criterion_scores"]) == 9


def test_unsupported_and_confidential_inputs_are_controlled():
    with client() as c:
        wrong = c.post(
            "/api/evaluate",
            data={"application_id": "a"},
            files={"pitch_deck": ("deck.txt", b"text", "text/plain")},
        )
        private = c.post(
            "/api/evaluate",
            data={"application_id": "a", "data_classification": "confidential"},
            files={"pitch_deck": ("deck.pdf", pdf(), "application/pdf")},
        )
    assert wrong.status_code == 415 and wrong.json()["error"]["code"] == "UNSUPPORTED_FILE"
    assert private.status_code == 403 and private.json()["error"]["code"] == "INVALID_REQUEST"


def test_compare_endpoint():
    scores = [
        CriterionScore(
            criterion_id=str(i),
            score=4,
            justification="x",
            evidence_quote="q",
            source_file="d.pdf",
            confidence="low",
        )
        for i in range(9)
    ]
    old = AssessmentSummary(
        application_id="a",
        rubric_version="3",
        rubric_digest="same",
        criterion_scores=scores,
        mamak_score=Decimal(40),
        band="Not ready",
    )
    new = old.model_copy(update={"mamak_score": Decimal(50)})
    with client() as c:
        response = c.post(
            "/api/compare",
            json={"previous": old.model_dump(mode="json"), "current": new.model_dump(mode="json")},
        )
    assert (
        response.status_code == 200 and response.json()["comparison"]["mamak_score_delta"] == "10"
    )
