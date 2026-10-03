#!/usr/bin/env python3
import argparse
import asyncio
import json
from pathlib import Path

from mamakscore.load_testing import run_load

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8000/api/evaluate")
p.add_argument("--deck", type=Path, required=True)
p.add_argument("--requests", type=int, default=20)
p.add_argument("--concurrency", type=int, default=4)
p.add_argument("--max-p90", type=float, default=60)
a = p.parse_args()
result = asyncio.run(run_load(a.url, a.deck, requests=a.requests, concurrency=a.concurrency))
print(json.dumps(result, indent=2))
raise SystemExit(
    0 if result["p90_seconds"] < a.max_p90 and set(result["status_counts"]) <= {"200", "429"} else 1
)
