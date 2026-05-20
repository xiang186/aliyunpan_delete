"""
Unit tests for token encryption/decryption utilities.

**Validates: Requirements 1.5, 8.1**
"""
import pytest
from cryptography.fernet import Fernet

from app.core.crypto import decrypt_token, encrypt_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode("utf-8")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(monkeypatch) -> None:
    """Encrypting then decrypting a token returns the original value."""
    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    token = "my-secret-access-token"
    encrypted = encrypt_token(token)
    assert decrypt_token(encrypted) == token


def test_encrypt_produces_different_ciphertext_each_time(monkeypatch) -> None:
    """Fernet uses a random IV, so two encryptions of the same plaintext differ."""
    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    token = "same-token"
    enc1 = encrypt_token(token)
    enc2 = encrypt_token(token)
    # Ciphertexts differ (probabilistic), but both decrypt to the same value
    assert enc1 != enc2
    assert decrypt_token(enc1) == token
    assert decrypt_token(enc2) == token


def test_encrypt_returns_string(monkeypatch) -> None:
    """encrypt_token returns a str."""
    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    result = encrypt_token("token")
    assert isinstance(result, str)


def test_decrypt_returns_string(monkeypatch) -> None:
    """decrypt_token returns a str."""
    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    encrypted = encrypt_token("token")
    result = decrypt_token(encrypted)
    assert isinstance(result, str)


def test_encrypt_empty_string(monkeypatch) -> None:
    """Empty string tokens can be encrypted and decrypted."""
    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    encrypted = encrypt_token("")
    assert decrypt_token(encrypted) == ""


def test_encrypt_unicode_token(monkeypatch) -> None:
    """Unicode tokens are handled correctly."""
    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    token = "日本語トークン🔑"
    encrypted = encrypt_token(token)
    assert decrypt_token(encrypted) == token


def test_encrypt_raises_value_error_when_key_missing(monkeypatch) -> None:
    """encrypt_token raises ValueError when encryption_key is empty."""
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": ""})())

    with pytest.raises(ValueError, match="[Ee]ncryption key"):
        encrypt_token("some-token")


def test_decrypt_raises_value_error_when_key_missing(monkeypatch) -> None:
    """decrypt_token raises ValueError when encryption_key is empty."""
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": ""})())

    with pytest.raises(ValueError, match="[Ee]ncryption key"):
        decrypt_token("some-encrypted-value")


def test_decrypt_raises_on_tampered_ciphertext(monkeypatch) -> None:
    """Tampered ciphertext raises an error during decryption."""
    from cryptography.fernet import InvalidToken

    key = _valid_fernet_key()
    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key})())

    with pytest.raises(Exception):  # InvalidToken or similar
        decrypt_token("this-is-not-valid-fernet-ciphertext")


def test_different_keys_cannot_decrypt(monkeypatch) -> None:
    """A token encrypted with one key cannot be decrypted with a different key."""
    from cryptography.fernet import InvalidToken

    key1 = _valid_fernet_key()
    key2 = _valid_fernet_key()

    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key1})())
    encrypted = encrypt_token("secret")

    monkeypatch.setattr("app.core.crypto.settings", type("S", (), {"encryption_key": key2})())
    with pytest.raises(Exception):  # InvalidToken
        decrypt_token(encrypted)
