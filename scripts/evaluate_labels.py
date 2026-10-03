#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from mamakscore.evaluation import compute_metrics

p = argparse.ArgumentParser()
p.add_argument("labels", type=Path)
p.add_argument("--output-dir", type=Path, required=True)
a = p.parse_args()
records = [json.loads(line) for line in a.labels.read_text().splitlines() if line.strip()]
result = compute_metrics(records)
a.output_dir.mkdir(parents=True, exist_ok=True)
(a.output_dir / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
(a.output_dir / "metrics.md").write_text(
    "# Evaluation Metrics\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in result.items()) + "\n"
)
