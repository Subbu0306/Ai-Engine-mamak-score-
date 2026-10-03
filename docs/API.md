# API

## POST /api/evaluate

Multipart fields: `application_id` (required safe identifier), `pitch_deck` (required PDF), `financial_model` (optional XLSX), `use_cache` (default false), and `data_classification` (`public`, `synthetic`, or `confidential`). Confidential input is rejected unless written authorisation is represented by server configuration.

Success is a version `1.0` envelope with UTC `generated_at`, request ID, extraction diagnostics, finance, nine category scores, deterministic MamakScore/band, provisional confidence, flags, 5–10 questions, improvement plan, HTML and provenance.

```json
{"api_version":"1.0","request_id":"demo","generated_at":"2026-09-14T12:00:00Z","assessment":{"application_id":"synthetic-001","mamak_score":"40.0"}}
```

Controlled error example:

```json
{"api_version":"1.0","request_id":"demo","generated_at":"2026-09-14T12:00:00Z","error":{"code":"UNGROUNDED_EVIDENCE","message":"One or more evidence quotations could not be verified.","field":null,"retryable":false,"details":{"criterion_ids":["market"]}}}
```

Other codes: `INVALID_REQUEST`, `UNSUPPORTED_FILE`, `FILE_TOO_LARGE`, `UNREADABLE_PDF`, `ENCRYPTED_PDF`, `VISION_REQUIRED`, `UNREADABLE_WORKBOOK`, `DOCUMENT_TOO_LARGE`, `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `INVALID_MODEL_OUTPUT`, `OVER_CAPACITY`, `INTERNAL_ERROR`.

## POST /api/compare

Takes `previous` and `current` assessment summaries. Different rubric digests are returned as not directly comparable.

## GET /health and GET /ready

Liveness and validated configuration/rubric readiness. Interactive OpenAPI is at `/docs`.
