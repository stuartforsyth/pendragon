# Rules Corpus Extraction Plan — resumable

**Goal:** a complete, accurate accounting of the Pendragon 6th Edition rules
in `rules_corpus/`, extracted from `rulebooks/corerulebook.pdf` and
`rulebooks/gmhandbook.pdf`.

**Status at last run (12 Sep 2026):** 120 rule files. Core Rulebook
essentially complete; GM Book partly done (Ch.3 Arthurian Acts, Ch.6 Battle,
Appendix A Glory). `COVERAGE.md` is the authoritative chapter-by-chapter
map — **read it first, it is the checklist.** This file is the *method* and
the *queue*. Use the **`extract-rule`** skill to do the actual extraction —
it implements the method below.

---

## How to pick this up

1. Read `COVERAGE.md` for what is ❌ / ⚠️ and the priority order.
2. Take the next unstarted item from the queue below.
3. Extract it with `extract-rule`, which writes the Markdown file(s) and
   regenerates `data/rules_index.jsonl`, then **update `COVERAGE.md`** —
   flip the status, update the file count in its header.
4. Append anything newly discovered to *Findings* at the bottom of this file.

Work in **one chapter-section at a time**. Do not try to do a whole GM
chapter in one pass.

---

## Method

**Page offset is printed + 3 for both books.** Cite **printed** numbers in
`pages:`.

```bash
# prose — raw mode reads two-column pages in the right order
pdftotext -f <pdf-first> -l <pdf-last> rulebooks/gmhandbook.pdf -

# statblocks and tables — ALWAYS use -layout, raw mode interleaves the
# columns and silently swaps values between adjacent blocks
pdftotext -layout -f <pdf-first> -l <pdf-last> rulebooks/gmhandbook.pdf -
```

> ==Use `-layout` for anything tabular.== Extracting statblocks or Foe
> Encounter tables in raw mode can put one row's values against its
> neighbour's. A subtly wrong number is worse than no entry at all.

> [!important] Never hard-wrap prose
> Write each paragraph, bullet, and blockquote paragraph as **one unbroken
> line**. A hard-wrapped line silently breaks phrase `grep` — the whole
> point of a corpus you search by phrase. Markdown renders both the same.
>
> To repair an already-wrapped file: join continuation lines within a
> paragraph/bullet/blockquote, leave frontmatter/tables/headings/rules/code
> untouched, and **compare the word multiset before and after — refuse to
> write any file that fails.** Eyeball every `> [!` callout line afterwards;
> a reflow pass can flatten a callout title into the line below it without
> losing any words, so the word-multiset check alone won't catch that.

**Frontmatter — all eight keys required** (`id`, `system`, `book`, `chapter`,
`pages`, `tags`, `title`, `see_also`). `see_also` is a **flow list of plain
ids** (`[core.combat.knockdown, data:combat.json#critical_hit]`), not
Obsidian wikilinks — this corpus is grepped, not browsed in Obsidian, and
`see_also` needs to be able to point at `data/*.json` refs the app uses.

---

## Queue (from `COVERAGE.md`, in priority order)

1. GM Book Ch.1 — The Fabled Realm (geography/setting is mostly background,
   but *Creating a Campaign* and *Sample Holding: Underditch Hundred* may be
   worth a GM-facing extraction).
2. GM Book Ch.2 — Running Pendragon: *How to Use Characteristics*,
   *Sessions/Scenarios/Campaigns*, *Tracking Time* are rules-adjacent GM
   advice worth capturing.
3. GM Book Ch.4–5 — not yet audited against the corpus at all; read the
   table of contents and slot into `COVERAGE.md` before extracting.
4. GM Book — anything beyond Ch.6/Appendix A not yet audited.

---

## Findings

- 12 Sep 2026 — baselined 25 files in from a parallel Obsidian-vault copy of
  this corpus that had drifted ahead independently; see the project's git
  log for the reconciliation (a handful of files had genuinely diverged in
  both directions, not just formatting — resolved by reading the PDF as
  tiebreaker in each case).
