# Generate a labeled benchmark

This guide builds a benchmark you can score an algorithm against, end to end.

## 1. Generate with ground truth

```python
from datetime import datetime
from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig
from psynthea.export import export_csv, export_ground_truth

module = load_module_file("path/to/copd.json")
people = Generator([module], GeneratorConfig(
    population=2000, seed=1, end_date=datetime(2025, 1, 1))).run()

export_csv(people, "bench/")                 # the data an analyst would see
counts = export_ground_truth(people, "bench/")   # the answer key
```

Or from the CLI:

```bash
psynthea generate -p 2000 -m copd -o bench/ --seed 1 --ground-truth
```

## 2. Read the answer key

`bench/gt_phenotypes.csv` lists the true cohort membership (the attributes the module
assigned). Suppose the module assigned `has_copd` to every patient it gave COPD:

```python
import csv

true_cohort = set()
with open("bench/gt_phenotypes.csv") as fh:
    for row in csv.DictReader(fh):
        if row["ATTRIBUTE"] == "has_copd":
            true_cohort.add(row["PATIENT"])
```

## 3. Run the algorithm under test

Here the "algorithm" is a naive computable phenotype over the *observable* data: any
patient with the COPD condition code in `conditions.csv`.

```python
predicted = set()
with open("bench/conditions.csv") as fh:
    for row in csv.DictReader(fh):
        if row["CODE"] == "13645005":         # COPD SNOMED code
            predicted.add(row["PATIENT"])
```

## 4. Score against the truth

```python
tp = len(true_cohort & predicted)
fp = len(predicted - true_cohort)
fn = len(true_cohort - predicted)
precision = tp / (tp + fp) if tp + fp else 0.0
recall    = tp / (tp + fn) if tp + fn else 0.0
print(f"precision={precision:.3f} recall={recall:.3f}")
```

Because `true_cohort` is the *actual* membership the simulator intended — not a noisy
proxy — these numbers are exact, not estimates.

## Variations

- **Imputation benchmark.** Apply the [observation model](../concepts/observation.md) before
  exporting, then score a method's reconstruction against `TRUE_VALUE` in
  `gt_observations.csv`.
- **Causal-discovery benchmark.** Run several interacting modules and score recovered
  edges against the causal ground-truth graph (see
  [ground-truth labels](../concepts/ground-truth.md)).
- **Trajectory / progression benchmark.** Use `gt_trajectories.csv` as the true latent
  path.
