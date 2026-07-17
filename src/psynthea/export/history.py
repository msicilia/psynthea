"""Export history window (Synthea's ``exporter.years_of_history``).

Synthea exports only the most recent *N* years of each patient's record by default
(``years_of_history = 10``): resolved conditions, past medications, old encounters and
observations that fall outside the window are pruned from the output. psynthea keeps
the entire simulated life, so for a lifetime-risk module its realized prevalence
accumulates with age while Synthea's stays flat. Applying the same window is what makes
psynthea reproduce Java-Synthea's realized distributions (ADR-008 reproduction mode).

Following Synthea, an *active* condition/medication/allergy (no stop date) is retained
regardless of when it started (chronic disease is still current); point events and
resolved episodes older than the cutoff are dropped. The reference date is the
simulation end date.
"""
from __future__ import annotations

from datetime import datetime, timedelta

_DAYS_PER_YEAR = 365.25


def apply_history_window(people: list, reference_date: datetime, years_of_history: float) -> dict:
    """Prune each person's record to the last ``years_of_history`` years (in place).

    Returns per-domain counts of how many entries were kept (for reporting)."""
    cutoff = reference_date - timedelta(days=_DAYS_PER_YEAR * years_of_history)

    def _recent(dt) -> bool:
        return dt is not None and dt >= cutoff

    def _active_or_recent(entry) -> bool:
        # chronic (unresolved) entries stay; resolved ones must be within the window
        return getattr(entry, "stop", None) is None or _recent(entry.start)

    kept = {"encounters": 0, "conditions": 0, "medications": 0,
            "observations": 0, "procedures": 0, "immunizations": 0, "allergies": 0}
    for p in people:
        r = p.record
        r.encounters = [e for e in r.encounters if _recent(e.start)]
        r.conditions = [c for c in r.conditions if _active_or_recent(c)]
        r.medications = [m for m in r.medications if _active_or_recent(m)]
        r.allergies = [a for a in r.allergies if _active_or_recent(a)]
        r.observations = [o for o in r.observations if _recent(o.date)]
        r.procedures = [pr for pr in r.procedures if _recent(pr.start)]
        r.immunizations = [im for im in r.immunizations if _recent(im.date)]
        for k in kept:
            kept[k] += len(getattr(r, k))
    return kept
