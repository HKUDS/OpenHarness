"""HTTP target validation helpers for outbound web tools."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from enum import Enum
from urllib.parse import ParseResult, urljoin, urlparse

import httpx


_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
}
_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
_SYNTHETIC_DNS_CIDRS_SETTING = "web.synthetic_dns_cidrs"
_RESOLUTION_MODE_SETTING = "web.resolution_mode"
_PROXY_SETTING = "web.proxy"
_LOCAL_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}
_LOCAL_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".cluster.local",
)


class ResolutionMode(str, Enum):
    """How outbound web tools should interpret target DNS resolution."""

    AUTO = "auto"
    DIRECT = "direct"
    PROXY = "proxy"
    SYNTHETIC_DNS = "synthetic_dns"


class NetworkGuardError(ValueError):
    """Raised when an outbound HTTP target violates security policy."""


def validate_http_url(url: str) -> None:
    """Validate basic HTTP/HTTPS URL syntax."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise NetworkGuardError("only http and https URLs are allowed")
    if not parsed.netloc or not parsed.hostname:
        raise NetworkGuardError("URL must include a host")
    if parsed.username or parsed.password:
        raise NetworkGuardError("URLs with embedded credentials are not allowed")


def get_web_resolution_mode(
    proxy: str | None = None,
    *,
    configured_mode: str | None = None,
) -> ResolutionMode:
    """Resolve the configured web target validation mode."""
    raw_mode = (configured_mode or "").strip().lower().replace("-", "_")
    if not raw_mode or raw_mode == ResolutionMode.AUTO.value:
        return ResolutionMode.PROXY if proxy else ResolutionMode.DIRECT
    try:
        mode = ResolutionMode(raw_mode)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in ResolutionMode)
        raise NetworkGuardError(f"{_RESOLUTION_MODE_SETTING} must be one of: {allowed}") from exc
    if mode is ResolutionMode.AUTO:
        return ResolutionMode.PROXY if proxy else ResolutionMode.DIRECT
    if mode is ResolutionMode.PROXY and not proxy:
        raise NetworkGuardError(f"{_RESOLUTION_MODE_SETTING}=proxy requires {_PROXY_SETTING}")
    return mode


def parse_synthetic_dns_cidrs(value: str | None = None) -> tuple[_IPNetwork, ...]:
    """Parse user-declared synthetic DNS CIDRs."""
    raw_value = "" if value is None else value
    entries = [entry.strip() for entry in raw_value.split(",") if entry.strip()]
    networks: list[_IPNetwork] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError as exc:
            raise NetworkGuardError(f"invalid {_SYNTHETIC_DNS_CIDRS_SETTING} entry: {entry}") from exc
    return tuple(networks)


async def ensure_public_http_url(url: str) -> None:
    """Reject loopback, private-network, and other non-public HTTP targets."""
    parsed = _validated_parsed_http_url(url)
    hostname = _normalized_hostname(parsed.hostname)
    literal = _parse_ip_literal(hostname)
    if literal is not None:
        _ensure_global_literal_ip(literal)
        return
    _ensure_not_local_hostname(hostname)
    port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
    addresses = await _resolve_host_addresses(hostname, port)
    if not addresses:
        raise NetworkGuardError(f"target host did not resolve: {hostname}")

    blocked = sorted({str(address) for address in addresses if not address.is_global})
    if blocked:
        raise NetworkGuardError(_format_blocked_addresses(blocked, include_synthetic_dns_hint=True))


async def ensure_http_url_allowed(
    url: str,
    *,
    mode: ResolutionMode,
    synthetic_cidrs: tuple[_IPNetwork, ...] = (),
) -> None:
    """Validate one outbound URL according to the configured resolution mode."""
    if mode is ResolutionMode.DIRECT:
        await ensure_public_http_url(url)
        return
    if mode is ResolutionMode.PROXY:
        _ensure_proxy_safe_http_url(url)
        return
    await _ensure_synthetic_dns_safe_http_url(url, synthetic_cidrs=synthetic_cidrs)


async def fetch_public_http_response(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = 15.0,
    max_redirects: int = 5,
    proxy: str | None = None,
) -> httpx.Response:
    """Fetch one HTTP resource while validating every redirect hop."""
    current_url = url
    current_params = params

    web_settings = _load_configured_web_settings()
    resolved_proxy = proxy if proxy is not None else web_settings.proxy
    if resolved_proxy:
        validate_http_url(resolved_proxy)
    mode = get_web_resolution_mode(
        resolved_proxy,
        configured_mode=web_settings.resolution_mode,
    )
    synthetic_cidrs = (
        parse_synthetic_dns_cidrs(",".join(web_settings.synthetic_dns_cidrs))
        if mode is ResolutionMode.SYNTHETIC_DNS
        else ()
    )

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        proxy=resolved_proxy,
    ) as client:
        for redirect_count in range(max_redirects + 1):
            await ensure_http_url_allowed(
                current_url,
                mode=mode,
                synthetic_cidrs=synthetic_cidrs,
            )
            response = await client.get(
                current_url,
                params=current_params,
                headers=headers,
            )
            if not response.has_redirect_location:
                return response

            location = response.headers.get("location")
            if not location:
                return response
            if redirect_count >= max_redirects:
                raise NetworkGuardError(f"too many redirects (>{max_redirects})")

            current_url = urljoin(str(response.url), location)
            current_params = None

    raise NetworkGuardError("request failed before receiving a response")


class _ConfiguredWebSettings:
    def __init__(
        self,
        *,
        proxy: str | None,
        resolution_mode: str,
        synthetic_dns_cidrs: list[str],
    ) -> None:
        self.proxy = proxy
        self.resolution_mode = resolution_mode
        self.synthetic_dns_cidrs = synthetic_dns_cidrs


def _load_configured_web_settings() -> _ConfiguredWebSettings:
    """Load persisted web settings, including environment overrides."""
    from openharness.config import load_settings

    web = load_settings().web
    return _ConfiguredWebSettings(
        proxy=web.proxy,
        resolution_mode=web.resolution_mode,
        synthetic_dns_cidrs=list(web.synthetic_dns_cidrs),
    )


def _ensure_proxy_safe_http_url(url: str) -> None:
    """Validate a URL whose hostname will be resolved by an explicit proxy."""
    parsed = _validated_parsed_http_url(url)
    hostname = _normalized_hostname(parsed.hostname)
    literal = _parse_ip_literal(hostname)
    if literal is not None:
        _ensure_global_literal_ip(literal)
        return
    _ensure_not_local_hostname(hostname)


async def _ensure_synthetic_dns_safe_http_url(
    url: str,
    *,
    synthetic_cidrs: tuple[_IPNetwork, ...],
) -> None:
    """Validate a URL in a user-declared synthetic DNS environment."""
    if not synthetic_cidrs:
        raise NetworkGuardError(
            f"{ResolutionMode.SYNTHETIC_DNS.value} mode requires {_SYNTHETIC_DNS_CIDRS_SETTING}"
        )
    parsed = _validated_parsed_http_url(url)
    hostname = _normalized_hostname(parsed.hostname)
    literal = _parse_ip_literal(hostname)
    if literal is not None:
        _ensure_global_literal_ip(literal)
        return
    _ensure_not_local_hostname(hostname)
    port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
    addresses = await _resolve_host_addresses(hostname, port)
    if not addresses:
        raise NetworkGuardError(f"target host did not resolve: {hostname}")

    blocked = sorted(
        {
            str(address)
            for address in addresses
            if not address.is_global and not _address_in_networks(address, synthetic_cidrs)
        }
    )
    if blocked:
        raise NetworkGuardError(_format_blocked_addresses(blocked))


async def _resolve_host_addresses(host: str, port: int) -> set[_IPAddress]:
    """Resolve a host into concrete IP addresses."""
    literal = _parse_ip_literal(host)
    if literal is not None:
        return {literal}

    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            port,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise NetworkGuardError(f"could not resolve target host {host}: {exc}") from exc

    addresses: set[_IPAddress] = set()
    for family, _, _, _, sockaddr in infos:
        if family == socket.AF_INET:
            candidate = sockaddr[0]
        elif family == socket.AF_INET6:
            candidate = sockaddr[0]
        else:
            continue
        if not isinstance(candidate, str):
            continue
        parsed = _parse_ip_literal(candidate)
        if parsed is not None:
            addresses.add(parsed)
    return addresses


def _parse_ip_literal(value: str) -> _IPAddress | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _validated_parsed_http_url(url: str) -> ParseResult:
    validate_http_url(url)
    parsed = urlparse(url)
    assert parsed.hostname is not None  # covered by validate_http_url
    return parsed


def _normalized_hostname(hostname: str | None) -> str:
    assert hostname is not None  # covered by validate_http_url
    return hostname.rstrip(".").lower()


def _ensure_global_literal_ip(address: _IPAddress) -> None:
    if not address.is_global:
        raise NetworkGuardError(f"target resolves to non-public address(es): {address}")


def _ensure_not_local_hostname(hostname: str) -> None:
    if hostname in _LOCAL_HOSTNAMES or any(hostname.endswith(suffix) for suffix in _LOCAL_HOST_SUFFIXES):
        raise NetworkGuardError(f"local hostnames are not allowed: {hostname}")
    if "." not in hostname:
        raise NetworkGuardError(f"single-label hostnames are not allowed: {hostname}")


def _address_in_networks(address: _IPAddress, networks: tuple[_IPNetwork, ...]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def _format_blocked_addresses(
    blocked: list[str],
    *,
    include_synthetic_dns_hint: bool = False,
) -> str:
    rendered = ", ".join(blocked[:3])
    if len(blocked) > 3:
        rendered += ", ..."
    message = f"target resolves to non-public address(es): {rendered}"
    if include_synthetic_dns_hint:
        message += (
            "; if this domain intentionally resolves through synthetic DNS, configure "
            "web.resolution_mode=synthetic_dns and web.synthetic_dns_cidrs=<cidr>"
        )
    return message
