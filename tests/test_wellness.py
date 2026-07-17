"""Scheduled wellness encounters: a module that waits for the next visit no longer
spins, and attaches to generated wellness encounters."""
from __future__ import annotations

from datetime import datetime

from psynthea.compat import load_module_dict
from psynthea.engine import Generator, GeneratorConfig

# waits for a wellness visit, records a finding, then loops to wait for the next one
_MODULE = {
    "name": "annual_check",
    "states": {
        "Initial": {"type": "Initial", "direct_transition": "Visit"},
        "Visit": {"type": "Encounter", "wellness": True, "encounter_class": "wellness",
                  "direct_transition": "Finding"},
        "Finding": {"type": "ConditionOnset",
                    "codes": [{"system": "SNOMED-CT", "code": "55", "display": "x"}],
                    "direct_transition": "Visit"},   # loop back -> next annual visit
    },
}


def _run(wellness):
    return Generator([load_module_dict(_MODULE)], GeneratorConfig(
        population=20, seed=1, end_date=datetime(2025, 1, 1), min_age=30, max_age=60,
        wellness_encounters=wellness)).run()


def test_without_scheduling_the_wait_loops_and_is_disabled():
    people = _run(False)      # wellness Encounter creates on the spot -> instant loop
    assert all("annual_check" in p.attributes.get("_disabled_modules", set()) for p in people)


def test_with_scheduling_it_runs_and_attaches_to_wellness_visits():
    people = _run(True)
    for p in people:
        assert "annual_check" not in p.attributes.get("_disabled_modules", set())
        wellness = [e for e in p.record.encounters if e.encounter_class == "wellness"]
        assert len(wellness) >= 5          # several annual visits over ~30-60 years
        # the module recorded a finding at wellness visits (repeatedly)
        assert sum(1 for c in p.record.conditions if c.code and c.code.code == "55") >= 5


def test_wellness_off_by_default():
    people = Generator([load_module_dict({
        "name": "m", "states": {
            "Initial": {"type": "Initial", "direct_transition": "Terminal"},
            "Terminal": {"type": "Terminal"}}})], GeneratorConfig(
        population=5, seed=1, end_date=datetime(2025, 1, 1))).run()
    assert all(not p.record.encounters for p in people)   # no wellness encounters added
