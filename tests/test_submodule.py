"""CallSubmodule: nested submodule execution + submodule-aware loading."""
from __future__ import annotations

import json
from datetime import datetime

from psynthea.compat import load_module_with_submodules
from psynthea.engine import Generator, GeneratorConfig

CODE = "12345"


def _write(d, name, states):
    p = d / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"name": name, "states": states}), encoding="utf-8")
    return p


def _run(module, n=10):
    people = Generator([module], GeneratorConfig(
        population=n, seed=1, end_date=datetime(2025, 1, 1))).run()
    return people


def test_submodule_events_are_produced(tmp_path):
    _write(tmp_path, "sub/emit", {
        "Initial": {"type": "Initial", "direct_transition": "Onset"},
        "Onset": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": CODE, "display": "X"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    parent = _write(tmp_path, "parent", {
        "Initial": {"type": "Initial", "direct_transition": "Call"},
        "Call": {"type": "CallSubmodule", "submodule": "sub/emit",
                 "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})

    module = load_module_with_submodules(parent, tmp_path)
    # the CallSubmodule resolved to the real submodule
    call = module.states["Call"]
    assert call.submodule is not None and call.submodule.name == "sub/emit"
    # every patient gets the submodule's condition
    people = _run(module)
    assert all(any(c.code and c.code.code == CODE for c in p.record.conditions) for p in people)


def test_submodule_with_delay_blocks_then_resumes(tmp_path):
    # submodule delays 2 years, then emits; parent must wait and then reach its own onset
    _write(tmp_path, "slow", {
        "Initial": {"type": "Initial", "direct_transition": "Wait"},
        "Wait": {"type": "Delay", "exact": {"quantity": 2, "unit": "years"},
                 "direct_transition": "Onset"},
        "Onset": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": CODE, "display": "X"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    parent = _write(tmp_path, "p2", {
        "Initial": {"type": "Initial", "direct_transition": "Call"},
        "Call": {"type": "CallSubmodule", "submodule": "slow", "direct_transition": "After"},
        "After": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": "999", "display": "Y"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    module = load_module_with_submodules(parent, tmp_path)
    people = _run(module, n=20)
    # both the submodule's condition and the parent's post-submodule condition appear
    assert any(any(c.code and c.code.code == CODE for c in p.record.conditions) for p in people)
    assert any(any(c.code and c.code.code == "999" for c in p.record.conditions) for p in people)


def test_submodule_deadend_does_not_hang_parent(tmp_path):
    # submodule emits then hits a state with no viable transition (mimics an
    # unsupported construct); the parent must still proceed past the call.
    _write(tmp_path, "deadend", {
        "Initial": {"type": "Initial", "direct_transition": "Onset"},
        "Onset": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": CODE, "display": "X"}]},
        # Onset has NO transition -> dead-end, never reaches Terminal
    })
    parent = _write(tmp_path, "p4", {
        "Initial": {"type": "Initial", "direct_transition": "Call"},
        "Call": {"type": "CallSubmodule", "submodule": "deadend", "direct_transition": "After"},
        "After": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": "999", "display": "Y"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    module = load_module_with_submodules(parent, tmp_path)
    people = _run(module, n=10)
    # submodule's event was produced AND the parent moved on to its own condition
    assert all(any(c.code and c.code.code == CODE for c in p.record.conditions) for p in people)
    assert all(any(c.code and c.code.code == "999" for c in p.record.conditions) for p in people)


def test_missing_submodule_is_noop_not_crash(tmp_path):
    parent = _write(tmp_path, "p3", {
        "Initial": {"type": "Initial", "direct_transition": "Call"},
        "Call": {"type": "CallSubmodule", "submodule": "does/not/exist",
                 "direct_transition": "After"},
        "After": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": "999", "display": "Y"}],
                  "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    module = load_module_with_submodules(parent, tmp_path)
    assert module.states["Call"].submodule is None
    people = _run(module)                      # unresolved submodule -> no-op, still runs
    assert all(any(c.code and c.code.code == "999" for c in p.record.conditions) for p in people)
