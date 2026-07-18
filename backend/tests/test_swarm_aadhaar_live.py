"""
Aadhaar LIVE client — offline crypto/assembly tests (no UIDAI network).

Proves the deterministic pieces: AES-GCM roundtrip with the UIDAI ts framing,
PID/Skey/HMAC construction, config/env loading, endpoint building, response
parsing, and that the client refuses to transmit when unconfigured.
"""

from __future__ import annotations

import base64

import pytest

crypto = pytest.importorskip("cryptography")

from app.swarm.connectors import AadhaarAuthConnector, AuaConfig
from app.swarm.connectors.aadhaar_live import (
    AadhaarLiveClient,
    aes_gcm_decrypt,
    aes_gcm_encrypt,
    build_pid_xml,
    cert_expiry_id,
    encrypt_session_key,
    load_from_env,
    new_session_key,
    pid_hmac,
)

TS = "2026-07-18T12:30:45"
VALID = "999941057058"


def _selfsigned_rsa_cert_pem() -> bytes:
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "UIDAI-TEST")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(issuer).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2027, 3, 4, tzinfo=timezone.utc))
        .sign(key, hashes.SHA256())
    )
    from cryptography.hazmat.primitives.serialization import Encoding
    return cert.public_bytes(Encoding.PEM)


# ── crypto ────────────────────────────────────────────────────────────────────

def test_aes_gcm_roundtrip_with_ts_framing():
    key = new_session_key()
    pid = build_pid_xml(ts=TS, otp="123456")
    framed = aes_gcm_encrypt(key, TS, pid)
    assert framed.startswith(TS.encode())            # ts prepended
    assert aes_gcm_decrypt(key, TS, framed) == pid   # recovers plaintext


def test_aes_gcm_tamper_fails():
    key = new_session_key()
    framed = bytearray(aes_gcm_encrypt(key, TS, b"<Pid/>"))
    framed[-1] ^= 0x01                                # flip a tag bit
    with pytest.raises(Exception):
        aes_gcm_decrypt(key, TS, bytes(framed))


def test_pid_hmac_is_deterministic_per_key():
    key = new_session_key()
    pid = build_pid_xml(ts=TS, otp="123456")
    assert pid_hmac(key, TS, pid) == pid_hmac(key, TS, pid)
    assert pid_hmac(new_session_key(), TS, pid) != pid_hmac(key, TS, pid)


def test_pid_xml_otp_and_demographic():
    otp_pid = build_pid_xml(ts=TS, otp="123456")
    assert b"<Pv otp=" in otp_pid and b'ver="2.0"' in otp_pid
    pi_pid = build_pid_xml(ts=TS, name="Shivshankar Choudhury", gender="M")
    assert b"<Pi" in pi_pid and b"Shivshankar" in pi_pid


def test_skey_encrypts_and_cert_id():
    pem = _selfsigned_rsa_cert_pem()
    skey = new_session_key()
    enc = encrypt_session_key(pem, skey)
    assert base64.b64decode(enc)                      # decodable ciphertext
    assert cert_expiry_id(pem) == "20270304"          # not_valid_after YYYYMMDD


# ── config / env ──────────────────────────────────────────────────────────────

def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("AUA_LICENSE_KEY", "env-lk")
    monkeypatch.setenv("ASA_LICENSE_KEY", "env-asa")
    cfg = load_from_env(AuaConfig(mode="live"))
    assert cfg.license_key == "env-lk" and cfg.asa_license_key == "env-asa"


# ── client guards ─────────────────────────────────────────────────────────────

def test_live_client_refuses_when_unconfigured():
    client = AadhaarLiveClient(AuaConfig(mode="live"))   # no keys/certs
    with pytest.raises(RuntimeError):
        client.authenticate(VALID, ts=TS, otp="123456", txn="t1")


def test_endpoint_url_shape():
    cfg = AuaConfig(aua_code="public", asa_license_key="ASALK", asa_endpoint="https://host/x")
    client = AadhaarLiveClient(cfg)
    url = client._endpoint("auth", VALID)
    assert url == "https://host/x/auth/2.5/public/9/9/ASALK"


def test_parse_response():
    body = b'<AuthRes ret="y" code="abc" txn="t1" err="" />'
    parsed = AadhaarLiveClient._parse_response(body)
    assert parsed["ret"] == "y" and parsed["code"] == "abc" and parsed["txn"] == "t1"


# ── connector delegates to a live client ──────────────────────────────────────

class _FakeLiveClient:
    def __init__(self):
        self.called_with = None

    def authenticate(self, uid, *, ts, otp=None, name=None, dob=None, txn):
        self.called_with = {"uid": uid, "otp": otp, "txn": txn}
        return {"ret": "y", "code": "200", "txn": txn, "err": None}


def test_connector_live_delegates_and_masks():
    fake = _FakeLiveClient()
    conn = AadhaarAuthConnector(AuaConfig(mode="live"), live_client=fake)
    r = conn.verify(VALID, otp="123456", txn="txn-1")
    assert r.ret == "y" and r.mode == "live" and r.masked_uid == "XXXX XXXX 7058"
    assert fake.called_with["uid"] == VALID          # raw uid only inside the client
    assert r.checks.get("transmitted") is True


def test_connector_live_skips_transmit_on_bad_checksum():
    fake = _FakeLiveClient()
    conn = AadhaarAuthConnector(AuaConfig(mode="live"), live_client=fake)
    r = conn.verify("999941057059")                  # bad Verhoeff → never transmit
    assert r.ret == "n" and r.err == "998"
    assert fake.called_with is None
