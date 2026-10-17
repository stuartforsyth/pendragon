"""Adversary and encounter-definition libraries (the two creator tools).

Edits are written to the git-ignored working ``data/combat.json`` (never the
tracked baseline). Library edits are prep, not play, so they aren't logged.
"""

import json

from fastapi import APIRouter, Request

from core import adversary as A
from core import battle_def as BD
from core import battle as B
from core import examples as X
from core.dice import NotationError, roll_notation
from core.rules import example_combat_path
from core.combat import alpha
from core.encounter_def import blank_encounter, preview_lines, roster_threat, to_editable
from web.routes.common import bad, st, to_int

router = APIRouter()



def _advs(state):
    return state.combat_data.setdefault("adversaries", {})


def _encs(state):
    return state.combat_data.setdefault("encounters", {})


def _summary(key, a):
    cat = a.get("category", "human")
    return {"key": key, "kind": a.get("kind", "generic"), "category": cat,
            "tier": a.get("tier", ""), "description": a.get("description", ""),
            "hp": a.get("health", {}).get("hit_points"),
            "glory": a.get("other", {}).get("glory", 0),
            "source": a.get("source", "")}


# -- adversaries -------------------------------------------------------------

@router.get("/api/adversaries")
def list_adversaries(request: Request):
    advs = _advs(st(request))
    return {"adversaries": [_summary(k, advs[k]) for k in alpha(advs)]}


@router.get("/api/adversaries/meta")
def adversary_meta(request: Request):
    state = st(request)
    combat, rules = state.combat_data, state.rules
    return {
        "weapons": {k: {"skill": v.get("skill", k), "vs_mail": v.get("vs_mail", ""),
                        "through_shields": "strikes through shields" in v.get("advantage", "").lower(),
                        "advantage": v.get("advantage", "")}
                    for k, v in combat.get("weapons", {}).items()},
        "armour_pieces": {k: v.get("protection", 0) for k, v in combat.get("armour_pieces", {}).items()},
        "helmets": {k: v.get("protection", 0) for k, v in combat.get("helmets", {}).items()},
        "shields": {k: v.get("protection", 0) for k, v in combat.get("shields", {}).items()},
        "tiers": list(combat.get("tiers", {})) or ["rabble", "trained", "veteran", "elite"],
        "skills": A.skill_vocab(rules, combat), "traits": A.trait_vocab(rules),
        "passions": A.passion_vocab(rules),
        "cultures": state.generator.culture_names(), "classes": list(rules.social_classes),
        "religions": list(rules.religions),
        "categories": ["human", "beast", "monster", "fae"],
    }


@router.get("/api/adversaries/blank")
def blank(kind: str = "generic", category: str = "human"):
    return {"adversary": A.blank_adversary(kind, category)}


@router.get("/api/adversaries/{key}")
def get_adversary(request: Request, key: str):
    state = st(request)
    a = _advs(state).get(key)
    if a is None:
        bad("No such adversary", 404)
    a = dict(a)
    arm = a.get("armour") or {}
    if not (arm.get("pieces") or arm.get("helmet") or arm.get("shield")):
        pieces, helmet, shield = A.parse_armour_desc(a.get("armour_desc", ""), state.combat_data)
        a["armour"] = {"pieces": pieces, "helmet": helmet, "shield": shield}
    a.setdefault("name", key)
    return {"key": key, "adversary": a}


@router.put("/api/adversaries")
async def save_adversary(request: Request, body: dict):
    """Save a draft. ``original`` is the key being edited (None for new);
    ``overwrite`` must be true to replace a different existing entry."""
    state = st(request)
    adv = A.finalise(body.get("adversary") or {}, state.rules, state.combat_data)
    key, original = adv["name"], body.get("original")
    if not key:
        bad("Enter a name (named) or type name (generic) before saving")
    advs = _advs(state)
    if key in advs and key != original and not body.get("overwrite"):
        bad(f"An adversary named '{key}' exists", 409)
    if original and original != key and original in advs:
        del advs[original]
    advs[key] = adv
    path = state.save_combat_data()
    state.notify("library")
    return {"key": key, "adversary": adv, "path": path}


@router.delete("/api/adversaries/{key}")
async def delete_adversary(request: Request, key: str):
    state = st(request)
    if key not in _advs(state):
        bad("No such adversary", 404)
    del _advs(state)[key]
    state.save_combat_data()
    state.notify("library")
    return {"ok": True}


@router.post("/api/adversaries/compute")
def compute(request: Request, body: dict):
    """Live editor feedback: derived stats and armour totals for a draft."""
    state = st(request)
    ch = body.get("characteristics") or {}
    ints = {k: A._int(ch.get(k), 0) for k in A.CHAR_ORDER}
    arm = body.get("armour") or {}
    ap, sp = A.compute_armour(arm.get("pieces", []), arm.get("helmet", ""),
                              arm.get("shield", ""), state.combat_data)
    return {"derived": state.rules.derive_stats(ints), "armor_points": ap, "shield": sp,
            "armour_desc": A.describe_armour(arm.get("pieces", []), arm.get("helmet", ""),
                                             arm.get("shield", ""))}


@router.post("/api/adversaries/brawling")
def brawling(body: dict):
    """The default Brawling skill and the Brawling Damage for an editor draft."""
    ch = body.get("characteristics") or {}
    ints = {k: A._int(ch.get(k), 0) for k in A.CHAR_ORDER}
    v, src = A.default_brawling(body.get("name", ""), body.get("category", "human"), ints,
                                body.get("attacks") or [], body.get("skills") or {})
    return {"default": v, "source": src, "damage": A.brawling_damage(ints)}


@router.post("/api/adversaries/weapon")
def weapon(request: Request, body: dict):
    state = st(request)
    w = state.combat_data.get("weapons", {}).get(body.get("weapon", ""))
    if w is None:
        bad("Unknown weapon")
    ch = body.get("characteristics") or {}
    ints = {k: A._int(ch.get(k), 0) for k in A.CHAR_ORDER}
    base = state.rules.derive_stats(ints)["Damage"]
    return {"attack": {"weapon": body["weapon"], "skill": w.get("skill", body["weapon"]),
                       "value": ints.get("DEX", 10),
                       "damage": A.resolve_weapon_damage(w, base)}}


@router.post("/api/adversaries/roll-characteristics")
def roll_characteristics(request: Request, body: dict):
    state = st(request)
    culture = body.get("culture") or (state.generator.culture_names() or [""])[0]
    stats, _ = state.rules.roll_characteristics(culture)
    return {"characteristics": {k: stats[k] for k in A.CHAR_ORDER}}


@router.post("/api/adversaries/auto")
def auto(request: Request, body: dict):
    state = st(request)
    culture = body.get("culture") or (state.generator.culture_names() or [""])[0]
    if culture not in state.generator.cultures:
        bad("Unknown culture")
    cls = body.get("social_class")
    cls = None if cls in (None, "", "Random") else cls
    draft, npc = A.auto_generate(state.generator, culture, body.get("gender") or "Male", cls)
    return {"draft": draft, "religion": npc.get("religion", ""),
            "looks": A._npc_looks(npc), "social_class": npc.get("social_class", "")}


@router.post("/api/adversaries/stat-value")
def stat_value(request: Request, body: dict):
    """Autoroll a value for a skill/passion, or a balanced value for a trait."""
    state = st(request)
    kind, name = body.get("kind"), (body.get("name") or "").strip()
    current = {k: A._int(v) for k, v in (body.get("current") or {}).items()}
    if not name:
        bad("Pick something to add")
    if kind == "trait":
        res = A.add_trait(state.rules, current, name)
        if res is None:
            bad(f"{name.split(' (')[0]} is already listed")
        n, v, note = res
        return {"name": n, "value": v, "note": note}
    if name in current:
        bad(f"{name} is already listed")
    if kind == "skill":
        return {"name": name, "value": A.roll_skill_value(), "note": "rolled"}
    if kind == "passion":
        return {"name": name, "value": A.roll_passion_value(state.rules, name), "note": "rolled"}
    bad("Unknown kind")


@router.post("/api/adversaries/balance-traits")
def balance_traits(request: Request, body: dict):
    state = st(request)
    raw = {k: A._int(v) for k, v in (body.get("traits") or {}).items()}
    snap = {k: A._int(v) for k, v in (body.get("before") or {}).items()}
    return {"traits": A.normalise_traits(state.rules, raw, snap)}


# -- encounter definitions -------------------------------------------------------

def _enc_summary(key, d):
    lines = d.get("roster", d.get("core", []))
    return {"key": key, "description": d.get("description", ""), "tags": d.get("tags", []),
            "lines": len(lines), "source": d.get("source", ""), "battle_role": d.get("battle_role"),
            "adversaries": [ln.get("adversary", "") if isinstance(ln, dict) else ln for ln in lines]}


@router.get("/api/encounters")
def list_encounters(request: Request):
    encs = _encs(st(request))
    return {"encounters": [_enc_summary(k, encs[k]) for k in alpha(encs)]}


@router.get("/api/encounters/blank")
def blank_enc():
    return {"encounter": blank_encounter()}


@router.get("/api/encounters/{key}")
def get_encounter(request: Request, key: str):
    d = _encs(st(request)).get(key)
    if d is None:
        bad("No such encounter", 404)
    e = to_editable(d)
    e["name"] = e.get("name") or key
    return {"key": key, "encounter": e}


def _clean_encounter(d, advs):
    out = blank_encounter()
    out["name"] = str(d.get("name", "")).strip()
    out["description"] = str(d.get("description", "")).strip()
    tags = d.get("tags", [])
    if isinstance(tags, str):
        tags = tags.split(",")
    out["tags"] = [t.strip() for t in tags if str(t).strip()]
    out["notes"] = str(d.get("notes", "")).rstrip()
    for ln in d.get("roster", []):
        adv = ln.get("adversary")
        if not adv:
            continue
        per = bool(ln.get("per_player"))
        try:
            count = float(ln.get("count", 1)) if per else max(0, int(round(float(ln.get("count", 1)))))
        except (TypeError, ValueError):
            count = 1.0 if per else 1
        out["roster"].append({"adversary": adv, "count": count, "per_player": per,
                              "promote": bool(ln.get("promote"))})
    lead = d.get("leader") or {}
    if isinstance(lead, dict) and lead.get("adversary"):
        out["leader"] = {"adversary": lead["adversary"], "promote": bool(lead.get("promote", True))}
    # Battle fields (Foe / Opportunity decks).
    role = d.get("battle_role") or None
    if role not in (None, "foe", "opportunity"):
        bad("Battle role is Foe, Opportunity or none")
    out["battle_role"] = role
    mm = d.get("morale_minimum")
    if mm in (None, ""):
        out["morale_minimum"] = None
    else:
        out["morale_minimum"] = to_int(mm, "Minimum Morale")
        if out["morale_minimum"] < 0:
            bad("Minimum Morale can't be negative")
    loss = str(d.get("morale_loss") or "").strip().upper()
    if loss:
        try:
            roll_notation(loss)
        except NotationError:
            bad("Morale Loss isn't dice — e.g. 1D6+3")
    out["morale_loss"] = loss
    out["missile"] = bool(d.get("missile")) and role == "foe"
    out["rules"] = str(d.get("rules") or "").strip()
    return out


@router.post("/api/encounters/preview")
def preview(request: Request, body: dict):
    state = st(request)
    d = _clean_encounter(body.get("encounter") or {}, _advs(state))
    n = max(1, to_int(body.get("players") or 4, "players"))
    lines, total = preview_lines(d, n)
    glory, hp = roster_threat(d, n, state.combat_data)
    mm, loss = B.default_morale(d, _advs(state))
    return {"lines": lines, "total": total, "glory": glory, "hp": hp,
            "battle_defaults": {"morale_minimum": mm, "morale_loss": loss, "kv_per_knight": _kv_per_knight(d, _advs(state))}}


_KV_TEXT = {(1, 8): "⅛", (1, 4): "¼", (3, 8): "⅜", (1, 2): "½", (5, 8): "⅝", (3, 4): "¾", (7, 8): "⅞"}


def _kv_text(f):
    """A Knight Value as the cards print it (¼, 1½…)."""
    whole, frac = int(f), f - int(f)
    glyph = _KV_TEXT.get((frac.numerator, frac.denominator), f"{frac.numerator}/{frac.denominator}") if frac else ""
    return (str(whole) if whole or not glyph else "") + glyph


def _kv_lines(d, advs):
    out = []
    for ln in to_editable(d)["roster"]:
        a = advs.get(ln.get("adversary"))
        if not a:
            continue
        kv = B.parse_kv(a.get("other", {}).get("knight_value", ""))
        per = float(ln.get("count", 1)) if ln.get("per_player") else 0.0
        out.append({"adversary": ln["adversary"], "kv": _kv_text(kv), "per_knight": per, "_kv": kv})
    return out


def _kv_per_knight(d, advs):
    from fractions import Fraction
    total = sum((x["_kv"] * Fraction(x["per_knight"]).limit_denominator(16) for x in _kv_lines(d, advs)), Fraction(0))
    return _kv_text(total)


@router.get("/api/battle-decks")
def battle_decks(request: Request, role: str | None = None):
    """Battle-approved encounters with their GM-only mechanics (Minimum, Loss,
    KV) for deck pickers. Never projected to the Table."""
    if role not in (None, "foe", "opportunity"):
        bad("role is foe or opportunity")
    advs = _advs(st(request))
    cards = []
    for key in alpha(_encs(st(request))):
        d = _encs(st(request))[key]
        r = d.get("battle_role")
        if not r or (role and r != role):
            continue
        ed = to_editable(d)
        mm, loss = B.default_morale(ed, advs)
        kvs = [{k: v for k, v in x.items() if k != "_kv"} for x in _kv_lines(d, advs)]
        cards.append({"key": key, "role": r, "description": d.get("description", ""),
                      "morale_minimum": d.get("morale_minimum") if d.get("morale_minimum") is not None else mm,
                      "morale_loss": d.get("morale_loss") or loss, "kv": kvs,
                      "kv_per_knight": _kv_per_knight(d, advs), "missile": bool(d.get("missile")),
                      "countercharge": B.has_countercharge(ed, advs), "mounted_charge": B.mounted_charge_card(ed, advs),
                      "has_roster": bool(ed["roster"] or ed.get("leader")), "rules": d.get("rules", "")})
    return {"cards": cards}


@router.put("/api/encounters")
async def save_encounter(request: Request, body: dict):
    state = st(request)
    d = _clean_encounter(body.get("encounter") or {}, _advs(state))
    key, original = d["name"], body.get("original")
    if not key:
        bad("Give the encounter a name before saving")
    encs = _encs(state)
    if key in encs and key != original and not body.get("overwrite"):
        bad(f"An encounter named '{key}' exists", 409)
    if original and original != key and original in encs:
        del encs[original]
    encs[key] = d
    path = state.save_combat_data()
    state.notify("library")
    return {"key": key, "encounter": d, "path": path}


@router.delete("/api/encounters/{key}")
async def delete_encounter(request: Request, key: str):
    state = st(request)
    if key not in _encs(state):
        bad("No such encounter", 404)
    del _encs(state)[key]
    state.save_combat_data()
    state.notify("library")
    return {"ok": True}


# -- examples: new shipped content into the user's library (Q19) -------------

def _baseline(state):
    with open(example_combat_path(state.data_dir), encoding="utf-8") as fh:
        return json.load(fh)


@router.get("/api/library/examples")
def examples(request: Request):
    state = st(request)
    return X.examples_report(state.combat_data, _baseline(state))


@router.post("/api/library/examples/merge")
async def examples_merge(request: Request):
    state = st(request)
    added = X.merge_missing(state.combat_data, _baseline(state))
    state.save_combat_data()
    state.notify("library")
    return {"added": added}


@router.post("/api/library/examples/restore")
async def examples_restore(request: Request, body: dict):
    state = st(request)
    kind, key = body.get("kind"), body.get("key")
    if kind not in ("adversaries", "encounters"):
        bad("Choose adversaries or encounters")
    try:
        entry = X.restore_entry(state.combat_data, _baseline(state), kind, key)
    except KeyError:
        bad(f"'{key}' isn't one of the shipped {kind}", 404)
    state.save_combat_data()
    state.notify("library")
    return {"key": key, "entry": entry}


# -- saved battles (the Battles prep tool) ------------------------------------

def _battles(state):
    return state.combat_data.setdefault("battles", {})


@router.get("/api/battles")
def list_battles(request: Request):
    bs = _battles(st(request))
    return {"battles": [{"key": k, "size": bs[k].get("size"), "days": len(bs[k].get("days", [])),
                         "source": bs[k].get("source", "")} for k in alpha(bs)]}


@router.get("/api/battles/blank")
def blank_battle(size: str = "clash"):
    return {"battle": BD.blank_battle(size)}


@router.get("/api/battles/{key}")
def get_battle(request: Request, key: str):
    bs = _battles(st(request))
    if key not in bs:
        bad("No such battle", 404)
    return {"key": key, "battle": bs[key]}


@router.put("/api/battles")
async def save_battle(request: Request, body: dict):
    state = st(request)
    try:
        b, warnings = BD.clean_battle(body.get("battle") or {}, _encs(state))
    except ValueError as exc:
        bad(str(exc))
    key, original = b["name"], body.get("original")
    if not key:
        bad("Give the battle a name before saving")
    bs = _battles(state)
    if key in bs and key != original and not body.get("overwrite"):
        bad(f"A battle named '{key}' exists", 409)
    if original and original != key and original in bs:
        del bs[original]
    bs[key] = b
    path = state.save_combat_data()
    state.notify("library")
    return {"key": key, "battle": b, "warnings": warnings, "path": path}


@router.delete("/api/battles/{key}")
async def delete_battle(request: Request, key: str):
    state = st(request)
    if key not in _battles(state):
        bad("No such battle", 404)
    del _battles(state)[key]
    state.save_combat_data()
    state.notify("library")
    return {"ok": True}
