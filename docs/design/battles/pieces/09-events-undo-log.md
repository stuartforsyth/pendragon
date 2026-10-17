# Piece 9 — Events, undo & log — CLOSED 2026-10-17

## Decisions
1. (K1) Events store what was entered (amount + reason, outcome, pick, posture, award, pill, position) — never derived/capped results; the battle reducer applies the rules (Morale cap, minimum check, outcomes) on replay, like combat state today. Small events per action; battle state rebuilt from them.
2. (K2) Stepper undo cascades: reopening a finished step strikes that step and every later step in the same turn, after a confirmation listing what will be undone. Single-event strike from the session log still works; an inconsistent turn is flagged by the stepper, not guessed.
3. (K3) Ending a session with a running battle writes `battle.paused`; Resume in a later session writes `battle.resumed` with a full snapshot of the rebuilt battle (and any fight in progress). Session files stand alone; undo reaches back to the resume, not into the previous session.
4. (K4) Saved battle definitions live in `data/combat.json` under a `battles` key (app reads/writes only that file). Bedegraine and Carlion ship as ready-made examples in `data/examplecombat.json`, turn-script text as short paraphrases, not book quotes.

## UI
- GM session log: battle events grouped under "Day N · Turn t" headers; a "Battle" filter chip. Table Fray shows each event's player-safe table_text.

## House rules
- None.

## Open questions
- None.
