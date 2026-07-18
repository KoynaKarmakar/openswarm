"""
Aadhaar LIVE client — UIDAI Auth/OTP API 2.5 request pipeline.

⚠️  AUTHORIZATION & SAFETY
    Calling UIDAI (sandbox/pre-production OR production) is only lawful for a
    UIDAI-registered AUA/KUA (or a sub-AUA under one). Point this at TEST-series
    Aadhaar numbers in the sandbox only. Never run it against a real person's
    Aadhaar without a licensed, authorized deployment. Credentials (AUA/ASA
    license keys, .p12 password) are read from config/env and MUST NOT be
    committed — auth.cfg and *.p12/*.cer are gitignored.

⚠️  REFERENCE IMPLEMENTATION
    This assembles the 2.5 request faithfully to the published spec, but the
    exact byte-framing of encrypted blocks, the certificate-id format, and the
    XMLDSig profile MUST be verified against UIDAI's current developer docs and
    tested in the sandbox before you trust a result. Each step is annotated.

Pipeline (per UIDAI Auth API 2.5):
    1. Build the Pid XML (Pi/Pv for demographic, Pv/otp for OTP auth) with a ts.
    2. Generate a random AES-256 session key.
    3. Encrypt the Pid with AES-256-GCM (IV = last 12 bytes of ts, AAD = last 16
       bytes of ts); Data = base64(ts_bytes + ciphertext+tag).
    4. Skey = base64(RSA-encrypt(UIDAI public cert, session key)); ci = cert
       expiry date (YYYYMMDD).
    5. Hmac = base64(ts_bytes + AES-GCM(session key, SHA-256(Pid))).
    6. Assemble the Auth XML (uid, ac, sa, ver, tid, txn, lk, Skey, Data, Hmac).
    7. XML-digitally-sign it with the AUA signing key (.p12).
    8. POST to the ASA-routed endpoint; parse <AuthRes ret=.. err=.. code=..>.

Heavy/optional deps (`lxml`, `signxml`) are imported lazily so importing this
module never breaks the base install; LIVE calls raise a clear error if missing.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets

logger = logging.getLogger("veritas.swarm.aadhaar.live")


# ── low-level crypto (standard, unit-testable) ────────────────────────────────

def aes_gcm_encrypt(key: bytes, ts: str, plaintext: bytes) -> bytes:
    """
    UIDAI-style AES-256-GCM: IV = last 12 bytes of ts, AAD = last 16 bytes of ts.
    Returns ts_bytes + ciphertext + tag (the framing UIDAI expects for Data/Hmac).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ts_bytes = ts.encode("utf-8")
    iv = ts_bytes[-12:]
    aad = ts_bytes[-16:]
    ct = AESGCM(key).encrypt(iv, plaintext, aad)   # ciphertext||tag
    return ts_bytes + ct


def aes_gcm_decrypt(key: bytes, ts: str, framed: bytes) -> bytes:
    """Inverse of aes_gcm_encrypt (used by tests to prove the roundtrip)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ts_bytes = ts.encode("utf-8")
    iv = ts_bytes[-12:]
    aad = ts_bytes[-16:]
    ct = framed[len(ts_bytes):]
    return AESGCM(key).decrypt(iv, ct, aad)


def new_session_key() -> bytes:
    """A fresh 256-bit AES session key (one per request, per UIDAI spec)."""
    return secrets.token_bytes(32)


def pid_hmac(session_key: bytes, ts: str, pid_bytes: bytes) -> str:
    """Hmac element: base64( ts_bytes + AES-GCM( SHA-256(Pid) ) )."""
    digest = hashlib.sha256(pid_bytes).digest()
    return base64.b64encode(aes_gcm_encrypt(session_key, ts, digest)).decode()


def load_certificate(data: bytes):
    """
    Load an X.509 cert from PEM or DER bytes. Real UIDAI .cer files are DER;
    many mirrors ship PEM — accept either so a downloaded cert just works.
    """
    from cryptography import x509

    try:
        return x509.load_pem_x509_certificate(data)
    except ValueError:
        return x509.load_der_x509_certificate(data)


def encrypt_session_key(public_cert: bytes, session_key: bytes) -> str:
    """Skey: base64( RSA-encrypt(UIDAI public key, session key) ) (PKCS1 v1.5)."""
    from cryptography.hazmat.primitives.asymmetric import padding

    cert = load_certificate(public_cert)
    encrypted = cert.public_key().encrypt(session_key, padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


def cert_expiry_id(public_cert: bytes) -> str:
    """UIDAI Skey 'ci' attribute — the cert's expiry date as YYYYMMDD."""
    cert = load_certificate(public_cert)
    # not_valid_after_utc (cryptography>=42) is preferred; fall back to the
    # deprecated naive not_valid_after on older versions.
    expiry = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    return expiry.strftime("%Y%m%d")


# ── request XML assembly ──────────────────────────────────────────────────────

def build_pid_xml(*, ts: str, otp: str | None = None,
                  name: str | None = None, gender: str | None = None,
                  dob: str | None = None) -> bytes:
    """
    Build the Pid block. `otp` selects OTP auth (Pv/otp); name/gender/dob build a
    demographic (Pi) match. `ver` of Pid is 2.0. Returned as UTF-8 bytes.
    """
    from xml.sax.saxutils import quoteattr

    parts = [f'<Pid ts={quoteattr(ts)} ver="2.0" wadh="">']
    if otp is not None:
        parts.append(f'<Pv otp={quoteattr(otp)}/>')
    if name or gender or dob:
        pi = ["<Pi"]
        if name:
            pi.append(f" ms=\"E\" name={quoteattr(name)}")
        if gender:
            pi.append(f" gender={quoteattr(gender)}")
        if dob:
            pi.append(f" dob={quoteattr(dob)}")
        pi.append("/>")
        parts.append("".join(pi))
    parts.append("</Pid>")
    return "".join(parts).encode("utf-8")


# ── config helpers ────────────────────────────────────────────────────────────

def load_from_env(config):
    """
    Overlay secrets from environment variables onto an AuaConfig (env wins).
    Keeps license keys out of files entirely if you prefer:
        AUA_LICENSE_KEY, ASA_LICENSE_KEY, UIDAI_AUA_CODE, UIDAI_SUB_AUA,
        UIDAI_PUBLIC_CERT_PATH, AUA_P12_PATH, AUA_P12_PASSWORD, UIDAI_API_HOST
    """
    config.license_key = os.environ.get("AUA_LICENSE_KEY", config.license_key)
    config.asa_license_key = os.environ.get("ASA_LICENSE_KEY", config.asa_license_key)
    config.aua_code = os.environ.get("UIDAI_AUA_CODE", config.aua_code)
    config.sub_aua = os.environ.get("UIDAI_SUB_AUA", config.sub_aua)
    config.public_cert_path = os.environ.get("UIDAI_PUBLIC_CERT_PATH", config.public_cert_path)
    config.identity_p12_path = os.environ.get("AUA_P12_PATH", config.identity_p12_path)
    config.p12_password = os.environ.get("AUA_P12_PASSWORD", config.p12_password)
    config.asa_endpoint = os.environ.get("UIDAI_API_HOST", config.asa_endpoint)
    return config


class AadhaarLiveClient:
    """
    Builds and sends UIDAI Auth/OTP 2.5 requests. Instantiate with a fully
    configured AuaConfig (license keys + certs). Missing config raises before any
    network call — this client never guesses credentials.
    """

    def __init__(self, config):
        self.config = config

    # -- readiness -----------------------------------------------------------
    def _require(self):
        missing = [name for name, val in (
            ("license_key", self.config.license_key),
            ("asa_license_key", self.config.asa_license_key),
            ("public_cert_path", self.config.public_cert_path),
            ("identity_p12_path", self.config.identity_p12_path),
        ) if not val]
        if missing:
            raise RuntimeError(
                "Aadhaar LIVE client is not fully configured. Missing: "
                f"{missing}. Set them in a gitignored auth.cfg or via env vars "
                "(AUA_LICENSE_KEY, ASA_LICENSE_KEY, UIDAI_PUBLIC_CERT_PATH, "
                "AUA_P12_PATH). Never commit these."
            )

    def _endpoint(self, kind: str, uid: str) -> str:
        base = self.config.asa_endpoint.rstrip("/")
        return f"{base}/{kind}/2.5/{self.config.aua_code}/{uid[0]}/{uid[1]}/{self.config.asa_license_key}"

    def _build_signed_auth(self, uid: str, pid_bytes: bytes, ts: str, txn: str) -> bytes:
        from xml.sax.saxutils import quoteattr

        with open(self.config.public_cert_path, "rb") as fh:
            cert_pem = fh.read()

        skey = new_session_key()
        data = base64.b64encode(aes_gcm_encrypt(skey, ts, pid_bytes)).decode()
        hmac_val = pid_hmac(skey, ts, pid_bytes)
        enc_skey = encrypt_session_key(cert_pem, skey)
        ci = cert_expiry_id(cert_pem)

        auth_xml = (
            f'<Auth xmlns="http://www.uidai.gov.in/authentication/uid-auth-request/2.0" '
            f'uid={quoteattr(uid)} ac={quoteattr(self.config.aua_code)} '
            f'sa={quoteattr(self.config.sub_aua)} ver="2.5" tid="" '
            f'txn={quoteattr(txn)} lk={quoteattr(self.config.license_key)}>'
            f'<Uses pi="{"y" if b"<Pi" in pid_bytes else "n"}" pa="n" pfa="n" '
            f'bio="n" bt="" pin="n" otp="{"y" if b"<Pv otp" in pid_bytes else "n"}"/>'
            f'<Skey ci={quoteattr(ci)}>{enc_skey}</Skey>'
            f'<Data type="X">{data}</Data>'
            f'<Hmac>{hmac_val}</Hmac>'
            f'</Auth>'
        ).encode("utf-8")

        return self._sign_xml(auth_xml)

    def _sign_xml(self, xml_bytes: bytes) -> bytes:
        """XMLDSig-sign with the AUA .p12 signing key (enveloped signature)."""
        try:
            from lxml import etree
            from signxml import XMLSigner
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "LIVE Aadhaar signing needs `lxml` and `signxml`. "
                "Install them: pip install lxml signxml"
            ) from exc
        from cryptography.hazmat.primitives.serialization import pkcs12

        with open(self.config.identity_p12_path, "rb") as fh:
            p12 = fh.read()
        key, cert, _chain = pkcs12.load_key_and_certificates(
            p12, self.config.p12_password.encode() if self.config.p12_password else None
        )
        root = etree.fromstring(xml_bytes)
        signed = XMLSigner().sign(root, key=key, cert=cert)
        return etree.tostring(signed)

    @staticmethod
    def _parse_response(body: bytes) -> dict:
        """Parse <AuthRes>/<OtpRes> → {ret, code, txn, err}."""
        import re
        text = body.decode("utf-8", "replace")
        def attr(name):
            m = re.search(rf'{name}="([^"]*)"', text)
            return m.group(1) if m else None
        return {"ret": attr("ret"), "code": attr("code"), "txn": attr("txn"), "err": attr("err")}

    # -- public API ----------------------------------------------------------
    def generate_otp(self, uid: str, *, txn: str) -> dict:
        """POST an OTP request (sends OTP to the Aadhaar-linked mobile)."""
        self._require()
        from xml.sax.saxutils import quoteattr
        import httpx

        otp_xml = (
            f'<Otp xmlns="http://www.uidai.gov.in/authentication/otp/1.0" '
            f'uid={quoteattr(uid)} ac={quoteattr(self.config.aua_code)} '
            f'sa={quoteattr(self.config.sub_aua)} ver="2.5" tid="" '
            f'txn={quoteattr(txn)} lk={quoteattr(self.config.license_key)}>'
            f'<Opts ch="01"/></Otp>'
        ).encode("utf-8")
        signed = self._sign_xml(otp_xml)
        resp = httpx.post(self._endpoint("otp", uid), content=signed,
                          headers={"Content-Type": "application/xml"}, timeout=15)
        return self._parse_response(resp.content)

    def authenticate(self, uid: str, *, ts: str, otp: str | None = None,
                     name: str | None = None, gender: str | None = None,
                     dob: str | None = None, txn: str) -> dict:
        """Build → encrypt → sign → POST an Auth request. Returns {ret, code, txn, err}."""
        self._require()
        import httpx

        pid_bytes = build_pid_xml(ts=ts, otp=otp, name=name, gender=gender, dob=dob)
        signed = self._build_signed_auth(uid, pid_bytes, ts, txn)
        resp = httpx.post(self._endpoint("auth", uid), content=signed,
                          headers={"Content-Type": "application/xml"}, timeout=15)
        return self._parse_response(resp.content)
