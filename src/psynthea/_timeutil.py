"""Duration/age helpers shared by the IR, engine, and importer.

Synthea uses calendar-ish units. We approximate months/years as fixed spans
(month = 30.44 days, year = 365.25 days) — good enough at the default 7-day
simulation step and documented as a Phase-1 simplification in DESIGN.md.
"""
from __future__ import annotations

import operator
from datetime import datetime, timedelta

# unit -> seconds
_UNIT_SECONDS: dict[str, float] = {
    "seconds": 1.0,
    "minutes": 60.0,
    "hours": 3600.0,
    "days": 86_400.0,
    "weeks": 604_800.0,
    "months": 2_629_746.0,  # 30.44 days
    "years": 31_556_952.0,  # 365.25 days
}


def to_timedelta(quantity: float, unit: str) -> timedelta:
    """Convert a (quantity, unit) pair to a timedelta."""
    try:
        return timedelta(seconds=quantity * _UNIT_SECONDS[unit])
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unknown time unit: {unit!r}") from exc


def age_in(birthdate: datetime, now: datetime, unit: str) -> float:
    """Age of a person born at ``birthdate``, expressed in ``unit``."""
    seconds = (now - birthdate).total_seconds()
    return seconds / _UNIT_SECONDS[unit]


_COMPARATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


def compare(left, op: str, right) -> bool:
    """Apply a GMF comparison operator, tolerant of ``None`` operands."""
    if op == "is nil":
        return left is None
    if op == "is not nil":
        return left is not None
    try:
        func = _COMPARATORS[op]
    except KeyError as exc:
        raise ValueError(f"Unknown operator: {op!r}") from exc
    if left is None or right is None:
        # numeric/string comparison against a missing value is never true,
        # except equality/inequality which are well-defined.
        if op == "==":
            return left is right
        if op == "!=":
            return left is not right
        return False
    return func(left, right)
