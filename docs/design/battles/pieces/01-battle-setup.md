# Piece 1 — Battle setup (in progress)

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
