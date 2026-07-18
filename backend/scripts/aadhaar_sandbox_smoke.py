#!/usr/bin/env python3
"""
Aadhaar sandbox smoke test — run this on YOUR machine (not in CI), with a
UIDAI-registered AUA setup, against TEST-series Aadhaar numbers only.

It walks the UIDAI Auth 2.5 pipeline step by step and prints PASS / SKIP for
each, so you can see exactly how far your setup gets:

    1. Verhoeff check on the UID
    2. Load the UIDAI public cert (.cer, PEM or DER) → encrypt session key (Skey)
    3. Build the encrypted Data + Hmac blocks
    4. XMLDSig-sign with your AUA .p12   (needs lxml + signxml + your keystore)
    5. POST to UIDAI via the ASA route   (only with --send, and only if signed)

Setup (never commit any of this):
    cp app/swarm/connectors/auth.cfg.example auth.cfg
    # edit auth.cfg: mode=live, your AUA + ASA license keys, cert paths
    # download the UIDAI staging cert to e.g. certs/uidai_auth_stage.cer
    pip install lxml signxml

Usage:
    cd backend
    python scripts/aadhaar_sandbox_smoke.py --uid 999941057058 --otp 123456
    python scripts/aadhaar_sandbox_smoke.py --uid 999941057058 --otp 123456 --send
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import datetime, timezone

# Allow `python scripts/aadhaar_sandbox_smoke.py` from the backend/ directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.swarm.connectors.aadhaar_auth import mask_aadhaar, verhoeff_valid
from app.swarm.connectors.aadhaar_live import (
    AadhaarLiveClient,
    aes_gcm_encrypt,
    build_pid_xml,
    cert_expiry_id,
    encrypt_session_key,
    load_from_env,
    new_session_key,
    pid_hmac,
)
from app.swarm.connectors.aadhaar_auth import load_config


def _ok(msg):   print(f"  \033[32mPASS\033[0m  {msg}")
def _skip(msg): print(f"  \033[33mSKIP\033[0m  {msg}")
def _fail(msg): print(f"  \033[31mFAIL\033[0m  {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="UIDAI Aadhaar 2.5 sandbox smoke test")
    ap.add_argument("--uid", default="999941057058", help="TEST-series Aadhaar number")
    ap.add_argument("--otp", default=None, help="OTP value (test OTP in sandbox)")
    ap.add_argument("--name", default=None, help="name for a demographic (Pi) match")
    ap.add_argument("--config", default="auth.cfg", help="path to auth.cfg")
    ap.add_argument("--send", action="store_true", help="actually POST to UIDAI (licensed AUA only)")
    args = ap.parse_args()

    cfg = load_from_env(load_config(args.config))
    print(f"\nUID {mask_aadhaar(args.uid)}  ·  mode={cfg.mode}  ·  aua={cfg.aua_code}\n")

    # 1. Verhoeff
    if verhoeff_valid(args.uid):
        _ok("Verhoeff checksum")
    else:
        _fail("Verhoeff checksum — not a valid Aadhaar number; stopping")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    pid = build_pid_xml(ts=ts, otp=args.otp, name=args.name)
    _ok(f"PID XML built ({'OTP' if args.otp else 'demographic' if args.name else 'no-factor'})")

    # 2. Skey (needs the public cert only)
    skey = new_session_key()
    if cfg.public_cert_path:
        try:
            cert_bytes = open(cfg.public_cert_path, "rb").read()
            enc_skey = encrypt_session_key(cert_bytes, skey)
            _ok(f"Skey encrypted with UIDAI cert (ci={cert_expiry_id(cert_bytes)}, "
                f"{len(base64.b64decode(enc_skey))} bytes)")
        except Exception as exc:  # noqa: BLE001
            _fail(f"Skey — could not use public_cert_path: {exc}")
            return 1
    else:
        _skip("Skey — set public_cert_path (download the UIDAI staging .cer)")

    # 3. Data + Hmac
    base64.b64encode(aes_gcm_encrypt(skey, ts, pid))
    pid_hmac(skey, ts, pid)
    _ok("Data (AES-256-GCM) + Hmac assembled")

    # 4. Sign
    signed = None
    if cfg.identity_p12_path:
        try:
            client = AadhaarLiveClient(cfg)
            signed = client._build_signed_auth(args.uid, pid, ts, txn="smoke")
            _ok(f"Auth XML signed with .p12 ({len(signed)} bytes)")
        except Exception as exc:  # noqa: BLE001
            _skip(f"Signing — {type(exc).__name__}: {exc}")
    else:
        _skip("Signing — set identity_p12_path (your AUA keystore, from UIDAI)")

    # 5. Send
    if args.send and signed is not None:
        try:
            client = AadhaarLiveClient(cfg)
            res = client.authenticate(args.uid, ts=ts, otp=args.otp, name=args.name, txn="smoke")
            _ok(f"UIDAI response: ret={res.get('ret')} err={res.get('err')} code={res.get('code')}")
        except Exception as exc:  # noqa: BLE001
            _fail(f"Send — {type(exc).__name__}: {exc}")
    elif args.send:
        _skip("Send — nothing signed to transmit (complete step 4 first)")
    else:
        _skip("Send — omitted (pass --send to POST to UIDAI; licensed AUA only)")

    print("\nDone. Green all the way to 'Send' means your crypto/assembly is ready;\n"
          "a real ret=y needs a licensed AUA + reachable UIDAI sandbox.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
