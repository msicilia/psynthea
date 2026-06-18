"""Bidirectional compatibility: IR -> GMF JSON export round-trips through the importer.

The strong guarantee we test: for any module in the supported subset,
``load(dump(m)) == m`` at the IR level — so a DSL-authored module can be written out
as stock GMF JSON, and any imported module re-exported, without information loss.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from psynthea.compat import dump_module, load_module_dict, load_module_file, save_module_file
from psynthea.dsl import ModuleBuilder, age, code, otherwise, when
from psynthea.engine import Generator, GeneratorConfig

_MODS = Path(__file__).resolve().parent / "fixtures" / "synthea_modules"
_MODULE_FILES = sorted(_MODS.glob("*.json"))


def _dsl_module():
    b = ModuleBuilder("rt_demo")
    b.initial().to("Annual_Check")
    b.delay("Annual_Check", years=1).complex(
        when(age("<", 8, "years")).distributed((0.3, "Visit"), (0.7, "Annual_Check")),
        otherwise("Annual_Check"),
    )
    b.encounter("Visit", code("SNOMED-CT", "185345009", "Encounter for symptom")).to("Diagnose")
    b.condition_onset("Diagnose", code("SNOMED-CT", "65363002", "Otitis media"),
                      assign_to="otitis_media").to("Resolve")
    b.delay("Resolve", days=10).to("Cure")
    b.condition_end("Cure", code("SNOMED-CT", "65363002", "Otitis media")).to("Annual_Check")
    return b.build()


def test_dsl_module_round_trips_through_json():
    m = _dsl_module()
    again = load_module_dict(dump_module(m), name=m.name)
    assert again == m


@pytest.mark.parametrize("path", _MODULE_FILES, ids=lambda p: p.stem)
def test_real_module_round_trips(path):
    m = load_module_file(path)
    again = load_module_dict(dump_module(m), name=m.name)
    assert again == m              # IR is identical after a JSON round-trip


def test_dumped_module_is_valid_gmf_shape():
    d = dump_module(_dsl_module())
    assert d["name"] == "rt_demo"
    assert d["states"]["Initial"]["type"] == "Initial"
    assert d["states"]["Annual_Check"]["type"] == "Delay"
    assert "complex_transition" in d["states"]["Annual_Check"]
    assert d["gmf_version"] == 2


def test_saved_dsl_module_loads_and_runs(tmp_path):
    m = _dsl_module()
    out = save_module_file(m, tmp_path / "rt_demo.json")
    assert out.exists()
    reloaded = load_module_file(out)
    people = Generator([reloaded], GeneratorConfig(
        population=10, seed=1, end_date=datetime(2025, 1, 1))).run()
    assert len(people) == 10


def test_cli_export_writes_loadable_module(tmp_path):
    from psynthea.cli import main

    out = tmp_path / "otitis.json"
    rc = main(["export", "-m", "otitis_media", "-o", str(out)])
    assert rc == 0 and out.exists()
    # the file the CLI wrote must import back and run
    reloaded = load_module_file(out)
    assert "Initial" in reloaded.states


def test_cli_export_rejects_multiple_modules(tmp_path):
    from psynthea.cli import main

    out = tmp_path / "x.json"
    rc = main(["export", "-m", "otitis_media", "-m", "otitis_media", "-o", str(out)])
    assert rc == 2
