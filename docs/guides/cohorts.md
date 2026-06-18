# Conditional & cohort generation

Two related needs: making the cohort's **age/sex structure** match a real population,
and **oversampling a rare subgroup** so you have enough cases to analyze.

## Match a population's age/sex structure

A `DemographicProfile` is a weighted set of (age-band, sex) strata — the shape a
national statistics office publishes (e.g. a population pyramid). Attach it to the
generator config and the cohort is sampled to match it instead of the uniform default.

```python
from psynthea.demographics import DemographicProfile

# rows of (min_age, max_age, weight_male, weight_female)
profile = DemographicProfile.from_bands([
    (0,  18, 9.0, 8.6),
    (18, 40, 13.0, 12.5),
    (40, 65, 17.0, 17.4),
    (65, 100, 9.0, 12.0),
])
```

Pass it via the generator config's `profile` field (see
[`GeneratorConfig`](../concepts/modules.md)); weights need not sum to 1.

## Oversample a rare cohort

`generate_matching` keeps simulating patients (deterministically) until *N* satisfy a
predicate — invaluable when the subgroup you care about is rare under the natural rate.

```python
from datetime import datetime
from psynthea.cohort import generate_matching, has_condition, has_attribute
from psynthea.engine import GeneratorConfig

config = GeneratorConfig(population=1, seed=1, end_date=datetime(2025, 1, 1))

cohort = generate_matching(
    [module], config,
    predicate=has_condition("13645005"),   # or has_attribute("has_copd")
    n_target=500,
)

print(len(cohort.people), "matched")
print(cohort.attempts, "patients simulated")
print(f"acceptance rate = {cohort.acceptance_rate:.3f}")
```

- `has_condition(code)` and `has_attribute(name)` are built-in predicates; any
  `Callable[[Person], bool]` works.
- A `max_factor` (default 200) caps attempts at `n_target * max_factor` so an
  impossible predicate can't loop forever — you get back whatever matched, plus the
  attempt count, so you can detect that case.

The **acceptance rate** doubles as a cheap estimate of the subgroup's natural
prevalence under the module(s).
