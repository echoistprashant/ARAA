import ipaddress
import socket
from urllib.parse import urlparse


class SSRFSecurityError(ValueError):
    """Raised when an outbound URL violates SSRF network perimeter boundaries."""
    pass


class SSRFValidator:
    """Rigorous SSRF (Server-Side Request Forgery) and DNS re-binding validation engine."""

    BLOCKED_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),      # Loopback
        ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
        ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
        ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
        ipaddress.ip_network("169.254.0.0/16"),   # Cloud metadata & Link-local
        ipaddress.ip_network("0.0.0.0/8"),        # Broadcast/Current network
        ipaddress.ip_network("::1/128"),          # IPv6 Loopback
        ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local
        ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
    ]

    def __init__(self, allowed_domains: list[str] | None = None, blocked_domains: list[str] | None = None):
        self.allowed_domains = set(d.lower() for d in allowed_domains) if allowed_domains is not None else None
        self.blocked_domains = set(d.lower() for d in (blocked_domains or []))

    def validate_url(self, url: str) -> str:
        """Validates that a URL is well-formed, uses http(s), and resolves only to public IPs."""
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise SSRFSecurityError(f"Malformed URL: {url} ({str(e)})")

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise SSRFSecurityError(f"Prohibited URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise SSRFSecurityError("URL is missing a valid hostname.")

        if hostname in self.blocked_domains:
            raise SSRFSecurityError(f"Access to blocked domain '{hostname}' is denied.")

        if self.allowed_domains is not None and hostname not in self.allowed_domains:
            raise SSRFSecurityError(f"Domain '{hostname}' is not in the authorized allowlist.")

        # Check raw IP directly if provided as hostname
        try:
            ip = ipaddress.ip_address(hostname)
            for network in self.BLOCKED_NETWORKS:
                if ip in network:
                    raise SSRFSecurityError(f"SSRF violation: Host IP {ip} resides in forbidden private subnet {network}.")
            return url
        except ValueError:
            pass  # Not a raw IP literal, proceed to DNS resolution

        # Resolve hostname to IPv4/IPv6 addresses
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                ip = ipaddress.ip_address(ip_str)
                for network in self.BLOCKED_NETWORKS:
                    if ip in network:
                        raise SSRFSecurityError(
                            f"SSRF violation: Hostname '{hostname}' resolves to private/internal IP {ip}."
                        )
        except socket.gaierror as e:
            # If DNS resolution fails, reject defensively
            raise SSRFSecurityError(f"DNS resolution failure for '{hostname}': {str(e)}")

        return url
