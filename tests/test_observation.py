"""Tests for the observation model (ADR-016 capability D)."""
from __future__ import annotations

from datetime import datetime

from psynthea.dsl import ModuleBuilder, code
from psynthea.engine import Generator, GeneratorConfig
from psynthea.observation import ObservationModel, observe


def _bp_module():
    """A module that records an annual systolic-BP observation (90–180 mmHg)."""
    b = ModuleBuilder("vitals")
    b.initial().to("Visit")
    b.encounter("Visit", code("SNOMED-CT", "185345009", "visit")).to("BP")
    b.observation("BP", code("LOINC", "8480-6", "SBP"), unit="mmHg", low=90, high=180).to("EndV")
    b.encounter_end("EndV").to("Wait")
    b.delay("Wait", years=1).to("Visit")
    return b.build()


def _cohort(n=200, max_age=40):
    cfg = GeneratorConfig(population=n, seed=4, end_date=datetime(2025, 1, 1), max_age=max_age)
    return Generator([_bp_module()], cfg).run()


def test_mcar_missingness_rate_and_truth_preserved():
    people = _cohort()
    rep = observe(people, ObservationModel(missingness_rate=0.3, mechanism="MCAR", seed=1))
    assert rep.n_observations > 500
    assert 0.25 < rep.missing_rate < 0.35  # ~0.3
    for p in people:
        for o in p.record.observations:
            if o.missing:
                assert o.value is None
                assert o.true_value is not None   # clean value retained for benchmarking


def test_measurement_error_perturbs_but_keeps_truth():
    people = _cohort(n=80)
    observe(people, ObservationModel(noise_sigma=5.0, seed=2))
    perturbed = [o for p in people for o in p.record.observations if not o.missing]
    assert perturbed
    assert any(o.true_value is not None and o.value != o.true_value for o in perturbed)


def test_mnar_makes_high_values_more_often_missing():
    people = _cohort(n=300)
    observe(people, ObservationModel(missingness_rate=0.1, mechanism="MNAR",
                                     mnar_threshold=150.0, mnar_factor=3.0, seed=3))
    hi_t = hi_m = lo_t = lo_m = 0
    for p in people:
        for o in p.record.observations:
            truth = o.true_value if o.true_value is not None else o.value
            if truth is None:
                continue
            if truth >= 150:
                hi_t += 1
                hi_m += o.missing
            else:
                lo_t += 1
                lo_m += o.missing
    assert hi_t and lo_t
    assert (hi_m / hi_t) > (lo_m / lo_t)   # informative missingness


def test_gt_observations_export_true_vs_observed(tmp_path):
    from psynthea.export import export_ground_truth
    people = _cohort(n=60)
    observe(people, ObservationModel(missingness_rate=0.3, seed=5))
    counts = export_ground_truth(people, tmp_path)
    assert counts["gt_observations.csv"] > 0
    import csv
    rows = list(csv.DictReader((tmp_path / "gt_observations.csv").open()))
    assert any(r["MISSING"] == "true" for r in rows)
    # missing rows still carry the true value (the benchmark label)
    for r in rows:
        if r["MISSING"] == "true":
            assert r["OBSERVED_VALUE"] == "" and r["TRUE_VALUE"] != ""
