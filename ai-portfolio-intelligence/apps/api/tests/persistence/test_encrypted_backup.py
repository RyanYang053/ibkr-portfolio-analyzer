"""Encrypted backup unit tests."""

from __future__ import annotations

from pathlib import Path

from app.services.backup.encrypted_backup import (
    decrypt_backup_bytes,
    encrypt_backup_bytes,
    write_encrypted_backup,
)


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = b"portfolio-backup-bytes"
    blob = encrypt_backup_bytes(plaintext, "test-passphrase-not-for-prod")
    assert blob.startswith(b"PAEB1")
    assert decrypt_backup_bytes(blob, "test-passphrase-not-for-prod") == plaintext


def test_write_encrypted_backup(tmp_path: Path) -> None:
    source = tmp_path / "src.zip"
    source.write_bytes(b"zip-bytes")
    dest = tmp_path / "out.paeb"
    write_encrypted_backup(source, dest, "pass")
    assert dest.exists()
    assert dest.with_suffix(dest.suffix + ".meta.json").exists()
    assert decrypt_backup_bytes(dest.read_bytes(), "pass") == b"zip-bytes"
