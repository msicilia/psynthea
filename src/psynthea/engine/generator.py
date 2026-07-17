"""Population generator — orchestrates people, the clock, and modules."""
from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from psynthea import mortality as _mortality
from psynthea import vitals as _vitals
from psynthea.demographics import DemographicProfile
from psynthea.engine import executor
from psynthea.engine.person import ModuleContext, Person
from psynthea.ir.module import Module
from psynthea.terminology import Code

# Fallback simulation end-date for reproducibility when none is supplied.
REFERENCE_DATE = datetime(2025, 1, 1)
_DAYS_PER_YEAR = 365.25

# Scheduled wellness visits (approximating Synthea's EncounterModule cadence by age),
# so modules that wait for the next annual checkup advance instead of spinning.
_WELLNESS_CODE = Code("SNOMED-CT", "162673000", "General examination of patient (procedure)")


def _wellness_interval_years(age: float) -> float:
    if age < 1:
        return 0.25
    if age < 3:
        return 0.5
    if age < 20:
        return 1.0
    if age < 40:
        return 3.0
    if age < 50:
        return 2.0
    return 1.0


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
    # Optional keystone hook: ``keystone(person, rng)`` seeds attributes that Synthea's
    # Java lifecycle sets but no JSON module does (e.g. smoker, insurance_status), so
    # modules gating on them trigger. Called once per patient before simulation.
    keystone: Callable[[Person, random.Random], None] | None = None
    # Schedule periodic wellness encounters (age-based cadence) that `wellness: true`
    # Encounter states attach to. Off by default (standalone modules create encounters
    # on the spot); enable to run modules that wait for scheduled wellness visits.
    wellness_encounters: bool = False
    # Generate physiological vital signs (height/weight/BMI/blood pressure) each step so
    # modules can read them; vitals are also recorded as observations at wellness visits.
    vitals: bool = False
    # Apply a background age/sex death hazard (patients may die during simulation).
    mortality: bool = False


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
        if cfg.vitals:
            _vitals.assign_baseline(person, rng)
            _vitals.update(person, birthdate)
        if cfg.keystone is not None:
            cfg.keystone(person, rng)
        for module in self.modules:
            person.module_contexts[module.name] = ModuleContext(module.name, birthdate)
        return person

    def _simulate(self, person: Person) -> None:
        cfg = self.config
        step = timedelta(days=cfg.step_days)
        time = person.birthdate
        last_time = time
        # A module that loops with no progress (typically one relying on Synthea's Java
        # lifecycle, e.g. scheduled wellness encounters) is disabled for this patient
        # rather than aborting the whole ensemble; recorded for honesty.
        disabled: set[str] = set()
        next_wellness = person.birthdate if cfg.wellness_encounters else None
        person.wellness_managed = cfg.wellness_encounters
        while time <= cfg.end_date and person.alive:
            if cfg.mortality:
                age = (time - person.birthdate).days / _DAYS_PER_YEAR
                if _mortality.died_this_step(person, age, cfg.step_days, person.rng):
                    person.die(time)
                    break
            if cfg.vitals:
                _vitals.update(person, time)
            wellness_enc = None
            if next_wellness is not None and time >= next_wellness:
                wellness_enc = person.record.start_encounter(
                    _WELLNESS_CODE, time, "wellness", source_module="wellness")
                person.wellness_active = True
                person.wellness_encounter_id = wellness_enc.id
                if cfg.vitals:
                    _vitals.emit_observations(person, time)
                age = (time - person.birthdate).days / _DAYS_PER_YEAR
                next_wellness = time + timedelta(
                    days=_wellness_interval_years(age) * _DAYS_PER_YEAR)
            else:
                person.wellness_active = False

            for module in self.modules:
                if module.name in disabled:
                    continue
                try:
                    executor.process_module(module, person, time,
                                            person.module_contexts[module.name])
                except executor.ModuleLoopError:
                    disabled.add(module.name)

            if wellness_enc is not None:
                if wellness_enc.stop is None:
                    wellness_enc.stop = time
                if person.record.current_encounter is wellness_enc:
                    person.record.current_encounter = None
                person.wellness_active = False
            last_time = time
            time += step
        if disabled:
            person.attributes.setdefault("_disabled_modules", set()).update(disabled)
        person.record.close_open(min(last_time, cfg.end_date))

    def generate_one(self, index: int) -> Person:
        """Make and simulate a single person by global index (deterministic)."""
        person = self._make_person(index)
        self._simulate(person)
        return person

    def run(self) -> list[Person]:
        return [self.generate_one(i) for i in range(self.config.population)]
