# Ground-truth labels

Because psynthea **is** the data-generating process, it knows everything about how each
record was produced. Ground-truth (GT) labels expose that hidden knowledge — the
**answer key** that real EHR can never give you and that generative models do not have.

Enable GT emission with `--ground-truth` on the CLI, or call
`psynthea.export.export_ground_truth(people, out_dir)` directly. It writes four sidecar
tables alongside your CSV/OMOP output.

## The four tables

| Table | Columns | What it answers |
| --- | --- | --- |
| `gt_provenance.csv` | `PATIENT, DOMAIN, CODE, DATE, SOURCE_MODULE, SOURCE_STATE` | Which module and GMF state produced each clinical event. |
| `gt_trajectories.csv` | `PATIENT, MODULE, STEP, STATE` | The full latent state path each patient took — *including* states that emit no observable event (Guard/Delay/skips). |
| `gt_phenotypes.csv` | `PATIENT, ATTRIBUTE, VALUE` | Module-assigned attributes = the **true** cohort membership the module intended. |
| `gt_observations.csv` | `PATIENT, CODE, DATE, TRUE_VALUE, OBSERVED_VALUE, MISSING` | The clean value vs the value after the [observation model](observation.md), with a missingness flag. |

## Why each one matters

### Provenance → audit attribution
Real EHR can't tell you *why* a code is on a record. With provenance you can check
whether an ETL job, a feature pipeline, or an attribution rule mapped each event to the
right source. If your pipeline claims condition X came from encounter Y, provenance is
the ground truth to verify it against.

### Trajectories → evaluate progression & sequence models
The latent state path is the true disease course, sampled at every step — not just the
events that happened to be recorded. Use it to score disease-progression models,
trajectory mining, and sequence learners against the path the simulator actually took.

### Phenotypes → score computable phenotypes
A computable phenotype (a query/algorithm that decides "does this patient have COPD?")
is normally validated against noisy proxy labels. Here `gt_phenotypes` is the *true*
cohort, so you can compute exact sensitivity, specificity, and PPV.

### Observations → benchmark imputation
`gt_observations` pairs the clean `TRUE_VALUE` with the noisy/missing `OBSERVED_VALUE`.
That is precisely the setup imputation and missing-data methods need: the input they
see and the value they should recover. See the [observation model](observation.md).

## The causal ground-truth graph

For temporal/causal-discovery benchmarks, the module structure also defines a **causal
ground-truth graph**: the union of *necessity* edges (structural dominators — events
that must occur on the way to another) and *modulation* edges (attribute gating that
changes another event's probability). This is distinct from mere observable
reachability, and it is the answer key against which a discovery method's recovered
edges are scored (e.g. causal-edge F1). It is what makes psynthea usable as a benchmark
generator for causal methods, not only a data generator.

!!! note "Fidelity caveat"
    A handful of advanced Synthea state types are imported as no-ops, so imported
    modules can under-produce those event types. Ground-truth labels always reflect
    what the engine *actually* did — they remain exact for whatever was generated.

## Minimal example

```python
from datetime import datetime
from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig
from psynthea.export import export_csv, export_ground_truth

module = load_module_file("path/to/module.json")
people = Generator([module], GeneratorConfig(
    population=200, seed=1, end_date=datetime(2025, 1, 1))).run()

export_csv(people, "out/")
counts = export_ground_truth(people, "out/")   # -> {'gt_provenance.csv': N, ...}
```

## A worked example

The tables below are **real output** from
`psynthea generate -p 8 -m otitis_media -o out/ --seed 3 --ground-truth`
(and a second `gout` run for the observations table). Patient IDs are abbreviated.

### `gt_phenotypes.csv` — true cohort membership

The attributes the module *assigned*. Every listed patient truly has otitis media,
regardless of how noisy the observable record is — this is the answer key for
phenotyping.

```text
PATIENT,         ATTRIBUTE,    VALUE
cd1f8048-…26f5,  otitis_media, 65363002
bf44181d-…eac5,  otitis_media, 65363002
a9afe81f-…6db2,  otitis_media, 65363002
…
```

### `gt_provenance.csv` — which module + state produced each event

For patient `cd1f8048…`:

```text
PATIENT,         DOMAIN,     CODE,       DATE,        SOURCE_MODULE, SOURCE_STATE
cd1f8048-…26f5,  encounter,  185345009,  1957-07-25,  otitis_media,  Ear_Infection_Encounter
cd1f8048-…26f5,  condition,  65363002,   1957-07-25,  otitis_media,  Diagnose_Otitis_Media
cd1f8048-…26f5,  medication, J01CA04,    1957-07-25,  otitis_media,  Prescribe_Amoxicillin
```

Real EHR can't tell you *why* a code is on a record; here you can verify any
ETL/attribution rule against the true source state.

### `gt_trajectories.csv` — the full latent state path

Every step the patient took through the state machine, **including states that emit no
observable event** (`Annual_Check`, `Resolve`, `Cure…`). The observable record only
reflects steps 8–10; the truth shows all 81:

```text
PATIENT,         MODULE,        STEP, STATE
cd1f8048-…26f5,  otitis_media,  0,    Initial
cd1f8048-…26f5,  otitis_media,  1,    Annual_Check
…                                     (7× Annual_Check — no events emitted)
cd1f8048-…26f5,  otitis_media,  8,    Ear_Infection_Encounter   ← becomes the encounter
cd1f8048-…26f5,  otitis_media,  9,    Diagnose_Otitis_Media     ← becomes the condition
cd1f8048-…26f5,  otitis_media,  10,   Prescribe_Amoxicillin     ← becomes the medication
cd1f8048-…26f5,  otitis_media,  11,   End_Encounter
cd1f8048-…26f5,  otitis_media,  12,   Resolve
cd1f8048-…26f5,  otitis_media,  13,   Cure_Otitis_Media
…                                     (81 steps total)
```

### `gt_observations.csv` — clean truth vs noisy observed

From `gout` (code `72514-3` = serum urate) after the [observation model](observation.md) adds
measurement noise and *informative* (MNAR) missingness:

```text
PATIENT,         CODE,     DATE,        TRUE_VALUE, OBSERVED_VALUE, MISSING
4e414351-…61f4,  72514-3,  2002-11-23,  5.92,       6.306…,         false   ← noise added
5cf10991-…e63a,  72514-3,  1987-06-11,  5.96,       (blank),        true    ← dropped, truth kept
5cf10991-…e63a,  72514-3,  1989-11-30,  4.12,       3.792…,         false
4658c533-…dfa8,  72514-3,  1999-12-29,  5.66,       (blank),        true    ← dropped, truth kept
```

The method under test sees only `OBSERVED_VALUE`; you score its reconstruction against
`TRUE_VALUE`. Because drops cluster on higher true values (MNAR), it stresses methods
exactly where they tend to fail.

See the [labeled-benchmark guide](../guides/benchmark.md) for an end-to-end scoring
example.
