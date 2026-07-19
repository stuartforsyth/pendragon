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
#
# Naming/flavour data (Roman nomen & honorifics, bynames, pronunciation hints,
# naming notes, manner) now lives in data/rules.json and is read via the Rules
# object. Only the feminisation logic stays in code.


def _feminise_roman(name):
    """Turn a Roman male name into its feminine 'ia' form (Arcavius -> Arcavia)."""
    return re.sub(r"(ius|us|is|os|a)$", "", name) + "ia"


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
            if not (self.rules and self.rules.roman_nomen):
                return ""  # no nomen data without rules
            nomen = random.choice(self.rules.roman_nomen)
            if gender == "Female":  # Julius -> Julia, etc.
                nomen = _feminise_roman(nomen)
            parts = [nomen]
            if self.rules.roman_honorifics and random.random() < 0.5:
                parts.append(random.choice(self.rules.roman_honorifics))
            return " ".join(parts)

        if self.rules and self.rules.bynames and random.random() < 0.7:
            return random.choice(self.rules.bynames)
        return ""

    def _pronunciation(self, culture, name):
        if not self.rules:
            return []
        hints, seen = [], set()
        for cluster, note in self.rules.pronunciation.get(culture, []):
            if cluster in name.lower() and note not in seen:
                hints.append(note)
                seen.add(note)
        return hints

    def _fill_name(self, r):
        """(Re)roll the name fields of a result dict in place."""
        culture, gender = r["culture"], r["gender"]
        pool = self._name_pool(culture, gender)
        if not pool:
            raise ValueError(f"No {gender} names available for {culture}.")
        given = random.choice(pool)
        surname = self._surname(culture, gender)
        full = f"{given} {surname}".strip()
        r.update(
            given=given, surname=surname, full=full,
            pronunciation=self._pronunciation(culture, full),
        )

    def _fill_characteristics(self, r):
        """(Re)roll characteristics and everything derived from them."""
        stats, derived = self.rules.roll_characteristics(r["culture"])
        r["stats"] = stats
        r["derived"] = derived
        r["height"] = self.rules.height_for(stats["SIZ"])
        r["appearance"] = self.rules.roll_appearance(stats["APP"])

    def _fill_class(self, r, requested=None):
        """(Re)roll the social class and its skills/Glory in place."""
        if not (self.rules and self.rules.social_classes):
            return
        if requested and requested in self.rules.social_classes:
            cls = requested
        else:  # "Random", None, or unknown -> weighted random
            cls = self.rules.roll_class()
        r["social_class"] = cls
        r["attire"] = self.rules.social_classes[cls].get("attire", "")
        self._fill_skills(r)

    def _fill_skills(self, r):
        rolled = self.rules.roll_skills(r.get("social_class"))
        if rolled:
            r["skills"] = rolled["skills"]
            r["glory"] = rolled["glory"]

    def generate(self, culture, gender, social_class=None):
        result = {"culture": culture, "gender": gender}
        self._fill_name(result)

        if self.rules is not None:
            result["naming_note"] = self.rules.naming_notes.get(culture, "")
            if self.rules.manner:
                result["manner"] = random.choice(self.rules.manner)
            self._fill_class(result, social_class)
            religion = self.rules.religion_for(culture)
            result["religion"] = religion
            self._fill_characteristics(result)
            result["traits"] = self.rules.roll_traits(religion)
            result["passions"] = self.rules.roll_passions(religion)
            result["directed"] = self.rules.roll_directed_trait()

        return result

    # Fields the GUI can reroll individually, mapped to how to reroll them.
    def reroll_fields(self):
        if self.rules is None:
            return ["Name"]
        fields = [
            "Name", "Religion", "Characteristics", "Appearance",
            "Personality Traits", "Passions", "Directed Trait", "Manner",
        ]
        if self.rules.social_classes:
            fields[1:1] = ["Class", "Skills"]  # right after Name
        return fields

    def reroll_field(self, r, field):
        """Reroll a single component of an existing result in place."""
        if field == "Name":
            self._fill_name(r)
            return
        if self.rules is None:
            return
        if field == "Class":
            self._fill_class(r)
        elif field == "Skills":
            self._fill_skills(r)
        elif field == "Manner":
            if self.rules.manner:
                r["manner"] = random.choice(self.rules.manner)
        elif field == "Religion":
            r["religion"] = self.rules.religion_for(r["culture"])
            r["traits"] = self.rules.roll_traits(r["religion"])
            r["passions"] = self.rules.roll_passions(r["religion"])
        elif field == "Characteristics":
            self._fill_characteristics(r)
        elif field == "Appearance":
            r["appearance"] = self.rules.roll_appearance(r["stats"]["APP"])
        elif field == "Personality Traits":
            r["traits"] = self.rules.roll_traits(r["religion"])
        elif field == "Passions":
            r["passions"] = self.rules.roll_passions(r["religion"])
        elif field == "Directed Trait":
            r["directed"] = self.rules.roll_directed_trait()


# ---------------------------------------------------------------------------
# Statblock formatting (shared by the display and the clipboard)
# ---------------------------------------------------------------------------

def _traits_str(traits):
    return ", ".join(f"{d} {dv}/{s} {sv}" for d, dv, s, sv in traits)


def _passions_str(passions):
    return ", ".join(f"{n} {v}" for n, v in passions)


def _skills_str(skills):
    return ", ".join(f"{k} {v}" for k, v in
                     sorted(skills.items(), key=lambda kv: (-kv[1], kv[0])))


def subtitle_str(r):
    """The '<gender> <class> · <culture> · <religion>' summary line."""
    sub = r["gender"]
    if r.get("social_class"):
        sub += f" {r['social_class']}"
    sub += f" · {r['culture']}"
    if r.get("religion"):
        sub += f" · {r['religion']}"
    return sub


def format_statblock(r):
    """Render a result dict as a plain-text statblock for the clipboard."""
    lines = [r["full"], subtitle_str(r)]

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
    if r.get("directed"):
        lines.append(f"{r['directed']['kind']}: {r['directed']['text']}")

    if r.get("stats"):
        st = r["stats"]
        lines.append("  ".join(f"{k} {st[k]}" for k in ("SIZ", "DEX", "STR", "CON", "APP")))
        d = r["derived"]
        lines.append(
            f"HP {d['Hit Points']} · Move {d['Move']} · Damage {d['Damage']} · "
            f"Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
            f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}"
        )
    if r.get("skills"):
        lines.append("Skills: " + _skills_str(r["skills"]))
    if r.get("glory") is not None:
        lines.append(f"Glory: {r['glory']}")

    if r.get("naming_note"):
        lines.append(f"Naming: {r['naming_note']}")
    if r.get("pronunciation"):
        lines.append("Pronunciation: " + "; ".join(r["pronunciation"]))

    return "\n".join(lines)


def format_statblock_markdown(r):
    """Render a result dict as a Markdown block for game notes."""
    lines = [f"## {r['full']}", f"*{subtitle_str(r)}*", ""]

    def bullet(label, value):
        lines.append(f"- **{label}:** {value}")

    if r.get("appearance"):
        a = r["appearance"]
        height = f", ~{r['height']} tall" if r.get("height") else ""
        bullet("Appearance", f"{a['descriptor']}{height}; {a['eyes']} eyes")
        if a["features"]:
            bullet("Distinctive Features", "; ".join(a["features"]))
    if r.get("manner"):
        bullet("Manner", r["manner"])
    if r.get("traits"):
        bullet("Personality Traits", _traits_str(r["traits"]))
    if r.get("passions"):
        bullet("Passions", _passions_str(r["passions"]))
    if r.get("directed"):
        bullet(r["directed"]["kind"], r["directed"]["text"])
    if r.get("stats"):
        st = r["stats"]
        bullet("Characteristics",
               "  ".join(f"{k} {st[k]}" for k in ("SIZ", "DEX", "STR", "CON", "APP")))
        d = r["derived"]
        bullet("Derived",
               f"HP {d['Hit Points']} · Move {d['Move']} · Damage {d['Damage']} · "
               f"Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
               f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}")
    if r.get("skills"):
        bullet("Skills", _skills_str(r["skills"]))
    if r.get("glory") is not None:
        bullet("Glory", r["glory"])
    if r.get("naming_note"):
        bullet("Naming", r["naming_note"])
    if r.get("pronunciation"):
        bullet("Pronunciation", "; ".join(r["pronunciation"]))

    return "\n".join(lines)


def build_image_prompt(r):
    """Build a period-accurate image-generation prompt from the NPC."""
    social = f"{r['social_class'].lower()} " if r.get("social_class") else ""
    subject = f"{r['gender'].lower()} {r['culture']} {social}person".replace("  ", " ")
    parts = [f"character portrait of a {subject}"]

    a = r.get("appearance")
    if a:
        if a.get("features"):
            parts.append(", ".join(a["features"]))
        parts.append(f"{a['eyes']} eyes")
        parts.append(f"{a['descriptor'].lower()}-looking")
    if r.get("height"):
        parts.append(f"about {r['height']} tall")

    attire = r.get("attire") or "period Dark Ages clothing"
    style = (
        f"sub-Roman Britain, 5th-6th century, Dark Ages, wearing {attire}, "
        "no plate armour, historically grounded, muted natural colours, "
        "overcast light, painterly, detailed face, head and shoulders"
    )
    negative = (
        "Negative prompt: plate armour, full helm, gothic castle, renaissance, "
        "modern clothing, anime, cartoon, text, watermark, deformed"
    )
    return ", ".join(p for p in parts if p) + ". " + style + "\n" + negative


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, generator):
        super().__init__()
        self.generator = generator
        self._current = None  # last generated result dict

        self.title("Pendragon NPC Generator")
        self.geometry("680x820")
        self.minsize(640, 700)

        self.gender_var = tk.StringVar(value="Male")
        self.culture_var = tk.StringVar(value=self.generator.culture_names()[0])
        self.class_var = tk.StringVar(value="Random")

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

        # Class selector (only if the rules data defines social classes).
        classes = self.generator.rules.class_names() if self.generator.rules else []
        if classes:
            class_box = ttk.LabelFrame(options, text="Class")
            class_box.pack(side="left", fill="y", padx=(0, 10))
            cgrid = ttk.Frame(class_box)
            cgrid.pack(padx=4, pady=4)
            for i, c in enumerate(["Random"] + classes):
                ttk.Radiobutton(
                    cgrid, text=c, value=c, variable=self.class_var
                ).grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=1)

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
        buttons.pack(anchor="w", fill="x", padx=10, pady=(2, 4))
        ttk.Button(buttons, text="Generate", command=self.on_generate).pack(side="left")

        # Copy buttons (disabled until something is generated).
        self.copy_buttons = []
        for text, cmd in (
            ("Copy Statblock", self.on_copy_statblock),
            ("Copy Markdown", self.on_copy_markdown),
            ("Copy Image Prompt", self.on_copy_image_prompt),
        ):
            b = ttk.Button(buttons, text=text, command=cmd, state="disabled")
            b.pack(side="left", padx=(8, 0))
            self.copy_buttons.append(b)

        # Reroll a single field.
        reroll = ttk.Frame(self)
        reroll.pack(anchor="w", padx=10, pady=(0, 8))
        ttk.Label(reroll, text="Reroll:").pack(side="left")
        self.reroll_var = tk.StringVar(value=self.generator.reroll_fields()[0])
        self.reroll_menu = ttk.Combobox(
            reroll, textvariable=self.reroll_var, state="disabled",
            values=self.generator.reroll_fields(), width=18,
        )
        self.reroll_menu.pack(side="left", padx=(6, 0))
        self.reroll_btn = ttk.Button(
            reroll, text="Reroll field", command=self.on_reroll, state="disabled",
        )
        self.reroll_btn.pack(side="left", padx=(6, 0))

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
        social_class = self.class_var.get()
        try:
            result = self.generator.generate(culture, gender, social_class)
        except ValueError as exc:
            messagebox.showwarning("No names", str(exc))
            return

        self._current = result
        self._refresh_display()
        for b in self.copy_buttons:
            b.config(state="normal")
        self.reroll_menu.config(state="readonly")
        self.reroll_btn.config(state="normal")
        self.status.config(
            text="Generated. Click the name to copy it, or use the Copy buttons.",
            foreground="#2a7d2a",
        )

    def _refresh_display(self):
        r = self._current
        self.name_label.config(text=r["full"])
        self.subtitle.config(text=subtitle_str(r))
        self._render_details(r)

    def on_reroll(self):
        if not self._current:
            return
        field = self.reroll_var.get()
        try:
            self.generator.reroll_field(self._current, field)
        except ValueError as exc:
            messagebox.showwarning("Cannot reroll", str(exc))
            return
        self._refresh_display()
        self.status.config(text=f"Rerolled {field}.", foreground="#2a7d2a")

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
        if r.get("directed"):
            row(r["directed"]["kind"], r["directed"]["text"])

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
        if r.get("skills"):
            row("Skills", _skills_str(r["skills"]))
        if r.get("glory") is not None:
            row("Glory", r["glory"])

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

    def on_copy_markdown(self):
        if self._current:
            self._to_clipboard(format_statblock_markdown(self._current),
                               "Copied Markdown statblock to clipboard.")

    def on_copy_image_prompt(self):
        if self._current:
            self._to_clipboard(build_image_prompt(self._current),
                               "Copied image prompt to clipboard.")


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

    try:
        rules = rules_module.load_rules(os.path.join(here, "data"))
    except rules_module.RulesError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Invalid rules data", str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if rules is None:
        print("Warning: data/rules.json not found; running in name-only mode.",
              file=sys.stderr)

    generator = Generator(cultures, rules)
    App(generator).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
