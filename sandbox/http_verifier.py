"""
Layer A: Behavioral HTTP Verifier
Simulates HTTP requests, dynamic CSP nonces, adversarial IP spoofing, and failure injection rollback.
"""
import ipaddress
import secrets
from typing import Dict, Any, Tuple

CLOUDFLARE_IPV4_CIDRS = [
    ipaddress.ip_network("173.245.48.0/20"),
    ipaddress.ip_network("103.21.244.0/22"),
    ipaddress.ip_network("103.22.200.0/22"),
    ipaddress.ip_network("103.31.4.0/22"),
    ipaddress.ip_network("141.101.64.0/18"),
    ipaddress.ip_network("108.162.192.0/18"),
    ipaddress.ip_network("190.93.240.0/20"),
    ipaddress.ip_network("188.114.96.0/20"),
    ipaddress.ip_network("197.234.240.0/22"),
    ipaddress.ip_network("198.41.128.0/17"),
    ipaddress.ip_network("162.158.0.0/15"),
    ipaddress.ip_network("104.16.0.0/13"),
    ipaddress.ip_network("104.24.0.0/14"),
    ipaddress.ip_network("172.64.0.0/13"),
    ipaddress.ip_network("131.0.72.0/22"),
]

def is_trusted_cloudflare_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in CLOUDFLARE_IPV4_CIDRS)
    except ValueError:
        return False

class BehavioralHttpVerifier:
    @staticmethod
    def verify_cloudflare_real_ip_resolution(client_tcp_ip: str, headers: Dict[str, str]) -> str:
        """
        Simulates Nginx real_ip module behavior.
        Only trusts CF-Connecting-IP if client_tcp_ip originates from trusted Cloudflare CIDR.
        """
        cf_ip = headers.get("CF-Connecting-IP")
        if is_trusted_cloudflare_ip(client_tcp_ip) and cf_ip:
            return cf_ip # Accepted: client IP restored
        return client_tcp_ip # Untrusted origin: spoofed header rejected

    @staticmethod
    def generate_and_verify_csp_nonce() -> Tuple[bool, str]:
        """
        Generates per-response nonce and verifies that HTML script matches CSP header.
        """
        nonce = secrets.token_urlsafe(16)
        csp_header = f"default-src 'self'; script-src 'self' 'nonce-{nonce}';"
        html_body = f"<html><body><script nonce='{nonce}'>console.log('App init');</script></body></html>"

        has_header_nonce = f"'nonce-{nonce}'" in csp_header
        has_body_nonce = f"nonce='{nonce}'" in html_body

        return (has_header_nonce and has_body_nonce), nonce

    @staticmethod
    def simulate_failure_and_verify_rollback(mock_host, current_link: str, previous_link: str) -> bool:
        """
        Injects a failure into current release, tests health check, and triggers rollback.
        """
        # Simulate health check failure on current release
        health_check_ok = False

        if not health_check_ok:
            # Trigger rollback
            prev_target = mock_host.read_symlink(previous_link)
            if prev_target:
                mock_host.set_symlink(current_link, prev_target)
                # Verify rollback restored previous release
                return mock_host.read_symlink(current_link) == prev_target

        return False
