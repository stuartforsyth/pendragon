# Rules Corpus (queryable prose rules)

Machine- **and** human-queryable rules extracted from the Pendragon PDFs.

## The format: Markdown + YAML frontmatter, one file per rule/topic

Each `.md` file is a single, self-contained rule chunk. The **frontmatter**
carries structured metadata for filtering and citation; the **body** carries the
paraphrased/summarised rule prose.

```markdown
---
id: core.combat.winners-outcome      # stable unique id (book.chapter.slug)
book: core                           # core | gm | battlecards
chapter: "7 — Combat"
pages: [133]                          # PRINTED page numbers, for citing the PDF
tags: [combat, resolution, critical, damage]
title: Winner's Outcome
see_also: [core.combat.critical-success, data:combat.json#critical_hit]
---

Prose rule text here...
```

## Why this format

- **Frontmatter = JSON-like queryability** (filter by book/chapter/tag/page)
  without forcing prose into a rigid schema.
- **Body = natural LLM/RAG chunk** and human-readable play aid.
- **Greppable + diffable + hand-editable**; page numbers cite back to the PDF.

## Three tiers, three jobs (don't mix them)

| Tier | Lives in | For |
|------|----------|-----|
| Computed tables / stat blocks / dice | `data/*.json` | app logic (already exists) |
| Prose rules | `rules_corpus/**/*.md` (this dir) | Q&A, browse, RAG |
| Derived search index | `data/rules_index.jsonl` (generated) | full-text / retrieval |

Never hand-edit the JSONL — regenerate it: `python build_rules_index.py`.

## Extraction workflow

1. `pdftotext -f <first> -l <last> rulebooks/corerulebook.pdf out.txt` (no `-layout`;
   raw mode reads two-column pages in correct order).
2. Clean per section: de-hyphenate line breaks, fix bullet glyphs (`Ő` → `-`),
   rejoin wrapped lines. (LLM-assisted, chapter by chapter.)
3. Split into one file per rule/topic; fill frontmatter (`pages` = printed
   numbers). PDF page = printed page + 3 for the core rulebook.
4. `python build_rules_index.py` to refresh the index.

**Source:** *King Arthur Pendragon* 5th Ed. (Chaosium / Nocturnal Media).
Paraphrased as a play aid; PDFs are copyrighted and kept locally only.
