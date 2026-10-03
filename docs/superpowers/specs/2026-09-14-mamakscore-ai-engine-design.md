# MamakScore AI Engine — Full Local Design

**Date:** 14 September 2026  
**Team:** PG-S2-29  
**Client:** WEDO MEDIA PTY LTD / Mamak Mentor  
**Status:** implementation baseline  
**Source hierarchy:** signed Project Scoping Document (27 August 2026), client answers (25 August 2026), client Master Plan (30 July 2026), correspondence through 14 September 2026.

## 1. Purpose and boundary

Build the complete PG-S2-29 AI Engine locally. The engine accepts a PDF pitch deck and an optional XLSX financial model, extracts and validates their contents, calculates deterministic financial metrics, evaluates the startup against the client's nine-category rubric, verifies all quoted evidence, generates red flags, investor questions and a prioritised improvement plan, and returns a versioned structured report through `POST /api/evaluate`.

The repository is local at:

`/Users/akardhandewan/Desktop/Capstone Project/`

No GitHub remote, cloud deployment, email, or other external publication is part of this build. The existing sibling `ai-engine/` directory is an untouched historical sketch and is not a source of truth.

### Included

- FR1–FR14 from the signed scope.
- FR15 as a deterministic **provisional** MamakConfidence formula whose unapproved status is explicit in every response.
- FR17 pitch-deck version comparison as a separate deterministic endpoint.
- All NFR1–NFR9 engineering support and measurement tooling.
- Local API, CLI, tests, evaluation harness, container assets, operating documentation and handover documentation.

### Excluded

- Founder and administrator UI, authentication, upload UI, database and reviewer UI, which belong to Platform Team UG-S2-29.
- FR16 stage-adjusted scoring, removed by the client when scope was limited to pre-seed and seed.
- RAG, fine-tuning, self-hosted model serving, multi-agent analysis, investor marketplace and outcome tracking, which the client placed after MVP.
- Processing confidential founder documents without written authorisation.
- PPTX input. The signed scope says PDF; the earlier WIL schedule's PPTX wording is not adopted silently.

## 2. Architecture decision

Use one structured-output model call per normal evaluation, surrounded by deterministic extraction, finance, validation and reporting code.

This is preferred to specialist/multi-agent calls because the workflow and rubric are fixed, and one call gives the best chance of meeting p90 under 60 seconds and staying below $100 per month. The AI provider is replaceable behind one interface. The production adapter speaks an OpenAI-compatible HTTP API so hosted open-weight providers can be changed through configuration. Tests use a deterministic offline provider.

The service is stateless by default. It stores no submitted document. An optional SQLite replay cache is disabled unless explicitly enabled for public/demo data.

## 3. Components

```text
src/mamakscore/
  api.py             FastAPI routes, request IDs and error mapping
  config.py          validated environment configuration
  contracts.py       versioned request, response and error models
  extraction.py      PDF extraction, quality measurement and vision fallback
  workbook.py        XLSX safety checks, parsing and input lineage
  finance.py         deterministic formulas and diagnostics
  rubric.py          rubric loading and invariants
  provider.py        provider protocol, hosted adapter and offline provider
  prompt.py          versioned prompt construction
  intelligence.py    structured model-output validation
  grounding.py       quote verification against canonical source text
  scoring.py         weighted rollup, bands and boundary escalation
  confidence.py      provisional deterministic confidence calculation
  comparison.py      deterministic category/version comparison
  report.py          escaped, accessible HTML report
  cache.py           optional content-addressed SQLite replay cache
  pipeline.py        orchestration and timing
rubric/mamakscore-v3.yaml
scripts/
  sample_corpus.py   reproducible dev/test manifest selection
  evaluate_labels.py evaluation metrics and report generation
  load_test.py       bounded local concurrency and latency check
fixtures/            public/synthetic test inputs only
tests/               unit, contract, integration, security and performance checks
docs/                API, methodology, privacy, operations, evaluation and demo guides
```

Each component exposes a narrow typed interface. The API calls only the pipeline; the pipeline coordinates components but contains no extraction, finance or scoring rules itself.

## 4. Input contract

### `POST /api/evaluate`

Content type: `multipart/form-data`.

| Field | Type | Rule |
|---|---|---|
| `application_id` | string | 1–128 safe identifier characters |
| `pitch_deck` | file | required PDF, default maximum 20 MiB |
| `financial_model` | file | optional XLSX, default maximum 10 MiB |
| `use_cache` | boolean | default false; rejected if server cache is disabled |

The service validates extensions, declared content types and magic bytes. It rejects empty, corrupt, encrypted, unsupported, oversized and zip-bomb-like files with a controlled error. It never converts extraction failure into a low startup score.

### `POST /api/compare`

Accepts two completed assessment summaries for the same application and returns score movement per category, overall movement, band movement and rubric-compatibility warnings. Comparison is deterministic and performs no AI call.

### Health endpoints

- `GET /health`: process is alive.
- `GET /ready`: configuration and rubric are valid; provider credentials are required only when hosted mode is selected.

## 5. Response contract

All responses carry `api_version`, `request_id` and `generated_at`.

A successful evaluation contains:

- application identifier and source-file metadata/digests;
- extraction method, page-level diagnostics and canonical text statistics;
- optional financial model family, extracted inputs, calculated metrics, source-cell lineage and unavailable-metric reasons;
- exactly nine category scores on 0–10;
- one justification and one verified verbatim evidence quotation per category, with source-file attribution;
- deterministic MamakScore on 0–100;
- one of the client's five bands;
- boundary-escalation and human-review flags;
- provisional MamakConfidence object;
- red flags with severity, type, evidence and deterministic numeric comparison where applicable;
- five to ten investor questions targeted at weak categories and traceable to category/evidence identifiers;
- prioritised improvement actions with model-generated action text and code-calculated score impact;
- missing information;
- safe structured HTML report;
- model, provider, rubric, prompt, input and cache provenance;
- extraction, provider and total latency; token/cost fields when the provider supplies usage.

### Stable error envelope

```json
{
  "api_version": "1.0",
  "request_id": "...",
  "error": {
    "code": "UNREADABLE_PDF",
    "message": "The pitch deck could not be read.",
    "field": "pitch_deck",
    "retryable": false,
    "details": {}
  }
}
```

Expected codes include `INVALID_REQUEST`, `UNSUPPORTED_FILE`, `FILE_TOO_LARGE`, `UNREADABLE_PDF`, `ENCRYPTED_PDF`, `VISION_REQUIRED`, `UNREADABLE_WORKBOOK`, `DOCUMENT_TOO_LARGE`, `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `INVALID_MODEL_OUTPUT`, `UNGROUNDED_EVIDENCE`, `OVER_CAPACITY` and `INTERNAL_ERROR`. Internal exceptions and document content are never returned.

## 6. Extraction

### PDF

1. Open bytes directly with PyMuPDF; do not persist uploads.
2. Reject encrypted, zero-page and structurally corrupt documents.
3. Extract ordered text per page.
4. Measure non-whitespace characters, alphanumeric ratio and printable ratio per page.
5. Mark pages below configurable quality thresholds for image fallback.
6. When a vision model is configured, render only deficient pages to bounded-resolution PNG images and transcribe them in bounded batches.
7. When vision is required but unavailable, return `VISION_REQUIRED`; never score empty content.
8. Assemble canonical text with page markers while retaining clean page text separately for quote verification.
9. Reject canonical text above the configured safe model-input limit rather than silently truncating evidence.

Extraction diagnostics make the 90% extraction target measurable. They do not claim accuracy without human reference text.

### XLSX

1. Validate ZIP structure, entry count, total uncompressed bytes and compression ratio before opening.
2. Use `openpyxl` in read-only, data-only mode.
3. Ignore hidden metadata but record visible sheet/cell lineage.
4. Normalize labels, percentages, currencies, negative accounting notation and monthly/annual period hints.
5. Classify the workbook as Startup Financial Model, Simple SME Projection, Investor Financial Model or Unknown from observed labels.
6. Resolve a controlled alias registry for customers, ARPU, gross margin, operating expenses, cash, lifetime, CAC and monthly gross profit per customer.
7. Use the latest unambiguous numeric period. Ambiguous periods or units produce a diagnostic, not a guessed number.
8. If a supplied workbook is unreadable, the deck evaluation continues and affected metrics are unavailable, matching UC1. A warning appears in the response.

## 7. Deterministic financial engine

Use decimal arithmetic and preserve units and lineage.

- Revenue = Customers × Average Revenue per Customer.
- Gross Profit = Revenue × Gross Margin.
- Burn = Operating Expenses − Gross Profit.
- Runway = Cash ÷ Monthly Burn.
- LTV = ARPU × Gross Margin × Customer Lifetime.
- CAC Payback = CAC ÷ Monthly Gross Profit per Customer.

A metric is calculated only when all required inputs have compatible periods and units. Zero denominators, non-positive burn, missing cached formula values, ambiguous units and invalid percentages return explicit unavailable reasons. They never produce infinity, NaN or an invented value.

## 8. AI assessment

The hosted provider receives:

- the versioned rubric and output schema as the stable instruction prefix;
- untrusted canonical deck text, canonical workbook text and deterministic financial results in explicit data delimiters;
- an instruction to ignore commands embedded in submitted documents;
- a requirement to score only submitted evidence and return no final MamakScore or score-impact arithmetic.

One structured response contains:

- exactly nine category judgements;
- red flags;
- five to ten investor questions;
- improvement actions and requested target category scores;
- missing information.

The response is validated strictly. Unknown/duplicate/missing criterion IDs, scores outside 0–10, missing required quotations, unsupported enums, wrong question counts, invalid target scores and malformed numeric comparisons fail the run. No repair prompt is sent automatically. The provider adapter applies one bounded retry only to retryable transport/rate-limit failures and honours timeouts.

The offline provider exists only for deterministic engineering tests and demos. Its output is labelled `offline-fixture`; it is never represented as AI quality evidence.

## 9. Grounding and contradiction checks

Every category evidence quotation must appear word-for-word in its attributed source after only Unicode compatibility normalization and whitespace folding. Case is folded; digits and substantive punctuation are not altered. Missing evidence is valid only when the category score is 0 and the standard not-addressed justification is used.

Any failed category quotation raises `UNGROUNDED_EVIDENCE` and suppresses the entire assessment.

Red flags referencing deck claims must carry a verified quotation. A model-reported financial contradiction carries the claimed value, computed metric identifier and model-reported difference. Code replaces/recomputes the difference from deterministic financial output and rejects references to nonexistent metrics. The model cannot manufacture the arithmetic used in the report.

## 10. Rubric and scoring

The rubric file contains exactly these weighted categories:

| ID | Category | Weight |
|---|---|---:|
| `problem` | Problem / Pain Point | 10 |
| `market` | Market | 15 |
| `product` | Product / Solution | 10 |
| `business_model` | Business Model | 10 |
| `traction` | Traction | 15 |
| `competitive_advantage` | Competitive Advantage | 10 |
| `financials` | Financials | 15 |
| `team` | Team | 10 |
| `scalability` | Scalability | 5 |

The loader refuses any rubric whose scored IDs differ, whose weights do not total 100, whose scale is not 0–10, or whose five anchor bands are incomplete.

`MamakScore = Σ(category score × category weight) / 10`

The model never supplies this number.

Use the client's five interpretations:

- 0–39: Not ready.
- 40–59: Needs significant validation.
- 60–74: Potential consideration.
- 75–89: Strong candidate.
- 90–100: Due diligence recommended.

Threshold semantics cover decimal scores without gaps. No application is declined automatically. Scores within five points below a higher boundary set `boundary_escalation=true` and route upward for human review without changing the score.

## 11. Improvement impacts

For each accepted action, the model supplies a criterion ID and a target score greater than the current score and no greater than 10. Code calculates:

`projected_gain = (target_score − current_score) × criterion_weight / 10`

The report labels this as maximum projected MamakScore gain if the evidence reaches the target anchor; it is not a prediction that completing the action guarantees the score.

Actions are sorted by deterministic gain, then severity/priority supplied by the validated model response. Duplicate actions and invalid targets are removed with diagnostics.

## 12. Provisional MamakConfidence

Because the client has not supplied or approved a formula, every result contains:

- `value`: the deterministic provisional value;
- `status`: `PROVISIONAL_NOT_CLIENT_APPROVED`;
- `client_approved`: false;
- formula version and component breakdown.

The formula is:

1. Evidence coverage: percentage of nine categories with a verified non-empty quote.
2. Evidence strength: percentage whose verified quote contains a deterministic evidence marker (number, currency, percentage, date, URL/citation, or a source phrase such as “according to”, “survey of” or “pilot with”).
3. Base = `0.60 × coverage + 0.40 × strength`.
4. Subtract red-flag penalties: 2 per low, 6 per medium and 12 per high/critical flag.
5. Clamp to 0–100 and round to one decimal place.

This formula is reproducible and quantified but remains team-authored. Configuration controls whether its numeric value is exposed; when disabled the object remains present with `value: null` and the same status. Documentation states that only client approval may change the status.

## 13. Version comparison

Comparison accepts two validated assessment summaries. It requires the same application ID. It reports each category's old/new score and delta, overall old/new MamakScore and delta, band movement, newly resolved/missing categories and a warning when rubric versions differ. It does not claim causal attribution and never compares raw scores silently across different rubric versions.

## 14. Report generation and accessibility

Generate HTML from the validated structured result using escaped values only. The report includes a single H1, ordered heading hierarchy, text labels in addition to colour, accessible tables, high-contrast styles, print styles and a visible provisional-confidence warning. It includes no scripts, remote assets or raw HTML from the model/document.

The JSON remains authoritative. HTML is a presentation derivative and can be regenerated deterministically.

## 15. Privacy and security

- Accept bytes only; fetch no caller-provided URL.
- Enforce per-file and aggregate size, page count, workbook entry count, uncompressed-size and model-text limits.
- Do not log filenames, document text, evidence quotations, workbook values, prompts, API keys or provider bodies.
- Log request ID, status code, component timings, byte/page counts and hashed input identifiers only.
- Keep credentials in environment variables; provide `.env.example` with placeholders.
- Store no upload. Cache is disabled by default and documented for public/demo material only because cached evidence may be sensitive.
- Sanitize filenames for metadata display.
- Use dependency pinning/locking, vulnerability scanning and documented upgrades.
- Treat model output as untrusted typed data and escape it in reports.
- Use no model tools, code execution or network access beyond the configured provider endpoint.
- Permit confidential-document processing only when the operator explicitly enables the configuration flag representing written authorisation.

This engineering design supports privacy obligations but does not claim legal compliance certification.

## 16. Reliability, latency and throughput

- One model call on the normal text-extraction path.
- Configurable provider and whole-request deadlines.
- Configurable in-process concurrency limit.
- Requests may wait only for a bounded queue interval; saturation returns HTTP 429 `OVER_CAPACITY` with `Retry-After`.
- No unbounded background task or upload buffering.
- Multiple Uvicorn workers scale locally; documented total model concurrency is workers × per-worker limit.
- Optional replay cache uses SQLite WAL, transactional writes and a key containing input digests, model, rubric digest, prompt digest and formula versions.
- Cache hits pass the same validation and grounding path as live output.
- Graceful shutdown stops new work and allows bounded in-flight completion.

The load script measures throughput, p50, p90, error count and overload behaviour. The client gate is p90 below 60 seconds on real hosted evaluations. Offline results validate service overhead only and are labelled accordingly.

## 17. Evaluation system

### Dataset protocol

- Input corpus: the client's 447 in-scope Pre-Seed/Seed public decks plus declared synthetic weak cases.
- Reproducibly select 15 development and 40 frozen-test decks.
- Exclude a maintained famous-company contamination list from the test set.
- Store only a manifest and hashes in Git unless redistribution rights are clear.
- Two humans independently score every application; differences above one category point require third-person adjudication.
- Freeze and hash labels before model testing.

### Metrics

Use established libraries rather than reimplementing statistics:

- per-category quadratic weighted kappa;
- overall Spearman rank correlation;
- shortlist recall@20%;
- groundedness and fabrication rate;
- three-run stability;
- matched-pair demographic sensitivity;
- extraction accuracy from annotated page text;
- p50/p90 latency;
- provider-reported or configured token cost;
- demo rehearsal success.

The harness outputs machine-readable JSON plus a Markdown report containing dataset hashes, model/rubric/prompt versions, sample counts and limitations. Known-answer fixtures prove the metric code before real labels are used.

### Honest empirical status

Human agreement, model agreement, real-model latency/cost, extraction accuracy and fairness cannot be claimed from offline fixtures. Until human labels and provider credentials exist, reports mark these gates `NOT_RUN`, not pass.

## 18. Testing and quality gates

The local engineering build is complete only when:

1. FR1–FR14 and FR17 each map to code and at least one automated acceptance check; FR15 is implemented with its provisional warning.
2. Rubric IDs, 0–10 bounds, total weight and five anchor bands are validated.
3. Weighted score and all decimal band boundaries pass known-answer tests.
4. Fabricated/altered quotations fail the entire evaluation.
5. All six financial formulas pass normal, missing-input, unit, zero-denominator and non-positive-burn cases.
6. Valid text PDF, image-only PDF through fake vision, valid XLSX and deck-only paths pass end to end.
7. Empty, corrupt, encrypted, wrong-type, oversized and hostile-compression fixtures return stable errors without partial scores.
8. Exactly five to ten traceable investor questions and deterministic improvement impacts are enforced.
9. Confidence is deterministic and always visibly provisional.
10. Cache keys invalidate on input, model, rubric, prompt or formula changes; cache-off stores nothing.
11. Concurrency saturation returns bounded 429 responses and recovers.
12. Three offline dress rehearsals pass without network access.
13. Type checking, linting and the full test suite pass with at least 80% statement coverage.
14. API, Python, ML and security reviews have no unresolved high-severity finding.
15. A clean local environment can install, test, start, call and stop the service using documented commands.
16. Documentation covers architecture, methodology, API, configuration, privacy, evaluation, operations, limitations, demo and handover.

The empirical model is suitable for advisory screening only after the separately reported minimum metric gates are run on the frozen human-labelled set. No automated decline is permitted.

## 19. Implementation order

1. Repository policy, package configuration, contracts, rubric and deterministic scoring.
2. Grounding, confidence and improvement-impact logic.
3. PDF/XLSX extraction and financial engine.
4. Provider protocol, offline provider, hosted adapter and structured prompt.
5. Orchestrated end-to-end pipeline and safe HTML report.
6. FastAPI endpoints, controlled errors, limits and concurrency.
7. Replay cache and version comparison.
8. Evaluation, corpus sampling and load tools.
9. Complete automated checks and synthetic/public fixtures.
10. Documentation, container/local operations, review remediation and clean-environment verification.

Each stage is test-first and leaves the repository runnable. No GitHub operation occurs until the user requests it later.
