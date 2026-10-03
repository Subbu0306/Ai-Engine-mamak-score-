from pathlib import Path

ROOT = Path(__file__).parents[1]
DOCS = [
    "API.md",
    "METHODOLOGY.md",
    "PRIVACY.md",
    "EVALUATION.md",
    "OPERATIONS.md",
    "LIMITATIONS.md",
    "DEMO.md",
    "HANDOVER.md",
    "REQUIREMENTS_TRACEABILITY.md",
]


def test_complete_documentation_set_and_links():
    assert (ROOT / "README.md").exists()
    for name in DOCS:
        assert (ROOT / "docs" / name).exists(), name
    readme = (ROOT / "README.md").read_text()
    assert (
        "2026-09-14-mamakscore-ai-engine-design.md" in readme
        and "2026-09-14-mamakscore-full-local-implementation.md" in readme
    )


def test_requirements_and_safety_are_explicit():
    trace = (ROOT / "docs/REQUIREMENTS_TRACEABILITY.md").read_text()
    for prefix, count in (("FR", 17), ("NFR", 9)):
        for i in range(1, count + 1):
            assert f"{prefix}{i}" in trace
    method = (ROOT / "docs/METHODOLOGY.md").read_text()
    assert "Σ(score × weight) / 10" in method and "PROVISIONAL_NOT_CLIENT_APPROVED" in method
    privacy = (ROOT / "docs/PRIVACY.md").read_text().lower()
    assert "confidential" in privacy and "written authorisation" in privacy
    api = (ROOT / "docs/API.md").read_text()
    assert "POST /api/evaluate" in api and "UNGROUNDED_EVIDENCE" in api
