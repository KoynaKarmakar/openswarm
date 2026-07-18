"""
Custom Presidio recognizers for Indian banking PII.
These supplement Presidio's built-in NER (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, etc.).
"""

import re
from presidio_analyzer import Pattern, PatternRecognizer


class PANRecognizer(PatternRecognizer):
    """Indian PAN card: 5 letters, 4 digits, 1 letter — e.g. ABCDE1234F."""

    PATTERNS = [
        Pattern(
            name="PAN_CARD",
            regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
            score=0.9,
        )
    ]
    CONTEXT = ["pan", "permanent account", "income tax", "pan card", "pan no"]

    def __init__(self):
        super().__init__(
            supported_entity="IN_PAN",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class AadhaarRecognizer(PatternRecognizer):
    """
    Synthetic Aadhaar-like 12-digit number used in test data.
    Real Aadhaar: 12 digits, first digit non-zero.
    Pattern intentionally conservative to avoid false positives on amounts.
    """

    PATTERNS = [
        Pattern(
            name="AADHAAR_SPACED",
            regex=r"\b[2-9]\d{3}\s\d{4}\s\d{4}\b",
            score=0.95,
        ),
        Pattern(
            name="AADHAAR_DASHED",
            regex=r"\b[2-9]\d{3}-\d{4}-\d{4}\b",
            score=0.95,
        ),
    ]
    CONTEXT = ["aadhaar", "uid", "unique identification", "aadhaar no", "aadhar"]

    def __init__(self):
        super().__init__(
            supported_entity="IN_AADHAAR",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class IndianPhoneRecognizer(PatternRecognizer):
    """
    Indian mobile numbers: 10 digits starting with 6-9, optionally prefixed with +91 or 0.
    Presidio's built-in PHONE_NUMBER uses libphonenumber-style patterns; this adds
    local-format Indian numbers that the generic recognizer may miss.
    """

    PATTERNS = [
        Pattern(
            name="IN_PHONE_E164",
            regex=r"\+91[-\s]?[6-9]\d{9}\b",
            score=0.95,
        ),
        Pattern(
            name="IN_PHONE_LOCAL",
            regex=r"\b0?[6-9]\d{9}\b",
            score=0.75,
        ),
    ]
    CONTEXT = ["mobile", "phone", "contact", "call", "whatsapp", "number", "mob"]

    def __init__(self):
        super().__init__(
            supported_entity="IN_PHONE",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class BankAccountRecognizer(PatternRecognizer):
    """
    Indian bank account numbers: 9–18 digits.
    High-context requirement to avoid false positives on transaction amounts.
    """

    PATTERNS = [
        Pattern(
            name="BANK_ACCOUNT",
            regex=r"\b\d{9,18}\b",
            score=0.6,
        )
    ]
    CONTEXT = [
        "account", "acc", "acct", "bank account", "account number",
        "account no", "savings", "current", "ifsc",
    ]

    def __init__(self):
        super().__init__(
            supported_entity="IN_BANK_ACCOUNT",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class IFSCRecognizer(PatternRecognizer):
    """IFSC code: 4-letter bank code + 0 + 6 alphanumeric branch code."""

    PATTERNS = [
        Pattern(
            name="IFSC",
            regex=r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
            score=0.9,
        )
    ]
    CONTEXT = ["ifsc", "branch code", "neft", "rtgs", "imps"]

    def __init__(self):
        super().__init__(
            supported_entity="IN_IFSC",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )
