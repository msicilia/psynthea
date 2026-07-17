"""Module executor — runs one module for one person at one time step.

Mirrors Synthea's ``Module.process`` loop: advance through states (following
transitions) until a state blocks (returns False) or the module reaches a state
with no outgoing transition. Per-person state lives in the ModuleContext.
"""
from __future__ import annotations

from datetime import datetime

from psynthea.engine.person import ModuleContext, Person
from psynthea.ir.module import Module
from psynthea.ir.states import CallSubmodule, Delay, Guard

# Guards against a malformed module looping forever within a single time step.
_MAX_ITERATIONS_PER_STEP = 10_000


class ModuleLoopError(RuntimeError):
    pass


def _run_submodule(state: CallSubmodule, person: Person, time: datetime,
                   ctx: ModuleContext) -> bool:
    """Advance ``state``'s submodule for this step; return True once it has terminated.

    A fresh nested context is created on entry and kept (in the parent scratch) across
    steps while the submodule blocks; it is discarded when the submodule reaches
    Terminal, so a later re-entry starts the submodule over.
    """
    submodule: Module | None = state.submodule
    if submodule is None:
        return True  # unresolved submodule -> no-op, let the parent proceed

    key = f"{state.name}::submodule"
    subctx = ctx.scratch.get(key)
    if subctx is None:
        subctx = ModuleContext(module_name=submodule.name, entered_time=time)
        ctx.scratch[key] = subctx

    process_module(submodule, person, time, subctx)

    # After a step, the submodule rests at a blocking state (Delay/Guard, still
    # waiting) or has stopped (Terminal, or a dead-end where an unsupported construct
    # left a state with no viable transition). Only Delay/Guard mean "resume later";
    # anything else lets the parent proceed, so an unsupported submodule construct
    # degrades to a no-op rather than hanging the caller.
    cur = submodule.states.get(subctx.current_state)
    if isinstance(cur, (Delay, Guard)):
        return False
    ctx.scratch.pop(key, None)
    return True


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
        if isinstance(state, CallSubmodule):
            if not _run_submodule(state, person, time, ctx):
                return  # submodule still running — resume here next step
        elif not state.process(person, time, ctx):
            return  # blocked — resume here next step

        next_name = state.transition.follow(person, time, ctx) if state.transition else None
        if next_name is None:
            return  # nowhere to go (e.g. a terminal-like leaf)

        ctx.history.append(ctx.current_state)
        ctx.current_state = next_name
        ctx.entered_time = time
