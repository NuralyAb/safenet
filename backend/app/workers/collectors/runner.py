"""Collection runner — source-agnostic glue around any BaseCollector.

For each fetched/discovered item: enforce the SSRF allowlist, store the original
to the WORM evidence bucket (SHA-256 chain of custody), and emit the `collect`
contract dict consumed by process_content.
"""
from __future__ import annotations

from app.services.ssrf import check_url


def _emit(items, evidence_store, allowed_hosts: list[str]) -> list[dict]:
    out: list[dict] = []
    for item in items:
        if item.url:
            check_url(item.url, allowed_hosts)        # raises UnsafeURLError if blocked
        ref = evidence_store.store(
            item.media, item.source, content_type=item.content_type, ext=item.ext
        )
        out.append({
            "content_id": ref.sha256,                 # content-addressed id
            "source": item.source,
            "sha256": ref.sha256,
            "raw_key": ref.raw_key,
            "evidence_key": ref.evidence_key,         # WORM custody key (for the Evidence row)
            "size": ref.size,
            "content_type": ref.content_type,
            "author": item.author,
            "url": item.url,
            "text": item.text,
            "telegram": item.telegram,
            "wallets": item.wallets,
            "domains": item.domains,
            "audio": item.audio,
            "image": item.image,
            "reach": item.reach,
        })
    return out


def collect_via(collector, evidence_store, target: str, allowed_hosts: list[str],
                *, limit: int = 20) -> list[dict]:
    """Fetch a known account/channel."""
    return _emit(collector.fetch(target, limit=limit), evidence_store, allowed_hosts)


def discover_via(collector, evidence_store, query: str, allowed_hosts: list[str],
                 *, limit: int = 20) -> list[dict]:
    """Proactively discover NEW content by keyword/hashtag."""
    return _emit(collector.search(query, limit=limit), evidence_store, allowed_hosts)
