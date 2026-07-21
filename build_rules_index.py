#!/usr/bin/env python3
"""Build data/rules_index.jsonl from the Markdown rules corpus.

Walks rules_corpus/**/*.md, parses the YAML frontmatter + body of each file,
and emits one JSON record per rule to data/rules_index.jsonl (one line each).

This is the *derived* search/RAG index — never hand-edit the JSONL; re-run this
script instead. The Markdown files under rules_corpus/ are the source of truth.

Frontmatter is parsed with PyYAML (see requirements.txt) and validated: a
malformed or incomplete file fails loudly here rather than producing a silently
wrong index.

Usage:
    python build_rules_index.py            # build the index
    python build_rules_index.py --check    # verify index is up to date (CI)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "rules_corpus"
INDEX = ROOT / "data" / "rules_index.jsonl"

# Frontmatter keys and their required Python types (after YAML parsing).
REQUIRED = {
    "id": str,
    "book": str,
    "chapter": str,
    "pages": list,
    "tags": list,
    "title": str,
}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a Markdown file into (frontmatter dict, body). Raises on malformed."""
    if not text.startswith("---"):
        raise ValueError("no frontmatter block (file must start with '---')")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("frontmatter block is not closed with '---'")
    _, fm, body = parts
    meta = yaml.safe_load(fm)
    if not isinstance(meta, dict):
        raise ValueError("frontmatter did not parse to a mapping")
    return meta, body.strip()


def validate(meta: dict, source: str) -> None:
    """Raise ValueError if a file's frontmatter is missing keys or mistyped."""
    for key, typ in REQUIRED.items():
        if key not in meta:
            raise ValueError(f"{source}: missing required key '{key}'")
        if not isinstance(meta[key], typ):
            raise ValueError(
                f"{source}: key '{key}' must be {typ.__name__}, "
                f"got {type(meta[key]).__name__}"
            )
    if not all(isinstance(p, int) for p in meta["pages"]):
        raise ValueError(f"{source}: 'pages' must be a list of integers")


def build() -> list[dict]:
    records: list[dict] = []
    seen: dict[str, str] = {}  # id -> source, to catch duplicates
    errors: list[str] = []
    for md in sorted(CORPUS.rglob("*.md")):
        if md.name == "README.md":
            continue
        source = str(md.relative_to(ROOT))
        try:
            meta, body = parse_frontmatter(md.read_text(encoding="utf-8"))
            validate(meta, source)
        except (ValueError, yaml.YAMLError) as exc:
            errors.append(str(exc))
            continue
        rule_id = meta["id"]
        if rule_id in seen:
            errors.append(
                f"{source}: duplicate id '{rule_id}' (also in {seen[rule_id]})"
            )
            continue
        seen[rule_id] = source
        records.append({
            "id": rule_id,
            "book": meta["book"],
            "chapter": meta["chapter"],
            "pages": meta["pages"],
            "tags": meta["tags"],
            "title": meta["title"],
            "text": body,
            "source": source,
        })
    if errors:
        raise SystemExit(
            "Corpus validation failed:\n  - " + "\n  - ".join(errors)
        )
    records.sort(key=lambda r: r["id"])
    return records


def render(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def main() -> int:
    records = build()
    out = render(records)
    if "--check" in sys.argv:
        current = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if current != out:
            print("rules_index.jsonl is stale — run: python build_rules_index.py")
            return 1
        print(f"OK: {len(records)} rules, index up to date")
        return 0
    INDEX.parent.mkdir(exist_ok=True)
    INDEX.write_text(out, encoding="utf-8")
    print(f"Wrote {len(records)} rules to {INDEX.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
