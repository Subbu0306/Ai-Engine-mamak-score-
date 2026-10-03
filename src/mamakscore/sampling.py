# Reproducible, contamination-aware corpus manifest selection.
from __future__ import annotations

import csv
import hashlib
import random
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _value(row: Mapping[str, str], names: tuple[str, ...]) -> str:
    return next((row.get(name, "").strip() for name in names if row.get(name, "").strip()), "")


def sample_corpus(
    index_path: Path,
    famous_path: Path,
    *,
    seed: int = 2900,
    dev_count: int = 15,
    test_count: int = 40,
) -> dict[str, Any]:
    raw = index_path.read_bytes()
    famous = {
        line.strip().casefold()
        for line in famous_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    with index_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    eligible = []
    for row in rows:
        round_name = _value(row, ("round", "funding_round"))
        if round_name.casefold() not in {"seed", "pre-seed", "pre seed"}:
            continue
        company = _value(row, ("company_name", "company", "display_name"))
        filename = _value(row, ("file_name", "file", "filename"))
        if not company or not filename:
            continue
        eligible.append(
            {
                "company": company,
                "round": "Pre-Seed"
                if round_name.casefold() in {"pre-seed", "pre seed"}
                else "Seed",
                "file": filename,
            }
        )
    rng = random.Random(seed)
    nonfamous = [r for r in eligible if r["company"].casefold() not in famous]
    if len(nonfamous) < test_count or len(eligible) < dev_count + test_count:
        raise ValueError("Not enough eligible non-famous records for requested splits")
    test = rng.sample(sorted(nonfamous, key=lambda r: (r["company"], r["file"])), test_count)
    test_files = {r["file"] for r in test}
    remaining = [r for r in eligible if r["file"] not in test_files]
    dev = rng.sample(sorted(remaining, key=lambda r: (r["company"], r["file"])), dev_count)
    records = [
        {
            **r,
            "split": "dev",
            "record_hash": hashlib.sha256(
                (r["company"] + r["round"] + r["file"]).encode()
            ).hexdigest(),
        }
        for r in dev
    ]
    records += [
        {
            **r,
            "split": "test",
            "record_hash": hashlib.sha256(
                (r["company"] + r["round"] + r["file"]).encode()
            ).hexdigest(),
        }
        for r in test
    ]
    return {
        "seed": seed,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(),
        "dev_count": dev_count,
        "test_count": test_count,
        "famous_excluded_from_test": sorted(famous),
        "records": records,
    }
