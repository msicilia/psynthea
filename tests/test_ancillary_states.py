"""Previously-no-op GMF state types now emit records (MultiObservation,
DiagnosticReport, Device, ImagingStudy, SupplyList) + the two rare transitions."""
from __future__ import annotations

from datetime import datetime

from psynthea.compat import dump_module, load_module_dict
from psynthea.engine import Generator, GeneratorConfig
from psynthea.ir import states as S


def _run(states, n=8):
    m = load_module_dict({"name": "m", "states": states})
    people = Generator([m], GeneratorConfig(
        population=n, seed=1, end_date=datetime(2025, 1, 1))).run()
    return m, people


CODE = {"system": "SNOMED-CT", "code": "111", "display": "x"}
OBS = {"codes": [{"system": "LOINC", "code": "2339-0", "display": "Glucose"}],
       "unit": "mg/dL", "category": "laboratory", "exact": {"quantity": 90}}


def test_diagnostic_report_emits_component_observations():
    _, people = _run({
        "Initial": {"type": "Initial", "direct_transition": "R"},
        "R": {"type": "DiagnosticReport", "codes": [{"system": "LOINC", "code": "24323-8"}],
              "observations": [OBS, dict(OBS, codes=[{"system": "LOINC", "code": "6299-2"}])],
              "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    for p in people:
        codes = {o.code.code for o in p.record.observations if o.code}
        assert codes == {"2339-0", "6299-2"}


def test_multiobservation_emits_components():
    _, people = _run({
        "Initial": {"type": "Initial", "direct_transition": "M"},
        "M": {"type": "MultiObservation", "category": "survey",
              "codes": [{"system": "LOINC", "code": "91148-7"}],
              "observations": [OBS], "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    assert all(any(o.code.code == "2339-0" for o in p.record.observations) for p in people)


def test_device_imaging_supply_emit_records():
    _, people = _run({
        "Initial": {"type": "Initial", "direct_transition": "D"},
        "D": {"type": "Device", "code": CODE, "direct_transition": "I"},
        "I": {"type": "ImagingStudy", "procedure_code": CODE,
              "series": [{"modality": {"system": "DICOM-DCM", "code": "DX"}, "body_site": CODE}],
              "direct_transition": "SUP"},
        "SUP": {"type": "SupplyList", "supplies": [{"quantity": 3, "code": CODE}],
                "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    for p in people:
        assert len(p.record.devices) == 1 and p.record.devices[0].code.code == "111"
        assert p.record.imaging_studies[0].modality == "DX"
        assert p.record.supplies[0].quantity == 3


def test_device_end_closes_device():
    _, people = _run({
        "Initial": {"type": "Initial", "direct_transition": "D"},
        "D": {"type": "Device", "code": CODE, "direct_transition": "E"},
        "E": {"type": "DeviceEnd", "code": CODE, "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    assert all(p.record.devices[0].stop is not None for p in people)


def test_alt_and_type_of_care_transitions_route():
    m, people = _run({
        "Initial": {"type": "Initial", "alt_direct_transition": "Care"},
        "Care": {"type": "Simple",
                 "type_of_care_transition": {"ambulatory": "Onset", "emergency": "Nope"}},
        "Onset": {"type": "ConditionOnset", "codes": [CODE], "direct_transition": "Terminal"},
        "Nope": {"type": "Terminal"},
        "Terminal": {"type": "Terminal"}})
    # alt_direct -> Care, type_of_care -> ambulatory -> Onset
    assert all(any(c.code.code == "111" for c in p.record.conditions) for p in people)


def test_new_states_round_trip():
    for states in [
        {"Initial": {"type": "Initial", "direct_transition": "R"},
         "R": {"type": "DiagnosticReport", "codes": [CODE], "observations": [OBS],
               "direct_transition": "Terminal"}, "Terminal": {"type": "Terminal"}},
        {"Initial": {"type": "Initial", "direct_transition": "S"},
         "S": {"type": "SupplyList", "supplies": [{"quantity": 2, "code": CODE}],
               "direct_transition": "Terminal"}, "Terminal": {"type": "Terminal"}},
    ]:
        m = load_module_dict({"name": "rt", "states": states})
        assert load_module_dict(dump_module(m), name=m.name) == m


def test_only_telemedicine_remains_passthrough():
    from psynthea.compat.synthea_json import _PASSTHROUGH_TYPES
    assert _PASSTHROUGH_TYPES == {"Telemedicine"}
    assert not isinstance(load_module_dict({"name": "m", "states": {
        "Initial": {"type": "Initial", "direct_transition": "D"},
        "D": {"type": "Device", "code": CODE, "direct_transition": "Terminal"},
        "Terminal": {"type": "Terminal"}}}).states["D"], S.Passthrough)
