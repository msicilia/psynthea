"""Import + run tests against real, vendored Synthea stock modules.

These exercise the importer against genuine modules (not hand-crafted fixtures),
checking it (a) imports them without crashing and (b) the imported module runs.
Modules are from MITRE Synthea (Apache-2.0); see fixtures/synthea_modules/NOTICE.txt.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig

_MODS = Path(__file__).resolve().parent / "fixtures" / "synthea_modules"
_MODULE_FILES = sorted(_MODS.glob("*.json"))


def test_fixtures_present():
    assert len(_MODULE_FILES) >= 6, "expected several vendored real Synthea modules"


@pytest.mark.parametrize("path", _MODULE_FILES, ids=lambda p: p.stem)
def test_real_stock_module_imports(path):
    module = load_module_file(path)          # must not raise (real modules)
    assert "Initial" in module.states
    assert len(module.states) > 5


@pytest.mark.parametrize("path", _MODULE_FILES, ids=lambda p: p.stem)
def test_real_stock_module_runs(path):
    module = load_module_file(path)
    people = Generator([module], GeneratorConfig(
        population=15, seed=1, end_date=datetime(2025, 1, 1))).run()
    assert len(people) == 15
