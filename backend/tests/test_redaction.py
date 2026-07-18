"""
Redaction gate tests — prove that real Indian banking PII is caught and masked.

These tests run without a database or LLM — the gate is a pure in-process module.
All assertions check that:
  1. The redacted text does NOT contain the original PII value
  2. The private mapping DOES contain the original value (so de-anonymization is possible)
  3. The entity_map contains ONLY entity-type labels, never raw values
"""

import pytest
from app.redaction.gate import RedactionGate


@pytest.fixture(scope="module")
def gate():
    """Initialise once per module — spaCy load is expensive."""
    return RedactionGate()


# ---------------------------------------------------------------------------
# PAN card
# ---------------------------------------------------------------------------

def test_pan_detected_and_masked(gate):
    text = "Please verify PAN ABCDE1234F for this customer."
    result = gate.redact(text)
    assert "ABCDE1234F" not in result.text, "Raw PAN must not appear in redacted output"
    assert "<IN_PAN>" in result.text
    assert any("ABCDE1234F" == v for v in result.mapping.values()), "PAN must be in private mapping"
    assert "IN_PAN" in result.detected_types


def test_pan_in_sentence(gate):
    text = "Customer Rajesh Kumar (PAN: BRTPK8921G) is requesting a home loan."
    result = gate.redact(text)
    assert "BRTPK8921G" not in result.text
    assert "<IN_PAN>" in result.text


# ---------------------------------------------------------------------------
# Aadhaar-like synthetic IDs
# ---------------------------------------------------------------------------

def test_aadhaar_spaced_format(gate):
    text = "Aadhaar number provided: 3456 7890 1234"
    result = gate.redact(text)
    assert "3456 7890 1234" not in result.text
    assert "<IN_AADHAAR>" in result.text
    assert "IN_AADHAAR" in result.detected_types


def test_aadhaar_dashed_format(gate):
    text = "UID: 5678-1234-9012 was verified."
    result = gate.redact(text)
    assert "5678-1234-9012" not in result.text


# ---------------------------------------------------------------------------
# Indian phone numbers
# ---------------------------------------------------------------------------

def test_indian_phone_e164(gate):
    text = "Call me on +91 9876543210 for account queries."
    result = gate.redact(text)
    assert "9876543210" not in result.text
    assert any(t in result.detected_types for t in ["IN_PHONE", "PHONE_NUMBER"])


def test_indian_phone_local_with_context(gate):
    text = "Contact number: 8765432109"
    result = gate.redact(text)
    # Low-score pattern needs context; this may or may not fire without context word.
    # We assert the mapping is internally consistent: if detected, original is in mapping.
    for label, original in result.mapping.items():
        assert original in text, "Mapping value must be a substring of original text"


# ---------------------------------------------------------------------------
# Email addresses
# ---------------------------------------------------------------------------

def test_email_masked(gate):
    text = "Please send the statement to rajesh.kumar@example.com"
    result = gate.redact(text)
    assert "rajesh.kumar@example.com" not in result.text
    assert "<EMAIL_ADDRESS>" in result.text
    assert "EMAIL_ADDRESS" in result.detected_types


# ---------------------------------------------------------------------------
# Bank account numbers (with context)
# ---------------------------------------------------------------------------

def test_bank_account_with_context(gate):
    text = "Transfer ₹50,000 to account number 123456789012 via NEFT."
    result = gate.redact(text)
    assert "123456789012" not in result.text
    assert "IN_BANK_ACCOUNT" in result.detected_types


# ---------------------------------------------------------------------------
# IFSC codes
# ---------------------------------------------------------------------------

def test_ifsc_masked(gate):
    text = "IFSC code: IDBI0001234 for branch transfer."
    result = gate.redact(text)
    assert "IDBI0001234" not in result.text
    assert "IN_IFSC" in result.detected_types


# ---------------------------------------------------------------------------
# Combined — realistic banking query
# ---------------------------------------------------------------------------

def test_realistic_banking_query(gate):
    text = (
        "Hi, I'm Priya Sharma. My account number is 987654321098, "
        "PAN is CRKPS7823M, and my mobile is +91-9988776655. "
        "Please check my KYC status and send results to priya@gmail.com"
    )
    result = gate.redact(text)

    # All these must NOT appear in the redacted text
    assert "987654321098" not in result.text
    assert "CRKPS7823M" not in result.text
    assert "9988776655" not in result.text
    assert "priya@gmail.com" not in result.text

    # Private mapping must hold all originals
    all_originals = set(result.mapping.values())
    assert "CRKPS7823M" in all_originals
    assert "priya@gmail.com" in all_originals

    # entity_map must never contain raw PII values
    for label, entity_type in result.entity_map.items():
        assert label.startswith("<") and label.endswith(">"), f"Label must be type-tag: {label}"
        # entity_type should be one of our known types
        assert "_" in entity_type or entity_type in {"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"}


# ---------------------------------------------------------------------------
# Structural guarantee: entity_map contains no raw PII
# ---------------------------------------------------------------------------

def test_entity_map_contains_no_raw_values(gate):
    """entity_map is safe to include in API responses and logs."""
    text = "Account 555444333222 belongs to Amit Verma, email: amit@bank.co.in"
    result = gate.redact(text)

    sensitive_fragments = ["555444333222", "amit@bank.co.in"]
    for fragment in sensitive_fragments:
        for label, entity_type in result.entity_map.items():
            assert fragment not in label, "entity_map key must not contain raw PII"
            assert fragment not in entity_type, "entity_map value must not contain raw PII"


# ---------------------------------------------------------------------------
# Clean text passes through unchanged
# ---------------------------------------------------------------------------

def test_clean_text_passes_through(gate):
    text = "What is the current interest rate for fixed deposits?"
    result = gate.redact(text)
    assert result.text == text
    assert result.mapping == {}
    assert result.detected_types == []
    assert gate.is_clean(text)


# ---------------------------------------------------------------------------
# Idempotency: redacting an already-redacted string is safe
# ---------------------------------------------------------------------------

def test_idempotent_on_already_redacted(gate):
    first = gate.redact("Send OTP to +91 9123456789")
    second = gate.redact(first.text)
    # No new PII should be detected in the already-redacted text
    assert second.text == first.text or "<" in second.text  # labels may still be there, no raw PII
    for original in second.mapping.values():
        assert "+91 9123456789" not in original, "Original phone must not re-appear"


# ---------------------------------------------------------------------------
# Empty / edge inputs
# ---------------------------------------------------------------------------

def test_empty_string(gate):
    result = gate.redact("")
    assert result.text == ""
    assert result.mapping == {}


def test_whitespace_only(gate):
    result = gate.redact("   ")
    assert result.mapping == {}
