"""Encryption at rest for the biometric vault (AES-256-GCM).

Face/voice embeddings are special-category data; they are encrypted before they
touch disk. AES-256-GCM gives confidentiality + integrity (tampering fails the
auth tag). The key comes from a KMS/HSM in production, never from source.

Wire format: nonce(12) || ciphertext+tag. Embeddings are serialized as float32.
"""
from __future__ import annotations

import base64
import os
import struct

from app.core.config import settings

_NONCE_LEN = 12


def _key() -> bytes:
    raw = base64.b64decode(settings.biometric_encryption_key + "===")
    if len(raw) != 32:
        raise ValueError("biometric_encryption_key must decode to 32 bytes (AES-256)")
    return raw


def encrypt(plaintext: bytes, key: bytes | None = None) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    k = key if key is not None else _key()
    nonce = os.urandom(_NONCE_LEN)
    return nonce + AESGCM(k).encrypt(nonce, plaintext, None)


def decrypt(blob: bytes, key: bytes | None = None) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    k = key if key is not None else _key()
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    return AESGCM(k).decrypt(nonce, ct, None)


def encrypt_embedding(vector: list[float], key: bytes | None = None) -> bytes:
    return encrypt(struct.pack(f"<{len(vector)}f", *vector), key)


def decrypt_embedding(blob: bytes, key: bytes | None = None) -> list[float]:
    raw = decrypt(blob, key)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))
