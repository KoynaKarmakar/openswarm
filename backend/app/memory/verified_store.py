"""
Verified memory — integrity-gated, source-cited retrieval.

Every memory entry is a genuine, source-cited policy file under
`app/memory/verified/*.md`. A `manifest.json` records the SHA-256 of each file's
content. On load, each file is re-hashed and compared to the manifest:

  * hash matches  → the entry is **verified** and searchable;
  * hash missing / mismatched → the entry is **quarantined** (never returned),
    and `verify_integrity()` reports the break.

This mirrors the ledger's tamper-evidence, but for the knowledge the Knowledge
agent grounds on: an answer can only be grounded in a file whose content is
provably unchanged since it was vouched for.

`search()` returns `VerifiedChunk` objects with the SAME fields as
`rag.qdrant_client.PolicyChunk` (chunk_id/policy_name/section/text/score), so a
`VerifiedMemoryStore` drops straight into `KnowledgeAgent(qdrant=…)` — no agent
change. Each chunk additionally carries `source` provenance for genuine citation.

Note: the file bodies are concise, CITED SUMMARIES of the referenced circulars
(with the real reference number + URL for verification), not verbatim official
text — consult the cited source for the authoritative wording.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field

import yaml

_HERE = os.path.dirname(__file__)
VERIFIED_DIR = os.path.join(_HERE, "verified")
MANIFEST_PATH = os.path.join(VERIFIED_DIR, "manifest.json")

MIN_RELEVANCE = 0.3          # matches policy_agent.MIN_RELEVANCE_SCORE
_STOPWORDS = {"the", "and", "for", "are", "was", "with", "that", "this", "from",
              "must", "may", "not", "any", "per", "its", "of", "to", "a", "an",
              "is", "be", "or", "on", "in", "by", "at", "as", "it"}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2 and t not in _STOPWORDS]


@dataclass
class VerifiedChunk:
    chunk_id: str
    policy_name: str
    section: str
    text: str
    score: float
    source: dict = field(default_factory=dict)   # provenance: ref, publisher, url, date


@dataclass
class _Entry:
    chunk_id: str
    policy_name: str
    section: str
    text: str
    source: dict
    verified: bool
    tokens: Counter


class VerifiedMemoryStore:
    """Load, verify, and search the cited policy corpus."""

    def __init__(self, directory: str = VERIFIED_DIR, manifest_path: str | None = None):
        self._dir = directory
        self._manifest_path = manifest_path or os.path.join(directory, "manifest.json")
        self._entries: list[_Entry] = []
        self._integrity: dict[str, str] = {}   # filename → "verified"|"tampered"|"unlisted"
        self.reload()

    # ── loading + integrity ──────────────────────────────────────────────────
    def _manifest(self) -> dict:
        if not os.path.exists(self._manifest_path):
            return {}
        with open(self._manifest_path, encoding="utf-8") as fh:
            return json.load(fh)

    def reload(self) -> None:
        manifest = self._manifest()
        self._entries = []
        self._integrity = {}
        if not os.path.isdir(self._dir):
            return
        for fname in sorted(os.listdir(self._dir)):
            if not fname.endswith(".md") or fname.lower() == "readme.md":
                continue
            path = os.path.join(self._dir, fname)
            with open(path, "rb") as fh:
                raw = fh.read()
            digest = sha256_hex(raw)
            expected = manifest.get(fname)
            if expected is None:
                self._integrity[fname] = "unlisted"
                verified = False
            elif expected != digest:
                self._integrity[fname] = "tampered"
                verified = False
            else:
                self._integrity[fname] = "verified"
                verified = True

            front, body = _split_frontmatter(raw.decode("utf-8"))
            self._entries.append(_Entry(
                chunk_id=fname,
                policy_name=front.get("policy_name", fname),
                section=front.get("section", ""),
                text=body.strip(),
                source={k: front.get(k) for k in ("ref", "publisher", "url", "date", "kind")},
                verified=verified,
                tokens=Counter(_tokens(f"{front.get('policy_name','')} {front.get('section','')} {body}")),
            ))

    def verify_integrity(self) -> dict[str, str]:
        """filename → 'verified' | 'tampered' | 'unlisted'."""
        return dict(self._integrity)

    @property
    def all_verified(self) -> bool:
        return bool(self._integrity) and all(v == "verified" for v in self._integrity.values())

    # ── retrieval (only verified entries) ────────────────────────────────────
    def search(self, query: str, top_k: int = 3) -> list[VerifiedChunk]:
        q = _tokens(query)
        if not q:
            return []
        q_set = set(q)
        scored: list[tuple[float, _Entry]] = []
        for e in self._entries:
            if not e.verified:
                continue                      # quarantined — never returned
            matched = sum(1 for t in q_set if e.tokens.get(t))
            if not matched:
                continue
            coverage = matched / len(q_set)
            total = sum(e.tokens.values()) or 1
            tf = sum(e.tokens.get(t, 0) for t in q_set) / total
            score = min(1.0, 0.65 * coverage + 0.35 * min(1.0, tf * 6))
            scored.append((score, e))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [
            VerifiedChunk(
                chunk_id=e.chunk_id, policy_name=e.policy_name, section=e.section,
                text=e.text, score=round(score, 4), source=e.source,
            )
            for score, e in scored[:top_k] if score >= MIN_RELEVANCE
        ]


def _split_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text
    return (yaml.safe_load("\n".join(lines[1:end])) or {}), "\n".join(lines[end + 1:])


from functools import lru_cache


@lru_cache(maxsize=1)
def get_verified_memory() -> VerifiedMemoryStore:
    """Singleton verified-memory store — a Qdrant-compatible retriever fallback."""
    return VerifiedMemoryStore()


def build_manifest(directory: str = VERIFIED_DIR) -> dict:
    """Compute {filename: sha256} for every .md — used to (re)generate manifest.json."""
    out = {}
    for fname in sorted(os.listdir(directory)):
        if fname.endswith(".md") and fname.lower() != "readme.md":
            with open(os.path.join(directory, fname), "rb") as fh:
                out[fname] = sha256_hex(fh.read())
    return out


def _rebuild_manifest() -> None:
    manifest = build_manifest()
    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"Wrote {MANIFEST_PATH} ({len(manifest)} files)")


if __name__ == "__main__":
    import sys

    if "--rebuild-manifest" in sys.argv:
        _rebuild_manifest()
    else:
        store = VerifiedMemoryStore()
        print("Integrity:", store.verify_integrity())
        print("All verified:", store.all_verified)
