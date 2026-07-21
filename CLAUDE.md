# Pendragon NPC + Encounter app

Tkinter, stdlib-only, GM tools for *King Arthur Pendragon* 5th Ed. Four tabs in a
`ttk.Notebook`: NPC Generator, Encounter (tracker), Adversary Creator, Encounter
Creator. Entry point: `./pendragon_names.py`.

## Answering rules questions — corpus first, then the PDFs

When you need to clarify, confirm, or apply a Pendragon rule (in code, in answers,
or when designing a feature):

1. **Check the rules corpus first.** Prose rules live in `rules_corpus/**/*.md`
   (one topic per file, YAML frontmatter). Search it — grep the corpus and/or
   `data/rules_index.jsonl` (the derived full-text index). Computed tables/dice
   the app uses live in `data/*.json` (`combat.json`, `rules.json`).
2. **Only if the corpus is silent or you're uncertain, consult the PDFs**
   (`corerulebook.pdf`, `gmhandbook.pdf`, `battlecards.pdf` — git-ignored, local
   only). Extract with `pdftotext -f <first> -l <last> <pdf> out.txt` (raw mode,
   NOT `-layout`). **PDF page = printed page + 3** for the core rulebook.
3. **Do not answer Pendragon rules from memory** when the corpus or a PDF can
   settle it — cite the corpus `id`/pages.

When you extract a new rule from the PDFs, capture it into the corpus so the next
lookup finds it: use the **`extract-rule`** skill (Markdown file + regenerated
JSON index). See `rules_corpus/README.md` for the format and workflow.

Never hand-edit `data/rules_index.jsonl` — regenerate it with
`python build_rules_index.py` (verify with `--check`).

## Data files

- `data/examplecombat.json` — tracked baseline for combat rules + the human-foe
  bestiary/tables (edit this for shared data).
- `data/combat.json` — the user's **git-ignored** working file with their own
  content (e.g. named adversaries). The app reads/writes only this. **Never
  delete or overwrite it**; a targeted string fix is fine, wholesale replacement
  is not.
