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

The rules corpus is **not in this repo**: `rules_corpus/` is a **read-only
symlink** to the user's ttrpg-parser project
(`/home/stuart/code/ttrpg-parser/Pendragon by Chaosium/rules-corpus/`), which
owns the corpus, its format (`CONVENTIONS.md` there), the extraction skills
(`ttrpgextract`, `ttrpgvalidate`) and the index builder. **Never write to
`rules_corpus/` or anywhere under `/home/stuart/code/ttrpg-parser/`** — read
only, with one exception: the **issue queue** below. The app reads `rules_corpus/index.jsonl` (`web/rules_index.py`).

When you need to clarify, confirm, or apply a Pendragon rule (in code, in answers,
or when designing a feature):

1. **Check the rules corpus first.** Prose rules live in `rules_corpus/**/*.md`
   (one topic per file, YAML frontmatter; tables are separate files under
   `rules_corpus/tables/`, embedded in topic files as `![[table-…]]`). Grep the
   corpus and/or `rules_corpus/index.jsonl`. Computed tables/dice the app uses
   live in `data/*.json` (`combat.json`, `rules.json`).
2. **Only if the corpus is silent or you're uncertain, consult the PDFs** in
   `rulebooks/` (`corerulebook.pdf`, `gmhandbook.pdf`, `battlecards.pdf`,
   `pendragon_printable_feast_cards.pdf` — the whole `rulebooks/` folder is
   git-ignored, local only). Extract with
   `pdftotext -f <first> -l <last> rulebooks/<pdf> out.txt` (raw mode, NOT
   `-layout`). **PDF page = printed page + 3** for both the core rulebook and the
   GM handbook.
3. **Do not answer Pendragon rules from memory** when the corpus or a PDF can
   settle it — cite the corpus `id`/pages.

### Reporting corpus problems — the issue queue

If the corpus is wrong, missing a rule, self-contradictory, or malformed, answer
the question from the PDF, then **file an issue** so ttrpg-parser's next
`/ttrpgextract` run fixes it in the master corpus: add one new file
`/home/stuart/code/ttrpg-parser/Pendragon by Chaosium/rules-issues/YYYY-MM-DD-slug.md`
in the format in that folder's `README.md` (`reported-by: pendragon-names`;
check existing open issues first to avoid duplicates). That new file is the
*only* thing you may write there — never edit the corpus or other issue files,
and never copy a fix into this repo.

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

## Homeserver deployment

This app deploys to the **homeserver** under the contract in
`~/code/nas-container-deploy/CONTRACT.md` (GitHub: `stuartforsyth/nas-container-deploy`, private).

- Read `CONTRACT.md` and `GLOSSARY.md` there before changing any deploy script, compose file,
  Dockerfile or `homeserver.toml`. The contract wins over anything in this repo's docs.
- This repo owns its deployment: `scripts/deploy` must meet the contract's Deploy rules (R-DEP-*);
  reference: `~/code/nas-container-deploy/templates/deploy`. Deploy target is the SSH alias `homeserver`. Never name the
  machine or its IPs.
- Need a rule changed, or an exception? Do not work around the contract. Add a request file to
  `~/code/nas-container-deploy/requests/inbox/` (template: `requests/TEMPLATE.md`). That is the
  only file you may write in that repo.
- Check compliance with `~/code/nas-container-deploy/bin/audit` (read-only).
- **Status: planned.** Not on the homeserver yet. When it moves there, write `scripts/deploy` from the
  reference, add `homeserver.toml`, and request an inventory entry via `requests/inbox/`. Today it runs locally on port 8020 with `./launch.sh`.
