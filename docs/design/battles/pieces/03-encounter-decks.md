# Piece 3 — Encounter decks & selection (in progress)

## Decisions so far
1. Loop: create/set up an encounter → mark it battle-approved via an explicit battle role (Foe / Opportunity / none) → it becomes selectable in battles. Battle encounters carry Morale Minimum and Morale Loss (default from their adversaries' cards, editable).
2. Data completeness: the 12 foe cards and 5 Opportunity cards must be checked complete and correct against battlecards.pdf (audit running; becomes a build slice).
3. Opportunities kept minimal for adaptability (own and future-module Opportunities): an Opportunity = name + flavour/description + Morale Minimum (+ Loss) + free-text rules/rewards + an *optional* foe roster (only when there's something to fight, e.g. dismounted squires). No per-card logic, no reward tables; card rolls and decisions are played at the table. App enforces only RAW structure: once per battle, reachable on a Battle crit (or GM's choice on an Intensity fumble), must be played if chosen. Glory from rewards is credited with a generic "Award Glory" action (usable anywhere).
4. Decks are fluid: a day can be pre-scripted (e.g. Day 1 = Pict cards only) and edited at any time mid-battle (add newly arrived foes, remove, quick-create). Draw = optional randomiser for the GM's set Encounter (Foes only, not Morale-filtered).
5. Quick-create mid-battle saves to the library as a battle encounter and adds to the current day's deck.
6. UI: deck picker checklist (Min/Loss/KV visible to GM), Foes/Opportunities tabs, reused for turn-script restrictions.

## Notes
- Visual: when an Encounter is set, a physical-looking card is "played" on the players' board (→ piece 8).
- Selection flow under redesign (see below).

## Battle-card data audit (2026-10-17, read-only, vs battlecards.pdf)
- examplecombat.json: all numbers on the 12 foe cards match the PDF (stats, attacks, HP/KD/MW/Unc, armor+shield, Morale Min/Loss, Glory, KV, ransom, counts).
- Missing: cards' own flavour/rules text (only one-line paraphrases); weapon footnotes (−1D6 shield protection, +1D6 vs mail, spear negates height penalty, inferior sword breaks on ties); 1D6 weapon tables (Saxons, Kerns); special rules (Knifemen horse-first, Saxon shield wall pairing, Kerns max 3 attackers, Archers Valorous-or-flee, Malahaut shield penalty pre-applied, Javeliniers/Archers missile reference).
- Wrong: Irish Kerns armor 4 / shield 0 should be armor 0 + shield 4 (Targe, "unarmored"); Archers "a third injured" → "seriously injured".
- Mounted: Gorre, Lothian, Malahaut, Cornwall, Breton, Northern Prickers. On foot: Pikemen, Javeliniers, Knifemen, Saxons, Kerns, Archers.
- The 5 Opportunity cards are absent from the app data.
- User's combat.json: Knights of Lothian replaced by a hand-edited version that lost battle_card, morale_minimum, per_player, ransom, morale_loss, KV and Glory (0 vs 50), HP 30 vs 31. User "Bodyguards" differ slightly from the card.
- Code bug: per-player counts use Python round() (banker's rounding) in core/combat.py:78, 82, 397 — 1.5× for 3 knights gives 4 instead of 5 (cards say "rounded normally").
