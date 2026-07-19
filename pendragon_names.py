#!/usr/bin/env python3
"""
Pendragon NPC Name Generator
============================

A small Tkinter GUI for quickly generating names and full NPC details for
non-player characters in *King Arthur Pendragon* (5th Edition).

Pick a gender and a culture, press **Generate**, and you get a random name plus
a rolled-up NPC: religion, Characteristics, Distinctive Features (appearance),
Personality Traits, and Passions. Click the name to copy just the name; press
**Copy Statblock** to copy the whole block for your GM notes.

Name lists are read from "Names by Culture.md"; the mechanical detail is driven
by the Markdown files in "rules/" (see rules.py). Editing those files changes
what the app produces.
"""

import os
import random
import re
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import rules as rules_module

# ---------------------------------------------------------------------------
# Locate and parse the source data file
# ---------------------------------------------------------------------------

DATA_FILE = "Names by Culture.md"


def find_data_file():
    """Return the path to the names file, searching next to the script first."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, DATA_FILE),
        os.path.join(os.getcwd(), DATA_FILE),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _split_names(text):
    """Turn a comma-separated blob of names into a clean list."""
    names = []
    for chunk in text.split(","):
        name = chunk.strip().strip(".").strip()
        name = name.replace("*", "").strip()
        if name and re.match(r"^[A-Za-z][A-Za-z'\- ]*$", name):
            names.append(name)
    return names


def parse_names_file(path):
    """
    Parse the markdown file into a dict:
        cultures[name] = {"Male": [...], "Female": [...], "clans": [...]}
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    cultures = {}
    current = None

    heading_re = re.compile(r"^\*\*([A-Za-z]+)\*\*")
    male_re = re.compile(r"^\*Male Names:\*\s*(.*)", re.IGNORECASE)
    female_re = re.compile(r"^\*Female Names:\*\s*(.*)", re.IGNORECASE)
    clan_re = re.compile(r"^[•\-]\s*[^:]+:\s*(.*)")

    in_front_matter = False

    for raw in lines:
        line = raw.rstrip("\n").strip()

        if line == "---":
            in_front_matter = not in_front_matter
            continue
        if in_front_matter or not line:
            continue

        m = heading_re.match(line)
        if m:
            current = m.group(1)
            cultures.setdefault(
                current, {"Male": [], "Female": [], "clans": [], "raw_female": ""}
            )
            continue

        if current is None:
            continue

        m = male_re.match(line)
        if m:
            body = m.group(1)
            if "following:" in body:
                body = body.split("following:", 1)[1]
            cultures[current]["Male"] = _split_names(body)
            continue

        m = female_re.match(line)
        if m:
            body = m.group(1)
            cultures[current]["raw_female"] = body
            if "following:" in body:
                body = body.split("following:", 1)[1]
            cultures[current]["Female"] = _split_names(body)
            continue

        m = clan_re.match(line)
        if m:
            cultures[current]["clans"].extend(_split_names(m.group(1)))

    return cultures


# ---------------------------------------------------------------------------
# Culture-specific naming rules
# ---------------------------------------------------------------------------

ROMAN_NOMEN = ["Aurelius", "Flavius", "Valerius", "Claudius", "Fabius", "Julius", "Junius"]


def _feminise_roman(name):
    """Turn a Roman male name into its feminine 'ia' form (Arcavius -> Arcavia)."""
    return re.sub(r"(ius|us|is|os|a)$", "", name) + "ia"


ROMAN_HONORIFICS = [
    "Magnus", "Maximus", "Rufus", "Eboricus", "Augustus",
    "Cicero", "Scaevola", "Numidicus",
]

BYNAMES = [
    "the Fair", "the Just", "the Tall", "the Old", "the Lame",
    "the Reckless", "the Learned", "the Honey-Tongued", "the Fat",
    "Swarthy-Cheeked", "Blue-Toothed", "the Far-Wanderer",
    "Battle-Blessed", "Head-Splitter", "of the Long Hunt",
    "of the Dales",
]

PRONUNCIATION = {
    "Cymri": [
        ("ll", "ll = the 'Welsh' aspirated L: tongue to roof of mouth, blow air out the sides"),
        ("dd", "dd = 'th' as in 'the'"),
        ("ff", "ff = 'f'"),
        ("w", "w = 'oo'"),
        ("c", "c = hard 'k'"),
        ("f", "f = 'v' (single f)"),
    ],
    "Irish": [
        ("ch", "ch = Scottish 'loch'"),
        ("dh", "d = 'j' as in 'joy'"),
        ("bh", "bh = 'v'"),
        ("s", "s before e/i = 'sh' as in 'short'"),
        ("t", "t = 'ch' as in 'church'"),
        ("c", "c = hard 'k' as in 'cow'"),
    ],
    "Roman": [
        ("c", "All C's are hard, like 'K'"),
    ],
    "Pict": [
        ("ch", "ch = Scottish 'loch'"),
    ],
}

NAMING_NOTE = {
    "Cymri": "Patronymic: 'ap' = son of, 'ferch' = daughter of.",
    "Pict": "Patronymic: 'mab' = son of, 'ferch' = daughter of.",
    "Irish": "Clan loyalty: 'Mc' = son of, 'O' = descendant of.",
    "Roman": "Roman form: praenomen + nomen (family) + optional honorific.",
}

# A plain-language roleplay hint; complements the mechanical Traits/Passions.
MANNER = [
    "cheerful and talkative", "wary of strangers", "proud and easily slighted",
    "pious and softly spoken", "boastful after a cup of ale",
    "shrewd and calculating", "quick to laugh", "sullen and taciturn",
    "courteous and formal", "restless and impatient",
    "generous to a fault", "quietly watchful",
]


# ---------------------------------------------------------------------------
# Name + character generation
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self, cultures, rules=None):
        self.cultures = cultures
        self.rules = rules

    def culture_names(self):
        return sorted(self.cultures.keys())

    def _name_pool(self, culture, gender):
        data = self.cultures[culture]
        pool = list(data.get(gender, []))

        if culture == "Roman" and gender == "Female":
            fem = [_feminise_roman(n) for n in data["Male"]
                   if not n.lower().endswith("rix")]
            pool = fem or pool

        if culture == "Pict" and gender == "Female" and not pool:
            for other in ("Cymri", "Irish"):
                if other in self.cultures:
                    pool.extend(self.cultures[other]["Female"])

        return pool

    def _surname(self, culture, gender):
        data = self.cultures[culture]

        if culture in ("Cymri", "Pict"):
            particle = ("ap" if culture == "Cymri" else "mab") if gender == "Male" else "ferch"
            fathers = data["Male"] or self.cultures.get("Cymri", {}).get("Male", [])
            if fathers:
                return f"{particle} {random.choice(fathers)}"
            return ""

        if culture == "Irish":
            if data["clans"]:
                return random.choice(data["clans"])
            return ""

        if culture == "Roman":
            nomen = random.choice(ROMAN_NOMEN)
            if gender == "Female":  # Julius -> Julia, etc.
                nomen = _feminise_roman(nomen)
            parts = [nomen]
            if random.random() < 0.5:
                parts.append(random.choice(ROMAN_HONORIFICS))
            return " ".join(parts)

        if random.random() < 0.7:
            return random.choice(BYNAMES)
        return ""

    def _pronunciation(self, culture, name):
        hints, seen = [], set()
        for cluster, note in PRONUNCIATION.get(culture, []):
            if cluster in name.lower() and note not in seen:
                hints.append(note)
                seen.add(note)
        return hints

    def generate(self, culture, gender):
        pool = self._name_pool(culture, gender)
        if not pool:
            raise ValueError(f"No {gender} names available for {culture}.")

        given = random.choice(pool)
        surname = self._surname(culture, gender)
        full = f"{given} {surname}".strip()

        result = {
            "full": full,
            "given": given,
            "surname": surname,
            "culture": culture,
            "gender": gender,
            "manner": random.choice(MANNER),
            "naming_note": NAMING_NOTE.get(culture, ""),
            "pronunciation": self._pronunciation(culture, full),
        }

        if self.rules is not None:
            religion = self.rules.religion_for(culture)
            stats, derived = self.rules.roll_characteristics(culture)
            result.update({
                "religion": religion,
                "stats": stats,
                "derived": derived,
                "height": self.rules.height_for(stats["SIZ"]),
                "appearance": self.rules.roll_appearance(stats["APP"]),
                "traits": self.rules.roll_traits(religion),
                "passions": self.rules.roll_passions(religion),
            })

        return result


# ---------------------------------------------------------------------------
# Statblock formatting (shared by the display and the clipboard)
# ---------------------------------------------------------------------------

def _traits_str(traits):
    return ", ".join(f"{d} {dv}/{s} {sv}" for d, dv, s, sv in traits)


def _passions_str(passions):
    return ", ".join(f"{n} {v}" for n, v in passions)


def format_statblock(r):
    """Render a result dict as a plain-text statblock for the clipboard."""
    lines = [r["full"]]

    sub = f"{r['gender']} · {r['culture']}"
    if r.get("religion"):
        sub += f" · {r['religion']}"
    lines.append(sub)

    if r.get("appearance"):
        a = r["appearance"]
        height = f", ~{r['height']} tall" if r.get("height") else ""
        lines.append(f"Appearance: {a['descriptor']}{height}; {a['eyes']} eyes")
        if a["features"]:
            lines.append("Distinctive Features: " + "; ".join(a["features"]))

    if r.get("manner"):
        lines.append(f"Manner: {r['manner']}")
    if r.get("traits"):
        lines.append("Personality Traits: " + _traits_str(r["traits"]))
    if r.get("passions"):
        lines.append("Passions: " + _passions_str(r["passions"]))

    if r.get("stats"):
        st = r["stats"]
        lines.append("  ".join(f"{k} {st[k]}" for k in ("SIZ", "DEX", "STR", "CON", "APP")))
        d = r["derived"]
        lines.append(
            f"HP {d['Hit Points']} · Move {d['Move']} · Damage {d['Damage']} · "
            f"Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
            f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}"
        )

    if r.get("naming_note"):
        lines.append(f"Naming: {r['naming_note']}")
    if r.get("pronunciation"):
        lines.append("Pronunciation: " + "; ".join(r["pronunciation"]))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, generator):
        super().__init__()
        self.generator = generator
        self._current = None  # last generated result dict

        self.title("Pendragon NPC Generator")
        self.geometry("660x760")
        self.minsize(600, 640)

        self.gender_var = tk.StringVar(value="Male")
        self.culture_var = tk.StringVar(value=self.generator.culture_names()[0])

        self._build_ui()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        ttk.Label(
            self, text="Pendragon NPC Generator",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", **pad)

        options = ttk.Frame(self)
        options.pack(fill="x", **pad)

        gender_box = ttk.LabelFrame(options, text="Gender")
        gender_box.pack(side="left", fill="y", padx=(0, 10))
        for g in ("Male", "Female"):
            ttk.Radiobutton(
                gender_box, text=g, value=g, variable=self.gender_var
            ).pack(anchor="w", padx=8, pady=2)

        culture_box = ttk.LabelFrame(options, text="Culture")
        culture_box.pack(side="left", fill="both", expand=True)
        grid = ttk.Frame(culture_box)
        grid.pack(fill="both", expand=True, padx=4, pady=4)
        cols = 2
        for i, c in enumerate(self.generator.culture_names()):
            ttk.Radiobutton(
                grid, text=c, value=c, variable=self.culture_var
            ).grid(row=i // cols, column=i % cols, sticky="w", padx=6, pady=2)

        buttons = ttk.Frame(self)
        buttons.pack(anchor="w", padx=10, pady=(2, 8))
        ttk.Button(buttons, text="Generate", command=self.on_generate).pack(side="left")
        self.copy_btn = ttk.Button(
            buttons, text="Copy Statblock", command=self.on_copy_statblock,
            state="disabled",
        )
        self.copy_btn.pack(side="left", padx=(8, 0))

        out_frame = ttk.LabelFrame(self, text="Result  (click the name to copy just the name)")
        out_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.name_font = tkfont.Font(family="TkDefaultFont", size=18, weight="bold")
        self.name_label = tk.Label(
            out_frame, text="—", font=self.name_font,
            fg="#1a5fb4", cursor="hand2", anchor="w", justify="left",
        )
        self.name_label.pack(fill="x", padx=10, pady=(10, 0))
        self.name_label.bind("<Button-1>", self.on_name_click)

        self.subtitle = ttk.Label(out_frame, text="", foreground="#555")
        self.subtitle.pack(fill="x", padx=10, pady=(0, 6))

        self.details = tk.Text(
            out_frame, height=18, wrap="word", relief="flat",
            background=self.cget("background"), font=("TkDefaultFont", 11),
        )
        self.details.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.details.tag_configure("label", font=("TkDefaultFont", 11, "bold"))
        self.details.configure(state="disabled")

        self.status = ttk.Label(self, text="Ready.", foreground="#2a7d2a")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

    # -- actions -----------------------------------------------------------

    def on_generate(self):
        culture = self.culture_var.get()
        gender = self.gender_var.get()
        try:
            result = self.generator.generate(culture, gender)
        except ValueError as exc:
            messagebox.showwarning("No names", str(exc))
            return

        self._current = result
        self.name_label.config(text=result["full"])
        sub = f"{result['gender']} · {result['culture']}"
        if result.get("religion"):
            sub += f" · {result['religion']}"
        self.subtitle.config(text=sub)

        self._render_details(result)
        self.copy_btn.config(state="normal")
        self.status.config(
            text="Generated. Click the name to copy it, or Copy Statblock for the lot.",
            foreground="#2a7d2a",
        )

    def _render_details(self, r):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")

        def row(label, value):
            self.details.insert("end", f"{label}: ", ("label",))
            self.details.insert("end", f"{value}\n")

        if r.get("appearance"):
            a = r["appearance"]
            height = f", ~{r['height']} tall" if r.get("height") else ""
            row("Appearance", f"{a['descriptor']}{height}; {a['eyes']} eyes")
            if a["features"]:
                row("Distinctive Features", "; ".join(a["features"]))

        if r.get("manner"):
            row("Manner", r["manner"])

        if r.get("traits"):
            self.details.insert("end", "\n")
            row("Personality Traits", _traits_str(r["traits"]))
        if r.get("passions"):
            row("Passions", _passions_str(r["passions"]))

        if r.get("stats"):
            self.details.insert("end", "\n")
            st = r["stats"]
            row("Characteristics",
                "  ".join(f"{k} {st[k]}" for k in ("SIZ", "DEX", "STR", "CON", "APP")))
            d = r["derived"]
            row("Derived",
                f"HP {d['Hit Points']} · Move {d['Move']} · Damage {d['Damage']} · "
                f"Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
                f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}")

        if r.get("naming_note"):
            self.details.insert("end", "\n")
            row("Naming", r["naming_note"])

        if r.get("pronunciation"):
            self.details.insert("end", "Pronunciation:\n", ("label",))
            for hint in r["pronunciation"]:
                self.details.insert("end", f"  • {hint}\n")

        self.details.configure(state="disabled")

    def _to_clipboard(self, text, message):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # keep clipboard populated after window events
        self.status.config(text=message, foreground="#1a5fb4")

    def on_name_click(self, _event):
        if self._current:
            self._to_clipboard(self._current["full"],
                               f"Copied '{self._current['full']}' to clipboard.")

    def on_copy_statblock(self):
        if self._current:
            self._to_clipboard(format_statblock(self._current),
                               "Copied full statblock to clipboard.")


# ---------------------------------------------------------------------------

def main():
    here = os.path.dirname(os.path.abspath(__file__))

    path = find_data_file()
    if path is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing data file",
            f"Could not find '{DATA_FILE}'.\n"
            "Place it next to this script and try again.",
        )
        print(f"Error: could not find '{DATA_FILE}'.", file=sys.stderr)
        return 1

    cultures = parse_names_file(path)
    if not cultures:
        print("Error: no cultures parsed from the data file.", file=sys.stderr)
        return 1

    rules = rules_module.load_rules(os.path.join(here, "rules"))
    if rules is None:
        print("Warning: rules/ files not found or unparsable; "
              "running in name-only mode.", file=sys.stderr)

    generator = Generator(cultures, rules)
    App(generator).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
