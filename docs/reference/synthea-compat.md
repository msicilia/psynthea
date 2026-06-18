# Synthea compatibility

psynthea executes Synthea's **Generic Module Framework (GMF)**, so existing Synthea
disease modules can be imported and run unchanged.

## Importing a module

```python
from psynthea.compat import load_module_file

module = load_module_file("path/to/synthea_module.json")
```

The importer parses the GMF JSON into psynthea's [IR](../concepts/modules.md) — the same
IR the [Python DSL](../guides/authoring.md) compiles to — so imported modules are
first-class: combine them, calibrate them, emit ground truth, export to OMOP.

## Coverage

Of the 85 v3.3.0 stock modules, **83 import** and run. The two that don't fail
**cleanly** with a `NotSupportedError` (no crash):

- one module using a `Physiology` / `PhysiologyValue` state (an ODE submodel psynthea
  does not implement);
- one using a by-name medication-reference condition the importer doesn't resolve.

The importer is **fail-loud**: an unsupported construct raises `NotSupportedError`
rather than silently producing wrong data.

### Supported states

`Initial`, `Terminal`, `Simple`, `Guard`, `Delay` (incl. distribution-valued delays),
`SetAttribute`, `Encounter`/`EncounterEnd`, `ConditionOnset`/`ConditionEnd`,
`MedicationOrder`/`MedicationEnd`, `Observation`, `Procedure`, `Immunization`,
`AllergyOnset`/`AllergyEnd`, `Symptom`, `VitalSign`, `Counter`,
`CarePlanStart`/`CarePlanEnd`, `Death`.

### Supported logic

`Age`, `Gender`, `Race`, `Socioeconomic Status`, `Date`, `Attribute`,
`Active Condition`/`Active Medication`/`Active Allergy`/`Active CarePlan`,
`Observation`, `Symptom`, `Vital Sign`, `PriorState`, `And`/`Or`/`Not`,
`At Least`/`At Most`, `True`/`False`.

## Parsed-but-no-op state types

A few advanced state types are **parsed so the module imports**, but run as **no-ops**
(they emit no event): `ImagingStudy`, `Device`/`DeviceEnd`, `SupplyList`,
`DiagnosticReport`, `MultiObservation`, `CallSubmodule`, `Telemedicine`.

!!! warning "Fidelity caveat"
    A module that relies on a no-op type will **under-produce** those event types. The
    module still runs and the rest of its behavior is faithful, but bound your fidelity
    claims accordingly. [Ground-truth labels](../concepts/ground-truth.md) always
    reflect what the engine actually emitted, so they stay exact.

## Exporting back to GMF JSON (bidirectional)

Compatibility runs both ways. Because the DSL and the JSON importer compile to the
*same* IR, a single serializer turns any module — DSL-authored or imported — back into
stock Synthea GMF JSON:

```python
from psynthea.compat import save_module_file, dump_module

save_module_file(my_module, "my_module.json")   # write GMF JSON to disk
d = dump_module(my_module)                       # or get the dict
```

This means you can **author a module in typed Python and hand a Synthea-format JSON file
to a Java-Synthea user** — or round-trip an imported module through the IR.

!!! note "Round-trip guarantee"
    For every construct in the supported subset, `load(dump(m)) == m` at the IR level
    (verified across all vendored stock modules). The export can only emit what the IR
    can hold, so it never invents or loses information the engine had. Note this is an
    *IR-level* identity, not byte-identical JSON: distribution-valued delays, for
    example, are already collapsed to a range at import time.

## Not modeled

psynthea deliberately omits Synthea's **billing/cost model** (claims, payers, costs).
This has no effect on the clinical record — conditions, medications, observations, and
encounters import and run normally.
