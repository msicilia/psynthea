"""OMOP CDM v5.4 exporter (ADR-007 — the European-research differentiator).

Emits a **source-loaded** CDM: structurally valid CSV tables with stable standard
concepts where we know them (gender, visit, type), and clinical codes preserved
as ``*_source_value`` with ``*_concept_id = 0`` (OMOP's "no matching concept"
convention). Mapping source codes to standard concepts needs the OHDSI Athena
vocabulary + a mapping pass (Usagi / source_to_concept_map) — a documented
downstream step, kept out of core so core stays dependency- and DB-free.

No payer/cost tables (ADR-011).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from psynthea.engine.person import Person

# --- standard OMOP concept ids we can assign without the vocabulary --------- #
_GENDER = {"M": 8507, "F": 8532}                 # MALE / FEMALE
_VISIT = {                                       # standard Visit concepts
    "inpatient": 9201, "emergency": 9203,
    "ambulatory": 9202, "outpatient": 9202, "wellness": 9202,
}
_EHR = 32817                                     # type concept: "EHR"

_PERSON_COLS = [
    "person_id", "gender_concept_id", "year_of_birth", "month_of_birth", "day_of_birth",
    "birth_datetime", "death_datetime", "race_concept_id", "ethnicity_concept_id",
    "location_id", "provider_id", "care_site_id", "person_source_value",
    "gender_source_value", "gender_source_concept_id", "race_source_value",
    "race_source_concept_id", "ethnicity_source_value", "ethnicity_source_concept_id",
]
_OBS_PERIOD_COLS = [
    "observation_period_id", "person_id", "observation_period_start_date",
    "observation_period_end_date", "period_type_concept_id",
]
_VISIT_COLS = [
    "visit_occurrence_id", "person_id", "visit_concept_id", "visit_start_date",
    "visit_start_datetime", "visit_end_date", "visit_end_datetime", "visit_type_concept_id",
    "provider_id", "care_site_id", "visit_source_value", "visit_source_concept_id",
]
_CONDITION_COLS = [
    "condition_occurrence_id", "person_id", "condition_concept_id", "condition_start_date",
    "condition_start_datetime", "condition_end_date", "condition_end_datetime",
    "condition_type_concept_id", "condition_status_concept_id", "stop_reason", "provider_id",
    "visit_occurrence_id", "visit_detail_id", "condition_source_value",
    "condition_source_concept_id", "condition_status_source_value",
]
_DRUG_COLS = [
    "drug_exposure_id", "person_id", "drug_concept_id", "drug_exposure_start_date",
    "drug_exposure_start_datetime", "drug_exposure_end_date", "drug_exposure_end_datetime",
    "verbatim_end_date", "drug_type_concept_id", "stop_reason", "refills", "quantity",
    "days_supply", "sig", "route_concept_id", "lot_number", "provider_id",
    "visit_occurrence_id", "visit_detail_id", "drug_source_value", "drug_source_concept_id",
    "route_source_value", "dose_unit_source_value",
]
_MEASUREMENT_COLS = [
    "measurement_id", "person_id", "measurement_concept_id", "measurement_date",
    "measurement_datetime", "measurement_time", "measurement_type_concept_id",
    "operator_concept_id", "value_as_number", "value_as_concept_id", "unit_concept_id",
    "range_low", "range_high", "provider_id", "visit_occurrence_id", "visit_detail_id",
    "measurement_source_value", "measurement_source_concept_id", "unit_source_value",
    "value_source_value",
]


def _d(value: datetime | None) -> str:
    return value.date().isoformat() if value is not None else ""


def _latest(p: Person) -> datetime:
    dts: list[datetime] = [p.birthdate]
    for e in p.record.encounters:
        dts += [e.start] + ([e.stop] if e.stop else [])
    for c in p.record.conditions:
        dts += [c.start] + ([c.stop] if c.stop else [])
    for m in p.record.medications:
        dts += [m.start] + ([m.stop] if m.stop else [])
    dts += [o.date for o in p.record.observations]
    return max(dts)


def _code(code) -> str:
    return code.code if code is not None else ""


def _as_number(value) -> str:
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return ""


def export_omop(people: list[Person], out_dir: str | Path) -> dict[str, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, list[dict]] = {
        "person": [], "observation_period": [], "visit_occurrence": [],
        "condition_occurrence": [], "drug_exposure": [], "measurement": [],
    }
    vid = cid = did = mid = opid = 0

    for i, p in enumerate(people):
        person_id = i + 1
        tables["person"].append({
            "person_id": person_id,
            "gender_concept_id": _GENDER.get(p.gender, 0),
            "year_of_birth": p.birthdate.year,
            "month_of_birth": p.birthdate.month,
            "day_of_birth": p.birthdate.day,
            "birth_datetime": p.birthdate.isoformat(),
            "death_datetime": p.deathdate.isoformat() if p.deathdate else "",
            "race_concept_id": 0, "ethnicity_concept_id": 0,
            "person_source_value": p.id,
            "gender_source_value": p.gender,
            "gender_source_concept_id": 0,
        })

        opid += 1
        tables["observation_period"].append({
            "observation_period_id": opid, "person_id": person_id,
            "observation_period_start_date": _d(p.birthdate),
            "observation_period_end_date": _d(p.deathdate or _latest(p)),
            "period_type_concept_id": _EHR,
        })

        visit_of: dict[str, int] = {}
        for e in p.record.encounters:
            vid += 1
            visit_of[e.id] = vid
            tables["visit_occurrence"].append({
                "visit_occurrence_id": vid, "person_id": person_id,
                "visit_concept_id": _VISIT.get(e.encounter_class, 0),
                "visit_start_date": _d(e.start), "visit_end_date": _d(e.stop or e.start),
                "visit_type_concept_id": _EHR,
                "visit_source_value": _code(e.code) or e.encounter_class,
                "visit_source_concept_id": 0,
            })

        for c in p.record.conditions:
            cid += 1
            tables["condition_occurrence"].append({
                "condition_occurrence_id": cid, "person_id": person_id,
                "condition_concept_id": 0,
                "condition_start_date": _d(c.start), "condition_end_date": _d(c.stop),
                "condition_type_concept_id": _EHR,
                "visit_occurrence_id": visit_of.get(c.encounter.id, "") if c.encounter else "",
                "condition_source_value": _code(c.code), "condition_source_concept_id": 0,
            })

        for m in p.record.medications:
            did += 1
            tables["drug_exposure"].append({
                "drug_exposure_id": did, "person_id": person_id, "drug_concept_id": 0,
                "drug_exposure_start_date": _d(m.start),
                "drug_exposure_end_date": _d(m.stop or m.start),
                "drug_type_concept_id": _EHR,
                "visit_occurrence_id": visit_of.get(m.encounter.id, "") if m.encounter else "",
                "drug_source_value": _code(m.code), "drug_source_concept_id": 0,
            })

        for o in p.record.observations:
            mid += 1
            tables["measurement"].append({
                "measurement_id": mid, "person_id": person_id, "measurement_concept_id": 0,
                "measurement_date": _d(o.date), "measurement_type_concept_id": _EHR,
                "value_as_number": _as_number(o.value),
                "visit_occurrence_id": visit_of.get(o.encounter.id, "") if o.encounter else "",
                "measurement_source_value": _code(o.code), "measurement_source_concept_id": 0,
                "unit_source_value": o.unit, "value_source_value": "" if o.value is None else str(o.value),
            })

    columns = {
        "person": _PERSON_COLS, "observation_period": _OBS_PERIOD_COLS,
        "visit_occurrence": _VISIT_COLS, "condition_occurrence": _CONDITION_COLS,
        "drug_exposure": _DRUG_COLS, "measurement": _MEASUREMENT_COLS,
    }
    counts: dict[str, int] = {}
    for table, rows in tables.items():
        path = out / f"{table}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns[table], restval="", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        counts[f"{table}.csv"] = len(rows)
    return counts
