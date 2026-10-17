#!/usr/bin/env python3
"""
Encounter Generator for the Pendragon app (human encounters).

The "Encounter" notebook tab. The combat model and resolution live in
``core.combat`` / ``core.dice`` (shared with the web app); data comes from
``data/combat.json`` via ``Rules.combat`` (see docs/encounter-generator-spec.md).
"""

import datetime
import random
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from core.combat import (  # noqa: F401  (re-exported for the other Tk tabs)
    CHAR_FULL, SURRENDER_RESULTS, alpha, CombatLog, Combatant, Encounter, resolve_roster,
    roll_ransom, surrender_check,
)
from core.dice import CRITICAL_BONUS, resolve_skill, roll_damage, skill_display


# ---------------------------------------------------------------------------
# Tk helpers
# ---------------------------------------------------------------------------


def bind_mousewheel(canvas):
    """Let the mouse wheel scroll a Canvas while the pointer is over it.

    A Canvas has no default wheel binding. On Tk 9 the wheel arrives as
    <MouseWheel> (delta +-120) even on X11; on Tk 8.6/X11 it arrives as
    Button-4/Button-5 — both are handled. Because the inner frame covers the
    whole canvas the pointer is almost always over a child widget, so bind
    globally while the pointer is anywhere in the canvas's subtree and release
    only once it has truly left (a <Leave> fired by moving onto a child must
    not unbind, or the wheel would die over the rows).
    """
    step = 3  # lines per wheel notch (one unit felt too slow)

    def _scroll(event):
        num = getattr(event, "num", 0)
        if num == 4:
            canvas.yview_scroll(-step, "units")
        elif num == 5:
            canvas.yview_scroll(step, "units")
        elif event.delta:
            canvas.yview_scroll(-step if event.delta > 0 else step, "units")

    def _over_canvas():
        w = canvas.winfo_containing(*canvas.winfo_pointerxy())
        while w is not None:
            if w is canvas:
                return True
            w = getattr(w, "master", None)
        return False

    def _bind(_e):
        canvas.bind_all("<MouseWheel>", _scroll)
        canvas.bind_all("<Button-4>", _scroll)
        canvas.bind_all("<Button-5>", _scroll)

    def _unbind(_e):
        if _over_canvas():
            return
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    canvas.bind("<Enter>", _bind, add="+")
    canvas.bind("<Leave>", _unbind, add="+")


def ask_damage_mode(parent, prompt):
    """Modal chooser for a damage roll.

    Returns ``(critical, rebated)`` booleans, or ``None`` (cancel — the caller
    should roll nothing and log nothing). "Rebated — ½ damage" is a checkbox
    that applies to whichever roll button is pressed, so a critical can be
    rebated too.
    """
    dlg = tk.Toplevel(parent)
    dlg.title("Damage roll")
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)
    result = {"value": None}
    rebated = tk.BooleanVar(value=False)

    ttk.Label(dlg, text=prompt, wraplength=340).pack(
        anchor="w", padx=14, pady=(14, 8))
    ttk.Checkbutton(dlg, text="Rebated — ½ damage (blunted / tournament weapon)",
                    variable=rebated).pack(anchor="w", padx=14, pady=(0, 8))

    def choose(critical):
        result["value"] = (critical, bool(rebated.get()))
        dlg.destroy()

    ttk.Button(dlg, text="Normal damage", width=32,
               command=lambda: choose(False)).pack(fill="x", padx=14, pady=2)
    ttk.Button(dlg, text=f"Critical — +{CRITICAL_BONUS}", width=32,
               command=lambda: choose(True)).pack(fill="x", padx=14, pady=2)
    ttk.Button(dlg, text="Cancel (don't roll or log)", width=32,
               command=dlg.destroy).pack(fill="x", padx=14, pady=(2, 0))
    tk.Frame(dlg, height=8).pack()

    dlg.bind("<Escape>", lambda e: dlg.destroy())
    dlg.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - dlg.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    dlg.grab_set()
    parent.wait_window(dlg)
    return result["value"]

# ---------------------------------------------------------------------------
# GUI — the Encounter tab
# ---------------------------------------------------------------------------

OUTCOME_COLOR = {
    "critical": "#1a7a1a", "success": "#2a7d2a",
    "failure": "#a33", "fumble": "#c00",
}


class EncounterTab(ttk.Frame):
    def __init__(self, parent, rules, set_status):
        super().__init__(parent)
        self.rules = rules
        self.set_status = set_status
        self.encounter = Encounter(rules)
        self.log = CombatLog()
        self._dirty = False  # unsaved log/notes since the last Save
        self._build_ui()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        self.norm_font = tkfont.Font(family="TkDefaultFont", size=10)
        self.down_font = tkfont.Font(family="TkDefaultFont", size=10, overstrike=1)
        self.elite_font = tkfont.Font(family="TkDefaultFont", size=10, weight="bold")
        # Stats are now the primary interaction surface (click-to-roll), so show
        # them at a readable size rather than the old tiny detail font.
        self.stat_font = tkfont.Font(family="TkDefaultFont", size=10)
        # The description/armour/looks flavour line, bumped up from the old 8pt.
        self.flavour_font = tkfont.Font(family="TkDefaultFont", size=10, slant="italic")
        self.frame_bg = ttk.Style().lookup("TFrame", "background") or self.cget("background")
        self._link_seq = 0

        setup = ttk.Frame(self)
        setup.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(setup, text="Players:").pack(side="left")
        self.players_var = tk.IntVar(value=4)
        ttk.Spinbox(setup, from_=1, to=20, width=4,
                    textvariable=self.players_var).pack(side="left", padx=(4, 10))
        ttk.Label(setup, text="Encounter search:").pack(side="left")
        self.theme_var = tk.StringVar(value="")   # the selected encounter to launch
        self.enc_search_var = tk.StringVar()
        enc_search = ttk.Entry(setup, textvariable=self.enc_search_var, width=22)
        enc_search.pack(side="left", padx=(4, 10))
        self.enc_search_var.trace_add("write", lambda *a: self._refresh_encounter_list())
        enc_search.bind("<Return>", lambda e: self.on_generate())
        ttk.Button(setup, text="Launch encounter",
                   command=self.on_generate).pack(side="left")
        ttk.Button(setup, text="Clear", command=self.on_clear).pack(side="left", padx=(6, 0))

        # Searchable list of matching encounters (type to filter; select then
        # Launch, or double-click) — replaces the old dropdown so a long theme
        # list is filterable rather than scrolled.
        enc_frame = ttk.Frame(self)
        enc_frame.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(enc_frame,
                  text="Matching encounters — select then Launch, or double-click:",
                  foreground="#444", font=("TkDefaultFont", 9)).pack(anchor="w")
        listrow = ttk.Frame(enc_frame)
        listrow.pack(fill="x")
        self.enc_list = tk.Listbox(listrow, height=5, activestyle="dotbox",
                                   exportselection=False)
        self.enc_list.pack(side="left", fill="x", expand=True)
        esb = ttk.Scrollbar(listrow, orient="vertical", command=self.enc_list.yview)
        esb.pack(side="right", fill="y")
        self.enc_list.configure(yscrollcommand=esb.set)
        self.enc_list.bind("<<ListboxSelect>>", self._on_encounter_select)
        self.enc_list.bind("<Double-Button-1>", lambda e: self.on_generate())
        self._refresh_encounter_list()

        addrow = ttk.Frame(self)
        addrow.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(addrow, text="Add combatant:").pack(side="left")
        adversaries = alpha(self.encounter.templates)
        self.add_var = tk.StringVar(value=adversaries[0] if adversaries else "")
        self.add_combo = ttk.Combobox(addrow, textvariable=self.add_var, width=20,
                                      state="readonly", values=adversaries)
        self.add_combo.pack(side="left", padx=(4, 6))
        ttk.Button(addrow, text="Add", command=self.on_add).pack(side="left")

        # How-to block: explain the per-row textboxes and click-to-roll, since the
        # tracker's controls aren't otherwise self-evident.
        howto = ttk.LabelFrame(self, text="How to use the tracker")
        howto.pack(fill="x", padx=10, pady=(0, 6))
        howto_lbl = ttk.Label(
            howto, justify="left", foreground="#444", font=("TkDefaultFont", 9),
            text=(
                "• engages — type who this enemy is fighting (e.g. a knight's name); it is logged.\n"
                "• HP change — type the total damage as a negative to subtract it, or healing as a "
                "positive to add it, then press Apply or Enter. Example: an enemy on 28/28 takes "
                "8 damage → type -8, Apply → 20/28. A single hit ≥ Constitution is a Major Wound.\n"
                "• Click any underlined stat number to roll it (characteristic, attack skill, damage, "
                "skill).\n"
                "• Mod — a situational modifier (e.g. -5 mounted vs. mounted, +5 mounted vs. foot, "
                "-2 shield penalty; net them yourself, e.g. +3), then press Enter. It's applied "
                "automatically to every characteristic, attack-skill and named-skill roll for that "
                "combatant — not to damage — until you change it back to 0. Red = penalty, "
                "green = bonus."
            ),
        )
        howto_lbl.pack(anchor="w", fill="x", padx=8, pady=4)
        # Wrap the help text to the panel width so long bullets fill the row rather
        # than leaving a wide blank gap on the right.
        howto.bind("<Configure>",
                   lambda e, lbl=howto_lbl: lbl.configure(wraplength=max(300, e.width - 24)))
        self.howto = howto

        # Shared descriptions: a generic adversary's flavour text (and any
        # special-mechanics notes) shown once per type here, rather than repeated
        # on every combatant row. Hidden while there is nothing to show.
        self.desc_frame = ttk.LabelFrame(self, text="Descriptions & mechanics")
        self.desc_label = ttk.Label(self.desc_frame, justify="left", foreground="#333",
                                    font=("TkDefaultFont", 9))
        self.desc_label.pack(anchor="w", fill="x", padx=8, pady=4)
        self.desc_frame.bind(
            "<Configure>",
            lambda e, lbl=self.desc_label: lbl.configure(wraplength=max(300, e.width - 24)))

        # Scrollable combatant tracker.
        tracker = ttk.LabelFrame(self, text="Combatants")
        tracker.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        canvas = tk.Canvas(tracker, highlightthickness=0)
        vs = ttk.Scrollbar(tracker, orient="vertical", command=canvas.yview)
        self.rows_frame = ttk.Frame(canvas)
        self.rows_frame.columnconfigure(0, weight=1)  # rows fill the tracker width
        self.rows_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        rows_window = canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        # Keep the rows as wide as the viewport so long stat lines wrap to the next
        # line instead of being clipped past the right edge.
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(rows_window, width=e.width))
        canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        bind_mousewheel(canvas)

        # Log + GM notes side by side.
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", padx=10, pady=(0, 8))

        log_frame = ttk.LabelFrame(bottom, text="Combat log")
        log_frame.pack(side="left", fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=7, wrap="word", state="disabled",
                                font=("TkDefaultFont", 9))
        self.log_text.pack(fill="both", expand=True, padx=6, pady=(6, 2))

        # Transient round note: write a one-off line into the log, then clear.
        noterow = ttk.Frame(log_frame)
        noterow.pack(fill="x", padx=6, pady=(0, 2))
        ttk.Label(noterow, text="Round note:").pack(side="left")
        self.round_note = ttk.Entry(noterow)
        self.round_note.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self.round_note.bind("<Return>", lambda e: self.on_add_round_note())
        ttk.Button(noterow, text="Add to log",
                   command=self.on_add_round_note).pack(side="left")

        logbar = ttk.Frame(log_frame)
        logbar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(logbar, text="Copy log", command=self.on_copy_log).pack(side="left")
        ttk.Button(logbar, text="Save log…", command=self.on_save_log).pack(
            side="left", padx=(6, 0))

        notes_frame = ttk.LabelFrame(bottom, text="GM Notes  (saved into the log file)")
        notes_frame.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.notes_text = tk.Text(notes_frame, height=7, wrap="word",
                                  font=("TkDefaultFont", 10))
        self.notes_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.notes_text.bind("<KeyRelease>",
                             lambda e: setattr(self, "_dirty", True))

        self._refresh_rows()

    # -- combatant rows ----------------------------------------------------

    # -- encounter search list ---------------------------------------------

    def _refresh_encounter_list(self):
        """Repopulate the encounter list with the themes matching the search
        box (case-insensitive substring); auto-select a lone match."""
        self.enc_list.delete(0, "end")
        q = self.enc_search_var.get().strip().lower()
        self._enc_keys = []
        for name in alpha(self.encounter.themes):
            if q and q not in name.lower():
                continue
            self.enc_list.insert("end", name)
            self._enc_keys.append(name)
        if len(self._enc_keys) == 1:
            self.enc_list.selection_set(0)
            self.theme_var.set(self._enc_keys[0])
        elif self.theme_var.get() in self._enc_keys:
            self.enc_list.selection_set(self._enc_keys.index(self.theme_var.get()))
        else:
            self.theme_var.set("")

    def _on_encounter_select(self, _e):
        sel = self.enc_list.curselection()
        if sel:
            self.theme_var.set(self._enc_keys[sel[0]])

    def _refresh_descriptions(self):
        """Collect each combatant type's description + mechanics notes once,
        in first-seen order, into the shared Descriptions panel above the
        tracker. Hidden when no combatant has a description or notes."""
        seen, lines = {}, []
        for c in self.encounter.combatants:
            if c.type in seen:
                continue
            seen[c.type] = True
            parts = []
            if c.description.strip():
                parts.append(c.description.strip())
            if c.notes.strip():
                parts.append(f"Mechanics: {c.notes.strip()}")
            if parts:
                lines.append(f"• {c.type} — " + "   ·   ".join(parts))
        if lines:
            self.desc_label.config(text="\n".join(lines))
            self.desc_frame.pack(fill="x", padx=10, pady=(0, 6), after=self.howto)
        else:
            self.desc_frame.pack_forget()

    def _refresh_rows(self):
        self._refresh_descriptions()
        for w in self.rows_frame.winfo_children():
            w.destroy()
        if not self.encounter.combatants:
            ttk.Label(self.rows_frame, foreground="#777",
                      text="No combatants. Generate an encounter or add one above."
                      ).grid(row=0, column=0, padx=8, pady=8, sticky="w")
            return
        for i, c in enumerate(self.encounter.combatants):
            self._build_row(i, c)

    def _build_row(self, i, c):
        row = ttk.Frame(self.rows_frame)
        row.grid(row=i, column=0, sticky="ew", padx=2, pady=1)
        # A weighted trailing column soaks up spare width so the stat and flavour
        # lines (which span it) stretch to the full width instead of being clipped.
        row.columnconfigure(11, weight=1)

        # Named NPCs and promoted champions both stand out from rank-and-file
        # combatants: bold, coloured, and prefixed with a marker (★ champion,
        # ◆ named — a named champion shows both).
        down = c.down
        creature = c.category in ("beast", "monster", "fae")
        standout = c.elite or c.named or creature
        name_font = self.down_font if down else (
            self.elite_font if standout else self.norm_font)
        if down:
            fg = "#999"
        elif c.elite:
            fg = "#8a4b00"          # champion — brown/gold
        elif c.named:
            fg = "#5a2a82"          # named NPC — royal purple
        elif c.category == "monster":
            fg = "#8b1a1a"          # monster — dark red
        elif c.category == "beast":
            fg = "#0a6b3b"          # beast — forest green
        elif c.category == "fae":
            fg = "#1a6a8a"          # faerie — teal
        else:
            fg = "#000"

        # ✦ marks a creature (beast/monster/fae); ★ champion, ◆ named.
        marker = ("★" if c.elite else "") + ("◆" if c.named else "") + \
                 ("✦" if creature and not c.named else "")
        marker = f"{marker} " if marker else ""
        # A fled combatant is greyed like any 'down' foe but flagged as untracked;
        # widen the label so the flag isn't clipped by the usual fixed width.
        fled = c.status == "fled"
        suffix = "  (fled — not tracked)" if fled else ""
        name = tk.Label(row, text=f"{marker}{c.display_name}{suffix}",
                        width=40 if fled else 22, anchor="w", font=name_font, fg=fg)
        name.grid(row=0, column=0, sticky="w")

        # "<name> engages [who] " — an inline label makes the textbox self-explaining.
        tk.Label(row, text="engages", font=self.norm_font, fg=fg).grid(
            row=0, column=1, padx=(2, 2))
        eng = ttk.Entry(row, width=14)
        eng.insert(0, c.engaged_with)
        eng.grid(row=0, column=2, padx=(0, 10))
        eng.bind("<KeyRelease>", lambda e, cc=c, w=eng: setattr(cc, "engaged_with", w.get()))
        eng.bind("<FocusOut>", lambda e, cc=c, w=eng: self._engage(cc, w.get()))

        # Hit Points current/max + an "HP change" delta box (type the total damage
        # as a negative, or healing as a positive, then Apply).
        ttk.Label(row, text=f"Hit Points {c.cur_hp}/{c.max_hp}", width=15, anchor="w",
                  foreground=fg).grid(row=0, column=3, padx=(0, 4))
        tk.Label(row, text="HP change", font=self.norm_font, fg=fg).grid(
            row=0, column=4, padx=(0, 2))
        dv = tk.StringVar()
        de = ttk.Entry(row, width=5, textvariable=dv)
        de.grid(row=0, column=5)
        de.bind("<Return>", lambda e, cc=c, v=dv: self._apply_hp(cc, v.get()))
        ttk.Button(row, text="Apply", width=5,
                   command=lambda cc=c, v=dv: self._apply_hp(cc, v.get())).grid(
                       row=0, column=6, padx=(2, 0))

        # Actions menu (promote/demote, knock out/revive, deactivate, ransom,
        # surrender check)
        mb = ttk.Menubutton(row, text="Actions ▾", width=9)
        menu = tk.Menu(mb, tearoff=0)
        menu.add_command(label="Demote" if c.elite else "Promote to champion",
                         command=lambda cc=c: self._toggle_promote(cc))
        menu.add_command(
            label="Revive" if c.status in ("unconscious", "dead") else "Knock out",
            command=lambda cc=c: self._toggle_down(cc))
        menu.add_command(
            label="Reactivate (resume tracking)" if c.status == "fled"
            else "Deactivate (fled / not tracked)",
            command=lambda cc=c: self._toggle_fled(cc))
        if c.ransom:
            menu.add_command(label="Roll ransom",
                             command=lambda cc=c: self._roll_ransom(cc))
        menu.add_command(label=f"Surrender check (Valorous {c.valorous})",
                         command=lambda cc=c: self._surrender_check(cc))
        mb["menu"] = menu
        mb.grid(row=0, column=7, padx=(8, 0))
        ttk.Button(row, text="✕", width=2,
                   command=lambda cc=c: self._remove(cc)).grid(row=0, column=8, padx=(4, 0))

        # Situational modifier — a single net value (e.g. -5 mounted vs. mounted,
        # +5 mounted vs. foot, -2 shield penalty, summed by the GM) applied
        # automatically to every characteristic/skill roll below until changed.
        tk.Label(row, text="Mod", font=self.norm_font, fg=fg).grid(
            row=0, column=9, padx=(10, 2))
        mod_fg = "#8b1a1a" if c.modifier < 0 else ("#0a6b3b" if c.modifier > 0 else fg)
        mv = tk.StringVar(value=f"{c.modifier:+d}" if c.modifier else "0")
        me = tk.Entry(row, width=4, justify="center", textvariable=mv,
                      fg=mod_fg, font=self.norm_font)
        me.grid(row=0, column=10)
        me.bind("<Return>", lambda e, cc=c, w=mv: self._set_modifier(cc, w.get()))
        me.bind("<FocusOut>", lambda e, cc=c, w=mv: self._set_modifier(cc, w.get()))

        # Clickable stat line: every number is a roll link (§7, §8). Characteristics,
        # attack skill values, attack damage and skills are all clickable tokens.
        self._build_stat_line(row, c, down)

        # Flavour line: the armour worn and this combatant's own distinctive
        # look — so the GM can vividly describe them. The shared type description
        # lives once in the Descriptions panel, not repeated on every row. (§7)
        arm = f"Armour: {c.describe_armour()}"
        looks = c.describe_looks()
        bits = [b for b in (arm, f"Looks: {looks}" if looks else "") if b]
        flavour = tk.Label(row, text="   ·   ".join(bits), anchor="w", justify="left",
                           wraplength=740, font=self.flavour_font,
                           fg=("#aaa" if down else "#555"))
        flavour.grid(row=2, column=0, columnspan=12, sticky="w", padx=(6, 0), pady=(0, 2))
        # Wrap flavour text to the current row width so it uses the space and never clips.
        row.bind("<Configure>",
                 lambda e, lbl=flavour: lbl.configure(wraplength=max(300, e.width - 12)))

    def _build_stat_line(self, row, c, down):
        """A read-only Text widget whose numbers are click-to-roll links."""
        # width=1 stops the Text's 80-char default from forcing the whole row
        # wider than the viewport (which clipped the trailing skills); sticky="ew"
        # then stretches it to the real width and wrap="word" flows onto more lines.
        txt = tk.Text(row, wrap="word", height=1, width=1, borderwidth=0, cursor="",
                      highlightthickness=0, background=self.frame_bg,
                      font=self.stat_font, spacing1=1, spacing3=1)
        txt.grid(row=1, column=0, columnspan=12, sticky="ew", padx=(6, 0))
        plain_fg = "#aaa" if down else "#333"
        txt.tag_configure("plain", foreground=plain_fg)

        def plain(text):
            txt.insert("end", text, "plain")

        def link(text, callback):
            self._link_seq += 1
            tag = f"lnk{self._link_seq}"
            txt.tag_configure(tag, foreground=("#9ab" if down else "#1a5fb4"),
                              underline=1)
            txt.tag_bind(tag, "<Button-1>", lambda e, cb=callback: cb())
            txt.tag_bind(tag, "<Enter>", lambda e: txt.configure(cursor="hand2"))
            txt.tag_bind(tag, "<Leave>", lambda e: txt.configure(cursor=""))
            txt.insert("end", text, (tag,))

        ch = c.characteristics
        for j, k in enumerate(("SIZ", "DEX", "STR", "CON", "APP")):
            if j:
                plain("  ")
            plain(f"{CHAR_FULL[k]} ")
            link(str(ch[k]), lambda cc=c, kk=k: self._roll_char(cc, kk))

        plain("   ·   ")
        for j, atk in enumerate(c.attacks):
            if j:
                plain(",  ")
            plain(f"{atk['weapon']} ")
            link(str(atk["value"]), lambda cc=c, a=atk: self._roll_attack(cc, a))
            plain(" (")
            link(atk["damage"], lambda cc=c, a=atk: self._roll_attack_damage(cc, a))
            plain(")")

        if c.skills:
            plain("   ·   Skills: ")
            for j, (name, value) in enumerate(c.skills.items()):
                if j:
                    plain(", ")
                plain(f"{name} ")
                link(str(value), lambda cc=c, nm=name, v=value: self._roll_named_skill(cc, nm, v))

        plain(f"   ·   Major Wound {c.major_wound}")
        if c.morale_minimum:
            # Battle-card datum: the conroi's Minimum Morale to engage this
            # Encounter (a Battle-system stat), not an individual foe's morale.
            plain(f", Min Morale to engage {c.morale_minimum}")

        txt.configure(state="disabled")
        txt.bind("<Configure>", lambda e, t=txt: self._fit_text_height(t, e.width))

    def _fit_text_height(self, txt, width):
        """Grow/shrink a stat-line Text to fit its wrapped content.

        Wrapped display lines can only be counted once the widget is tall enough
        to lay them all out — at height=1 the overflow (e.g. the trailing skills)
        stays hidden, and Tk's ``count -displaylines``/``-ypixels`` under-report
        it. So briefly give the widget room and walk ``dlineinfo`` (which reports
        actually-laid-out display lines), then set the real line count.

        Keyed on width: the height changes made here fire their own <Configure>
        but never change the width, so the guard skips them and avoids a loop.
        """
        if getattr(txt, "_fit_width", None) == width:
            return
        txt._fit_width = width
        txt.configure(height=30)          # room to lay out every wrapped line
        txt.update_idletasks()
        n = 0
        idx = "1.0"
        while txt.dlineinfo(idx) is not None:
            n += 1
            nxt = txt.index(f"{idx} + 1 display line")
            if txt.compare(nxt, "==", idx) or txt.compare(nxt, ">", "end - 1c"):
                break
            idx = nxt
        txt.configure(height=max(1, n))

    # -- actions -----------------------------------------------------------

    def _log(self, line):
        self.log.add(line)
        self._dirty = True
        self.log_text.configure(state="normal")
        self.log_text.insert("end", self.log.entries[-1] + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _sync_notes(self):
        self.log.gm_notes = self.notes_text.get("1.0", "end").rstrip("\n")

    def _apply_hp(self, c, text):
        """Apply an HP delta: '-10' = take 10 damage, '5' = heal 5."""
        text = text.strip().lstrip("+")
        try:
            delta = int(text)
        except (TypeError, ValueError):
            self._refresh_rows()
            return
        if delta == 0:
            self._refresh_rows()
            return
        old, msg = c.apply_hp(delta)
        self._log(f"{c.log_name}: {old} → {c.cur_hp} Hit Points ({delta:+d}){msg}")
        self._refresh_rows()

    def _engage(self, c, name):
        name = name.strip()
        if name == c._engaged_logged:
            return
        c.engaged_with = name
        c._engaged_logged = name
        if name:
            # Note the foe's specific look on the engagement line so the GM can
            # describe who this character is fighting at a glance.
            looks = c.describe_looks()
            detail = f" — {looks}" if looks else ""
            self._log(f"{c.display_name} engaged with {name}{detail}")
        else:
            self._log(f"{c.display_name} no longer engaged")

    def _toggle_down(self, c):
        # Knock out <-> revive (unconscious). Kept separate from the fled flag so
        # 'down' also covering fled doesn't flip the wrong way.
        if c.status in ("unconscious", "dead"):
            c._out = None
            self._log(f"{c.log_name} brought back up")
        else:
            c._out = "unconscious"
            self._log(f"{c.log_name} knocked out (unconscious)")
        self._refresh_rows()

    def _toggle_fled(self, c):
        """Mark a fleeing foe as no longer active/tracked (or resume tracking)."""
        if c.status == "fled":
            c._out = None
            self._log(f"{c.log_name} resumes the fight — active again")
        else:
            c._out = "fled"
            self._log(f"{c.log_name} flees the field — no longer active")
        self._refresh_rows()

    def _roll_ransom(self, c):
        if c.ransom:
            self._log(roll_ransom(c)[1])

    def _surrender_check(self, c):
        """The rulebook Surrender check (see core.combat.surrender_check)."""
        roll, outcome, line = surrender_check(c)
        self._log(line)
        self.set_status(f"{c.display_name} Valorous {skill_display(c.valorous)}: "
                        f"{roll} — {SURRENDER_RESULTS[outcome]}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def on_add_round_note(self):
        text = self.round_note.get().strip()
        if text:
            self._log(f"— {text}")
            self.round_note.delete(0, "end")

    def _set_modifier(self, c, text):
        """Apply a combatant's situational modifier (§ How-to). Blank/unparsable
        text is treated as 0 rather than rejected, so clearing the box just
        clears the modifier."""
        text = text.strip()
        try:
            value = int(text) if text not in ("", "+", "-") else 0
        except ValueError:
            value = 0
        if value == c.modifier:
            return
        c.modifier = value
        self._log(f"{c.display_name} situational modifier set to {value:+d}" if value
                  else f"{c.display_name} situational modifier cleared")
        self._refresh_rows()

    def _mod_shown(self, c, base, display=str):
        """Roll target plus a combatant's situational modifier: the effective
        value to roll against, and a label for the log/status line showing the
        breakdown (e.g. '15 -5 = 10') or just the base when unmodified."""
        if not c.modifier:
            return base, display(base)
        eff = base + c.modifier
        return eff, f"{display(base)} {c.modifier:+d} = {display(eff)}"

    def _roll_char(self, c, key):
        """Characteristic roll: pass/fail only (no crit/fumble — Core Ch.2)."""
        eff, shown = self._mod_shown(c, c.characteristics[key])
        roll = random.randint(1, 20)
        outcome = "success" if roll <= eff else "failure"
        label = CHAR_FULL[key]
        self._log(f"{c.log_name} rolls {label} ({shown}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {label} {shown}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_named_skill(self, c, name, value):
        eff, shown = self._mod_shown(c, value, display=skill_display)
        roll, outcome = resolve_skill(eff)
        self._log(f"{c.log_name} rolls {name} ({shown}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {name} {shown}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_attack(self, c, atk):
        weapon = atk["weapon"]
        eff, shown = self._mod_shown(c, atk["value"], display=skill_display)
        roll, outcome = resolve_skill(eff)
        self._log(f"{c.log_name} rolls {weapon} ({shown}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {weapon} {shown}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_attack_damage(self, c, atk):
        weapon = atk["weapon"]
        choice = ask_damage_mode(
            self, f"{c.display_name}'s {weapon} ({atk['damage']}) — resolve damage:")
        if choice is None:
            return
        critical, rebated = choice
        total, breakdown = roll_damage(atk["damage"], critical=critical, rebated=rebated)
        self._log(f"{c.log_name} {weapon} damage: {breakdown}")
        self.set_status(f"{c.display_name} {weapon} damage: {total}", "#1a5fb4")

    def _toggle_promote(self, c):
        if c.elite:
            c.demote()
            self._log(f"{c.display_name} demoted to a common {c.type}")
        else:
            self.encounter.promote(c)
            self._log(f"{c.label} promoted to {c.promotion_title} (elite)")
        self._refresh_rows()

    def _remove(self, c):
        self.encounter.remove(c)
        self._log(f"{c.display_name} removed from the encounter")
        self._refresh_rows()

    def on_generate(self):
        theme = self.theme_var.get()
        if not theme:                      # nothing picked — fall back to a lone match
            if len(getattr(self, "_enc_keys", [])) == 1:
                theme = self._enc_keys[0]
            else:
                self.set_status("Search, then select an encounter to launch.", "#a33")
                return
        self.encounter.generate_from_theme(theme, self.players_var.get())
        names = ", ".join(c.display_name for c in self.encounter.combatants)
        self._log(f"Launched '{theme}' for {self.players_var.get()} players: {names}")
        self._refresh_rows()
        self.set_status(f"Launched '{theme}' — {len(self.encounter.combatants)} combatants.",
                        "#2a7d2a")

    def refresh_choices(self):
        """Re-populate the encounter search list and Add-combatant dropdown
        (alphabetical) so encounters/adversaries created or edited in other tabs
        appear here without restarting the app. Current selections are left untouched."""
        self._refresh_encounter_list()
        self.add_combo["values"] = alpha(self.encounter.templates)

    # Kept for the Encounter Creator's Send-to-tracker bridge.
    refresh_themes = refresh_choices

    def run_definition(self, defn, n_players, name=""):
        """Generate a live encounter from a definition (Send-to-tracker bridge)."""
        self.encounter.generate_from_definition(defn, n_players)
        names = ", ".join(c.display_name for c in self.encounter.combatants)
        self._log(f"Generated '{name or defn.get('name', 'encounter')}' "
                  f"for {n_players} players: {names}")
        if defn.get("description", "").strip():
            self._log(f"  {defn['description'].strip()}")
        if defn.get("notes", "").strip():
            self._log(f"  GM notes: {defn['notes'].strip()}")
        self._refresh_rows()
        self.set_status(f"Generated {len(self.encounter.combatants)} combatants.", "#2a7d2a")

    def on_add(self):
        t = self.add_var.get()
        if t in self.encounter.templates:
            c = self.encounter.add_one(t)
            self._log(f"Added {c.display_name}")
            self._refresh_rows()

    def on_clear(self):
        """Start a new session: clears combatants, the log, and GM notes."""
        self._sync_notes()
        if self._dirty and (self.log.entries or self.log.gm_notes.strip()):
            ans = messagebox.askyesnocancel(
                "Start a new encounter",
                "Save the current combat log and GM notes before clearing?\n\n"
                "Yes = save first\nNo = discard\nCancel = go back")
            if ans is None:
                return
            if ans and not self.on_save_log():
                return  # save cancelled -> keep everything
        self.encounter.clear()
        self.log.clear()
        self.log.gm_notes = ""
        self._dirty = False
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.notes_text.delete("1.0", "end")
        self.round_note.delete(0, "end")
        self._refresh_rows()
        self.set_status("Cleared — ready for a new encounter.", "#1a5fb4")

    def on_copy_log(self):
        self._sync_notes()
        self.clipboard_clear()
        self.clipboard_append(self.log.to_markdown(self.encounter.combatants))
        self.update()
        self.set_status("Copied combat log to clipboard.", "#1a5fb4")

    def on_save_log(self):
        """Save the log to a file. Returns True on success, False if cancelled."""
        self._sync_notes()
        default = f"pendragon-encounter-{datetime.date.today().isoformat()}.md"
        path = filedialog.asksaveasfilename(
            title="Save combat log", defaultextension=".md", initialfile=default,
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")])
        if not path:
            return False
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log.to_markdown(self.encounter.combatants))
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return False
        self._dirty = False
        self.set_status(f"Saved combat log to {path}", "#2a7d2a")
        return True
