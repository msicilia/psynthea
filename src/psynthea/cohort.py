"""Conditional / controllable cohort generation (ADR-016 capability G).

Generate cohorts that satisfy a constraint — most usefully **rare-cohort
oversampling**: keep simulating patients until N of them match a predicate (e.g.
have a given condition). Combined with a ``DemographicProfile`` (age/sex targeting)
this covers the "conditional generation" desideratum the literature flags as
critical for subgroup analyses.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from psynthea.engine.generator import Generator, GeneratorConfig
from psynthea.engine.person import Person
from psynthea.ir.module import Module

Predicate = Callable[[Person], bool]


@dataclass
class MatchedCohort:
    people: list[Person] = field(default_factory=list)
    attempts: int = 0          # patients simulated to reach the target
    target: int = 0

    @property
    def acceptance_rate(self) -> float:
        return len(self.people) / self.attempts if self.attempts else 0.0


def has_condition(code_str: str) -> Predicate:
    return lambda p: any(c.code is not None and c.code.code == code_str
                         for c in p.record.conditions)


def has_attribute(name: str) -> Predicate:
    return lambda p: p.attributes.get(name) not in (None, False)


def generate_matching(modules: list[Module], config: GeneratorConfig, predicate: Predicate,
                      n_target: int, *, max_factor: int = 200) -> MatchedCohort:
    """Simulate patients (deterministically) until ``n_target`` match ``predicate``.

    ``max_factor`` caps attempts at ``n_target * max_factor`` so an impossible
    predicate can't loop forever; the cohort is returned with whatever matched.
    """
    gen = Generator(modules, config)
    matched: list[Person] = []
    attempts = 0
    cap = n_target * max_factor
    while len(matched) < n_target and attempts < cap:
        person = gen.generate_one(attempts)
        if predicate(person):
            matched.append(person)
        attempts += 1
    return MatchedCohort(people=matched, attempts=attempts, target=n_target)
