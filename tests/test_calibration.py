"""Tests for aggregate-statistics calibration (ADR-016 capability C)."""
from __future__ import annotations

from datetime import datetime

from psynthea.calibration import (
    AgeBand,
    EpiSpec,
    StratifiedEpiSpec,
    build_module,
    build_stratified_module,
    calibrate,
    calibrate_stratified,
    mean_onset_age,
    realized_prevalence,
    realized_prevalence_in_band,
)
from psynthea.engine import Generator, GeneratorConfig
from psynthea.terminology import Code

_CODE = Code("SNOMED-CT", "12345", "Demo condition")


def _spec(prevalence=0.3, onset_age=5.0):
    return EpiSpec(code=_CODE, prevalence=prevalence, onset_age=onset_age)


def _cfg(max_age=12.0):
    # coarse step keeps the test fast; young cohort makes the calibration bias visible
    return GeneratorConfig(population=400, seed=11, end_date=datetime(2025, 1, 1),
                           min_age=0.0, max_age=max_age, step_days=30.0)


def test_build_module_has_condition_and_gate():
    m = build_module(_spec(), gate_probability=0.5)
    types = {type(s).__name__ for s in m.states.values()}
    assert "ConditionOnset" in types and "Guard" in types
    onset = next(s for s in m.states.values() if type(s).__name__ == "ConditionOnset")
    assert onset.codes[0].code == "12345"


def test_naive_probability_undershoots_on_young_cohort():
    # With onset at age 5 and a 0-12 cohort, only ~half ever reach the gate,
    # so naively setting p = target prevalence undershoots.
    spec, cfg = _spec(prevalence=0.3, onset_age=5.0), _cfg()
    naive = build_module(spec)  # gate_probability defaults to 0.3
    people = Generator([naive], cfg).run()
    assert realized_prevalence(people, "12345") < 0.3 - 0.05  # clear undershoot


def test_calibration_hits_target_within_tolerance():
    spec, cfg = _spec(prevalence=0.3, onset_age=5.0), _cfg()
    result = calibrate(spec, cfg, tol=0.02)
    assert abs(result.realized_prevalence - 0.3) <= 0.02
    assert result.gate_probability > 0.3  # had to raise p above the naive value


def test_calibration_recovers_onset_age():
    spec, cfg = _spec(prevalence=0.3, onset_age=5.0), _cfg()
    result = calibrate(spec, cfg, tol=0.02)
    people = Generator([result.module], cfg).run()
    age = mean_onset_age(people, "12345")
    assert age is not None and abs(age - 5.0) < 1.0


def test_full_age_cohort_needs_little_correction():
    # When everyone outlives the onset age, p ~ realized prevalence.
    spec, cfg = _spec(prevalence=0.25, onset_age=5.0), _cfg(max_age=80.0)
    result = calibrate(spec, cfg, tol=0.02)
    assert abs(result.realized_prevalence - 0.25) <= 0.02
    assert abs(result.gate_probability - 0.25) < 0.1  # close to naive


# --------------------------------------------------------------------------- #
# Age-stratified calibration
# --------------------------------------------------------------------------- #
def _strat_spec():
    return StratifiedEpiSpec(code=_CODE, bands=[
        AgeBand(40, 55, 0.02),
        AgeBand(55, 70, 0.08),
        AgeBand(70, 200, 0.18),
    ])


def _strat_cfg():
    return GeneratorConfig(population=1200, seed=1, end_date=datetime(2025, 1, 1),
                           min_age=40.0, max_age=95.0, step_days=30.0)


def test_build_stratified_module_has_one_branch_per_band():
    spec = _strat_spec()
    m = build_stratified_module(spec, [0.01, 0.01, 0.01])
    types = {type(s).__name__ for s in m.states.values()}
    assert "ConditionOnset" in types and "Delay" in types
    # the Check state's complex transition has: diseased-guard + 3 bands + otherwise
    check = m.states["Check"]
    assert len(check.transition.branches) == len(spec.bands) + 2


def test_stratified_calibration_matches_each_band():
    spec, cfg = _strat_spec(), _strat_cfg()
    res = calibrate_stratified(spec, cfg, tol=0.02, max_iter=30)
    assert len(res.bands) == 3
    for bc in res.bands:
        assert bc.realized_prevalence is not None
        assert abs(bc.realized_prevalence - bc.band.prevalence) <= 0.03


def test_stratified_reproduces_increasing_curve():
    # the whole point: rates rise with age, which a single gate cannot reproduce
    spec, cfg = _strat_spec(), _strat_cfg()
    res = calibrate_stratified(spec, cfg, tol=0.02, max_iter=30)
    realized = [bc.realized_prevalence for bc in res.bands]
    assert realized[0] < realized[1] < realized[2]


def test_realized_prevalence_in_band_returns_none_when_empty():
    cfg = _strat_cfg()
    people = Generator([build_stratified_module(_strat_spec(), [0.0, 0.0, 0.0])], cfg).run()
    assert realized_prevalence_in_band(people, "12345", 0, 30, cfg.end_date) is None
