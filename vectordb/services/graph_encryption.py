"""Fernet encryption helpers for per-collection LLM API keys."""
import base64
import json
import structlog

logger = structlog.get_logger(__name__)
_warned_no_key = False


def _make_fernet(key_hex: str):
    from cryptography.fernet import Fernet
    key_bytes = bytes.fromhex(key_hex)[:32]
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_api_keys(keys: dict, encryption_key: str) -> str:
    """Encrypt keys dict to a string blob. Falls back to plaintext JSON if no key."""
    global _warned_no_key
    if not encryption_key:
        if not _warned_no_key:
            logger.warning("graph_encryption_key_not_set_storing_plaintext")
            _warned_no_key = True
        return json.dumps(keys)
    return _make_fernet(encryption_key).encrypt(json.dumps(keys).encode()).decode()


def decrypt_api_keys(blob: str, encryption_key: str) -> dict:
    """Decrypt blob back to keys dict. Falls back to plaintext JSON if no key."""
    if not encryption_key:
        return json.loads(blob)
    return json.loads(_make_fernet(encryption_key).decrypt(blob.encode()).decode())
