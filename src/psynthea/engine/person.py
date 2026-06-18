"""Person and per-module execution context."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from psynthea.engine.record import HealthRecord


@dataclass
class ModuleContext:
    """Per-person, per-module execution state (the IR states stay stateless)."""
    module_name: str
    entered_time: datetime
    current_state: str = "Initial"
    history: list[str] = field(default_factory=list)
    scratch: dict = field(default_factory=dict)


class Person:
    def __init__(self, person_id: str, gender: str, birthdate: datetime, rng: random.Random) -> None:
        self.id = person_id
        self.gender = gender
        self.birthdate = birthdate
        self.rng = rng
        self.attributes: dict = {}
        self.symptoms: dict = {}          # symptom name -> value (0-100), GMF Symptom state
        self.record = HealthRecord(person_id)
        self.alive = True
        self.deathdate: datetime | None = None
        self.module_contexts: dict[str, ModuleContext] = {}

    def die(self, time: datetime) -> None:
        if self.alive:
            self.alive = False
            self.deathdate = time
