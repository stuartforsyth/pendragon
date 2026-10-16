#!/usr/bin/env python3
"""
Pendragon NPC Name Generator
============================

A small Tkinter GUI for quickly generating names and full NPC details for
non-player characters in *King Arthur Pendragon* (6th Edition).

Pick a gender and a culture, press **Generate**, and you get a random name plus
a rolled-up NPC: religion, Characteristics, Distinctive Features (appearance),
Personality Traits, and Passions. Click the name to copy just the name; press
**Copy Statblock** to copy the whole block for your GM notes.

Name lists are read from "Names by Culture.md"; the mechanical detail is driven
by the Markdown files in "rules/" (see rules.py). Editing those files changes
what the app produces.
"""

import datetime
import json
import os
import random
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk


import adversary as adversary_module
import encounter as encounter_module
import encounter_creator as encounter_creator_module
from core import pdf_export
from core import rules as rules_module
from core.names import DATA_FILE, find_data_file, parse_names_file
from core.npc import (
    EXALTED, FAMOUS, Generator, _ideals_summary, _squire_summary,
    build_description, build_image_prompt, format_roster_markdown,
    format_statblock, format_statblock_markdown, subtitle_str,
)



# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, generator):
        super().__init__()
        self.generator = generator
        self._current = None            # currently displayed result dict
        self._current_in_roster = None  # index if the current NPC is a roster entry
        self.roster = []                # NPCs kept this session
        self._detail_link_tags = []     # click-to-roll tags in the details Text

        self.title("Pendragon NPC Generator")
        self.geometry("780x1000")
        self.minsize(720, 860)

        names = self.generator.culture_names()
        self.gender_var = tk.StringVar(value="Male")
        self.culture_var = tk.StringVar(value="Cymri" if "Cymri" in names else names[0])
        self.class_var = tk.StringVar(value="Random")
        self.religion_var = tk.StringVar(value="Random")
        # When off, omit unflattering features and battle scars (e.g. for a
        # refined noble whom 'battle-scarred hands' would not suit).
        self.negative_traits_var = tk.BooleanVar(value=True)

        self._build_ui()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        # Global status bar, pinned at the bottom and shared by every tab.
        self.status = ttk.Label(self, text="Ready.", foreground="#2a7d2a")
        self.status.pack(side="bottom", fill="x", padx=10, pady=(0, 6))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        gen_tab = ttk.Frame(self.notebook)
        self.notebook.add(gen_tab, text="NPC Generator")
        self._build_generator_tab(gen_tab)

        # Encounter + creator tabs (only if combat data is available).
        self.adversary_tab = None
        self.encounter_tab = None
        if self.generator.rules and self.generator.rules.combat:
            self.encounter_tab = encounter_module.EncounterTab(
                self.notebook, self.generator.rules, self._set_status)
            self.notebook.add(self.encounter_tab, text="Encounter")
            self.adversary_tab = adversary_module.AdversaryTab(
                self.notebook, self.generator, self._set_status,
                on_change=self.encounter_tab.refresh_choices)
            self.notebook.add(self.adversary_tab, text="Adversary & Creature Creator")
            creator = encounter_creator_module.EncounterCreatorTab(
                self.notebook, self.generator.rules, self._set_status,
                self._send_encounter_to_tracker)
            self.notebook.add(creator, text="Encounter Creator")

    def _send_encounter_to_tracker(self, defn, n_players, name):
        """Generate a live encounter from a definition and switch to the tracker."""
        if not self.encounter_tab:
            return
        self.encounter_tab.refresh_choices()
        self.encounter_tab.run_definition(defn, n_players, name)
        self.notebook.select(self.encounter_tab)

    def _set_status(self, text, color="#2a7d2a"):
        self.status.config(text=text, foreground=color)

    def _build_generator_tab(self, parent):
        pad = {"padx": 10, "pady": 6}

        options = ttk.Frame(parent)
        options.pack(fill="x", **pad)

        gender_box = ttk.LabelFrame(options, text="Gender")
        gender_box.pack(side="left", fill="y", padx=(0, 10))
        for g in ("Male", "Female", "Random"):
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
        culture_box.pack(side="left", fill="y", padx=(0, 10))
        grid = ttk.Frame(culture_box)
        grid.pack(fill="both", expand=True, padx=4, pady=4)
        cols = 2
        # Preferred display order (Cymri default); any other cultures follow, and
        # a Random option to leave culture to the dice.
        order = ["Cymri", "Pict", "Saxon", "Irish", "Roman", "Frankish", "Aquitanian"]
        names = self.generator.culture_names()
        ordered = [c for c in order if c in names] + [c for c in names if c not in order]
        for i, c in enumerate(ordered + ["Random"]):
            ttk.Radiobutton(
                grid, text=c, value=c, variable=self.culture_var
            ).grid(row=i // cols, column=i % cols, sticky="w", padx=6, pady=2)

        # Religion — normally rolled from culture; Random keeps that behaviour,
        # a specific faith overrides it (and drives the trait virtue modifiers).
        religions = list(self.generator.rules.religions) if self.generator.rules else []
        if religions:
            religion_box = ttk.LabelFrame(options, text="Religion")
            religion_box.pack(side="left", fill="both", expand=True)
            rgrid = ttk.Frame(religion_box)
            rgrid.pack(fill="both", expand=True, padx=4, pady=4)
            for i, rel in enumerate(["Random"] + religions):
                ttk.Radiobutton(
                    rgrid, text=rel, value=rel, variable=self.religion_var
                ).pack(anchor="w", padx=6, pady=1)

        toggles = ttk.Frame(parent)
        toggles.pack(anchor="w", fill="x", padx=10, pady=(2, 0))
        ttk.Checkbutton(
            toggles, text="Negative physical traits (scars, unflattering features)",
            variable=self.negative_traits_var,
        ).pack(side="left")

        buttons = ttk.Frame(parent)
        buttons.pack(anchor="w", fill="x", padx=10, pady=(2, 4))
        ttk.Button(buttons, text="Generate", command=self.on_generate).pack(side="left")
        ttk.Button(buttons, text="Randomise", command=self.on_randomise).pack(
            side="left", padx=(8, 0))

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

        # Save the current NPC as a named adversary (Adversary Creator bridge).
        self.create_adv_btn = ttk.Button(buttons, text="Create Adversary",
                                         command=self.on_create_adversary, state="disabled")
        self.create_adv_btn.pack(side="left", padx=(8, 0))
        self.copy_buttons.append(self.create_adv_btn)

        # Export the official fillable character sheet (full Cymric knights only;
        # needs pypdf). Enabled by _update_export_state after each generate.
        self.export_pdf_btn = ttk.Button(buttons, text="Export sheet PDF…",
                                         command=self.on_export_pdf, state="disabled")
        self.export_pdf_btn.pack(side="left", padx=(8, 0))

        # Reroll a single field.
        reroll = ttk.Frame(parent)
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

        out_frame = ttk.LabelFrame(parent, text="Result  (click the name to copy just the name)")
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

        details_wrap = ttk.Frame(out_frame)
        details_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.details = tk.Text(
            details_wrap, height=14, wrap="word", relief="flat",
            background=self.cget("background"), font=("TkDefaultFont", 11),
        )
        self.details.pack(side="left", fill="both", expand=True)
        dscroll = ttk.Scrollbar(details_wrap, orient="vertical",
                                command=self.details.yview)
        dscroll.pack(side="right", fill="y")
        self.details.config(yscrollcommand=dscroll.set)
        self.details.tag_configure("label", font=("TkDefaultFont", 11, "bold"))
        self.details.tag_configure("desc", font=("TkDefaultFont", 11, "italic"),
                                   foreground="#333")
        # Famous/Exalted trait names share the brown highlight of their roll number.
        self.details.tag_configure("famous_name", foreground="#8a4b00",
                                   font=("TkDefaultFont", 11, "bold"))
        self.details.configure(state="disabled")

        # GM notes — free text per NPC, persisted with the roster.
        notes_frame = ttk.LabelFrame(out_frame, text="GM Notes  (saved with the roster)")
        notes_frame.pack(fill="x", padx=10, pady=(0, 8))
        self.notes_text = tk.Text(notes_frame, height=4, wrap="word",
                                  font=("TkDefaultFont", 11))
        self.notes_text.pack(fill="x", padx=6, pady=6)

        self._build_roster_ui(parent)

    def _build_roster_ui(self, parent):
        frame = ttk.LabelFrame(parent, text="Session roster")
        frame.pack(fill="both", padx=10, pady=(0, 6))

        top = ttk.Frame(frame)
        top.pack(fill="both", expand=True, padx=6, pady=(6, 2))
        self.roster_list = tk.Listbox(top, height=5, activestyle="dotbox")
        self.roster_list.pack(side="left", fill="both", expand=True)
        self.roster_list.bind("<<ListboxSelect>>", self.on_roster_select)
        scroll = ttk.Scrollbar(top, orient="vertical",
                               command=self.roster_list.yview)
        scroll.pack(side="right", fill="y")
        self.roster_list.config(yscrollcommand=scroll.set)

        bar = ttk.Frame(frame)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        # "Add current" is enabled once something is generated; the rest depend
        # on the roster being non-empty.
        self.add_btn = ttk.Button(bar, text="Add current", state="disabled",
                                  command=self.on_add_to_roster)
        self.add_btn.pack(side="left")
        # Load is always available (you can load into an empty roster).
        ttk.Button(bar, text="Load roster…", command=self.on_load_roster).pack(
            side="left", padx=(6, 0))
        self.roster_buttons = []
        for text, cmd in (
            ("Remove", self.on_remove_from_roster),
            ("Clear", self.on_clear_roster),
            ("Copy Markdown", self.on_copy_roster),
            ("Save roster…", self.on_save_roster),
        ):
            b = ttk.Button(bar, text=text, command=cmd, state="disabled")
            b.pack(side="left", padx=(6, 0))
            self.roster_buttons.append(b)

    # -- actions -----------------------------------------------------------

    # -- GM notes -----------------------------------------------------------

    def _sync_notes_from_widget(self):
        """Write the notes box back into the current NPC dict."""
        if self._current is not None:
            self._current["notes"] = self.notes_text.get("1.0", "end").rstrip("\n")

    def _load_notes(self):
        self.notes_text.delete("1.0", "end")
        if self._current is not None:
            self.notes_text.insert("1.0", self._current.get("notes", ""))

    def _confirm_discard_notes(self):
        """Before replacing the current NPC: guard unsaved notes. Returns True to proceed."""
        self._sync_notes_from_widget()
        cur = self._current
        if cur and self._current_in_roster is None and cur.get("notes", "").strip():
            ans = messagebox.askyesnocancel(
                "Unsaved GM notes",
                f"'{cur['full']}' has GM notes that aren't in the roster yet.\n\n"
                "Add this NPC (with its notes) to the roster first?\n\n"
                "Yes = add to roster and continue\n"
                "No = discard the notes and continue\n"
                "Cancel = go back",
            )
            if ans is None:
                return False
            if ans:
                self.on_add_to_roster()
        return True

    # -- generation ---------------------------------------------------------

    def on_randomise(self):
        """One-click: randomise gender, class, and culture, then generate."""
        if not self._confirm_discard_notes():
            return
        gender = random.choice(("Male", "Female"))
        self.gender_var.set(gender)
        self.culture_var.set(random.choice(self.generator.culture_names()))
        self.religion_var.set("Random")   # let religion follow the rolled culture
        rules = self.generator.rules
        if rules and rules.social_classes:
            self.class_var.set(rules.roll_class(gender))  # valid for the gender
        self.on_generate(_checked=True)

    def on_generate(self, _checked=False):
        if not _checked and not self._confirm_discard_notes():
            return
        # "Random" leaves that field to the dice; the radio stays on Random so
        # repeated Generate keeps re-rolling it (class Random is resolved inside
        # generate()). Fixed choices are used as-is.
        culture = self.culture_var.get()
        if culture == "Random":
            culture = random.choice(self.generator.culture_names())
        gender = self.gender_var.get()
        if gender == "Random":
            gender = random.choice(("Male", "Female"))
        social_class = self.class_var.get()
        religion = self.religion_var.get()
        if religion == "Random":
            religion = None            # roll from culture (the default)
        try:
            result = self.generator.generate(
                culture, gender, social_class, religion,
                include_negative_appearance=self.negative_traits_var.get())
        except ValueError as exc:
            messagebox.showwarning("No names", str(exc))
            return

        self._current = result
        self._current_in_roster = None
        # A single-gender class (Lady) may have overridden the choice; reflect it
        # — unless the user asked for a random gender, which we leave selected.
        if self.gender_var.get() != "Random":
            self.gender_var.set(result["gender"])
        self._refresh_display()
        for b in self.copy_buttons:
            b.config(state="normal")
        self.add_btn.config(state="normal")
        self.reroll_menu.config(state="readonly")
        self.reroll_btn.config(state="normal")
        self.status.config(
            text="Generated. Click the name to copy it; click any characteristic, skill, "
                 "damage, trait or passion value to roll it.",
            foreground="#2a7d2a",
        )

    def _refresh_display(self):
        r = self._current
        self.name_label.config(text=r["full"])
        self.subtitle.config(text=subtitle_str(r))
        self._render_details(r)
        self._load_notes()
        self._update_export_state()

    def _update_export_state(self):
        """The PDF export button is only meaningful for a full Cymric knight, and
        only works when pypdf is installed."""
        ok = (pdf_export.PDF_AVAILABLE and self._current
              and self._current.get("full_knight"))
        self.export_pdf_btn.config(state="normal" if ok else "disabled")

    def on_export_pdf(self):
        r = self._current
        if not (r and r.get("full_knight")):
            return
        if not pdf_export.PDF_AVAILABLE:
            messagebox.showinfo(
                "PDF export unavailable",
                "Exporting a filled character sheet needs the 'pypdf' package.\n\n"
                "Install it with:  python -m pip install pypdf")
            return
        here = os.path.dirname(os.path.abspath(__file__))
        template = pdf_export.sheet_template_path(here)
        if not os.path.isfile(template):
            messagebox.showerror(
                "Sheet template missing",
                f"Could not find the fillable character sheet at:\n{template}")
            return
        path = filedialog.asksaveasfilename(
            title="Export character sheet PDF",
            defaultextension=".pdf",
            initialfile=f"{pdf_export.safe_filename(r['full'])}.pdf",
            filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
        if not path:
            return
        try:
            n = pdf_export.export_sheet(r, template, path)
        except Exception as exc:                      # noqa: BLE001
            messagebox.showerror("Export failed", str(exc))
            return
        self._set_status(f"Exported {n} fields to {path}", "#2a7d2a")

    def on_reroll(self):
        if not self._current:
            return
        self._sync_notes_from_widget()  # keep any typed notes across the reroll
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

        # Drop the click-to-roll tags from the previous render so they don't leak.
        for tag in self._detail_link_tags:
            self.details.tag_delete(tag)
        self._detail_link_tags = []

        def row(label, value):
            self.details.insert("end", f"{label}: ", ("label",))
            self.details.insert("end", f"{value}\n")

        def link(text, callback, famous=False):
            """Insert a click-to-roll link that runs callback() when clicked."""
            self._detail_link_tags.append(tag := f"roll{len(self._detail_link_tags)}")
            self.details.tag_configure(
                tag, underline=1, foreground=("#8a4b00" if famous else "#1a5fb4"),
                font=("TkDefaultFont", 11, "bold" if famous else "normal"))
            self.details.tag_bind(tag, "<Button-1>", lambda e, cb=callback: cb())
            self.details.tag_bind(tag, "<Enter>",
                                  lambda e: self.details.configure(cursor="hand2"))
            self.details.tag_bind(tag, "<Leave>",
                                  lambda e: self.details.configure(cursor=""))
            self.details.insert("end", str(text), (tag,))

        def roll_link(name, value):
            """A value that rolls d20 against itself (traits/passions/skills)."""
            link(value, lambda n=name, v=value: self._roll_personality(n, v),
                 famous=value >= FAMOUS)

        def named_roll(name, value):
            """Insert 'Name <link>'. Famous/Exalted names get the brown highlight;
            Exalted names are also uppercased."""
            shown = name.upper() if value >= EXALTED else name
            name_tags = ("famous_name",) if value >= FAMOUS else ()
            self.details.insert("end", shown, name_tags)
            self.details.insert("end", " ")
            roll_link(name, value)

        # Read-aloud description paragraph, above everything else.
        self.details.insert("end", build_description(r) + "\n\n", ("desc",))

        if r.get("appearance"):
            a = r["appearance"]
            height = f", ~{r['height']} tall" if r.get("height") else ""
            build = f"{a['build']}; " if a.get("build") else ""
            row("Appearance", f"{build}{a['descriptor']}{height}; {a['eyes']} eyes")
            if a["features"]:
                row("Distinctive Features", "; ".join(a["features"]))

        if r.get("manner"):
            row("Manner", r["manner"])

        if r.get("traits"):
            self.details.insert("end", "\n")
            self.details.insert("end", "Personality Traits: ", ("label",))
            for i, (left, lval, right, rval) in enumerate(r["traits"]):
                if i:
                    self.details.insert("end", ", ")
                named_roll(left, lval)
                self.details.insert("end", "/")
                named_roll(right, rval)
            self.details.insert("end", "\n")
        if r.get("passions"):
            self.details.insert("end", "Passions: ", ("label",))
            for i, (name, value) in enumerate(r["passions"]):
                if i:
                    self.details.insert("end", ", ")
                named_roll(name, value)
            self.details.insert("end", "\n")
        if r.get("directed"):
            row(r["directed"]["kind"], r["directed"]["text"])

        if r.get("stats"):
            self.details.insert("end", "\n")
            st = r["stats"]
            # Characteristics: spelled out (no SIZ/DEX acronyms) and click-to-roll
            # (pass/fail only — characteristics have no critical/fumble).
            self.details.insert("end", "Characteristics: ", ("label",))
            for i, k in enumerate(("SIZ", "DEX", "STR", "CON", "APP")):
                if i:
                    self.details.insert("end", "  ")
                full = encounter_module.CHAR_FULL[k]
                self.details.insert("end", f"{full} ")
                link(st[k], lambda n=full, v=st[k]: self._roll_characteristic(n, v))
            self.details.insert("end", "\n")
            # Derived: only Damage is a roll; the rest are thresholds/values.
            d = r["derived"]
            self.details.insert("end", "Derived: ", ("label",))
            self.details.insert("end", f"HP {d['Hit Points']} · Move {d['Move']} · Damage ")
            link(d["Damage"],
                 lambda expr=d["Damage"]: self._roll_damage_expr("Damage", expr))
            self.details.insert(
                "end", f" · Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
                f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}\n")
        if r.get("skills"):
            self.details.insert("end", "Skills: ", ("label",))
            for i, (name, value) in enumerate(
                    sorted(r["skills"].items(), key=lambda kv: (-kv[1], kv[0]))):
                if i:
                    self.details.insert("end", ", ")
                named_roll(name, value)
            self.details.insert("end", "\n")
        if r.get("glory") is not None:
            row("Glory", r["glory"])

        if r.get("full_knight"):
            self.details.insert("end", "\n")
            if r.get("homeland"):
                res = f" ({r['residence']})" if r.get("residence") else ""
                row("Age / Home", f"{r.get('age', 21)} · {r['homeland']}{res}")
            if r.get("family_talent"):
                row("Family talent", "+3 " + ", ".join(r["family_talent"]))
            if r.get("family_lore"):
                self.details.insert("end", "Family lore:\n", ("label",))
                for ln in r["family_lore"]:
                    self.details.insert("end", f"  • an ancestor {ln}\n")
            if r.get("ideals"):
                row("Ideals", _ideals_summary(r["ideals"]))
            if r.get("squire"):
                row("Squire", _squire_summary(r["squire"]))

        if r.get("naming_note"):
            self.details.insert("end", "\n")
            row("Naming", r["naming_note"])

        if r.get("pronunciation"):
            self.details.insert("end", "Pronunciation:\n", ("label",))
            for hint in r["pronunciation"]:
                self.details.insert("end", f"  • {hint}\n")

        self.details.configure(state="disabled")

    def _log_roll(self, line, status, color):
        """Append a click-to-roll result to GM Notes and flash it in the status bar."""
        stamp = datetime.datetime.now().strftime("%H:%M")
        entry = f"[{stamp}] {line}"
        existing = self.notes_text.get("1.0", "end").strip()
        self.notes_text.insert("end" if existing else "1.0",
                               ("\n" + entry) if existing else entry)
        self.notes_text.see("end")
        self._sync_notes_from_widget()  # keep the current NPC dict / roster in sync
        self._set_status(status, color)

    def _roll_personality(self, name, value):
        """Trait/passion/skill: d20 vs value with success/critical/fumble.

        A value over 20 uses the critical bonus (Core Ch.2): 20 (+x), never
        fails, criticals on 20 - x and above. See encounter.resolve_skill."""
        roll, outcome = encounter_module.resolve_skill(value)
        shown = encounter_module.skill_display(value)
        self._log_roll(f"{name} ({shown}): rolled {roll} — {outcome.upper()}",
                       f"{name} ({shown}): rolled {roll} — {outcome}",
                       encounter_module.OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_characteristic(self, name, value):
        """Characteristic: d20 pass/fail only — no critical/fumble (Core Ch.2)."""
        roll = random.randint(1, 20)
        outcome = "success" if roll <= value else "failure"
        self._log_roll(f"{name} ({value}): rolled {roll} — {outcome.upper()}",
                       f"{name} ({value}): rolled {roll} — {outcome}",
                       encounter_module.OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_damage_expr(self, label, expr):
        """Damage: choose normal or critical (+4D6), optionally rebated (½), or cancel."""
        choice = encounter_module.ask_damage_mode(
            self, f"{label} ({expr}) — resolve damage:")
        if choice is None:
            return
        critical, rebated = choice
        total, breakdown = encounter_module.roll_damage(
            expr, critical=critical, rebated=rebated)
        self._log_roll(f"{label} {breakdown}", f"{label}: {total}", "#1a5fb4")

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

    def on_create_adversary(self):
        """Draft the current NPC as a named adversary and open the creator tab."""
        if not (self._current and self.adversary_tab):
            return
        draft = adversary_module.draft_from_npc(
            self._current, self.generator.rules.combat)
        self.adversary_tab.open_with_draft(draft)
        self.notebook.select(self.adversary_tab)

    # -- roster ------------------------------------------------------------

    def _refresh_roster(self):
        self.roster_list.delete(0, "end")
        for r in self.roster:
            mark = "  ✎" if r.get("notes", "").strip() else ""
            self.roster_list.insert("end", f"{r['full']}  ·  {subtitle_str(r)}{mark}")
        state = "normal" if self.roster else "disabled"
        for b in self.roster_buttons:
            b.config(state=state)

    def _reindex_current(self):
        """Recompute which roster slot (if any) the current NPC is, by identity."""
        self._current_in_roster = next(
            (i for i, x in enumerate(self.roster) if x is self._current), None)

    def _enable_npc_controls(self):
        for b in self.copy_buttons:
            b.config(state="normal")
        self.add_btn.config(state="normal")
        self.reroll_menu.config(state="readonly")
        self.reroll_btn.config(state="normal")

    def on_roster_select(self, _event=None):
        """Clicking a roster entry loads it into the result view for viewing/editing."""
        sel = self.roster_list.curselection()
        if not sel or sel[0] >= len(self.roster):
            return
        self._sync_notes_from_widget()  # preserve edits to the previous NPC
        # Edit the roster entry live, so GM notes and edits stick to the saved NPC.
        self._current = self.roster[sel[0]]
        self._current_in_roster = sel[0]
        r = self._current
        self.gender_var.set(r["gender"])
        self.culture_var.set(r["culture"])
        if r.get("social_class"):
            self.class_var.set(r["social_class"])
        if r.get("religion"):
            self.religion_var.set(r["religion"])
        self._refresh_display()
        self._enable_npc_controls()
        self.status.config(text=f"Editing '{r['full']}' from the roster.",
                           foreground="#1a5fb4")

    def on_add_to_roster(self):
        if not self._current:
            return
        self._sync_notes_from_widget()
        if self._current_in_roster is not None:  # already saved; nothing to add
            self.status.config(text=f"'{self._current['full']}' is already in the roster.",
                               foreground="#1a5fb4")
            return
        self.roster.append(self._current)  # keep editing this same object live
        self._current_in_roster = len(self.roster) - 1
        self._refresh_roster()
        self.roster_list.see("end")
        self.status.config(
            text=f"Added '{self._current['full']}' to roster ({len(self.roster)} total).",
            foreground="#2a7d2a")

    def on_remove_from_roster(self):
        sel = self.roster_list.curselection()
        if not sel:
            self.status.config(text="Select a roster entry to remove.", foreground="#a33")
            return
        removed = self.roster.pop(sel[0])
        self._reindex_current()
        self._refresh_roster()
        self.status.config(text=f"Removed '{removed['full']}' from roster.",
                           foreground="#1a5fb4")

    def on_clear_roster(self):
        if self.roster and messagebox.askyesno(
                "Clear roster", f"Remove all {len(self.roster)} NPCs from the roster?"):
            self.roster.clear()
            self._current_in_roster = None
            self._refresh_roster()
            self.status.config(text="Roster cleared.", foreground="#1a5fb4")

    def on_copy_roster(self):
        self._sync_notes_from_widget()
        if self.roster:
            self._to_clipboard(
                format_roster_markdown(self.roster),
                f"Copied roster ({len(self.roster)} NPCs) as Markdown.")

    def on_save_roster(self):
        self._sync_notes_from_widget()
        if not self.roster:
            return
        default = f"pendragon-roster-{datetime.date.today().isoformat()}.json"
        path = filedialog.asksaveasfilename(
            title="Save roster", defaultextension=".json", initialfile=default,
            filetypes=[("Roster (JSON)", "*.json"), ("Markdown", "*.md"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                if path.lower().endswith(".md"):
                    fh.write(format_roster_markdown(self.roster))  # readable, not loadable
                else:
                    json.dump(self.roster, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.status.config(text=f"Saved {len(self.roster)} NPCs to {path}",
                           foreground="#2a7d2a")

    def on_load_roster(self):
        path = filedialog.askopenfilename(
            title="Load roster",
            filetypes=[("Roster (JSON)", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if not isinstance(loaded, list):
                raise ValueError("file is not a saved roster")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Load failed",
                                 f"Could not load roster:\n{exc}\n\n"
                                 "Load a .json roster saved by this app.")
            return
        if self.roster and not messagebox.askyesno(
                "Load roster",
                f"Replace the current roster ({len(self.roster)} NPCs) with "
                f"{len(loaded)} loaded NPCs?\n\nNo = append them instead."):
            self.roster.extend(loaded)
        else:
            self.roster = loaded
        self._reindex_current()
        self._refresh_roster()
        self.status.config(text=f"Loaded {len(loaded)} NPCs from {path}",
                           foreground="#2a7d2a")


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
