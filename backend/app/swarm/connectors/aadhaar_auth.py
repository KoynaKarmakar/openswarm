"""
Aadhaar Auth connector — UIDAI Auth API 2.5-shaped identity verification.

WHAT THIS IS
------------
A structured, PII-safe Aadhaar verification connector for the Identity & Fraud
agent. It mirrors the shape of the real UIDAI Authentication API (the `Auth` /
`Pid` / `Uses` envelope, the AUA/sub-AUA/license-key fields, and the `ret="y"/"n"`
response with UIDAI error codes) so that a licensed AUA integration is a drop-in
swap — but by default it runs in DEMO mode and performs NO network call.

WHAT THIS IS NOT
----------------
It is NOT a live UIDAI client. Authenticating against auth.uidai.gov.in
(production or pre-production/staging) requires being a UIDAI-licensed
AUA/KUA with a registered license key, an ASA network route, and approved
certificates. Real Aadhaar numbers must never be transmitted without that
authorization. LIVE mode here therefore refuses to send: it builds the request
envelope and raises, pointing at the exact seam a licensed operator fills in.

PII CONTRACT
------------
The 12-digit Aadhaar is treated like the redaction mapping: it stays in the
caller's request scope, is never written to the trace, the ledger, or the LLM
path. Only a masked reference ("XXXX XXXX 9012") leaves this module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("veritas.swarm.aadhaar")

# ── Verhoeff checksum (the real Aadhaar check-digit scheme) ───────────────────
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 9, 1, 6, 7, 4, 3, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_valid(number: str) -> bool:
    """True if `number` (a digit string) passes the Verhoeff checksum."""
    if not number or not number.isdigit():
        return False
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(digit)]]
    return c == 0


def verhoeff_generate(base: str) -> str:
    """Return the Verhoeff check digit for `base` (a digit string, no check digit)."""
    c = 0
    for i, digit in enumerate(reversed(base)):
        c = _D[c][_P[(i + 1) % 8][int(digit)]]
    return str(_INV[c])


def mask_aadhaar(number: str) -> str:
    """Return a UIDAI-style masked reference: only the last 4 digits shown."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) != 12:
        return "XXXX XXXX XXXX"
    return f"XXXX XXXX {digits[-4:]}"


# UIDAI Auth API error codes (subset) used for a realistic response shape.
UIDAI_ERR = {
    "998": "Invalid Aadhaar Number / non-availability of data",
    "997": "Aadhaar suspended / cancelled",
    "300": "Biometric data did not match",
    "310": "Duplicate fingers used",
    "400": "Invalid OTP value",
    "402": "txn value not matching",
    "k-100": "Demographic (Pi) data did not match",
}


@dataclass
class AadhaarAuthResult:
    ret: str                       # "y" | "n" — the UIDAI auth verdict
    txn: str                       # transaction id echoed back
    code: str                      # response code / auth code
    err: str | None                # UIDAI error code on failure, else None
    err_text: str | None           # human-readable error
    masked_uid: str                # "XXXX XXXX 9012" — safe to log/return
    mode: str                      # "demo" | "live"
    checks: dict = field(default_factory=dict)

    @property
    def outcome(self) -> str:
        """Map the UIDAI verdict onto a VERITAS identity outcome."""
        if self.ret == "y":
            return "APPROVED"
        if self.err == "998":          # invalid number — hard reject
            return "REJECTED"
        return "NEEDS_REVIEW"          # mismatch / unresolved → human review

    def to_dict(self) -> dict:
        return {
            "ret": self.ret,
            "txn": self.txn,
            "code": self.code,
            "err": self.err,
            "err_text": self.err_text,
            "masked_uid": self.masked_uid,
            "mode": self.mode,
            "checks": self.checks,
        }


@dataclass
class AuaConfig:
    """
    The AUA/ASA identity — the values a licensed operator sets in auth.cfg.
    None of these enable live access on their own; UIDAI must register them.
    """
    aua_code: str = "public"           # your AUA code
    sub_aua: str = "public"            # sub-AUA code
    license_key: str = ""              # AUA license key (never commit a real one)
    asa_license_key: str = ""          # ASA license key
    asa_endpoint: str = "https://auth.uidai.gov.in/2.5"  # ASA-routed UIDAI endpoint
    public_cert_path: str = ""         # UIDAI staging public cert (.cer)
    identity_p12_path: str = ""        # your signing keystore (.p12)
    p12_password: str = ""
    mode: str = "demo"                 # "demo" | "live"


# UIDAI's published developer test-series Aadhaar numbers (9999xxxxxxxx).
# Safe to hardcode — they are fictitious sample numbers, not real identities.
_DEMO_REGISTRY: dict[str, dict] = {
    "999941057058": {"name": "Shivshankar Choudhury", "yob": "1968", "gender": "M"},
    "999971658846": {"name": "Kumar Agarwal", "yob": "1972", "gender": "M"},
    "999933119400": {"name": "Fatima Bedi", "yob": "1943", "gender": "F"},
    "999955183437": {"name": "Rohit Pandey", "yob": "1985", "gender": "M"},
}


class AadhaarAuthConnector:
    """
    UIDAI Auth API 2.5-shaped verification.

    demo mode  → local Verhoeff check + optional demographic (Pi) match against
                 UIDAI's published test-series numbers. No network.
    live mode  → builds the request envelope and refuses to transmit, naming the
                 licensed-AUA seam. It does not call auth.uidai.gov.in.
    """

    def __init__(self, config: AuaConfig | None = None, live_client=None):
        """
        config      : AuaConfig (mode "demo"|"live").
        live_client : optional AadhaarLiveClient. In "live" mode, if provided and
                      fully configured, the connector transmits via it; otherwise
                      live mode refuses (never silently downgrades to demo).
        """
        self.config = config or AuaConfig()
        self._live_client = live_client

    # ── public API ────────────────────────────────────────────────────────────
    def verify(
        self,
        aadhaar: str,
        *,
        name: str | None = None,
        yob: str | None = None,
        otp: str | None = None,
        txn: str = "veritas-demo",
    ) -> AadhaarAuthResult:
        """
        Verify an Aadhaar number. `name`/`yob` drive a demographic (Pi) match;
        `otp` selects the OTP auth flow. Returns a UIDAI-shaped result whose only
        UID reference is masked.
        """
        digits = re.sub(r"\D", "", aadhaar or "")
        masked = mask_aadhaar(digits)
        checks: dict = {}

        # 1. structural: 12 digits + Verhoeff check digit
        checks["length_12"] = len(digits) == 12
        checks["verhoeff"] = verhoeff_valid(digits)
        if not checks["length_12"] or not checks["verhoeff"]:
            return AadhaarAuthResult(
                ret="n", txn=txn, code="", err="998", err_text=UIDAI_ERR["998"],
                masked_uid=masked, mode=self.config.mode, checks=checks,
            )

        if self.config.mode == "live":
            return self._verify_live(digits, name=name, yob=yob, otp=otp, txn=txn, checks=checks)
        return self._verify_demo(digits, name=name, yob=yob, otp=otp, txn=txn, checks=checks)

    # ── demo path ─────────────────────────────────────────────────────────────
    def _verify_demo(self, digits, *, name, yob, otp, txn, checks) -> AadhaarAuthResult:
        masked = mask_aadhaar(digits)
        record = _DEMO_REGISTRY.get(digits)
        checks["known_test_uid"] = record is not None

        if record is None:
            # Passes Verhoeff but not a seeded identity → "no data" in demo.
            return AadhaarAuthResult(
                ret="n", txn=txn, code="", err="998", err_text="No demo identity seeded for this UID",
                masked_uid=masked, mode="demo", checks=checks,
            )

        # OTP flow (demo OTP is 6 digits "123456").
        if otp is not None:
            checks["otp"] = otp == "123456"
            if not checks["otp"]:
                return AadhaarAuthResult(
                    ret="n", txn=txn, code="", err="400", err_text=UIDAI_ERR["400"],
                    masked_uid=masked, mode="demo", checks=checks,
                )

        # Demographic (Pi) match on name / year of birth if supplied.
        if name is not None:
            checks["pi_name"] = _norm(name) == _norm(record["name"])
        if yob is not None:
            checks["pi_yob"] = str(yob).strip() == record["yob"]
        if any(k.startswith("pi_") and v is False for k, v in checks.items()):
            return AadhaarAuthResult(
                ret="n", txn=txn, code="", err="k-100", err_text=UIDAI_ERR["k-100"],
                masked_uid=masked, mode="demo", checks=checks,
            )

        return AadhaarAuthResult(
            ret="y", txn=txn, code=f"DEMO-{digits[-4:]}", err=None, err_text=None,
            masked_uid=masked, mode="demo", checks=checks,
        )

    # ── live path ─────────────────────────────────────────────────────────────
    def _verify_live(self, digits, *, name, yob, otp, txn, checks) -> AadhaarAuthResult:
        masked = mask_aadhaar(digits)

        # With a configured live client, actually transmit (sandbox/test numbers
        # only, inside a licensed deployment).
        if self._live_client is not None:
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            resp = self._live_client.authenticate(
                digits, ts=ts, otp=otp, name=name,
                dob=(f"{yob}" if yob else None), txn=txn,
            )
            ret = (resp.get("ret") or "n").lower()
            err = resp.get("err")
            checks["transmitted"] = True
            return AadhaarAuthResult(
                ret="y" if ret == "y" else "n",
                txn=resp.get("txn") or txn,
                code=resp.get("code") or "",
                err=err,
                err_text=UIDAI_ERR.get(err) if err else None,
                masked_uid=masked, mode="live", checks=checks,
            )

        # No live client wired → build the envelope (shape only) and refuse.
        checks["envelope_built"] = bool(
            self.build_auth_envelope(digits, name=name, yob=yob, otp=otp, txn=txn)
        )
        raise NotImplementedError(
            "LIVE Aadhaar auth requires a configured AadhaarLiveClient AND a "
            "UIDAI-licensed AUA/KUA (license key + ASA route + approved certs). "
            "Pass live_client=AadhaarLiveClient(config) and run only in an "
            "authorized deployment — never against real Aadhaar numbers otherwise."
        )

    # ── request-shape helpers (mirror UIDAI Auth 2.5) ─────────────────────────
    def build_auth_envelope(self, digits, *, name, yob, otp, txn) -> dict:
        """
        Construct the UIDAI Auth 2.5 request skeleton. Values that would carry
        PII or secrets are placeholders — this is for shape/review, not sending.
        The real flow: build Pid XML → session key (Skey, RSA-encrypted with the
        UIDAI public cert) → AES-encrypt Pid into Data → Hmac → sign the Auth XML.
        """
        uses = {"pi": "y" if (name or yob) else "n", "otp": "y" if otp else "n",
                "pa": "n", "bio": "n", "pin": "n"}
        return {
            "Auth": {
                "uid": mask_aadhaar(digits),          # masked here on purpose
                "ac": self.config.aua_code,
                "sa": self.config.sub_aua,
                "ver": "2.5",
                "txn": txn,
                "lk": "<AUA_LICENSE_KEY>",            # from config at send time
                "Uses": uses,
                "Skey": {"ci": "<cert_id>", "_": "<RSA(session_key)>"},
                "Hmac": "<SHA256_HMAC(Pid)>",
                "Data": {"type": "X", "_": "<AES(Pid_XML)>"},
                "Signature": "<XMLDSig>",
            },
            "endpoint": f"{self.config.asa_endpoint}/{self.config.aua_code}/"
                        f"{digits[0]}/{digits[1]}/<asalk>",
        }


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def load_config(path: str) -> AuaConfig:
    """Load an auth.cfg (INI: [aua] section) into an AuaConfig."""
    import configparser

    parser = configparser.ConfigParser()
    parser.read(path)
    if not parser.has_section("aua"):
        return AuaConfig()
    a = parser["aua"]
    return AuaConfig(
        aua_code=a.get("aua_code", "public"),
        sub_aua=a.get("sub_aua", "public"),
        license_key=a.get("license_key", ""),
        asa_license_key=a.get("asa_license_key", ""),
        asa_endpoint=a.get("asa_endpoint", "https://auth.uidai.gov.in/2.5"),
        public_cert_path=a.get("public_cert_path", ""),
        identity_p12_path=a.get("identity_p12_path", ""),
        p12_password=a.get("p12_password", ""),
        mode=a.get("mode", "demo"),
    )
