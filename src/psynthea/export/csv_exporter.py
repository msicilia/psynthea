"""CSV exporter (ADR-007: simplest output first).

Column names track Synthea's CSV exporter closely so existing tooling and the
fidelity-comparison harness (ADR-008/012) can read both. No payer/claims/cost
tables (ADR-011).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from psynthea.engine.person import Person


def _iso(value: datetime | None) -> str:
    return value.date().isoformat() if value is not None else ""


def _code(code) -> tuple[str, str]:
    return (code.code, code.display) if code is not None else ("", "")


def _enc_id(encounter) -> str:
    return encounter.id if encounter is not None else ""


def export_csv(people: list[Person], out_dir: str | Path) -> dict[str, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    def _write(filename: str, header: list[str], rows: list[list]) -> None:
        with (out / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
        counts[filename] = len(rows)

    patients, encounters, conditions, medications, observations = [], [], [], [], []
    devices, imaging, supplies = [], [], []

    for p in people:
        patients.append([p.id, _iso(p.birthdate), _iso(p.deathdate), p.gender])
        for e in p.record.encounters:
            code, desc = _code(e.code)
            encounters.append([e.id, p.id, _iso(e.start), _iso(e.stop), e.encounter_class, code, desc])
        for c in p.record.conditions:
            code, desc = _code(c.code)
            conditions.append([_iso(c.start), _iso(c.stop), p.id, _enc_id(c.encounter), code, desc])
        for m in p.record.medications:
            code, desc = _code(m.code)
            medications.append([_iso(m.start), _iso(m.stop), p.id, _enc_id(m.encounter), code, desc])
        for o in p.record.observations:
            code, desc = _code(o.code)
            observations.append(
                [_iso(o.date), p.id, _enc_id(o.encounter), code, desc, o.value, o.unit, o.category]
            )
        for dv in p.record.devices:
            code, desc = _code(dv.code)
            devices.append([_iso(dv.start), _iso(dv.stop), p.id, _enc_id(dv.encounter), code, desc])
        for im in p.record.imaging_studies:
            pcode, pdesc = _code(im.procedure_code)
            bcode, bdesc = _code(im.body_site)
            imaging.append([_iso(im.date), p.id, _enc_id(im.encounter), pcode, pdesc,
                            im.modality, bcode, bdesc])
        for su in p.record.supplies:
            code, desc = _code(su.code)
            supplies.append([_iso(su.date), p.id, _enc_id(su.encounter), code, desc, su.quantity])

    _write("patients.csv", ["Id", "BIRTHDATE", "DEATHDATE", "GENDER"], patients)
    _write("encounters.csv",
           ["Id", "PATIENT", "START", "STOP", "ENCOUNTERCLASS", "CODE", "DESCRIPTION"], encounters)
    _write("conditions.csv",
           ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"], conditions)
    _write("medications.csv",
           ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"], medications)
    _write("observations.csv",
           ["DATE", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION", "VALUE", "UNITS", "CATEGORY"],
           observations)
    _write("devices.csv",
           ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"], devices)
    _write("imaging_studies.csv",
           ["DATE", "PATIENT", "ENCOUNTER", "PROCEDURE_CODE", "PROCEDURE_DESCRIPTION",
            "MODALITY", "BODYSITE_CODE", "BODYSITE_DESCRIPTION"], imaging)
    _write("supplies.csv",
           ["DATE", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION", "QUANTITY"], supplies)
    return counts
