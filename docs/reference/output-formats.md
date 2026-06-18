# Output formats

Select with `--format` on the CLI, or call the exporter directly
(`psynthea.export.export_csv` / `export_omop` / `export_ground_truth`). Ground-truth
tables work with **either** format.

## `--format csv` (default)

Synthea-like flat tables:

| File | Contents |
| --- | --- |
| `patients.csv` | demographics |
| `encounters.csv` | visits |
| `conditions.csv` | diagnoses |
| `medications.csv` | prescriptions |
| `observations.csv` | measurements |

## `--format omop` — OMOP CDM v5.4

Source-loaded OMOP Common Data Model v5.4 tables:

| File | Contents |
| --- | --- |
| `person.csv` | demographics |
| `observation_period.csv` | coverage windows |
| `visit_occurrence.csv` | encounters |
| `condition_occurrence.csv` | conditions |
| `drug_exposure.csv` | medications |
| `measurement.csv` | observations |

!!! note "Source-loaded, not mapped"
    Standard concept IDs are filled where known; clinical codes are written to the
    `*_source_value` columns with `concept_id = 0`. Map to standard concepts downstream
    with the [OHDSI Athena](https://athena.ohdsi.org/) vocabulary. This keeps psynthea
    free of a bundled vocabulary while remaining a faithful OMOP source.

## `--ground-truth`

Adds four sidecar tables — `gt_provenance`, `gt_trajectories`, `gt_phenotypes`,
`gt_observations` — to the output directory. See
[Ground-truth labels](../concepts/ground-truth.md) for the schema and meaning.
