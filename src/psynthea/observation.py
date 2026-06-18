"""The observation model (ADR-016 capability D).

psynthea generates the latent *truth* of a patient's course. The **observation model**
is the process that turns that truth into the *observed* record a researcher actually
sees: it injects measurement noise and---crucially---*informative* missingness ("the
curse of knowing": a value is often missing because of what it would have been). The
clean value is kept in ``true_value``, so the observed cohort is a labeled
imputation/robustness benchmark, complementing the ground-truth labels.

This is the natural complement to ground truth: ground truth is the latent state; the
observation model is the (lossy, noisy) map from that state to what is recorded.

Mechanisms: MCAR (uniform) and MNAR (missingness depends on the value --- the
informative case). Measurement error is additive Gaussian.

Scope (honest limitation): the observation model presently perturbs **numeric
observation values only**. It does not yet model miscoded conditions, missing
encounters, duplicate records, or visit-timing irregularity --- broader observation
artifacts left as future work. So it supports imputation/measurement-error benchmarks,
not (yet) coding-error or record-linkage benchmarks.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class ObservationModel:
    missingness_rate: float = 0.0          # base P(missing)
    mechanism: str = "MCAR"                # "MCAR" | "MNAR"
    mnar_threshold: float | None = None    # MNAR: values >= threshold are more often missing
    mnar_factor: float = 3.0               # how much more likely above the threshold
    noise_sigma: float = 0.0               # gaussian measurement error (absolute units)
    seed: int = 0


@dataclass
class ObservationReport:
    n_observations: int = 0
    n_noised: int = 0
    n_missing: int = 0

    @property
    def missing_rate(self) -> float:
        return self.n_missing / self.n_observations if self.n_observations else 0.0


def observe(people: list, model: ObservationModel) -> ObservationReport:
    """Observe the latent cohort through ``model``: mutate observations in place to an
    'observed' view, keeping the latent truth in ``true_value``."""
    rng = random.Random(model.seed)
    report = ObservationReport()
    for person in people:
        for obs in person.record.observations:
            report.n_observations += 1
            numeric = isinstance(obs.value, (int, float)) and not isinstance(obs.value, bool)

            # measurement error
            if model.noise_sigma > 0 and numeric:
                obs.true_value = obs.value
                obs.value = obs.value + rng.gauss(0.0, model.noise_sigma)
                report.n_noised += 1

            # missingness
            if model.missingness_rate > 0:
                prob = model.missingness_rate
                if (model.mechanism == "MNAR" and numeric and model.mnar_threshold is not None
                        and float(obs.true_value if obs.true_value is not None else obs.value)
                        >= model.mnar_threshold):
                    prob = min(1.0, prob * model.mnar_factor)
                if rng.random() < prob:
                    if obs.true_value is None:
                        obs.true_value = obs.value
                    obs.value = None
                    obs.missing = True
                    report.n_missing += 1
    return report
