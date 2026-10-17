# Piece 8 — The players' board (Table) — CLOSED 2026-10-17

Also answers the user's separate request: make the board easier for players to follow what happened and whether it affected their knight.

## Decisions
1. (J1) Two board layouts, switching automatically. **Battle view** (between fights): title band (battle, Day/Turn, Intensity), Morale gauge, "This turn" card slot, deck spread row, knights row (Glory + Mounted), Fray feed. **Fight view** (during an Encounter): header band with battle/day/turn/encounter, Morale bar and Glory per knight; lanes by knight mirroring the GM tracker; Defeated strip.
2. (J2) Morale gauge: large number + "of N", draining fill, frame shifting colour (green-gold → deep red) AND texture (clean → bloodied) AND a word (Steady · Shaken · Bloodied · Breaking) — never colour alone; each change animates briefly with its reason ("−4 · Knights of Gorre"). No thresholds/minimums shown.
3. (J3) Styled card frames (parchment, heraldic border, faction device, name, GM flavour line); Opportunities gold-bordered with ★; set Encounter flips from the deck into the This-turn slot; picked cards carry the picking knight's shield token; spent Opportunities greyed. Real card art (local-only from the PDF) = possible later option, not v1.
4. (J4) Per-knight running Glory counter (this fight / this battle) that ticks up with a flourish ("+50 · Sir Erik unhorses a Knight of Gorre"). No ranking.
5. (J5) Knight cards as the players' reminder sheet: live effect chips (+5 Height, −5 two foes, −5 Battle army fumble, Charge +5, On foot, Reckless 2/3, Passion used, At the rear) and a "happened to you" line with the last 2–3 events touching that knight; full history in the Fray.
6. (J6/J6′) Never on the Table: Morale Minimum and Loss values (RAW GM Book p.126 — describe without mechanics), foe stats/HP numbers/Glory before defeat, KV, GM notes, unrevealed turn scripts, deck card details. Players see current Morale + cap, actual drops after the fact, and "Not enough Morale — Retire to the Rear". Foes keep wound-state words. Filtering server-side in web/table.py.
7. Already decided elsewhere and shown here: title card (piece 1), Intensity number and each roll's result (piece 3), charge/barrage/countercharge results (pieces 4, 6), postures and Passions (piece 5), the aftermath finale (piece 7).

## House rules
- None.

## Rejected / out of scope
- Showing Morale Minimum/Loss on cards; Glory ranking; real card art in v1.

## Open questions
- None.

## Interfaces
- web/table.py projection gains battle state; piece 9 events carry player-safe table_text.
