"""The DSL builder: ModuleBuilder, StateRef, transition helpers.

Compiles to the IR (psynthea.ir). Validation happens at author/build time —
unknown transition targets, a missing Initial, or invalid codes raise DslError
before the module ever runs.
"""
from __future__ import annotations

from psynthea.ir import states as S
from psynthea.ir import transitions as T
from psynthea.ir.logic import Logic
from psynthea.ir.module import Module
from psynthea.terminology import Code

_UNITS = {"seconds", "minutes", "hours", "days", "weeks", "months", "years"}


class DslError(ValueError):
    """A module authoring error, caught at build time rather than at run time."""


# --------------------------------------------------------------------------- #
# Codes
# --------------------------------------------------------------------------- #
def code(system: str, value: str | int, display: str = "") -> Code:
    """Construct a validated clinical code (author-time check)."""
    if not system or value in (None, ""):
        raise DslError(f"code() needs a non-empty system and code (got {system!r}, {value!r})")
    return Code(system=system, code=str(value), display=display)


# --------------------------------------------------------------------------- #
# Transition branch helpers
# --------------------------------------------------------------------------- #
def dist(*pairs: tuple[float, object]) -> T.DistributedTransition:
    """A weighted distribution: dist((0.3, "A"), (0.7, "B"))."""
    return T.DistributedTransition([(_name(target), float(weight)) for weight, target in pairs])


class _Branch:
    def __init__(self, condition: Logic | None, payload: "str | T.DistributedTransition") -> None:
        self.condition = condition
        self.payload = payload


class _When:
    def __init__(self, condition: Logic) -> None:
        self.condition = condition

    def then(self, target: object) -> _Branch:
        return _Branch(self.condition, _name(target))

    def distributed(self, *pairs: tuple[float, object]) -> _Branch:
        return _Branch(self.condition, dist(*pairs))


def when(condition: Logic) -> _When:
    return _When(condition)


def otherwise(target_or_dist: object) -> _Branch:
    """The default branch (no condition) for conditional()/complex()."""
    payload = target_or_dist if isinstance(target_or_dist, T.DistributedTransition) else _name(target_or_dist)
    return _Branch(None, payload)


def _name(target: object) -> str:
    if isinstance(target, StateRef):
        return target.name
    if isinstance(target, str):
        return target
    raise DslError(f"expected a state name or StateRef, got {target!r}")


# --------------------------------------------------------------------------- #
# State handle
# --------------------------------------------------------------------------- #
class StateRef:
    def __init__(self, builder: "ModuleBuilder", name: str) -> None:
        self._builder = builder
        self.name = name

    def to(self, target: object) -> "StateRef":
        self._set(T.DirectTransition(_name(target)))
        return self

    def distributed(self, *pairs: tuple[float, object]) -> "StateRef":
        self._set(dist(*pairs))
        return self

    def conditional(self, *branches: _Branch) -> "StateRef":
        self._set(T.ConditionalTransition([(b.condition, _branch_target(b)) for b in branches]))
        return self

    def complex(self, *branches: _Branch) -> "StateRef":
        self._set(T.ComplexTransition([(b.condition, b.payload) for b in branches]))
        return self

    def _set(self, transition: T.Transition) -> None:
        self._builder._states[self.name].transition = transition


def _branch_target(b: _Branch) -> str:
    if not isinstance(b.payload, str):
        raise DslError("conditional() branches must be plain targets; use complex() for distributions")
    return b.payload


# --------------------------------------------------------------------------- #
# Module builder
# --------------------------------------------------------------------------- #
class ModuleBuilder:
    def __init__(self, name: str) -> None:
        self.name = name
        self._states: dict[str, S.State] = {}

    def _add(self, state: S.State) -> StateRef:
        if state.name in self._states:
            raise DslError(f"duplicate state {state.name!r}")
        self._states[state.name] = state
        return StateRef(self, state.name)

    # -- state constructors ------------------------------------------------ #
    def initial(self, name: str = "Initial") -> StateRef:
        return self._add(S.Initial(name))

    def terminal(self, name: str = "Terminal") -> StateRef:
        return self._add(S.Terminal(name))

    def simple(self, name: str) -> StateRef:
        return self._add(S.Simple(name))

    def guard(self, name: str, condition: Logic) -> StateRef:
        return self._add(S.Guard(name, allow=condition))

    def delay(self, name: str, *, years: float | None = None, months: float | None = None,
              days: float | None = None, low: float | None = None, high: float | None = None,
              unit: str | None = None) -> StateRef:
        lo, hi, u = _delay_spec(name, years, months, days, low, high, unit)
        return self._add(S.Delay(name, low=lo, high=hi, unit=u))

    def set_attribute(self, name: str, attribute: str, value: object) -> StateRef:
        return self._add(S.SetAttribute(name, attribute=attribute, value=value))

    def encounter(self, name: str, code: Code | None = None,
                  encounter_class: str = "ambulatory", wellness: bool = False) -> StateRef:
        return self._add(S.Encounter(name, codes=[code] if code else [],
                                     encounter_class=encounter_class, wellness=wellness))

    def encounter_end(self, name: str) -> StateRef:
        return self._add(S.EncounterEnd(name))

    def condition_onset(self, name: str, code: Code, assign_to: str | None = None,
                        target_encounter: str | None = None) -> StateRef:
        return self._add(S.ConditionOnset(name, codes=[code], assign_to_attribute=assign_to,
                                          target_encounter=target_encounter))

    def condition_end(self, name: str, code: Code) -> StateRef:
        return self._add(S.ConditionEnd(name, codes=[code]))

    def medication(self, name: str, code: Code, assign_to: str | None = None) -> StateRef:
        return self._add(S.MedicationOrder(name, codes=[code], assign_to_attribute=assign_to))

    def medication_end(self, name: str, code: Code) -> StateRef:
        return self._add(S.MedicationEnd(name, codes=[code]))

    def observation(self, name: str, code: Code, unit: str = "", category: str = "",
                    exact: float | None = None, low: float | None = None,
                    high: float | None = None, attribute: str | None = None) -> StateRef:
        return self._add(S.Observation(name, codes=[code], unit=unit, category=category,
                                       exact_value=exact, range_low=low, range_high=high,
                                       attribute=attribute))

    def death(self, name: str) -> StateRef:
        return self._add(S.Death(name))

    # -- build ------------------------------------------------------------- #
    def build(self) -> Module:
        if "Initial" not in self._states:
            raise DslError(f"module {self.name!r} has no Initial state (call .initial())")
        known = set(self._states)
        for state in self._states.values():
            for target in _targets(state.transition):
                if target not in known:
                    raise DslError(
                        f"state {state.name!r} transitions to unknown state {target!r}")
        return Module(self.name, dict(self._states))


def _delay_spec(name, years, months, days, low, high, unit):
    if years is not None:
        return years, years, "years"
    if months is not None:
        return months, months, "months"
    if days is not None:
        return days, days, "days"
    if low is not None and high is not None and unit:
        if unit not in _UNITS:
            raise DslError(f"delay {name!r}: unknown unit {unit!r}")
        return low, high, unit
    raise DslError(f"delay {name!r}: specify years=/months=/days= or low=,high=,unit=")


def _targets(transition: T.Transition | None) -> list[str]:
    if transition is None:
        return []
    if isinstance(transition, T.DirectTransition):
        return [transition.to]
    if isinstance(transition, T.DistributedTransition):
        return [t for t, _ in transition.choices]
    if isinstance(transition, T.ConditionalTransition):
        return [t for _, t in transition.branches]
    if isinstance(transition, T.ComplexTransition):
        out: list[str] = []
        for _, payload in transition.branches:
            if isinstance(payload, T.DistributedTransition):
                out += [t for t, _ in payload.choices]
            else:
                out.append(payload)
        return out
    return []
