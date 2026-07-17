"""Default keystone attributes (approximating Synthea's Java-lifecycle assignments).

Synthea's Java code sets demographic and behavioral attributes that no GMF module does —
race, ethnicity, socioeconomic status, smoking, alcohol use — which disease modules then
gate on. ``default_keystone`` seeds these with simple, documented population rates so
those modules trigger. Distributions are crude national defaults; supply your own
``GeneratorConfig(keystone=...)`` (optionally built with ``make_keystone``) to localize.
"""
from __future__ import annotations

from collections.abc import Callable

# Values match what stock modules compare against (Race/Socioeconomic Status conditions).
_RACE_DIST = {"White": 0.60, "Hispanic": 0.19, "Black": 0.13, "Asian": 0.06,
              "Native": 0.012, "Hawaiian": 0.003, "Other": 0.005}
_SES_DIST = {"Low": 0.25, "Middle": 0.50, "High": 0.25}
_SMOKER_RATE = 0.14        # current smoking (adults)
_ALCOHOLIC_RATE = 0.06     # alcohol use disorder


def _weighted(dist: dict[str, float], rng) -> str:
    r = rng.random() * sum(dist.values())
    upto = 0.0
    for key, weight in dist.items():
        upto += weight
        if r < upto:
            return key
    return next(iter(dist))


def make_keystone(*, race_dist: dict[str, float] | None = None,
                  ses_dist: dict[str, float] | None = None,
                  smoker_rate: float = _SMOKER_RATE,
                  alcoholic_rate: float = _ALCOHOLIC_RATE) -> Callable:
    """Build a keystone callable with custom demographic/behavioral distributions."""
    races = race_dist or _RACE_DIST
    ses = ses_dist or _SES_DIST

    def keystone(person, rng) -> None:
        race = _weighted(races, rng)
        person.attributes["race"] = race
        person.attributes["ethnicity"] = "hispanic" if race == "Hispanic" else "nonhispanic"
        person.attributes["socioeconomic_status"] = _weighted(ses, rng)
        person.attributes["smoker"] = rng.random() < smoker_rate
        person.attributes["alcoholic"] = rng.random() < alcoholic_rate

    return keystone


default_keystone = make_keystone()
