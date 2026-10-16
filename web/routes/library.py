"""Adversary and encounter-definition libraries (the two creator tools).

Edits are written to the git-ignored working ``data/combat.json`` (never the
tracked baseline). Library edits are prep, not play, so they aren't logged.
"""

from fastapi import APIRouter, Request

from core import adversary as A
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
        "weapons": {k: {"skill": v.get("skill", k)} for k, v in combat.get("weapons", {}).items()},
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
            "lines": len(lines), "source": d.get("source", ""),
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
    return out


@router.post("/api/encounters/preview")
def preview(request: Request, body: dict):
    state = st(request)
    d = _clean_encounter(body.get("encounter") or {}, _advs(state))
    n = max(1, to_int(body.get("players") or 4, "players"))
    lines, total = preview_lines(d, n)
    glory, hp = roster_threat(d, n, state.combat_data)
    return {"lines": lines, "total": total, "glory": glory, "hp": hp}


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
