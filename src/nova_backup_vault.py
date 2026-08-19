"""Authenticated, portable encryption for Nova reliability archives.

The vault format is intentionally small and documented in its authenticated
header. Passphrases are used only in memory and are never written to metadata.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import struct
from typing import Any
from datetime import datetime, timezone
import uuid


MAGIC = b"NOVA_VAULT_1\n"
FORMAT_VERSION = 1
TAG_BYTES = 16
PBKDF2_ITERATIONS = 600_000
MAX_HEADER_BYTES = 64 * 1024


class VaultError(RuntimeError):
    """A portable vault operation could not be completed safely."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encryption_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher  # noqa: F401
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # noqa: F401

        return True
    except Exception:
        return False


def _derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except Exception as exc:
        raise VaultError(
            "Strong backup encryption is unavailable. Install the runtime requirements."
        ) from exc
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _validate_passphrase(passphrase: Any) -> str:
    value = str(passphrase or "")
    if len(value) < 12:
        raise VaultError("Use a backup passphrase with at least 12 characters.")
    if len(value) > 512:
        raise VaultError("Backup passphrase is too long.")
    return value


class BackupVault:
    def __init__(self, application_root: str | Path, export_root: str | Path | None = None):
        self.root = Path(application_root).expanduser().resolve()
        self.export_root = Path(
            export_root or (self.root / "exports" / "reliability")
        ).expanduser().resolve()
        self.export_root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        archive_path: str | Path,
        backup_id: str,
        passphrase: Any,
    ) -> dict[str, Any]:
        source = Path(archive_path).expanduser().resolve()
        if not source.is_file():
            raise VaultError("The selected verified backup archive was not found.")
        secret = _validate_passphrase(passphrase)
        if not encryption_available():
            raise VaultError("Strong backup encryption is unavailable.")

        salt = os.urandom(16)
        nonce = os.urandom(12)
        vault_id = uuid.uuid4().hex
        created_at = _timestamp()
        safe_backup_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(backup_id))[:80]
        filename = f"nova_{safe_backup_id}_{vault_id[:8]}.novavault"
        destination = self.export_root / filename
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        metadata_path = self.export_root / f"nova_vault_{vault_id}.json"

        header = {
            "format_version": FORMAT_VERSION,
            "vault_id": vault_id,
            "created_at": created_at,
            "source_backup_id": str(backup_id),
            "source_filename": source.name,
            "plaintext_bytes": source.stat().st_size,
            "cipher": "AES-256-GCM",
            "kdf": "PBKDF2-HMAC-SHA256",
            "kdf_iterations": PBKDF2_ITERATIONS,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        }
        header_bytes = json.dumps(
            header, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(header_bytes) > MAX_HEADER_BYTES:
            raise VaultError("Portable vault header is unexpectedly large.")

        key = _derive_key(secret, salt, PBKDF2_ITERATIONS)
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            encryptor.authenticate_additional_data(header_bytes)
            with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
                output_stream.write(MAGIC)
                output_stream.write(struct.pack(">I", len(header_bytes)))
                output_stream.write(header_bytes)
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    output_stream.write(encryptor.update(chunk))
                output_stream.write(encryptor.finalize())
                output_stream.write(encryptor.tag)
            os.replace(temporary, destination)

            metadata = {
                "format_version": FORMAT_VERSION,
                "vault_id": vault_id,
                "created_at": created_at,
                "source_backup_id": str(backup_id),
                "filename": filename,
                "vault_bytes": destination.stat().st_size,
                "plaintext_bytes": source.stat().st_size,
                "cipher": "AES-256-GCM",
                "verified": True,
                "download_url": f"/api/reliability/vault/{vault_id}/download",
            }
            temporary_metadata = metadata_path.with_suffix(".json.tmp")
            temporary_metadata.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary_metadata, metadata_path)
            return metadata
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise
        finally:
            key = b""
            secret = ""

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        results: list[dict[str, Any]] = []
        for metadata_path in self.export_root.glob("nova_vault_*.json"):
            try:
                item = json.loads(metadata_path.read_text(encoding="utf-8"))
                filename = str(item.get("filename") or "")
                destination = (self.export_root / filename).resolve()
                destination.relative_to(self.export_root)
                if item.get("vault_id") and destination.is_file():
                    results.append(item)
            except (OSError, ValueError, TypeError):
                continue
        results.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return results[:safe_limit]

    def get(self, vault_id: str) -> tuple[dict[str, Any], Path] | None:
        normalized = str(vault_id or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{32}", normalized):
            return None
        metadata_path = self.export_root / f"nova_vault_{normalized}.json"
        if not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            destination = (self.export_root / str(metadata.get("filename") or "")).resolve()
            destination.relative_to(self.export_root)
        except (OSError, ValueError, TypeError):
            return None
        if metadata.get("vault_id") != normalized or not destination.is_file():
            return None
        return metadata, destination

    def decrypt(
        self,
        vault_path: str | Path,
        destination_path: str | Path,
        passphrase: Any,
    ) -> dict[str, Any]:
        source = Path(vault_path).expanduser().resolve()
        destination = Path(destination_path).expanduser().resolve()
        secret = _validate_passphrase(passphrase)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            from cryptography.exceptions import InvalidTag
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            with source.open("rb") as input_stream:
                if input_stream.read(len(MAGIC)) != MAGIC:
                    raise VaultError("This is not a supported Nova vault file.")
                raw_header_length = input_stream.read(4)
                if len(raw_header_length) != 4:
                    raise VaultError("Nova vault header is incomplete.")
                header_length = struct.unpack(">I", raw_header_length)[0]
                if not 1 <= header_length <= MAX_HEADER_BYTES:
                    raise VaultError("Nova vault header length is invalid.")
                header_bytes = input_stream.read(header_length)
                if len(header_bytes) != header_length:
                    raise VaultError("Nova vault header is incomplete.")
                try:
                    header = json.loads(header_bytes.decode("utf-8"))
                    salt = base64.b64decode(header["salt_b64"], validate=True)
                    nonce = base64.b64decode(header["nonce_b64"], validate=True)
                    iterations = int(header["kdf_iterations"])
                except (KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
                    raise VaultError("Nova vault header is invalid.") from exc
                if header.get("format_version") != FORMAT_VERSION:
                    raise VaultError("Nova vault version is not supported.")
                if header.get("cipher") != "AES-256-GCM" or header.get("kdf") != "PBKDF2-HMAC-SHA256":
                    raise VaultError("Nova vault encryption settings are not supported.")
                if len(salt) != 16 or len(nonce) != 12:
                    raise VaultError("Nova vault encryption parameters are invalid.")
                if not 100_000 <= iterations <= 2_000_000:
                    raise VaultError("Nova vault key settings are outside safe limits.")

                content_start = len(MAGIC) + 4 + header_length
                source_size = source.stat().st_size
                ciphertext_bytes = source_size - content_start - TAG_BYTES
                if ciphertext_bytes < 0:
                    raise VaultError("Nova vault content is incomplete.")
                input_stream.seek(source_size - TAG_BYTES)
                tag = input_stream.read(TAG_BYTES)
                input_stream.seek(content_start)

                key = _derive_key(secret, salt, iterations)
                decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
                decryptor.authenticate_additional_data(header_bytes)
                remaining = ciphertext_bytes
                written = 0
                destination.parent.mkdir(parents=True, exist_ok=True)
                with temporary.open("wb") as output_stream:
                    while remaining:
                        chunk = input_stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise VaultError("Nova vault content ended unexpectedly.")
                        remaining -= len(chunk)
                        plaintext = decryptor.update(chunk)
                        output_stream.write(plaintext)
                        written += len(plaintext)
                    try:
                        final = decryptor.finalize()
                    except InvalidTag as exc:
                        raise VaultError("Vault passphrase is incorrect or the file is damaged.") from exc
                    output_stream.write(final)
                    written += len(final)
                if written != int(header.get("plaintext_bytes") or -1):
                    raise VaultError("Decrypted backup size verification failed.")
                os.replace(temporary, destination)
                return {
                    "ok": True,
                    "destination": str(destination),
                    "bytes": written,
                    "source_backup_id": header.get("source_backup_id"),
                }
        except VaultError:
            temporary.unlink(missing_ok=True)
            raise
        except (OSError, TypeError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise VaultError("The encrypted backup could not be opened safely.") from exc
        finally:
            secret = ""


__all__ = [
    "BackupVault",
    "FORMAT_VERSION",
    "MAGIC",
    "VaultError",
    "encryption_available",
]
