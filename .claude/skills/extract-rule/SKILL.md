---
name: extract-rule
description: Extract a Pendragon rule or event into the rules corpus as a Markdown file (with frontmatter) plus the regenerated JSON index, following the corpus outline. Use when the user says "extract <rule>", "add <rule/event> to the corpus", "capture the <X> rules", or names a rule/event to document.
---

# Extract a rule/event into the rules corpus

Given a rule or event (e.g. `Grapple action`, `Knockdown`, `the Tournament event`,
`Squire skill`), produce the two corpus artefacts:

1. **Markdown** — one topic file `rules_corpus/<book>/<NN-chapter>/<slug>.md`
   (prose = source of truth), and
2. **JSON** — the regenerated derived index `data/rules_index.jsonl` (never
   hand-edit; rebuild it). If the rule carries computed numbers the app uses,
   also update the relevant `data/*.json` table.

The corpus format, three-tier split, and page-numbering rule are documented in
`rules_corpus/README.md` — read it if anything below is unclear.

## Steps

### 1. Check for an existing entry first
Grep `rules_corpus/**` and `data/rules_index.jsonl` for the rule. If it already
exists, **update that file in place** rather than creating a duplicate (the index
build fails loudly on duplicate `id`s). Tell the user you're updating, not adding.

### 2. Find the authoritative text
- **Corpus first**, then the **PDFs** in `rulebooks/`: `corerulebook.pdf`,
  `gmhandbook.pdf`, `battlecards.pdf`, `pendragon_printable_feast_cards.pdf` (the
  whole `rulebooks/` folder is git-ignored, local only). Identify the book,
  chapter, and **printed** page range.
- Extract prose with raw mode (NOT `-layout` — raw reads two-column pages in
  order): `pdftotext -f <first> -l <last> rulebooks/corerulebook.pdf out.txt`.
  **For anything tabular — statblocks, dice tables — use `-layout` instead.**
  Raw mode silently interleaves two-column pages and can swap values between
  adjacent tables/statblocks; a subtly wrong number is worse than no entry.
  **PDF page = printed page + 3** for the core rulebook and the GM handbook, so
  offset the `-f/-l` range accordingly.
- If the PDFs are absent, ask the user to paste the rule text; do not invent
  rules from memory.

### 3. Clean & paraphrase — capture the *entire* rule
De-hyphenate line breaks, fix bullet glyphs (`Ő` → `-`), rejoin wrapped lines.
**Paraphrase** as a concise play aid — do not copy long verbatim passages (the
PDFs are copyrighted). Keep tables/dice/thresholds exact. Capture the **whole
rule** — every case, example, table, and edge condition — not just the snippet
you came for, so the corpus can answer the next lookup without the PDF.

**Write prose one paragraph per line — never hard-wrap.** Each paragraph,
bullet, and blockquote paragraph is one unbroken line, however long: a
hard-wrapped line silently breaks phrase `grep`, which defeats the point of a
corpus meant to be searched by phrase. Tables, headings, list markers, and
fenced code are unaffected — this only applies to prose.

### 4. Write the Markdown file
Path: `rules_corpus/<book>/<NN-chaptername>/<slug>.md` (create the chapter dir if
new; `NN` = two-digit chapter number, e.g. `07-combat`, `11-events`) — or the
corpus root for a genuine cross-cutting synthesis that draws on several
chapters (see existing root files for the pattern). Match the style of
existing files (`## headings`, `-` bullets, markdown tables, **bold** key
terms). Frontmatter — all keys required, exact types (the build script
validates and fails on anything missing/mistyped):

```yaml
---
id: core.combat.winners-outcome      # book.chaptername.slug — stable & unique
system: Pendragon 6th Edition        # the ruleset this file belongs to
book: core                           # core | gm | battlecards
chapter: "7 — Combat"                # "N — Name"
pages: [133]                         # PRINTED page numbers (ints), for citing
tags: [combat, resolution, critical] # lowercase kebab-case
title: Winner's Outcome
see_also: [core.combat.melee-distances, data:combat.json#critical_hit]
---
```

`see_also` is a **flow list of plain ids** (not Obsidian `[[wikilinks]]`,
even though a copy of this corpus is mirrored into an Obsidian vault — see
`rules_corpus/README.md`) — plain ids can point at `data:<file>#<key>`
computed refs, which a wikilink can't represent. Links related corpus `id`s
and, where relevant, computed data via `data:<file>#<key>`.

### 5. Update computed JSON only if the app needs the numbers
Prose stays in the corpus. If the rule defines a table/stat block/dice the app
consumes (like `combat.json`), add/update that entry too — but **edit the tracked
baseline `data/examplecombat.json`**, never the user's git-ignored working
`data/combat.json` (it holds their own content; see the encounter-generator-status
memory). Point at it from `see_also`.

### 6. Rebuild & verify the index
```
python build_rules_index.py
python build_rules_index.py --check   # must report up to date
```
The build validates frontmatter and `id` uniqueness; fix any error it reports.

### 7. Update the coverage/extraction tracking files
If `rules_corpus/COVERAGE.md` marks this chapter/topic ❌ or ⚠️, flip its
status and bump the file count in its header. If the extraction closed an
item from `rules_corpus/EXTRACTION-PLAN.md`'s queue, check it off there too.

### 8. Report & commit
Tell the user the file(s) created/updated, the `id`, and the printed pages cited.
Then commit + push per the auto-commit preference (corpus `.md` + regenerated
`rules_index.jsonl` + any `examplecombat.json`/`COVERAGE.md`/`EXTRACTION-PLAN.md`
change together).
