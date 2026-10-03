# MamakScore AI Engine

Local, evidence-grounded startup assessment service for **PG-S2-29** and **WEDO MEDIA PTY LTD / Mamak Mentor**. It owns the AI Engine behind `POST /api/evaluate`; the separate Platform Team owns authentication, upload UI and dashboards.

## Safety status

The default is deterministic **offline fixture mode**. It verifies engineering and demo wiring but is not evidence that model scoring is accurate. Confidential founder material must not be processed without written authorisation. No application is declined automatically.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/mamakscore check-config
.venv/bin/mamakscore serve
```

Open `http://127.0.0.1:8000/docs`. Evaluate locally:

```bash
curl -F application_id=demo-1 -F pitch_deck=@deck.pdf http://127.0.0.1:8000/api/evaluate
```

For a hosted open-weight provider, copy `.env.example` to `.env`, set the provider URL/key/model, and set `MAMAKSCORE_MODE=hosted`. Never commit `.env`.

## What is deterministic

PDF/XLSX validation, all six financial formulas, evidence matching, MamakScore, score bands, boundary escalation, improvement impacts, provisional confidence, comparison and report escaping are code. The provider judges only category evidence, red flags, questions and action text.

## Documents

- [Full design](docs/superpowers/specs/2026-09-14-mamakscore-ai-engine-design.md)
- [Implementation plan](docs/superpowers/plans/2026-09-14-mamakscore-full-local-implementation.md)
- [API](docs/API.md) · [Methodology](docs/METHODOLOGY.md) · [Privacy](docs/PRIVACY.md)
- [Evaluation](docs/EVALUATION.md) · [Operations](docs/OPERATIONS.md) · [Limitations](docs/LIMITATIONS.md)
- [Demo](docs/DEMO.md) · [Handover](docs/HANDOVER.md) · [Requirements](docs/REQUIREMENTS_TRACEABILITY.md)

GitHub and external deployment are deliberately deferred.
