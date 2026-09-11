# Rules Corpus (queryable prose rules)

Machine- **and** human-queryable rules extracted from the Pendragon PDFs.

## The format: Markdown + YAML frontmatter, one file per rule/topic

Each `.md` file is a single, self-contained rule chunk. The **frontmatter**
carries structured metadata for filtering and citation; the **body** carries the
paraphrased/summarised rule prose.

```markdown
---
id: core.combat.winners-outcome      # stable unique id (book.chapter.slug)
system: Pendragon 6th Edition        # the ruleset this file belongs to
book: core                           # core | gm | battlecards
chapter: "7 — Combat"
pages: [133]                          # PRINTED page numbers, for citing the PDF
tags: [combat, resolution, critical, damage]
title: Winner's Outcome
see_also: [core.combat.critical-success, data:combat.json#critical_hit]
---

Prose rule text here...
```

`see_also` is a **flow list of plain ids**, not Obsidian wikilinks —
deliberately, even though a mirror of this corpus lives in an Obsidian
vault (see *Mirrored elsewhere*, below): an id can point at a `data:*.json`
key the app actually reads, which a `[[wikilink]]` cannot represent, and
this corpus is grepped/indexed, not browsed in a vault.

## One paragraph, one line — never hard-wrap prose

**Do not wrap prose to a column width.** Each paragraph, each bullet, and
each blockquote paragraph is **one unbroken line**, however long. This is
not a style preference — a sentence split across a hard line break can't be
found by `grep`, which defeats the point of a corpus meant to be searched by
phrase. Markdown renders wrapped and unwrapped prose identically, so
wrapping only costs you, never gains you anything. Tables, headings, list
markers, fenced code, and blank paragraph separators are unaffected.

To repair an already-wrapped file (or a batch of them), write a script that
joins continuation lines within a paragraph/bullet/blockquote, leaves
frontmatter/tables/headings/HRs/code/list-markers untouched, and **refuses
to write any file whose word multiset changed** — then eyeball every
`> [!...]` callout line afterwards by hand, since a reflow pass can flatten
a callout title into the line below it without losing a single word (the
multiset check alone won't catch that).

## Why this format

- **Frontmatter = JSON-like queryability** (filter by book/chapter/tag/page)
  without forcing prose into a rigid schema.
- **Body = natural LLM/RAG chunk** and human-readable play aid.
- **Greppable + diffable + hand-editable**; page numbers cite back to the PDF.

## Mirrored elsewhere

This project is the **source of truth** for the corpus. A read-only copy
also lives in an Obsidian vault, refreshed by a one-way sync script run
from time to time — never edited there directly, since the next sync would
silently overwrite any such edit. If you're looking at a copy of this
corpus outside `pendragon-names/rules_corpus/`, treat it as a snapshot and
make the change here instead.

## Three tiers, three jobs (don't mix them)

| Tier | Lives in | For |
|------|----------|-----|
| Computed tables / stat blocks / dice | `data/*.json` | app logic (already exists) |
| Prose rules | `rules_corpus/**/*.md` (this dir) | Q&A, browse, RAG |
| Derived search index | `data/rules_index.jsonl` (generated) | full-text / retrieval |

Never hand-edit the JSONL — regenerate it: `python build_rules_index.py`.

## Coverage & extraction queue

`COVERAGE.md` maps every chapter of both books against what's actually in
this directory (✅/⚠️/❌); `EXTRACTION-PLAN.md` holds the method and the
ordered queue of what's left. Use the **`extract-rule`** skill to do the
actual extraction — it implements the workflow below and updates both
tracking files.

## Extraction workflow

1. `pdftotext -f <first> -l <last> rulebooks/corerulebook.pdf out.txt` (no `-layout`;
   raw mode reads two-column pages in correct order). **For anything tabular
   — statblocks, dice tables — use `-layout` instead**: raw mode silently
   interleaves two-column pages and can swap values between adjacent tables.
2. Clean per section: de-hyphenate line breaks, fix bullet glyphs (`Ő` → `-`),
   rejoin wrapped lines. (LLM-assisted, chapter by chapter.)
3. Split into one file per rule/topic; fill frontmatter (`pages` = printed
   numbers). PDF page = printed page + 3 for the core rulebook. Write prose
   one paragraph per line (above), not hard-wrapped.
4. `python build_rules_index.py` to refresh the index.
5. Update `COVERAGE.md` (flip the status, bump the file count) and, if the
   extraction closed a queue item, `EXTRACTION-PLAN.md`.

**Source:** *King Arthur Pendragon* 6th Ed. (Chaosium).
Paraphrased as a play aid; PDFs are copyrighted and kept locally only.
