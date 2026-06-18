"""Aggregate-statistics calibration (ADR-016 capability C).

Build a disease module from **epidemiological summary statistics** (target
lifetime prevalence + mean onset age — the kind a national registry publishes by
age/sex), then **calibrate** it by simulation so the generated cohort actually
hits those targets. Uses only aggregate numbers, no patient-level data — the
privacy-preserving mechanism behind European localization (e.g. fit to Spanish
INE / registry rates).

Why calibration is needed (not just "set the probability = prevalence"): the
realized prevalence depends on the cohort's age structure and the simulation
horizon — patients younger than the onset age never reach the onset gate — so the
gate probability that *yields* a target prevalence differs from the target. We
find it with a deterministic bisection (realized prevalence is monotonic in the
gate probability).
"""
from __future__ import annotations

from dataclasses import dataclass

from psynthea.dsl import (
    ModuleBuilder,
    active_condition,
    age,
    all_of,
    code,
    otherwise,
    when,
)
from psynthea.engine import Generator, GeneratorConfig
from psynthea.ir.module import Module
from psynthea.terminology import Code

_VISIT = code("SNOMED-CT", "185345009", "Encounter for symptom")


@dataclass
class EpiSpec:
    code: Code                         # the condition
    prevalence: float                  # target lifetime prevalence (0..1)
    onset_age: float                   # target mean age at onset (years)
    resolution_days: tuple[int, int] | None = None  # optional (low, high) for resolution


def build_module(spec: EpiSpec, name: str = "calibrated",
                 gate_probability: float | None = None) -> Module:
    """Build a parametric disease module from an EpiSpec.

    ``gate_probability`` defaults to the naive ``spec.prevalence``; calibration
    overrides it with the value that actually realizes the target.
    """
    p = spec.prevalence if gate_probability is None else gate_probability
    p = max(0.0, min(1.0, p))
    attr = f"has_{spec.code.code}"

    b = ModuleBuilder(name)
    b.initial().to("Onset_Gate")
    b.guard("Onset_Gate", age(">=", round(spec.onset_age), "years")).to("Onset_Prob")
    b.simple("Onset_Prob").distributed((p, "Visit"), (round(1.0 - p, 6), "Terminal"))
    b.encounter("Visit", _VISIT).to("Onset")

    after_onset = "Resolve" if spec.resolution_days else "End_Visit"
    b.condition_onset("Onset", spec.code, assign_to=attr, target_encounter="Visit").to("End_Visit")
    b.encounter_end("End_Visit").to(after_onset if spec.resolution_days else "Terminal")
    if spec.resolution_days:
        lo, hi = spec.resolution_days
        b.delay("Resolve", low=lo, high=hi, unit="days").to("Cure")
        b.condition_end("Cure", spec.code).to("Terminal")
    b.terminal()
    return b.build()


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #
def realized_prevalence(people, code_str: str) -> float:
    if not people:
        return 0.0
    have = sum(any(c.code is not None and c.code.code == code_str for c in p.record.conditions)
               for p in people)
    return have / len(people)


def mean_onset_age(people, code_str: str) -> float | None:
    ages: list[float] = []
    for p in people:
        firsts = [c.start for c in p.record.conditions
                  if c.code is not None and c.code.code == code_str]
        if firsts:
            ages.append((min(firsts) - p.birthdate).days / 365.25)
    return (sum(ages) / len(ages)) if ages else None


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
@dataclass
class CalibrationResult:
    target_prevalence: float
    realized_prevalence: float
    gate_probability: float
    iterations: int
    module: Module


def calibrate(spec: EpiSpec, config: GeneratorConfig, *, tol: float = 0.02,
              max_iter: int = 25) -> CalibrationResult:
    """Find the gate probability that realizes ``spec.prevalence`` for ``config``.

    Bisection on [0, 1]; deterministic given ``config.seed``.
    """
    target = spec.prevalence
    lo, hi, mid = 0.0, 1.0, spec.prevalence
    realized = 0.0
    module = build_module(spec, gate_probability=mid)
    for i in range(1, max_iter + 1):
        mid = (lo + hi) / 2
        module = build_module(spec, gate_probability=mid)
        people = Generator([module], config).run()
        realized = realized_prevalence(people, spec.code.code)
        if abs(realized - target) <= tol:
            return CalibrationResult(target, realized, mid, i, module)
        if realized < target:
            lo = mid
        else:
            hi = mid
    return CalibrationResult(target, realized, mid, max_iter, module)


# --------------------------------------------------------------------------- #
# Age-stratified calibration
# --------------------------------------------------------------------------- #
# A single gate can only hit ONE aggregate prevalence; it cannot reproduce a
# prevalence *curve* (different rates at 50 vs 70 vs 80). Registries almost always
# publish rates by age band, so here we give each band its own yearly onset gate and
# calibrate them — one per band — so the cross-sectional prevalence *within each band*
# matches its target. See docs/concepts/calibration.md ("age-stratified").


@dataclass
class AgeBand:
    min_age: float        # inclusive lower bound (years)
    max_age: float        # exclusive upper bound; use a large number for an open top band
    prevalence: float     # target cross-sectional prevalence among patients now in [min,max)


@dataclass
class StratifiedEpiSpec:
    code: Code
    bands: list[AgeBand]  # ordered youngest-first; should be contiguous & non-overlapping


def build_stratified_module(spec: StratifiedEpiSpec, gate_probabilities: list[float],
                            name: str = "calibrated_stratified") -> Module:
    """Build a per-band module: a yearly loop that, while the patient is undiseased and
    in band *b*, applies band *b*'s onset probability.

    ``gate_probabilities`` are *per-year* onset hazards, one per band (not prevalences).
    Calibration finds the values that realize the per-band target prevalences.
    """
    if len(gate_probabilities) != len(spec.bands):
        raise ValueError("need exactly one gate probability per band")
    attr = f"has_{spec.code.code}"

    b = ModuleBuilder(name)
    b.initial().to("Wait")
    b.delay("Wait", years=1).to("Check")

    # already diseased -> never re-onset; else pick the branch for the current band
    branches = [when(active_condition(spec.code)).then("Wait")]
    for band, p in zip(spec.bands, gate_probabilities):
        p = max(0.0, min(1.0, p))
        in_band = all_of(age(">=", band.min_age, "years"), age("<", band.max_age, "years"))
        branches.append(when(in_band).distributed((p, "Visit"), (round(1.0 - p, 6), "Wait")))
    branches.append(otherwise("Wait"))
    b.simple("Check").complex(*branches)

    b.encounter("Visit", _VISIT).to("Onset")
    b.condition_onset("Onset", spec.code, assign_to=attr, target_encounter="Visit").to("End_Visit")
    b.encounter_end("End_Visit").to("Wait")
    return b.build()


def _age_years(person, end_date) -> float:
    return (end_date - person.birthdate).days / 365.25


def realized_prevalence_in_band(people, code_str: str, lo: float, hi: float,
                                end_date) -> float | None:
    """Cross-sectional prevalence among patients whose age at ``end_date`` is in [lo, hi).

    Returns None when no patient falls in the band (cannot estimate).
    """
    in_band = [p for p in people if lo <= _age_years(p, end_date) < hi]
    if not in_band:
        return None
    have = sum(any(c.code is not None and c.code.code == code_str for c in p.record.conditions)
               for p in in_band)
    return have / len(in_band)


@dataclass
class BandCalibration:
    band: AgeBand
    realized_prevalence: float | None
    gate_probability: float
    iterations: int


@dataclass
class StratifiedCalibrationResult:
    bands: list[BandCalibration]
    gate_probabilities: list[float]
    module: Module


def calibrate_stratified(spec: StratifiedEpiSpec, config: GeneratorConfig, *,
                         tol: float = 0.02, max_iter: int = 25) -> StratifiedCalibrationResult:
    """Calibrate one onset gate per age band, youngest-first.

    Each band's realized prevalence depends only on the gates of that band and the
    younger ones (older-band gates change only older-band prevalence), so calibrating
    in age order lets each band be solved independently by bisection while earlier
    bands stay fixed. Requires enough patients spanning every band (set the config's
    age range and population accordingly).
    """
    gates = [band.prevalence for band in spec.bands]  # initial guesses
    band_results: list[BandCalibration] = []

    for k, band in enumerate(spec.bands):
        lo_p, hi_p, mid = 0.0, 1.0, gates[k]
        realized: float | None = None
        used = max_iter
        for i in range(1, max_iter + 1):
            mid = (lo_p + hi_p) / 2
            gates[k] = mid
            module = build_stratified_module(spec, gates)
            people = Generator([module], config).run()
            realized = realized_prevalence_in_band(
                people, spec.code.code, band.min_age, band.max_age, config.end_date)
            if realized is None:                 # no patients in band — can't calibrate
                used = i
                break
            if abs(realized - band.prevalence) <= tol:
                used = i
                break
            if realized < band.prevalence:
                lo_p = mid
            else:
                hi_p = mid
        gates[k] = mid
        band_results.append(BandCalibration(band, realized, mid, used))

    module = build_stratified_module(spec, gates)
    return StratifiedCalibrationResult(band_results, list(gates), module)
