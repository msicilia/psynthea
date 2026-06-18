# Why psynthea

## The problem with synthetic EHR today

Synthetic patient data exists to do three things at once: **resemble** real data
(fidelity), **support the same analyses** as real data (utility), and **leak nothing**
about real individuals (privacy). Two families of tools dominate, and each gives up
something:

- **Generative models** learn from real patient records. They can resemble the source
  closely, but (a) they require access to protected data to train, (b) they can leak
  membership of real patients, and (c) they *do not know the truth* they generated —
  there is no answer key, so you cannot use the output to objectively score an
  algorithm.
- **Synthea** is rule-based: it simulates patients from hand-authored disease modules,
  so it needs no real data and has no membership to leak. But Synthea has the truth
  internally and **does not expose it**, and its modules are Java/JSON-centric and
  US-calibrated.

## What psynthea adds

psynthea keeps the rule-based, privacy-by-construction stance (it trains on **no real
patient data**, so there is structurally no membership to infer) and adds the missing
pieces:

1. **It exposes the truth.** Because psynthea is the data-generating process, it emits
   [ground-truth labels](ground-truth.md): which state produced each event, the latent
   trajectory each patient took, true cohort membership, and clean-vs-observed values.
   This is what turns "synthetic data" into a **labeled benchmark with an answer key**.

2. **It calibrates from aggregates.** [Calibration](calibration.md) fits a module's
   free parameters to a target prevalence and onset age using *only* published
   aggregate statistics — the privacy-preserving path to localizing a module to, say, a
   European public-hospital population.

3. **It models the observation process — labeled.** The
   [observation model](observation.md) injects measurement noise and *informative*
   missingness while keeping the clean value, so the noisy output is itself an
   imputation/robustness benchmark.

4. **It's Python-native and Synthea-compatible.** Author modules as typed Python via
   the [DSL](../guides/authoring.md) *or* import existing Synthea GMF JSON, and export
   flat CSV or [OMOP CDM v5.4](../reference/output-formats.md).

## Primary use cases

- **Benchmark phenotyping / cohort definitions** against true membership.
- **Benchmark temporal & causal discovery** against a known causal ground-truth graph.
- **Benchmark imputation / missing-data methods** against retained true values.
- **Stress-test ETL and analytics pipelines** with provenance you can check against.
- **Localize disease epidemiology** to a target population from public statistics.

See [Ground-truth labels](ground-truth.md) and [Calibration](calibration.md) for the
two features that most distinguish psynthea.
