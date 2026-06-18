"""The `generate --profile-file` flag (demographic matching for cross-engine fidelity)."""
from __future__ import annotations

import csv
import json

from psynthea.cli import _load_profile, main


def _write_profile(path):
    path.write_text(json.dumps({"bands": [[60, 80, 1.0, 1.0]]}), encoding="utf-8")
    return path


def test_load_profile_from_json(tmp_path):
    prof = _load_profile(str(_write_profile(tmp_path / "p.json")))
    age, sex = prof.sample(__import__("random").Random(0))
    assert 60 <= age < 80 and sex in {"M", "F"}


def test_generate_with_profile_constrains_ages(tmp_path):
    prof = _write_profile(tmp_path / "p.json")
    out = tmp_path / "out"
    rc = main(["generate", "-m", "otitis_media", "-p", "30", "-o", str(out),
               "--seed", "1", "--profile-file", str(prof), "--end-date", "2025-01-01"])
    assert rc == 0
    years = [int(r["BIRTHDATE"][:4]) for r in csv.DictReader((out / "patients.csv").open())]
    # ages 60-80 at 2025 -> birth years 1945-1965
    assert years and all(1945 <= y <= 1965 for y in years)
