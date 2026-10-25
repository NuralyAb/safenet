import os

from app.services.crypto import decrypt, decrypt_embedding, encrypt, encrypt_embedding


def test_aesgcm_roundtrip():
    key = os.urandom(32)
    pt = b"face-embedding-bytes"
    assert decrypt(encrypt(pt, key), key) == pt


def test_tampering_with_ciphertext_fails_auth():
    key = os.urandom(32)
    blob = bytearray(encrypt(b"secret", key))
    blob[-1] ^= 0x01                       # flip a tag bit
    try:
        decrypt(bytes(blob), key)
        assert False, "tampered ciphertext must not decrypt"
    except Exception:
        pass                               # InvalidTag


def test_embedding_roundtrip_preserves_values():
    key = os.urandom(32)
    vec = [0.1, -0.5, 3.14, 0.0]
    out = decrypt_embedding(encrypt_embedding(vec, key), key)
    assert all(abs(a - b) < 1e-6 for a, b in zip(vec, out))
    assert len(out) == len(vec)


def test_wrong_key_cannot_decrypt():
    blob = encrypt(b"x", os.urandom(32))
    try:
        decrypt(blob, os.urandom(32))
        assert False, "wrong key must fail"
    except Exception:
        pass
