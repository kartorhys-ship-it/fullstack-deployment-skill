"""
Deterministic Policy Engine & Precondition Verifiers
Enforces hard safety invariants, precondition checks, and credential protection.
"""
import re
from typing import Dict, Any, List, Optional

class PolicyViolation(Exception):
    """Raised when an agent action violates a deterministic safety invariant."""
    pass

class PreconditionFailure(Exception):
    """Raised when system preconditions for an action are not satisfied."""
    pass

class PolicyEngine:
    PROHIBITED_COMMAND_PATTERNS = [
        (r'rm\s+-rf\s+/(?:$|\s)', "Prohibited: root directory deletion"),
        (r'rm\s+-rf\s+/var/www(?:$|\s|/)', "Prohibited: total application directory deletion"),
        (r'chmod\s+777\b', "Prohibited: world-writable permissions (0777)"),
        (r'chmod\s+666\b', "Prohibited: world-writable file permissions (0666)"),
        (r'set_real_ip_from\s+0\.0\.0\.0/0', "Prohibited: trusting all IPs for real-IP header"),
        (r'NOPASSWD:\s*ALL\b', "Prohibited: blanket root passwordless sudo"),
        (r'PermitRootLogin\s+yes\b', "Prohibited: root login over SSH"),
        (r'PasswordAuthentication\s+yes\b', "Prohibited: password authentication over SSH")
    ]

    SECRET_PATTERN = re.compile(
        r'(?:(?:password|secret|key|token|database_url|db_pass)\s*[:=]\s*["\']?(?!(?:<SECRET_REF_[A-Z0-9_]+>))[^\s"\']{6,})|'
        r'(?:://[^:]+:(?!(?:<SECRET_REF_[A-Z0-9_]+>))[^@\s]+@)',
        re.IGNORECASE
    )

    @classmethod
    def validate_command_safety(cls, command_string: str) -> None:
        """Validates that a proposed command contains no prohibited destructive patterns."""
        for pattern, reason in cls.PROHIBITED_COMMAND_PATTERNS:
            if re.search(pattern, command_string, re.IGNORECASE):
                raise PolicyViolation(f"Policy Engine Blocked Action: {reason}")

    @classmethod
    def inspect_for_raw_secrets(cls, text_payload: str) -> None:
        """Ensures raw secrets are not leaked in plain text; must use <SECRET_REF_*> placeholders."""
        match = cls.SECRET_PATTERN.search(text_payload)
        if match:
            raise PolicyViolation(
                f"Security Violation: Raw credentials detected in payload ('{match.group(0)[:15]}...'). "
                "Must use abstract <SECRET_REF_*> placeholder."
            )

    @classmethod
    def verify_nginx_reload_preconditions(cls, preconditions: Dict[str, Any]) -> None:
        """
        Preconditions required before executing nginx reload:
        - nginx_configuration_valid == True (nginx -t passed)
        - backup_exists == True
        - rollback_command_known == True
        """
        required = [
            ("nginx_configuration_valid", "Nginx syntax test (nginx -t) must return 0"),
            ("backup_exists", "Previous working configuration backup must exist"),
            ("rollback_command_known", "Rollback procedure must be specified in the execution plan")
        ]
        for key, msg in required:
            if not preconditions.get(key, False):
                raise PreconditionFailure(f"Nginx Reload Precondition Failed: {msg}")

    @classmethod
    def verify_atomic_cutover_preconditions(cls, preconditions: Dict[str, Any]) -> None:
        """
        Preconditions required before switching production release symlink:
        - staged_release_dir_exists == True
        - previous_pointer_saved == True
        - health_check_defined == True
        - rollback_script_ready == True
        """
        required = [
            ("staged_release_dir_exists", "Staged release directory must exist"),
            ("previous_pointer_saved", "Pointer to current working release must be recorded"),
            ("health_check_defined", "Post-deployment health check endpoint must be defined"),
            ("rollback_script_ready", "Instant rollback trigger must be armed")
        ]
        for key, msg in required:
            if not preconditions.get(key, False):
                raise PreconditionFailure(f"Atomic Cutover Precondition Failed: {msg}")
