# Pendragon GM Tools

A Tkinter, stdlib-only desktop app for running *King Arthur Pendragon* (6th
Edition, Chaosium). What started as a name generator has grown into a small
GM toolkit: four tabs covering NPC generation, a live combat tracker, a
stat-block/encounter editor, and a queryable rules corpus behind the scenes.

![Tkinter](https://img.shields.io/badge/GUI-Tkinter-blue) ![Python 3](https://img.shields.io/badge/Python-3-green) ![stdlib only](https://img.shields.io/badge/dependencies-stdlib--only-lightgrey)

## The four tabs

1. **NPC Generator** — instant, rules-accurate NPCs: name, religion,
   characteristics, appearance, personality traits, passions, and (for Cymric
   knights) a full Core Ch.3 character sheet. Session roster with GM notes.
2. **Encounter** — a live combat tracker: launch a themed encounter or a
   custom one, click any characteristic/skill/damage value to roll it
   (success/critical/fumble handled automatically), track HP and status per
   combatant, apply a **situational modifier** (mounted, shield penalty,
   etc.) that sticks to a combatant and applies to every roll, and keep a
   combat log you can save or copy.
3. **Adversary & Creature Creator** — build and edit the reusable adversary
   stat blocks (generic types and named NPCs) that encounters are made from:
   weapons/armour, characteristics, skills, traits — or promote a generated
   NPC straight into a named adversary.
4. **Encounter Creator** — design and save reusable encounter *definitions*
   (which adversaries, how many, how they scale with party size), then send
   one straight to the live tracker.

Only the NPC Generator needs `Names by Culture.md`; the other three tabs
appear once `data/combat.json` (or its tracked baseline,
`data/examplecombat.json`) is present.

## NPC Generator — features

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
    **skills block** and a **Glory** value, and period-accurate attire (court
    dress plus battle gear for knights).
  - **Religion** (defaulted by culture, or chosen directly — drives trait
    virtue modifiers).
  - **Characteristics** (SIZ/DEX/STR/CON/APP) with derived stats (Hit Points,
    Move, Damage, Healing, Major Wound, Knockdown, Unconscious) — every value
    is a **click-to-roll** link.
  - **Appearance** — height from SIZ plus **Distinctive Features** drawn from
    the rulebook tables (their number/tone set by APP; negative features
    optional via a toggle), and eye colour.
  - **Personality Traits** — all 13 trait pairs, rolled by the rulebook Random
    Method (2D6+3 per trait, Valorous 2D6+8, ±3 for the religion's virtues).
    Famous (16+) and Exalted (20+) traits are highlighted.
  - **Passions** — Honor, Homage, Love (Family), a religion-specific Devotion,
    and one motivating Passion (a hook).
  - **Manner** — a compound roleplay hint derived from the traits: the outward
    demeanour trait plus the underlying moral one (e.g. "guarded and slow to
    trust, but merciful at heart").
  - **Full Cymric knight creation** (Core Ch.3) for Knight-class Cymri: Table
    3.5 beginning skills, inherited Glory via Quick Family History (+ family
    lore), the complete starting passion set, age/homeland, an **Ideals**
    assessment (Chivalrous/Religious/Romantic), and a rerollable **squire**
    NPC.
- **Click any characteristic, skill, trait, passion, or damage value** to roll
  it — logged to GM Notes and flashed in the status bar.
- **Reroll a single field** (name, class, religion, characteristics,
  appearance, traits, passions, squire, …) without regenerating the whole NPC.
- **Export sheet PDF** — fill the official Cymric character sheet for a full
  knight (needs the optional `pypdf` package).
- **Copy Statblock**, **Copy Markdown**, and **Copy Image Prompt** (a
  period-accurate prompt for an external image generator) to the clipboard.
- **Create Adversary** — send the current NPC straight into the Adversary
  Creator as a draft.
- **Session roster with GM notes** — keep a list of NPCs; add free-text **GM
  notes** to each (plot points, interactions, roll history) that persist with
  the roster. **Save/Load** the roster as JSON (full fidelity incl. notes),
  **Copy** it as Markdown for reading, and click a roster entry to
  reload/edit it. You're prompted before losing unsaved notes.
- **Pronunciation hints** appear only when a name contains a tricky cluster
  (e.g. Cymric `ll`/`dd`/`w`, Irish `ch`, Roman hard `c`).

If `data/rules.json` is missing, the app degrades gracefully to name-only mode.

## Encounter tab — features

Runs a live combat, driven by `data/combat.json`:

- **Generate an encounter** by theme (bandit ambush, conroi of knights, Saxon
  raiders, the Battle-Card conrois — Knights of Gorre/Lothian, Pictish
  Pikemen, Cambrian Archers, etc., or any custom definition from the
  Encounter Creator) scaled to the number of players; a leader is
  auto-promoted.
- **Click any underlined stat number to roll it** — characteristic, attack
  skill, damage, or named skill — with correct success/critical/fumble
  resolution (including the 20 (+x) critical-bonus notation for values over
  20) and a critical-bonus/rebated-damage chooser for weapon damage.
- **Situational modifiers** — a per-combatant "Mod" field (e.g. -5 mounted
  vs. mounted, +5 mounted vs. foot, -2 shield penalty; net them yourself)
  that applies automatically to every characteristic/attack-skill/named-skill
  roll for that combatant until changed back to 0. Colour-coded red/green;
  logged when set or cleared.
- **Add/remove** combatants at any time; each row has an editable label, an
  **"engaged with"** field, and **cur/max HP** with a delta box (type damage
  as negative, healing as positive) that auto-detects Major Wounds and
  Mortal Wounds.
- **Promote** any combatant to a champion/elite (Gang Leader, Elite
  Commander…): tougher HP, skills, damage, armour, and Glory — and demote
  back.
- **Ransom** and **Morale** rolls for battle-card foes; a **Surrender check**
  (Valorous) for GM foes at half HP or less.
- Knock out/revive, deactivate ("fled — not tracked"), and remove combatants.
  Downed combatants are **greyed out**.
- A **combat log** with round notes, a **GM Notes** box for the fight, and
  both are written to the saved/copied/exported log.

## Adversary & Creature Creator — features

Build and maintain the `adversaries` library that both the NPC Generator's
"Create Adversary" bridge and the Encounter Creator draw from:

- Search/filter the library by kind (generic/named) and category
  (human/beast/monster/fae); create new, duplicate, or delete entries.
- Full stat editor: characteristics (roll or type), derived stats, weapons
  and armour (picked from the enriched combat tables, with automatic skill
  and damage lookup), natural attacks for creatures, traits, and notes.
- **Auto-generate all** — roll a complete adversary (characteristics through
  skills) for a given gender/class in one click, reusing the NPC Generator's
  own rules engine.

## Encounter Creator — features

Design reusable **encounter definitions** — which adversaries, how many, and
how the roster scales with party size — rather than one-off tracker sessions:

- Build a roster of adversary entries with counts that scale by player count
  (fixed, per-player, or a formula), tag and describe the encounter, and pick
  a leader to auto-promote.
- Save alongside the built-in themes, so it appears in the Encounter tab's
  theme picker.
- **Send to tracker** — launch the definition as a live encounter immediately
  and switch to the Encounter tab.

See `docs/adversary-creator-spec.md` and `docs/encounter-creator-spec.md` for
the detailed design of these two tabs.

## Requirements

- Python 3 with Tkinter (`tkinter` ships with most Python installs; on some
  distros install `python3-tk`).
- A running graphical (X11/Wayland) session.
- The `Names by Culture.md` data file (included).
- Optional: `pypdf` (`pip install pypdf`) to export a filled Cymric character
  sheet PDF. Optional: `PyYAML` (`requirements.txt`) only if you're
  rebuilding the rules-corpus search index (`build_rules_index.py`) — not
  needed to run the app itself.

## Usage

Run from the project folder so it can find the data files (or use
`run.sh` / `run.bat`, which `cd` there for you):

```bash
./pendragon.py
# or
python3 pendragon.py
```

1. Select a **Gender** and a **Culture**.
2. Press **Generate**.
3. **Click the blue name** to copy it to the clipboard — the status line
   confirms the copy.
4. Switch tabs for the combat tracker and creators (only shown once
   `data/combat.json` / `data/examplecombat.json` exists).

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

Source data: [Names by Culture (Pendragon 5th Edition)](https://scruffygrognard.wordpress.com/2015/05/18/names-by-culture-pendragon-5th-edition/)
by ScruffyGrognard. To change what the app produces, edit
`Names by Culture.md` — adding a new `**Culture**` heading with
`*Male Names:*` / `*Female Names:*` lines makes a new culture appear
automatically.

## Data files

- [`data/rules.json`](data/rules.json) — the NPC Generator's **source of
  truth**: Traits, Passions, Directed Traits, Religion, Characteristics,
  Distinctive Features, social classes/skills/attire, and naming data. A
  schema check runs at startup, so a malformed file fails loudly rather than
  producing broken NPCs.
- [`data/examplecombat.json`](data/examplecombat.json) — the tracked baseline
  for combat rules, the adversary bestiary, and built-in encounter themes.
  `data/combat.json` is the user's git-ignored working copy (created from the
  baseline on first edit); the app reads/writes only that file, so your own
  named adversaries and custom encounters persist locally without polluting
  the repo.
- [`rules_corpus/`](rules_corpus/README.md) — prose rules extracted from the
  rulebooks as one Markdown file per topic (YAML frontmatter + citable page
  numbers), for Q&A/browsing/RAG. `data/rules_index.jsonl` is its generated
  full-text index — regenerate with `python build_rules_index.py`, never
  hand-edit it.
- [`rules/`](rules/) — the older human-readable Markdown docs the generator
  used to parse directly; kept as reference, no longer read by the app
  (superseded by `data/rules.json` and `rules_corpus/`).
- `rulebooks/` (git-ignored, local only) — the source PDFs, used to extract
  material into `rules_corpus/` and `data/*.json`. Not included in the repo
  (copyrighted).
- [`docs/`](docs/) — design specs for the click-to-roll behaviour and the
  Adversary/Encounter Creator tabs.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the running backlog of ideas and what's
already landed.

## License

Personal gaming tool. Name data is from the linked ScruffyGrognard article;
rules are paraphrased from the Chaosium rulebooks as a play aid (the PDFs
themselves are copyrighted and kept local only, never committed).
