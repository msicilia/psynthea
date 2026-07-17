"""Import Synthea Generic Module Framework (GMF) JSON into the psynthea IR.

Fidelity principle (ADR-003): unsupported state/transition/logic types raise
``NotSupportedError`` rather than being silently skipped — a silent skip would
corrupt any fidelity claim. The one deliberate exception is billing/cost metadata
(ADR-011): we simply never read it, so it is ignored without error.
"""
from __future__ import annotations

import csv
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
    if "alt_direct_transition" in d:
        return T.DirectTransition(d["alt_direct_transition"])
    if "type_of_care_transition" in d:
        # psynthea has no explicit care-setting model; route to ambulatory (else any).
        routes = d["type_of_care_transition"]
        target = routes.get("ambulatory") or next(iter(routes.values()), None)
        return T.DirectTransition(target) if target else None
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
    if "lookup_table_transition" in d:
        entries = d["lookup_table_transition"]
        choices = [(e["transition"], float(e.get("default_probability", 0.0))) for e in entries]
        table_name = entries[0].get("lookup_table_name", "") if entries else ""
        return T.LookupTableTransition(choices=choices, table_name=table_name)
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


_PASSTHROUGH_TYPES = {"Telemedicine"}


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
    if kind == "CallSubmodule":
        return S.CallSubmodule(name=name, transition=tr, submodule_name=d.get("submodule", ""))
    if kind in ("MultiObservation", "DiagnosticReport"):
        components = [_parse_observation(f"{name}_c{i}", o, None)
                     for i, o in enumerate(d.get("observations", []))]
        cls = S.MultiObservation if kind == "MultiObservation" else S.DiagnosticReport
        return cls(name=name, transition=tr, codes=_parse_codes(d.get("codes", [])),
                   category=d.get("category", ""), components=components)
    if kind == "Device":
        return S.Device(name=name, transition=tr,
                        code=Code.from_dict(d["code"]) if "code" in d else None)
    if kind == "DeviceEnd":
        code = None
        if "code" in d:
            code = Code.from_dict(d["code"])
        elif d.get("codes"):
            code = _parse_codes(d["codes"])[0]
        return S.DeviceEnd(name=name, transition=tr, code=code)
    if kind == "ImagingStudy":
        proc = Code.from_dict(d["procedure_code"]) if "procedure_code" in d else None
        series = d.get("series") or []
        modality, body_site = "", None
        if series:
            m, bs = series[0].get("modality"), series[0].get("body_site")
            modality = (m.get("code", "") if isinstance(m, dict) else "") or ""
            body_site = Code.from_dict(bs) if isinstance(bs, dict) else None
        return S.ImagingStudy(name=name, transition=tr, procedure_code=proc,
                              modality=modality, body_site=body_site)
    if kind == "SupplyList":
        supplies = [(Code.from_dict(s["code"]), s.get("quantity", 1))
                    for s in d.get("supplies", []) if "code" in s]
        return S.SupplyList(name=name, transition=tr, supplies=supplies)
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


def _fill_lookup_table(tr: "T.LookupTableTransition", csv_path: Path) -> None:
    """Populate a LookupTableTransition's rows from its CSV; leave empty if missing
    (the transition then falls back to per-target default probabilities)."""
    if not csv_path.exists():
        return
    targets = {t for t, _ in tr.choices}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader)]
        input_cols = [h for h in header if h not in targets]
        rows: list[tuple[dict, dict]] = []
        for raw in reader:
            if not raw or not any(cell.strip() for cell in raw):
                continue
            cells = dict(zip(header, raw))
            inputs = {c: cells.get(c, "") for c in input_cols}
            probs: dict[str, float] = {}
            for t in targets:
                try:
                    probs[t] = float(cells.get(t, 0.0))
                except ValueError:
                    probs[t] = 0.0
            rows.append((inputs, probs))
    tr.input_columns = input_cols
    tr.rows = rows


def load_module_with_submodules(path: str | Path, modules_dir: str | Path,
                                *, name: str | None = None) -> Module:
    """Load a module and resolve its ``CallSubmodule`` references from ``modules_dir``.

    Submodules are referenced by path relative to ``modules_dir`` (e.g.
    ``"medications/otc_pain_reliever"`` -> ``<modules_dir>/medications/…​.json``),
    resolved transitively and shared/cycle-safe. A reference whose file is missing is
    left unresolved (the executor treats it as a no-op), so partial module trees still
    run.
    """
    modules_dir = Path(modules_dir)
    registry: dict[str, Module | None] = {}

    def _resolve(module: Module) -> None:
        for st in module.states.values():
            if isinstance(st, S.CallSubmodule) and st.submodule_name and st.submodule is None:
                st.submodule = _load_ref(st.submodule_name)
            tr = getattr(st, "transition", None)
            if isinstance(tr, T.LookupTableTransition) and tr.table_name and not tr.rows:
                _fill_lookup_table(tr, modules_dir / "lookup_tables" / tr.table_name)

    def _load_ref(ref: str) -> Module | None:
        if ref in registry:
            return registry[ref]
        sub_path = modules_dir / f"{ref}.json"
        if not sub_path.exists():
            registry[ref] = None
            return None
        with sub_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        sub = load_module_dict(data, name=data.get("name") or ref)
        registry[ref] = sub          # register before recursing (cycle-safe)
        _resolve(sub)
        return sub

    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    top = load_module_dict(data, name=name or data.get("name") or path.stem)
    _resolve(top)
    return top


def load_all_modules(modules_dir: str | Path, *, names: list[str] | None = None,
                     skip_unsupported: bool = True) -> list[Module]:
    """Load the whole top-level module set (each with submodules + lookup tables
    resolved) for running as an ensemble, so cross-module attributes set by one module
    are visible to others (as in Synthea). Top-level modules are the ``*.json`` files in
    ``modules_dir`` root; submodules live in subdirectories and load on demand.

    With ``skip_unsupported`` (default), modules that hit an unsupported construct on
    import are skipped rather than aborting the whole load.
    """
    modules_dir = Path(modules_dir)
    if names is not None:
        files = [modules_dir / f"{n}.json" for n in names]
    else:
        files = sorted(p for p in modules_dir.glob("*.json"))
    modules: list[Module] = []
    for f in files:
        try:
            modules.append(load_module_with_submodules(f, modules_dir))
        except NotSupportedError:
            if not skip_unsupported:
                raise
    return modules
