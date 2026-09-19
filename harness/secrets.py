"""
Secret Masking Boundary & Credential Resolver
Isolates real credentials from model context, reasoning traces, and logs.
"""
import re
from typing import Dict, Any

class SecretMasker:
    """
    Manages secret reference resolution.
    The agent sees ONLY <SECRET_REF_NAME>. The deterministic layer resolves values.
    """
    def __init__(self, secret_vault: Dict[str, str] = None):
        self._vault = secret_vault or {
            "DATABASE_URL": "postgresql://webapp_user:P@ssw0rd123!@127.0.0.1:5432/webapp_prod",
            "MEILI_MASTER_KEY": "a_super_secure_meilisearch_master_key_32bytes_long",
            "SSH_PRIVATE_KEY": "-----BEGIN OPENSSH PRIVATE KEY-----\nMOCK_KEY_FOR_TESTING\n-----END OPENSSH PRIVATE KEY-----"
        }

    def mask_text(self, text: str) -> str:
        """Replaces any accidental plain-text occurrence of known secrets with references."""
        masked = text
        for key, val in self._vault.items():
            if val in masked:
                masked = masked.replace(val, f"<SECRET_REF_{key}>")
        return masked

    def resolve_references(self, text_with_placeholders: str) -> str:
        """Resolves <SECRET_REF_NAME> placeholders to real credentials strictly at execution time."""
        def replacer(match):
            key = match.group(1)
            return self._vault.get(key, f"<UNRESOLVED_SECRET_{key}>")

        return re.sub(r'<SECRET_REF_([A-Z0-9_]+)>', replacer, text_with_placeholders)

    def contains_raw_secrets(self, text: str) -> bool:
        """Checks if text contains any raw values from the secret vault."""
        return any(val in text for val in self._vault.values())
