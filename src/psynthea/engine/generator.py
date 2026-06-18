"""Population generator — orchestrates people, the clock, and modules."""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from psynthea.demographics import DemographicProfile
from psynthea.engine import executor
from psynthea.engine.person import ModuleContext, Person
from psynthea.ir.module import Module

# Fallback simulation end-date for reproducibility when none is supplied.
REFERENCE_DATE = datetime(2025, 1, 1)
_DAYS_PER_YEAR = 365.25


@dataclass
class GeneratorConfig:
    population: int = 1
    seed: int = 0
    step_days: float = 7.0          # configurable time step (ADR-010), default 7d
    end_date: datetime = REFERENCE_DATE
    min_age: float = 0.0
    max_age: float = 100.0
    # Optional demographic profile (ADR-016 cap. G / Phase-3 demographics): when
    # set, age + sex are sampled from it instead of uniform/50-50.
    profile: DemographicProfile | None = None


class Generator:
    def __init__(self, modules: list[Module], config: GeneratorConfig | None = None) -> None:
        if not modules:
            raise ValueError("Generator needs at least one module")
        self.modules = modules
        self.config = config or GeneratorConfig()

    def _make_person(self, index: int) -> Person:
        cfg = self.config
        # Deterministic per-person RNG derived from the base seed + index.
        seed = (cfg.seed * 2_654_435_761 + index * 40_503) & 0xFFFFFFFFFFFFFFFF
        rng = random.Random(seed)
        pid = str(uuid.UUID(int=rng.getrandbits(128)))
        if cfg.profile is not None:
            age_years, gender = cfg.profile.sample(rng)
        else:
            gender = "M" if rng.random() < 0.5 else "F"
            age_years = rng.uniform(cfg.min_age, cfg.max_age)
        birthdate = cfg.end_date - timedelta(days=age_years * _DAYS_PER_YEAR)
        person = Person(pid, gender, birthdate, rng)
        for module in self.modules:
            person.module_contexts[module.name] = ModuleContext(module.name, birthdate)
        return person

    def _simulate(self, person: Person) -> None:
        cfg = self.config
        step = timedelta(days=cfg.step_days)
        time = person.birthdate
        last_time = time
        while time <= cfg.end_date and person.alive:
            for module in self.modules:
                executor.process_module(module, person, time, person.module_contexts[module.name])
            last_time = time
            time += step
        person.record.close_open(min(last_time, cfg.end_date))

    def generate_one(self, index: int) -> Person:
        """Make and simulate a single person by global index (deterministic)."""
        person = self._make_person(index)
        self._simulate(person)
        return person

    def run(self) -> list[Person]:
        return [self.generate_one(i) for i in range(self.config.population)]
