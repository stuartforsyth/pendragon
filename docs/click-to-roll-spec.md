# Project Specification — Click-to-roll everywhere

Status: **active convention**. Applies to every tab and every future feature.

## Rule

Whenever a **rollable value** is displayed to the user, it is rendered as a
**click-to-roll link**: clicking it performs the appropriate die roll,
reports the outcome, and records it.

Rollable values are:

| Displayed value | Roll on click | Outcomes |
|---|---|---|
| **Characteristic** (Size, Dexterity, …) | `d20` vs the value | **pass/fail only** — no critical/fumble (Core Ch.2) |
| **Skill** (incl. an attack's skill value) | `d20` vs the value | success / **critical** (roll == value) / failure / **fumble** (natural 20 unless value ≥ 20) |
| **Passion** | `d20` vs the value | success / critical / failure / fumble |
| **Personality trait** (each side of a pair) | `d20` vs that side's value | success / critical / failure / fumble |
| **Damage** (a dice expression, e.g. `4d6`, `5D6`) | roll the dice; prompt a **damage-mode chooser** — a **Rebated (½, rounded up)** checkbox that applies to either the **Normal** or **Critical (flat +4D6)** button (so a critical can be rebated), plus Cancel (roll & log nothing) | total + breakdown |

Non-rollable numbers (Hit Points, Move, Major Wound, Knockdown, Unconscious,
Glory, armour points, thresholds) are **plain text**, not links.

## Presentation

- Roll links are **visually distinct**: underlined, coloured (blue
  `#1a5fb4`; a Famous trait/passion value ≥ 16 stays bold brown `#8a4b00`),
  with a **hand cursor** on hover.
- The number itself is the click target; its label (e.g. "Strength ",
  "Sword ") is plain text beside it.

## Where each roll result goes

- **NPC Generator tab:** the result is appended to that NPC's **GM Notes**
  box (timestamped) and flashed in the shared status bar. Because it lands in
  GM Notes it is saved with the roster.
- **Encounter tab:** the result is written to the **combat log** (naming the
  engaged combatant) and flashed in the status bar.

In both cases the log line reads, e.g.:
`[12:17] Strength (13): rolled 10 — SUCCESS` /
`Sir Kay Sword (17): 10 — SUCCESS` /
`Damage 4d6 = 16  +critical 4D6 = 15  ->  31`.

## Shared implementation (do not fork the dice logic)

- Resolution lives once in `encounter.py`:
  - `resolve_skill(value) -> (roll, outcome)` — the d20 success/critical/
    fumble core (used for skills, passions, traits).
  - `roll_damage(expr, critical=False, rebated=False) -> (total, breakdown)` —
    weapon/damage dice; `critical` adds a flat +4D6, `rebated` halves (rounded
    up); the two combine (a rebated critical adds +4D6 then halves).
    `ask_damage_mode(parent, prompt)` is the shared chooser dialog (returns
    `(critical, rebated)` or `None` to cancel).
  - Characteristic rolls are pass/fail only: `roll = d20; success if roll <=
    value`. No `resolve_skill` crit/fumble branch.
- Dice strings go through `rules.roll_expr("XdY+Z")`.
- New UIs **reuse these**; they do not re-implement resolution.

## Rationale

The GM/player should be able to make any check straight from the sheet or the
tracker without hunting for a separate "roll" control — the displayed number
*is* the button. This keeps the two tabs consistent and makes new rollable
fields "free" (render them as a link and wire the shared roll helper).

## Applying this going forward

Any new feature that displays a characteristic, skill, damage expression,
passion, or trait **must** render it as a click-to-roll link wired to the
shared helpers above — not as inert text. If a genuinely non-interactive
display is needed (e.g. a printed export), that is the exception and should be
called out.

## Related

- `docs/characteristic-naming-spec.md` — characteristics are spelled out.
- `docs/encounter-generator-spec.md` §7–§8 — the encounter tracker's
  click-to-roll (the first place this pattern shipped).
