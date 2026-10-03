# Privacy and Security

Do not process confidential founder material without written authorisation from the client and an appropriate lawful handling arrangement. Public and synthetic decks are the approved default. Setting `MAMAKSCORE_CONFIDENTIAL_PROCESSING_AUTHORIZED=true` is an operator attestation, not legal certification.

Uploads are processed in memory and not stored. Cache is disabled by default because cached evidence may be sensitive. Logs must never contain filenames, document text, workbook values, prompts, evidence, provider responses or keys. The API accepts bytes, not URLs, and applies file, page, text, ZIP expansion, timeout and concurrency limits.

Secrets live only in `.env`/environment variables. Rotate any exposed provider key immediately. This design supports Malaysian PDPA and Australian Privacy Act obligations but does not claim legal compliance certification.
