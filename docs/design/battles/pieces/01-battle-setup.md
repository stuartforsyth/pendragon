# Piece 1 — Battle setup — CLOSED 2026-10-17

## Inputs captured so far (not yet final decisions)
- Must serve on-the-fly battles AND pre-written multi-day scripted events (e.g. Bedegraine: 2 days, Intensity 14 / 18, 5 turns/day, per-day battle-card deck, per-turn scripted events).
- Minimum to launch: Size (plus optional days / flavour). Commander, Morale etc. decided after start.
- Battles are their own thing: saved pre-written battles in the Library; live battle state survives across sessions (pause/resume).
- Three play modes: random foe fight; set encounter fight (exists); battle = container of many encounter fights + battle metadata, with quick pick/create of an encounter into the current battle.
- Foe kind (Table 6.9 plunder): design consideration for piece 7, not needed for v1 setup.
- Mounted pill (cross-piece → piece 6): per-combatant toggle, auto Height ±5 and Large-shield −2 mounted.
- **Retire to the Rear for one or more turns, with Morale changed during the rest** (→ piece 5; RAW gm.battle.battlefield-position-and-surrender p.131: ≥1 Battle Turn, +1D6 Morale on retiring, +1D6/turn while disengaged, capped at starting Morale; then return next turn or Left the Field; First Aid 14+1D6 per knight; remounts via Squire/Horsemanship).
- Dice: the GM enters players' rolls (screenshare); the app enforces integrity (e.g. rest Morale +1D6 entered, capped at starting Morale). Player-side VTT dice = later design phase.
- Forced retire only when the conroi is left with no engageable option at its Morale after the turn's Intensity/Battle rolls (RAW step 4: the *selected* Encounter's minimum).
- Rest is decided at the start of a turn: voluntary (too injured) or forced (nothing engageable).
- Mid-fight retreat: not built (immersion). GM plays it out at the table, ends the fight normally, and marks the conroi retired at the start of the next turn — same outcome as RAW.

## Decisions (accepted 2026-10-17)
1. Battle → Days → optional per-day turn scripts. Turn-script modifiers are text the GM applies (no automation in v1).
2. Each new day resets the engagement (Morale to start, Passions usable again, per-day Participation Glory) — labelled "scenario rule" (Sword Campaign).
3. Battles pause/resume across sessions by full snapshot (`battle.resumed`), allowed anywhere incl. mid-fight. Library holds the template; the session holds the live copy.
4. Mounted state persists within a battle (default mounted only at start); adversaries get an explicit `mounted` flag. Detail → piece 6.
5. "Random fight" draws from any encounter with optional tag filter; separate from the battle deck (piece 3).
6. Rest/retire: start-of-turn decision (voluntary or forced only when no engageable option after the turn's rolls); rest Morale +1D6 entered by GM, capped at start; manual Morale adjust = logged GM override. Mid-fight retreat not built.

7. Glory ledger (cross-cutting → pieces 6, 7, 8): Glory auto-awarded when a foe is unconscious, dead, fled or surrendered (Table A.1, gm.glory-awards.combat-and-adventure p.227), credited to the knight it was engaged with, else a "Who defeated them?" prompt; each award an undoable/reassignable event. Tallies: per standalone fight, and per whole battle (per-day breakdown kept internally for per-day participation Glory). No session tally, no lifetime totals (paper). Works in all three modes; beast-glory splitting later.
8. Encounter end raises conroi Morale by total KV of defeated foes, capped at start (RAW, gm.battle.fighting-the-battle).

## UI
- Rail: **Battle** (play group, beside Combat) — launch panel when idle, live battle when running. **Battles** (prep group, beside Encounters) — saved-battle library editor (list + form + Launch), Encounters pattern.
- Launch panel: Paused battles (Resume, shows day/turn/Morale) · Quick battle (Size chips with turns + Intensity dice hint, Days stepper, Name, folded flavour: where/against/notes, Launch) · Saved battles list (Launch). Quick launch = 2 clicks.
- Saved-battle editor: header (name, Size, flavour) + one card per day (Intensity roll-from-Size or fixed; Turns stepper, hint when over Table 6.1 max — scenario override, not blocked; First charge toggle; deck picker → piece 3; notes; turn scripts: turn #, text, restricted deck, "only if Intensity succeeds") + Add day.
- Launch → `battle.started` (full definition copy) → Battle tool in **Mustering** (Turn 0, piece 2) → Table switches to Battle mode with a title card (name, where, against, Day). Rolled Intensity is rolled at the start of each day (GM "roll for me" or entered). ~~Intensity never shown on the Table~~ — CORRECTED in piece 3 (decision 7): Intensity is shown to players, RAW.
- Live "Battle settings" drawer edits current + future days (past locked), every change a logged event. "Save as template" copies a running battle's definition (no live state) to the library.

## House rules
- None. Days, per-day Intensity and per-day engagement reset come from the Sword Campaign scenario (labelled "scenario rule"), which the core rules allow ("max turns per Table 6.1 or the scenario").

## Rejected / out of scope
- Foe kind at setup — only drives Table 6.9 plunder; asked at aftermath (piece 7). Not game-breaking for v1.
- Automated turn-script modifiers (text only in v1).
- Pre-scripted rest turns (rest is decided in play).
- Mid-fight "Call the retreat" (played out at the table; marked at next turn start).
- Session Glory tally; lifetime Glory.

## Open questions
- None.

## Interfaces
- Piece 2: Mustering state; Morale must exist before Turn 1. Piece 3: deck picker, battle-approved pool, random fight tag filter. Piece 5: turn loop, rest. Piece 6: mounted pill, Glory awards, KV Morale. Piece 7: participation Glory, foe kind/plunder. Piece 8: title card, Morale visual, Glory tally. Piece 9: battle.* events, pause/resume snapshot.

## Notes for later pieces
- Piece 8 (Table): current Morale is a major visual on the players' board, shifting from green/clean to red/bloody as it drops.
