# Pendragon NPC Name Generator

A small Linux GUI tool for quickly generating names and NPC traits for
*King Arthur Pendragon* (5th Edition). Pick a gender and a culture, press
**Generate**, and you get a random period-appropriate name plus a short set of
Arthurian-Britain traits. Click the name to copy it to your clipboard for game
notes or Discord.

![Tkinter](https://img.shields.io/badge/GUI-Tkinter-blue) ![Python 3](https://img.shields.io/badge/Python-3-green)

## Features

- **Gender** (Male / Female) and **Culture** radio buttons — cultures are read
  live from `Names by Culture.md`.
- **Generate** a random name with a culture-appropriate surname or byname.
- **Click the name to copy** the full name to the system clipboard.
- **Random NPC traits** flavoured for Arthurian Britain: Size, Appearance
  (with hair), Eye colour, Identifying mark, and Demeanour.
- **Pronunciation hints** appear only when a name contains a tricky cluster
  (e.g. Cymric `ll`/`dd`/`w`, Irish `ch`, Roman hard `c`).

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

## Rules reference

The [`rules/`](rules/) folder holds NPC-relevant rules and lore extracted from
the Pendragon 5e Core Rulebook and Gamemaster's Handbook (Traits, Passions,
Directed Traits, Religion, Characteristics, and Distinctive Features). Future
features draw on these Markdown files rather than parsing the copyrighted PDFs,
which are kept locally and git-ignored. See [rules/README.md](rules/README.md).

## Possible future additions

Ideas for turning this into a fuller "instant NPC" tool, leaning on Pendragon
5e mechanics:

- Personality Traits (the 13 paired traits) and a defining Passion.
- Religion defaulted by culture (Wotanic / Christian / Pagan).
- Social class / rank with a quick stat block (SIZ, DEX, STR, CON, APP).
- Save a session roster and export NPCs to Markdown.
- Lock and re-roll individual fields; batch-generate a village or warband.

## License

Personal gaming tool. Name data is from the linked ScruffyGrognard article.
