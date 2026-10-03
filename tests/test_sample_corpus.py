import csv

from mamakscore.sampling import sample_corpus


def test_reproducible_disjoint_in_scope_sampling(tmp_path):
    path = tmp_path / "index.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company", "round", "file"])
        w.writeheader()
        for i in range(70):
            w.writerow(
                {
                    "company": "Airbnb" if i == 0 else f"Company {i}",
                    "round": "Pre-Seed" if i % 2 else "Seed",
                    "file": f"{i}.pdf",
                }
            )
    famous = tmp_path / "famous.txt"
    famous.write_text("Airbnb\n")
    a = sample_corpus(path, famous, seed=2900, dev_count=15, test_count=40)
    b = sample_corpus(path, famous, seed=2900, dev_count=15, test_count=40)
    assert a["records"] == b["records"] and len(a["records"]) == 55
    dev = {r["file"] for r in a["records"] if r["split"] == "dev"}
    test = {r["file"] for r in a["records"] if r["split"] == "test"}
    assert dev.isdisjoint(test) and all(r["round"] in {"Seed", "Pre-Seed"} for r in a["records"])
    assert all(r["company"] != "Airbnb" for r in a["records"] if r["split"] == "test")
