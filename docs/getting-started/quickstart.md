# Quick start

## What is a module?

A **module** is a small state machine describing how a disease unfolds over a
patient's life: states such as encounters, condition onsets, medications and
observations, connected by transitions that may be probabilistic, conditional, or
time-delayed. psynthea ships a few example modules, can [import any Synthea GMF
module](../reference/synthea-compat.md), and lets you [author your own in
Python](../guides/authoring.md).

## Generate a cohort (CLI)

```bash
# generate a cohort from a bundled module (flat CSV output)
psynthea generate -p 100 -m otitis_media -o out/ --seed 1

# export OMOP CDM v5.4 instead, and also emit ground-truth labels
psynthea generate -p 100 -m otitis_media -o omop/ --seed 1 --format omop --ground-truth
```

Generation is **deterministic** given `--seed`: same seed, same cohort.

## Generate a cohort (Python)

```python
from datetime import datetime
from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig

module = load_module_file("path/to/module.json")        # import a Synthea GMF module
people = Generator([module], GeneratorConfig(
    population=100, seed=1, end_date=datetime(2025, 1, 1))).run()

# `people` is a list of Person objects with a `.record` (encounters, conditions,
# medications, observations) and module attributes.
print(len(people), "patients")
```

## Next steps

- [Generate a labeled benchmark](../guides/benchmark.md) — emit the answer key and
  score an algorithm against it.
- [Calibrate to registry rates](../guides/calibrate.md) — make a module's prevalence
  match a published target.
- [Authoring modules](../guides/authoring.md) — write a disease model in the DSL.
