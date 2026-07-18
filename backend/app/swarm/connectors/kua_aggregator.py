"""
KUA / e-KYC aggregator client — the licence-free path to a real Aadhaar call.

Getting your own UIDAI AUA/KUA licence (and the .p12 signing keystore) is an
organizational process. A faster, common path: call a **UIDAI-authorized KYC
aggregator** (Signzy, Setu, Cashfree, Sandbox.co.in, Digitap, …). They hold the
licence and the crypto; you hold a simple REST API key. Aadhaar Offline e-KYC
via OTP is a two-call flow:

    1. generate_otp(uid) → aggregator sends an OTP to the linked mobile, returns a
       reference id (ref_id / client_id / transaction id).
    2. authenticate(uid, otp=…, ref_id=…) → aggregator verifies and returns the
       KYC result (valid / name / etc.).

This client is interface-compatible with `AadhaarLiveClient`, so it drops into
`AadhaarAuthConnector(live_client=…)` unchanged. Response schemas differ per
provider, so the field mapping is configurable (see AggregatorConfig).

Secrets (base URL, API key/token) come from config or env — never hardcode or
commit them. httpx transport is injectable so tests need no network.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger("veritas.swarm.kua")


@dataclass
class AggregatorConfig:
    provider: str = "generic"
    base_url: str = ""                 # e.g. https://api.provider.com/kyc/v1
    api_key: str = ""                  # bearer token / api key
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "    # set "" if the provider wants a bare key
    otp_path: str = "/aadhaar/okyc/otp"
    verify_path: str = "/aadhaar/okyc/verify"
    timeout: float = 15.0
    # Response field mapping (adapt to your provider's JSON schema).
    success_field: str = "valid"       # a truthy value here == verified
    success_values: tuple = (True, "true", "success", "VALID", "completed", 1, "1")
    ref_field: str = "ref_id"          # where generate_otp returns the reference
    message_field: str = "message"
    code_field: str = "code"

    @classmethod
    def from_env(cls, base: "AggregatorConfig | None" = None) -> "AggregatorConfig":
        cfg = base or cls()
        cfg.base_url = os.environ.get("KUA_BASE_URL", cfg.base_url)
        cfg.api_key = os.environ.get("KUA_API_KEY", cfg.api_key)
        cfg.provider = os.environ.get("KUA_PROVIDER", cfg.provider)
        return cfg


class KuaAggregatorClient:
    """
    live_client-compatible client that calls a KYC aggregator over REST.

    transport : optional httpx transport (e.g. httpx.MockTransport) for tests.
    """

    def __init__(self, config: AggregatorConfig, transport=None):
        self.config = config
        self._transport = transport

    def _require(self):
        missing = [n for n, v in (("base_url", self.config.base_url),
                                  ("api_key", self.config.api_key)) if not v]
        if missing:
            raise RuntimeError(
                f"KUA aggregator not configured. Missing: {missing}. "
                "Set KUA_BASE_URL / KUA_API_KEY (or AggregatorConfig). Never commit them."
            )

    def _client(self):
        import httpx

        headers = {self.config.api_key_header: f"{self.config.api_key_prefix}{self.config.api_key}",
                   "Content-Type": "application/json"}
        kwargs = {"base_url": self.config.base_url, "headers": headers, "timeout": self.config.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _post(self, path: str, payload: dict) -> dict:
        with self._client() as client:
            resp = client.post(path, json=payload)
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                data = {}
            data["_http_status"] = resp.status_code
            return data

    def _is_success(self, data: dict) -> bool:
        val = data.get(self.config.success_field)
        if val in self.config.success_values:
            return True
        # Fall back to nested data.{field} and HTTP 200 + explicit success.
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        return nested.get(self.config.success_field) in self.config.success_values

    # ── live_client interface ────────────────────────────────────────────────
    def generate_otp(self, uid: str, *, txn: str) -> dict:
        """Request an OTP. Returns {ret, txn, ref_id, err} (ref_id feeds authenticate)."""
        self._require()
        data = self._post(self.config.otp_path, {"aadhaar_number": uid, "txn": txn})
        ok = self._is_success(data) or data.get("_http_status") == 200
        ref = data.get(self.config.ref_field) or (data.get("data") or {}).get(self.config.ref_field)
        return {
            "ret": "y" if ok else "n",
            "txn": txn,
            "ref_id": ref,
            "err": None if ok else str(data.get(self.config.message_field) or "otp request failed"),
        }

    def authenticate(self, uid: str, *, otp: str | None = None, txn: str,
                     ref_id: str | None = None, **_ignored) -> dict:
        """Verify the OTP with the aggregator. Returns {ret, code, txn, err}."""
        self._require()
        if not otp:
            return {"ret": "n", "code": "", "txn": txn, "err": "otp required for e-KYC"}
        payload = {"aadhaar_number": uid, "otp": otp, "txn": txn}
        if ref_id:
            payload["ref_id"] = ref_id
        data = self._post(self.config.verify_path, payload)
        ok = self._is_success(data)
        return {
            "ret": "y" if ok else "n",
            "code": str(data.get(self.config.code_field) or data.get("_http_status") or ""),
            "txn": txn,
            "err": None if ok else str(data.get(self.config.message_field) or "verification failed"),
        }
