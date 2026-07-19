# Pendragon NPC Name Generator

A small Linux GUI tool for quickly generating names and NPC traits for
*King Arthur Pendragon* (6th Edition). Pick a gender and a culture, press
**Generate**, and you get a random period-appropriate name plus a short set of
Arthurian-Britain traits. Click the name to copy it to your clipboard for game
notes or Discord.

![Tkinter](https://img.shields.io/badge/GUI-Tkinter-blue) ![Python 3](https://img.shields.io/badge/Python-3-green)

## Features

- **Gender**, **Class**, and **Culture** radio buttons — cultures are read live
  from `Names by Culture.md`; Class can be a specific rank or **Random**.
  Period gender rules apply: a woman may hold any class, but **Lady** is
  female-only (choosing Male + Lady yields a female Lady).
- **Generate** a random name with a culture-appropriate surname or byname.
- **Randomise** — one click picks a random gender, class, and culture (valid
  combinations only) and generates a complete NPC.
- **A read-aloud description** — a short "You see a…" paragraph assembled from
  all the details (build, looks, class attire, eyes, distinctive features,
  manner) for the moment the party meets the NPC.
- **A full rolled-up NPC**, driven by `data/rules.json`:
  - **Social class** (Commoner, Squire, Knight, Lady, Noble, Clergy) with a
    **skills block** and a **Glory** value.
  - **Religion** (defaulted by culture).
  - **Characteristics** (SIZ/DEX/STR/CON/APP) with derived stats (Hit Points,
    Move, Damage, Healing, Major Wound, Knockdown, Unconscious).
  - **Appearance** — height from SIZ plus **Distinctive Features** drawn from
    the rulebook tables (their number/tone set by APP), and eye colour.
  - **Personality Traits** — all 13 trait pairs, rolled by the rulebook Random
    Method (2D6+3 per trait, Valorous 2D6+8, ±3 for the religion's virtues).
    Famous traits (16+) are highlighted.
  - **Passions** — Honor, Homage, Love (Family), a religion-specific Devotion,
    and one motivating Passion (a hook).
  - **Manner** — a compound roleplay hint derived from the traits: the outward
    demeanour trait plus the underlying moral one (e.g. "guarded and slow to
    trust, but merciful at heart").
- **Click the name** to copy just the name to the clipboard.
- **Copy Statblock** to copy the entire NPC as text for your GM notes/Discord.
- **Session roster with GM notes** — keep a list of NPCs; add free-text **GM
  notes** to each (plot points, interactions) that persist with the roster.
  **Save/Load** the roster as JSON (full fidelity incl. notes), **Copy** it as
  Markdown for reading, and click a roster entry to reload/edit it. You're
  prompted before losing unsaved notes.
- **Pronunciation hints** appear only when a name contains a tricky cluster
  (e.g. Cymric `ll`/`dd`/`w`, Irish `ch`, Roman hard `c`).

If the `rules/` files are missing, the app degrades gracefully to name-only
mode.

## Requirements

- Python 3 with Tkinter (`tkinter` ships with most Python installs; on some
  distros install `python3-tk`).
- A running graphical (X11/Wayland) session.
- The `Names by Culture.md` data file (included).

## Usage

Run from the project folder so it can find the data file:

```bash
./pendragon_names.py
# or
python3 pendragon_names.py
```

1. Select a **Gender** and a **Culture**.
2. Press **Generate**.
3. **Click the blue name** to copy it to the clipboard — the status line
   confirms the copy.

## Cultures & naming rules

Cultures are parsed from `Names by Culture.md`. The generator follows the
source book's special cases for each:

| Culture     | Naming behaviour |
|-------------|------------------|
| Aquitanian  | Draws on Frankish names plus its own additions; random byname |
| Cymri       | Patronymic surname: `ap` (son of) / `ferch` (daughter of) + a father's name |
| Frankish    | Personal name + optional byname (e.g. "the Fair") |
| Irish       | Personal name + a real clan name (e.g. "Mc Alister") |
| Pict        | Patronymic: `mab` / `ferch`; women fall back to Cymri/Irish names (none are recorded) |
| Roman       | *praenomen + nomen (+ honorific)*; women are feminised properly (Arcavius → Arcavia, Julius → Julia) |
| Saxon       | Personal name + optional byname |

## Data file

The tool reads `Names by Culture.md` on startup. It searches next to the script
first, then the current working directory. To change what the app produces,
edit that file — adding a new `**Culture**` heading with `*Male Names:*` /
`*Female Names:*` lines makes a new culture appear automatically.

Source data: [Names by Culture (Pendragon 5th Edition)](https://scruffygrognard.wordpress.com/2015/05/18/names-by-culture-pendragon-5th-edition/)
by ScruffyGrognard.

## Rules data

The generator's mechanical data lives in a single structured file,
[`data/rules.json`](data/rules.json) — Traits, Passions, Directed Traits,
Religion, Characteristics, Distinctive Features, and naming data. This is the
**source of truth**: edit it to change what the app produces, and add keys to
it as you extract more material. A schema check runs at startup, so a malformed
file fails loudly rather than producing broken NPCs.

The [`rules/`](rules/) folder holds the same material as human-readable
Markdown documentation (no longer parsed by the app). See
[rules/README.md](rules/README.md).

## Possible future additions

Ideas for taking the "instant NPC" tool further:

- Social class / rank weighting (commoner vs. knight stat blocks).
- Save a session roster and export NPCs to Markdown.
- Lock and re-roll individual fields; batch-generate a village or warband.
- A full skills list and combat weapon skill for knightly NPCs.

## License

Personal gaming tool. Name data is from the linked ScruffyGrognard article.
