"""Tests for fidelity/utility/privacy evaluation (ADR-016 capability F)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from psynthea.compat import load_module_file
from psynthea.engine import Generator, GeneratorConfig
from psynthea.evaluation import fidelity_report, privacy_report, utility_agreement

_ROOT = Path(__file__).resolve().parents[1]


def _cohort(seed):
    module = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    cfg = GeneratorConfig(population=200, seed=seed, end_date=datetime(2025, 1, 1), max_age=40)
    return Generator([module], cfg).run()


def test_fidelity_two_samples_are_close():
    a, b = _cohort(1), _cohort(2)
    rep = fidelity_report(a, b)
    assert rep["prevalence_mae"] < 0.1          # same process -> similar prevalence
    assert rep["female_fraction_diff"] < 0.15


def test_fidelity_self_is_perfect():
    a = _cohort(1)
    rep = fidelity_report(a, a)
    assert rep["prevalence_mae"] == 0.0
    assert rep["mean_birth_year_diff"] == 0.0


def test_utility_agreement_same_conclusion():
    a, b = _cohort(1), _cohort(2)

    def otitis_prevalence(people):
        have = sum(any(c.code and c.code.code == "65363002" for c in p.record.conditions)
                   for p in people)
        return have / len(people)

    u = utility_agreement(a, b, otitis_prevalence)
    assert u["abs_diff"] < 0.1


def test_privacy_self_match_and_membership_note():
    a = _cohort(1)
    rep = privacy_report(a, a)            # cohort vs itself -> every record matches
    assert rep["dcr_min"] == 0.0
    assert rep["exact_feature_matches"] == rep["n_synthetic"]
    assert "not applicable" in rep["membership_inference"]


def test_privacy_distinct_cohorts_have_distance():
    a, b = _cohort(1), _cohort(2)
    rep = privacy_report(a, b)
    assert rep["dcr_mean"] > 0.0          # synthetic records are not copies of the reference
