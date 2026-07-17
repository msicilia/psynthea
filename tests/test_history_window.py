"""The export history window (Synthea's years_of_history)."""
from __future__ import annotations

from datetime import datetime

from psynthea.engine.record import (
    ConditionEntry,
    ObservationEntry,
)
from psynthea.export import apply_history_window
from psynthea.terminology import Code


class _Rec:
    def __init__(self):
        self.encounters, self.conditions, self.medications = [], [], []
        self.observations, self.procedures, self.immunizations, self.allergies = [], [], [], []


class _Person:
    def __init__(self, record):
        self.record = record


C = Code("SNOMED-CT", "X", "x")
REF = datetime(2026, 1, 1)


def _person():
    r = _Rec()
    # resolved old condition (2000-2000) -> pruned; resolved recent (2020) -> kept;
    # chronic old (no stop) -> kept
    r.conditions = [
        ConditionEntry(code=C, start=datetime(2000, 1, 1), stop=datetime(2000, 1, 8)),
        ConditionEntry(code=C, start=datetime(2020, 1, 1), stop=datetime(2020, 1, 8)),
        ConditionEntry(code=C, start=datetime(1990, 1, 1), stop=None),   # chronic
    ]
    r.observations = [
        ObservationEntry(code=C, value=1, unit="", date=datetime(2005, 1, 1), category=""),
        ObservationEntry(code=C, value=2, unit="", date=datetime(2024, 1, 1), category=""),
    ]
    return _Person(r)


def test_window_prunes_old_resolved_keeps_recent_and_chronic():
    p = _person()
    apply_history_window([p], REF, years_of_history=10)   # cutoff = 2016
    starts = sorted(c.start.year for c in p.record.conditions)
    assert starts == [1990, 2020]           # 2000 pruned; 1990 chronic kept; 2020 kept
    assert [o.date.year for o in p.record.observations] == [2024]   # 2005 pruned


def test_window_counts_returned():
    p = _person()
    kept = apply_history_window([p], REF, years_of_history=10)
    assert kept["conditions"] == 2 and kept["observations"] == 1


def test_large_window_keeps_everything():
    p = _person()
    apply_history_window([p], REF, years_of_history=100)   # cutoff = 1926
    assert len(p.record.conditions) == 3 and len(p.record.observations) == 2
