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

from rules import roll_expr, _rhu


# ---------------------------------------------------------------------------
# Combat resolution (rulebook: d20 roll-under; crit = exact; fumble = nat 20)
# ---------------------------------------------------------------------------

def _alpha(names):
    """Case-insensitive alphabetical list of the keys in a names mapping."""
    return sorted(names, key=str.casefold)


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


def resolve_skill(value):
    """Roll d20 against a skill value. Returns (roll, outcome).

    Core Rulebook Ch.2 'The Critical Bonus' (printed pp.30-31): a value over 20
    is written 20 (+x) where x = value - 20 is a *critical bonus* added to the
    die roll. A Statistic of 20 or more therefore cannot fail or fumble, and
    criticals on any natural roll >= 20 - x. So Sword 22 (i.e. 20 (+2))
    criticals on 18-20 and never fails. At or below 20: a critical is an exact
    roll, a natural 20 is a fumble, otherwise roll-under succeeds.
    """
    roll = random.randint(1, 20)
    if value >= 20:
        crit_floor = 20 - (value - 20)   # 20 -> 20; 22 -> 18; 25 -> 15
        return roll, ("critical" if roll >= crit_floor else "success")
    if roll == 20:
        return roll, "fumble"
    if roll == value:
        return roll, "critical"
    if roll < value:
        return roll, "success"
    return roll, "failure"


def skill_display(value):
    """Pendragon notation for a skill/trait value: '20 (+2)' once it exceeds 20."""
    return f"20 (+{value - 20})" if value > 20 else str(value)


CRITICAL_BONUS = "4D6"  # a critical hit adds a flat +4D6 (Core Ch.7, Table 7.1)

# Fallback Valorous for the Surrender check when a foe lists no traits
# (e.g. battle-card conrois). A middling courage the GM can override.
DEFAULT_VALOROUS = 13


def roll_damage(damage_expr, critical=False, rebated=False):
    """Roll weapon damage.

    ``critical`` — a critical hit: adds a flat +4D6 (Core Ch.7, Table 7.1).
    ``rebated``  — blunted/tournament weapon: halve the result, rounded up.

    The two combine: a rebated critical adds +4D6 and then halves. Returns
    ``(total, breakdown)``.
    """
    base = roll_expr(damage_expr)
    total = base
    breakdown = f"{damage_expr} = {base}"
    if critical:
        bonus = roll_expr(CRITICAL_BONUS)
        total += bonus
        breakdown += f"  +critical {CRITICAL_BONUS} = {bonus}"
    if rebated:
        if critical:
            breakdown += f"  =  {total}"
        total = (total + 1) // 2
        breakdown += f"  rebated ½  ->  {total}"
    elif critical:
        breakdown += f"  ->  {total}"
    return total, breakdown


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


def _to_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def resolve_roster(defn, n_players):
    """Resolve an encounter definition's roster to concrete counts.

    Scaling lives on each roster line: with ``per_player`` true the line's
    ``count`` is a multiplier of the party size (e.g. 1.5 × players), otherwise
    ``count`` is a fixed integer. Returns a list of ``(adversary, n, promote)``.

    Legacy definitions — a global ``scaling`` block with lines whose ``count``
    is the string ``"per_player"`` — are still understood.
    """
    scaling = defn.get("scaling", {})
    legacy_factor = scaling.get("per_player", 1.0)
    if scaling.get("mode", "per_player") != "per_player":
        legacy_factor = 1.0  # legacy fixed-count encounter
    out = []
    for line in defn.get("roster", []):
        adv = line.get("adversary")
        if not adv:
            continue
        count = line.get("count", 1)
        if "per_player" in line:                    # new self-scaling line
            if line["per_player"]:
                n = max(1, round(_to_float(count, 1.0) * n_players))
            else:
                n = max(0, _to_int(count, 0))
        elif count == "per_player":                 # legacy global-scaled line
            n = max(1, round(n_players * legacy_factor))
        else:                                       # legacy fixed line
            n = max(0, _to_int(count, 0))
        if n:
            out.append((adv, n, bool(line.get("promote"))))
    return out


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
        # A named adversary (a specific NPC) reads distinctly in the tracker,
        # much like a promoted champion.
        self.named = template.get("kind") == "named"

        ch = template["characteristics"]
        app_raw = ch.get("APP", "2D6+3")  # battle-card foes list no APP
        app = roll_expr(app_raw) if isinstance(app_raw, str) else app_raw
        self.characteristics = {
            "SIZ": ch["SIZ"], "DEX": ch["DEX"], "STR": ch["STR"],
            "CON": ch["CON"], "APP": app,
        }

        self.attacks = copy.deepcopy(template["attacks"])
        self.skills = dict(template.get("skills", {}))
        self.traits = dict(template.get("traits", {}))  # e.g. Valorous, for Surrender
        # Valorous drives the Surrender check; battle-card conrois list no traits,
        # so fall back to a middling courage the GM can adjust.
        self.valorous = self.traits.get("Valorous", DEFAULT_VALOROUS)
        self.notes = template.get("notes", "")
        self.armour_desc = template.get("armour_desc", "")
        self.culture = template.get("culture", "")
        self.religion = template.get("religion", "")
        self.category = template.get("category", "human")  # human/beast/monster/fae
        self.feature = ""   # distinctive physical traits (rolled by Encounter)
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
        self._out = None           # override: None / "unconscious" / "dead" / "fled"
        self._engaged_logged = ""  # last engaged-with value written to the log

    # -- status ------------------------------------------------------------

    @property
    def status(self):
        if self.cur_hp <= 0 or self._out == "dead":
            return "dead"
        if self._out == "fled":            # left the field — no longer tracked
            return "fled"
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
        """A short describable look: the rolled distinctive physical traits."""
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
        # Pendragon rounds derived stats half-up (0.5+ up); Python's round() uses
        # banker's rounding, which would round e.g. 22.5 HP or 6.5 Unconscious down.
        self.max_hp = _rhu(self.max_hp * mult)
        self.cur_hp = _rhu(self.cur_hp * mult)
        self.unconscious = max(1, _rhu(self.max_hp / 4))
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
        # Humans get distinctive, period-appropriate physical traits (frame from
        # SIZ/STR, scars, woad tattoos for pagans/Saxons, the odd hair/eye detail),
        # joined with "; " so traits with internal commas stay legible. Beasts and
        # monsters get none — their flavour is their own description/notes.
        if c.category == "human":
            c.feature = "; ".join(self.rules.random_physical_traits(
                siz=c.characteristics["SIZ"], str_=c.characteristics["STR"],
                culture=c.culture, religion=c.religion, n=random.choice([2, 2, 3])))
        c.eyes = ""
        self.combatants.append(c)
        return c

    def remove(self, combatant):
        if combatant in self.combatants:
            self.combatants.remove(combatant)

    def promote(self, combatant):
        combatant.promote(self.promotion_cfg)

    def generate_from_theme(self, theme_name, n_players):
        return self.generate_from_definition(self.themes[theme_name], n_players)

    def generate_from_definition(self, defn, n_players):
        """Build combatants from an encounter definition.

        Supports the new explicit roster shape (``roster`` + ``scaling`` +
        optional ``leader`` block) and the legacy pool shape (``core`` pool +
        ``per_player`` + ``leader`` name).
        """
        self.clear()
        if "roster" in defn:
            for adv, count, promote in resolve_roster(defn, n_players):
                if adv not in self.templates:
                    continue
                for _ in range(count):
                    c = self.add_one(adv)
                    if promote:
                        self.promote(c)
            leader = defn.get("leader")
            if isinstance(leader, dict) and leader.get("adversary") in self.templates:
                c = self.add_one(leader["adversary"])
                if leader.get("promote", True):
                    self.promote(c)
        else:  # legacy random-pool theme
            core = defn.get("core", list(self.templates))
            count = max(1, round(n_players * defn.get("per_player", 1.0)))
            for _ in range(count):
                self.add_one(random.choice(core))
            leader = defn.get("leader")
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
        adversaries = _alpha(self.encounter.templates)
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
                "skill)."
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
        for name in _alpha(self.encounter.themes):
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
        row.columnconfigure(9, weight=1)

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
        flavour.grid(row=2, column=0, columnspan=10, sticky="w", padx=(6, 0), pady=(0, 2))
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
        txt.grid(row=1, column=0, columnspan=10, sticky="ew", padx=(6, 0))
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
        if not c.ransom:
            return
        roll = random.randint(1, 6)
        row = next((r for r in c.ransom if r["min"] <= roll <= r["max"]), None)
        if row:
            self._log(f"{c.log_name} ransom (1D6={roll}): {row['type']} — {row['amount']}")
        else:
            self._log(f"{c.log_name} ransom (1D6={roll}): none")

    # Outcomes of the unopposed Valorous roll (GM Handbook Ch.6, Surrender —
    # gm.battle.battlefield-position-and-surrender, pp.131-132).
    _SURRENDER = {
        "critical": "fights on until dead or unconscious",
        "success": "holds — fights one more round, then checks again",
        "failure": "attempts to FLEE — resolve the escape, then Deactivate if it gets away",
        "fumble": "SURRENDERS — take prisoner / Roll ransom, or Deactivate",
    }

    def _surrender_check(self, c):
        """The rulebook Surrender check: a GM foe at half Hit Points or less rolls
        unopposed Valorous. This is the real 'does it flee?' mechanic — Pendragon
        has no per-foe morale roll (Morale is a conroi-level Battle stat)."""
        roll, outcome = resolve_skill(c.valorous)
        shown = skill_display(c.valorous)
        result = self._SURRENDER[outcome]
        note = "" if c.cur_hp * 2 <= c.max_hp else \
            "  (note: the check normally applies only at ½ Hit Points or less)"
        self._log(f"{c.log_name} surrender check — Valorous {shown}: "
                  f"{roll} — {outcome.upper()}: {result}{note}")
        self.set_status(f"{c.display_name} Valorous {shown}: {roll} — {result}",
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
        shown = skill_display(value)
        self._log(f"{c.log_name} rolls {name} ({shown}): {roll} — {outcome.upper()}")
        self.set_status(f"{c.display_name} {name} {shown}: rolled {roll} — {outcome}",
                        OUTCOME_COLOR.get(outcome, "#000"))

    def _roll_attack(self, c, atk):
        weapon = atk["weapon"]
        roll, outcome = resolve_skill(atk["value"])
        shown = skill_display(atk["value"])
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
        self.add_combo["values"] = _alpha(self.encounter.templates)

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
