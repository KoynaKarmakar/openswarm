"""
VERITAS Redaction Gate — the single chokepoint before any LLM call or memory write.

Contract:
  redact(text) -> RedactionResult
    .text        : string safe to send to LLM / write to cache
    .entity_map  : {label_in_text: entity_type} — what was replaced and what kind it was
                   NEVER contains original values; safe to include in API trace.
    .mapping     : {label_in_text: original_value} — PRIVATE, never returned to client,
                   never logged, never persisted; lives only in caller's request scope.

The mapping is returned to the CALLER (not the client), allowing de-anonymization
within the same request if the agent needs to reconstruct a response for the user.
The caller must not store it beyond the request lifecycle.

All LLM calls MUST use llm/router.py which calls redact() internally.
A separate test (test_no_llm_bypass.py) enforces this structurally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

# Presidio / spaCy are imported lazily inside RedactionGate.__init__ to avoid
# loading them at module import time (which would conflict with XGBoost's OpenMP
# initialisation on macOS ARM when both are collected by pytest in the same process).

logger = logging.getLogger(__name__)

# Entity types to detect — ordered from highest to lowest sensitivity.
# EMAIL_ADDRESS and PERSON come from Presidio's spaCy NER pipeline.
ENTITIES = [
    "IN_PAN",
    "IN_AADHAAR",
    "IN_PHONE",
    "IN_BANK_ACCOUNT",
    "IN_IFSC",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "PERSON",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_SSN",  # catch tourist/NRI documents
]

# Confidence threshold — results below this are skipped.
SCORE_THRESHOLD = 0.6


@dataclass
class RedactionResult:
    text: str
    entity_map: dict[str, str] = field(default_factory=dict)
    mapping: dict[str, str] = field(default_factory=dict)
    detected_types: list[str] = field(default_factory=list)


class RedactionGate:
    """
    Singleton — initialised once at app startup (spaCy model load is expensive).
    Thread-safe: Presidio AnalyzerEngine and AnonymizerEngine are stateless after init.
    """

    def __init__(self):
        # Lazy imports — deferred until first instantiation to keep module-level
        # import clean and avoid OpenMP conflicts with XGBoost on macOS ARM.
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_anonymizer import AnonymizerEngine
        from app.redaction.recognizers import (
            AadhaarRecognizer, BankAccountRecognizer,
            IFSCRecognizer, IndianPhoneRecognizer, PANRecognizer,
        )

        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()

        for recognizer_cls in [PANRecognizer, AadhaarRecognizer, IndianPhoneRecognizer,
                                BankAccountRecognizer, IFSCRecognizer]:
            registry.add_recognizer(recognizer_cls())

        self._analyzer = AnalyzerEngine(registry=registry)
        self._anonymizer = AnonymizerEngine()
        logger.info("RedactionGate initialised with %d recognizers", len(registry.recognizers))

    def redact(self, text: str) -> RedactionResult:
        """
        Analyse text, replace detected PII with entity-type labels,
        return the safe text plus the private mapping.

        Labels look like <IN_PAN>, <PERSON>, <EMAIL_ADDRESS> — human-readable
        in the LLM prompt and in the frontend "what went to the model" panel.
        """
        if not text or not text.strip():
            return RedactionResult(text=text)

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=ENTITIES,
            score_threshold=SCORE_THRESHOLD,
        )

        if not results:
            return RedactionResult(text=text)

        # Sort by start position descending so we can replace in-place
        # without position drift.
        results_sorted = sorted(results, key=lambda r: r.start, reverse=True)

        redacted = text
        entity_map: dict[str, str] = {}
        mapping: dict[str, str] = {}
        detected_types: list[str] = []

        # Track original→label to reuse the same label for identical values.
        seen: dict[str, str] = {}

        for result in results_sorted:
            original = text[result.start : result.end]
            label = f"<{result.entity_type}>"

            if original not in seen:
                seen[original] = label
                entity_map[label] = result.entity_type
                mapping[label] = original
                if result.entity_type not in detected_types:
                    detected_types.append(result.entity_type)
            else:
                label = seen[original]

            redacted = redacted[: result.start] + label + redacted[result.end :]

        return RedactionResult(
            text=redacted,
            entity_map=entity_map,
            mapping=mapping,
            detected_types=detected_types,
        )

    def is_clean(self, text: str) -> bool:
        """Quick check — returns True if no PII detected above threshold."""
        results = self._analyzer.analyze(
            text=text, language="en", entities=ENTITIES, score_threshold=SCORE_THRESHOLD
        )
        return len(results) == 0


@lru_cache(maxsize=1)
def get_redaction_gate() -> RedactionGate:
    """FastAPI dependency: returns the singleton gate."""
    return RedactionGate()
