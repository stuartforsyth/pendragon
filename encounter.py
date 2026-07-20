#!/usr/bin/env python3
"""
Encounter Generator for the Pendragon app (human encounters).

Model + combat resolution + the "Encounter" notebook tab. Data comes from
``data/combat.json`` via ``rules.Rules.combat`` (see docs/encounter-generator-spec.md).
Reuses ``rules.roll_expr`` for all dice.
"""

import copy
import datetime
import random
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from rules import roll_expr


# ---------------------------------------------------------------------------
# Combat resolution (rulebook: d20 roll-under; crit = exact; fumble = nat 20)
# ---------------------------------------------------------------------------

def resolve_skill(value):
    """Roll d20 against a skill value. Returns (roll, outcome)."""
    roll = random.randint(1, 20)
    if value >= 20:
        return roll, ("critical" if roll == 20 else "success")
    if roll == 20:
        return roll, "fumble"
    if roll == value:
        return roll, "critical"
    if roll < value:
        return roll, "success"
    return roll, "failure"


def roll_damage(damage_expr, base_dice, critical):
    """Roll weapon damage; a critical adds the attacker's base Damage dice again."""
    base = roll_expr(damage_expr)
    if critical:
        bonus_expr = f"{base_dice}D6"
        bonus = roll_expr(bonus_expr)
        return base + bonus, f"{damage_expr} = {base}  +critical {bonus_expr} = {bonus}  ->  {base + bonus}"
    return base, f"{damage_expr} = {base}"


# ---------------------------------------------------------------------------
# Combatant
# ---------------------------------------------------------------------------

class Combatant:
    def __init__(self, type_name, template, label, hp_jitter=True):
        self.type = type_name
        self.label = label
        self.engaged_with = ""
        self.description = template.get("description", "")
        self.tier = template.get("tier", "")
        self.promotion_title = template.get("promotion_title", "Champion")

        ch = template["characteristics"]
        app_raw = ch.get("APP", "2D6+3")  # battle-card foes list no APP
        app = roll_expr(app_raw) if isinstance(app_raw, str) else app_raw
        self.characteristics = {
            "SIZ": ch["SIZ"], "DEX": ch["DEX"], "STR": ch["STR"],
            "CON": ch["CON"], "APP": app,
        }
        self.base_damage_dice = max(1, round((ch["STR"] + ch["SIZ"]) / 6))

        self.attacks = copy.deepcopy(template["attacks"])
        self.skills = dict(template.get("skills", {}))
        self.notes = template.get("notes", "")
        self.armour_desc = template.get("armour_desc", "")
        self.feature = ""   # a defining physical characteristic (rolled by Encounter)
        self.eyes = ""
        h, o = template["health"], template["other"]
        jitter = random.randint(-2, 2) if hp_jitter else 0
        self.max_hp = max(1, h["hit_points"] + jitter)
        self.cur_hp = self.max_hp
        self.knockdown = h["knockdown"]
        self.major_wound = h["major_wound"]
        self.unconscious = h["unconscious"]
        self.armor_points = o.get("armor_points", 0)
        self.shield = o.get("shield", 0)
        self.movement = o.get("movement", 0)
        self.glory = o.get("glory", 0)
        self.healing_rate = o.get("healing_rate", 0)

        # Battle-card extras (morale + ransom); harmless defaults otherwise.
        self.morale_minimum = template.get("morale_minimum")
        self.morale_loss = o.get("morale_loss", "")
        self.knight_value = o.get("knight_value", "")
        self.ransom = template.get("ransom")  # list of {min,max,type,amount} or None

        self.elite = False
        self._base = None          # snapshot for demotion
        self._out = None           # override: None / "unconscious" / "dead"
        self._engaged_logged = ""  # last engaged-with value written to the log

    # -- status ------------------------------------------------------------

    @property
    def status(self):
        if self.cur_hp <= 0 or self._out == "dead":
            return "dead"
        if self._out == "unconscious" or self.cur_hp < self.unconscious:
            return "unconscious"
        return "active"

    @property
    def down(self):
        return self.status != "active"

    @property
    def display_name(self):
        return f"{self.label} — {self.promotion_title}" if self.elite else self.label

    @property
    def log_name(self):
        """Name used in the log, noting who they're engaged with for readability."""
        if self.engaged_with.strip():
            return f"{self.display_name} ({self.engaged_with.strip()})"
        return self.display_name

    def armor_total(self):
        return self.armor_points + self.shield

    def describe_armour(self):
        """Armour and shield shown separately, plus the total. A GM needs the
        armour-only value because some hits bypass the shield."""
        if self.shield:
            breakdown = (f"{self.armor_points} armour + {self.shield} shield "
                         f"= {self.armor_total()} total")
        else:
            breakdown = f"{self.armor_points} armour, no shield"
        return f"{self.armour_desc} — {breakdown}" if self.armour_desc else breakdown

    def describe_looks(self):
        """A short describable look: defining feature + eye colour."""
        parts = [p for p in (self.feature,
                             f"{self.eyes} eyes" if self.eyes else "") if p]
        return ", ".join(parts)

    # -- promotion ---------------------------------------------------------

    def promote(self, cfg):
        if self.elite:
            return
        self._base = {
            "attacks": copy.deepcopy(self.attacks),
            "max_hp": self.max_hp, "cur_hp": self.cur_hp,
            "unconscious": self.unconscious, "armor_points": self.armor_points,
            "glory": self.glory,
        }
        for atk in self.attacks:
            atk["value"] += cfg.get("skill_bonus", 5)
            atk["damage"] = f"{atk['damage']}+{cfg.get('damage_bonus_dice', 1)}D6"
        mult = cfg.get("hp_multiplier", 1.5)
        self.max_hp = round(self.max_hp * mult)
        self.cur_hp = round(self.cur_hp * mult)
        self.unconscious = max(1, round(self.max_hp / 4))
        self.armor_points += cfg.get("armour_bonus", 0)
        self.glory *= cfg.get("glory_multiplier", 1)
        self.elite = True

    def demote(self):
        if not self.elite or not self._base:
            return
        self.attacks = self._base["attacks"]
        self.max_hp = self._base["max_hp"]
        self.cur_hp = min(self.cur_hp, self.max_hp)
        self.unconscious = self._base["unconscious"]
        self.armor_points = self._base["armor_points"]
        self.glory = self._base["glory"]
        self.elite = False
        self._base = None


# ---------------------------------------------------------------------------
# Encounter + log
# ---------------------------------------------------------------------------

class Encounter:
    def __init__(self, rules):
        self.rules = rules
        self.combat = rules.combat
        self.templates = self.combat["enemy_templates"]
        self.themes = self.combat.get("encounter_themes", {})
        self.promotion_cfg = self.combat.get("promotion", {})
        self.combatants = []
        self._counts = {}

    def clear(self):
        self.combatants = []
        self._counts = {}

    def add_one(self, type_name):
        template = self.templates[type_name]
        self._counts[type_name] = self._counts.get(type_name, 0) + 1
        label = f"{type_name} {self._counts[type_name]}"
        c = Combatant(type_name, template, label)
        # Roll a defining physical feature so identical combatants differ.
        c.feature = self.rules.random_appearance_feature()
        c.eyes = self.rules.random_eye_colour()
        self.combatants.append(c)
        return c

    def remove(self, combatant):
        if combatant in self.combatants:
            self.combatants.remove(combatant)

    def promote(self, combatant):
        combatant.promote(self.promotion_cfg)

    def generate_from_theme(self, theme_name, n_players):
        theme = self.themes[theme_name]
        self.clear()
        core = theme.get("core", list(self.templates))
        count = max(1, round(n_players * theme.get("per_player", 1.0)))
        for _ in range(count):
            self.add_one(random.choice(core))
        leader = theme.get("leader")
        if leader and leader in self.templates:
            self.promote(self.add_one(leader))
        return self.combatants


class CombatLog:
    def __init__(self):
        self.entries = []
        self.gm_notes = ""

    def add(self, line):
        stamp = datetime.datetime.now().strftime("%H:%M")
        self.entries.append(f"[{stamp}] {line}")

    def clear(self):
        self.entries = []

    def text(self):
        return "\n".join(self.entries)

    def to_markdown(self, combatants=None):
        today = datetime.date.today().isoformat()
        out = [f"# Encounter Log — {today}", ""]
        if combatants:
            out += ["## Combatants", ""]
            for c in combatants:
                eng = (f" — engaged with {c.engaged_with}"
                       if c.engaged_with.strip() else "")
                out.append(f"- {c.display_name} — Hit Points {c.cur_hp}/{c.max_hp} "
                           f"({c.status}){eng}")
                looks = c.describe_looks()
                out.append(f"    - Armour: {c.describe_armour()}"
                           + (f"; Looks: {looks}" if looks else ""))
            out.append("")
        out += ["## Events", ""]
        out.extend(self.entries or ["(no events logged)"])
        if self.gm_notes.strip():
            out += ["", "## GM Notes", "", self.gm_notes.rstrip()]
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# GUI — the Encounter tab
# ---------------------------------------------------------------------------

OUTCOME_COLOR = {
    "critical": "#1a7a1a", "success": "#2a7d2a",
    "failure": "#a33", "fumble": "#c00",
}

# Full characteristic names (spelled out rather than SIZ/DEX/STR/CON/APP).
CHAR_FULL = {
    "SIZ": "Size", "DEX": "Dexterity", "STR": "Strength",
    "CON": "Constitution", "APP": "Appeal",
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
        ttk.Label(setup, text="Encounter:").pack(side="left")
        self.theme_var = tk.StringVar(value=next(iter(self.encounter.themes), ""))
        ttk.Combobox(setup, textvariable=self.theme_var, width=20, state="readonly",
                     values=list(self.encounter.themes)).pack(side="left", padx=(4, 10))
        ttk.Button(setup, text="Generate encounter",
                   command=self.on_generate).pack(side="left")
        ttk.Button(setup, text="Clear", command=self.on_clear).pack(side="left", padx=(6, 0))

        addrow = ttk.Frame(self)
        addrow.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(addrow, text="Add combatant:").pack(side="left")
        self.add_var = tk.StringVar(value=next(iter(self.encounter.templates), ""))
        ttk.Combobox(addrow, textvariable=self.add_var, width=20, state="readonly",
                     values=list(self.encounter.templates)).pack(side="left", padx=(4, 6))
        ttk.Button(addrow, text="Add", command=self.on_add).pack(side="left")

        # How-to block: explain the per-row textboxes and click-to-roll, since the
        # tracker's controls aren't otherwise self-evident.
        howto = ttk.LabelFrame(self, text="How to use the tracker")
        howto.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(
            howto, justify="left", foreground="#444", font=("TkDefaultFont", 9),
            text=(
                "• engages — type who this enemy is fighting (e.g. a knight's name); it is logged.\n"
                "• HP change — type the total damage as a negative to subtract it, or healing as a\n"
                "   positive to add it, then press Apply or Enter. Example: an enemy on 28/28 takes\n"
                "   8 damage → type -8, Apply → 20/28. A single hit ≥ Constitution is a Major Wound.\n"
                "• Click any underlined stat number to roll it (characteristic, attack skill, damage, "
                "skill)."
            ),
        ).pack(anchor="w", padx=8, pady=4)

        # Scrollable combatant tracker.
        tracker = ttk.LabelFrame(self, text="Combatants")
        tracker.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        canvas = tk.Canvas(tracker, highlightthickness=0)
        vs = ttk.Scrollbar(tracker, orient="vertical", command=canvas.yview)
        self.rows_frame = ttk.Frame(canvas)
        self.rows_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

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

    def _refresh_rows(self):
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

        down = c.down
        name_font = self.down_font if down else (self.elite_font if c.elite else self.norm_font)
        fg = "#999" if down else ("#8a4b00" if c.elite else "#000")

        star = "★ " if c.elite else ""
        name = tk.Label(row, text=f"{star}{c.display_name}", width=22, anchor="w",
                        font=name_font, fg=fg)
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

        # Actions menu (promote/demote, knock out/revive, ransom, morale)
        mb = ttk.Menubutton(row, text="Actions ▾", width=9)
        menu = tk.Menu(mb, tearoff=0)
        menu.add_command(label="Demote" if c.elite else "Promote to champion",
                         command=lambda cc=c: self._toggle_promote(cc))
        menu.add_command(label="Revive" if c.down else "Knock out",
                         command=lambda cc=c: self._toggle_down(cc))
        if c.ransom:
            menu.add_command(label="Roll ransom",
                             command=lambda cc=c: self._roll_ransom(cc))
        if c.morale_minimum:
            menu.add_command(label="Morale check",
                             command=lambda cc=c: self._morale_check(cc))
        mb["menu"] = menu
        mb.grid(row=0, column=7, padx=(8, 0))
        ttk.Button(row, text="✕", width=2,
                   command=lambda cc=c: self._remove(cc)).grid(row=0, column=8, padx=(4, 0))

        # Clickable stat line: every number is a roll link (§7, §8). Characteristics,
        # attack skill values, attack damage and skills are all clickable tokens.
        self._build_stat_line(row, c, down)

        # Flavour line: the template's description, the armour worn, and a defining
        # look — so the GM can vividly describe the combatant. Readable size (§7).
        arm = f"Armour: {c.describe_armour()}"
        looks = c.describe_looks()
        bits = [b for b in (c.description, arm,
                            f"Looks: {looks}" if looks else "") if b]
        tk.Label(row, text="   ·   ".join(bits), anchor="w", justify="left",
                 wraplength=740, font=self.flavour_font,
                 fg=("#aaa" if down else "#555")
                 ).grid(row=2, column=0, columnspan=9, sticky="w", padx=(6, 0), pady=(0, 2))

    def _build_stat_line(self, row, c, down):
        """A read-only Text widget whose numbers are click-to-roll links."""
        txt = tk.Text(row, wrap="word", height=1, borderwidth=0, cursor="",
                      highlightthickness=0, background=self.frame_bg,
                      font=self.stat_font, spacing1=1, spacing3=1)
        txt.grid(row=1, column=0, columnspan=9, sticky="ew", padx=(6, 0))
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
            plain(f", Morale {c.morale_minimum}")

        txt.configure(state="disabled")
        txt.bind("<Configure>", lambda e, t=txt: self._fit_text_height(t))

    @staticmethod
    def _fit_text_height(txt):
        """Grow/shrink a Text widget to fit its wrapped content."""
        res = txt.count("1.0", "end-1c", "displaylines")
        if isinstance(res, tuple):
            res = res[0] if res else 1
        n = max(1, int(res or 1))
        if int(txt["height"]) != n:
            txt.configure(height=n)

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
        old = c.cur_hp
        c.cur_hp = min(old + delta, c.max_hp)
        msg = ""
        if delta < 0:  # took damage — the applied amount is the single blow
            dmg = -delta
            if dmg >= c.max_hp:
                c._out = "dead"
                msg = f"  — Mortal Wound! ({dmg} ≥ total Hit Points {c.max_hp}) — slain"
            elif dmg >= c.major_wound and c._out is None:
                c._out = "unconscious"
                msg = f"  — Major Wound! ({dmg} ≥ Constitution {c.major_wound}) — unconscious"
        else:  # healed
            if c._out == "unconscious" and c.cur_hp >= c.unconscious:
                c._out = None
                msg = "  — revived"
        tag = "" if msg else (f"  [{c.status}]" if c.down else "")
        self._log(f"{c.log_name}: {old} → {c.cur_hp} Hit Points ({delta:+d}){msg}{tag}")
        self._refresh_rows()

    def _engage(self, c, name):
        name = name.strip()
        if name == c._engaged_logged:
            return
        c.engaged_with = name
        c._engaged_logged = name
        if name:
            self._log(f"{c.display_name} engaged with {name}")
        else:
            self._log(f"{c.display_name} no longer engaged")

    def _toggle_down(self, c):
        if c.status == "active":
            c._out = "unconscious"
            self._log(f"{c.log_name} knocked out (unconscious)")
        else:
            c._out = None
            self._log(f"{c.log_name} brought back up")
        self._refresh_rows()

    def _roll_ransom(self, c):
        if not c.ransom:
            return
        roll = random.randint(1, 6)
        row = next((r for r in c.ransom if r["min"] <= roll <= r["max"]), None)
        if row:
            self._log(f"{c.log_name} ransom (1D6={roll}): {row['type']} — {row['amount']}")
        else:
            self._log(f"{c.log_name} ransom (1D6={roll}): none")

    def _morale_check(self, c):
        # Morale = d20 roll-under the unit's Morale value; fail = would flee.
        roll, outcome = resolve_skill(c.morale_minimum)
        result = "holds" if outcome in ("success", "critical") else "FLEES"
        self._log(f"{c.log_name} morale check ({c.morale_minimum}): {roll} — {result}")
        self.set_status(f"{c.display_name} morale {c.morale_minimum}: {roll} — {result}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def on_add_round_note(self):
        text = self.round_note.get().strip()
        if text:
            self._log(f"— {text}")
            self.round_note.delete(0, "end")

    def _roll_char(self, c, key):
        """Characteristic roll: pass/fail only (no crit/fumble — Core Ch.2)."""
        value = c.characteristics[key]
        roll = random.randint(1, 20)
        outcome = "success" if roll <= value else "failure"
        label = CHAR_FULL[key]
        self._log(f"{c.log_name} rolls {label} ({value}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {label} {value}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_named_skill(self, c, name, value):
        roll, outcome = resolve_skill(value)
        self._log(f"{c.log_name} rolls {name} ({value}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {name} {value}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_attack(self, c, atk):
        weapon = atk["weapon"]
        roll, outcome = resolve_skill(atk["value"])
        self._log(f"{c.log_name} rolls {weapon} ({atk['value']}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {weapon} {atk['value']}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_attack_damage(self, c, atk):
        weapon = atk["weapon"]
        crit = messagebox.askyesno(
            "Critical hit?",
            f"Was {c.display_name}'s {weapon} attack a critical hit?\n\n"
            "Yes adds the critical bonus dice.")
        total, breakdown = roll_damage(atk["damage"], c.base_damage_dice, crit)
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
        if not theme:
            return
        self.encounter.generate_from_theme(theme, self.players_var.get())
        names = ", ".join(c.display_name for c in self.encounter.combatants)
        self._log(f"Generated '{theme}' for {self.players_var.get()} players: {names}")
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
