"""A Module: a named graph of states with an entry point."""
from __future__ import annotations

from dataclasses import dataclass, field

from psynthea.ir.states import State


@dataclass
class Module:
    name: str
    states: dict[str, State] = field(default_factory=dict)
    remarks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if "Initial" not in self.states:
            raise ValueError(f"Module {self.name!r} has no 'Initial' state")

    def state(self, name: str) -> State:
        return self.states[name]
