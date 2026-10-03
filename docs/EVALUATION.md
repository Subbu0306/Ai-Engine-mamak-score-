# Evaluation

Use Dennis Ong's 447 Pre-Seed/Seed public decks as the source pool. Run `scripts/sample_corpus.py` to select 15 development and 40 sealed test records; the famous-company list excludes contamination from test. Add declared synthetic weak cases because the source corpus has survivorship and US-market bias. Store manifests/hashes, not redistributed decks.

Two humans score each deck independently; a third adjudicates category differences over one point. Freeze labels before opening test results. `scripts/evaluate_labels.py` reports per-category QWK, Spearman, shortlist recall@20%, groundedness, fabrication, stability, demographic sensitivity, latency and cost. Missing human/provider fields are `NOT_RUN`.

Minimum gates from the project plan: fabrication zero; groundedness ≥90%; model-human QWK ≥0.45; Spearman ≥0.55; shortlist recall ≥0.80; real-provider p90 <60 seconds. These cannot be claimed from offline fixtures.
