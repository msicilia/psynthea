# psynthea

A Python-native, rule-based **synthetic patient generator**, **compatible with
[Synthea](https://github.com/synthetichealth/synthea) disease modules**.

psynthea executes Synthea's Generic Module Framework — so existing Synthea modules
can be imported and run — and adds a typed **Python DSL** for authoring modules as
code, **ground-truth label** emission, statistical **calibration** of modules to
aggregate (e.g. registry) rates, and **CSV / OMOP CDM** export, with a focus on
European care.

!!! warning "Early release (0.0.x)"
    The API may change between minor versions.

## What makes it different

Most synthetic-EHR tools fall into two camps: **generative** models (learn from real
data, can't tell you the truth they invented) and **Synthea** (rule-based and knows
the truth, but never exposes it). psynthea is rule-based *and* exposes the truth — it
**is** the data-generating process, so it can emit an answer key alongside the data.

That turns synthetic data into a **labeled benchmark**:

- **[Ground-truth labels](concepts/ground-truth.md)** — per-event provenance, latent
  state trajectories, true cohort membership, and clean-vs-observed value pairs.
- **[Calibration](concepts/calibration.md)** — fit a module to a target lifetime
  prevalence and onset age using *aggregate statistics only* — no patient-level data.
- **[Observation model](concepts/observation.md)** — inject labeled noise and
  informative missingness, so the data is also an imputation / robustness benchmark.

## Where to start

| If you want to… | Go to |
| --- | --- |
| Install and generate your first cohort | [Quick start](getting-started/quickstart.md) |
| Understand the design and the use cases | [Why psynthea](concepts/overview.md) |
| Build a labeled benchmark for an algorithm | [Generate a labeled benchmark](guides/benchmark.md) |
| Match a national registry's rates | [Calibrate to registry rates](guides/calibrate.md) |
| Write your own disease module | [Authoring modules](guides/authoring.md) |

## License

MIT.
