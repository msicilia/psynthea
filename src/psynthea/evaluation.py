"""Fidelity / utility / privacy evaluation (ADR-016 capability F).

Bundles the synthetic-data trilemma into one dependency-free module that compares
a psynthea cohort against a *reference* cohort (a real holdout in practice):

- **fidelity** — statistical resemblance (per-condition prevalence, demographics).
- **utility** — does an analysis reach the same conclusion on synthetic vs
  reference? (a pluggable statistic; TSTR-style, no ML dependency).
- **privacy** — distance-to-closest-record (DCR) + exact-duplicate count.
  NB: membership-inference is *not applicable* to psynthea — it is trained on no
  real patient data, so there is no membership to infer (a structural privacy
  advantage worth stating explicitly).
"""
from __future__ import annotations

from collections.abc import Callable

from psynthea.engine.person import Person


def _condition_codes(people: list[Person]) -> set[str]:
    return {c.code.code for p in people for c in p.record.conditions if c.code is not None}


def _prevalence(people: list[Person], code: str) -> float:
    if not people:
        return 0.0
    have = sum(any(c.code is not None and c.code.code == code for c in p.record.conditions)
               for p in people)
    return have / len(people)


def fidelity_report(synthetic: list[Person], reference: list[Person]) -> dict:
    codes = sorted(_condition_codes(synthetic) | _condition_codes(reference))
    per_code = {c: {"synthetic": _prevalence(synthetic, c), "reference": _prevalence(reference, c)}
                for c in codes}
    prev_mae = (sum(abs(v["synthetic"] - v["reference"]) for v in per_code.values()) / len(codes)
                if codes else 0.0)

    def _female(ppl):
        return (sum(p.gender == "F" for p in ppl) / len(ppl)) if ppl else 0.0

    def _mean_birth_year(ppl):
        return (sum(p.birthdate.year for p in ppl) / len(ppl)) if ppl else 0.0

    return {
        "prevalence_mae": prev_mae,
        "per_code_prevalence": per_code,
        "female_fraction_diff": abs(_female(synthetic) - _female(reference)),
        "mean_birth_year_diff": abs(_mean_birth_year(synthetic) - _mean_birth_year(reference)),
    }


def utility_agreement(synthetic: list[Person], reference: list[Person],
                      statistic: Callable[[list[Person]], float]) -> dict:
    """Apply the same analysis ``statistic`` to both cohorts and compare."""
    s, r = statistic(synthetic), statistic(reference)
    return {"synthetic": s, "reference": r, "abs_diff": abs(s - r),
            "rel_diff": (abs(s - r) / abs(r)) if r else None}


def _feature_vector(person: Person, codes: list[str]) -> list[float]:
    vec = [person.birthdate.year / 100.0, 1.0 if person.gender == "F" else 0.0]
    present = {c.code.code for c in person.record.conditions if c.code is not None}
    vec += [1.0 if c in present else 0.0 for c in codes]
    return vec


def _dist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def privacy_report(synthetic: list[Person], reference: list[Person]) -> dict:
    """Distance-to-closest-record from each synthetic record to the reference set."""
    codes = sorted(_condition_codes(synthetic) | _condition_codes(reference))
    ref_vecs = [_feature_vector(p, codes) for p in reference]
    if not ref_vecs or not synthetic:
        return {"applicable": False, "note": "need non-empty cohorts"}

    dcrs, exact = [], 0
    for p in synthetic:
        v = _feature_vector(p, codes)
        nearest = min(_dist(v, rv) for rv in ref_vecs)
        dcrs.append(nearest)
        if nearest == 0.0:
            exact += 1
    return {
        "dcr_min": min(dcrs),
        "dcr_mean": sum(dcrs) / len(dcrs),
        "exact_feature_matches": exact,
        "n_synthetic": len(synthetic),
        "membership_inference": "not applicable — psynthea trains on no real patient data",
    }
