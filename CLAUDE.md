# Pendragon

GM tools for *King Arthur Pendragon* 6th Ed, as a local **web app** (FastAPI +
vanilla JS, no build step) that replaces the original Tkinter desktop app.

- `core/` — all game logic, UI-free (rules data, dice engine, NPC generation,
  combat model, adversary/encounter helpers). Both UIs use it; put new logic here.
- `web/` — server (`web/app.py`, routes in `web/routes/`), the event-sourced
  session log (`web/sessions.py`), combat state rebuilt from events
  (`web/combat_state.py`), and the player-safe Table projection (`web/table.py`
  — the only path to the shared screen; filter secrets there, server-side).
  Frontend: `web/templates/`, `web/static/js/{gm,table,lib}.js`, one module per
  GM tool in `web/static/js/tools/`, CSS per tool in `web/static/css/tools/`.
- Every action is an **event** appended to the active session (never edited or
  deleted — corrections are `meta.strike`/`meta.reveal` events). State that
  must survive undo is derived by replaying events, so events carry
  deterministic deltas, never re-rolls.
- Run: `./launch.sh` (port 8020) / `./stop.sh`; dev: `.venv/bin/python -m web --reload`.
  Throwaway instance against copies of the data: set `PENDRAGON_DATA_DIR` and
  `PENDRAGON_SESSIONS_DIR`. Tests: `.venv/bin/python -m pytest -q`.
- Legacy Tk app: `./pendragon.py` (tabs in `encounter.py`, `adversary.py`,
  `encounter_creator.py`) — kept working on `core/` until it is retired.
- Design decisions: `docs/web-app.md`.

## Answering rules questions — corpus first, then the PDFs

When you need to clarify, confirm, or apply a Pendragon rule (in code, in answers,
or when designing a feature):

1. **Check the rules corpus first.** Prose rules live in `rules_corpus/**/*.md`
   (one topic per file, YAML frontmatter). Search it — grep the corpus and/or
   `data/rules_index.jsonl` (the derived full-text index). Computed tables/dice
   the app uses live in `data/*.json` (`combat.json`, `rules.json`).
2. **Only if the corpus is silent or you're uncertain, consult the PDFs** in
   `rulebooks/` (`corerulebook.pdf`, `gmhandbook.pdf`, `battlecards.pdf`,
   `pendragon_printable_feast_cards.pdf` — the whole `rulebooks/` folder is
   git-ignored, local only). Extract with
   `pdftotext -f <first> -l <last> rulebooks/<pdf> out.txt` (raw mode, NOT
   `-layout`). **PDF page = printed page + 3** for both the core rulebook and the
   GM handbook.
3. **Do not answer Pendragon rules from memory** when the corpus or a PDF can
   settle it — cite the corpus `id`/pages.

**Whenever you query a rule from the PDFs, extract the *entire* rule into the
corpus before moving on** — capture the whole rule (all cases, examples, tables,
edge conditions), not just the snippet you needed, so the next lookup is answered
from the corpus and never needs the PDF again. Use the **`extract-rule`** skill
(Markdown file + regenerated JSON index). See `rules_corpus/README.md` for the
format and workflow.

Never hand-edit `data/rules_index.jsonl` — regenerate it with
`python build_rules_index.py` (verify with `--check`).

## Data files

- `data/examplecombat.json` — tracked baseline for combat rules + the human-foe
  bestiary/tables (edit this for shared data).
- `data/combat.json` — the user's **git-ignored** working file with their own
  content (e.g. named adversaries). The app reads/writes only this. **Never
  delete or overwrite it**; a targeted string fix is fine, wholesale replacement
  is not.
- `data/party.json`, `data/cast.json`, `sessions/*.json` — also the user's
  git-ignored content, with the same rule. Tests and screenshots must run
  against copies (see `tests/test_web.py`'s fixture).
