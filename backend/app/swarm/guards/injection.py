"""
Prompt-injection & policy-evasion detector for the Guardrail agent.

Pure regex — no LLM, no heavy deps — so it runs before anything reaches the
model and is cheap to unit-test. It powers the demo's "Scenario B (The Catch)":
the terminal shows the Guardrail agent intercepting a jailbreak or an illegal
financial-advice request and short-circuiting straight to the Auditor.

Two categories:
  * "prompt_injection" — attempts to override the system prompt / instructions.
  * "policy_evasion"   — attempts to get help laundering money, faking KYC docs,
                         evading tax, or eliciting illegal financial advice.

detect_injection(text) -> list[InjectionHit]  (empty == clean)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (category, human label, compiled pattern). Patterns are case-insensitive.
_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # ── prompt injection ────────────────────────────────────────────────────
    ("prompt_injection", "ignore-previous-instructions",
     re.compile(r"\bignore\s+(?:all\s+|the\s+)?(?:previous|above|prior)\s+"
                r"(?:instructions?|prompts?|rules?)", re.I)),
    ("prompt_injection", "disregard-rules",
     re.compile(r"\bdisregard\b.{0,30}\b(?:instructions?|rules?|policy|policies|guidelines?)", re.I)),
    ("prompt_injection", "forget-instructions",
     re.compile(r"\bforget\s+(?:all\s+|everything\s+)?(?:you|your|the\s+previous|prior)", re.I)),
    ("prompt_injection", "reveal-system-prompt",
     re.compile(r"\b(?:reveal|show|print|repeat|leak)\b.{0,30}\b(?:system\s+prompt|instructions?)", re.I)),
    ("prompt_injection", "override-policy",
     re.compile(r"\boverride\b.{0,30}\b(?:rules?|policy|policies|compliance|safety)", re.I)),
    ("prompt_injection", "role-hijack",
     re.compile(r"\byou\s+are\s+now\b|\bact\s+as\s+(?:a\s+|an\s+)?(?:dan|jailbreak|unfiltered)", re.I)),
    ("prompt_injection", "do-anything-now",
     re.compile(r"\bdo\s+anything\s+now\b|\bDAN\s+mode\b", re.I)),
    ("prompt_injection", "bypass-checks",
     re.compile(r"\bbypass\b.{0,30}\b(?:compliance|kyc|rules?|checks?|verification)", re.I)),

    # ── policy evasion / illegal financial advice ───────────────────────────
    ("policy_evasion", "money-laundering",
     re.compile(r"\b(?:launder(?:ing)?|hawala|structuring)\b.{0,30}\b(?:money|cash|funds?)"
                r"|\blaunder\s+money\b", re.I)),
    ("policy_evasion", "fake-kyc-document",
     re.compile(r"\b(?:fake|forge|forged|fabricate|spoof)\b.{0,20}"
                r"\b(?:aadhaar|aadhar|pan|kyc|identity|document|passport|voter\s*id)\b", re.I)),
    ("policy_evasion", "evade-tax-kyc",
     re.compile(r"\b(?:evade|avoid|dodge|bypass|skip)\b.{0,20}\b(?:tax|taxes|kyc|reporting|audit)\b", re.I)),
    ("policy_evasion", "hide-from-regulator",
     re.compile(r"\bhide\b.{0,30}\b(?:from\s+)?(?:rbi|regulator|tax|income\s*tax|authorities?)\b", re.I)),
]


@dataclass
class InjectionHit:
    category: str      # "prompt_injection" | "policy_evasion"
    label: str         # which rule matched
    match: str         # the matched substring (safe to log — no PII)


def detect_injection(text: str) -> list[InjectionHit]:
    """Return all injection/evasion hits in `text`. Empty list means clean."""
    if not text or not text.strip():
        return []
    hits: list[InjectionHit] = []
    for category, label, pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            hits.append(InjectionHit(category=category, label=label, match=m.group(0)))
    return hits
