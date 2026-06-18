"""Unit tests for the IR + executor on hand-built modules (PLAN.md milestone 2)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from psynthea.engine import executor
from psynthea.engine.person import ModuleContext, Person
from psynthea.ir import states as S
from psynthea.ir import transitions as T
from psynthea.ir.module import Module


def _person(birthdate: datetime) -> Person:
    return Person("p0", "F", birthdate, random.Random(1))


def _run_to(module: Module, person: Person, start: datetime, steps: int, step_days: int = 7):
    ctx = ModuleContext(module.name, start)
    person.module_contexts[module.name] = ctx
    t = start
    for _ in range(steps):
        executor.process_module(module, person, t, ctx)
        t += timedelta(days=step_days)
    return ctx


def test_initial_delay_terminal_blocks_then_advances():
    birth = datetime(2000, 1, 1)
    module = Module("delaytest", {
        "Initial": S.Initial("Initial", T.DirectTransition("Wait")),
        "Wait": S.Delay("Wait", T.DirectTransition("Terminal"), low=30, high=30, unit="days"),
        "Terminal": S.Terminal("Terminal"),
    })
    person = _person(birth)
    ctx = _run_to(module, person, birth, steps=2)  # 0d, 7d -> still waiting (<30d)
    assert ctx.current_state == "Wait"
    ctx = _run_to(module, person, birth, steps=10)  # restart from Initial, reach >30d
    assert ctx.current_state == "Terminal"


def test_set_attribute_and_guard():
    birth = datetime(2000, 1, 1)
    from psynthea.ir.logic import Attribute
    module = Module("guardtest", {
        "Initial": S.Initial("Initial", T.DirectTransition("Set")),
        "Set": S.SetAttribute("Set", T.DirectTransition("Gate"), attribute="ready", value=True),
        "Gate": S.Guard("Gate", T.DirectTransition("Terminal"),
                         allow=Attribute("ready", "==", True)),
        "Terminal": S.Terminal("Terminal"),
    })
    person = _person(birth)
    ctx = _run_to(module, person, birth, steps=1)
    assert person.attributes["ready"] is True
    assert ctx.current_state == "Terminal"


def test_distributed_transition_is_deterministic_per_seed():
    birth = datetime(2000, 1, 1)
    module = Module("disttest", {
        "Initial": S.Initial("Initial", T.DistributedTransition([("A", 1.0), ("B", 0.0)])),
        "A": S.Terminal("A"),
        "B": S.Terminal("B"),
    })
    person = _person(birth)
    ctx = _run_to(module, person, birth, steps=1)
    assert ctx.current_state == "A"  # weight 1.0 vs 0.0


def test_loop_guard_raises_on_cycle_without_blocker():
    module = Module("looptest", {
        "Initial": S.Initial("Initial", T.DirectTransition("A")),
        "A": S.Simple("A", T.DirectTransition("Initial")),
    })
    person = _person(datetime(2000, 1, 1))
    ctx = ModuleContext("looptest", datetime(2000, 1, 1))
    try:
        executor.process_module(module, person, datetime(2000, 1, 1), ctx)
        assert False, "expected ModuleLoopError"
    except executor.ModuleLoopError:
        pass
