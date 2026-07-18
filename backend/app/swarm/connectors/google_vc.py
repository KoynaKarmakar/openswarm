"""
Google Verifiable Credentials connector — the "verifiable authentic docs" leg
of the Identity & Fraud agent.

Instead of OCR-ing a scanned ID (spoofable), this verifies a **W3C Verifiable
Credential (VC 2.0)** presented by the customer — the shape Google Wallet /
Google Digital Credentials issues. "Verifiable" here means *cryptographically
signature-checked* against a trusted issuer's public key, not merely parsed.

verify(vc) walks five checks:
  1. @context includes the VC v2 context
  2. type includes "VerifiableCredential"
  3. issuer present AND on the trust registry
  4. credentialSubject present, and not expired (validUntil)
  5. proof signature verifies (Ed25519) against the issuer's registered key

Signature verification uses `cryptography` (a project dependency). If it is not
importable in a given environment, the signature is reported as "unchecked"
(the agent then downgrades to NEEDS_REVIEW rather than trusting it blindly).

`issue_credential()` / `generate_issuer_keypair()` are demo helpers so a hackathon
can mint a Google-style signed VC without a live Google issuer.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("veritas.swarm.google_vc")

VC_V2_CONTEXT = "https://www.w3.org/ns/credentials/v2"


def _canonical(obj) -> bytes:
    """Stable bytes for signing/verifying — sorted keys, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _ed25519():
    """Return the cryptography Ed25519 primitives, or None if unavailable."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        return Ed25519PrivateKey, Ed25519PublicKey, InvalidSignature
    except Exception:  # noqa: BLE001
        return None


def _issuer_id(vc: dict) -> str | None:
    issuer = vc.get("issuer")
    if isinstance(issuer, str):
        return issuer
    if isinstance(issuer, dict):
        return issuer.get("id")
    return None


@dataclass
class VCVerification:
    verified: bool
    issuer: str | None
    issuer_trusted: bool
    signature_state: str          # "valid" | "invalid" | "unchecked"
    structural_ok: bool
    expired: bool
    reason: str
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verified": self.verified,
            "issuer": self.issuer,
            "issuer_trusted": self.issuer_trusted,
            "signature_state": self.signature_state,
            "structural_ok": self.structural_ok,
            "expired": self.expired,
            "reason": self.reason,
            "checks": self.checks,
        }


class GoogleVerifiableCredentialsConnector:
    """
    Verifies presented W3C Verifiable Credentials against a trust registry.

    trust_registry maps an issuer id (e.g. "did:web:issuer.google.com") to that
    issuer's raw Ed25519 public key, base64-encoded.
    """

    def __init__(self, trust_registry: dict[str, str] | None = None):
        self._trust = dict(trust_registry or {})

    def verify(self, vc: dict, *, now: datetime | None = None) -> VCVerification:
        checks: dict = {}

        if not isinstance(vc, dict) or not vc:
            return VCVerification(
                verified=False, issuer=None, issuer_trusted=False,
                signature_state="unchecked", structural_ok=False, expired=False,
                reason="no credential presented", checks=checks,
            )

        # 1-2. structural
        contexts = vc.get("@context")
        checks["context"] = isinstance(contexts, list) and VC_V2_CONTEXT in contexts
        types = vc.get("type")
        checks["type"] = isinstance(types, list) and "VerifiableCredential" in types
        checks["credentialSubject"] = bool(vc.get("credentialSubject"))

        issuer = _issuer_id(vc)
        structural_ok = bool(checks["context"] and checks["type"] and checks["credentialSubject"] and issuer)

        # 3. issuer trust
        issuer_trusted = issuer in self._trust
        checks["issuer_trusted"] = issuer_trusted

        # 4. expiry
        now = now or datetime.now(timezone.utc)
        expired = False
        valid_until = vc.get("validUntil") or vc.get("expirationDate")
        if valid_until:
            try:
                exp = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                expired = now > exp
            except ValueError:
                expired = False
        checks["not_expired"] = not expired

        # 5. signature
        signature_state = "unchecked"
        proof = vc.get("proof")
        ed = _ed25519()
        if proof and issuer_trusted and ed:
            Ed25519PrivateKey, Ed25519PublicKey, InvalidSignature = ed
            try:
                pub_raw = base64.b64decode(self._trust[issuer])
                pubkey = Ed25519PublicKey.from_public_bytes(pub_raw)
                sig = base64.b64decode(proof.get("proofValue", ""))
                unsigned = {k: v for k, v in vc.items() if k != "proof"}
                pubkey.verify(sig, _canonical(unsigned))
                signature_state = "valid"
            except InvalidSignature:
                signature_state = "invalid"
            except Exception as exc:  # noqa: BLE001 — malformed proof / key
                logger.warning("VC signature verification error: %s", exc)
                signature_state = "invalid"
        checks["signature"] = signature_state

        verified = bool(structural_ok and issuer_trusted and not expired and signature_state == "valid")

        if verified:
            reason = "verified"
        else:
            failed = [k for k, v in checks.items() if v not in (True, "valid")]
            reason = "failed: " + ", ".join(failed) if failed else "verification failed"

        return VCVerification(
            verified=verified,
            issuer=issuer,
            issuer_trusted=issuer_trusted,
            signature_state=signature_state,
            structural_ok=structural_ok,
            expired=expired,
            reason=reason,
            checks=checks,
        )


# ── Demo issuer helpers (mock "Google issuer" for the hackathon) ──────────────

def generate_issuer_keypair() -> tuple[str, str]:
    """Return (private_key_b64, public_key_b64) raw Ed25519 keys for a demo issuer."""
    ed = _ed25519()
    if not ed:
        raise RuntimeError("cryptography is required to generate an issuer keypair")
    Ed25519PrivateKey, _pub, _inv = ed
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    priv = Ed25519PrivateKey.generate()
    priv_b64 = base64.b64encode(
        priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ).decode()
    pub_b64 = base64.b64encode(
        priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    return priv_b64, pub_b64


def issue_credential(
    subject: dict,
    *,
    issuer: str,
    private_key_b64: str,
    verification_method: str | None = None,
    valid_until: str | None = None,
) -> dict:
    """Mint a signed W3C VC 2.0 (demo helper standing in for a Google issuer)."""
    ed = _ed25519()
    if not ed:
        raise RuntimeError("cryptography is required to issue a credential")
    Ed25519PrivateKey, _pub, _inv = ed

    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    credential: dict = {
        "@context": [VC_V2_CONTEXT],
        "type": ["VerifiableCredential", "IdentityCredential"],
        "issuer": issuer,
        "credentialSubject": subject,
    }
    if valid_until:
        credential["validUntil"] = valid_until

    signature = priv.sign(_canonical(credential))
    credential["proof"] = {
        "type": "Ed25519Signature2020",
        "verificationMethod": verification_method or f"{issuer}#key-1",
        "proofValue": base64.b64encode(signature).decode(),
    }
    return credential
