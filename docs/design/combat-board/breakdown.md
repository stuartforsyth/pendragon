# Combat board — breakdown

**Status:** stage 1. The pieces and their order were agreed on 2026-10-17. Next: a concept mockup, then grill piece 1.

## Why

The combat tracker is a list of rows ("looks like a spreadsheet"), and a foe can fight only one
knight. The user wants a **picture of the fight**:
- tokens for knights and foes
- **drag one onto the other, either way, to engage** (three knights onto a monster, three Picts onto a knight)
- **glowing red lines** between engaged tokens
- a richer players' board showing the same scene
- **real dice rolling across the board** whenever the app rolls

Folded in:
- the open questions from the "many knights, one foe" proposal (Attack all, Ignore, Glory for a shared foe)
- the tournament **rebated weapons ("for love")** switch

## Boundaries (agreed)

- **Tokens only, no map.** The app lays the clusters out automatically. There is no grid, no movement and no distance. Dragging only links and unlinks (VTT territory stays out).
- **Dice animate only the rolls the app makes**: foe attacks and damage, characteristics, Intensity, plain tray rolls. Players still roll physical dice and report outcomes (design-mechanic Notes). Player dice in the app would be a later, separate design.
- **The dice library is vendored** into `web/static/vendor/`, so it works offline mid-session.
- **Secrets stay server-side** (`web/table.py`): foe numbers, horse attacks, GM notes.

## The sequence of a fight (what the board must show)

1. **Launch.** Foes appear, unengaged, beside the party's tokens. Battle fights arrive from the Battle tool with posture and rounds.
2. **Engage.** The GM drags a token onto a token. They link: a red line, and a cluster forms. Clusters can merge (one knight fighting two foes, one of which is shared).
3. **Exchange** (one round, per engaged pair):
   - a foe attacks: roll its weapon in hand, the GM clicks the knight's result, damage if the foe wins
   - or a knight hits: enter the damage, armour comes off
   - Multiple Opponents applies to whoever faces several
4. **Outcomes.** Wounds, Major Wound, knockdown, unconscious, slain, fled, surrendered, disarmed, unhorsed. The defeated drop out of the cluster with Glory credited.
5. **Next round** until the fight ends. For battles: round limits by posture, withdraw, extra round.
6. **End.** Glory summary.

## Pieces

| # | Piece | Rules | Exists today | Scope |
|---|---|---|---|---|
| 1 | **Engagement model:** many-to-many links (either direction); 3-on-foot / 2-mounted limit; unlink; foe's Multiple Opponents −5s; *Attack all* with *Ignore*; Glory for a shared foe; **rebated "for love" fight switch** | `core.combat.multiple-opponents` p.148; Table A.1 `gm.glory-awards.combat-and-adventure` p.227 (beasties divided; ⅒ for love); `core.weapons.melee-weapons` (rebated) | `engaged_with` is a single knight name on the foe; knight-side MO chip and limit warning; Distribute foes equally; Glory credit to `defeated_with` | app |
| 2 | **GM battlefield:** token design (knight shield, foe device by category, condition ring, mounted/disarmed/elite marks); automatic cluster layout; drag to link; the token control card (weapon in hand, Attack, Hit, ±HP, status, horse, Height, modifier); type headers; battle extras (Morale strip, posture/rounds, Opportunity) | combat chapter, as built | lane/row tracker (`web/static/js/tools/combat.js`) | app |
| 3 | **Players' battlefield:** the same clusters as an illuminated-parchment scene; animated red links; hit flashes, wound words, falls, criticals; the Fray panel; knight cards (Glory, effects, Last line) | n/a (presentation) | lanes plus foe tiles plus Fray (`web/static/js/table.js`, `board.js`) | app |
| 4 | **Dice on the board:** 3D dice tumble on the players' screen (and a small tray on the GM's?) landing on the server's values; d20 checks, d6 damage pools, crit dice | dice engine `core.dice` | number "tumble" animation only | app |
| 5 | **Battle integration:** battle fights and Opportunity fights use the board; Morale gauge alongside; posture/withdraw marks on tokens | `gm.battle.*` | battle fights reuse the tracker with a Morale strip | app |

## Cross-cutting concerns

- **Events:**
  - links become `combat.link` / `combat.unlink`, or `combat.engage` extended to a set; legacy `combat.engage` must keep replaying
  - `combat.distribute` and `combat.wield` already exist
  - the rebated switch becomes a fight-level event
  - Attack all is a sequence of existing roll and attack events
- **Undo:** strike any link, attack or blow as today. One gesture is one event.
- **Table:** links, wound words, Disarmed and the narrative blows are public. Numbers, horse attacks and Height chips stay GM-only.
- **Performance and size:** the board must read on a 720p Discord stream. A 3D dice canvas must not stall the page. Respect `prefers-reduced-motion` (dice become a static result).
- **Tests:** click-through e2e for drag-to-link (both directions), Attack all, unlink, rebated, and dice landing on the logged values.
