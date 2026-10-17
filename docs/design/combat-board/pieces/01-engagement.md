# Piece 1 — Engagement model

**Status:** rules and workflow settled on 2026-10-17 (Q1–Q9). The UI conversation is still to come.

## Decisions

1. **What a drag does.** Dragging a **knight** onto a foe always **adds** a link: a knight can fight several foes, or join others on one foe. Dragging a **foe** onto a knight **moves** it: its previous link goes (today's quick retarget). To share one powerful foe, drag each knight onto it.
2. **Other drops.** A foe dropped on another foe joins that foe's knight or knights. A knight dropped on a knight does nothing.
3. **Unlinking.** Three ways: the ✕ on a hovered line, dragging a foe to *Waiting*, or dragging a knight onto empty ground.
4. **Over the limit.** More than 3 attackers on foot (2 mounted) on one opponent turns the link amber and shows a warning. The drop is still allowed: warn, don't block (`core.combat.multiple-opponents`).
5. **A foe facing several knights** takes −5 per knight after the first on each of its rolls, applied automatically (`core.combat.multiple-opponents`). *(Revised 2026-10-17: Ignore isn't tracked at all. If a foe ignores someone, the GM just enters the Hit or rolls the damage as usual.)*
6. **Attacks stay one at a time, as today, in the new format.** The foe's card has **Attack** for the weapon in hand. If the foe is linked to several knights, the GM picks which knight with a chip first; otherwise it attacks the knight it's fighting. Then the knight's result chips, then damage if it wins. *(Revised 2026-10-17: "Attack all" was my proposal, not the user's request, and is dropped.)*
7. **Glory for a shared foe.**
   - A beast, monster or fairy: divided among the knights linked to it when it falls, each share rounded half up (Table A.1, RAW).
   - A human foe: the knight who landed the defeating blow (**Hit by…** asks which knight struck).
   - A foe defeated any other way (status, ±HP): the GM is asked which knight, if several are linked.
   - Reassign Glory still overrides all of these.
8. **Rebated weapons ("for love").** A fight-level switch, offered at launch and as a header toggle.
   - It halves every blow, both ways: the critical dice are added first, then the total is halved, and Knockdown uses the full roll.
   - A foe defeated while it's on gives ⅒ Combat Glory (Table A.1).
   - Turning it on or off is logged.
9. **Distribute foes equally** moves only foes linked to at most one knight, and never splits a shared foe.

## UI decisions

- U13 **Rebated:** a toggle in the fight header plus a checkbox at launch. While it's on, a "for love" ribbon shows on the players' board.

## Open questions

- (none for rules or workflow; the UI conversation is next)

## User notes (2026-10-17, on the concept mockup)

- The mockups are not final. On the sketch's dice (for piece 4):
  - "they stack on top of each other"
  - "they don't stay where they land"
  - "the d20 spins in from the outside with the chosen number already in place — it doesn't roll naturally"
- Both boards should be **less linear and use free space better**.
- They must work for **six knights**, not just three.

## Rules cited

- `core.combat.multiple-opponents` p.148
- `gm.glory-awards.combat-and-adventure` p.227 (Table A.1)
- `core.weapons.melee-weapons` (rebated)

## Interfaces

- **Piece 2 (GM battlefield):** drag targets, line ✕, the foe card's Attack with knight chips.
- **Piece 3 (players' board):** shared clusters (one foe, several lines).
