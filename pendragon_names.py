#!/usr/bin/env python3
"""
Pendragon NPC Name Generator
============================

A small Tkinter GUI for quickly generating names and traits for
non-player characters in *King Arthur Pendragon* (5th Edition).

Pick a gender and a culture, press **Generate**, and a random name plus a
short set of Arthurian-Britain NPC traits appears. Click a generated name
to copy it to the system clipboard (handy for game notes or Discord).

Name lists are read from the accompanying "Names by Culture.md" file, so
editing that file changes what the app produces.
"""

import os
import random
import re
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

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
        # Drop stray markdown emphasis or empty fragments.
        name = name.replace("*", "").strip()
        if name and re.match(r"^[A-Za-z][A-Za-z'\- ]*$", name):
            names.append(name)
    return names


def parse_names_file(path):
    """
    Parse the markdown file into a dict:
        cultures[name] = {"Male": [...], "Female": [...], "clans": [...]}

    The markdown is loosely structured, so we work line by line, tracking the
    current culture heading (**Bold**) and picking up the *Male Names:* /
    *Female Names:* / clan bullet lines beneath it.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    cultures = {}
    current = None

    heading_re = re.compile(r"^\*\*([A-Za-z]+)\*\*")
    male_re = re.compile(r"^\*Male Names:\*\s*(.*)", re.IGNORECASE)
    female_re = re.compile(r"^\*Female Names:\*\s*(.*)", re.IGNORECASE)
    clan_re = re.compile(r"^[•\-]\s*[^:]+:\s*(.*)")

    # Skip the YAML front matter at the top of the file.
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
            # Aquitanian adds names on top of Frankish ones.
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
# Culture-specific rules the flat name lists can't express on their own
# ---------------------------------------------------------------------------

# Roman nomen (family) names and honorifics, per the source notes.
ROMAN_NOMEN = ["Aurelius", "Flavius", "Valerius", "Claudius", "Fabius", "Julius", "Junius"]


def _feminise_roman(name):
    """Turn a Roman male name into its feminine 'ia' form (Arcavius -> Arcavia)."""
    return re.sub(r"(ius|us|is|os|a)$", "", name) + "ia"


ROMAN_HONORIFICS = [
    "Magnus", "Maximus", "Rufus", "Eboricus", "Augustus",
    "Cicero", "Scaevola", "Numidicus",
]

# Bynames used by cultures that lack inherited surnames (Saxon / Frankish /
# Aquitanian). Drawn from the "Surnames" notes in the source file.
BYNAMES = [
    "the Fair", "the Just", "the Tall", "the Old", "the Lame",
    "the Reckless", "the Learned", "the Honey-Tongued", "the Fat",
    "Swarthy-Cheeked", "Blue-Toothed", "the Far-Wanderer",
    "Battle-Blessed", "Head-Splitter", "of the Long Hunt",
    "of the Dales",
]

# Compact pronunciation hints keyed by the letter/cluster that triggers them.
# Shown only when a generated name actually contains the cluster.
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

# General notes about how a culture builds its full name, shown under the name.
NAMING_NOTE = {
    "Cymri": "Patronymic: 'ap' = son of, 'ferch' = daughter of.",
    "Pict": "Patronymic: 'mab' = son of, 'ferch' = daughter of.",
    "Irish": "Clan loyalty: 'Mc' = son of, 'O' = descendant of.",
    "Roman": "Roman form: praenomen + nomen (family) + optional honorific.",
}

# ---------------------------------------------------------------------------
# NPC trait tables (Arthurian Britain flavour)
# ---------------------------------------------------------------------------

SIZE = [
    "short and slight", "short but sturdy", "of middling height",
    "average build", "tall and lean", "tall and broad-shouldered",
    "towering and powerful", "stocky and thickset", "wiry and quick",
    "gaunt and long-limbed",
]

APPEARANCE = [
    "weather-beaten and sun-browned", "pale and fine-featured",
    "ruddy and cheerful", "hard-faced and grim", "handsome and well-kept",
    "plain but honest-looking", "sallow and hollow-cheeked",
    "freckled and open-faced", "scarred but dignified",
    "youthful and unlined", "aged and deeply wrinkled",
    "broad-faced and heavy-browed",
]

HAIR = [
    "raven-black hair", "dark brown hair", "chestnut hair", "auburn hair",
    "fiery red hair", "sandy blond hair", "flaxen hair",
    "iron-grey hair", "silver-white hair", "a shaven head",
    "close-cropped hair", "long braided hair",
]

EYES = [
    "pale blue", "grey", "steel-grey", "green", "hazel",
    "dark brown", "amber", "one blue and one brown (heterochromia)",
    "deep-set black", "watery pale",
]

MARKS = [
    "a jagged scar across one cheek",
    "a missing finger on the left hand",
    "an old battle wound that makes them limp",
    "a birthmark shaped like a crescent on the neck",
    "startlingly white teeth",
    "a broken nose set slightly crooked",
    "a booming, carrying voice",
    "a soft, careful way of speaking",
    "elaborate Pictish-style tattoos",
    "a heavy iron torc at the throat",
    "a nervous habit of tugging their beard",
    "a Christian cross worn openly",
    "a pagan charm on a leather cord",
    "unusually large, calloused hands",
    "a milky, blind left eye",
    "a proud, upright bearing",
    "a perpetual squint",
    "richly dyed clothing beyond their apparent station",
]

DEMEANOUR = [
    "cheerful and talkative", "wary of strangers", "proud and easily slighted",
    "pious and softly spoken", "boastful after a cup of ale",
    "shrewd and calculating", "quick to laugh", "sullen and taciturn",
    "courteous and formal", "restless and impatient",
    "generous to a fault", "quietly watchful",
]


# ---------------------------------------------------------------------------
# Name + trait generation
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self, cultures):
        self.cultures = cultures

    def culture_names(self):
        return sorted(self.cultures.keys())

    def _name_pool(self, culture, gender):
        """Return the given-name pool, handling the source's special cases."""
        data = self.cultures[culture]
        pool = list(data.get(gender, []))

        # Roman women: feminise male names (non -rix) by ending them in 'ia'.
        if culture == "Roman" and gender == "Female":
            fem = [_feminise_roman(n) for n in data["Male"]
                   if not n.lower().endswith("rix")]
            pool = fem or pool

        # Pict women: the source has no recorded names -> use Cymri + Irish.
        if culture == "Pict" and gender == "Female" and not pool:
            for other in ("Cymri", "Irish"):
                if other in self.cultures:
                    pool.extend(self.cultures[other]["Female"])

        return pool

    def _surname(self, culture, gender):
        """Build a culture-appropriate surname / byname, or '' if none."""
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
            if gender == "Female":  # Julius -> Julia, Claudius -> Claudia, etc.
                nomen = _feminise_roman(nomen)
            parts = [nomen]
            if random.random() < 0.5:
                parts.append(random.choice(ROMAN_HONORIFICS))
            return " ".join(parts)

        # Saxon / Frankish / Aquitanian and anything else: bynames.
        if random.random() < 0.7:
            return random.choice(BYNAMES)
        return ""

    def _pronunciation(self, culture, name):
        hints = []
        rules = PRONUNCIATION.get(culture, [])
        lname = name.lower()
        seen = set()
        for cluster, note in rules:
            if cluster in lname and note not in seen:
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

        traits = {
            "Size": random.choice(SIZE),
            "Appearance": f"{random.choice(APPEARANCE)}, with {random.choice(HAIR)}",
            "Eye colour": random.choice(EYES),
            "Identifying mark": random.choice(MARKS),
            "Demeanour": random.choice(DEMEANOUR),
        }

        return {
            "full": full,
            "given": given,
            "surname": surname,
            "culture": culture,
            "gender": gender,
            "traits": traits,
            "naming_note": NAMING_NOTE.get(culture, ""),
            "pronunciation": self._pronunciation(culture, full),
        }


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, generator):
        super().__init__()
        self.generator = generator

        self.title("Pendragon NPC Name Generator")
        self.geometry("640x620")
        self.minsize(560, 520)

        self.gender_var = tk.StringVar(value="Male")
        self.culture_var = tk.StringVar(value=self.generator.culture_names()[0])

        self._build_ui()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        header = ttk.Label(
            self, text="Pendragon NPC Generator",
            font=("TkDefaultFont", 16, "bold"),
        )
        header.pack(anchor="w", **pad)

        options = ttk.Frame(self)
        options.pack(fill="x", **pad)

        # Gender radio buttons
        gender_box = ttk.LabelFrame(options, text="Gender")
        gender_box.pack(side="left", fill="y", padx=(0, 10))
        for g in ("Male", "Female"):
            ttk.Radiobutton(
                gender_box, text=g, value=g, variable=self.gender_var
            ).pack(anchor="w", padx=8, pady=2)

        # Culture radio buttons
        culture_box = ttk.LabelFrame(options, text="Culture")
        culture_box.pack(side="left", fill="both", expand=True)
        grid = ttk.Frame(culture_box)
        grid.pack(fill="both", expand=True, padx=4, pady=4)
        cultures = self.generator.culture_names()
        cols = 2
        for i, c in enumerate(cultures):
            ttk.Radiobutton(
                grid, text=c, value=c, variable=self.culture_var
            ).grid(row=i // cols, column=i % cols, sticky="w", padx=6, pady=2)

        # Generate button
        ttk.Button(
            self, text="Generate", command=self.on_generate
        ).pack(anchor="w", padx=10, pady=(2, 8))

        # Output area
        out_frame = ttk.LabelFrame(self, text="Result  (click a name to copy)")
        out_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.name_font = tkfont.Font(family="TkDefaultFont", size=18, weight="bold")

        # Clickable name label
        self.name_label = tk.Label(
            out_frame, text="—", font=self.name_font,
            fg="#1a5fb4", cursor="hand2", anchor="w", justify="left",
        )
        self.name_label.pack(fill="x", padx=10, pady=(10, 0))
        self.name_label.bind("<Button-1>", self.on_name_click)

        self.subtitle = ttk.Label(out_frame, text="", foreground="#555")
        self.subtitle.pack(fill="x", padx=10, pady=(0, 6))

        # Traits / details text
        self.details = tk.Text(
            out_frame, height=12, wrap="word", relief="flat",
            background=self.cget("background"), font=("TkDefaultFont", 11),
        )
        self.details.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.details.configure(state="disabled")

        # Status line
        self.status = ttk.Label(self, text="Ready.", foreground="#2a7d2a")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

        self._current_name = ""

    # -- actions -----------------------------------------------------------

    def on_generate(self):
        culture = self.culture_var.get()
        gender = self.gender_var.get()
        try:
            result = self.generator.generate(culture, gender)
        except ValueError as exc:
            messagebox.showwarning("No names", str(exc))
            return

        self._current_name = result["full"]
        self.name_label.config(text=result["full"])
        self.subtitle.config(text=f"{result['gender']} · {result['culture']}")

        self._render_details(result)
        self.status.config(text="Generated. Click the name to copy it.",
                           foreground="#2a7d2a")

    def _render_details(self, result):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")

        for key, value in result["traits"].items():
            self.details.insert("end", f"{key}: ", ("label",))
            self.details.insert("end", f"{value}\n")

        if result["naming_note"]:
            self.details.insert("end", "\n")
            self.details.insert("end", "Naming: ", ("label",))
            self.details.insert("end", result["naming_note"] + "\n")

        if result["pronunciation"]:
            self.details.insert("end", "\n")
            self.details.insert("end", "Pronunciation:\n", ("label",))
            for hint in result["pronunciation"]:
                self.details.insert("end", f"  • {hint}\n")

        self.details.tag_configure("label", font=("TkDefaultFont", 11, "bold"))
        self.details.configure(state="disabled")

    def on_name_click(self, _event):
        if not self._current_name:
            return
        self.clipboard_clear()
        self.clipboard_append(self._current_name)
        self.update()  # keep clipboard populated after window events
        self.status.config(text=f"Copied '{self._current_name}' to clipboard.",
                           foreground="#1a5fb4")


# ---------------------------------------------------------------------------

def main():
    path = find_data_file()
    if path is None:
        # No GUI yet, so report on the console and via a minimal dialog.
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

    generator = Generator(cultures)
    app = App(generator)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
