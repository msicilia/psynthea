# Modules & the engine

## Modules are state machines

A psynthea **module** models one disease (or one care process) as a finite state
machine. Each patient walks the module independently over simulated time:

- **States** do something or represent a step: `Initial`, `Guard`, `Delay`,
  `Encounter`, `ConditionOnset`/`ConditionEnd`, `Medication`/`MedicationEnd`,
  `Observation`, `Procedure`, `Immunization`, `Allergy`, `Symptom`, `VitalSign`,
  `CarePlan`, `SetAttribute`, `Death`, `Terminal`.
- **Transitions** connect states and decide where the patient goes next. They may be
  direct, **probabilistic** (distributed), **conditional** (logic-guarded), or
  **complex** (a guarded list of probabilistic branches).

States can **assign an attribute** to the patient (e.g. `assign_to="has_copd"`). Those
attributes are the true cohort labels that show up in
[ground-truth phenotypes](ground-truth.md), and the gates that
[calibration](calibration.md) tunes.

## The intermediate representation (IR)

Both the [Synthea JSON importer](../reference/synthea-compat.md) and the
[Python DSL](../guides/authoring.md) compile to the **same IR** (`psynthea.ir`). A DSL
module and its JSON equivalent are therefore interchangeable, and the engine only ever
sees the IR. This is what lets psynthea be "Synthea-compatible" without reimplementing
Synthea's runtime semantics twice.

## The engine

```python
from datetime import datetime
from psynthea.engine import Generator, GeneratorConfig

config = GeneratorConfig(
    population=100,                 # number of patients
    seed=1,                         # deterministic given the seed
    step_days=7.0,                  # simulation time step
    end_date=datetime(2025, 1, 1),  # simulate up to this date
    min_age=0.0, max_age=100.0,     # age bounds at end_date
)
people = Generator([module_a, module_b], config).run()
```

- **Multiple modules** run concurrently on each patient — comorbidities and shared
  attributes interact, which is exactly what makes confounding (and the causal
  ground-truth graph) interesting.
- **Time advances in fixed steps** of `step_days`; `Delay` states schedule future
  transitions.
- **Determinism**: the same `(modules, config)` always yields the same cohort. This is
  the basis of reproducible benchmarks and of the bisection used in calibration.

Each returned `Person` has a `.record` (encounters, conditions, medications,
observations, procedures, immunizations, allergies), `.attributes`, and per-module
context including the **state history** used to emit trajectories.

To match a real population's age/sex structure, pass a
[`DemographicProfile`](../guides/cohorts.md); to force rare subgroups, use
[conditional generation](../guides/cohorts.md).
