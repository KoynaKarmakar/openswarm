# Aadhaar auth — how it connects, and how to go live

The Identity & Fraud swarm agent verifies Aadhaar through a **UIDAI Auth API
2.5-shaped connector**. It ships in **DEMO mode** (offline, no network, test
numbers only) and has a **LIVE seam** for a licensed AUA. This doc records the
ways to connect, which apply, and the exact steps + blockers to reach LIVE.

## The three ways to connect (pick one per axis)

**Auth factor** — OTP ✅ (realistic; sandbox uses a fixed test OTP) · Demographic
Pi/Pa ✅ (weak alone) · Biometric ❌ (needs a UIDAI-certified capture device).

**API** — Auth 2.5 `/auth` ✅ · OTP 2.5 `/otp` ✅ · e-KYC 2.5 `/ekyc` ⚠️ (needs a
**KUA** licence, a tier above AUA).

**Transport** — AUA→UIDAI direct ❌ (needs your server IP whitelisted) ·
**AUA→ASA→UIDAI ✅** (you have an ASA license key, so you route via an ASA).

➡️ **Applicable path for this project: OTP auth (Auth API 2.5) via the ASA route.**
That is what `AadhaarLiveClient` implements.

## What you can and can't "find"

| Artifact | Where | Public? |
|---|---|---|
| UIDAI **staging public cert** (`.cer`, encrypts the PID) | `https://uidai.gov.in/images/uidai_auth_stage.cer` | ✅ Public — download in your browser (this repo's CI/proxy blocks `uidai.gov.in`, so fetch it yourself). Real file is **DER**; the loader accepts DER or PEM. |
| **AUA signing keystore** (`.p12`, signs the Auth XML) | issued by UIDAI to a registered AUA | ❌ **Not public.** No download exists — you get it only as a licensed AUA (or a sub-AUA under one). **This is the real gate to LIVE, and it's licensing, not code.** |

## Setup (nothing here is committed — all gitignored)

```bash
cd backend
cp app/swarm/connectors/auth.cfg.example auth.cfg     # gitignored
# edit auth.cfg: mode=live, AUA+ASA license keys, cert paths
mkdir -p certs                                          # put the UIDAI .cer + your .p12 here
pip install lxml signxml                                # LIVE-only signing deps
```

`auth.cfg` (or env vars `AUA_LICENSE_KEY`, `ASA_LICENSE_KEY`,
`UIDAI_PUBLIC_CERT_PATH`, `AUA_P12_PATH`, `AUA_P12_PASSWORD`) supplies the
secrets. **Never commit `auth.cfg`, `*.p12`, or `*.cer`.**

## Verify your setup

```bash
cd backend
python scripts/aadhaar_sandbox_smoke.py --uid 999941057058 --otp 123456
```
It prints PASS/SKIP for each step: Verhoeff → PID → Skey (needs the cert) →
Data+Hmac → Sign (needs the `.p12` + signxml) → Send (`--send`, licensed AUA).
Green through **Sign** means your crypto/assembly is correct; a real `ret=y`
additionally needs a licensed AUA and a reachable UIDAI sandbox.

## Wire LIVE into the agent

```python
from app.swarm.connectors.aadhaar_auth import AadhaarAuthConnector, load_config
from app.swarm.connectors.aadhaar_live import AadhaarLiveClient, load_from_env

cfg = load_from_env(load_config("auth.cfg"))          # mode=live
connector = AadhaarAuthConnector(cfg, live_client=AadhaarLiveClient(cfg))
agent = IdentityFraudAgent(adapter=..., aadhaar_connector=connector)
```
OTP flow: `client.generate_otp(uid)` → user enters code → `authenticate(uid, otp=…)`.
Invalid Verhoeff is rejected **before** any transmission.

## The blockers, honestly

1. **AUA licence** — the `.p12` and a working license key exist only inside a
   registered AUA. Without that you cannot complete LIVE, full stop.
2. **Sandbox status** — UIDAI's old public `public/public` sandbox has been
   heavily restricted; the endpoint may no longer authenticate even with correct
   code. Confirm current access on the UIDAI developer portal.
3. **Reference crypto** — verify the encrypted-block byte-framing, the Skey `ci`
   format, and the XMLDSig profile against UIDAI's current spec before trusting a
   live result. Test with the sandbox test number `999941057058` first.

## If you can't get an AUA licence (common for a hackathon)

Front UIDAI through an **authorized KUA / e-KYC aggregator** (they hold the
licence; you call their REST API). The connector interface stays the same — you
implement their call in place of the direct UIDAI POST. For the demo itself,
**DEMO mode** already shows the full flow end-to-end with no licence needed.
