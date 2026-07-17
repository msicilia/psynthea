"""Cross-module ensembles: load_all_modules, loop-resilience, and the keystone hook."""
from __future__ import annotations

import json
from datetime import datetime

from psynthea.compat import load_all_modules, load_module_dict
from psynthea.engine import Generator, GeneratorConfig


def _write(d, name, states):
    (d / f"{name}.json").write_text(json.dumps({"name": name, "states": states}), encoding="utf-8")


def _run(modules, n=10, **kw):
    return Generator(modules, GeneratorConfig(
        population=n, seed=1, end_date=datetime(2025, 1, 1), **kw)).run()


def test_load_all_modules_loads_top_level(tmp_path):
    _write(tmp_path, "a", {"Initial": {"type": "Initial", "direct_transition": "Terminal"},
                           "Terminal": {"type": "Terminal"}})
    _write(tmp_path, "b", {"Initial": {"type": "Initial", "direct_transition": "Terminal"},
                           "Terminal": {"type": "Terminal"}})
    mods = load_all_modules(tmp_path)
    assert {m.name for m in mods} == {"a", "b"}


def test_cross_module_attribute_visible_across_modules():
    # setter module writes an attribute; reader module gates on it -> reader fires
    setter = load_module_dict({"name": "setter", "states": {
        "Initial": {"type": "Initial", "direct_transition": "Set"},
        "Set": {"type": "SetAttribute", "attribute": "flag", "value": True,
                "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}})
    reader = load_module_dict({"name": "reader", "states": {
        "Initial": {"type": "Initial", "direct_transition": "G"},
        "G": {"type": "Guard", "allow": {"condition_type": "Attribute", "attribute": "flag",
                                         "operator": "==", "value": True},
              "direct_transition": "Onset"},
        "Onset": {"type": "ConditionOnset",
                  "codes": [{"system": "S", "code": "77", "display": "x"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}})
    # setter listed first so the attribute is set before the reader is processed
    people = _run([setter, reader])
    assert all(any(c.code and c.code.code == "77" for c in p.record.conditions) for p in people)


def test_looping_module_is_disabled_not_crashing():
    looper = load_module_dict({"name": "loop", "states": {   # A -> A, no Delay/Guard
        "Initial": {"type": "Initial", "direct_transition": "A"},
        "A": {"type": "Simple", "direct_transition": "A"}}})
    ok = load_module_dict({"name": "ok", "states": {
        "Initial": {"type": "Initial", "direct_transition": "Onset"},
        "Onset": {"type": "ConditionOnset",
                  "codes": [{"system": "S", "code": "88", "display": "y"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}})
    people = _run([looper, ok])                      # must not raise
    assert all("loop" in p.attributes.get("_disabled_modules", set()) for p in people)
    assert all(any(c.code and c.code.code == "88" for c in p.record.conditions) for p in people)


def test_keystone_seeds_attributes():
    reader = load_module_dict({"name": "smk", "states": {
        "Initial": {"type": "Initial", "direct_transition": "G"},
        "G": {"type": "Guard", "allow": {"condition_type": "Attribute", "attribute": "smoker",
                                         "operator": "==", "value": True},
              "direct_transition": "Onset"},
        "Onset": {"type": "ConditionOnset",
                  "codes": [{"system": "S", "code": "99", "display": "z"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}})

    def keystone(person, rng):
        person.attributes["smoker"] = True

    without = _run([reader])
    seeded = _run([reader], keystone=keystone)
    assert not any(any(c.code and c.code.code == "99" for c in p.record.conditions) for p in without)
    assert all(any(c.code and c.code.code == "99" for c in p.record.conditions) for p in seeded)
