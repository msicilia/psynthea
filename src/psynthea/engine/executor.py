"""Module executor — runs one module for one person at one time step.

Mirrors Synthea's ``Module.process`` loop: advance through states (following
transitions) until a state blocks (returns False) or the module reaches a state
with no outgoing transition. Per-person state lives in the ModuleContext.
"""
from __future__ import annotations

from datetime import datetime

from psynthea.engine.person import ModuleContext, Person
from psynthea.ir.module import Module

# Guards against a malformed module looping forever within a single time step.
_MAX_ITERATIONS_PER_STEP = 10_000


class ModuleLoopError(RuntimeError):
    pass


def process_module(module: Module, person: Person, time: datetime, ctx: ModuleContext) -> None:
    iterations = 0
    while True:
        iterations += 1
        if iterations > _MAX_ITERATIONS_PER_STEP:
            raise ModuleLoopError(
                f"Module {module.name!r} exceeded {_MAX_ITERATIONS_PER_STEP} state "
                f"transitions in one step (stuck at {ctx.current_state!r}); "
                f"likely a cycle with no Delay/Guard."
            )

        state = module.states[ctx.current_state]
        if not state.process(person, time, ctx):
            return  # blocked — resume here next step

        next_name = state.transition.follow(person, time, ctx) if state.transition else None
        if next_name is None:
            return  # nowhere to go (e.g. a terminal-like leaf)

        ctx.history.append(ctx.current_state)
        ctx.current_state = next_name
        ctx.entered_time = time
