"""Track B: vitals generation, background mortality, behavioral keystone."""
from __future__ import annotations

from datetime import datetime

from psynthea.compat import load_module_dict
from psynthea.engine import Generator, GeneratorConfig
from psynthea.keystone import default_keystone
from psynthea.mortality import annual_death_probability

_NULL = {"name": "m", "states": {
    "Initial": {"type": "Initial", "direct_transition": "Terminal"},
    "Terminal": {"type": "Terminal"}}}


def _run(cfg_kw, module=None, n=400):
    return Generator([load_module_dict(module or _NULL)], GeneratorConfig(
        population=n, seed=1, end_date=datetime(2025, 1, 1), **cfg_kw)).run()


# --- vitals ---------------------------------------------------------------- #
def test_vitals_are_age_appropriate():
    child = _run({"vitals": True, "min_age": 5, "max_age": 7})[0]
    adult = _run({"vitals": True, "min_age": 40, "max_age": 45})[0]
    assert child.attributes["Height"] < adult.attributes["Height"]     # kids shorter
    assert 12 < child.attributes["Body Mass Index"] < 22
    assert 90 < adult.attributes["Systolic Blood Pressure"] < 160


def test_vitals_feed_modules_and_emit_at_wellness():
    obese_mod = {"name": "ob", "states": {
        "Initial": {"type": "Initial", "direct_transition": "G"},
        "G": {"type": "Guard", "allow": {"condition_type": "Vital Sign",
              "vital_sign": "Body Mass Index", "operator": ">=", "value": 30},
              "direct_transition": "O"},
        "O": {"type": "ConditionOnset", "codes": [{"system": "S", "code": "obese"}],
              "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}}
    people = _run({"vitals": True, "wellness_encounters": True, "min_age": 40, "max_age": 70},
                  module=obese_mod, n=500)
    assert any(any(c.code.code == "obese" for c in p.record.conditions) for p in people)
    assert any(any(o.category == "vital-signs" for o in p.record.observations) for p in people)


def test_vitals_off_by_default():
    p = _run({}, n=5)[0]
    assert "Body Mass Index" not in p.attributes


# --- mortality ------------------------------------------------------------- #
def test_mortality_hazard_increases_with_age():
    assert annual_death_probability(30, "M") < annual_death_probability(60, "M") \
        < annual_death_probability(90, "M")
    assert annual_death_probability(60, "M") > annual_death_probability(60, "F")


def test_mortality_produces_some_dead_patients():
    people = _run({"mortality": True, "min_age": 0, "max_age": 95}, n=1000)
    dead = [p for p in people if not p.alive]
    assert 20 < len(dead) < 400            # some, not all
    assert all(p.deathdate is not None for p in dead)


def test_no_mortality_by_default():
    assert all(p.alive for p in _run({"min_age": 0, "max_age": 95}, n=200))


# --- keystone: demographics + behaviors ------------------------------------ #
def test_default_keystone_sets_behaviors_near_rates():
    people = _run({"keystone": default_keystone}, n=1000)
    smokers = sum(1 for p in people if p.attributes.get("smoker"))
    assert 100 < smokers < 190             # ~14%
    assert any(p.attributes.get("alcoholic") for p in people)


def test_default_keystone_assigns_race_and_ses():
    people = _run({"keystone": default_keystone}, n=2000)
    races = {p.attributes["race"] for p in people}
    assert "White" in races and "Black" in races                 # from the distribution
    assert sum(p.attributes["race"] == "White" for p in people) > 900   # majority White
    assert all(p.attributes["socioeconomic_status"] in {"Low", "Middle", "High"}
               for p in people)
    # ethnicity tied to Hispanic race
    assert all((p.attributes["ethnicity"] == "hispanic") == (p.attributes["race"] == "Hispanic")
               for p in people)


def test_race_gated_module_fires_for_matching_patients():
    mod = {"name": "r", "states": {
        "Initial": {"type": "Initial", "direct_transition": "G"},
        "G": {"type": "Guard", "allow": {"condition_type": "Race", "race": "Black"},
              "direct_transition": "O"},
        "O": {"type": "ConditionOnset", "codes": [{"system": "S", "code": "cond"}],
              "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}}
    people = _run({"keystone": default_keystone}, module=mod, n=1500)
    fired = sum(any(c.code.code == "cond" for c in p.record.conditions) for p in people)
    black = sum(p.attributes["race"] == "Black" for p in people)
    assert fired == black > 0             # exactly the Black patients
