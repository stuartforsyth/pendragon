#!/usr/bin/env python3
"""Build data/rules_index.jsonl from the Markdown rules corpus.

Walks rules_corpus/**/*.md, parses the YAML frontmatter + body of each file,
and emits one JSON record per rule to data/rules_index.jsonl (one line each).

This is the *derived* search/RAG index — never hand-edit the JSONL; re-run this
script instead. The Markdown files under rules_corpus/ are the source of truth.

Usage:
    python build_rules_index.py            # build the index
    python build_rules_index.py --check    # verify index is up to date (CI)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "rules_corpus"
INDEX = ROOT / "data" / "rules_index.jsonl"

# Minimal YAML frontmatter parser (avoids a PyYAML dependency for our subset:
# scalars, and inline [a, b] lists). Good enough for this schema.
def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("file has no frontmatter block")
    _, fm, body = text.split("---", 2)
    meta: dict = {}
    for line in fm.strip().splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [p.strip() for p in inner.split(",")] if inner else []
        else:
            meta[key] = val.strip('"')
    return meta, body.strip()


def build() -> list[dict]:
    records: list[dict] = []
    for md in sorted(CORPUS.rglob("*.md")):
        if md.name == "README.md":
            continue
        meta, body = parse_frontmatter(md.read_text(encoding="utf-8"))
        records.append({
            "id": meta.get("id", md.stem),
            "book": meta.get("book", ""),
            "chapter": meta.get("chapter", ""),
            "pages": [int(p) for p in meta.get("pages", []) if p],
            "tags": meta.get("tags", []),
            "title": meta.get("title", ""),
            "text": body,
            "source": str(md.relative_to(ROOT)),
        })
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
