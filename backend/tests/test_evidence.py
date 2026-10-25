from app.services.evidence import evidence_key, sha256_bytes


def test_hash_is_deterministic_and_correct():
    # Known SHA-256 of b"abc"
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")


def test_identical_bytes_map_to_identical_key_idempotent():
    a = evidence_key(sha256_bytes(b"same video"), "telegram", "mp4")
    b = evidence_key(sha256_bytes(b"same video"), "telegram", "mp4")
    assert a == b  # content-addressed -> re-ingest is a no-op


def test_key_is_sharded_and_namespaced_by_source():
    digest = sha256_bytes(b"x")
    key = evidence_key(digest, "youtube", ".mp4")
    assert key == f"youtube/{digest[:2]}/{digest[2:4]}/{digest}.mp4"


def test_key_without_extension():
    digest = sha256_bytes(b"x")
    assert evidence_key(digest, "tiktok").endswith(digest)
    assert "." not in evidence_key(digest, "tiktok").rsplit("/", 1)[1]
