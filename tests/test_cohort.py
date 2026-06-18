"""Tests for demographic profiles + conditional generation (ADR-016 cap. G)."""
from __future__ import annotations

from datetime import datetime

from psynthea.cohort import generate_matching, has_attribute, has_condition
from psynthea.compat import load_module_file
from psynthea.demographics import DemographicProfile, Stratum
from psynthea.engine import Generator, GeneratorConfig
from psynthea.calibration import EpiSpec, build_module
from psynthea.terminology import Code
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_profile_matches_target_sex_ratio():
    # 80% female, 20% male
    profile = DemographicProfile([Stratum(0, 80, "F", 0.8), Stratum(0, 80, "M", 0.2)])
    module = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    cfg = GeneratorConfig(population=500, seed=1, end_date=datetime(2025, 1, 1), profile=profile)
    people = Generator([module], cfg).run()
    frac_f = sum(p.gender == "F" for p in people) / len(people)
    assert 0.74 < frac_f < 0.86  # ~0.8


def test_profile_matches_target_age_bands():
    # mostly children
    profile = DemographicProfile.from_bands([(0, 10, 0.7, 0.7), (40, 60, 0.3, 0.3)])
    module = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    cfg = GeneratorConfig(population=500, seed=2, end_date=datetime(2025, 1, 1), profile=profile)
    people = Generator([module], cfg).run()
    end = datetime(2025, 1, 1)
    ages = [(end - p.birthdate).days / 365.25 for p in people]
    frac_children = sum(a < 10 for a in ages) / len(ages)
    assert 0.62 < frac_children < 0.78  # ~0.7


def test_profile_does_not_change_default_path_reproducibility():
    # without a profile, behaviour is unchanged (regression guard)
    module = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    cfg = GeneratorConfig(population=50, seed=7, end_date=datetime(2025, 1, 1), max_age=40)
    a = [p.id for p in Generator([module], cfg).run()]
    b = [p.id for p in Generator([module], cfg).run()]
    assert a == b


def test_oversample_rare_cohort_all_match():
    # a rare condition (prevalence ~5%); oversample 40 patients who all have it
    spec = EpiSpec(Code("SNOMED-CT", "777", "Rare"), prevalence=0.05, onset_age=3.0)
    module = build_module(spec)
    cfg = GeneratorConfig(population=1, seed=3, end_date=datetime(2025, 1, 1), max_age=60)
    cohort = generate_matching([module], cfg, has_condition("777"), n_target=40)
    assert len(cohort.people) == 40
    assert all(has_condition("777")(p) for p in cohort.people)
    assert cohort.acceptance_rate < 0.5          # it really was rare (oversampled)
    assert has_attribute("has_777")(cohort.people[0])
