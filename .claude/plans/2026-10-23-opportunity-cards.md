# Opportunity cards — play offline, reproduce the card, allocate Glory

Repo copy of this plan (build-chain convention): `.claude/plans/2026-10-23-opportunity-cards.md` — copy it there as step 0.

## Context

A chosen Opportunity currently falls into the Foe flow: after ⑦ Morale it asks for ⑧ Postures and
⑨ "Begin the fight → combat tracker" (or, with no roster, "Award Glory in Combat…"), and the Player
board only ever shows a small card frame. Opportunities don't follow combat rules and vary too much
for a common framework (more cards will come), so for now they are **played offline at the table**.
The app must: let the GM pick an Opportunity (already works — crit pick or Intensity fumble), then
after ⑦ show a **faithful reproduction of the card** (Player board: the front/instructions; GM: the
back/stats), skip Postures and the combat tracker, let the GM **allocate the Glory listed on the card**
to one knight or all knights, and rejoin ⑩ End turn.

Source of truth for the cards: `rulebooks/battlecards.pdf` pp. 25–36 (5 Opportunity cards, 12 faces).
Reviewed in full:

| Card | Instruction faces | Stat faces | Glory on the card |
|---|---|---|---|
| Capture the Banner | p25 front, p26 (Roll Result table, rewards) | p29 Guards | carrier +100; each escort +50 (+£2 loot) |
| Fight Enemy Commander | p27 front | p28 Bodyguards, p30 Commander | commander's captor/killer +150 (stat card); bodyguard +50 each; all others +50 (+£5) |
| Rescue Captive Knights | p31 front, p32 top (Battle Roll Result) | p32 bottom Dismounted Squires | each +100 if freed; then per knight Battle roll: crit 350 / success 150 / failure 50 / fumble 0 |
| Rally the Division! | p33, p34 (stages, Results) | none | multiples of "battle Glory" (double/triple/×5) — no fixed number → custom amount |
| Clash of Champions | p35 front | p36 Champion | defeating the champion +50 (stat card Glory Award) |

Morale Loss/Minimum already in `data/examplecombat.json` and match the cards (Clash: loss 0).

## Design

### Turn flow (when the chosen card's role is `opportunity`)
⑦ Morale (unchanged, incl. minimum check / forced retire) → **⑧ Play the Opportunity** (new step
`opportunity`, replaces Postures + Fight; both shown as skipped "Opportunity — played at the table")
→ ⑩ End turn / End day (unchanged). Forced retire still skips everything to the rest step.

The `opportunity` step has two parts in one body: the cards (play offline) and **Resolve: award
Glory**, finished by **Done — rejoin End turn** (`battle.opportunity_done`), after which ⑩ is current.

### Events (append-only, deterministic, undoable via existing step cascade)
- Glory: `glory.awarded` (existing type, so `battle_state.reduce` folds it into `manual_glory`, the
  Table knight cards show the "last Glory" chip, and the finale totals include it) recorded by the
  battle step route with `battle` link `step: "opportunity"`, `fight: None`, `source: "opportunity"`,
  `reason` = preset label or GM text. One event per knight; "all knights" records one per conroi knight.
- `battle.opportunity_done` `{encounter}` → step done. `EVENT_STEP["battle.opportunity_done"]="opportunity"`.
- Reopening ⑦ (or ⑧) strikes the opportunity awards via the existing `_undo_targets` cascade
  (they carry `step: "opportunity"`; verify the glory events are picked up, since today
  `/api/glory` events have `step: None` and are skipped).

### Card content (faithful reproduction)
New tracked data file `data/battle_cards.json` of transcribed faces, keyed by encounter name:
```json
{"Capture the Banner": {
  "front": [ {"title","flavour","blocks":[{"p":"…**Valorous**…"}, {"results":{"title","rows":[["Win","…"]]}}],"footer":{"label":"Morale Minimum","value":"13"}},
             {"blocks":[…p26…]} ],
  "back":  [ {"title":"Capture the Banner","subtitle":"Guards","chars":{"SIZ":16,"DEX":15,"STR":14,"CON":17},
              "attacks":[["Spear","Spear","16","5D6"],…],"notes":["* …"],
              "health":[["Hit Points","33"],…],"other":[["Morale Loss","3D6"],["Armor Points","12+6"],…],
              "lines":[["Armor","Advanced hauberk…"],["Traits","Valorous 18"],…],"ransom":"£5"} ],
  "rewards": [ {"label":"Banner carrier","amount":100,"scope":"one"},
               {"label":"Escort","amount":50,"scope":"each"} ] } }
```
Inline markup limited to `**bold**` / `*italic*`, rendered by building DOM nodes (never innerHTML).
Transcribed by hand from `pdftotext` (raw) + page renders, then checked face by face against the
PNGs. **Fallback** for Opportunities without a transcription (user-made cards, future cards):
front = name + description + `rules` + Morale Minimum; back = stat faces built from the roster's
adversaries in the bestiary (same face structure, built in `core/`); rewards = none (custom only).

### Player board (Table) — `web/table.py` / `battle_state.table_view` + `table.js`
- While ⑧ `opportunity` is current or done this turn: `battle.opportunity = {"faces": front faces}`
  (**never** the back — filtered server-side in `table_view`).
- `battleView` switches to an **opportunity layout**: deck spread and tally strip hidden; the front
  faces fill the centre column side by side at the largest size that fits (CSS grid, `vh`-based card
  height, font scaled with `clamp()`); Morale gauge and knight cards stay (knights' Glory updates live
  as it's awarded). Before ⑦ is done the existing small selected card shows, as now.

### GM console — `web/static/js/tools/battle.js`
- `opportunityBody()` for step ⑧: the **back** (stat faces) beside the full instruction faces,
  rendered readably with the same face renderer; then **Resolve — award Glory**:
  - preset chips from `rewards` (`+100 Banner carrier`, `+50 each Escort`…), plus a custom amount + reason;
  - recipient: a knight picker (conroi knights) or **All knights**; `scope: "each"` presets default to All;
  - a running list of awards made this step (each strikeable via the existing strike/undo);
  - **Done — End turn ⑩**.
- `fightBody`'s no-roster branch ("Award Glory in Combat…") is removed; `/api/battle/fight` returns 409
  "Opportunities are played at the table" for an opportunity card.

### Shared rendering — `web/static/js/board.js` + `web/static/css/board.css`
- `cardFace(face)` (instruction face: olive title band with italic flavour, checked red border, body
  paragraphs, Roll-Result tables, footer roundel) and `statFace(face)` (dark title bar, red subtitle,
  SIZ/DEX/STR/CON row, Attacks / Health / Other tables, Armor/Traits/Skills/Passions lines, Ransom),
  both styled after the printed cards (pg-25/pg-28 renders). Used by the Table and the GM console.

## Files

- `data/battle_cards.json` (new, tracked) — 5 cards transcribed.
- `core/battle_cards.py` (new) — load faces; fallback faces from encounter + adversaries; validate rewards.
- `web/battle_state.py` — `STEP_ORDER` adds `"opportunity"` after `"morale"`; `steps()` branch for
  opportunity cards; `EVENT_STEP`; `table_view`/`gm_view` expose the faces (front only on the Table).
- `web/routes/battle.py` — `record_outcome`: `"opportunity_glory"` `{knights: [pid]|"all", amount, reason}`
  and `"opportunity_done"`; `/api/battle/fight` 409 for opportunities.
- `web/battle_state.py` `battle.turn_ended` — opportunity turns count as fought (Decision 2).
- `web/static/js/board.js`, `web/static/css/board.css`, `web/static/js/table.js`, `web/static/css/table.css`,
  `web/static/js/tools/battle.js`, `web/static/css/tools/battle.css`.
- `docs/design/battles/spec.md` — replace Open point 16 / "Opportunity without a roster" with this flow.
- Tests: `tests/test_web_battle.py`, `tests/test_battle_cards.py` (new), `tests/e2e/test_battle_clickthrough.py`.

Reuse: `BS.chosen`, `BS.conroi_ids`, `_rec`/`_link` in routes, `battle_state.reduce` manual-glory fold,
`battle_glory`, `_undo_targets`, `cardFrame` styling tokens, `h()` DOM helper, `amountEntry`/chips in battle.js.

## Execution (build chain, Sonnet executes)
0. Copy plan to `.claude/plans/2026-10-23-opportunity-cards.md`.
1. Transcribe the 5 cards into the data file (Sonnet, checked against page PNGs).
2. Backend: step, events, views, fallback, 409; unit tests (test-first).
3. Face renderers + CSS; Table opportunity layout; GM step body + Glory panel.
4. e2e click-through: crit pick of Clash of Champions → Morale → ⑧ shows faces on GM and Table (no stat
   text on Table) → award +50 to one knight and +50 to all → Done → End turn → next turn; reopen ⑦ strikes awards.
5. Review: fidelity+UX pass against this plan, `code-review` skill, then Q&A with Stuart; ≤2 cycles.
6. Commit only after Stuart approves the review summary.

## Verification
- `.venv/bin/python -m pytest -q` (unit + e2e).
- Throwaway instance on copies (`PENDRAGON_DATA_DIR`/`PENDRAGON_SESSIONS_DIR` → scratchpad, port 8021),
  resume the TEST battle, play each of the 5 Opportunities; Playwright screenshots of GM ⑧ and `/table`
  at 1136×912 and 1920×1080; compare each face with the PDF page render.
- Confirm `/api/table` JSON never contains stat-face fields.

## Decisions (Stuart, 2026-10-23)
1. **GM view:** back (stat faces) **and** the full instruction faces, side by side.
2. **Counts as fought:** yes. On `battle.turn_ended`, a turn with `battle.opportunity_done` adds the
   day to `fought_days` for knights with the conroi and sets `fought_last = True` (next charge roll
   treats them as engaged).
3. **Card text:** tracked in the repo as `data/battle_cards.json` (verbatim transcription).
4. **"All knights":** the knights with the conroi at ⑧ (`BS.conroi_ids(b)`), not those at the rear or fled.

## Revision (Stuart, mid-build, 2026-10-23)
**The players see only the green title box (red border) of the card** — name and flavour. All the
instruction text beneath it is GM-only, as are the stat faces. The Table gets
`{name, title, flavour}` and nothing else (filtered in `battle_state.table_view`); the GM console shows
the instruction faces + stat faces. This supersedes "Player board gets the front faces" above.
