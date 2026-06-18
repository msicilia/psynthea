"""Tests for the Synthea GMF JSON importer."""
from __future__ import annotations

import pytest

from psynthea.compat import NotSupportedError, load_module_dict
from psynthea.ir import states as S
from psynthea.ir import transitions as T


def test_import_otitis_media_fixture():
    from pathlib import Path

    from psynthea.compat import load_module_file

    root = Path(__file__).resolve().parents[1]
    module = load_module_file(root / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    assert module.name == "otitis_media"
    assert isinstance(module.states["Initial"], S.Initial)
    assert isinstance(module.states["Annual_Check"], S.Delay)
    assert isinstance(module.states["Annual_Check"].transition, T.ComplexTransition)
    assert isinstance(module.states["Ear_Infection_Encounter"], S.Encounter)
    onset = module.states["Diagnose_Otitis_Media"]
    assert isinstance(onset, S.ConditionOnset)
    assert onset.codes[0].code == "65363002"
    med = module.states["Prescribe_Amoxicillin"]
    assert med.codes[0].system == "ATC"


def test_unsupported_state_type_raises():
    data = {"states": {
        "Initial": {"type": "Initial", "direct_transition": "Weird"},
        "Weird": {"type": "Physiology", "direct_transition": "Initial"},  # still unsupported
    }}
    with pytest.raises(NotSupportedError):
        load_module_dict(data)


def test_unsupported_logic_type_raises():
    data = {"states": {
        "Initial": {"type": "Initial",
                    "conditional_transition": [
                        {"condition": {"condition_type": "PhysiologyValue"},  # still unsupported
                         "transition": "Initial"}]},
    }}
    with pytest.raises(NotSupportedError):
        load_module_dict(data)


def test_passthrough_types_import():
    # previously-unsupported states now parse (executed as no-ops) for compatibility
    data = {"states": {
        "Initial": {"type": "Initial", "direct_transition": "Img"},
        "Img": {"type": "ImagingStudy", "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"},
    }}
    module = load_module_dict(data)
    assert isinstance(module.states["Img"], S.Passthrough)
