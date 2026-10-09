"""
scraper/utils/ssrf.py
---------------------
Centralized SSRF (Server-Side Request Forgery) protection boundary.
Validates user-supplied URLs against private, loopback, link-local,
reserved, and cloud metadata destinations. Enforces safe bounded redirect
inspection so redirects cannot bypass the validation boundary.
"""

import socket
import urllib.parse
import ipaddress
import logging
from typing import List, Dict, Any, Optional, Union

import requests
from scraper.utils.exceptions import ScraperException

logger = logging.getLogger(__name__)


class SSRFValidationError(ScraperException, ValueError):
    """Raised when a URL violates SSRF security boundaries."""
    pass


# Disallowed hostnames and domains
DISALLOWED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata.local",
    "metadata",
    "instance-data",
}

# Special reserved, benchmark, and carrier-grade NAT networks
DISALLOWED_NETWORKS = [
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-Grade NAT (includes 100.100.100.200 metadata)
    ipaddress.ip_network("198.18.0.0/15"),     # Network interconnect benchmark tests
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved / Future use
    ipaddress.ip_network("0.0.0.0/8"),         # Current network (default route)
]

# Sensitive internal service ports that should not be targeted via SSRF
BLOCKED_PORTS = {
    20, 21,    # FTP
    22,        # SSH
    23,        # Telnet
    25,        # SMTP
    53,        # DNS
    69,        # TFTP
    110,       # POP3
    119,       # NNTP
    123,       # NTP
    135, 137, 138, 139, # NetBIOS / SMB
    143,       # IMAP
    161,       # SNMP
    389,       # LDAP
    445,       # SMB
    636,       # LDAPS
    1433,      # MSSQL
    1521,      # Oracle
    2049,      # NFS
    2375, 2376,# Docker API
    2379, 2380,# etcd
    3306,      # MySQL
    3389,      # RDP
    5432,      # PostgreSQL
    5900,      # VNC
    6379,      # Redis
    6443,      # Kubernetes API
    8500,      # HashiCorp Consul
    9200,      # Elasticsearch
    11211,     # Memcached
    27017, 28017 # MongoDB
}


def is_ip_allowed(ip: Union[str, ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """
    Checks if an IP address is a safe, routable public IP.
    Rejects private, loopback, link-local, multicast, unspecified, reserved,
    and cloud provider metadata addresses.
    """
    if isinstance(ip, str):
        try:
            ip = ipaddress.ip_address(ip)
        except ValueError:
            return False

    # Handle IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    # Check standard RFC ipaddress flags
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        return False

    # Check specific disallowed networks (CGNAT, benchmark, doc ranges)
    for net in DISALLOWED_NETWORKS:
        if ip in net:
            return False

    # Check explicit AWS IPv6 metadata address
    if str(ip).lower() == "fd00:ec2::254":
        return False

    return True


def is_hostname_allowed(hostname: str) -> bool:
    """
    Checks if a hostname is allowed.
    Rejects localhost aliases, cloud metadata names, and internal TLDs.
    """
    if not hostname:
        return False
    host_clean = hostname.strip().lower()

    if host_clean in DISALLOWED_HOSTNAMES:
        return False
    if host_clean.endswith(".localhost"):
        return False
    if host_clean.endswith(".metadata.google.internal"):
        return False
    if (
        host_clean.endswith(".internal")
        or host_clean.endswith(".local")
        or host_clean.endswith(".lan")
        or host_clean.endswith(".corp")
    ):
        return False

    return True


def resolve_all_ips(hostname: str, port: int = 80) -> List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    """
    Resolves all IPv4 and IPv6 addresses for a hostname using socket.getaddrinfo.
    Returns a list of parsed ipaddress objects.
    """
    # Literal IP check
    try:
        literal = ipaddress.ip_address(hostname)
        return [literal]
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFValidationError(f"Could not resolve host '{hostname}': {e}") from e

    ips = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ips.append(ipaddress.ip_address(ip_str))
        except ValueError:
            pass

    if not ips:
        raise SSRFValidationError(f"No IP addresses resolved for host '{hostname}'")

    return ips


def validate_url_for_ssrf(url: str, resolve_dns: bool = True) -> str:
    """
    Validates a URL against SSRF attack vectors.
    Enforces scheme, hostname, port, credential, and IP checks.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL must be a non-empty string")

    url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception as e:
        raise SSRFValidationError(f"Malformed URL: {e}") from e

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFValidationError(f"Disallowed URL scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    if not parsed.netloc:
        raise SSRFValidationError("URL must contain a valid host")

    if parsed.username or parsed.password:
        raise SSRFValidationError("URLs with embedded credentials are not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("Could not extract hostname from URL")

    if not is_hostname_allowed(hostname):
        raise SSRFValidationError(f"Host '{hostname}' is not permitted")

    # Port checking
    if parsed.port is not None:
        if parsed.port < 1 or parsed.port > 65535:
            raise SSRFValidationError(f"Invalid port: {parsed.port}")
        if parsed.port in BLOCKED_PORTS:
            raise SSRFValidationError(f"Port {parsed.port} is blocked for security")

    # DNS and destination IP validation
    if resolve_dns:
        port = parsed.port or (443 if scheme == "https" else 80)
        resolved_ips = resolve_all_ips(hostname, port)
        for ip in resolved_ips:
            if not is_ip_allowed(ip):
                raise SSRFValidationError(f"Host '{hostname}' resolves to prohibited IP address: {ip}")

    return url


def safe_fetch_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    max_redirects: int = 5,
    verify: bool = True,
    method: str = "GET",
    session: Optional[requests.Session] = None,
    **kwargs
) -> requests.Response:
    """
    Safely fetches a URL enforcing preflight SSRF validation and per-hop redirect validation.
    Prevents redirects from escaping into internal networks or cloud metadata.
    """
    current_url = url
    redirects_followed = 0
    http_client = session or requests

    while True:
        # Validate target destination and DNS before making the request
        validated_url = validate_url_for_ssrf(current_url, resolve_dns=True)

        resp = http_client.request(
            method=method,
            url=validated_url,
            headers=headers,
            timeout=timeout,
            verify=verify,
            allow_redirects=False,
            **kwargs
        )

        # Check for HTTP redirect response
        if resp.status_code in (301, 302, 303, 307, 308) and "Location" in resp.headers:
            redirects_followed += 1
            if redirects_followed > max_redirects:
                raise requests.TooManyRedirects(f"Exceeded maximum redirects ({max_redirects})")

            location = resp.headers["Location"].strip()
            # Resolve relative redirects against current URL
            next_url = urllib.parse.urljoin(current_url, location)

            if resp.status_code == 303:
                method = "GET"

            current_url = next_url
            continue

        return resp
