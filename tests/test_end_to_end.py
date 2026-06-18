"""End-to-end: import a module, generate a cohort, export CSV (PLAN.md milestone 5)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig
from psynthea.export import export_csv

_ROOT = Path(__file__).resolve().parents[1]


def _otitis():
    return load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")


def test_generate_cohort_produces_conditions():
    module = _otitis()
    config = GeneratorConfig(population=200, seed=42, end_date=datetime(2025, 1, 1),
                             min_age=0, max_age=60)
    people = Generator([module], config).run()
    assert len(people) == 200

    total_conditions = sum(len(p.record.conditions) for p in people)
    total_meds = sum(len(p.record.medications) for p in people)
    # The module only triggers otitis under age 8, so some — but not all — people
    # should have acquired the condition, and every condition pairs with a med.
    assert total_conditions > 0
    assert total_meds > 0
    assert total_conditions == total_meds  # one amoxicillin order per diagnosis


def test_reproducible_with_same_seed():
    module = _otitis()
    cfg = GeneratorConfig(population=50, seed=7, end_date=datetime(2025, 1, 1), max_age=40)
    a = Generator([module], cfg).run()
    b = Generator([module], cfg).run()
    assert [p.id for p in a] == [p.id for p in b]
    assert [len(p.record.conditions) for p in a] == [len(p.record.conditions) for p in b]


def test_csv_export_writes_valid_tables(tmp_path):
    module = _otitis()
    cfg = GeneratorConfig(population=30, seed=3, end_date=datetime(2025, 1, 1), max_age=20)
    people = Generator([module], cfg).run()
    counts = export_csv(people, tmp_path)

    assert counts["patients.csv"] == 30
    for name in ("patients", "encounters", "conditions", "medications", "observations"):
        path = tmp_path / f"{name}.csv"
        assert path.exists()
        with path.open() as fh:
            rows = list(csv.reader(fh))
        assert len(rows) >= 1  # at least a header

    # conditions should reference a real encounter id from encounters.csv
    enc_ids = {r[0] for r in csv.reader((tmp_path / "encounters.csv").open())} - {"Id"}
    with (tmp_path / "conditions.csv").open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            assert row["ENCOUNTER"] in enc_ids
