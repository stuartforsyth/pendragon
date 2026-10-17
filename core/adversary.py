"""Adversary stat blocks: pure model helpers (no UI).

Generic types (e.g. "Bandit") and named individuals live in one
``adversaries`` map in ``data/combat.json``. These helpers resolve weapon
damage, armour, NPC→adversary drafts, trait-pair balancing, and turn an
editor draft into a saved stat block (deriving human health from
characteristics; creatures keep their printed values).
"""

import random
import re

from core.rules import roll_expr

CHAR_ORDER = ("SIZ", "DEX", "STR", "CON", "APP")

# A default weapon per combat skill, used when seeding attacks from an NPC.
WEAPON_FOR_SKILL = {
    "Sword": "Sword", "Spear": "Spear", "Charge": "Lance", "Bow": "Self Bow",
    "Hafted": "Axe", "Two-Handed Hafted": "Great Axe", "Brawling": "Dagger",
    "Crossbow": "Light Crossbow",
}


# ---------------------------------------------------------------------------
# Model helpers (pure — no UI)
# ---------------------------------------------------------------------------

def _dice_count(expr):
    """Number of d6 in a damage string ('4d6' -> 4, '5D6+4' -> 5, '12' -> 0)."""
    m = re.match(r"\s*(\d+)\s*[dD]6", str(expr))
    return int(m.group(1)) if m else 0


def resolve_weapon_damage(wdef, base_damage):
    """The damage a weapon deals for a wielder whose Weapon Damage is base_damage.

    base_damage is a dice string like '4d6' (the adversary's derived Damage). Its
    die count is also the wielder's flat **Brawling Damage** — both equal
    (STR + SIZ) ÷ 6 (Core p.34). Handles the table's damage_base/damage_mod/
    damage_max model (Weapons Tables 8.1 & 8.2).
    """
    base = wdef.get("damage_base", "character")
    if base == "fixed":
        return wdef.get("damage_dice", str(base_damage))
    if base == "horse":
        return "Horse"
    flat = _dice_count(base_damage)
    m = re.match(r"\s*([+-])\s*(\d+)\s*[dD]6", wdef.get("damage_mod", "") or "")
    mod_dice = (1 if m.group(1) == "+" else -1) * int(m.group(2)) if m else 0
    if base == "brawling":
        # Brawling weapons (Dagger, Club, Javelin…) add their XD6 modifier to the
        # flat Brawling Damage number: Brawling +2D6 with Brawling 4 -> '2D6+4'
        # (Table 8.1) — NOT 6D6.
        if mod_dice <= 0:
            return str(max(1, flat))
        return f"{mod_dice}D6+{flat}" if flat else f"{mod_dice}D6"
    # character-based: dice = weapon-damage dice ± the modifier dice, then capped.
    n = flat + mod_dice
    cap = wdef.get("damage_max")
    if cap:
        n = min(n, _dice_count(cap))
    return f"{max(1, n)}D6"


def compute_armour(pieces, helmet, shield, combat):
    """(armor_points, shield_points) from selected body pieces + helmet + shield."""
    ap = sum(combat.get("armour_pieces", {}).get(p, {}).get("protection", 0)
             for p in pieces)
    if helmet:
        ap += combat.get("helmets", {}).get(helmet, {}).get("protection", 0)
    sp = combat.get("shields", {}).get(shield, {}).get("protection", 0) if shield else 0
    return ap, sp


def describe_armour(pieces, helmet, shield):
    """A readable armour description from the selection."""
    worn = list(pieces) + ([helmet] if helmet else [])
    desc = ", ".join(worn)
    if shield:
        desc = f"{desc} + {shield} shield" if desc else f"{shield} shield"
    return desc


def _match_shield(text, shield_names):
    t = text.strip().lower().replace("shield", "").strip()
    return shield_names.get(t, "")


def parse_armour_desc(desc, combat):
    """Derive (pieces, helmet, shield) from a free-text armour_desc.

    Legacy adversaries store armour only as text (e.g. "Haubergeon, aketon,
    open helm + kite shield") plus precomputed points; the editor needs the
    structured selection so the checkboxes/dropdowns reflect it.
    """
    pieces, helmet, shield = [], "", ""
    if not desc or desc.strip().lower() == "none":
        return pieces, helmet, shield
    desc = re.split(r"[;(]", desc)[0]  # drop trailing notes / parentheticals
    piece_names = {n.lower(): n for n in combat.get("armour_pieces", {})}
    helmet_names = {n.lower(): n for n in combat.get("helmets", {})}
    shield_names = {n.lower(): n for n in combat.get("shields", {})}
    body = desc
    if "+" in desc:
        body, shield_part = desc.split("+", 1)
        shield = _match_shield(shield_part, shield_names)
    for tok in re.split(r",|\band\b", body):
        t = tok.strip().lower()
        if not t:
            continue
        if t in piece_names:
            pieces.append(piece_names[t])
        elif t in helmet_names:
            helmet = helmet_names[t]
        else:
            s = _match_shield(t, shield_names)  # e.g. "Targe shield" in the body
            if s:
                shield = s
    return pieces, helmet, shield


def blank_adversary(kind="generic", category="human"):
    return {
        "kind": kind, "category": category, "source": "user",
        "name": "", "tier": "trained", "description": "",
        "characteristics": {"SIZ": 10, "DEX": 10, "STR": 10, "CON": 10, "APP": 10},
        "attacks": [],
        "armour": {"pieces": [], "helmet": "", "shield": ""},
        "health": {"hit_points": 20, "knockdown": 10, "major_wound": 10, "unconscious": 5},
        "other": {"movement": 10, "armor_points": 0, "shield": 0, "glory": 0, "healing_rate": 2},
        "skills": {}, "traits": {}, "passions": {},
        "armour_desc": "", "promotion_title": "Champion", "notes": "",
    }


def _npc_traits_map(pairs):
    """Keep the dominant side of each trait pair when it is notable (>= 13)."""
    out = {}
    for left, lval, right, rval in pairs:
        if lval >= rval and lval >= 13:
            out[left] = lval
        elif rval > lval and rval >= 13:
            out[right] = rval
    return out


def _npc_looks(r):
    a = r.get("appearance") or {}
    bits = [a.get("descriptor", "")]
    if a.get("features"):
        bits.append("; ".join(a["features"]))
    if a.get("eyes"):
        bits.append(f"{a['eyes']} eyes")
    return ", ".join(b for b in bits if b)


def draft_from_npc(r, combat):
    """Build a **named** human adversary draft from an NPC result dict (§6.1)."""
    adv = blank_adversary("named", "human")
    adv["name"] = r.get("full", "")
    adv["culture"] = r.get("culture", "")
    adv["religion"] = r.get("religion", "")
    adv["created_from_npc"] = True
    adv["description"] = _npc_looks(r)
    stats = r.get("stats") or {}
    if stats:
        adv["characteristics"] = {k: stats.get(k, 10) for k in CHAR_ORDER}
    d = r.get("derived") or {}
    base_damage = d.get("Damage", "1d6")
    adv["health"] = {
        "hit_points": d.get("Hit Points", 20), "knockdown": d.get("Knockdown", 10),
        "major_wound": d.get("Major Wound", 10), "unconscious": d.get("Unconscious", 5),
    }
    adv["other"] = {
        "movement": d.get("Move", 10), "armor_points": 0, "shield": 0,
        "glory": r.get("glory", 0), "healing_rate": d.get("Healing Rate", 2),
    }
    adv["skills"] = dict(r.get("skills") or {})
    adv["traits"] = _npc_traits_map(r.get("traits") or [])
    adv["passions"] = {n: v for n, v in (r.get("passions") or [])}
    weapons = combat.get("weapons", {})
    for skill, weapon in WEAPON_FOR_SKILL.items():
        if skill in adv["skills"] and weapon in weapons:
            adv["attacks"].append({
                "weapon": weapon, "skill": skill, "value": adv["skills"][skill],
                "damage": resolve_weapon_damage(weapons[weapon], base_damage),
            })
    return adv


def _map_to_text(m):
    return "\n".join(f"{k} {v}" for k, v in m.items())


def _text_to_map(s):
    """Parse 'Name value' lines into an ordered dict of {name: int}."""
    out = {}
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)[\s:]+(-?\d+)\s*$", line)
        if m:
            out[m.group(1).strip()] = int(m.group(2))
    return out


# ---------------------------------------------------------------------------
# Editor support: vocabularies, autorolled values, trait-pair balance, finalise
# ---------------------------------------------------------------------------

def skill_vocab(rules, combat):
    names = set()
    for info in rules.social_classes.values():
        names |= set(info.get("skills", {}))
    names |= {w.get("skill") for w in combat.get("weapons", {}).values() if w.get("skill")}
    return sorted(n for n in names if n)


def trait_vocab(rules):
    """Each trait with its balancing partner, e.g. 'Valorous (Cowardly)'."""
    opts = []
    for a, b in rules.trait_pairs:
        opts.append(f"{a} ({b})")
        opts.append(f"{b} ({a})")
    return sorted(opts)


def passion_vocab(rules):
    return sorted(rules.passion_starts)


def roll_skill_value():
    return roll_expr("2D6+5")                       # a competent 7–17


def roll_trait_value():
    return max(1, min(19, roll_expr("2D6+3")))      # rulebook base, 1–19


def roll_passion_value(rules, name):
    base = rules.passion_starts.get(name)
    if base is not None:
        return max(1, min(25, base + random.randint(-2, 3)))
    return max(1, min(20, roll_expr("2D6+8")))


def partner_of(rules, trait):
    for a, b in rules.trait_pairs:
        if trait == a:
            return b
        if trait == b:
            return a
    return None


def add_trait(rules, current, choice):
    """Value for a newly added trait: 20 - partner if the partner is listed,
    otherwise rolled. Returns (name, value, note) or None if already present."""
    name = choice.split(" (")[0].strip()
    if not name or name in current:
        return None
    partner = partner_of(rules, name)
    if partner and partner in current:
        return name, max(0, min(20, 20 - current[partner])), \
            f"balanced against {partner} {current[partner]}"
    return name, roll_trait_value(), "rolled"


def normalise_traits(rules, raw, snap):
    """Keep every listed trait pair summing to 20 without disturbing a score the
    user did not touch. ``raw`` is the edited {trait: value}, ``snap`` the
    values before the edit. Returns the balanced ordered dict.

    - A pre-existing score is never changed just because its partner was added
      or given an out-of-range value; the added/invalid side is recalculated.
    - A valid edit (0..20) to an existing score wins, and its partner follows.
    """
    if not raw:
        return {}
    order = list(raw)
    m = {n: max(0, min(20, raw[n])) for n in order}
    in_range = lambda x: 0 <= raw[x] <= 20  # noqa: E731
    handled = set()
    for n in order:
        if n in handled:
            continue
        p = partner_of(rules, n)
        if not p or p not in m:
            continue
        if (n in snap) != (p in snap):
            auth = n if n in snap else p
        elif n in snap and p in snap:
            n_ch, p_ch = snap[n] != raw[n], snap[p] != raw[p]
            if n_ch and not p_ch:
                auth = n if in_range(n) else p
            elif p_ch and not n_ch:
                auth = p if in_range(p) else n
            else:
                auth = n if order.index(n) < order.index(p) else p
        else:
            auth = n if order.index(n) < order.index(p) else p
        other = p if auth == n else n
        m[other] = max(0, min(20, 20 - m[auth]))
        handled.update((n, p))
    return {k: m[k] for k in order}


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


_DICE = re.compile(r"\d*[dD]\d+(\s*[+-]\s*\d+)?")


def _characteristic(v):
    """A whole number, or a dice expression kept as-is — battle-card foes list
    e.g. APP '1D6+5', rolled per combatant when the encounter is launched."""
    if isinstance(v, str) and _DICE.fullmatch(v.strip()):
        return v.strip().upper()
    return _int(v, 0)


def finalise(draft, rules, combat):
    """Turn an editor draft into a saved adversary stat block.

    Humans derive Hit Points/Move/etc. from characteristics and armour from
    worn pieces; creatures and battle-card foes keep their printed combat stats
    (never re-derived — that would turn a Dragon's 16d6/Move 65 into
    human-formula values, or a card's 31 Hit Points into 30). Fields the editor
    doesn't manage (battle-card Morale, Knight Value, ransom, per-player
    scaling…) are carried over from the draft untouched.
    """
    kind = draft.get("kind", "generic")
    category = draft.get("category", "human")
    adv = blank_adversary(kind, category)
    for key in ("name", "tier", "culture", "religion", "description"):
        adv[key] = str(draft.get(key, "") or "").strip()
    adv["tier"] = adv["tier"] or "trained"
    adv["promotion_title"] = str(draft.get("promotion_title") or "").strip() or "Champion"
    ch = draft.get("characteristics", {})
    adv["characteristics"] = {k: _characteristic(ch.get(k)) for k in CHAR_ORDER}
    numeric = {k: v if isinstance(v, int) else 0 for k, v in adv["characteristics"].items()}
    other_in = draft.get("other", {}) or {}
    health_in = draft.get("health", {}) or {}
    printed = category != "human" or bool(draft.get("battle_card"))
    if not printed:
        d = rules.derive_stats(numeric)
        adv["health"] = {"hit_points": d["Hit Points"], "knockdown": d["Knockdown"],
                         "major_wound": d["Major Wound"], "unconscious": d["Unconscious"]}
        arm = draft.get("armour", {}) or {}
        pieces = [p for p in arm.get("pieces", []) if p in combat.get("armour_pieces", {})]
        helmet, shield = arm.get("helmet", "") or "", arm.get("shield", "") or ""
        ap, sp = compute_armour(pieces, helmet, shield, combat)
        adv["armour"] = {"pieces": pieces, "helmet": helmet, "shield": shield}
        adv["armour_desc"] = describe_armour(pieces, helmet, shield)
        adv["other"] = {"movement": d["Move"], "armor_points": ap, "shield": sp,
                        "glory": _int(other_in.get("glory"), 0),
                        "healing_rate": d["Healing Rate"]}
    else:
        adv["health"] = {k: _int(health_in.get(k), 0)
                         for k in ("hit_points", "knockdown", "major_wound", "unconscious")}
        adv["armour"] = {"pieces": [], "helmet": "", "shield": ""}
        shield = _int(other_in.get("shield"), 0)
        if category == "human":     # battle card: keep the printed armour line
            adv["armour_desc"] = str(draft.get("armour_desc", "") or "").strip()
        else:
            adv["armour_desc"] = "Natural armour" + (" + shield" if shield else "")
        adv["other"] = {"movement": _int(other_in.get("movement")),
                        "armor_points": _int(other_in.get("armor_points")),
                        "shield": shield, "glory": _int(other_in.get("glory")),
                        "healing_rate": _int(other_in.get("healing_rate"))}
        if str(other_in.get("valorous_modifier", "")).strip() not in ("", "None"):
            adv["other"]["valorous_modifier"] = _int(other_in.get("valorous_modifier"))
    attacks = []
    for atk in draft.get("attacks", []) or []:
        weapon = str(atk.get("weapon", "")).strip()
        if not weapon:
            continue
        wdef = combat.get("weapons", {}).get(weapon, {})
        attacks.append({"weapon": weapon, "skill": wdef.get("skill", atk.get("skill") or weapon),
                        "value": _int(atk.get("value")),
                        "damage": str(atk.get("damage", "")).strip()})
    adv["attacks"] = attacks
    for key in ("skills", "traits", "passions"):
        m = draft.get(key, {}) or {}
        adv[key] = {str(k).strip(): _int(v) for k, v in m.items() if str(k).strip()}
    adv["notes"] = str(draft.get("notes", "") or "").strip()
    if draft.get("created_from_npc"):
        adv["created_from_npc"] = True
    for k, v in draft.items():
        if k not in adv:
            adv[k] = v
    for k, v in other_in.items():
        adv["other"].setdefault(k, v)
    return adv


def auto_generate(generator, culture, gender, social_class=None):
    """Combat-relevant fields rolled from a generated NPC (Auto-generate all).
    Returns (draft_fields, npc)."""
    r = generator.generate(culture, gender, social_class)
    return draft_from_npc(r, generator.rules.combat), r
