"""Ground-truth label emission (ADR-016 capability A).

Because psynthea *is* the data-generating process, it can emit truth that
observable data hides — invaluable for benchmarking phenotyping, temporal/causal
discovery (the recovery study, C2), and more. Three sidecar tables:

- ``gt_provenance.csv``   — which module + GMF state generated each clinical event.
- ``gt_trajectories.csv`` — the full latent state path each patient took through
  each module (incl. states that emit no observable event: Guard/Delay/skips).
- ``gt_phenotypes.csv``   — module-assigned attributes per patient (true cohort
  membership the module intended).

Generative models cannot produce these (they don't know the truth); Synthea has
the truth but doesn't expose it.
"""
from __future__ import annotations

import csv
from pathlib import Path

from psynthea.engine.person import Person


def _iso(value) -> str:
    return value.date().isoformat() if value is not None else ""


def _code(code) -> str:
    return code.code if code is not None else ""


def _attr_value(value) -> str:
    """Stringify an attribute value (often a Condition/Medication entry)."""
    inner = getattr(value, "code", None)
    if inner is not None and getattr(inner, "code", None) is not None:
        return inner.code
    if isinstance(value, (bool, int, float, str)):
        return str(value)
    return type(value).__name__


def export_ground_truth(people: list[Person], out_dir: str | Path) -> dict[str, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    provenance: list[list] = []
    trajectories: list[list] = []
    phenotypes: list[list] = []
    observations: list[list] = []  # true vs observed (after the observation model, cap. D)

    for p in people:
        for e in p.record.encounters:
            provenance.append([p.id, "encounter", _code(e.code), _iso(e.start),
                               e.source_module or "", e.source_state or ""])
        for c in p.record.conditions:
            provenance.append([p.id, "condition", _code(c.code), _iso(c.start),
                               c.source_module or "", c.source_state or ""])
        for m in p.record.medications:
            provenance.append([p.id, "medication", _code(m.code), _iso(m.start),
                               m.source_module or "", m.source_state or ""])
        for o in p.record.observations:
            provenance.append([p.id, "observation", _code(o.code), _iso(o.date),
                               o.source_module or "", o.source_state or ""])

        for module_name, ctx in p.module_contexts.items():
            for step, state in enumerate(ctx.history):
                trajectories.append([p.id, module_name, step, state])

        for attribute, value in p.attributes.items():
            phenotypes.append([p.id, attribute, _attr_value(value)])

        for o in p.record.observations:
            true_v = o.true_value if o.true_value is not None else o.value
            observations.append([p.id, _code(o.code), _iso(o.date),
                                 "" if true_v is None else true_v,
                                 "" if o.value is None else o.value,
                                 "true" if o.missing else "false"])

    def _write(filename: str, header: list[str], rows: list[list]) -> None:
        with (out / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)

    _write("gt_provenance.csv",
           ["PATIENT", "DOMAIN", "CODE", "DATE", "SOURCE_MODULE", "SOURCE_STATE"], provenance)
    _write("gt_trajectories.csv", ["PATIENT", "MODULE", "STEP", "STATE"], trajectories)
    _write("gt_phenotypes.csv", ["PATIENT", "ATTRIBUTE", "VALUE"], phenotypes)
    _write("gt_observations.csv",
           ["PATIENT", "CODE", "DATE", "TRUE_VALUE", "OBSERVED_VALUE", "MISSING"], observations)
    return {
        "gt_provenance.csv": len(provenance),
        "gt_trajectories.csv": len(trajectories),
        "gt_phenotypes.csv": len(phenotypes),
        "gt_observations.csv": len(observations),
    }
