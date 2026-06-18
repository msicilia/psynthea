"""DSL logic helpers — thin, typed constructors over the IR logic types."""
from __future__ import annotations

from psynthea.ir import logic as L
from psynthea.terminology import Code


def age(operator: str, quantity: float, unit: str = "years") -> L.Age:
    return L.Age(operator=operator, quantity=quantity, unit=unit)


def gender(value: str) -> L.Gender:
    return L.Gender(gender=value)


def attribute(name: str, operator: str, value: object = None) -> L.Attribute:
    return L.Attribute(attribute=name, operator=operator, value=value)


def active_condition(c: Code) -> L.ActiveCondition:
    return L.ActiveCondition(codes=[c])


def prior_state(name: str) -> L.PriorState:
    return L.PriorState(name=name)


def all_of(*conditions: L.Logic) -> L.And:
    return L.And(conditions=list(conditions))


def any_of(*conditions: L.Logic) -> L.Or:
    return L.Or(conditions=list(conditions))


def not_(condition: L.Logic) -> L.Not:
    return L.Not(condition=condition)


def true_() -> L.TrueLogic:
    return L.TrueLogic()


def false_() -> L.FalseLogic:
    return L.FalseLogic()
