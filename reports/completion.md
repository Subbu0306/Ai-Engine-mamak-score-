# MamakScore AI Engine — Completion Report

**Group** PG-S2-29 · **Client** WEDO MEDIA PTY LTD / Mamak Mentor
**Generated** 15 September 2026 · **Repository** `~/Desktop/Capstone Project`, branch `feature/full-local`, **3 commits, 0 remotes** (local-only, as instructed)

---

## Verdict

The engine is **built, typed, tested, packaged, and verified end-to-end in a clean environment**.

It is **not yet a validated assessment tool.** Every score it has produced comes from a deterministic
offline fixture that returns 4/10 on every category. That fixture proves the plumbing; it judges nothing.
Two things stand between this and a defensible tool: a real model connection, and a human-agreement study.

---

## Gates

| # | Gate | Status | Evidence |
|---|------|--------|----------|
| G1 | Signed scope implemented | **PASS** | 24 modules: FR1–FR14 (Must+Should), FR15 provisional confidence, FR17 comparison. FR16 and post-MVP roadmap excluded by agreed scope. |
| G2 | Tests and coverage | **PASS** | 68 passed, 0 failed; coverage **87.79%** against an 80% floor |
| G3 | Lint and formatting | **PASS** | `ruff check`: All checks passed · `ruff format --check`: 61 files already formatted |
| G4 | mypy strict | **PASS** | Success: no issues found in 24 source files (**from 61 errors**) |
| G5 | Dependency + secret hygiene | **PASS\*** | `pip check` clean; secret scan zero matches; `.gitignore` verified. *pip-audit not installed → CVE audit `NOT_RUN`* |
| G6 | Offline dress rehearsals | **PASS** | 3 runs, **7/7 checks** — see `dress-rehearsal.json` |
| G7 | Clean-environment verification | **PASS** | Fresh venv → install → `check-config` → full evaluate. **Caught a real packaging bug** (F1) |
| G8 | Live API contract | **PASS** | Real uvicorn server; 5 endpoint/security cases verified |
| G9 | Code review (5 areas) | **PASS** | 3 defects fixed, 1 open finding recorded |
| G10 | Documentation currency | **PASS** | No stale paths; historical spec/plan left as dated records |

### G6 — Dress rehearsal checks (all passed)

- Byte-identical output digests across 3 runs (determinism)
- Every evidence quote verbatim in source (grounding enforced)
- Nine categories scored
- `human_review_required` always true
- Confidence flagged `PROVISIONAL_NOT_CLIENT_APPROVED`
- Score maths matches the client formula (4 × 100 ÷ 10 = 40.0 exactly)
- Report rendered

### G8 — Live API results

| Request | Result |
|---|---|
| `GET /health` | **200** `{"status":"ok"}` |
| `GET /ready` | **200** `{"status":"ready","mode":"offline","rubric_version":"3.0"}` |
| `POST /api/evaluate` — public | **200** full assessment + provenance digests |
| `POST /api/evaluate` — confidential | **403** *"Confidential processing requires recorded written authorisation."* |
| `POST /api/evaluate` — `.xlsx` as deck | **415** UNSUPPORTED_FILE |

---

## Findings

### F1 · HIGH · **FIXED** — rubric was not shipped with the package

The engine resolved its rubric via `Path(__file__).parents[2]`, a path that exists **only in a source
checkout**. A normal `pip install` produced a working import and console script that then died at runtime
with `FileNotFoundError`. The clean-environment gate exists precisely to catch this, and it did.

**Fix** `git mv rubric/mamakscore-v3.yaml src/mamakscore/data/`, declared `[tool.setuptools.package-data]`,
repointed 8 test files. Re-verified in a fresh venv.

### F2 · MEDIUM · **FIXED** — unnarrowed `Decimal | None` in financial parsing

`workbook.py` paired cells with `_number(cell.value)` (typed `Decimal | None`) and never narrowed it, so
the later `value > 1` comparison and `value / Decimal(100)` division could run against `None`.
**Fix** rebuilt as an explicit narrowing loop.

### F3 · MEDIUM · **FIXED** — bare `str` into a `Literal` contract

`_period()` returned `str` into `FinancialInput.period`, which requires
`Literal["monthly","annual","point_in_time","unknown"]`. A typo would have surfaced as a runtime
validation error instead of a type error. **Fix** introduced `PeriodLiteral`.

### F4 · LOW · **OPEN** — red flags can pass grounding without evidence

`verify_red_flag_evidence()` skips any flag whose `evidence_quote` is empty, and `RedFlag.evidence_quote`
defaults to `""`. Category scores are held to a stricter rule — an empty quote is allowed only when the
score is 0 *and* the justification is exactly the not-stated text. A model could therefore emit an
**unevidenced red flag** that passes grounding.

**Recommendation** either require a non-empty `evidence_quote` on `RedFlag`, or allow an empty one only for
`flag_type: "missing_information"`. **Deferred deliberately** — it changes a data contract and warrants
client confirmation rather than a unilateral change.

### F5 · ENVIRONMENTAL · **MITIGATED** — iCloud sync stalls the toolchain

The Desktop is iCloud-synced, so the whole project went through the file provider. Python blocked at **0%
CPU** on ordinary reads: a run needing **1.08s of compute took 3m45s of wall clock**, and interpreter
startup alone took 90s.

**Fix** `.venv` → `.venv.nosync` + symlink (macOS excludes `*.nosync`), cutting startup to **2.1s**.
Verification runs were executed from a local scratchpad copy of identical bytes.
**Recommendation** for sustained development, keep the working copy off iCloud-synced Desktop.

---

## Not run — and why

These are recorded as **not run** rather than assumed, because claiming them would be fabrication.

| Item | Blocker | Consequence |
|---|---|---|
| Human-expert agreement (QWK) | No human-scored labels collected; harness exists (`scripts/evaluate_labels.py`) | **No evidence the scores agree with expert judgement** |
| Real-model accuracy / latency / cost | No LLM credentials configured | Every score so far verifies plumbing, not judgement |
| Fairness and bias evaluation | Needs a labelled corpus with varied founder/sector attributes | Bias profile unknown |
| Load and capacity testing | `scripts/load_test.py` exists, not executed | Throughput limits unmeasured |
| Dependency CVE audit | `pip-audit` not installed | Vulnerability status unknown |

---

## Safety properties verified

- Human review **always** required; no automated decline path exists
- Confidential uploads rejected **403** without recorded written authorisation
- Evidence grounding enforced — an unverifiable quote fails the whole run
- MamakConfidence permanently flagged `PROVISIONAL_NOT_CLIENT_APPROVED`, `client_approved: false`
- No document text, prompts, evidence, or credentials written to logs
- No uploads persisted; replay cache disabled by default

---

## To make this a real assessment tool

1. **Set `MAMAKSCORE_LLM_BASE_URL`, `_LLM_API_KEY`, `_LLM_MODEL`** and run with `--hosted`. Until then every
   score is the fixture's 4/10.
2. **Configure a vision model** so scanned/image-only decks stop failing with `VISION_REQUIRED`.
3. **Collect human expert scores** for the evaluation corpus and run the agreement study. Without this
   number, the engine has no demonstrated validity.
4. **Decide F4** with the client.
