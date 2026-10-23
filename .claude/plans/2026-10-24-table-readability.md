# Table readability over Discord — type scale, space, and a card "spotlight"

Repo copy (build-chain convention): `.claude/plans/2026-10-24-table-readability.md` — copy as step 0.

## Context

The Table (`/table`) is shared over Discord, which downsamples and compresses video: anything under
~16px at 1080p smears. Stuart loves the look and the way the important thing is promoted to take the
space (cards, the Field, the latest roll). The problems, measured at 1920×1080 (audit of `table.css`,
`board.css`, `cardface.css`):

- **Text under 16px that players need or glance at:** field token names/subs `13.5×s`/`13×s`
  (s = 0.55–1.6, so 7–20px), knight-card chips `.fx` 12, "Glory" label 11, "Last" 11, "played by" 15,
  card kind labels 9–12, "Morale Minimum" 11–14 on deck cards, `.cant-rib` 9.5, deck label `.dl` 12,
  Fray dividers 12, tally 10.5–15, Morale gauge labels 13–15, header mode text 15, `.ttok` 12.
- **Absolute px everywhere**, so the composition only works at one window size; at 1280×720 text is
  relatively larger and clips, on a bigger window it is relatively tiny.
- **Wasted space beside cramped text:** the Morale gauge takes a 230px column but is ~360px tall
  (≈435px empty under it); the Fray column (340px) holds mostly 16–18px entries; the Defeated tally
  (~175px) uses the smallest text on screen; the knights row is 110–165px for tiny chips; the Mustering
  title repeats the header; Mustering lays out the whole library (18 cards, runs off screen).
- **No way to say "everyone read THIS"** — the GM can only read a card out.

Intended outcome: every player-facing word ≥ ~20px at 1080p (secondary labels ≥ 16px, nothing player-facing
below that), the layout scaling as one unit with the window, the space re-spent on what matters, and a
GM-driven **spotlight** that blows a card up over the Table.

## Decisions (Stuart, 2026-10-24)
1. **Defeated ledger folds into the knight cards** (a big ⚔ count); the full ledger shows in the finale
   and when spotlighted.
2. **Mustering shows the title only** until a step where players choose; cards then appear. The GM can
   still spotlight any card.
3. Spotlight = the existing overlay idea: GM clicks, players read.

## Design

### A. One scale for the whole Table (foundation)
- `table.js` sets `document.documentElement.style.fontSize = 16 * min(innerWidth/1920, innerHeight/1080) * tableScale`
  px on load/resize (`tableScale` from the payload, below). Convert Table text/box sizes in `table.css`,
  `board.css` and the Table-facing parts of `cardface.css` from `px` to `rem` (÷16) by a script
  (`font-size`, paddings, widths, gaps), so the composition is identical at 1280×720, 1920×1080 and 4K.
  The existing `clamp(… vh …)` card sizes become plain rem.
- **Type tokens** in `:root`: `--t-hero` (numbers, titles) 2.6rem+, `--t-body` 1.25rem (20px),
  `--t-label` 1rem (16px, floor). Rule: nothing player-facing below `--t-label`; caps micro-labels
  ("Glory", "Last", "Morale", kind labels) are either promoted to `--t-label` or dropped.
- **GM text-size control**: new `table_scale` (0.9 / 1 / 1.15 / 1.3), in-memory like `table_mode`
  (`web/state.py`, `POST /api/table/scale` mirroring `/api/table/mode`, `scale` in `table.build`).
  Two small buttons in the GM bar next to Auto/Story/Fight/Battle (`gm.js` `renderTableMode`): "A−  A+".
- **Guard test** `tests/test_table_css.py`: parse the three CSS files; fail on any `font-size` below
  `1rem` (px < 16 equiv) unless the selector is on an explicit allow-list of purely decorative rules.
  This is what stops regression.

### B. Space re-spent (battle view, then fight view)
- **Morale into the header bar** (battle and fight): a wide horizontal gauge "MORALE 20 / 22 STEADY ▮▮▮▮▯"
  with the last change, in the header's empty middle; frees the 230px left column → the centre gets
  ~1480px (8 cards/row at readable size). Reuse `moraleGauge()` (`board.js`) with a `horizontal` variant.
- **Fray slimmed**: battle view keeps the newest 3 entries at `--t-body` (older ones dropped, they are in
  the GM log); fight view keeps the latest-roll card + 3 minis. Column 340px → ~300px, no divider text.
- **Knight cards compact + bigger text**: shield, name, player (inline, `--t-label`), Glory number, ⚔ count,
  effect chips at `--t-label`; drop the "LAST …" line (the Fray has it) and the "Glory"/"Last" micro-labels;
  height ~120 → ~95px; laurel/crown keep, `played by` folds beside the name.
- **Defeated tally removed from the board** (Decision 1): `tallyStrip()` is no longer rendered in the battle
  or fight view; `knightCard` gets `defeated` count (from `p.battle_knights[].tally.length`);
  the finale scene already lists them; spotlight can show the ledger (kind "tally", later).
- **Mustering** (Decision 2): `battleView` shows only the title block (trim the duplicated kicker/where/day
  to what the header does not already say) while `status === "mustering"`; `_table_options` returns `[]` at
  mustering. The deck spread returns at the choice steps.
- **Cards**: deck/picked cards go from 15px to ~20px base (now cheap: Mustering no longer competes);
  "Morale Minimum" footer → `--t-label`; `.kind` label → `--t-label`; `.cant-rib` → `--t-label`.
  Keep scroll (`.bv-centre`, already added) for the rare overflow.
- **Field (fight view)**: token labels get a **floor of 16px** regardless of `--s` (`field.css` rule:
  `font-size: max(1rem, calc(0.84rem*var(--s)))`); `layoutArea` (`field.js`) is passed `tokW/tokH` derived
  from that floor (≈ 170×110) so clusters pack without overlap; when even min scale cannot fit, foe sub-labels
  (wound word) hide and the foe shows its short name only; the `.tfield` may scroll vertically as a last resort.
  Wound state keeps its drop badges (not text-dependent).

### C. Spotlight — GM clicks a card, it blows up over the Table
Modelled on the rule overlay (`rules.js` → `/api/rules/{id}/show` → `rule.shown` event → `table.py shown_rule()`
→ `table.js ruleOverlay()`), reusing its CSS animation and `position:fixed` layer.
- **Events**: `table.spotlight` (public) `{kind:"card", name}`; `table.spotlight_off` (gm visibility).
  Routes in a new `web/routes/spotlight.py`: `POST /api/spotlight {kind, name}`, `POST /api/spotlight/off`.
  The event stores only the name; the server resolves display data at payload time (nothing secret in events).
- **`web/table.py`**: `shown_spotlight(events, fl)` — a shared helper with `shown_rule` (extract
  `_latest_toggle(events, fl, on, off)`); the spotlight also ends at the **next `battle.*` step event**
  (the choice has moved on) and at `table.cleared` (already a cutoff). `build()` adds `spotlight`.
- **`web/battle_state.py`**: `table_card(b, name, library, faces_for)` returns the player-safe dict
  `{name, flavour (green(), incl. typed override), minimum, opportunity}` — the same fields `table_view`
  already exposes; used for the spotlight payload so no new leak path. `state.table_payload()` resolves it.
- **`web/static/js/table.js`**: `spotlightOverlay(sp)` (same shape as `ruleOverlay`): a dim layer with the
  card at ~88vh tall — `cardFrame(c, {size:"huge"})` (new size in `board.css`: base font ~3.6rem; Opportunities
  stay gold); tumbles in with the existing `card-in`/`bloom` animation; removed when `spotlight` is null.
- **GM side (`battle.js`, `cardface.js`)**: a "present" button (same icon as Rules' Show on Table) in the corner
  of every `cardTile` (②), the picks/select `.gcard`s and the Opportunity body; when active it becomes
  "Remove from Table". A top-bar chip "On the Table: <card> ✕" (next to Rules ▾, `gm.js`) clears it from
  any tool. Clicking the card itself still sets the Encounter; the explode button never does (stopPropagation,
  like the flip toggle).
- Later kinds (not in this build, same plumbing): `knight` (Glory + defeated list), `tally`, `morale`.

## Files
- New: `web/routes/spotlight.py`, `tests/test_table_css.py`, `tests/test_web_spotlight.py`, `tests/e2e/test_spotlight.py`, a script
  `scripts/rem_convert.py` (one-off px→rem, kept for the record).
- Modified: `web/static/css/table.css`, `board.css`, `cardface.css`, `field.css` (token labels, in `combat.css`/`table.css`),
  `web/static/js/table.js`, `board.js`, `field.js`, `tools/battle.js`, `gm.js`, `cardface.js`,
  `web/table.py`, `web/battle_state.py` (`table_card`, mustering options), `web/state.py`, `web/routes/session.py`
  (scale), `web/app.py` (include router), `docs/design/battles/spec.md` (players' board section), tests that
  assert the Defeated strip / Mustering spread.
- Reuse: `ruleOverlay` pattern + `.rule-overlay` CSS, `shown_rule`, `moraleGauge`, `cardFrame`, `green()`,
  `table_mode` plumbing for `table_scale`, `layoutArea`/`linkLines`.

## Execution (build chain, Sonnet executes; plan reviewed by Opus here)
0. Copy plan into repo. 1. **A** (scale + tokens + rem script + guard test); screenshot every view at 1920×1080 and
1280×720. 2. **C** spotlight (server → Table → GM buttons → tests). 3. **B** space (battle view → fight view →
cards → Field floor), one commit per sub-step, each with a stream-simulation check (below). 4. Review: fidelity+UX
against this plan, `code-review`, Q&A with Stuart (≤2 cycles). 5. Commit/push only after Stuart approves.

## Verification
- **Stream simulation script** (`scripts/stream_sim.py`, Playwright): render `/table` for each state (Mustering,
  Set Encounter, Choose your fate, Opportunity, fight with 9 foes, finale), screenshot at 1920×1080, then
  downscale to 960×540 and JPEG q≈35 (what Discord can do to a share) and Read the images: every player-facing
  word must still be legible. Also at 1280×720 and with `table_scale` 1.3.
- Unit/e2e: CSS floor test; spotlight lifecycle (on → payload has only safe fields → next battle step clears it →
  off event clears it → Clear Table clears it); GM button click-through (explode doesn't set the Encounter);
  Mustering shows title only; fight view labels ≥ 16px computed (`getComputedStyle`) for tokens at 9 foes;
  scroll position test still passes; full suite (`.venv/bin/python -m pytest -q`).
- Manual: Stuart shares the Table to Discord and checks the three busiest screens.

## Risks / open
- rem conversion touches most Table CSS — mitigated by the script + screenshot diffs per view.
- Field with 12+ foes at a 16px label floor may need the vertical scroll fallback; verify with Bedegraine (18 foes).
- Spotlight resolves card text server-side from the current library; a card renamed mid-battle shows the new text (acceptable).
