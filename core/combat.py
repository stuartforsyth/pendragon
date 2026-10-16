"""Combat model: combatants, live encounters, encounter-definition rosters.

Pure logic shared by the web tracker and the Tk tab. Data comes from
``data/combat.json`` via ``Rules.combat``. A ``Combatant`` round-trips through
``to_dict``/``from_dict`` so the web app can snapshot one into a session event
and rebuild combat state by replaying events.
"""

import copy
import datetime
import random

from core.dice import resolve_skill, skill_display
from core.rules import roll_expr, _rhu

# Fallback Valorous for the Surrender check when a foe lists no traits
# (e.g. battle-card conrois). A middling courage the GM can override.
DEFAULT_VALOROUS = 13

# Full characteristic names (spelled out rather than SIZ/DEX/STR/CON/APP).
CHAR_FULL = {
    "SIZ": "Size", "DEX": "Dexterity", "STR": "Strength",
    "CON": "Constitution", "APP": "Appeal",
}
CHAR_ORDER = ("SIZ", "DEX", "STR", "CON", "APP")

# Outcomes of the unopposed Valorous roll (GM Handbook Ch.6, Surrender —
# gm.battle.battlefield-position-and-surrender, pp.131-132).
SURRENDER_RESULTS = {
    "critical": "fights on until dead or unconscious",
    "success": "holds — fights one more round, then checks again",
    "failure": "attempts to FLEE — resolve the escape, then Deactivate if it gets away",
    "fumble": "SURRENDERS — take prisoner / Roll ransom, or Deactivate",
}


def alpha(names):
    """Case-insensitive alphabetical list of the keys in a names mapping."""
    return sorted(names, key=str.casefold)


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
        self.id = ""            # assigned by Encounter / the web tracker
        self.side = "foe"       # "foe" or "party"
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

        # Situational modifier (mounted vs. foot, shield penalty, prone, etc.).
        # A single net value the GM sets per combatant; every characteristic,
        # attack-skill and named-skill roll for them applies it automatically
        # until it's changed or cleared back to 0.
        self.modifier = 0

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

    # -- state changes (shared by every UI) ---------------------------------

    def apply_hp(self, delta):
        """Apply an HP delta: negative = one blow of damage, positive = healing.

        Returns the log suffix describing any wound consequence: a blow of at
        least total Hit Points is a Mortal Wound (slain), one of at least
        Constitution a Major Wound (unconscious) — Core Ch.11,
        ``core.injury-health.states-of-health-and-wounds``.
        """
        old = self.cur_hp
        self.cur_hp = min(old + delta, self.max_hp)
        msg = ""
        if delta < 0:
            dmg = -delta
            if dmg >= self.max_hp:
                self._out = "dead"
                msg = f"  — Mortal Wound! ({dmg} ≥ total Hit Points {self.max_hp}) — slain"
            elif dmg >= self.major_wound and self._out is None:
                self._out = "unconscious"
                msg = (f"  — Major Wound! ({dmg} ≥ Constitution {self.major_wound})"
                       " — unconscious")
        elif self._out == "unconscious" and self.cur_hp >= self.unconscious:
            self._out = None
            msg = "  — revived"
        if not msg and self.down:
            msg = f"  [{self.status}]"
        return old, msg

    def set_out(self, out):
        """Override status: None (back up), 'unconscious', 'dead' or 'fled'."""
        self._out = out

    def wound_state(self):
        """A player-facing description of health that never reveals numbers."""
        status = self.status
        if status == "dead":
            return "Slain"
        if status == "fled":
            return "Fled"
        if status == "unconscious":
            return "Near death" if self.cur_hp <= 0 else "Unconscious"
        if self.cur_hp >= self.max_hp:
            return "Unhurt"
        if self.cur_hp * 2 > self.max_hp:
            return "Wounded"
        return "Badly wounded"

    def effective(self, base):
        """A roll target with this combatant's situational modifier applied."""
        return base + self.modifier

    # -- serialisation -------------------------------------------------------

    def to_dict(self):
        return copy.deepcopy(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        c = cls.__new__(cls)
        c.__dict__.update(copy.deepcopy(d))
        return c

    @classmethod
    def from_party(cls, member):
        """A player knight as a combatant (lightweight: tracking, not a sheet)."""
        hp = int(member.get("max_hp") or 0) or 1
        con = int(member.get("major_wound") or 0) or max(1, hp // 2)
        template = {
            "kind": "named", "category": "human",
            "characteristics": {k: member.get("characteristics", {}).get(k, 0)
                                for k in ("SIZ", "DEX", "STR", "CON", "APP")},
            "attacks": [], "skills": {}, "traits": {},
            "health": {"hit_points": hp, "knockdown": member.get("knockdown") or hp,
                       "major_wound": con,
                       "unconscious": int(member.get("unconscious") or 0) or max(1, _rhu(hp / 4))},
            "other": {"armor_points": int(member.get("armour") or 0),
                      "shield": int(member.get("shield") or 0),
                      "movement": int(member.get("move") or 0)},
            "armour_desc": member.get("armour_desc", ""),
            "notes": member.get("notes", ""),
        }
        c = cls(member.get("name", "Knight"), template, member.get("name", "Knight"),
                hp_jitter=False)
        c.characteristics["APP"] = template["characteristics"]["APP"]
        cur = member.get("cur_hp")
        if cur is not None and str(cur) != "":
            c.cur_hp = min(int(cur), c.max_hp)
        c.side = "party"
        c.party_id = member.get("id")
        c.player = member.get("player", "")
        return c

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
        self._seq = getattr(self, "_seq", 0) + 1
        c.id = f"c{self._seq}"
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


def surrender_check(c, roll=None):
    """The rulebook Surrender check: a foe at half Hit Points or less rolls
    unopposed Valorous (GM Handbook Ch.6). Returns (roll, outcome, line)."""
    roll, outcome = resolve_skill(c.valorous, roll)
    shown = skill_display(c.valorous)
    note = "" if c.cur_hp * 2 <= c.max_hp else \
        "  (note: the check normally applies only at ½ Hit Points or less)"
    line = (f"{c.log_name} surrender check — Valorous {shown}: "
            f"{roll} — {outcome.upper()}: {SURRENDER_RESULTS[outcome]}{note}")
    return roll, outcome, line


def roll_ransom(c, roll=None):
    """Roll 1D6 on a combatant's ransom table. Returns (roll, line)."""
    roll = random.randint(1, 6) if roll is None else roll
    row = next((r for r in c.ransom or [] if r["min"] <= roll <= r["max"]), None)
    if row:
        return roll, f"{c.log_name} ransom (1D6={roll}): {row['type']} — {row['amount']}"
    return roll, f"{c.log_name} ransom (1D6={roll}): none"
