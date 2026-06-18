"""GMF logic / conditions.

Each Logic implements ``test(person, time, ctx) -> bool``. ``person`` and ``ctx``
are duck-typed engine objects (Person, ModuleContext) — the IR deliberately does
not import the engine, so the same IR can be reused by other drivers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from psynthea import _timeutil
from psynthea.terminology import Code


class Logic:
    def test(self, person, time, ctx) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class TrueLogic(Logic):
    def test(self, person, time, ctx) -> bool:
        return True


@dataclass
class FalseLogic(Logic):
    def test(self, person, time, ctx) -> bool:
        return False


@dataclass
class Gender(Logic):
    gender: str

    def test(self, person, time, ctx) -> bool:
        return person.gender == self.gender


@dataclass
class Age(Logic):
    operator: str
    quantity: float
    unit: str

    def test(self, person, time, ctx) -> bool:
        age = _timeutil.age_in(person.birthdate, time, self.unit)
        return _timeutil.compare(age, self.operator, self.quantity)


@dataclass
class Attribute(Logic):
    attribute: str
    operator: str
    value: object = None

    def test(self, person, time, ctx) -> bool:
        current = person.attributes.get(self.attribute)
        return _timeutil.compare(current, self.operator, self.value)


@dataclass
class ActiveCondition(Logic):
    codes: list[Code]

    def test(self, person, time, ctx) -> bool:
        wanted = {c.code for c in self.codes}
        return any(c.code in wanted for c in person.record.active_condition_codes())


@dataclass
class PriorState(Logic):
    name: str

    def test(self, person, time, ctx) -> bool:
        return self.name in ctx.history


@dataclass
class And(Logic):
    conditions: list[Logic] = field(default_factory=list)

    def test(self, person, time, ctx) -> bool:
        return all(c.test(person, time, ctx) for c in self.conditions)


@dataclass
class Or(Logic):
    conditions: list[Logic] = field(default_factory=list)

    def test(self, person, time, ctx) -> bool:
        return any(c.test(person, time, ctx) for c in self.conditions)


@dataclass
class Not(Logic):
    condition: Logic

    def test(self, person, time, ctx) -> bool:
        return not self.condition.test(person, time, ctx)


@dataclass
class DateLogic(Logic):
    operator: str
    year: int

    def test(self, person, time, ctx) -> bool:
        return _timeutil.compare(time.year, self.operator, self.year)


@dataclass
class Race(Logic):
    race: str

    def test(self, person, time, ctx) -> bool:
        return person.attributes.get("race") == self.race


@dataclass
class SocioeconomicStatus(Logic):
    category: str

    def test(self, person, time, ctx) -> bool:
        return person.attributes.get("socioeconomic_status") == self.category


@dataclass
class VitalSign(Logic):
    vital_sign: str
    operator: str
    value: object = None

    def test(self, person, time, ctx) -> bool:
        return _timeutil.compare(person.attributes.get(self.vital_sign), self.operator, self.value)


@dataclass
class Symptom(Logic):
    symptom: str
    operator: str
    value: object = None

    def test(self, person, time, ctx) -> bool:
        return _timeutil.compare(person.symptoms.get(self.symptom, 0), self.operator, self.value)


@dataclass
class ActiveMedication(Logic):
    codes: list[Code]

    def test(self, person, time, ctx) -> bool:
        wanted = {c.code for c in self.codes}
        return any(c.code in wanted for c in person.record.active_medication_codes())


@dataclass
class ActiveAllergy(Logic):
    codes: list[Code]

    def test(self, person, time, ctx) -> bool:
        wanted = {c.code for c in self.codes}
        return any(c.code in wanted for c in person.record.active_allergy_codes())


@dataclass
class ActiveCarePlan(Logic):
    codes: list[Code]

    def test(self, person, time, ctx) -> bool:
        return any(c.code in person.record.careplans for c in self.codes)


@dataclass
class ObservationLogic(Logic):
    codes: list[Code]
    operator: str
    value: object = None

    def test(self, person, time, ctx) -> bool:
        wanted = {c.code for c in self.codes}
        vals = [o.value for o in person.record.observations
                if o.code is not None and o.code.code in wanted and o.value is not None]
        return _timeutil.compare(vals[-1], self.operator, self.value) if vals else False


@dataclass
class AtLeast(Logic):
    minimum: int
    conditions: list[Logic] = field(default_factory=list)

    def test(self, person, time, ctx) -> bool:
        return sum(bool(c.test(person, time, ctx)) for c in self.conditions) >= self.minimum


@dataclass
class AtMost(Logic):
    maximum: int
    conditions: list[Logic] = field(default_factory=list)

    def test(self, person, time, ctx) -> bool:
        return sum(bool(c.test(person, time, ctx)) for c in self.conditions) <= self.maximum
