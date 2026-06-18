# Calibrate to registry rates

Goal: produce a cohort whose COPD prevalence matches a published target, starting from
nothing but that aggregate number. See [the concept page](../concepts/calibration.md)
for *why* this needs a search rather than a direct assignment.

## 1. Describe the epidemiology

```python
from psynthea.calibration import EpiSpec
from psynthea.terminology import Code

spec = EpiSpec(
    code=Code("SNOMED-CT", "13645005", "COPD"),
    prevalence=0.06,     # 6% lifetime prevalence — from a registry, by age/sex
    onset_age=55.0,      # mean age at onset, years
)
```

## 2. Calibrate

```python
from datetime import datetime
from psynthea.calibration import calibrate
from psynthea.engine import GeneratorConfig

config = GeneratorConfig(population=2000, seed=1, end_date=datetime(2025, 1, 1))
result = calibrate(spec, config, tol=0.02, max_iter=25)

print(f"target  = {result.target_prevalence:.3f}")
print(f"realized= {result.realized_prevalence:.3f}")
print(f"gate p  = {result.gate_probability:.3f} (vs naive {spec.prevalence:.3f})")
print(f"iters   = {result.iterations}")
```

The realized prevalence lands within `tol` of the target, and `result.gate_probability`
is typically **higher** than the naive `prevalence` — that gap is the age/horizon
correction the bisection discovers.

## 3. Generate from the calibrated module

```python
from psynthea.engine import Generator

people = Generator([result.module], config).run()
```

`result.module` is a normal module — combine it with others, emit
[ground-truth labels](../concepts/ground-truth.md), or export to
[OMOP](../reference/output-formats.md) as usual.

## Tips

- **Use a large enough population.** Realized prevalence is a sample estimate; a small
  cohort makes the bisection noisy. A few thousand patients is a good default.
- **Keep the seed fixed** during calibration so the search is deterministic; change it
  afterwards if you want fresh draws at the same calibrated rate.
- **Self-resolving conditions.** Pass `resolution_days=(low, high)` in the `EpiSpec` to
  add a resolution arm with a delay drawn uniformly in that range.
- **Match the population structure too.** Pair calibration with a
  [`DemographicProfile`](cohorts.md) so both the rate *and* the age/sex pyramid match
  your target population.

## Matching a rate that varies by age

Registries usually publish prevalence **by age band**, not as one number. A single gate
can't reproduce a rising curve — use `calibrate_stratified`, which calibrates one onset
gate per band:

```python
from datetime import datetime
from psynthea.calibration import AgeBand, StratifiedEpiSpec, calibrate_stratified
from psynthea.engine import GeneratorConfig, Generator
from psynthea.terminology import Code

spec = StratifiedEpiSpec(
    code=Code("SNOMED-CT", "13645005", "COPD"),
    bands=[
        AgeBand(40, 55, 0.02),
        AgeBand(55, 70, 0.08),
        AgeBand(70, 200, 0.18),    # open top band: use a large max_age
    ],
)
config = GeneratorConfig(population=1200, seed=1, end_date=datetime(2025, 1, 1),
                         min_age=40, max_age=95)

res = calibrate_stratified(spec, config, tol=0.02)
for bc in res.bands:
    print(f"{int(bc.band.min_age)}-{int(bc.band.max_age)}: "
          f"target {bc.band.prevalence:.3f}, realized {bc.realized_prevalence:.3f}")

people = Generator([res.module], config).run()
```

The cohort **must span every band** — set `min_age`/`max_age` to cover them and use a
population large enough that each band has plenty of patients (a few hundred per band).
See [the concept page](../concepts/calibration.md#age-stratified-calibration) for how it
works and why the oldest band needs the smallest per-year gate.
