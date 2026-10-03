# MamakScore Full Local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and locally verify the complete PG-S2-29 MamakScore AI Engine through a stable FastAPI contract, without publishing or deploying it externally.

**Architecture:** A stateless pipeline performs local PDF/XLSX extraction and deterministic finance, makes one provider-neutral structured model call, then validates grounding and computes every number in code. A local offline provider and synthetic fixtures make all engineering paths testable without credentials; real-model quality gates remain explicitly not run until human labels and an API key exist.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, PyMuPDF, openpyxl, HTTPX, PyYAML, SQLite, pytest, Ruff, mypy, scikit-learn and SciPy.

**Spec:** `docs/superpowers/specs/2026-09-14-mamakscore-ai-engine-design.md`

## Global Constraints

- Build locally at `/Users/akardhandewan/Desktop/Capstone Project/`; create no GitHub remote or external deployment.
- Accept one PDF pitch deck and optional XLSX financial model; never silently accept PPTX.
- Score exactly nine client categories from 0–10 with weights totalling 100.
- Compute `MamakScore = Σ(score × weight) / 10` in code.
- Any unverified category quotation fails the whole evaluation.
- Use the client's five bands and route scores within five points below a boundary upward for human review.
- MamakConfidence is deterministic and always labelled `PROVISIONAL_NOT_CLIENT_APPROVED`.
- Store no upload; disable replay caching by default.
- Never log document text, prompts, evidence, workbook values or credentials.
- One normal model call; bounded file sizes, deadlines, concurrency and queue wait.
- No automated decline; every result requires human review.
- Real quality, latency and fairness claims remain `NOT_RUN` without human labels/provider credentials.
- Do not create commits or remotes unless the user explicitly requests them.

---

## File Map

- `pyproject.toml`: package, dependency and tool configuration.
- `.env.example`, `.gitignore`: safe local configuration and ignored runtime state.
- `src/mamakscore/contracts.py`: all public and internal Pydantic contracts.
- `src/mamakscore/errors.py`: typed service errors and stable codes.
- `src/mamakscore/config.py`: environment settings and validation.
- `rubric/mamakscore-v3.yaml`, `src/mamakscore/rubric.py`: source-of-truth rubric and strict loader.
- `src/mamakscore/scoring.py`: weighted score, bands, escalation and improvement impacts.
- `src/mamakscore/grounding.py`: strict quotation verification.
- `src/mamakscore/confidence.py`: provisional deterministic confidence.
- `src/mamakscore/comparison.py`: version comparison.
- `src/mamakscore/finance.py`: formulas and metric diagnostics.
- `src/mamakscore/workbook.py`: safe XLSX parsing and aliases.
- `src/mamakscore/extraction.py`: PDF extraction and optional vision fallback.
- `src/mamakscore/provider.py`: offline and OpenAI-compatible provider implementations.
- `src/mamakscore/prompt.py`: prompt/schema construction and hashes.
- `src/mamakscore/intelligence.py`: strict model-output semantic validation.
- `src/mamakscore/cache.py`: optional SQLite replay cache.
- `src/mamakscore/report.py`: escaped accessible HTML report.
- `src/mamakscore/pipeline.py`: one orchestration entry point.
- `src/mamakscore/api.py`, `src/mamakscore/cli.py`: HTTP and command-line surfaces.
- `scripts/sample_corpus.py`, `scripts/evaluate_labels.py`, `scripts/load_test.py`: evaluation and operations tools.
- `tests/`: focused unit, integration, contract, security and load tests.
- `docs/`: API, methodology, privacy, evaluation, operations, limitations, demo and handover guides.
- `Dockerfile`, `compose.yaml`, `Makefile`: reproducible local operation.

---

### Task 1: Package, contracts, rubric and deterministic scoring

**Files:** Create `pyproject.toml`, `.gitignore`, `.env.example`, `src/mamakscore/__init__.py`, `contracts.py`, `errors.py`, `config.py`, `rubric/mamakscore-v3.yaml`, `rubric.py`, `scoring.py`; test with `tests/test_rubric_scoring.py`, `tests/test_contracts.py`.

**Interfaces:** `load_rubric(path: Path) -> RubricDefinition`; `calculate_mamak_score(scores, rubric) -> Decimal`; `classify_score(score) -> BandResult`; strict public contracts for later tasks.

- [ ] Configure a Python 3.12 `src` package. Runtime dependencies: FastAPI, Uvicorn, Pydantic, pydantic-settings, HTTPX, PyMuPDF, openpyxl, PyYAML and python-multipart. Development: pytest, pytest-cov, Ruff, mypy, scikit-learn and SciPy.
- [ ] Write failing tests for exact nine IDs, weights 100, scale 0–10, complete anchors, score extremes, duplicate/missing scores, and boundaries 0/39.9/40/59.9/60/74.9/75/89.9/90/100.

```python
def test_score_extremes_and_decimal_band(rubric, criterion_scores):
    assert calculate_mamak_score(criterion_scores(0), rubric) == Decimal("0.0")
    assert calculate_mamak_score(criterion_scores(10), rubric) == Decimal("100.0")
    band = classify_score(Decimal("74.5"))
    assert band.label == "Potential consideration"
    assert band.boundary_escalation is True
```

- [ ] Run `python -m pytest tests/test_rubric_scoring.py tests/test_contracts.py -q`; confirm collection fails before implementation.
- [ ] Define strict Pydantic models with `extra="forbid"`: `SourceFile`, `PageDiagnostic`, `ExtractionResult`, `FinancialInput`, `FinancialMetric`, `FinancialResult`, `CriterionScore`, `RedFlag`, `InvestorQuestion`, `ImprovementActionDraft`, `ImprovementAction`, `ConfidenceResult`, `Provenance`, `Timing`, `AssessmentResult`, `EvaluationEnvelope`, `ErrorDetail`, `ErrorEnvelope`, `AssessmentSummary`, `ComparisonRequest`, `CategoryMovement`, `ComparisonResult`.

```python
class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str
    score: int = Field(ge=0, le=10)
    justification: str = Field(min_length=1, max_length=4000)
    evidence_quote: str = Field(max_length=4000)
    source_file: str = Field(min_length=1, max_length=255)
    confidence: Literal["high", "medium", "low"]
```

- [ ] Define `ServiceError` with typed code, safe message, field, retryability, status and non-sensitive details.
- [ ] Copy the client weights and all five 0–2/3–4/5–6/7–8/9–10 anchors exactly from Obsidian note 05. Validate exact IDs/weights/scale/anchors and compute a canonical SHA-256 digest.
- [ ] Implement score and band logic:

```python
def calculate_mamak_score(scores, rubric):
    by_id = {item.criterion_id: item for item in scores}
    if set(by_id) != {item.id for item in rubric.criteria} or len(by_id) != len(scores):
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT, "Exactly nine unique category scores are required."
        )
    total = sum(Decimal(by_id[item.id].score) * Decimal(item.weight) for item in rubric.criteria)
    return (total / Decimal(10)).quantize(Decimal("0.1"))
```

Use lower thresholds 90/75/60/40/0; set escalation within five points below the next threshold and always require human review.
- [ ] Run the focused tests; expect all pass.

---

### Task 2: Grounding, confidence, impacts and comparison

**Files:** Create `grounding.py`, `confidence.py`, `comparison.py`; modify `scoring.py`; test with `test_grounding.py`, `test_confidence.py`, `test_comparison.py`.

**Interfaces:** `verify_category_evidence`, `calculate_confidence`, `build_improvement_actions`, `compare_assessments`.

- [ ] Write tests for smart quotes/whitespace acceptance, altered-number rejection, score-zero absent evidence, wrong source, full failure, confidence markers/penalties/clamping, impact validation/deduplication and version compatibility.

```python
def test_altered_number_is_not_grounded():
    sources = {"deck.pdf": "We interviewed 120 customers in Adelaide."}
    score = make_score(score=8, quote="We interviewed 150 customers in Adelaide.")
    with pytest.raises(ServiceError, match="verified"):
        verify_category_evidence([score], sources)
```

- [ ] Normalize with Unicode NFKC, smart quote/dash folding, whitespace collapse and lowercase only. Never remove digits. Empty evidence is valid only for score 0 with the standard absent-evidence justification.
- [ ] Implement confidence as `0.60*coverage + 0.40*strength - penalties`, penalties 2/6/12 for low/medium/high-or-critical, clamp 0–100, one decimal. Evidence markers are digits, currency, percentages, dates, URLs and fixed source phrases. Always return status `PROVISIONAL_NOT_CLIENT_APPROVED` and `client_approved=false`; hide only the numeric value when configured.
- [ ] Validate action criterion/target, calculate `(target-current)*weight/10`, deduplicate normalized action text, and sort by gain descending.
- [ ] Compare equal application IDs; return nine deltas, total/band movement and `comparable=false` with an explicit warning when rubric digests differ.
- [ ] Run focused tests; expect all pass.

---

### Task 3: Deterministic financial engine

**Files:** Create `finance.py`; test with `tests/test_finance.py`.

**Interface:** `calculate_financials(inputs: Mapping[str, FinancialInput]) -> FinancialResult`.

- [ ] Write Decimal-based tests for all six formulas, 0.6/60% margins, missing inputs, zero denominators, non-positive burn, invalid margin and mixed periods.

```python
def test_client_financial_formulas():
    result = calculate_financials(
        financial_inputs(
            customers="100",
            arpu="50",
            gross_margin="0.60",
            operating_expenses="4000",
            cash="12000",
            customer_lifetime="24",
            cac="300",
        )
    )
    assert result.metrics["revenue"].value == Decimal("5000")
    assert result.metrics["gross_profit"].value == Decimal("3000")
    assert result.metrics["burn"].value == Decimal("1000")
    assert result.metrics["runway"].value == Decimal("12")
    assert result.metrics["ltv"].value == Decimal("720")
    assert result.metrics["cac_payback"].value == Decimal("10")
```

- [ ] Run focused test and confirm import failure.
- [ ] Implement client formulas with input lineage. Unavailable reasons are `MISSING_INPUT`, `INCOMPATIBLE_PERIOD`, `ZERO_DENOMINATOR`, `NON_POSITIVE_BURN`, `INVALID_INPUT`; never emit NaN/infinity.
- [ ] Run focused tests; expect all pass.

---

### Task 4: Safe XLSX parser

**Files:** Create `workbook.py`; test with generated workbooks in `tests/test_workbook.py`.

**Interface:** `parse_workbook(data: bytes, filename: str, limits: WorkbookLimits) -> FinancialResult`.

- [ ] Generate tests for all three model families, labels in varied columns, percentages, accounting negatives, formula cells lacking cached values, hidden sheets, corrupt ZIP and hostile compression metadata.
- [ ] Require ZIP magic, <=1,000 entries, <=50 MiB uncompressed total, <=100:1 per-entry ratio, and no traversal names.
- [ ] Parse visible sheets with openpyxl read-only/data-only. Normalize aliases for customers, ARPU, gross margin, operating expenses, cash, customer lifetime, CAC and monthly gross profit per customer. Choose rightmost numeric cell, record cell lineage, and infer units/period only when explicit.
- [ ] Classify `startup`, `simple_sme`, `investor` or `unknown`, call the financial engine, and preserve diagnostics.
- [ ] Run focused tests; expect all pass.

---

### Task 5: PDF extraction and vision fallback

**Files:** Create `extraction.py`; test with in-memory PDFs in `tests/test_extraction.py`.

**Interfaces:** `VisionExtractor.transcribe(pages) -> Mapping[int,str]`; `extract_pdf(data, filename, limits, vision=None) -> ExtractionResult`.

- [ ] Generate tests for text PDF, blank/image-only PDF, mixed pages, fake vision, encryption, zero bytes, corruption, page limit and text limit.
- [ ] Require PDF magic, enforce byte/page limits, reject encryption, extract ordered text and calculate non-whitespace/alphanumeric/printable measures. Mark deficient when fewer than 40 non-whitespace characters or alphanumeric ratio below 0.35.
- [ ] Render only deficient pages at 144 DPI, maximum side 2,048, batches of four. Without configured vision, an all-deficient deck raises `VISION_REQUIRED`.
- [ ] Merge stable `[Page N]` sections, enforce nonempty and maximum text, return digest/method/diagnostics, and persist no bytes.
- [ ] Run focused tests; expect all pass.

---

### Task 6: Provider, prompt and intelligence validation

**Files:** Create `provider.py`, `prompt.py`, `intelligence.py`; test with `test_provider.py`, `test_prompt.py`, `test_intelligence.py`.

**Interfaces:** `AssessmentProvider.assess(ProviderRequest)->ProviderResponse`; optional `VisionProvider.transcribe`; `build_provider_request`; `validate_assessment_draft`.

- [ ] Test untrusted delimiters, all rubric anchors, no model arithmetic, prompt digest semantics, HTTP success/429/5xx/timeout/401/malformed output, exact criterion IDs, question count and target constraints.
- [ ] Build prompt version `1.0`, canonical schema/rubric serialization, prompt-injection resistance, evidence-only rules, 5–10 questions and action target rules.
- [ ] Implement OpenAI-compatible `/chat/completions` adapter with bearer auth, temperature 0, JSON schema, timeout and usage parsing. Retry once only for 429/5xx; never leak response bodies.
- [ ] Implement deterministic `offline-fixture-v1` provider that returns valid grounded output, five questions and actions. Label it as a wiring fixture, never AI evidence.
- [ ] Reject unknown/duplicate/missing criteria, inconsistent empty evidence, bad flags, wrong question count, unknown references and invalid action targets.
- [ ] Run focused tests; expect all pass.

---

### Task 7: Cache, report and end-to-end pipeline

**Files:** Create `cache.py`, `report.py`, `pipeline.py`; test with `test_cache.py`, `test_report.py`, `test_pipeline.py`.

**Interfaces:** `ReplayCache.get/put`; `render_report`; `EvaluationPipeline.evaluate`.

- [ ] Test disabled-cache no-file behaviour, all cache-key dimensions, malformed cache eviction, concurrent consistency, HTML injection escaping, accessibility structure, and all pipeline success/failure variants.
- [ ] Use SQLite WAL with `(key,payload,created_at)`; cache validated provider drafts only and only when server and request opt in.
- [ ] Render escaped script-free HTML with H1/H2 hierarchy, captions/headers, text labels, print styles and visible provisional warning.
- [ ] Orchestrate extraction, optional workbook parsing, provider, semantic validation, grounding, contradiction normalization, deterministic score/band/impacts/confidence, report, provenance and timing. Grounding failure returns no assessment.
- [ ] Run focused tests; expect all pass.

---

### Task 8: FastAPI, CLI, controlled errors and capacity

**Files:** Create `api.py`, `cli.py`, `__main__.py`; test with `test_api.py`, `test_cli.py`, `test_capacity.py`.

**Interfaces:** `POST /api/evaluate`, `POST /api/compare`, `GET /health`, `GET /ready`; console command `mamakscore`.

- [ ] Test multipart success, compare, OpenAPI schemas, invalid IDs/types/limits, request-ID propagation, error mappings, 429 saturation/recovery and CLI exits.
- [ ] Build `create_app(settings,pipeline=None)` with lifespan dependencies and safe UUID request IDs.
- [ ] Read uploads in 64 KiB chunks, stop above limits, sanitize filenames, and distrust Content-Length.
- [ ] Gate work with `asyncio.Semaphore`, bounded `wait_for`, 429 plus Retry-After, thread-pool execution and `finally` release.
- [ ] Map known errors safely; unknown errors log request ID/type only. JSON logs contain timings/counts/hashes, no submitted content.
- [ ] Implement CLI `serve`, `evaluate`, `compare`, `check-config`; default to offline mode unless hosted configuration is explicit.
- [ ] Run focused tests; expect all pass.

---

### Task 9: Evaluation, sampling and load tools

**Files:** Create `scripts/sample_corpus.py`, `scripts/evaluate_labels.py`, `scripts/load_test.py`, `eval/famous_companies.txt`, `eval/labels.example.jsonl`; test with `test_sample_corpus.py`, `test_evaluation_metrics.py`, `test_load_script.py`.

- [ ] Test deterministic 15/40 sampling from synthetic index, in-scope rounds, disjoint splits, famous-company exclusion, hashes and insufficient rows.
- [ ] Implement sampling with stdlib CSV/random/hashlib; output manifest only, never copy decks.
- [ ] Test known-answer QWK, Spearman, recall, grounding, fabrication, stability and paired fairness.
- [ ] Use sklearn QWK and SciPy Spearman. Output JSON/Markdown with dataset/model/rubric/prompt versions. Missing inputs are `NOT_RUN`.
- [ ] Implement bounded async HTTPX load client with status counts, throughput, p50 and nearest-rank p90; nonzero exit on unexpected errors/threshold failure; label offline results `service-overhead-only`.
- [ ] Run focused tests; expect all pass.

---

### Task 10: Documentation, local operation and final verification

**Files:** Create `README.md`, `Makefile`, `Dockerfile`, `compose.yaml`, `docs/API.md`, `METHODOLOGY.md`, `PRIVACY.md`, `EVALUATION.md`, `OPERATIONS.md`, `LIMITATIONS.md`, `DEMO.md`, `HANDOVER.md`, `REQUIREMENTS_TRACEABILITY.md`; test with `tests/test_documentation.py`.

- [ ] Assert all docs exist; README links design/plan; traceability names FR1–FR17/NFR1–NFR9; privacy forbids confidential data; methodology includes exact formula/provisional status; API includes success/error examples.
- [ ] Build non-root local container; compose binds `127.0.0.1:8000`; Make targets `install`, `test`, `lint`, `typecheck`, `quality`, `serve`, `demo`, `load-test`, `clean`.
- [ ] Document architecture, contract, rubric provenance, formulas, grounding, prompt/versioning, confidence warning, provider replacement, environment, privacy, capacity, cache policy, metrics, limitations, demo and handover. Map every requirement to implementation/test; mark FR16 out and empirical gates not run.
- [ ] Run `ruff check`, `ruff format --check`, `mypy src scripts`, and `pytest --cov=mamakscore --cov-fail-under=80`; all must exit 0.
- [ ] Run `pip check`; run `pip-audit` if installed or record the skipped check honestly. Scan files for secrets and verify runtime/private artifacts are ignored.
- [ ] Run three offline end-to-end rehearsals, excluding volatile fields when comparing, and save aggregate results only.
- [ ] Verify from a fresh external virtual environment: install local package, run tests, start localhost service, call health/ready/evaluate, stop cleanly, and record measured outcomes.
- [ ] Perform Python, FastAPI, ML, security/privacy and silent-failure reviews; fix every confirmed high-severity issue and rerun all checks.
- [ ] Produce `reports/completion.json` and `.md` with evidence for every gate. Human-label, provider and client-approval gates are `NOT_RUN_EXTERNAL_INPUT_REQUIRED`.

---

## Requirement Coverage Matrix

| Requirement | Implementation task | Acceptance evidence |
|---|---:|---|
| FR1 PDF ingestion | 5, 8 | text-PDF extraction and multipart API tests |
| FR2 image fallback | 5, 6 | mixed/image-only PDF tests with fake vision |
| FR3 three XLSX families | 4 | generated startup, SME and investor workbook tests |
| FR4 six fixed formulas | 3 | Decimal known-answer and unavailable-input tests |
| FR5 contradiction surfacing | 6, 7 | verified claim/computed-metric red-flag tests |
| FR6 nine category scores | 1, 6 | exact-ID, 0–10 and structured-output tests |
| FR7 fixed MamakScore | 1 | extremes, weighted fixture and boundaries |
| FR8 evidence validation | 2, 7 | altered-number quote fails whole pipeline |
| FR9 red flags | 6, 7 | type, severity, evidence and missing-info validation |
| FR10 investor questions | 6 | 5–10 count, uniqueness and traceability tests |
| FR11 improvement plan | 2, 7 | model text plus code-calculated impact tests |
| FR12 structured report | 7 | JSON contract and escaped accessible HTML tests |
| FR13 POST /api/evaluate | 8 | multipart integration and OpenAPI tests |
| FR14 controlled failures | 5, 8 | corrupt/encrypted/type/size/error-envelope tests |
| FR15 MamakConfidence | 2 | deterministic formula and mandatory provisional warning |
| FR16 stage profiles | excluded by client | traceability records out-of-scope decision |
| FR17 version comparison | 2, 8 | deterministic comparison endpoint tests |
| NFR1 p90 <60s | 8, 9 | bounded service and real-provider load report |
| NFR2 extraction ≥90% | 5, 9 | annotation-capable extraction metric, external corpus pending |
| NFR3 reproducibility | 1, 7 | pure scoring and cache/provenance tests |
| NFR4 traceability | 1, 7 | model/rubric/prompt/input/formula digests |
| NFR5 cost ≤$100/month | 6, 9 | token/cost capture and evaluation report |
| NFR6 privacy | 4, 5, 7, 8 | no persistence/log content and safety-limit tests |
| NFR7 replaceable AI | 6 | provider protocol and two implementations |
| NFR8 maintainability | 10 | clean install, operations and handover verification |
| NFR9 fairness | 9 | matched-pair demographic sensitivity metric |

## Execution Mode

Execute inline in this session. The user requested continuous autonomous completion and did not request subagents. Pause only for irreversible external action, credentials, or a requirements decision without a safe default. GitHub and external deployment are excluded.
