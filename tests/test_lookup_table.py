"""lookup_table_transition: CSV-driven, attribute-matched transitions."""
from __future__ import annotations

import json
from datetime import datetime

from psynthea.compat import load_module_with_submodules
from psynthea.engine import Generator, GeneratorConfig

YOUNG, OLD = "1000", "2000"


def _module(tmp_path, table_name="agebranch.csv", with_csv=True):
    if with_csv:
        tbl = tmp_path / "lookup_tables" / table_name
        tbl.parent.mkdir(parents=True, exist_ok=True)
        tbl.write_text("age,Young,Old\n0-40,1.0,0.0\n40-120,0.0,1.0\n", encoding="utf-8")
    mod = tmp_path / "m.json"
    mod.write_text(json.dumps({"name": "m", "states": {
        "Initial": {"type": "Initial", "direct_transition": "Split"},
        "Split": {"type": "Simple", "lookup_table_transition": [
            {"transition": "Young", "default_probability": 0.5, "lookup_table_name": table_name},
            {"transition": "Old", "default_probability": 0.5, "lookup_table_name": table_name}]},
        "Young": {"type": "ConditionOnset",
                  "codes": [{"system": "SNOMED-CT", "code": YOUNG, "display": "y"}],
                  "direct_transition": "Terminal"},
        "Old": {"type": "ConditionOnset",
                "codes": [{"system": "SNOMED-CT", "code": OLD, "display": "o"}],
                "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}}), encoding="utf-8")
    return load_module_with_submodules(mod, tmp_path)


def _cohort(module, lo, hi, n=60):
    return Generator([module], GeneratorConfig(
        population=n, seed=1, end_date=datetime(2025, 1, 1), min_age=lo, max_age=hi)).run()


def _has(person, code):
    return any(c.code and c.code.code == code for c in person.record.conditions)


def test_lookup_table_routes_by_age():
    # route is decided by the patient's age *at the moment the state is reached*, so
    # test the transition directly at controlled ages (a module would reach Split at
    # whatever age the flow arrives there).
    import random
    import tempfile
    from pathlib import Path

    from psynthea.compat.synthea_json import _fill_lookup_table
    from psynthea.engine.person import Person
    from psynthea.ir.transitions import LookupTableTransition

    with tempfile.TemporaryDirectory() as d:
        csv_path = Path(d) / "agebranch.csv"
        csv_path.write_text("age,Young,Old\n0-40,1.0,0.0\n40-120,0.0,1.0\n", encoding="utf-8")
        tr = LookupTableTransition(choices=[("Young", 0.5), ("Old", 0.5)], table_name="x")
        _fill_lookup_table(tr, csv_path)
        assert tr.input_columns == ["age"] and len(tr.rows) == 2

        time = datetime(2025, 1, 1)
        young = Person("y", "M", datetime(2005, 1, 1), random.Random(1))   # age 20
        old = Person("o", "F", datetime(1960, 1, 1), random.Random(1))     # age 65
        assert tr.follow(young, time, None) == "Young"
        assert tr.follow(old, time, None) == "Old"


def test_missing_table_falls_back_to_default_probabilities():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        module = _module(Path(d), with_csv=False)      # no CSV -> rows empty
        split = module.states["Split"].transition
        assert split.rows == []
        people = _cohort(module, 10, 80, n=200)
        # defaults are 0.5/0.5 -> both branches occur across the cohort
        assert any(_has(p, YOUNG) for p in people) and any(_has(p, OLD) for p in people)
