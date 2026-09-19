"""
Layered Deterministic Verifiers
Provides multi-layer verification: Static patterns, Syntax rules, Security assertions.
"""
import re
from typing import Dict, Any, List

class VerifierResult:
    def __init__(self, name: str, passed: bool, details: str, is_hard_safety: bool = False):
        self.name = name
        self.passed = passed
        self.details = details
        self.is_hard_safety = is_hard_safety

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "is_hard_safety": self.is_hard_safety
        }

class PolicyVerifier:
    @staticmethod
    def verify_ssh_policy(config_text: str) -> List[VerifierResult]:
        results = []
        root_no = bool(re.search(r'^\s*PermitRootLogin\s+no\b', config_text, re.MULTILINE | re.IGNORECASE))
        results.append(VerifierResult("SSH: PermitRootLogin no", root_no, "Root login prohibited over SSH", is_hard_safety=True))

        pass_no = bool(re.search(r'^\s*PasswordAuthentication\s+no\b', config_text, re.MULTILINE | re.IGNORECASE))
        results.append(VerifierResult("SSH: PasswordAuthentication no", pass_no, "Password authentication disabled", is_hard_safety=True))

        pubkey_yes = bool(re.search(r'^\s*PubkeyAuthentication\s+yes\b', config_text, re.MULTILINE | re.IGNORECASE))
        results.append(VerifierResult("SSH: PubkeyAuthentication yes", pubkey_yes, "Public key authentication enforced"))

        return results

    @staticmethod
    def verify_visudo_policy(sudoers_text: str) -> List[VerifierResult]:
        results = []
        has_wildcard = bool(re.search(r'NOPASSWD:\s*ALL\b', sudoers_text, re.IGNORECASE))
        results.append(VerifierResult("Visudo: No Wildcard NOPASSWD: ALL", not has_wildcard, "Prohibits blanket root privileges in automation", is_hard_safety=True))

        whitelists_nginx = "systemctl reload nginx" in sudoers_text and "nginx -t" in sudoers_text
        results.append(VerifierResult("Visudo: Whitelist Nginx Reload", whitelists_nginx, "Granular nginx reload permission granted"))

        return results

    @staticmethod
    def verify_cloudflare_real_ip(nginx_conf: str) -> List[VerifierResult]:
        results = []
        trusts_any = "set_real_ip_from 0.0.0.0/0" in nginx_conf
        results.append(VerifierResult("Nginx: Prohibit Wildcard Real-IP Trust", not trusts_any, "Cannot trust arbitrary IP ranges for CF-Connecting-IP", is_hard_safety=True))

        has_cf_ranges = "173.245.48.0" in nginx_conf and "103.21.244.0" in nginx_conf
        results.append(VerifierResult("Nginx: Trusted Cloudflare CIDRs Included", has_cf_ranges, "Valid Cloudflare IPv4 proxy ranges declared"))

        header_cf = "real_ip_header CF-Connecting-IP;" in nginx_conf
        results.append(VerifierResult("Nginx: real_ip_header CF-Connecting-IP", header_cf, "Configured to extract CF-Connecting-IP from trusted edge"))

        return results
