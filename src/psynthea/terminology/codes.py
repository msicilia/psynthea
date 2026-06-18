"""Minimal terminology layer.

Code-system agnostic on purpose (ADR-006): psynthea targets European coding
(ATC for medications, SNOMED CT, LOINC, ICD-10) but the engine never assumes a
specific system — it just carries (system, code, display) triples. A normalizing
mapping layer (e.g. RxNorm->ATC for imported US modules) belongs here later.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Code:
    system: str
    code: str
    display: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Code":
        return cls(
            system=data["system"],
            code=str(data["code"]),
            display=data.get("display", ""),
        )

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.code} ({self.system})"
