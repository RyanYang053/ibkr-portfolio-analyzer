"""Encrypted backup helpers for desktop personal data."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive_backup_key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


def encrypt_backup_bytes(plaintext: bytes, passphrase: str) -> bytes:
    salt = os.urandom(16)
    key = derive_backup_key(passphrase, salt)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    header = b"PAEB1" + salt + nonce
    return header + ciphertext


def decrypt_backup_bytes(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(b"PAEB1"):
        raise ValueError("Unsupported backup envelope")
    salt = blob[5:21]
    nonce = blob[21:33]
    ciphertext = blob[33:]
    key = derive_backup_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def write_encrypted_backup(source_zip: Path, destination: Path, passphrase: str) -> Path:
    plaintext = source_zip.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encrypt_backup_bytes(plaintext, passphrase))
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_zip),
        "sha256_plaintext": hashlib.sha256(plaintext).hexdigest(),
        "envelope": "PAEB1",
    }
    destination.with_suffix(destination.suffix + ".meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    return destination
