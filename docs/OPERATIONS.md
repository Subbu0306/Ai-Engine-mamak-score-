# Local Operations

Install with `make install`, verify with `make quality`, start with `make serve`, and inspect `/health`, `/ready`, and `/docs`. Compose binds only `127.0.0.1:8000`.

Capacity is per process: total model concurrency = worker count × `MAMAKSCORE_MAX_CONCURRENCY`. Saturated requests wait only `MAMAKSCORE_QUEUE_WAIT_SECONDS` then receive 429 and `Retry-After`. Keep whole-request timeout below upstream request timeout.

Hosted operation requires base URL, key and model. Vision fallback additionally requires a vision model. Cache is opt-in for public/demo decks only. Back up rubric, source and evaluation manifests; uploaded documents are never service state. Stop with Ctrl-C or `docker compose down`.
