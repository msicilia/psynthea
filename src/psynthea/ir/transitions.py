"""GMF transitions.

Each Transition implements ``follow(person, time, ctx) -> str | None`` returning
the name of the next state (or ``None`` when there is nowhere to go).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from psynthea import _timeutil
from psynthea.ir.logic import Logic


class Transition:
    def follow(self, person, time, ctx) -> str | None:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class DirectTransition(Transition):
    to: str

    def follow(self, person, time, ctx) -> str | None:
        return self.to


def _sample_weighted(choices: list[tuple[str, float]], rng) -> str | None:
    """Pick a target name from (name, weight) pairs using the person's RNG."""
    total = sum(w for _, w in choices)
    if total <= 0:
        return choices[0][0] if choices else None
    r = rng.random() * total
    upto = 0.0
    for name, weight in choices:
        upto += weight
        if r < upto:
            return name
    return choices[-1][0]


@dataclass
class DistributedTransition(Transition):
    # list of (target_state, weight)
    choices: list[tuple[str, float]]

    def follow(self, person, time, ctx) -> str | None:
        return _sample_weighted(self.choices, person.rng)


@dataclass
class ConditionalTransition(Transition):
    # list of (condition_or_None, target_state); first matching wins; None == else
    branches: list[tuple[Logic | None, str]]

    def follow(self, person, time, ctx) -> str | None:
        for condition, target in self.branches:
            if condition is None or condition.test(person, time, ctx):
                return target
        return None


@dataclass
class ComplexTransition(Transition):
    # list of (condition_or_None, payload); payload is either a target name (str)
    # or a DistributedTransition to sample from. First matching condition wins.
    branches: list[tuple[Logic | None, "str | DistributedTransition"]]

    def follow(self, person, time, ctx) -> str | None:
        for condition, payload in self.branches:
            if condition is None or condition.test(person, time, ctx):
                if isinstance(payload, DistributedTransition):
                    return payload.follow(person, time, ctx)
                return payload
        return None


def _cell_matches(cell: str, value) -> bool:
    """Match a lookup-table input cell against a patient value: ``*`` is a wildcard,
    ``lo-hi`` a numeric range (inclusive), otherwise an exact (string) match."""
    cell = cell.strip()
    if cell in ("", "*"):
        return True
    if "-" in cell[1:]:  # a range like 6-103 (allow a leading '-' for negatives, rare)
        lo, _, hi = cell.partition("-")
        try:
            return float(lo) <= float(value) <= float(hi)
        except (TypeError, ValueError):
            return False
    try:  # exact numeric
        return float(cell) == float(value)
    except (TypeError, ValueError):
        return str(value) == cell


@dataclass
class LookupTableTransition(Transition):
    """CSV-table-driven transition (Synthea ``lookup_table_transition``): the patient's
    attributes select a table row, whose per-target probabilities drive the draw.

    Input columns are matched against the patient (``age`` -> years, ``gender`` -> sex,
    any other -> a patient attribute); output columns are named for the transition
    targets. ``rows``/``input_columns`` are filled at load time from the CSV; until then
    (or if no row matches) the per-target ``default_probability`` weights are used.
    """
    choices: list[tuple[str, float]] = field(default_factory=list)   # (target, default_prob)
    table_name: str = ""
    input_columns: list[str] = field(default_factory=list)
    rows: list[tuple[dict, dict]] = field(default_factory=list)      # (inputs, {target: prob})

    def _match(self, person, time) -> dict | None:
        if not self.rows:
            return None
        for inputs, probs in self.rows:
            if all(self._value_matches(col, cell, person, time)
                   for col, cell in inputs.items()):
                return probs
        return None

    @staticmethod
    def _value_matches(col: str, cell: str, person, time) -> bool:
        key = col.strip().lower()
        if key == "age":
            value = _timeutil.age_in(person.birthdate, time, "years")
        elif key == "gender":
            value = person.gender
        else:
            value = person.attributes.get(col)
        return _cell_matches(cell, value)

    def follow(self, person, time, ctx) -> str | None:
        probs = self._match(person, time)
        if probs is None:
            weighted = list(self.choices)                      # fall back to defaults
        else:
            weighted = [(t, probs.get(t, 0.0)) for t, _ in self.choices]
        return _sample_weighted(weighted, person.rng)
