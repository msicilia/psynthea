"""Tests for ground-truth label emission (ADR-016 capability A)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig
from psynthea.export import export_ground_truth

_ROOT = Path(__file__).resolve().parents[1]


def _cohort():
    module = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    cfg = GeneratorConfig(population=120, seed=9, end_date=datetime(2025, 1, 1), max_age=40)
    return Generator([module], cfg).run()


def _rows(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def test_provenance_records_generating_module_and_state(tmp_path):
    counts = export_ground_truth(_cohort(), tmp_path)
    assert counts["gt_provenance.csv"] > 0
    prov = _rows(tmp_path / "gt_provenance.csv")
    # every event names the module that produced it
    assert all(r["SOURCE_MODULE"] == "otitis_media" for r in prov)
    # conditions came from the diagnosis state; drugs from the prescribe state
    conds = [r for r in prov if r["DOMAIN"] == "condition"]
    meds = [r for r in prov if r["DOMAIN"] == "medication"]
    assert conds and all(r["SOURCE_STATE"] == "Diagnose_Otitis_Media" for r in conds)
    assert meds and all(r["SOURCE_STATE"] == "Prescribe_Amoxicillin" for r in meds)
    assert all(r["CODE"] == "65363002" for r in conds)


def test_trajectories_capture_latent_path(tmp_path):
    export_ground_truth(_cohort(), tmp_path)
    traj = _rows(tmp_path / "gt_trajectories.csv")
    states_seen = {r["STATE"] for r in traj}
    # latent control states (no observable event) are still recorded
    assert "Annual_Check" in states_seen
    assert "Initial" in states_seen
    # patients who got otitis pass through the encounter/diagnosis path
    assert "Diagnose_Otitis_Media" in states_seen


def test_phenotypes_record_assigned_attribute(tmp_path):
    export_ground_truth(_cohort(), tmp_path)
    pheno = _rows(tmp_path / "gt_phenotypes.csv")
    otitis = [r for r in pheno if r["ATTRIBUTE"] == "otitis_media"]
    assert otitis, "expected otitis_media cohort membership labels"
    assert all(r["VALUE"] == "65363002" for r in otitis)  # entry's code surfaced


def test_provenance_aligns_with_record_counts(tmp_path):
    people = _cohort()
    counts = export_ground_truth(people, tmp_path)
    total_events = sum(len(p.record.encounters) + len(p.record.conditions)
                       + len(p.record.medications) + len(p.record.observations)
                       for p in people)
    assert counts["gt_provenance.csv"] == total_events
