"""GMF state types (Phase-1 supported subset — see PLAN.md §1.1).

Contract (mirrors Synthea's ``State.process``):
``process(person, time, ctx) -> bool`` returns True if the module may advance to
the next state *now*, or False if the state blocks (Delay not elapsed, Guard
false, Terminal). The executor follows ``self.transition`` only when True.

States are shared across all people; all per-person execution state lives in the
ModuleContext (``ctx``), never on the state object.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from psynthea import _timeutil
from psynthea.ir.logic import Logic
from psynthea.ir.transitions import Transition
from psynthea.terminology import Code


@dataclass
class State:
    name: str
    transition: Transition | None = None

    def process(self, person, time, ctx) -> bool:
        return True


@dataclass
class Initial(State):
    pass


@dataclass
class Terminal(State):
    def process(self, person, time, ctx) -> bool:
        return False  # a module rests forever in Terminal


@dataclass
class Simple(State):
    pass


@dataclass
class Guard(State):
    allow: Logic | None = None

    def process(self, person, time, ctx) -> bool:
        return self.allow.test(person, time, ctx) if self.allow else True


@dataclass
class Delay(State):
    # exactly one of exact / range is set, as (quantity|low, high|None, unit)
    low: float = 0.0
    high: float | None = None
    unit: str = "days"

    def _key(self) -> str:
        return f"{self.name}::delay_end"

    def process(self, person, time, ctx) -> bool:
        key = self._key()
        end = ctx.scratch.get(key)
        if end is None:
            if self.high is None or self.high == self.low:
                quantity = self.low
            else:
                quantity = person.rng.uniform(self.low, self.high)
            end = ctx.entered_time + _timeutil.to_timedelta(quantity, self.unit)
            ctx.scratch[key] = end
        if time >= end:
            ctx.scratch.pop(key, None)
            return True
        return False


@dataclass
class SetAttribute(State):
    attribute: str = ""
    value: object = None

    def process(self, person, time, ctx) -> bool:
        person.attributes[self.attribute] = self.value
        return True


@dataclass
class Encounter(State):
    codes: list[Code] = field(default_factory=list)
    encounter_class: str = "ambulatory"
    wellness: bool = False

    def process(self, person, time, ctx) -> bool:
        # A `wellness: true` encounter waits for a *scheduled* wellness visit. When the
        # generator manages wellness (see GeneratorConfig.wellness_encounters), block
        # until a visit is active and attach to it once (so loops that wait for the
        # next annual visit don't spin); otherwise fall back to creating one on the spot
        # so standalone disease modules still run end-to-end.
        if self.wellness and getattr(person, "wellness_managed", False):
            if not person.wellness_active:
                return False
            key = f"{self.name}::used_wellness"
            if ctx.scratch.get(key) == person.wellness_encounter_id:
                return False  # already used this visit — wait for the next one
            ctx.scratch[key] = person.wellness_encounter_id
            return True       # attach to the active wellness encounter
        code = self.codes[0] if self.codes else None
        person.record.start_encounter(code, time, self.encounter_class,
                                      source_module=ctx.module_name, source_state=self.name)
        return True


@dataclass
class EncounterEnd(State):
    def process(self, person, time, ctx) -> bool:
        person.record.end_encounter(time)
        return True


@dataclass
class ConditionOnset(State):
    codes: list[Code] = field(default_factory=list)
    assign_to_attribute: str | None = None
    target_encounter: str | None = None  # parsed for fidelity; see note below

    def process(self, person, time, ctx) -> bool:
        # Phase-1 simplification: we associate the condition with the *current*
        # encounter rather than deferring diagnosis to a named target_encounter.
        code = self.codes[0] if self.codes else None
        entry = person.record.start_condition(code, time,
                                              source_module=ctx.module_name, source_state=self.name)
        if self.assign_to_attribute and code is not None:
            person.attributes[self.assign_to_attribute] = entry
        return True


def _end_referenced(person, attr: str | None, time) -> None:
    """End the clinical entry stored in an attribute (by an onset's assign_to)."""
    entry = person.attributes.get(attr) if attr else None
    if entry is not None and getattr(entry, "stop", "missing") is None:
        entry.stop = time


@dataclass
class ConditionEnd(State):
    codes: list[Code] = field(default_factory=list)
    referenced_by_attribute: str | None = None
    references_state: str | None = None    # onset state whose codes to end (resolved at load)

    def process(self, person, time, ctx) -> bool:
        _end_referenced(person, self.referenced_by_attribute, time)
        for code in self.codes:
            person.record.end_condition(code, time)
        return True


@dataclass
class MedicationOrder(State):
    codes: list[Code] = field(default_factory=list)
    assign_to_attribute: str | None = None

    def process(self, person, time, ctx) -> bool:
        code = self.codes[0] if self.codes else None
        entry = person.record.start_medication(code, time,
                                               source_module=ctx.module_name, source_state=self.name)
        if self.assign_to_attribute and code is not None:
            person.attributes[self.assign_to_attribute] = entry
        return True


@dataclass
class MedicationEnd(State):
    codes: list[Code] = field(default_factory=list)
    referenced_by_attribute: str | None = None
    references_state: str | None = None

    def process(self, person, time, ctx) -> bool:
        _end_referenced(person, self.referenced_by_attribute, time)
        for code in self.codes:
            person.record.end_medication(code, time)
        return True


@dataclass
class Observation(State):
    codes: list[Code] = field(default_factory=list)
    unit: str = ""
    category: str = ""
    # value source (Phase-1 subset)
    exact_value: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    attribute: str | None = None

    def _value(self, person):
        if self.exact_value is not None:
            return self.exact_value
        if self.range_low is not None and self.range_high is not None:
            return round(person.rng.uniform(self.range_low, self.range_high), 2)
        if self.attribute is not None:
            return person.attributes.get(self.attribute)
        return None

    def process(self, person, time, ctx) -> bool:
        code = self.codes[0] if self.codes else None
        person.record.add_observation(code, self._value(person), self.unit, time, self.category,
                                      source_module=ctx.module_name, source_state=self.name)
        return True


@dataclass
class Death(State):
    def process(self, person, time, ctx) -> bool:
        person.die(time)
        return True


@dataclass
class Procedure(State):
    codes: list[Code] = field(default_factory=list)
    assign_to_attribute: str | None = None
    target_encounter: str | None = None

    def process(self, person, time, ctx) -> bool:
        code = self.codes[0] if self.codes else None
        entry = person.record.start_procedure(code, time,
                                               source_module=ctx.module_name, source_state=self.name)
        if self.assign_to_attribute and code is not None:
            person.attributes[self.assign_to_attribute] = entry
        return True


@dataclass
class Immunization(State):
    codes: list[Code] = field(default_factory=list)
    assign_to_attribute: str | None = None

    def process(self, person, time, ctx) -> bool:
        code = self.codes[0] if self.codes else None
        entry = person.record.add_immunization(code, time,
                                               source_module=ctx.module_name, source_state=self.name)
        if self.assign_to_attribute and code is not None:
            person.attributes[self.assign_to_attribute] = entry
        return True


@dataclass
class AllergyOnset(State):
    codes: list[Code] = field(default_factory=list)
    assign_to_attribute: str | None = None
    target_encounter: str | None = None

    def process(self, person, time, ctx) -> bool:
        code = self.codes[0] if self.codes else None
        entry = person.record.start_allergy(code, time,
                                            source_module=ctx.module_name, source_state=self.name)
        if self.assign_to_attribute and code is not None:
            person.attributes[self.assign_to_attribute] = entry
        return True


@dataclass
class AllergyEnd(State):
    codes: list[Code] = field(default_factory=list)
    referenced_by_attribute: str | None = None
    references_state: str | None = None

    def process(self, person, time, ctx) -> bool:
        _end_referenced(person, self.referenced_by_attribute, time)
        for code in self.codes:
            person.record.end_allergy(code, time)
        return True


@dataclass
class Symptom(State):
    symptom: str = ""
    value: float = 0.0

    def process(self, person, time, ctx) -> bool:
        person.symptoms[self.symptom] = self.value
        return True


@dataclass
class VitalSign(State):
    vital_sign: str = ""
    value: float = 0.0

    def process(self, person, time, ctx) -> bool:
        person.attributes[self.vital_sign] = self.value
        return True


@dataclass
class Counter(State):
    attribute: str = ""
    action: str = "increment"   # increment | decrement
    amount: float = 1

    def process(self, person, time, ctx) -> bool:
        cur = person.attributes.get(self.attribute, 0) or 0
        person.attributes[self.attribute] = cur + (self.amount if self.action == "increment"
                                                    else -self.amount)
        return True


@dataclass
class CarePlanStart(State):
    codes: list[Code] = field(default_factory=list)
    assign_to_attribute: str | None = None
    target_encounter: str | None = None

    def process(self, person, time, ctx) -> bool:
        for code in self.codes:
            person.record.careplans.add(code.code)
        if self.assign_to_attribute and self.codes:
            person.attributes[self.assign_to_attribute] = self.codes[0]
        return True


@dataclass
class CarePlanEnd(State):
    codes: list[Code] = field(default_factory=list)

    def process(self, person, time, ctx) -> bool:
        for code in self.codes:
            person.record.careplans.discard(code.code)
        return True


@dataclass
class Device(State):
    code: Code | None = None

    def process(self, person, time, ctx) -> bool:
        person.record.start_device(self.code, time,
                                   source_module=ctx.module_name, source_state=self.name)
        return True


@dataclass
class DeviceEnd(State):
    code: Code | None = None

    def process(self, person, time, ctx) -> bool:
        if self.code is not None:
            person.record.end_device(self.code, time)
        return True


@dataclass
class ImagingStudy(State):
    procedure_code: Code | None = None
    modality: str = ""
    body_site: Code | None = None

    def process(self, person, time, ctx) -> bool:
        person.record.add_imaging_study(self.procedure_code, self.modality, self.body_site, time,
                                        source_module=ctx.module_name, source_state=self.name)
        return True


@dataclass
class SupplyList(State):
    supplies: list[tuple[Code, float]] = field(default_factory=list)   # (code, quantity)

    def process(self, person, time, ctx) -> bool:
        for code, qty in self.supplies:
            person.record.add_supply(code, qty, time,
                                     source_module=ctx.module_name, source_state=self.name)
        return True


@dataclass
class MultiObservation(State):
    """A panel that groups component observations (Synthea MultiObservation): emits each
    inline component observation. The panel ``codes`` are the grouping code (recorded on
    the components' shared encounter); flat exporters see the individual measurements."""
    codes: list[Code] = field(default_factory=list)
    category: str = ""
    components: list["Observation"] = field(default_factory=list)

    def process(self, person, time, ctx) -> bool:
        for comp in self.components:
            comp.process(person, time, ctx)
        return True


@dataclass
class DiagnosticReport(State):
    """A report bundling result observations (Synthea DiagnosticReport): emits each
    inline component observation (e.g. the analytes of a metabolic panel)."""
    codes: list[Code] = field(default_factory=list)
    category: str = ""
    components: list["Observation"] = field(default_factory=list)

    def process(self, person, time, ctx) -> bool:
        for comp in self.components:
            comp.process(person, time, ctx)
        return True


@dataclass
class Passthrough(State):
    """Imported-but-not-yet-modelled state (e.g. ImagingStudy, Device, SupplyList,
    DiagnosticReport, MultiObservation): parsed for compatibility and executed as a
    no-op so the module runs. Recorded honestly as a known limitation.
    """
    assign_to_attribute: str | None = None
    gmf_type: str = ""

    def process(self, person, time, ctx) -> bool:
        return True


@dataclass
class CallSubmodule(State):
    """Transfer control to a named submodule, then resume at this state's transition
    once the submodule terminates. The submodule runs on the *same* person (shared
    attributes and record). ``submodule`` is the resolved IR ``Module`` (filled at load
    time); the executor special-cases this state, running the submodule across time
    steps via a nested context until it reaches Terminal. If ``submodule`` is unresolved
    the executor treats it as a no-op so the parent module still runs.
    """
    submodule_name: str = ""
    submodule: object = None   # resolved psynthea.ir.module.Module (avoid import cycle)

    def process(self, person, time, ctx) -> bool:  # pragma: no cover - executor handles it
        return True
