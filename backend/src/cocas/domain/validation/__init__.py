"""Domain validation — the ⭐ source-of-truth layer of §8.1's four defences.

Layer 3 of four (Zod → Pydantic → **here** → database constraints). The
promise §8.1 makes is that layers 1 and 2 can be bypassed entirely — someone
calling the API directly — without dirty data reaching the database, and that
promise rests on this package.

v1.0 delivers the `OCR_RESULT` set (23 rules, §8.4). The other three sets are
registered empty until P3 builds the form, the contract flow and the template
registration they belong to.
"""
from cocas.domain.validation.engine import DEFAULT_REGISTRY, ValidationEngine
from cocas.domain.validation.ocr_rules import (
    FIELD_LABELS_VI,
    OCR_RESULT_RULES,
    REQUIRED_FIELDS,
    OcrValidationTarget,
)
from cocas.domain.validation.report import Severity, ValidationIssue, ValidationReport
from cocas.domain.validation.rule import FunctionRule, Rule, RuleContext, RuleSetKey

__all__ = [
    "DEFAULT_REGISTRY",
    "FIELD_LABELS_VI",
    "OCR_RESULT_RULES",
    "REQUIRED_FIELDS",
    "FunctionRule",
    "OcrValidationTarget",
    "Rule",
    "RuleContext",
    "RuleSetKey",
    "Severity",
    "ValidationEngine",
    "ValidationIssue",
    "ValidationReport",
]
