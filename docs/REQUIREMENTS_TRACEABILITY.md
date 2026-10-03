# Requirements Traceability

Signed-scope mapping. “Pending” means evidence cannot be manufactured without the named external input.

| ID | Requirement | Implementation | Evidence |
|---|---|---|---|
| FR1 | PDF ingestion | `extraction.extract_pdf` | test_extraction.py |
| FR2 | Vision fallback | `extraction + provider.transcribe` | test_extraction.py |
| FR3 | Three XLSX families | `workbook.parse_workbook` | test_workbook.py |
| FR4 | Six fixed formulas | `finance.calculate_financials` | test_finance.py |
| FR5 | Contradictions | `pipeline._normalize_contradictions` | test_pipeline.py |
| FR6 | Nine 0–10 scores | `contracts + intelligence` | test_contracts.py, test_intelligence.py |
| FR7 | Fixed MamakScore | `scoring.calculate_mamak_score` | test_rubric_scoring.py |
| FR8 | Evidence verification | `grounding` | test_grounding.py, test_pipeline.py |
| FR9 | Red flags | `contracts + intelligence + grounding` | test_intelligence.py |
| FR10 | 5–10 investor questions | `intelligence` | test_intelligence.py |
| FR11 | Improvement plan/impact | `scoring.build_improvement_actions` | test_comparison.py |
| FR12 | Structured JSON/HTML | `contracts + report` | test_api.py, test_report.py |
| FR13 | POST /api/evaluate | `api.evaluate` | test_api.py |
| FR14 | Controlled failures | `errors + API mapping` | test_api.py, test_extraction.py |
| FR15 | Provisional confidence | `confidence.calculate_confidence` | test_confidence.py |
| FR16 | Stage scoring | `Out of scope by client decision` | documentation assertion |
| FR17 | Version comparison | `comparison + POST /api/compare` | test_comparison.py, test_api.py |
| NFR1 | p90 <60 seconds | `capacity + load_testing` | test_capacity.py, test_load_script.py; real run pending |
| NFR2 | Extraction ≥90% | `page diagnostics + evaluation protocol` | test_extraction.py; annotated corpus pending |
| NFR3 | Reproducibility | `Decimal scoring + replay cache` | test_rubric_scoring.py, test_cache.py |
| NFR4 | Traceability | `Provenance hashes/versions` | test_pipeline.py |
| NFR5 | Cost ≤$100/month | `provider usage + evaluation aggregate` | test_provider.py; priced run pending |
| NFR6 | Privacy/data protection | `in-memory limits + authorization gate` | test_api.py, test_workbook.py |
| NFR7 | Replaceable AI | `offline and OpenAI-compatible providers` | test_provider.py |
| NFR8 | Maintainability/handover | `docs + local container/Makefile` | test_documentation.py |
| NFR9 | Fairness | `matched-pair metric` | test_evaluation_metrics.py; human set pending |
