"""
Circular document chunker — splits IDBI policy circulars into semantic chunks
with rich metadata including extracted rule IDs and rule conditions.

Each chunk becomes one Qdrant point in the `veritas_circulars` collection.
Metadata stored per chunk:
  - policy_name       human-readable circular name
  - section           section heading text
  - source_file       filename
  - rule_ids          list of rule IDs found in this chunk (CLM-001, UEBT-003, ...)
  - has_hard_rules    True if chunk contains extractable rule JSON
  - rule_blocks       list of parsed rule dicts (condition + outcome)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

POLICY_DIR = (
    Path(__file__).parent.parent.parent.parent / "seed_data" / "sample_policies"
)
MIN_CHUNK_CHARS = 80

_RULE_ID_PATTERN = re.compile(r"\b(CLM|UEBT|KYC|COMP)-\d{3}\b")


@dataclass
class CircularChunk:
    chunk_id: str
    policy_name: str
    section: str
    text: str
    source_file: str
    rule_ids: list[str] = field(default_factory=list)
    has_hard_rules: bool = False
    rule_blocks: list[dict] = field(default_factory=list)


def _extract_rule_blocks(text: str) -> tuple[list[str], list[dict]]:
    """Parse rule JSON blocks embedded in markdown (```json ... ```)."""
    rule_ids: list[str] = []
    rule_blocks: list[dict] = []

    # Extract all ```json blocks
    json_matches = re.findall(r"```json\s*([\s\S]*?)```", text)
    for raw in json_matches:
        try:
            parsed = json.loads(raw.strip())
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "rule_id" in item:
                        rule_ids.append(item["rule_id"])
                        rule_blocks.append(item)
            elif isinstance(parsed, dict) and "rule_id" in parsed:
                rule_ids.append(parsed["rule_id"])
                rule_blocks.append(parsed)
        except json.JSONDecodeError:
            pass

    # Also capture rule IDs mentioned in plain text
    for match in _RULE_ID_PATTERN.finditer(text):
        rid = match.group()
        if rid not in rule_ids:
            rule_ids.append(rid)

    return rule_ids, rule_blocks


def _chunk_markdown(text: str, policy_name: str, source_file: str) -> list[CircularChunk]:
    """
    Split a policy markdown file on ## / ### headers.
    Each section becomes one chunk; JSON rule blocks get their own chunk too.
    """
    chunks: list[CircularChunk] = []

    # Split on markdown section headers (## or ###)
    raw_sections = re.split(r"\n(?=#{2,3} )", text)

    for i, section_text in enumerate(raw_sections):
        section_text = section_text.strip()
        if len(section_text) < MIN_CHUNK_CHARS:
            continue

        first_line = section_text.split("\n")[0]
        section_title = first_line.lstrip("#").strip()

        rule_ids, rule_blocks = _extract_rule_blocks(section_text)

        chunk = CircularChunk(
            chunk_id=f"{source_file}::{i}::{section_title[:40]}",
            policy_name=policy_name,
            section=section_title,
            text=section_text,
            source_file=source_file,
            rule_ids=rule_ids,
            has_hard_rules=bool(rule_blocks),
            rule_blocks=rule_blocks,
        )
        chunks.append(chunk)

    return chunks


def load_all_circular_chunks() -> list[CircularChunk]:
    """Load and chunk every .md file from sample_policies/."""
    if not POLICY_DIR.exists():
        return []

    all_chunks: list[CircularChunk] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        policy_name = path.stem.replace("_", " ").title()
        text = path.read_text(encoding="utf-8")
        chunks = _chunk_markdown(text, policy_name, path.name)
        all_chunks.extend(chunks)

    return all_chunks
