"""
Token encryption/decryption utilities using Fernet symmetric encryption.
"""
from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    """
    Build a Fernet instance from the configured encryption key.

    Raises:
        ValueError: If the encryption key is not configured.
    """
    key = settings.encryption_key
    if not key:
        raise ValueError(
            "Encryption key is not configured. "
            "Set the ENCRYPTION_KEY environment variable."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    """
    Encrypt a plaintext token string using Fernet symmetric encryption.

    Args:
        token: The plaintext token to encrypt.

    Returns:
        The encrypted token as a URL-safe base64-encoded string.

    Raises:
        ValueError: If the encryption key is not configured.
    """
    fernet = _get_fernet()
    return fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted: str) -> str:
    """
    Decrypt a Fernet-encrypted token string.

    Args:
        encrypted: The encrypted token (URL-safe base64-encoded string).

    Returns:
        The original plaintext token.

    Raises:
        ValueError: If the encryption key is not configured.
        cryptography.fernet.InvalidToken: If the token is invalid or tampered.
    """
    fernet = _get_fernet()
    return fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
