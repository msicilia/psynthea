# Authoring modules (Python DSL)

Instead of hand-writing GMF JSON you can author modules as typed Python that is
validated at build time and runs on the same engine. The DSL compiles to the same
[IR](../concepts/modules.md) as the JSON importer, so a DSL module and its JSON
equivalent are interchangeable.

## A complete module

```python
from psynthea.dsl import ModuleBuilder, code, when, otherwise, age

b = ModuleBuilder("otitis_media")
b.initial().to("Annual_Check")

# once a year, children under 8 have a 30% chance of an ear infection
b.delay("Annual_Check", years=1).complex(
    when(age("<", 8, "years")).distributed((0.3, "Visit"), (0.7, "Annual_Check")),
    otherwise("Annual_Check"),
)
b.encounter("Visit", code("SNOMED-CT", "185345009", "Encounter for symptom")).to("Diagnose")
b.condition_onset("Diagnose", code("SNOMED-CT", "65363002", "Otitis media"),
                  assign_to="otitis_media").to("Prescribe")
b.medication("Prescribe", code("ATC", "J01CA04", "Amoxicillin")).to("Annual_Check")

module = b.build()   # raises DslError on unknown transitions, missing Initial, or bad codes
```

## States

Each builder method adds a state and returns a `StateRef` you attach a transition to:

| Method | State |
| --- | --- |
| `initial()` / `terminal()` | entry / sink |
| `simple(name)` | pass-through (for branching) |
| `guard(name, condition)` | wait until a condition holds |
| `delay(name, years=/months=/days=/low=,high=,unit=)` | wait a fixed or random time |
| `set_attribute(name, attribute, value)` | set a patient attribute |
| `encounter(name, code)` / `encounter_end(name)` | open / close an encounter |
| `condition_onset(name, code, assign_to=)` / `condition_end(name, code)` | condition on/off |
| `medication(name, code, assign_to=)` / `medication_end(name, code)` | medication on/off |
| `observation(name, code, unit=, category=, ...)` | record an observation |
| `death(name)` | patient death |

`assign_to=` records the condition/medication as a patient attribute — that attribute
becomes the true label in [`gt_phenotypes`](../concepts/ground-truth.md).

## Transitions

Off any `StateRef`:

```python
ref.to("Next")                                   # direct
ref.distributed((0.3, "A"), (0.7, "B"))          # probabilistic
ref.conditional(when(cond).then("A"), otherwise("B"))   # first matching condition
ref.complex(when(cond).distributed((0.3, "A"), (0.7, "B")), otherwise("B"))  # guarded + probabilistic
```

## Logic helpers

`when(...)` takes a condition built from `psynthea.dsl`:

```python
from psynthea.dsl import (age, gender, attribute, active_condition,
                          prior_state, all_of, any_of, not_, true_, false_)

when(all_of(age(">=", 18, "years"), gender("F")))
when(any_of(active_condition(code("SNOMED-CT", "13645005")), attribute("smoker", "==", True)))
when(not_(prior_state("Vaccinated")))
```

## Build-time validation

`b.build()` raises `DslError` if a transition points at an undefined state, there is no
`Initial`, or a code is malformed — so authoring mistakes are caught before you ever
run a simulation. Test modules like any other Python.

## Export to Synthea GMF JSON

A DSL module isn't locked into psynthea: you can write it out as a stock Synthea
GMF JSON file (e.g. to share with a Java-Synthea user). See
[Synthea compatibility](../reference/synthea-compat.md#exporting-back-to-gmf-json-bidirectional).

```python
from psynthea.compat import save_module_file

save_module_file(module, "otitis_media.json")
```
