"""The module Intermediate Representation (IR).

This is the linchpin of psynthea (ADR-002): a typed in-memory representation of
Synthea's Generic Module Framework. Every authoring format (the JSON importer,
the future Python DSL) targets the IR; the engine only ever executes the IR.
"""
from psynthea.ir.module import Module
from psynthea.ir.states import State

__all__ = ["Module", "State"]
