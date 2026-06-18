"""Demographic profiles (ADR-016 cap. G + Phase-3 demographics).

A ``DemographicProfile`` is a weighted set of (age-band, sex) strata — exactly the
shape a national statistics office publishes (e.g. Spain's INE population pyramid).
Plugging one into ``GeneratorConfig.profile`` makes the generated cohort match that
country's age/sex structure instead of the uniform/50-50 default.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stratum:
    min_age: float
    max_age: float
    sex: str          # "M" or "F"
    weight: float     # relative size (need not sum to 1)


@dataclass
class DemographicProfile:
    strata: list[Stratum]

    def __post_init__(self) -> None:
        if not self.strata or sum(s.weight for s in self.strata) <= 0:
            raise ValueError("DemographicProfile needs strata with positive total weight")

    def sample(self, rng) -> tuple[float, str]:
        """Sample (age_years, sex): pick a stratum by weight, then a uniform age."""
        total = sum(s.weight for s in self.strata)
        r = rng.random() * total
        upto = 0.0
        for s in self.strata:
            upto += s.weight
            if r < upto:
                return rng.uniform(s.min_age, s.max_age), s.sex
        last = self.strata[-1]
        return rng.uniform(last.min_age, last.max_age), last.sex

    @classmethod
    def from_bands(cls, bands: list[tuple[float, float, float, float]]) -> "DemographicProfile":
        """Build from (min_age, max_age, weight_male, weight_female) rows."""
        strata: list[Stratum] = []
        for lo, hi, wm, wf in bands:
            if wm > 0:
                strata.append(Stratum(lo, hi, "M", wm))
            if wf > 0:
                strata.append(Stratum(lo, hi, "F", wf))
        return cls(strata)
