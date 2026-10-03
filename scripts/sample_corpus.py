#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from mamakscore.sampling import sample_corpus

p = argparse.ArgumentParser()
p.add_argument("index", type=Path)
p.add_argument("--famous", type=Path, required=True)
p.add_argument("--seed", type=int, default=2900)
p.add_argument("--dev", type=int, default=15)
p.add_argument("--test", type=int, default=40)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
a.output.write_text(
    json.dumps(
        sample_corpus(a.index, a.famous, seed=a.seed, dev_count=a.dev, test_count=a.test), indent=2
    )
    + "\n"
)
