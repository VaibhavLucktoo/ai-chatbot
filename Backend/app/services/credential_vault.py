"""Authenticated encryption; the master key is stored separately from PostgreSQL."""

import json
import os
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core.config import Settings


class CredentialError(RuntimeError):
    """Safe to display: never includes plaintext, ciphertext or a filesystem path."""


_key_lock = Lock()


class CredentialVault:
    def __init__(self, settings: Settings) -> None:
        self._configured_key = settings.assistant_encryption_key
        self._key_file: Path = settings.assistant_key_file

    def _cipher(self, *, create: bool = False) -> Fernet:
        try:
            key = self._configured_key.get_secret_value().encode("ascii")
            if not key:
                with _key_lock:
                    if create and not self._key_file.exists():
                        self._key_file.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            descriptor = os.open(self._key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        except FileExistsError:
                            pass
                        else:
                            with os.fdopen(descriptor, "wb") as stream:
                                stream.write(Fernet.generate_key())
                                stream.flush()
                                os.fsync(stream.fileno())
                    key = self._key_file.read_bytes().strip()
            return Fernet(key)
        except (OSError, ValueError, UnicodeError):
            raise CredentialError("The provider credential encryption key is unavailable or invalid.") from None

    def encrypt(self, api_key: SecretStr, *, provider: str, connection_id: str) -> str:
        # Bind ciphertext to its connection and provider to detect row substitution.
        payload = json.dumps({"provider": provider, "connection_id": connection_id,
                              "api_key": api_key.get_secret_value()}).encode("utf-8")
        return self._cipher(create=True).encrypt(payload).decode("ascii")

    def decrypt(self, encrypted: str, *, provider: str, connection_id: str) -> SecretStr:
        try:
            payload = json.loads(self._cipher().decrypt(encrypted.encode("ascii")))
            if payload["provider"] != provider or payload["connection_id"] != connection_id:
                raise ValueError("Credential binding mismatch")
            key = payload["api_key"]
            if not isinstance(key, str) or not key:
                raise ValueError("Invalid key")
            return SecretStr(key)
        except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError):
            raise CredentialError("The saved provider key could not be decrypted. Restore the encryption key or replace the connection key.") from None
