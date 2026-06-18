# Calibration

A module encodes a **mechanism** — the state machine of how a disease unfolds — but its
raw transition probabilities are often arbitrary or US-derived. **Calibration** fits
those free parameters so the generated cohort matches a **target aggregate statistic**,
using only published numbers and **no patient-level data**.

## Why you can't just set probability = prevalence

It is tempting to set the onset gate's probability equal to the target lifetime
prevalence. That undershoots, because the *realized* prevalence depends on the cohort's
age structure and the simulation horizon: patients younger than the onset age never
reach the gate, so they can never acquire the condition. The gate probability that
*yields* a target prevalence is therefore higher than the target itself.

psynthea finds the right gate probability by **bisection**: realized prevalence is
monotonic in the gate probability, and generation is deterministic given the seed, so a
deterministic binary search converges to the value that hits the target within
tolerance.

## The API

```python
from datetime import datetime
from psynthea.calibration import EpiSpec, calibrate
from psynthea.engine import GeneratorConfig
from psynthea.terminology import Code

spec = EpiSpec(
    code=Code("SNOMED-CT", "13645005", "COPD"),
    prevalence=0.06,        # target lifetime prevalence (e.g. from a registry)
    onset_age=55.0,         # target mean age at onset, years
    resolution_days=None,   # set (low, high) for a self-resolving condition
)

config = GeneratorConfig(population=2000, seed=1, end_date=datetime(2025, 1, 1))
result = calibrate(spec, config, tol=0.02, max_iter=25)

print(result.target_prevalence)    # 0.06
print(result.realized_prevalence)  # ~0.06 (within tol)
print(result.gate_probability)     # the value that achieves it
print(result.iterations)
module = result.module             # ready to generate with
```

`EpiSpec` is exactly the shape a national registry publishes (a prevalence and a mean
onset age, by age/sex). `build_module(spec)` constructs a parametric module from it;
`calibrate(...)` returns a `CalibrationResult` whose `.module` realizes the target.

## Why it matters

1. **Localize from public statistics.** Make a stock module match a European registry's
   prevalence and onset-age distribution without ever touching protected records — the
   core of the public-hospital localization story.
2. **Realistic *and* labeled.** Calibration only tunes parameters of a mechanism
   psynthea controls, so you keep the full [ground-truth answer key](ground-truth.md)
   while the marginal rates look like the real target. Real data cannot give you both.
3. **Honest, testable fidelity claims.** Set a target, calibrate, regenerate, and check
   the recovered rate falls inside an equivalence margin. This "set-target →
   calibrate → recover" loop is the basis of psynthea's calibration experiments.

## What a single gate can and can't match

A single gate matches **one** number — an overall lifetime prevalence. It does *not*
need to know the rate at each age: because the calibrator runs the real simulation and
*measures* the output, the "young people dilute the rate" effect is handled
automatically by the cohort's own age mix. You only supply the overall rate and roughly
when onset begins.

What one gate **cannot** do is reproduce a prevalence **curve** — a different rate at 50
vs 70 vs 80. That is a *shape*, and one dial only sets a level. Registries, though,
almost always publish rates **by age band**. For that, use age-stratified calibration.

## Age-stratified calibration

`calibrate_stratified` gives each age band its own yearly onset gate and calibrates them
so the **cross-sectional prevalence within each band** matches its target.

```python
from datetime import datetime
from psynthea.calibration import AgeBand, StratifiedEpiSpec, calibrate_stratified
from psynthea.engine import GeneratorConfig
from psynthea.terminology import Code

spec = StratifiedEpiSpec(
    code=Code("SNOMED-CT", "13645005", "COPD"),
    bands=[                       # rates published by age band, youngest first
        AgeBand(40, 55, 0.02),
        AgeBand(55, 70, 0.08),
        AgeBand(70, 200, 0.18),   # open-ended top band: large max_age
    ],
)
# the cohort must span every band — set the age range and a big enough population
config = GeneratorConfig(population=1200, seed=1, end_date=datetime(2025, 1, 1),
                         min_age=40, max_age=95)

res = calibrate_stratified(spec, config, tol=0.02)
for bc in res.bands:
    print(bc.band.min_age, bc.realized_prevalence, bc.gate_probability)
module = res.module
```

Real output reproduces the rising curve (targets 0.02 / 0.08 / 0.18):

```text
     band   target  realized  gate/yr
40-55       0.020    0.015     0.004
55-70       0.080    0.092     0.008
70-200      0.180    0.194     0.002
```

!!! note "Why the oldest band needs the *smallest* per-year gate"
    By age 70 a patient has already had many years to acquire the disease in the earlier
    bands, so that **carryover** does most of the work — only a small extra per-year
    hazard is needed to reach 18%. Calibration discovers this automatically.

How it works: each band's prevalence depends only on that band's gate and the *younger*
ones (older gates change only older prevalence), so the bands are calibrated
**youngest-first by bisection**, each solved while earlier bands stay fixed. Requires
enough patients spanning every band.

See the [calibration guide](../guides/calibrate.md) for a worked, end-to-end example.
