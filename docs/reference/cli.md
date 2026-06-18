# CLI reference

psynthea installs two commands:

```bash
psynthea generate [options]    # generate a synthetic cohort
psynthea export   [options]    # write a module back to Synthea GMF JSON
```

## `generate`

Generate a synthetic cohort from one or more modules.

| Option | Default | Description |
| --- | --- | --- |
| `-p`, `--population N` | `1` | Number of patients to generate. |
| `-s`, `--seed N` | `0` | Random seed. Generation is deterministic given the seed. |
| `-m`, `--module NAME` | — | Module name within `--modules-dir` (repeatable). |
| `--module-file PATH` | — | Path to a GMF JSON module file (repeatable). |
| `-d`, `--modules-dir DIR` | bundled modules | Directory holding `<name>.json` modules. |
| `-o`, `--output DIR` | `out` | Output directory. |
| `--format {csv,omop}` | `csv` | Flat CSV or OMOP CDM v5.4 (source-loaded). |
| `--ground-truth` | off | Also emit ground-truth label tables. |
| `--step-days FLOAT` | `7.0` | Simulation time step, in days. |
| `--min-age FLOAT` | `0.0` | Minimum patient age (years) at the end date. |
| `--max-age FLOAT` | `100.0` | Maximum patient age (years) at the end date. |
| `--profile-file PATH` | — | JSON demographic profile to match a target age/sex structure (overrides `--min/max-age`). |
| `--end-date YYYY-MM-DD` | today | Simulation end date. |

The `--profile-file` JSON is a list of `(min_age, max_age, weight_male, weight_female)`
bands — the shape a national statistics office publishes (see
[Conditional & cohort generation](../guides/cohorts.md)):

```json
{"bands": [[0, 18, 9.0, 8.6], [18, 40, 13, 12.5], [40, 65, 17, 17.4], [65, 100, 9, 12]]}
```

At least one of `-m` / `--module-file` is required.

## Examples

```bash
# 100 patients from a bundled module, CSV
psynthea generate -p 100 -m otitis_media -o out/ --seed 1

# from an arbitrary GMF JSON file, OMOP output + ground truth
psynthea generate -p 100 --module-file ./copd.json -o omop/ --format omop --ground-truth

# multiple modules run together (comorbidities interact)
psynthea generate -p 500 -m copd -m asthma -o out/ --seed 7

# from your own modules directory
psynthea generate -p 50 -d ./my_modules -m diabetes -o out/
```

The command prints the patient count, the format, the output path, and a row count per
written file.

## `export`

Write a single module back to Synthea GMF JSON (the [bidirectional
bridge](synthea-compat.md#exporting-back-to-gmf-json-bidirectional)). Useful to hand a
DSL- or psynthea-authored module to a Java-Synthea user, or to re-export an imported
module through the IR.

| Option | Default | Description |
| --- | --- | --- |
| `-m`, `--module NAME` | — | Module name within `--modules-dir`. |
| `--module-file PATH` | — | A GMF JSON file to re-export through the IR. |
| `-d`, `--modules-dir DIR` | bundled modules | Directory holding `<name>.json` modules. |
| `-o`, `--output FILE` | *(required)* | Output `.json` file path. |

Exactly **one** module must be resolved.

```bash
# export a bundled module to Synthea GMF JSON
psynthea export -m otitis_media -o otitis_media.json

# round-trip an arbitrary module through the IR
psynthea export --module-file ./copd.json -o ./copd.roundtrip.json
```
