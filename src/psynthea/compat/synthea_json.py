"""Import Synthea Generic Module Framework (GMF) JSON into the psynthea IR.

Fidelity principle (ADR-003): unsupported state/transition/logic types raise
``NotSupportedError`` rather than being silently skipped — a silent skip would
corrupt any fidelity claim. The one deliberate exception is billing/cost metadata
(ADR-011): we simply never read it, so it is ignored without error.
"""
from __future__ import annotations

import json
from pathlib import Path

from psynthea.ir import logic as L
from psynthea.ir import states as S
from psynthea.ir import transitions as T
from psynthea.ir.module import Module
from psynthea.terminology import Code


class NotSupportedError(NotImplementedError):
    """A GMF construct psynthea does not yet support (Phase-1 subset)."""


# --------------------------------------------------------------------------- #
# Logic
# --------------------------------------------------------------------------- #
def _parse_codes(items: list[dict]) -> list[Code]:
    return [Code.from_dict(i) for i in items]


def _logic_codes(d: dict) -> list[Code]:
    """Codes for a code-based condition; fail loud (not crash) if absent."""
    if "codes" not in d:
        raise NotSupportedError(f"{d.get('condition_type')!r} condition without 'codes'")
    return _parse_codes(d["codes"])


def _parse_logic(d: dict) -> L.Logic:
    kind = d.get("condition_type")
    if kind == "True":
        return L.TrueLogic()
    if kind == "False":
        return L.FalseLogic()
    if kind == "Gender":
        return L.Gender(gender=d["gender"])
    if kind == "Age":
        return L.Age(operator=d["operator"], quantity=d["quantity"], unit=d["unit"])
    if kind == "Attribute":
        return L.Attribute(attribute=d["attribute"], operator=d["operator"], value=d.get("value"))
    if kind == "Active Condition":
        return L.ActiveCondition(codes=_logic_codes(d))
    if kind == "PriorState":
        return L.PriorState(name=d["name"])
    if kind == "And":
        return L.And(conditions=[_parse_logic(c) for c in d["conditions"]])
    if kind == "Or":
        return L.Or(conditions=[_parse_logic(c) for c in d["conditions"]])
    if kind == "Not":
        return L.Not(condition=_parse_logic(d["condition"]))
    if kind == "Date":
        year = d.get("year") or d.get("date", {}).get("year")
        if year is None:
            raise NotSupportedError("Date condition without a year")
        return L.DateLogic(operator=d.get("operator", ">="), year=int(year))
    if kind == "Race":
        return L.Race(race=d["race"])
    if kind == "Socioeconomic Status":
        return L.SocioeconomicStatus(category=d["category"])
    if kind == "Vital Sign":
        return L.VitalSign(vital_sign=d["vital_sign"], operator=d["operator"], value=d.get("value"))
    if kind == "Symptom":
        return L.Symptom(symptom=d["symptom"], operator=d["operator"], value=d.get("value"))
    if kind == "Active Medication":
        return L.ActiveMedication(codes=_logic_codes(d))
    if kind == "Active Allergy":
        return L.ActiveAllergy(codes=_logic_codes(d))
    if kind == "Active CarePlan":
        return L.ActiveCarePlan(codes=_logic_codes(d))
    if kind == "Observation":
        return L.ObservationLogic(codes=_logic_codes(d),
                                  operator=d["operator"], value=d.get("value"))
    if kind == "At Least":
        return L.AtLeast(minimum=int(d["minimum"]),
                         conditions=[_parse_logic(c) for c in d["conditions"]])
    if kind == "At Most":
        return L.AtMost(maximum=int(d["maximum"]),
                        conditions=[_parse_logic(c) for c in d["conditions"]])
    raise NotSupportedError(f"logic condition_type {kind!r}")


# --------------------------------------------------------------------------- #
# Transitions
# --------------------------------------------------------------------------- #
def _parse_distribution(items: list[dict]) -> T.DistributedTransition:
    choices: list[tuple[str, float]] = []
    for e in items:
        dist = e["distribution"]
        if isinstance(dist, dict):
            # GMF allows an attribute/table-based distribution object; we use its
            # numeric default rather than crashing (fail loud only if there is none).
            if "default" in dist:
                dist = dist["default"]
            else:
                raise NotSupportedError("distributed_transition with a non-numeric "
                                        "distribution and no 'default'")
        choices.append((e["transition"], float(dist)))
    return T.DistributedTransition(choices)


def _parse_transition(d: dict) -> T.Transition | None:
    if "direct_transition" in d:
        return T.DirectTransition(d["direct_transition"])
    if "distributed_transition" in d:
        return _parse_distribution(d["distributed_transition"])
    if "conditional_transition" in d:
        branches = [
            (_parse_logic(e["condition"]) if "condition" in e else None, e["transition"])
            for e in d["conditional_transition"]
        ]
        return T.ConditionalTransition(branches)
    if "complex_transition" in d:
        branches: list[tuple[L.Logic | None, object]] = []
        for e in d["complex_transition"]:
            condition = _parse_logic(e["condition"]) if "condition" in e else None
            if "distributions" in e:
                payload: object = _parse_distribution(e["distributions"])
            elif "transition" in e:
                payload = e["transition"]
            else:
                raise NotSupportedError("complex_transition entry without transition/distributions")
            branches.append((condition, payload))
        return T.ComplexTransition(branches)
    return None


# --------------------------------------------------------------------------- #
# States
# --------------------------------------------------------------------------- #
def _parse_delay(name: str, d: dict, tr) -> S.Delay:
    if "exact" in d:
        q = d["exact"]
        return S.Delay(name=name, transition=tr, low=q["quantity"], high=q["quantity"], unit=q["unit"])
    if "range" in d:
        r = d["range"]
        return S.Delay(name=name, transition=tr, low=r["low"], high=r["high"], unit=r["unit"])
    if "distribution" in d:
        dist = d["distribution"]
        unit = d.get("unit", "days")
        p = dist.get("parameters", {})
        kind = dist.get("kind")
        if kind == "UNIFORM":
            lo, hi = p["low"], p["high"]
        elif kind == "EXACT":
            lo = hi = p.get("value", p.get("quantity"))
        elif kind in ("GAUSSIAN", "EXPONENTIAL"):
            lo = hi = p["mean"]    # spread ignored (Phase-1 approximation)
        else:
            raise NotSupportedError(f"Delay {name!r} distribution kind {kind!r}")
        return S.Delay(name=name, transition=tr, low=lo, high=hi, unit=unit)
    raise NotSupportedError(f"Delay state {name!r} without exact/range/distribution")


def _parse_observation(name: str, d: dict, tr) -> S.Observation:
    obs = S.Observation(
        name=name,
        transition=tr,
        codes=_parse_codes(d.get("codes", [])),
        unit=d.get("unit", ""),
        category=d.get("category", ""),
    )
    if "exact" in d:
        obs.exact_value = d["exact"]["quantity"]
    elif "range" in d:
        obs.range_low, obs.range_high = d["range"]["low"], d["range"]["high"]
    elif "attribute" in d:
        obs.attribute = d["attribute"]
    elif "vital_sign" in d:
        obs.attribute = d["vital_sign"]
    return obs


def _scalar_value(d: dict) -> float:
    """A representative numeric value from an exact/range spec (Symptom/VitalSign)."""
    if "exact" in d:
        return float(d["exact"]["quantity"])
    if "range" in d:
        return (float(d["range"]["low"]) + float(d["range"]["high"])) / 2.0
    return 0.0


_PASSTHROUGH_TYPES = {
    "ImagingStudy", "Device", "DeviceEnd", "SupplyList", "DiagnosticReport",
    "MultiObservation", "CallSubmodule", "Telemedicine",
}


def _end_state(kind: str, name: str, d: dict, tr, cls, ref_key: str):
    """ConditionEnd/MedicationEnd/AllergyEnd: end by explicit codes, by an attribute
    reference (set by the onset's assign_to_attribute), or by the onset *state name*
    (``ref_key``), which is resolved to codes at load time."""
    codes = _parse_codes(d.get("codes", []))
    ref_attr = d.get("referenced_by_attribute")
    ref_state = d.get(ref_key)
    if not codes and not ref_attr and not ref_state:
        raise NotSupportedError(
            f"{kind} state {name!r} without 'codes', 'referenced_by_attribute', or {ref_key!r}")
    return cls(name=name, transition=tr, codes=codes,
               referenced_by_attribute=ref_attr, references_state=ref_state)


def _parse_state(name: str, d: dict) -> S.State:
    kind = d.get("type")
    tr = _parse_transition(d)

    if kind == "Initial":
        return S.Initial(name=name, transition=tr)
    if kind == "Terminal":
        return S.Terminal(name=name, transition=tr)
    if kind == "Simple":
        return S.Simple(name=name, transition=tr)
    if kind == "Guard":
        return S.Guard(name=name, transition=tr, allow=_parse_logic(d["allow"]))
    if kind == "Delay":
        return _parse_delay(name, d, tr)
    if kind == "SetAttribute":
        return S.SetAttribute(name=name, transition=tr, attribute=d["attribute"], value=d.get("value"))
    if kind == "Encounter":
        enc_class = d.get("encounter_class", "ambulatory")
        return S.Encounter(
            name=name, transition=tr,
            codes=_parse_codes(d.get("codes", [])),
            encounter_class=enc_class,
            wellness=bool(d.get("wellness", enc_class == "wellness")),
        )
    if kind == "EncounterEnd":
        return S.EncounterEnd(name=name, transition=tr)
    if kind == "ConditionOnset":
        return S.ConditionOnset(
            name=name, transition=tr,
            codes=_parse_codes(d.get("codes", [])),
            assign_to_attribute=d.get("assign_to_attribute"),
            target_encounter=d.get("target_encounter"),
        )
    if kind == "ConditionEnd":
        return _end_state("ConditionEnd", name, d, tr, S.ConditionEnd, "condition_onset")
    if kind == "MedicationOrder":
        return S.MedicationOrder(
            name=name, transition=tr,
            codes=_parse_codes(d.get("codes", [])),
            assign_to_attribute=d.get("assign_to_attribute"),
        )
    if kind == "MedicationEnd":
        return _end_state("MedicationEnd", name, d, tr, S.MedicationEnd, "medication_order")
    if kind == "Observation":
        return _parse_observation(name, d, tr)
    if kind == "Death":
        return S.Death(name=name, transition=tr)
    if kind == "Procedure":
        return S.Procedure(name=name, transition=tr, codes=_parse_codes(d.get("codes", [])),
                           assign_to_attribute=d.get("assign_to_attribute"),
                           target_encounter=d.get("target_encounter"))
    if kind in ("Immunization", "Vaccine"):
        return S.Immunization(name=name, transition=tr, codes=_parse_codes(d.get("codes", [])),
                              assign_to_attribute=d.get("assign_to_attribute"))
    if kind == "AllergyOnset":
        return S.AllergyOnset(name=name, transition=tr, codes=_parse_codes(d.get("codes", [])),
                              assign_to_attribute=d.get("assign_to_attribute"),
                              target_encounter=d.get("target_encounter"))
    if kind == "AllergyEnd":
        return _end_state("AllergyEnd", name, d, tr, S.AllergyEnd, "allergy_onset")
    if kind == "Symptom":
        return S.Symptom(name=name, transition=tr, symptom=d.get("symptom", ""), value=_scalar_value(d))
    if kind == "VitalSign":
        return S.VitalSign(name=name, transition=tr, vital_sign=d.get("vital_sign", ""),
                           value=_scalar_value(d))
    if kind == "Counter":
        return S.Counter(name=name, transition=tr, attribute=d["attribute"],
                         action=d.get("action", "increment"), amount=d.get("amount", 1))
    if kind == "CarePlanStart":
        return S.CarePlanStart(name=name, transition=tr, codes=_parse_codes(d.get("codes", [])),
                               assign_to_attribute=d.get("assign_to_attribute"),
                               target_encounter=d.get("target_encounter"))
    if kind == "CarePlanEnd":
        return S.CarePlanEnd(name=name, transition=tr, codes=_parse_codes(d.get("codes", [])))
    if kind in _PASSTHROUGH_TYPES:
        return S.Passthrough(name=name, transition=tr,
                             assign_to_attribute=d.get("assign_to_attribute"), gmf_type=kind)

    raise NotSupportedError(f"state type {kind!r} (state {name!r})")


# --------------------------------------------------------------------------- #
# Module
# --------------------------------------------------------------------------- #
def _resolve_end_references(states: dict) -> None:
    """Fill end-state codes that referenced their onset by state name."""
    end_types = (S.ConditionEnd, S.MedicationEnd, S.AllergyEnd)
    for st in states.values():
        if isinstance(st, end_types) and not st.codes and st.references_state:
            ref = states.get(st.references_state)
            if ref is not None and getattr(ref, "codes", None):
                st.codes = list(ref.codes)


def load_module_dict(data: dict, *, name: str | None = None) -> Module:
    module_name = name or data.get("name") or "unnamed"
    states = {sn: _parse_state(sn, sd) for sn, sd in data["states"].items()}
    _resolve_end_references(states)
    return Module(name=module_name, states=states, remarks=list(data.get("remarks", [])))


def load_module_file(path: str | Path) -> Module:
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return load_module_dict(data, name=data.get("name") or path.stem)
