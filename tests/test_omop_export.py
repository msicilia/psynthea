"""Tests for the OMOP CDM v5.4 exporter (ADR-007)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig
from psynthea.export import export_omop

_ROOT = Path(__file__).resolve().parents[1]


def _cohort():
    module = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    cfg = GeneratorConfig(population=80, seed=5, end_date=datetime(2025, 1, 1), max_age=40)
    return Generator([module], cfg).run()


def _rows(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def test_omop_writes_all_core_tables(tmp_path):
    counts = export_omop(_cohort(), tmp_path)
    for table in ("person", "observation_period", "visit_occurrence",
                  "condition_occurrence", "drug_exposure", "measurement"):
        assert (tmp_path / f"{table}.csv").exists()
    assert counts["person.csv"] == 80
    # otitis fires -> there should be conditions and drugs
    assert counts["condition_occurrence.csv"] > 0
    assert counts["drug_exposure.csv"] == counts["condition_occurrence.csv"]


def test_person_has_standard_gender_concepts_and_source(tmp_path):
    export_omop(_cohort(), tmp_path)
    persons = _rows(tmp_path / "person.csv")
    assert [int(p["person_id"]) for p in persons] == list(range(1, 81))  # sequential ints
    for p in persons:
        assert p["gender_concept_id"] in {"8507", "8532"}      # standard concepts
        assert p["gender_source_value"] in {"M", "F"}
        assert p["person_source_value"]                        # UUID preserved


def test_clinical_codes_are_source_loaded(tmp_path):
    export_omop(_cohort(), tmp_path)
    conds = _rows(tmp_path / "condition_occurrence.csv")
    assert conds, "expected some conditions"
    for c in conds:
        assert c["condition_concept_id"] == "0"               # unmapped (no vocab in core)
        assert c["condition_source_value"] == "65363002"      # SNOMED otitis preserved
        assert c["condition_type_concept_id"] == "32817"      # EHR


def test_visit_foreign_keys_resolve(tmp_path):
    export_omop(_cohort(), tmp_path)
    visit_ids = {v["visit_occurrence_id"] for v in _rows(tmp_path / "visit_occurrence.csv")}
    for c in _rows(tmp_path / "condition_occurrence.csv"):
        assert c["visit_occurrence_id"] in visit_ids           # FK points at a real visit
    # visits use standard Visit concepts (ambulatory -> 9202)
    for v in _rows(tmp_path / "visit_occurrence.csv"):
        assert v["visit_concept_id"] == "9202"


def test_drug_uses_atc_source_value(tmp_path):
    export_omop(_cohort(), tmp_path)
    drugs = _rows(tmp_path / "drug_exposure.csv")
    assert drugs
    assert all(d["drug_source_value"] == "J01CA04" for d in drugs)  # ATC amoxicillin
