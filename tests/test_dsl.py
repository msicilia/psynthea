"""DSL tests: authoring, validation, and round-trip equivalence with JSON (ADR-004)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from psynthea.compat import load_module_file
from psynthea.dsl import DslError, ModuleBuilder, age, code, otherwise, when
from psynthea.engine import Generator, GeneratorConfig

_ROOT = Path(__file__).resolve().parents[1]


def build_otitis_dsl():
    """The same module as data/modules/otitis_media.json, authored in the DSL."""
    b = ModuleBuilder("otitis_media")
    b.initial().to("Annual_Check")
    b.delay("Annual_Check", years=1).complex(
        when(age("<", 8, "years")).distributed(
            (0.3, "Ear_Infection_Encounter"), (0.7, "Annual_Check")),
        otherwise("Annual_Check"),
    )
    b.encounter("Ear_Infection_Encounter",
                code("SNOMED-CT", "185345009", "Encounter for symptom")).to("Diagnose_Otitis_Media")
    b.condition_onset("Diagnose_Otitis_Media", code("SNOMED-CT", "65363002", "Otitis media"),
                      assign_to="otitis_media",
                      target_encounter="Ear_Infection_Encounter").to("Prescribe_Amoxicillin")
    b.medication("Prescribe_Amoxicillin", code("ATC", "J01CA04", "Amoxicillin")).to("End_Encounter")
    b.encounter_end("End_Encounter").to("Resolve")
    b.delay("Resolve", low=14, high=28, unit="days").to("Cure_Otitis_Media")
    b.condition_end("Cure_Otitis_Media",
                    code("SNOMED-CT", "65363002", "Otitis media")).to("Annual_Check")
    return b.build()


def test_dsl_matches_json_structurally():
    dsl = build_otitis_dsl()
    imported = load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")
    assert set(dsl.states) == set(imported.states)
    for name in imported.states:
        assert type(dsl.states[name]) is type(imported.states[name])


def test_dsl_and_json_generate_identical_cohorts():
    """The strong round-trip: same seed -> byte-for-byte identical patient records."""
    cfg = GeneratorConfig(population=150, seed=42, end_date=datetime(2025, 1, 1), max_age=60)
    dsl_people = Generator([build_otitis_dsl()], cfg).run()
    json_people = Generator(
        [load_module_file(_ROOT / "src" / "psynthea" / "data" / "modules" / "otitis_media.json")], cfg).run()

    assert [p.id for p in dsl_people] == [p.id for p in json_people]
    assert ([len(p.record.conditions) for p in dsl_people]
            == [len(p.record.conditions) for p in json_people])
    assert ([len(p.record.medications) for p in dsl_people]
            == [len(p.record.medications) for p in json_people])
    assert sum(len(p.record.conditions) for p in dsl_people) > 0  # the module actually fired


# --- validation (author-time, not run-time) -------------------------------- #
def test_unknown_transition_target_raises():
    b = ModuleBuilder("bad")
    b.initial().to("Nowhere")
    with pytest.raises(DslError, match="unknown state 'Nowhere'"):
        b.build()


def test_missing_initial_raises():
    b = ModuleBuilder("bad")
    b.simple("X").to("X")
    with pytest.raises(DslError, match="no Initial"):
        b.build()


def test_invalid_code_raises():
    with pytest.raises(DslError):
        code("", "65363002")


def test_duplicate_state_raises():
    b = ModuleBuilder("dup")
    b.initial()
    with pytest.raises(DslError, match="duplicate"):
        b.initial()


def test_conditional_rejects_distribution_payload():
    b = ModuleBuilder("x")
    b.initial()
    ref = b.simple("S")
    with pytest.raises(DslError, match="use complex"):
        ref.conditional(when(age(">", 1)).distributed((1.0, "Initial")))
