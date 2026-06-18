"""GMF transitions.

Each Transition implements ``follow(person, time, ctx) -> str | None`` returning
the name of the next state (or ``None`` when there is nowhere to go).
"""
from __future__ import annotations

from dataclasses import dataclass

from psynthea.ir.logic import Logic


class Transition:
    def follow(self, person, time, ctx) -> str | None:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class DirectTransition(Transition):
    to: str

    def follow(self, person, time, ctx) -> str | None:
        return self.to


def _sample_weighted(choices: list[tuple[str, float]], rng) -> str | None:
    """Pick a target name from (name, weight) pairs using the person's RNG."""
    total = sum(w for _, w in choices)
    if total <= 0:
        return choices[0][0] if choices else None
    r = rng.random() * total
    upto = 0.0
    for name, weight in choices:
        upto += weight
        if r < upto:
            return name
    return choices[-1][0]


@dataclass
class DistributedTransition(Transition):
    # list of (target_state, weight)
    choices: list[tuple[str, float]]

    def follow(self, person, time, ctx) -> str | None:
        return _sample_weighted(self.choices, person.rng)


@dataclass
class ConditionalTransition(Transition):
    # list of (condition_or_None, target_state); first matching wins; None == else
    branches: list[tuple[Logic | None, str]]

    def follow(self, person, time, ctx) -> str | None:
        for condition, target in self.branches:
            if condition is None or condition.test(person, time, ctx):
                return target
        return None


@dataclass
class ComplexTransition(Transition):
    # list of (condition_or_None, payload); payload is either a target name (str)
    # or a DistributedTransition to sample from. First matching condition wins.
    branches: list[tuple[Logic | None, "str | DistributedTransition"]]

    def follow(self, person, time, ctx) -> str | None:
        for condition, payload in self.branches:
            if condition is None or condition.test(person, time, ctx):
                if isinstance(payload, DistributedTransition):
                    return payload.follow(person, time, ctx)
                return payload
        return None
