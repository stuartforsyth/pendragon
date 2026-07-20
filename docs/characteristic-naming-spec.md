# Project Specification — Characteristic naming (spelled out, no acronyms)

Status: **active convention**. Applies to every tab and every future feature.

## Rule

Whenever a **characteristic** is shown to the user on screen, it is spelled
out in full — never the three/four-letter acronym.

| Store as (data / dict key) | Display as |
|---|---|
| `SIZ` | **Size** |
| `DEX` | **Dexterity** |
| `STR` | **Strength** |
| `CON` | **Constitution** |
| `APP` | **Appeal** |

## Why

The acronyms (SIZ/DEX/STR/CON/APP) are compact but not self-explanatory,
especially for players new to Pendragon. The Encounter tab already spells
them out; the NPC Generator now matches. One consistent, readable naming
across the app.

## Single source of truth

The mapping lives once, in `encounter.py`:

```python
CHAR_FULL = {"SIZ": "Size", "DEX": "Dexterity", "STR": "Strength",
             "CON": "Constitution", "APP": "Appeal"}
```

Any UI that renders characteristics imports/uses `encounter_module.CHAR_FULL`
rather than re-spelling the names inline. Do **not** hard-code "Size",
"Dexterity", … at call sites; go through the map so a future rename is a
one-line change.

## Scope

- **Applies to on-screen display** (the result panel, the encounter tracker,
  any future characteristic UI).
- The **internal data model keeps the acronym keys** (`stats["SIZ"]`, the
  `characteristics` dict, `data/rules.json`) — this is a display convention,
  not a data migration.
- **Plain-text / Markdown exports** (`format_statblock`,
  `format_statblock_markdown`) currently keep the acronyms for compactness and
  parity with printed character sheets. If a future change spells them out
  there too, update this spec and do it via `CHAR_FULL` as well.

## Related

- Click-to-roll convention: see `docs/click-to-roll-spec.md` — characteristics
  are rolled **pass/fail only** (no critical/fumble), per Core Ch.2.
