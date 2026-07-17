"""Background mortality (approximating an actuarial life table).

An opt-in per-step death hazard by age and sex; when a draw succeeds the patient dies
(``deathdate`` set, simulation stops), producing dead patients alongside the living. The
hazard is a simple Gompertz fit (~0.1%/yr at 50, ~10%/yr at 90), not a real life table.

Caveat: psynthea samples each patient's age-at-end assuming they are alive then, so
enabling mortality can kill some earlier — the realized *living*-age distribution then
skews younger than requested. Use demographic profiles (without mortality) when a
specific living-age structure is required.
"""
from __future__ import annotations

import math

_A, _B = 3.2e-6, 0.115                 # Gompertz q_year ~ A*exp(B*age)
_SEX_MULT = {"M": 1.3, "F": 0.8}


def annual_death_probability(age: float, sex: str) -> float:
    q = _A * math.exp(_B * max(0.0, age))
    return min(0.6, q * _SEX_MULT.get(sex, 1.0))


def died_this_step(person, age: float, step_days: float, rng) -> bool:
    q_year = annual_death_probability(age, person.gender)
    q_step = 1.0 - (1.0 - q_year) ** (step_days / 365.25)
    return rng.random() < q_step
