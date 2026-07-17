"""Physiological vital-sign generation (approximating Synthea's growth/BP models).

Synthea synthesizes height/weight/BMI/blood-pressure trajectories over a patient's life
via Java modules (CDC growth charts + a blood-pressure model). psynthea provides a
lightweight, deterministic approximation so that (a) disease modules gating on vital
signs (BMI, blood pressure) have values to read, and (b) vital observations populate the
record / OMOP ``measurement`` table.

Each patient gets a fixed height and BMI *z-score* at birth (their percentile for life);
vitals are recomputed for the current age each step. The curves are simplified---this is
plausible, age/sex-consistent physiology, not a reproduction of Synthea's exact charts.
Vital-sign attributes use Synthea's names so ``Vital Sign`` logic conditions match.
"""
from __future__ import annotations

from datetime import datetime

from psynthea.terminology import Code

_DAYS_PER_YEAR = 365.25

# vital-sign attribute name -> (LOINC code, display, unit)
_VITAL_CODES = {
    "Height": Code("LOINC", "8302-2", "Body Height"),
    "Weight": Code("LOINC", "29463-7", "Body Weight"),
    "Body Mass Index": Code("LOINC", "39156-5", "Body mass index (BMI) [Ratio]"),
    "Systolic Blood Pressure": Code("LOINC", "8480-6", "Systolic Blood Pressure"),
    "Diastolic Blood Pressure": Code("LOINC", "8462-4", "Diastolic Blood Pressure"),
}
_VITAL_UNITS = {"Height": "cm", "Weight": "kg", "Body Mass Index": "kg/m2",
                "Systolic Blood Pressure": "mm[Hg]", "Diastolic Blood Pressure": "mm[Hg]"}


def assign_baseline(person, rng) -> None:
    """Fix the patient's lifelong height/BMI percentiles (as z-scores)."""
    person.attributes["_height_z"] = rng.gauss(0.0, 1.0)
    person.attributes["_bmi_z"] = rng.gauss(0.0, 1.0)


def _height_cm(age: float, sex: str, z: float) -> float:
    adult = (176.0 if sex == "M" else 162.0) + z * (7.0 if sex == "M" else 6.5)
    if age >= 18:
        return adult
    birth = 50.0
    return birth + (adult - birth) * (age / 18.0) ** 0.7


def _bmi(age: float, z: float) -> float:
    if age < 2:
        mean, sd = 17.0, 2.0
    elif age < 18:
        mean, sd = 16.0 + (age - 2) / 16.0 * 6.0, 2.5   # 16 -> 22 across childhood
    else:
        mean, sd = 27.0, 5.0
    return max(12.0, mean + z * sd)


def _blood_pressure(age: float, bmi: float) -> tuple[float, float]:
    a = min(age, 80.0)
    systolic = 95.0 + 0.45 * a + 0.6 * (bmi - 25.0)
    diastolic = 62.0 + 0.18 * a + 0.35 * (bmi - 25.0)
    return systolic, diastolic


def compute(person, time: datetime) -> dict[str, float]:
    """Current vital signs for the patient at ``time``."""
    age = (time - person.birthdate).days / _DAYS_PER_YEAR
    height = _height_cm(age, person.gender, person.attributes.get("_height_z", 0.0))
    bmi = _bmi(age, person.attributes.get("_bmi_z", 0.0))
    weight = bmi * (height / 100.0) ** 2
    systolic, diastolic = _blood_pressure(age, bmi)
    return {
        "Height": round(height, 1),
        "Weight": round(weight, 1),
        "Body Mass Index": round(bmi, 1),
        "Systolic Blood Pressure": float(round(systolic)),
        "Diastolic Blood Pressure": float(round(diastolic)),
    }


def update(person, time: datetime) -> None:
    """Set the patient's current vital-sign attributes (read by modules)."""
    person.attributes.update(compute(person, time))


def emit_observations(person, time: datetime, source_module: str = "vitals") -> None:
    """Record the current vitals as observations (e.g. at a wellness visit)."""
    vitals = compute(person, time)
    for name, code in _VITAL_CODES.items():
        person.record.add_observation(code, vitals[name], _VITAL_UNITS[name], time,
                                      "vital-signs", source_module=source_module,
                                      source_state=name)
