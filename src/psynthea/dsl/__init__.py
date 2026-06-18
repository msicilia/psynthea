"""The psynthea Python DSL — author modules as code (ADR-004).

A typed, composable, testable alternative to hand-writing GMF JSON. The DSL
compiles to the same module IR (ADR-002) the JSON importer targets, so a DSL
module and its JSON equivalent are interchangeable.

Example::

    from psynthea.dsl import ModuleBuilder, code, when, otherwise, age

    b = ModuleBuilder("otitis_media")
    b.initial().to("Annual_Check")
    b.delay("Annual_Check", years=1).complex(
        when(age("<", 8, "years")).distributed(
            (0.3, "Ear_Infection_Encounter"), (0.7, "Annual_Check")),
        otherwise("Annual_Check"),
    )
    b.encounter("Ear_Infection_Encounter",
                code("SNOMED-CT", "185345009", "Encounter for symptom")).to("Diagnose")
    ...
    module = b.build()   # -> psynthea.ir.Module
"""
from psynthea.dsl.builder import DslError, ModuleBuilder, code, dist, otherwise, when
from psynthea.dsl.logic import (
    active_condition,
    age,
    all_of,
    any_of,
    attribute,
    false_,
    gender,
    not_,
    prior_state,
    true_,
)

__all__ = [
    "ModuleBuilder", "DslError", "code", "dist", "when", "otherwise",
    "age", "gender", "attribute", "active_condition", "prior_state",
    "all_of", "any_of", "not_", "true_", "false_",
]
