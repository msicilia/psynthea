# The observation model

psynthea generates the latent **truth** of each patient's course. The **observation
model** is the process that turns that truth into the **observed** record a researcher
actually sees. It is the natural complement to [ground truth](ground-truth.md): ground
truth is the latent state; the observation model is the (lossy, noisy) map from that
state to what is recorded.

Real EHR has **measurement noise** and — crucially — **informative missingness**: a
value is often missing *because of* what it would have been (the sickest patients skip a
follow-up; an out-of-range result triggers a re-test that replaces it). The observation
model injects these as a post-generation transform, while **keeping the clean value**,
so the result is itself a labeled benchmark.

## Mechanisms

- **MCAR** (missing completely at random) — uniform missingness, the easy case.
- **MNAR** (missing not at random) — missingness probability rises for values past a
  threshold. This is the *informative* case real methods struggle with.
- **Measurement error** — additive Gaussian noise on numeric observations.

## The API

```python
from psynthea.observation import ObservationModel, observe

model = ObservationModel(
    missingness_rate=0.10,    # base P(missing)
    mechanism="MNAR",         # "MCAR" | "MNAR"
    mnar_threshold=140.0,     # values >= threshold go missing more often
    mnar_factor=3.0,          # how much more often, above the threshold
    noise_sigma=2.0,          # Gaussian measurement error (absolute units)
    seed=0,
)
report = observe(people, model)   # observe the true cohort through the model

print(report.n_observations, report.n_noised, report.n_missing)
print(report.missing_rate)
```

`observe` rewrites each observation to its *observed* view (`value` becomes noisy or
`None`, and `missing=True` when dropped) **but preserves the original in
`true_value`**. When you then emit [ground-truth labels](ground-truth.md),
`gt_observations.csv` carries both `TRUE_VALUE` and `OBSERVED_VALUE`.

## Why it matters

Because the truth is retained, the noised/missing cohort *is* an imputation and
robustness benchmark: a method sees only the observed view, and you score its
reconstruction against `true_value`. MNAR in particular lets you measure how methods
degrade exactly where they tend to fail — when missingness is informative.

!!! note "Scope (current limitation)"
    The observation model presently perturbs **numeric observation values only**. It
    does not yet model miscoded conditions, missing encounters, duplicate records, or
    visit-timing irregularity. So it supports imputation and measurement-error
    benchmarks today; coding-error and record-linkage artifacts are future work.
