"""Export the psynthea IR back to Synthea Generic Module Framework (GMF) JSON.

This is the inverse of :mod:`psynthea.compat.synthea_json`. Because the DSL and the
JSON importer both compile to the same IR, a single IR->JSON serializer makes
compatibility **bidirectional**: a module authored in the Python DSL can be written
out as a stock-format GMF module, and any imported module re-exported.

Round-trip guarantee: for every construct in the supported subset, ``load`` ∘ ``dump``
is the identity on the IR (verified in tests). Constructs psynthea cannot represent
never reach the IR in the first place, so the exporter does not lose information the
engine had.
"""
from __future__ import annotations

import json
from pathlib import Path

from psynthea.ir import logic as L
from psynthea.ir import states as S
from psynthea.ir import transitions as T
from psynthea.ir.module import Module
from psynthea.terminology import Code


class ExportError(NotImplementedError):
    """An IR construct the exporter does not know how to serialize (should not occur
    for IR produced by the importer or DSL)."""


# --------------------------------------------------------------------------- #
# Codes
# --------------------------------------------------------------------------- #
def _dump_code(c: Code) -> dict:
    return {"system": c.system, "code": c.code, "display": c.display}


def _dump_codes(codes: list[Code]) -> list[dict]:
    return [_dump_code(c) for c in codes]


# --------------------------------------------------------------------------- #
# Logic  (inverse of synthea_json._parse_logic)
# --------------------------------------------------------------------------- #
def _dump_logic(lg: L.Logic) -> dict:
    if isinstance(lg, L.TrueLogic):
        return {"condition_type": "True"}
    if isinstance(lg, L.FalseLogic):
        return {"condition_type": "False"}
    if isinstance(lg, L.Gender):
        return {"condition_type": "Gender", "gender": lg.gender}
    if isinstance(lg, L.Age):
        return {"condition_type": "Age", "operator": lg.operator,
                "quantity": lg.quantity, "unit": lg.unit}
    if isinstance(lg, L.Attribute):
        d = {"condition_type": "Attribute", "attribute": lg.attribute, "operator": lg.operator}
        if lg.value is not None:
            d["value"] = lg.value
        return d
    if isinstance(lg, L.ActiveCondition):
        return {"condition_type": "Active Condition", "codes": _dump_codes(lg.codes)}
    if isinstance(lg, L.PriorState):
        return {"condition_type": "PriorState", "name": lg.name}
    if isinstance(lg, L.And):
        return {"condition_type": "And", "conditions": [_dump_logic(c) for c in lg.conditions]}
    if isinstance(lg, L.Or):
        return {"condition_type": "Or", "conditions": [_dump_logic(c) for c in lg.conditions]}
    if isinstance(lg, L.Not):
        return {"condition_type": "Not", "condition": _dump_logic(lg.condition)}
    if isinstance(lg, L.DateLogic):
        return {"condition_type": "Date", "operator": lg.operator, "year": lg.year}
    if isinstance(lg, L.Race):
        return {"condition_type": "Race", "race": lg.race}
    if isinstance(lg, L.SocioeconomicStatus):
        return {"condition_type": "Socioeconomic Status", "category": lg.category}
    if isinstance(lg, L.VitalSign):
        d = {"condition_type": "Vital Sign", "vital_sign": lg.vital_sign, "operator": lg.operator}
        if lg.value is not None:
            d["value"] = lg.value
        return d
    if isinstance(lg, L.Symptom):
        d = {"condition_type": "Symptom", "symptom": lg.symptom, "operator": lg.operator}
        if lg.value is not None:
            d["value"] = lg.value
        return d
    if isinstance(lg, L.ActiveMedication):
        return {"condition_type": "Active Medication", "codes": _dump_codes(lg.codes)}
    if isinstance(lg, L.ActiveAllergy):
        return {"condition_type": "Active Allergy", "codes": _dump_codes(lg.codes)}
    if isinstance(lg, L.ActiveCarePlan):
        return {"condition_type": "Active CarePlan", "codes": _dump_codes(lg.codes)}
    if isinstance(lg, L.ObservationLogic):
        d = {"condition_type": "Observation", "codes": _dump_codes(lg.codes),
             "operator": lg.operator}
        if lg.value is not None:
            d["value"] = lg.value
        return d
    if isinstance(lg, L.AtLeast):
        return {"condition_type": "At Least", "minimum": lg.minimum,
                "conditions": [_dump_logic(c) for c in lg.conditions]}
    if isinstance(lg, L.AtMost):
        return {"condition_type": "At Most", "maximum": lg.maximum,
                "conditions": [_dump_logic(c) for c in lg.conditions]}
    raise ExportError(f"cannot serialize logic {type(lg).__name__}")


# --------------------------------------------------------------------------- #
# Transitions  (inverse of synthea_json._parse_transition)
# --------------------------------------------------------------------------- #
def _dump_distribution(tr: T.DistributedTransition) -> list[dict]:
    return [{"transition": target, "distribution": weight} for target, weight in tr.choices]


def _dump_transition(tr: T.Transition | None) -> dict:
    """Return the transition keys to merge into a state dict ({} if none)."""
    if tr is None:
        return {}
    if isinstance(tr, T.DirectTransition):
        return {"direct_transition": tr.to}
    if isinstance(tr, T.DistributedTransition):
        return {"distributed_transition": _dump_distribution(tr)}
    if isinstance(tr, T.ConditionalTransition):
        entries = []
        for condition, target in tr.branches:
            e: dict = {}
            if condition is not None:
                e["condition"] = _dump_logic(condition)
            e["transition"] = target
            entries.append(e)
        return {"conditional_transition": entries}
    if isinstance(tr, T.ComplexTransition):
        entries = []
        for condition, payload in tr.branches:
            e = {}
            if condition is not None:
                e["condition"] = _dump_logic(condition)
            if isinstance(payload, T.DistributedTransition):
                e["distributions"] = _dump_distribution(payload)
            else:
                e["transition"] = payload
            entries.append(e)
        return {"complex_transition": entries}
    raise ExportError(f"cannot serialize transition {type(tr).__name__}")


# --------------------------------------------------------------------------- #
# States  (inverse of synthea_json._parse_state)
# --------------------------------------------------------------------------- #
def _dump_delay(st: S.Delay) -> dict:
    if st.high is None or st.high == st.low:
        return {"type": "Delay", "exact": {"quantity": st.low, "unit": st.unit}}
    return {"type": "Delay", "range": {"low": st.low, "high": st.high, "unit": st.unit}}


def _dump_observation(st: S.Observation) -> dict:
    d: dict = {"type": "Observation", "codes": _dump_codes(st.codes)}
    if st.unit:
        d["unit"] = st.unit
    if st.category:
        d["category"] = st.category
    if st.exact_value is not None:
        d["exact"] = {"quantity": st.exact_value}
    elif st.range_low is not None and st.range_high is not None:
        d["range"] = {"low": st.range_low, "high": st.range_high}
    elif st.attribute is not None:
        d["attribute"] = st.attribute
    return d


def _dump_end_state(gmf_type: str, st, ref_key: str) -> dict:
    """ConditionEnd/MedicationEnd/AllergyEnd: prefer explicit codes, else the
    attribute reference, else the onset state name (``ref_key``)."""
    d: dict = {"type": gmf_type}
    if st.codes:
        d["codes"] = _dump_codes(st.codes)
    if st.referenced_by_attribute:
        d["referenced_by_attribute"] = st.referenced_by_attribute
    # keep the by-name reference even when codes are present, so an imported module
    # whose end-state codes were resolved from the onset name round-trips exactly
    if st.references_state:
        d[ref_key] = st.references_state
    return d


def _with_assign(d: dict, st) -> dict:
    if getattr(st, "assign_to_attribute", None):
        d["assign_to_attribute"] = st.assign_to_attribute
    if getattr(st, "target_encounter", None):
        d["target_encounter"] = st.target_encounter
    return d


def _dump_state_body(st: S.State) -> dict:
    if isinstance(st, S.Initial):
        return {"type": "Initial"}
    if isinstance(st, S.Terminal):
        return {"type": "Terminal"}
    if isinstance(st, S.Simple):
        return {"type": "Simple"}
    if isinstance(st, S.Guard):
        return {"type": "Guard", "allow": _dump_logic(st.allow)}
    if isinstance(st, S.Delay):
        return _dump_delay(st)
    if isinstance(st, S.SetAttribute):
        d = {"type": "SetAttribute", "attribute": st.attribute}
        if st.value is not None:
            d["value"] = st.value
        return d
    if isinstance(st, S.Encounter):
        d = {"type": "Encounter", "codes": _dump_codes(st.codes),
             "encounter_class": st.encounter_class}
        if st.wellness:
            d["wellness"] = True
        return d
    if isinstance(st, S.EncounterEnd):
        return {"type": "EncounterEnd"}
    if isinstance(st, S.ConditionOnset):
        return _with_assign({"type": "ConditionOnset", "codes": _dump_codes(st.codes)}, st)
    if isinstance(st, S.ConditionEnd):
        return _dump_end_state("ConditionEnd", st, "condition_onset")
    if isinstance(st, S.MedicationOrder):
        return _with_assign({"type": "MedicationOrder", "codes": _dump_codes(st.codes)}, st)
    if isinstance(st, S.MedicationEnd):
        return _dump_end_state("MedicationEnd", st, "medication_order")
    if isinstance(st, S.Observation):
        return _dump_observation(st)
    if isinstance(st, S.Death):
        return {"type": "Death"}
    if isinstance(st, S.Procedure):
        return _with_assign({"type": "Procedure", "codes": _dump_codes(st.codes)}, st)
    if isinstance(st, S.Immunization):
        return _with_assign({"type": "Immunization", "codes": _dump_codes(st.codes)}, st)
    if isinstance(st, S.AllergyOnset):
        return _with_assign({"type": "AllergyOnset", "codes": _dump_codes(st.codes)}, st)
    if isinstance(st, S.AllergyEnd):
        return _dump_end_state("AllergyEnd", st, "allergy_onset")
    if isinstance(st, S.Symptom):
        return {"type": "Symptom", "symptom": st.symptom, "exact": {"quantity": st.value}}
    if isinstance(st, S.VitalSign):
        return {"type": "VitalSign", "vital_sign": st.vital_sign, "exact": {"quantity": st.value}}
    if isinstance(st, S.Counter):
        return {"type": "Counter", "attribute": st.attribute,
                "action": st.action, "amount": st.amount}
    if isinstance(st, S.CarePlanStart):
        return _with_assign({"type": "CarePlanStart", "codes": _dump_codes(st.codes)}, st)
    if isinstance(st, S.CarePlanEnd):
        return {"type": "CarePlanEnd", "codes": _dump_codes(st.codes)}
    if isinstance(st, S.Passthrough):
        d = {"type": st.gmf_type}
        if st.assign_to_attribute:
            d["assign_to_attribute"] = st.assign_to_attribute
        return d
    raise ExportError(f"cannot serialize state {type(st).__name__} ({st.name!r})")


# --------------------------------------------------------------------------- #
# Module
# --------------------------------------------------------------------------- #
def dump_module(module: Module) -> dict:
    """Serialize a Module to a Synthea GMF JSON dict."""
    states: dict[str, dict] = {}
    for name, st in module.states.items():
        body = _dump_state_body(st)
        body.update(_dump_transition(st.transition))
        states[name] = body
    out: dict = {"name": module.name, "states": states}
    if module.remarks:
        out["remarks"] = list(module.remarks)
    out["gmf_version"] = 2
    return out


def save_module_file(module: Module, path: str | Path, *, indent: int = 2) -> Path:
    """Write ``module`` to ``path`` as Synthea GMF JSON; returns the path."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(dump_module(module), fh, indent=indent, ensure_ascii=False)
        fh.write("\n")
    return path
