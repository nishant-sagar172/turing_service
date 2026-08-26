"""Symmetric encryption helpers for sensitive config values (e.g. per-client
LLM API keys stored in the database).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The master key must be a URL-safe base64-encoded 32-byte value, set via the
ENCRYPTION_KEY environment variable.
"""

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    pass


def encrypt(plaintext: str, key: str) -> str:
    """Return a Fernet-encrypted, base64-encoded ciphertext string."""
    try:
        return Fernet(key.encode()).encrypt(plaintext.encode()).decode()
    except Exception as exc:
        raise EncryptionError("Encryption failed") from exc


def decrypt(ciphertext: str, key: str) -> str:
    """Decrypt a Fernet ciphertext string back to plaintext.

    Raises EncryptionError on invalid token or wrong key.
    """
    try:
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError("Decryption failed: invalid token or wrong key") from exc
    except Exception as exc:
        raise EncryptionError("Decryption failed") from exc
