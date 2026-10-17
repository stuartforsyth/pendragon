"""Battle rules (GM Handbook ch. 6) as pure tables and functions.

Every rule the Battle mode applies lives here, UI-free and deterministic: the
web reducers call these on replay, so a battle rebuilt from its events always
comes out the same. Nothing here rolls dice — rolled numbers arrive as
arguments. Each rule cites its corpus id (``rules_corpus/``).

Departures from the book are labelled in their docstrings: *scenario rule*
(the Sword Campaign's multi-day battles) or *GM ruling* (the book is silent).
"""

from fractions import Fraction

from core.combat import resolve_roster
from core.rules import _rhu

OUTCOMES = ("critical", "success", "failure", "fumble")

# Tables 6.1 (size, turns, random Intensity), 6.6 (participation Glory) and the
# Battle Size Multiplier of Table 6.10. gm.battle.running-a-battle,
# gm.battle.after-the-battle, gm.battle.plunder-and-encounters.
SIZES = {
    "fight":    {"label": "Fight",         "turns": 1, "intensity": "1D6+2", "participation": 5,  "plunder_mult": None, "army_rolls": False},
    "skirmish": {"label": "Skirmish",      "turns": 3, "intensity": "2D6",   "participation": 5,  "plunder_mult": None, "army_rolls": False},
    "clash":    {"label": "Clash",         "turns": 5, "intensity": "2D6+1", "participation": 10, "plunder_mult": None, "army_rolls": True},
    "small":    {"label": "Small Battle",  "turns": 6, "intensity": "2D6+2", "participation": 20, "plunder_mult": 1,    "army_rolls": True},
    "medium":   {"label": "Medium Battle", "turns": 7, "intensity": "2D6+3", "participation": 30, "plunder_mult": 2,    "army_rolls": True},
    "large":    {"label": "Large Battle",  "turns": 8, "intensity": "3D6",   "participation": 45, "plunder_mult": 3,    "army_rolls": True},
    "huge":     {"label": "Huge Battle",   "turns": 8, "intensity": "3D6+1", "participation": 60, "plunder_mult": 4,    "army_rolls": True},
}

# ----------------------------------------------------------------- commanders

DEFAULT_BATTLE = "2D6+10"   # an unknown commander's Battle skill (gm.battle.running-a-battle)

# Table 6.2 (gm.battle.running-a-battle): ticklist for an NPC commander's roll.
TABLE_6_2 = [
    {"label": "Outnumber the enemy 1½:1", "mod": 2},
    {"label": "Outnumber the enemy 2:1", "mod": 5},
    {"label": "Outnumber the enemy 3:1", "mod": 7},
    {"label": "Outnumber the enemy 5:1", "mod": 10},
    {"label": "Outnumbered 1½:1", "mod": -2},
    {"label": "Outnumbered 2:1", "mod": -5},
    {"label": "Outnumbered 3:1", "mod": -7},
    {"label": "Outnumbered 5:1", "mod": -10},
    {"label": "Fighting in own Homeland", "mod": 5},
    {"label": "Last Stand (not with Homeland)", "mod": 5},
    {"label": "Scouts, ⅕ of KV (not with Homeland)", "mod": 5},
    {"label": "Fatigued (forced march, hot weather)", "mod": -5},
    {"label": "Disease or hunger", "mod": -5},
    {"label": "Multiple fractious commanders", "mod": -5},
]


def army_effects(side, outcome):
    """What an Army Commander roll does (gm.battle.running-a-battle).

    Friendly success/critical: turn 1 is a mounted charge; fumble: no charge and
    the whole army is −5 Battle on turn 1. Enemy success/critical: the GM may
    force one Encounter; enemy fumble: the conroi may negate one Encounter's
    Morale loss.
    """
    if side == "friendly":
        if outcome in ("critical", "success"):
            return {"first_charge": True}
        if outcome == "fumble":
            return {"first_charge": False, "minus5": True}
        return {"first_charge": False}
    if outcome in ("critical", "success"):
        return {"force_token": True}
    if outcome == "fumble":
        return {"negate_token": True}
    return {}


# ---------------------------------------------------------------- the charge

def charge_opportunity(outcome, engaged_last):
    """Table 6.3, Mounted Charge Opportunity (gm.battle.fighting-the-battle)."""
    if outcome == "fumble":
        return "enemy_charge"
    if outcome == "critical":
        return "may_charge" if engaged_last else "may_charge_plus5"
    if outcome == "success" and not engaged_last:
        return "may_charge"
    return "no_charge"


def charge_line(result, mounted):
    """One knight's line for a charge result. Only mounted knights can charge;
    a knight on foot facing an enemy charge gives the enemy +5 Height and may
    Set Spear (gm.battle.fighting-the-battle, core.combat.action-set-spear)."""
    if result == "enemy_charge":
        return "Enemy knights charge!" if mounted else "Charged on foot — enemy +5 Height; Set Spear possible"
    if not mounted:
        return "On foot — no charge"
    return {"may_charge_plus5": "Charges +5", "may_charge": "May charge"}.get(result, "No charge")


# ----------------------------------------------------------- turn procedure

POSTURES = {
    "reckless": {"rounds": 3, "dice": "1D3", "sign": 1},
    "valorous": {"rounds": 2, "dice": None, "sign": 0},
    "prudent":  {"rounds": 1, "dice": "1D3", "sign": -1},
    "cowardly": {"rounds": 0, "dice": "1D6", "sign": -1},
}
FIRST_CHARGE_POSTURES = ("reckless", "valorous")
_DIE_MAX = {"1D3": 3, "1D6": 6}


def posture_delta(posture, amount=None, above_half=False):
    """Morale change from a knight's Posture (gm.battle.fighting-the-battle):
    Reckless +1D3, Valorous 0, Prudent −1D3, Cowardly −1D6 only if the knight
    is above half Hit Points. ``amount`` is the die the player rolled."""
    p = POSTURES[posture]
    if p["dice"] is None:
        return 0
    if posture == "cowardly" and not above_half:
        return 0
    amount = int(amount)
    if not 1 <= amount <= _DIE_MAX[p["dice"]]:
        raise ValueError(f"{p['dice']} can't roll {amount}")
    return p["sign"] * amount


def intensity_result(outcome):
    """The GM's Intensity roll: a success keeps the set Encounter (a critical
    doubles the foes), a fumble brings an Opportunity of the GM's choice, a
    failure lets the knights choose (gm.battle.fighting-the-battle)."""
    return {"critical": "doubled", "success": "stands",
            "fumble": "opportunity"}.get(outcome, "choose")


def barrage_rounds(outcome):
    """Rounds of missile barrage before contact, from the commander's Battle
    roll (gm.battle.fighting-the-battle)."""
    return {"critical": 0, "success": 1, "failure": 2, "fumble": 3}[outcome]


def reaches(rounds, extra, barrage):
    """Does a knight reach the archers? Only if their Posture's rounds (plus an
    Energetic+Valorous extra round) outlast the barrage — the book's worked
    example (gm.battle.fighting-the-battle)."""
    return rounds + extra > barrage


def countercharge(first_turn_of_day, roll=None):
    """Lance-armed foes always countercharge on the first Battle Turn, later on
    a 1D6 roll of 1–2 (gm.battle.plunder-and-encounters). *Scenario rule:* in a
    multi-day battle each day's first turn counts as a first turn."""
    if first_turn_of_day:
        return True
    return roll in (1, 2)


# ------------------------------------------------------------- the melee

def height(foe_mounted, knight_mounted, override=None, attacks_horse=False):
    """Height Advantage as ``(foe_mod, knight_mod)``: +5/−5 reflexive in the
    taller combatant's favour (core.combat.combat-modifiers). A footman
    attacking a rider's horse loses the −5 but the rider keeps +5
    (core.combat.action-attack). ``override="none"`` cancels it, e.g. a
    two-handed spear against a rider."""
    if override == "none":
        return (0, 0)
    if foe_mounted and not knight_mounted:
        return (5, -5)
    if knight_mounted and not foe_mounted:
        return (0, 5) if attacks_horse else (-5, 5)
    return (0, 0)


def multiple_opponents(n):
    """−5 per opponent after the first (core.combat.multiple-opponents)."""
    return 0 if n <= 1 else -5 * (n - 1)


def mo_limit(attackers_mounted):
    """How many may attack one opponent: three on foot, two mounted — counted
    by the attackers' horses (core.combat.multiple-opponents)."""
    return 2 if attackers_mounted else 3


# ------------------------------------------------------------ knight value

_KV_GLYPHS = {"½": Fraction(1, 2), "¼": Fraction(1, 4), "¾": Fraction(3, 4),
              "⅛": Fraction(1, 8), "⅜": Fraction(3, 8), "⅓": Fraction(1, 3)}


def parse_kv(s):
    """A card's Knight Value ("1", "½", "⅛", "1/16", "3/4") as a Fraction
    (Table 6.4, gm.battle.after-the-battle). Blank is 0."""
    s = str(s or "").strip()
    if not s:
        return Fraction(0)
    if s in _KV_GLYPHS:
        return _KV_GLYPHS[s]
    if s[-1] in _KV_GLYPHS and s[:-1].isdigit():          # e.g. "1½"
        return int(s[:-1]) + _KV_GLYPHS[s[-1]]
    return Fraction(s)


def kv_total(kvs):
    return sum((parse_kv(k) if not isinstance(k, Fraction) else k for k in kvs), Fraction(0))


def kv_morale_gain(per_encounter):
    """Morale regained after Encounters: the KV of the foes defeated in each
    (gm.battle.fighting-the-battle). *GM ruling:* fractions round half up per
    Encounter."""
    return sum(_rhu(kv_total(kvs)) for kvs in per_encounter)


# ---------------------------------------------------------------- aftermath

OUTCOME_LABEL = {"decisive_victory": "Decisive Victory", "victory": "Victory",
                 "indecisive": "Indecisive", "defeat": "Defeat",
                 "decisive_defeat": "Decisive Defeat"}
OUTCOME_MULT = {"decisive_victory": Fraction(2), "victory": Fraction(3, 2),
                "indecisive": Fraction(1), "defeat": Fraction(3, 4),
                "decisive_defeat": Fraction(1, 2)}            # Table 6.7
LEADER_MULT = {"conroi": 2, "bataille": 3, "army": 5}          # Table 6.8


def outcome(enemy_kv, friendly_kv, outnumber="none"):
    """Victory or defeat from KV losses (gm.battle.after-the-battle): enemy ÷
    friendly, ×2 if we greatly outnumbered them, ×½ if they did us.
    *GM ruling:* with no friendly losses, any enemy loss is a Decisive Victory
    and none at all is Indecisive."""
    enemy_kv, friendly_kv = Fraction(enemy_kv), Fraction(friendly_kv)
    if friendly_kv == 0:
        return "decisive_victory" if enemy_kv > 0 else "indecisive"
    ratio = enemy_kv / friendly_kv * {"we": 2, "they": Fraction(1, 2)}.get(outnumber, 1)
    if ratio >= 4:
        return "decisive_victory"
    if ratio >= 2:
        return "victory"
    if ratio >= Fraction(1, 2):
        return "indecisive"
    if ratio >= Fraction(1, 4):
        return "defeat"
    return "decisive_defeat"


_LOSSES = {"critical": (0, 0), "success": (0, 10), "failure": (10, 10), "fumble": (30, 20)}


def conroi_losses(outcome_, n_gm_knights):
    """Table 6.5, Conroi Losses among GM knights riding with the conroi."""
    killed, captured = _LOSSES[outcome_]
    return {"killed": _rhu(n_gm_knights * killed / 100),
            "captured": _rhu(n_gm_knights * captured / 100)}


def participation_glory(size, days, outcome_, role=None):
    """Participation Glory (Tables 6.6–6.8): base by size × (outcome multiplier
    + leader multiplier — added, then applied). The leader multiplier counts
    only in battles larger than a Skirmish. *Scenario rule:* × days fought."""
    mult = OUTCOME_MULT[outcome_]
    if role and size not in ("fight", "skirmish"):
        mult += LEADER_MULT[role]
    return _rhu(SIZES[size]["participation"] * days * mult)


PLUNDER_BASE = {"feudal": Fraction(2), "inferior": Fraction(3, 2), "saxons": Fraction(1),
                "cymric": Fraction(1, 2), "picts_irish": Fraction(1, 4)}   # Table 6.9


def plunder(opponents, outcome_, decisive_roll=None, outnumber="none", role=None, size=None):
    """£ of plunder per knight (Tables 6.9–6.10), only after a (Decisive)
    Victory. A Decisive Victory adds +£2D3 (``decisive_roll``). Bataille and
    army leaders multiply by the Battle Size Multiplier; below a Small battle
    there is none, so they get the conroi commander's +⅓ instead."""
    if outcome_ not in ("victory", "decisive_victory"):
        return Fraction(0)
    p = PLUNDER_BASE[opponents]
    if outcome_ == "decisive_victory" and decisive_roll:
        p += decisive_roll
    p *= {"we": Fraction(1, 2), "they": 2}.get(outnumber, 1)
    size_mult = SIZES.get(size, {}).get("plunder_mult")
    if role in ("bataille", "army") and size_mult:
        p *= (3 if role == "bataille" else 10) * size_mult
    elif role:
        p *= Fraction(4, 3)
    return p


# -------------------------------------------------------------- Glory, Morale

DEFEATED = {"unconscious", "dead", "fled", "surrendered"}   # Table A.1


def is_defeated(status):
    """Defeated for Glory: surrendered, killed, disabled or driven from the
    fight (gm.glory-awards.combat-and-adventure, Table A.1)."""
    return status in DEFEATED


def glory_for(c):
    """A defeated foe's Glory (already raised by promotion)."""
    return int(getattr(c, "glory", 0) or 0)


def apply_morale(current, start, delta):
    """Morale never exceeds its starting value and never drops below 0
    (gm.battle.running-a-battle)."""
    return max(0, min(start, current + delta))


def morale_band(current, start):
    """The word on the players' Morale gauge."""
    if not start:
        return "Breaking"
    share = current / start
    if share > 0.75:
        return "Steady"
    if share > 0.5:
        return "Shaken"
    if share > 0.25:
        return "Bloodied"
    return "Breaking"


def forced_retire(morale, minimum):
    """The conroi must Retire to the Rear at Morale 0 or below the chosen
    Encounter's Minimum (gm.battle.running-a-battle,
    gm.battle.battlefield-position-and-surrender)."""
    return morale == 0 or morale < (minimum or 0)


# ------------------------------------------------------------ encounters

def scale_roster(defn, n_knights, doubled=False):
    """An Encounter's foes for the knights with the conroi; an Intensity
    critical doubles each line's resolved count (the leader stays single)."""
    return [(adv, n * 2 if doubled else n, promote)
            for adv, n, promote in resolve_roster(defn, n_knights)]


def _roster_cards(defn, adversaries):
    for line in defn.get("roster", []):
        card = adversaries.get(line.get("adversary"))
        if card:
            yield card


def default_morale(defn, adversaries):
    """A battle Encounter's default (Minimum, Loss): the highest card Minimum
    and the first card's Loss."""
    cards = list(_roster_cards(defn, adversaries))
    minimums = [c["morale_minimum"] for c in cards if c.get("morale_minimum") is not None]
    loss = next((c.get("other", {}).get("morale_loss") for c in cards
                 if c.get("other", {}).get("morale_loss")), "")
    return (max(minimums) if minimums else None, loss)


def mounted_charge_card(defn, adversaries):
    """Can this Encounter answer "Enemy knights charge you!"? Only mounted foes
    with lances (flagged mounted and countercharge)."""
    return any(c.get("mounted") and c.get("countercharge") for c in _roster_cards(defn, adversaries))


def has_countercharge(defn, adversaries):
    return any(c.get("countercharge") for c in _roster_cards(defn, adversaries))


def leader_default(commander_by_day):
    """The knight who commanded the most days (ties: the earliest), for the
    aftermath's leader multiplier."""
    counts, first = {}, {}
    for i, pid in enumerate(commander_by_day):
        if not pid or pid == "gm":
            continue
        counts[pid] = counts.get(pid, 0) + 1
        first.setdefault(pid, i)
    if not counts:
        return None
    return max(counts, key=lambda p: (counts[p], -first[p]))
