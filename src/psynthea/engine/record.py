"""The simulated clinical record.

Deliberately carries no billing/payer/cost concepts (ADR-011). The entry shapes
are chosen to be a superset of what the CSV exporter needs and to extend cleanly
toward FHIR/OMOP later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psynthea.terminology import Code


# Provenance (source_module/source_state) records which module + GMF state
# produced each entry. It is ground truth the engine knows but observable data
# hides — the foundation of ground-truth label emission (ADR-016 cap. A).
@dataclass
class EncounterEntry:
    id: str
    code: Code | None
    encounter_class: str
    start: datetime
    stop: datetime | None = None
    source_module: str | None = None
    source_state: str | None = None


@dataclass
class ConditionEntry:
    code: Code | None
    start: datetime
    stop: datetime | None = None
    encounter: EncounterEntry | None = None
    source_module: str | None = None
    source_state: str | None = None


@dataclass
class MedicationEntry:
    code: Code | None
    start: datetime
    stop: datetime | None = None
    encounter: EncounterEntry | None = None
    source_module: str | None = None
    source_state: str | None = None


@dataclass
class ObservationEntry:
    code: Code | None
    value: object
    unit: str
    date: datetime
    category: str
    encounter: EncounterEntry | None = None
    source_module: str | None = None
    source_state: str | None = None
    # Observation model (ADR-016 cap. D): the clean ground-truth value is kept in
    # ``true_value`` when ``value`` is perturbed/redacted, so noised/missing data
    # doubles as an imputation/robustness benchmark.
    true_value: object = None
    missing: bool = False


@dataclass
class ProcedureEntry:
    code: Code | None
    start: datetime
    encounter: EncounterEntry | None = None
    source_module: str | None = None
    source_state: str | None = None


@dataclass
class ImmunizationEntry:
    code: Code | None
    date: datetime
    encounter: EncounterEntry | None = None
    source_module: str | None = None
    source_state: str | None = None


@dataclass
class AllergyEntry:
    code: Code | None
    start: datetime
    stop: datetime | None = None
    encounter: EncounterEntry | None = None
    source_module: str | None = None
    source_state: str | None = None


class HealthRecord:
    def __init__(self, person_id: str) -> None:
        self.person_id = person_id
        self.encounters: list[EncounterEntry] = []
        self.conditions: list[ConditionEntry] = []
        self.medications: list[MedicationEntry] = []
        self.observations: list[ObservationEntry] = []
        self.procedures: list[ProcedureEntry] = []
        self.immunizations: list[ImmunizationEntry] = []
        self.allergies: list[AllergyEntry] = []
        self.careplans: set[str] = set()          # active care-plan codes
        self.current_encounter: EncounterEntry | None = None
        self._enc_counter = 0

    # -- encounters --------------------------------------------------------
    def start_encounter(self, code: Code | None, time: datetime, encounter_class: str,
                        source_module: str | None = None, source_state: str | None = None) -> EncounterEntry:
        self._enc_counter += 1
        enc = EncounterEntry(
            id=f"{self.person_id}-e{self._enc_counter}",
            code=code,
            encounter_class=encounter_class,
            start=time,
            source_module=source_module,
            source_state=source_state,
        )
        self.encounters.append(enc)
        self.current_encounter = enc
        return enc

    def end_encounter(self, time: datetime) -> None:
        if self.current_encounter is not None:
            self.current_encounter.stop = time
            self.current_encounter = None

    # -- conditions --------------------------------------------------------
    def start_condition(self, code: Code | None, time: datetime,
                        source_module: str | None = None, source_state: str | None = None) -> ConditionEntry:
        entry = ConditionEntry(code=code, start=time, encounter=self.current_encounter,
                               source_module=source_module, source_state=source_state)
        self.conditions.append(entry)
        return entry

    def end_condition(self, code: Code, time: datetime) -> None:
        for entry in reversed(self.conditions):
            if entry.stop is None and entry.code is not None and entry.code.code == code.code:
                entry.stop = time
                return

    def active_condition_codes(self) -> list[Code]:
        return [c.code for c in self.conditions if c.stop is None and c.code is not None]

    # -- medications -------------------------------------------------------
    def start_medication(self, code: Code | None, time: datetime,
                         source_module: str | None = None, source_state: str | None = None) -> MedicationEntry:
        entry = MedicationEntry(code=code, start=time, encounter=self.current_encounter,
                                source_module=source_module, source_state=source_state)
        self.medications.append(entry)
        return entry

    def end_medication(self, code: Code, time: datetime) -> None:
        for entry in reversed(self.medications):
            if entry.stop is None and entry.code is not None and entry.code.code == code.code:
                entry.stop = time
                return

    def active_medication_codes(self) -> list[Code]:
        return [m.code for m in self.medications if m.stop is None and m.code is not None]

    # -- procedures / immunizations / allergies / care plans ---------------
    def start_procedure(self, code: Code | None, time: datetime,
                        source_module: str | None = None, source_state: str | None = None) -> ProcedureEntry:
        entry = ProcedureEntry(code=code, start=time, encounter=self.current_encounter,
                               source_module=source_module, source_state=source_state)
        self.procedures.append(entry)
        return entry

    def add_immunization(self, code: Code | None, time: datetime,
                         source_module: str | None = None, source_state: str | None = None) -> ImmunizationEntry:
        entry = ImmunizationEntry(code=code, date=time, encounter=self.current_encounter,
                                  source_module=source_module, source_state=source_state)
        self.immunizations.append(entry)
        return entry

    def start_allergy(self, code: Code | None, time: datetime,
                      source_module: str | None = None, source_state: str | None = None) -> AllergyEntry:
        entry = AllergyEntry(code=code, start=time, encounter=self.current_encounter,
                             source_module=source_module, source_state=source_state)
        self.allergies.append(entry)
        return entry

    def end_allergy(self, code: Code, time: datetime) -> None:
        for entry in reversed(self.allergies):
            if entry.stop is None and entry.code is not None and entry.code.code == code.code:
                entry.stop = time
                return

    def active_allergy_codes(self) -> list[Code]:
        return [a.code for a in self.allergies if a.stop is None and a.code is not None]

    # -- observations ------------------------------------------------------
    def add_observation(
        self, code: Code | None, value, unit: str, time: datetime, category: str,
        source_module: str | None = None, source_state: str | None = None,
    ) -> ObservationEntry:
        entry = ObservationEntry(
            code=code, value=value, unit=unit, date=time, category=category,
            encounter=self.current_encounter,
            source_module=source_module, source_state=source_state,
        )
        self.observations.append(entry)
        return entry

    def close_open(self, time: datetime) -> None:
        """Close any still-open encounter at end of simulation."""
        self.end_encounter(time)
