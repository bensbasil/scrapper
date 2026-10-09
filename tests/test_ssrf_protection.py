"""
tests/test_ssrf_protection.py
-----------------------------
Comprehensive regression tests for Phase 5B P0-2: SSRF Protection.
Verifies:
1. Localhost and loopback rejection (IPv4, IPv6, hostnames).
2. Private, link-local, and reserved IP address rejection.
3. Cloud metadata endpoint rejection (AWS, GCP, Azure, Alibaba).
4. Malformed URLs, embedded credentials, and unsupported schemes rejection.
5. Hostnames resolving to private addresses rejection (DNS resolution check).
6. Safe bounded redirect protection preventing redirects to internal targets.
7. Valid public business URL acceptance.
8. Integration with WebsiteAnalyzer, TechSignalAnalyzer, and AuditWebsiteTechCapability.

All DNS lookups and HTTP requests use deterministic mocks to ensure no network calls.
"""

import socket
import pytest
from unittest.mock import patch, MagicMock

import requests
from scraper.utils.ssrf import (
    validate_url_for_ssrf,
    safe_fetch_url,
    is_ip_allowed,
    is_hostname_allowed,
    SSRFValidationError,
)
from scraper.connectors.public_web.company_website import WebsiteAnalyzer
from scraper.connectors.technical.tech_signals import TechSignalAnalyzer
from application.capabilities.website_audit import AuditWebsiteTechCapability
from application.contracts.inputs import AuditWebsiteTechInput


def mock_getaddrinfo_public(host, port, *args, **kwargs):
    """Deterministic mock resolving any domain to a public routable IP."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port)),
    ]


def mock_getaddrinfo_private(host, port, *args, **kwargs):
    """Deterministic mock resolving any domain to a private RFC 1918 IP."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', port)),
    ]


def mock_getaddrinfo_loopback(host, port, *args, **kwargs):
    """Deterministic mock resolving domain to 127.0.0.1."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', port)),
    ]


# -----------------------------------------------------------------------------
# 1. Localhost & Loopback
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost",
    "http://localhost:8000",
    "https://localhost:443",
    "http://localhost.localdomain",
    "http://foo.localhost",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "http://127.0.0.2",
    "http://127.255.255.254",
    "http://[::1]",
    "http://[::1]:8000",
])
def test_localhost_and_loopback_rejected(url):
    with pytest.raises(SSRFValidationError):
        validate_url_for_ssrf(url)


# -----------------------------------------------------------------------------
# 2. Private, Link-Local, and Reserved IP Addresses
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://10.0.0.1",
    "http://10.254.254.254:80",
    "http://172.16.0.1",
    "http://172.31.255.255",
    "http://192.168.0.1",
    "http://192.168.1.100",
    "http://169.254.0.1",         # Link-local
    "http://169.254.100.100",
    "http://0.0.0.0",             # Unspecified
    "http://[fe80::1]",           # Link-local IPv6
    "http://[fc00::1]",           # Unique local IPv6
    "http://[::ffff:127.0.0.1]",  # IPv4-mapped loopback
    "http://[::ffff:10.0.0.1]",   # IPv4-mapped private
])
def test_private_and_link_local_ip_rejected(url):
    with pytest.raises(SSRFValidationError):
        validate_url_for_ssrf(url)


# -----------------------------------------------------------------------------
# 3. Cloud Metadata Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://169.254.169.254",
    "http://169.254.169.254/latest/meta-data/",
    "http://169.254.169.254/computeMetadata/v1/",
    "http://metadata.google.internal",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://sub.metadata.google.internal",
    "http://metadata.local",
    "http://instance-data",
    "http://100.100.100.200",      # Alibaba metadata
    "http://[fd00:ec2::254]",      # AWS IPv6 metadata
])
def test_cloud_metadata_endpoints_rejected(url):
    with pytest.raises(SSRFValidationError):
        validate_url_for_ssrf(url)


# -----------------------------------------------------------------------------
# 4. Malformed URLs, Embedded Credentials, Schemes, and Blocked Ports
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ftp://example.com/file.txt",
    "file:///etc/passwd",
    "gopher://127.0.0.1:70",
    "javascript:alert(1)",
    "data:text/plain;base64,SGVsbG8=",
    "http://admin:secret@example.com",
    "http://user@example.com",
    "http://",
    "",
    "   ",
    "http://example.com:22",      # Blocked SSH port
    "http://example.com:25",      # Blocked SMTP port
    "http://example.com:3306",    # Blocked MySQL port
    "http://example.com:5432",    # Blocked Postgres port
    "http://example.com:6379",    # Blocked Redis port
    "http://example.com:27017",   # Blocked MongoDB port
])
def test_malformed_urls_and_schemes_rejected(url):
    with pytest.raises(SSRFValidationError):
        validate_url_for_ssrf(url)


# -----------------------------------------------------------------------------
# 5. Hostnames Resolving to Private Addresses
# -----------------------------------------------------------------------------

def test_hostnames_resolving_to_private_address_rejected():
    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo_private):
        with pytest.raises(SSRFValidationError) as exc:
            validate_url_for_ssrf("http://internal-portal.corp.com")
        assert "resolves to prohibited ip address" in str(exc.value).lower()


def test_hostnames_resolving_to_loopback_rejected():
    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo_loopback):
        with pytest.raises(SSRFValidationError) as exc:
            validate_url_for_ssrf("http://dev.mycompany.org")
        assert "resolves to prohibited ip address" in str(exc.value).lower()


# -----------------------------------------------------------------------------
# 6. Safe Bounded Redirects Targeting Prohibited Destinations
# -----------------------------------------------------------------------------

def test_redirect_to_metadata_endpoint_blocked():
    """An initial public URL returning a redirect to 169.254.169.254 must be blocked."""
    # First request returns redirect response
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo_public):
        with patch("requests.request", return_value=mock_resp):
            with pytest.raises(SSRFValidationError) as exc:
                safe_fetch_url("https://benign-looking-site.com")
            assert "prohibited ip address" in str(exc.value).lower() or "not permitted" in str(exc.value).lower()


def test_redirect_to_internal_network_blocked():
    """A redirect towards a private RFC 1918 IP must be blocked before fetching."""
    mock_resp = MagicMock()
    mock_resp.status_code = 301
    mock_resp.headers = {"Location": "http://192.168.1.1/admin"}

    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo_public):
        with patch("requests.request", return_value=mock_resp):
            with pytest.raises(SSRFValidationError):
                safe_fetch_url("https://benign-looking-site.com")


def test_redirect_loop_bounded():
    """A circular redirect chain must hit max_redirects limit safely."""
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "https://benign-looking-site.com/loop"}

    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo_public):
        with patch("requests.request", return_value=mock_resp):
            with pytest.raises(requests.TooManyRedirects):
                safe_fetch_url("https://benign-looking-site.com", max_redirects=3)


# -----------------------------------------------------------------------------
# 7. Valid Public URL Behavior
# -----------------------------------------------------------------------------

def test_valid_public_url_succeeds():
    """Legitimate public domains pass validation and fetch safely."""
    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo_public):
        validated = validate_url_for_ssrf("https://acme-plumbing.com")
        assert validated == "https://acme-plumbing.com"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><head><title>Acme Plumbing</title></head><body><h1>Welcome</h1></body></html>"
        mock_resp.url = "https://acme-plumbing.com"
        mock_resp.headers = {}

        with patch("requests.request", return_value=mock_resp):
            res = safe_fetch_url("https://acme-plumbing.com")
            assert res.status_code == 200
            assert "Acme Plumbing" in res.text


# -----------------------------------------------------------------------------
# 8. Callers Enforce SSRF Protection
# -----------------------------------------------------------------------------

def test_website_analyzer_blocks_ssrf_without_network_call():
    """WebsiteAnalyzer must catch SSRF URLs and return a structured failure result."""
    analyzer = WebsiteAnalyzer()
    with patch("requests.get") as mock_req_get:
        result = analyzer.analyze_url("Localhost Test", "http://127.0.0.1:8000")
        assert result.website_exists is False
        assert "ssrf blocked" in result.error.lower()
        mock_req_get.assert_not_called()


def test_tech_signal_analyzer_blocks_ssrf_without_network_call():
    """TechSignalAnalyzer must abort when domain resolves to disallowed target."""
    analyzer = TechSignalAnalyzer()
    with patch("socket.gethostbyname") as mock_sock:
        signals = analyzer.fetch_raw("http://169.254.169.254")
        assert signals.get("has_ssl") is False
        assert signals.get("resolves") is False
        mock_sock.assert_not_called()


def test_capability_audit_website_blocks_ssrf_safely():
    """AuditWebsiteTechCapability must return safe output without executing analyzers on SSRF target."""
    cap = AuditWebsiteTechCapability()
    output = cap.execute(
        AuditWebsiteTechInput(
            business_name="Evil Test",
            website_url="http://169.254.169.254/latest/meta-data/"
        )
    )
    assert output.is_active is False
    assert output.has_ssl is False
    assert "ssrf blocked" in output.raw_details["error"].lower()
