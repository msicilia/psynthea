# Evaluate fidelity, utility, privacy

The synthetic-data trilemma — **fidelity** (does it resemble real data?), **utility**
(does it support the same analyses?), **privacy** (does it leak individuals?) — is
bundled in `psynthea.evaluation`, dependency-free. Each function compares a psynthea
cohort against a **reference** cohort (a real holdout in practice).

```python
from psynthea.evaluation import fidelity_report, utility_agreement, privacy_report
```

## Fidelity — statistical resemblance

```python
report = fidelity_report(synthetic, reference)
report["prevalence_mae"]          # mean abs error of per-condition prevalence
report["per_code_prevalence"]     # {code: {"synthetic": .., "reference": ..}}
report["female_fraction_diff"]
report["mean_birth_year_diff"]
```

## Utility — same conclusion?

Apply the *same* analysis to both cohorts and compare the result (TSTR-style, no ML
dependency). The statistic is any `Callable[[list[Person]], float]`:

```python
def copd_prevalence(people):
    have = sum(any(c.code and c.code.code == "13645005" for c in p.record.conditions)
               for p in people)
    return have / len(people) if people else 0.0

agree = utility_agreement(synthetic, reference, copd_prevalence)
agree["synthetic"], agree["reference"], agree["abs_diff"], agree["rel_diff"]
```

## Privacy — distance to closest record

```python
priv = privacy_report(synthetic, reference)
priv["dcr_min"]                 # min distance to any reference record
priv["dcr_mean"]
priv["exact_feature_matches"]   # synthetic records identical (in features) to a real one
```

!!! info "Membership inference is not applicable"
    psynthea trains on **no real patient data**, so there is no membership to infer —
    a structural privacy advantage over generative models, and worth stating
    explicitly when you report results. `privacy_report` notes this in its output.
