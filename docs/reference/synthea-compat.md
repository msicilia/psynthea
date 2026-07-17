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
`CarePlanStart`/`CarePlanEnd`, `Death`, `CallSubmodule`, `MultiObservation`,
`DiagnosticReport`, `Device`/`DeviceEnd`, `ImagingStudy`, `SupplyList`.

Transitions: `direct`, `distributed`, `conditional`, `complex`, `lookup_table`,
`alt_direct`, `type_of_care`. **The only GMF state type not executed is `Physiology`**
(an ODE physiology model), so the module framework is otherwise fully covered.

### Supported logic

`Age`, `Gender`, `Race`, `Socioeconomic Status`, `Date`, `Attribute`,
`Active Condition`/`Active Medication`/`Active Allergy`/`Active CarePlan`,
`Observation`, `Symptom`, `Vital Sign`, `PriorState`, `And`/`Or`/`Not`,
`At Least`/`At Most`, `True`/`False`.

## Submodules (`CallSubmodule`)

`CallSubmodule` is **executed**: control transfers to the named submodule (which runs on
the same patient, across time steps, until it terminates), then resumes at the calling
state. Load a module together with its submodule tree using the submodule-aware loader,
which resolves references (transitively, cycle-safe) from a modules directory:

```python
from psynthea.compat import load_module_with_submodules
module = load_module_with_submodules("modules/copd.json", "modules/")
```

A submodule reference whose file is missing, or a submodule that dead-ends on an
unsupported construct, degrades to a **no-op** (the parent proceeds) rather than hanging.

**42 of 85 stock modules use `CallSubmodule`**, so this substantially widens faithful
coverage. `lookup_table_transition` — the CSV-driven, attribute-matched transition that
stock **medication** submodules use to pick a drug — is also **supported** (resolved
from `<modules_dir>/lookup_tables/`), so those submodules now prescribe.

### Cross-module attributes

A stock disease module often branches on state that *other* modules set — a prior
condition, or a behavioral attribute like `smoker`. Run one module in isolation and
those are unset, so it triggers less often than in Synthea. Two mechanisms close this:

- **Run the ensemble.** `load_all_modules(modules_dir)` loads the whole top-level module
  set (each with submodules + lookup tables resolved); pass them all to one `Generator`
  and attributes set by one module (`atopic`, condition-presence flags, …) are visible
  to the others — exactly as in Synthea. (Running `atopy` alongside `asthma`, for
  example, quadruples asthma's trigger rate.)
- **Keystone hook.** A few attributes are set by Synthea's *Java* lifecycle, not any
  JSON module (`smoker`, `insurance_status`, …). `GeneratorConfig(keystone=fn)` calls
  `fn(person, rng)` per patient to seed them:

  ```python
  def keystone(person, rng):
      person.attributes["smoker"] = rng.random() < 0.15
  GeneratorConfig(..., keystone=keystone)
  ```

### Simulation realism (vitals, mortality, behaviors)

Synthea's Java lifecycle synthesizes physiology and behavior that modules read. psynthea
provides opt-in approximations:

- **Vitals** (`vitals=True` / `--vitals`) — height/weight/BMI/blood-pressure generated
  each step from an age/sex/percentile model, set as vital-sign attributes (so modules
  gating on BMI or blood pressure trigger) and recorded as observations at wellness
  visits. The curves are a plausible approximation, not Synthea's exact CDC charts.
- **Mortality** (`mortality=True` / `--mortality`) — a background age/sex death hazard
  (simple Gompertz); patients may die during simulation. *Caveat:* since psynthea samples
  age-at-end assuming the patient is alive then, enabling mortality skews the realized
  living-age distribution younger — use demographic profiles without mortality when a
  specific living structure is required.
- **Demographics + behaviors** (`GeneratorConfig(keystone=default_keystone)` /
  `--keystone`) — seeds the attributes Synthea's Java lifecycle sets: **race**,
  **ethnicity**, **socioeconomic status** (so modules gating on `Race`/`Socioeconomic
  Status` fire), plus `smoker`/`alcoholic`, at documented default rates. Use
  `keystone.make_keystone(race_dist=…, ses_dist=…, …)` or your own callable to localize.
  *(Names, addresses and other cosmetic demographic detail remain future work.)*

### Wellness encounters

Some modules act *at scheduled wellness visits* (annual checkups) — they use a
`wellness: true` Encounter state that, in Synthea, blocks until the Java lifecycle starts
the next wellness encounter. Enable psynthea's scheduler so those modules advance instead
of spinning:

```python
GeneratorConfig(..., wellness_encounters=True)   # or  psynthea generate --wellness-encounters
```

It schedules wellness visits on an age-based cadence (roughly Synthea's) and `wellness:
true` states attach to them. With it enabled, the previously loop-prone modules (e.g.
Wellness Encounters, Medication Reconciliation, Metabolic Syndrome) run normally — in a
full-ensemble run this took the number of *disabled* modules from ~7 to **0** and, by
gating disease modules on real visits, sharply reduced spurious over-production.

!!! note "Ensemble caveats"
    Running the full library is heavier (~1 s/patient for ~80 modules) and, without a
    [history window](#reproducing-synthea-s-realized-output), produces long records.
    A module that still loops (needing a lifecycle feature psynthea lacks) is **disabled**
    for that patient (recorded in the `_disabled_modules` attribute) rather than aborting
    the run.

## Not fully modeled

- **`Physiology`** — an ODE physiology model (one stock module); imported but not run.
- **`Telemedicine`** — imported as a no-op (an encounter-modality variant).

`MultiObservation` and `DiagnosticReport` now emit their component observations;
`Device`/`DeviceEnd`, `ImagingStudy`, and `SupplyList` emit records (exported to
`devices.csv`, `imaging_studies.csv`, `supplies.csv`).

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

## Reproducing Synthea's realized output

Importing and running a module gives you psynthea's **literal** execution of the GMF
text. That is not the same as reproducing **Java-Synthea's realized rates**, because
Synthea layers execution policy on top of the module — most importantly, it exports only
the **last 10 years** of each record (`exporter.years_of_history`). psynthea keeps the
full simulated life by default, so for a lifetime-risk module its prevalence
*accumulates with age* while Synthea's stays flat.

To reproduce Synthea's output, run under the **compatibility configuration** — three
knobs, each closing a distinct, empirically identified divergence:

```bash
psynthea generate -m appendicitis -p 1000 --seed 1 \
    --years-of-history 10 \        # export window (lifetime accumulation)
    --profile-file census.json \   # population age/sex structure
    --step-days 1                  # fine step (recurrent-episode rate)
```

- **`--years-of-history 10`** — Synthea exports only the last 10 years; without this a
  lifetime-risk condition's prevalence accumulates with age instead of staying flat.
- **`--profile-file`** — match Synthea's population age pyramid (age-gated onset rates
  depend on it).
- **`--step-days 1`** — a fine time step; the default 7-day step *undersamples* short
  recurrent-episode loops (e.g. viral sinusitis: 0.594 at 7 days vs. Java's 0.637,
  which a 1-day step reproduces exactly).

With this configuration, psynthea's realized per-condition prevalence and age-at-onset
match Java-Synthea to within its own seed-to-seed sampling noise for supported modules
(e.g. prevalence MAE 0.0009 on appendicitis at 10 seeds, versus ~0.016 unconfigured).
See the [method paper's cross-engine study](../concepts/overview.md) for the full
evaluation.

!!! note "Which one do you want?"
    Leave `--years-of-history` unset to get psynthea's faithful full-history execution
    of the module (often what you want for a *benchmark*). Set it to `10` (plus matched
    demographics) when the goal is to **mirror Java-Synthea's output**.

## Not modeled

psynthea deliberately omits Synthea's **billing/cost model** (claims, payers, costs).
This has no effect on the clinical record — conditions, medications, observations, and
encounters import and run normally.
