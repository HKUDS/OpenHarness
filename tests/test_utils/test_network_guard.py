"""Tests for outbound HTTP target validation."""

from __future__ import annotations

import ipaddress

import httpx
import pytest

from openharness.utils.network_guard import fetch_public_http_response


class FakeAsyncClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url, params=kwargs.get("params"))
        return httpx.Response(200, text="ok", request=request)


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))


@pytest.mark.asyncio
async def test_fetch_public_http_response_direct_rejects_non_public_dns(monkeypatch):
    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address("100.64.1.2")}

    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)

    with pytest.raises(ValueError, match="synthetic DNS"):
        await fetch_public_http_response("https://example.com/")


@pytest.mark.asyncio
async def test_fetch_public_http_response_synthetic_dns_allows_declared_cidr(monkeypatch):
    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address("100.64.1.2")}

    monkeypatch.setenv("OPENHARNESS_WEB_RESOLUTION_MODE", "synthetic_dns")
    monkeypatch.setenv("OPENHARNESS_WEB_SYNTHETIC_DNS_CIDRS", "100.64.0.0/10")
    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    response = await fetch_public_http_response("https://example.com/")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_fetch_public_http_response_synthetic_dns_uses_persisted_settings(
    monkeypatch,
):
    from openharness.config.settings import Settings, WebSettings, save_settings

    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address("100.64.1.2")}

    save_settings(
        Settings(
            web=WebSettings(
                resolution_mode="synthetic_dns",
                synthetic_dns_cidrs=["100.64.0.0/10"],
            )
        )
    )
    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    response = await fetch_public_http_response("https://example.com/")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_fetch_public_http_response_synthetic_dns_requires_declared_cidrs(monkeypatch):
    monkeypatch.setenv("OPENHARNESS_WEB_RESOLUTION_MODE", "synthetic_dns")

    with pytest.raises(ValueError, match="web.synthetic_dns_cidrs"):
        await fetch_public_http_response("https://example.com/")


@pytest.mark.asyncio
async def test_fetch_public_http_response_synthetic_dns_rejects_literal_non_public_ip(
    monkeypatch,
):
    monkeypatch.setenv("OPENHARNESS_WEB_RESOLUTION_MODE", "synthetic_dns")
    monkeypatch.setenv("OPENHARNESS_WEB_SYNTHETIC_DNS_CIDRS", "100.64.0.0/10")

    with pytest.raises(ValueError, match="non-public"):
        await fetch_public_http_response("http://100.64.1.2/")


@pytest.mark.asyncio
async def test_fetch_public_http_response_synthetic_dns_rejects_undeclared_private_dns(
    monkeypatch,
):
    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address("10.0.0.1")}

    monkeypatch.setenv("OPENHARNESS_WEB_RESOLUTION_MODE", "synthetic_dns")
    monkeypatch.setenv("OPENHARNESS_WEB_SYNTHETIC_DNS_CIDRS", "100.64.0.0/10")
    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)

    with pytest.raises(ValueError, match="non-public"):
        await fetch_public_http_response("https://example.com/")


@pytest.mark.asyncio
async def test_fetch_public_http_response_proxy_mode_does_not_resolve_target_dns(monkeypatch):
    async def fail_resolve(host: str, port: int):
        raise AssertionError("proxy mode should not resolve ordinary target domains locally")

    monkeypatch.setenv("OPENHARNESS_WEB_PROXY", "http://proxy.example.com:7890")
    monkeypatch.setenv("OPENHARNESS_WEB_SYNTHETIC_DNS_CIDRS", "not-a-cidr")
    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fail_resolve)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    response = await fetch_public_http_response("https://example.com/")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_fetch_public_http_response_proxy_mode_rejects_literal_non_public_ip(monkeypatch):
    monkeypatch.setenv("OPENHARNESS_WEB_PROXY", "http://proxy.example.com:7890")

    with pytest.raises(ValueError, match="non-public"):
        await fetch_public_http_response("http://127.0.0.1/")


@pytest.mark.asyncio
async def test_fetch_public_http_response_rejects_non_public_redirect_in_proxy_mode(
    monkeypatch,
):
    class RedirectClient(FakeAsyncClient):
        async def get(self, url: str, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", url, params=kwargs.get("params"))
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/"}, request=request)

    monkeypatch.setenv("OPENHARNESS_WEB_PROXY", "http://proxy.example.com:7890")
    monkeypatch.setattr(httpx, "AsyncClient", RedirectClient)

    with pytest.raises(ValueError, match="non-public"):
        await fetch_public_http_response("https://example.com/")


# ---------------------------------------------------------------------------
# TUN / fake-IP detection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fakeip",
    [
        "198.18.0.1",    # Clash / sing-box default (198.18.0.0/15)
        "198.19.255.1",  # upper end of 198.18.0.0/15
        "198.51.100.5",  # TEST-NET-2 (RFC 5737)
        "203.0.113.42",  # TEST-NET-3 (RFC 5737)
        "100.64.0.1",    # Shared Address Space (RFC 6598)
    ],
)
async def test_direct_mode_fakeip_error_includes_tun_hint(monkeypatch, fakeip):
    """When DNS returns a well-known fake-IP address the error message should
    name TUN/fake-IP and give copy-paste env-var instructions."""
    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address(fakeip)}

    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)

    with pytest.raises(ValueError) as exc_info:
        await fetch_public_http_response("https://example.com/")

    message = str(exc_info.value)
    assert "TUN" in message or "fake-IP" in message or "fake-ip" in message.lower(), message
    assert "OPENHARNESS_WEB_RESOLUTION_MODE=synthetic_dns" in message, message
    assert "OPENHARNESS_WEB_SYNTHETIC_DNS_CIDRS=" in message, message


@pytest.mark.asyncio
async def test_direct_mode_private_non_fakeip_uses_generic_hint(monkeypatch):
    """Private addresses outside known fake-IP ranges should use the generic
    synthetic DNS hint, not the TUN-specific one."""
    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address("10.0.0.1")}

    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)

    with pytest.raises(ValueError) as exc_info:
        await fetch_public_http_response("https://example.com/")

    message = str(exc_info.value)
    # generic hint present
    assert "synthetic DNS" in message, message
    # TUN-specific hint NOT present
    assert "OPENHARNESS_WEB_RESOLUTION_MODE=synthetic_dns" not in message, message


@pytest.mark.asyncio
async def test_synthetic_dns_mode_allows_fakeip_cidr(monkeypatch):
    """synthetic_dns mode with 198.18.0.0/15 declared must allow Clash fake-IP."""
    async def fake_resolve(host: str, port: int):
        return {ipaddress.ip_address("198.18.0.1")}

    monkeypatch.setenv("OPENHARNESS_WEB_RESOLUTION_MODE", "synthetic_dns")
    monkeypatch.setenv("OPENHARNESS_WEB_SYNTHETIC_DNS_CIDRS", "198.18.0.0/15")
    monkeypatch.setattr("openharness.utils.network_guard._resolve_host_addresses", fake_resolve)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    response = await fetch_public_http_response("https://example.com/")

    assert response.status_code == 200
