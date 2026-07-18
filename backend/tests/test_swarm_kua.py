"""
KUA aggregator client tests — mocked HTTP transport, no network.

Proves the two-call OKYC flow (generate_otp → authenticate), the configurable
success mapping, the not-configured guard, and that it drops into
AadhaarAuthConnector as a live_client.
"""

from __future__ import annotations

import pytest

httpx = pytest.importorskip("httpx")

from app.swarm.connectors import (
    AadhaarAuthConnector,
    AggregatorConfig,
    AuaConfig,
    KuaAggregatorClient,
)

VALID = "999941057058"


def _client(handler, **cfg_overrides):
    cfg = AggregatorConfig(base_url="https://api.test/kyc", api_key="k", **cfg_overrides)
    return KuaAggregatorClient(cfg, transport=httpx.MockTransport(handler))


def test_generate_otp_returns_ref_id():
    def handler(request):
        assert request.url.path.endswith("/otp")
        return httpx.Response(200, json={"valid": True, "ref_id": "REF123"})
    r = _client(handler).generate_otp(VALID, txn="t1")
    assert r["ret"] == "y" and r["ref_id"] == "REF123"


def test_authenticate_success_maps_to_y():
    def handler(request):
        assert request.url.path.endswith("/verify")
        body = request.read().decode()
        assert "otp" in body
        return httpx.Response(200, json={"valid": True, "code": "200"})
    r = _client(handler).authenticate(VALID, otp="123456", txn="t1", ref_id="REF123")
    assert r["ret"] == "y" and r["code"] == "200" and r["err"] is None


def test_authenticate_failure_maps_to_n():
    def handler(request):
        return httpx.Response(200, json={"valid": False, "message": "OTP mismatch"})
    r = _client(handler).authenticate(VALID, otp="000000", txn="t1")
    assert r["ret"] == "n" and r["err"] == "OTP mismatch"


def test_authenticate_requires_otp():
    r = _client(lambda req: httpx.Response(200, json={})).authenticate(VALID, txn="t1")
    assert r["ret"] == "n" and "otp required" in r["err"]


def test_nested_data_success_mapping():
    def handler(request):
        return httpx.Response(200, json={"status": "ok", "data": {"valid": "success"}})
    r = _client(handler).authenticate(VALID, otp="123456", txn="t1")
    assert r["ret"] == "y"


def test_not_configured_raises():
    client = KuaAggregatorClient(AggregatorConfig())   # no base_url/api_key
    with pytest.raises(RuntimeError):
        client.generate_otp(VALID, txn="t1")


def test_drops_into_connector_as_live_client():
    def handler(request):
        return httpx.Response(200, json={"valid": True, "code": "200"})
    kua = _client(handler)
    conn = AadhaarAuthConnector(AuaConfig(mode="live"), live_client=kua)
    result = conn.verify(VALID, otp="123456", txn="t1")
    assert result.ret == "y" and result.mode == "live"
    assert result.masked_uid == "XXXX XXXX 7058"


def test_env_config(monkeypatch):
    monkeypatch.setenv("KUA_BASE_URL", "https://env.provider/api")
    monkeypatch.setenv("KUA_API_KEY", "env-key")
    cfg = AggregatorConfig.from_env()
    assert cfg.base_url == "https://env.provider/api" and cfg.api_key == "env-key"
