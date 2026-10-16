"""The combat tracker. Every change is an event (see web.combat_state); this
module validates a request, works out the log line (and a player-safe line for
the Table that never shows a foe's numbers), and records it."""

from fastapi import APIRouter, Request

from core.combat import (CHAR_FULL, CHAR_ORDER, Combatant, Encounter, blow_breakdown,
                         resolve_attack, resolve_blow, roll_ransom, surrender_check)
from core.dice import NotationError, roll_notation, skill_display
from core.encounter_def import to_editable
from web.routes.common import bad, st, to_int
from web.routes.rolls import record_check, record_damage

router = APIRouter()


def _state(request):
    state = st(request)
    cs = state.combat_state()
    return state, cs


def _active(request):
    state, cs = _state(request)
    if not cs or not cs["active"]:
        bad("No combat in progress", 409)
    return state, cs


def _combatant(cs, cid):
    c = next((x for x in cs["combatants"] if x.id == cid), None)
    if c is None:
        bad("No such combatant", 404)
    return c


def _is_foe(c):
    return getattr(c, "side", "foe") != "party"


def _descriptions(combatants):
    seen, out = set(), []
    for c in combatants:
        if c.type in seen or not _is_foe(c):
            continue
        seen.add(c.type)
        parts = []
        if c.description.strip():
            parts.append(c.description.strip())
        if c.notes.strip() and c.notes.strip() != c.description.strip():
            parts.append(f"Mechanics: {c.notes.strip()}")
        if parts:
            out.append({"type": c.type, "text": "   ·   ".join(parts)})
    return out


def _active_party(state):
    return [m for m in state.party.items if m.get("active", True)]


def _end(state, cs, reason="ended"):
    """Close the combat and carry the knights' Hit Points back to the Party."""
    for c in cs["combatants"]:
        pid = getattr(c, "party_id", None)
        if pid and state.party.get(pid):
            state.party.update(pid, {"cur_hp": c.cur_hp})
    state.record("combat.ended", f"Combat {reason}: {cs['name']}", title=cs["name"],
                 data={"name": cs["name"]})


# -- start / add / end -----------------------------------------------------

@router.post("/api/combat/start")
async def start(request: Request, body: dict):
    state, cs = _state(request)
    combat = state.combat_data
    defn = body.get("definition")
    name = (body.get("name") or "").strip()
    if not defn:
        key = body.get("encounter", "")
        if key not in combat.get("encounters", {}):
            bad("Choose an encounter to launch")
        defn = combat["encounters"][key]
        name = name or key
    defn = to_editable(defn)
    name = name or defn.get("name") or "Encounter"
    party = _active_party(state) if body.get("include_party", True) else []
    players = to_int(body.get("players") or len(party) or 4, "players")
    if players < 1:
        bad("At least one player")

    enc = Encounter(state.rules)
    foes = enc.generate_from_definition(defn, players)
    knights = []
    for m in party:
        k = Combatant.from_party(m)
        k.id = f"p-{m['id']}"
        knights.append(k)
    if not foes and not knights:
        bad("That encounter has no combatants")

    if cs and cs["active"]:
        _end(state, cs, "abandoned")

    names = ", ".join(c.display_name for c in foes)
    lines = [f"Launched '{name}' for {players} players: {names}"]
    if defn.get("description", "").strip():
        lines.append(defn["description"].strip())
    descriptions = _descriptions(foes)
    if defn.get("notes", "").strip():
        descriptions.insert(0, {"type": "GM notes", "text": defn["notes"].strip()})
    ev = state.record(
        "combat.started", " — ".join(lines), title=name,
        data={"name": name, "players": players, "descriptions": descriptions,
              "combatants": [c.to_dict() for c in knights + foes],
              "table_text": (f"{len(foes)} foe{'s' if len(foes) != 1 else ''} take the field: {names}"
                             + (f". {defn['description'].strip()}" if defn.get("description", "").strip() else ""))})
    return {"event": ev}


@router.post("/api/combat/add")
async def add(request: Request, body: dict):
    state, cs = _active(request)
    adv = body.get("adversary", "")
    if adv not in state.combat_data.get("adversaries", {}):
        bad("Unknown adversary")
    enc = Encounter(state.rules)
    enc._counts = {}
    for c in cs["combatants"]:
        if _is_foe(c):
            enc._counts[c.type] = enc._counts.get(c.type, 0) + 1
    enc._seq = max([int(c.id[1:]) for c in cs["combatants"]
                    if c.id[:1] == "c" and c.id[1:].isdigit()] + [0])
    c = enc.add_one(adv)
    ev = state.record("combat.added", f"Added {c.display_name}", title=c.display_name,
                      data={"combatant": c.to_dict(),
                            "table_text": f"{c.display_name} joins the fray"})
    return {"event": ev}


@router.post("/api/combat/add-party")
async def add_party(request: Request, body: dict):
    state, cs = _active(request)
    m = state.party.get(body.get("member_id", ""))
    if m is None:
        bad("No such knight", 404)
    if any(getattr(c, "party_id", None) == m["id"] for c in cs["combatants"]):
        bad(f"{m['name']} is already in the fight")
    k = Combatant.from_party(m)
    k.id = f"p-{m['id']}"
    ev = state.record("combat.added", f"{k.display_name} joins the fight", title=k.display_name,
                      data={"combatant": k.to_dict()})
    return {"event": ev}


@router.post("/api/combat/round")
async def next_round(request: Request):
    state, cs = _active(request)
    n = cs["round"] + 1
    ev = state.record("combat.round", f"Round {n}", title=f"Round {n}", data={"round": n})
    return {"event": ev}


@router.post("/api/combat/end")
async def end(request: Request):
    state, cs = _active(request)
    _end(state, cs)
    return {"ok": True}


@router.post("/api/combat/note")
async def combat_note(request: Request, body: dict):
    state, _cs = _active(request)
    text = (body.get("text") or "").strip()
    if not text:
        bad("Empty note")
    ev = state.record("combat.note", f"— {text}", data={"text": text})
    return {"event": ev}


# -- per-combatant changes -------------------------------------------------

@router.post("/api/combat/{cid}/hp")
async def hp(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    delta = to_int(body.get("delta"), "delta")
    if not delta:
        bad("Enter damage as a negative number or healing as a positive one")
    old, msg = c.apply_hp(delta)          # on the replayed copy, just for the text
    text = f"{c.log_name}: {old} → {c.cur_hp} Hit Points ({delta:+d}){msg}"
    if _is_foe(c):
        if "Mortal" in msg:
            table = f"{c.display_name} is struck down — slain!"
        elif "Major" in msg:
            table = f"{c.display_name} takes a terrible wound and falls unconscious!"
        elif "revived" in msg:
            table = f"{c.display_name} stirs — revived"
        elif delta < 0:
            table = f"{c.display_name} is hit — {c.wound_state()}"
        else:
            table = f"{c.display_name} recovers — {c.wound_state()}"
    else:
        table = text
    ev = state.record("combat.hp", text, title=c.display_name,
                      data={"cid": cid, "delta": delta, "table_text": table})
    return {"event": ev}


_STATUS_TEXT = {
    None: ("{n} brought back up", "{n} is back on their feet"),
    "unconscious": ("{n} knocked out (unconscious)", "{n} is knocked senseless"),
    "dead": ("{n} slain", "{n} is slain"),
    "fled": ("{n} flees the field — no longer active", "{n} flees the field"),
}


@router.post("/api/combat/{cid}/status")
async def status(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    out = body.get("out")
    if out not in _STATUS_TEXT:
        bad("Unknown status")
    if c.status == "fled" and out is None:
        log, table = "{n} resumes the fight — active again", "{n} returns to the fight"
    else:
        log, table = _STATUS_TEXT[out]
    ev = state.record("combat.status", log.format(n=c.log_name), title=c.display_name,
                      data={"cid": cid, "out": out,
                            "table_text": table.format(n=c.display_name)})
    return {"event": ev}


@router.post("/api/combat/{cid}/promote")
async def promote(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if c.elite:
        text = f"{c.display_name} demoted to a common {c.type}"
        data = {"cid": cid, "promote": False, "table_text": f"{c.label} is no champion after all"}
    else:
        text = f"{c.label} promoted to {c.promotion_title} (elite)"
        data = {"cid": cid, "promote": True,
                "cfg": state.combat_data.get("promotion", {}),
                "table_text": f"{c.label} is revealed as {c.promotion_title}!"}
    ev = state.record("combat.promote", text, title=c.label, data=data)
    return {"event": ev}


@router.post("/api/combat/{cid}/modifier")
async def modifier(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    value = to_int(body.get("value") or 0, "modifier")
    if value == c.modifier:
        return {"event": None}
    text = (f"{c.display_name} situational modifier set to {value:+d}" if value
            else f"{c.display_name} situational modifier cleared")
    ev = state.record("combat.modifier", text, title=c.display_name, visibility="gm",
                      data={"cid": cid, "value": value})
    return {"event": ev}


@router.post("/api/combat/{cid}/engage")
async def engage(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    who = (body.get("with") or "").strip()
    if who == c.engaged_with:
        return {"event": None}
    if who:
        looks = c.describe_looks()
        text = f"{c.display_name} engaged with {who}" + (f" — {looks}" if looks else "")
        table = f"{c.display_name} engages {who}" + (f" — {looks}" if looks else "")
    else:
        text = table = f"{c.display_name} no longer engaged"
    ev = state.record("combat.engage", text, title=c.display_name,
                      data={"cid": cid, "with": who, "table_text": table})
    return {"event": ev}


@router.post("/api/combat/{cid}/remove")
async def remove(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    ev = state.record("combat.removed", f"{c.display_name} removed from the encounter",
                      title=c.display_name, visibility="gm", data={"cid": cid})
    return {"event": ev}


# -- rolls -------------------------------------------------------------------

@router.post("/api/combat/{cid}/roll")
async def roll(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    what, key = body.get("what"), body.get("key")
    masked = False      # combat rolls are always public — players see every roll
    common = dict(actor=c.log_name, masked=masked, extra={"cid": cid})
    if what == "char":
        if key not in CHAR_ORDER:
            bad("Unknown characteristic")
        ev = record_check(state, label=CHAR_FULL[key], value=c.characteristics[key],
                          kind="characteristic", modifier=c.modifier, **common)
    elif what in ("attack", "damage"):
        try:
            atk = c.attacks[int(key)]
        except (TypeError, ValueError, IndexError):
            bad("Unknown attack")
        if what == "attack":
            common["extra"]["attack"] = int(key)
            ev = record_check(state, label=atk["weapon"], value=atk["value"],
                              modifier=c.modifier, **common)
        else:
            ev = record_damage(state, label=atk["weapon"], expr=atk["damage"],
                               critical=bool(body.get("critical")),
                               rebated=bool(body.get("rebated")),
                               actor=c.log_name, masked=masked, extra={"cid": cid})
    elif what == "skill":
        if key not in c.skills:
            bad("Unknown skill")
        ev = record_check(state, label=key, value=c.skills[key], modifier=c.modifier, **common)
    else:
        bad("Unknown roll")
    return {"event": ev}


@router.post("/api/combat/{cid}/surrender")
async def surrender(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    roll_, outcome, line = surrender_check(c)
    ev = state.record("combat.check", line, title=f"{c.display_name} — Surrender check",
                      data={"cid": cid, "roll": roll_, "outcome": outcome,
                            "label": "Surrender check"})
    return {"event": ev}


@router.post("/api/combat/{cid}/ransom")
async def ransom(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not c.ransom:
        bad("No ransom table for this combatant")
    roll_, line = roll_ransom(c)
    ev = state.record("combat.check", line, title=f"{c.display_name} — Ransom",
                      data={"cid": cid, "roll": roll_, "label": "Ransom"})
    return {"event": ev}


# -- blows: damage → rebate → protection → wound ------------------------------

def _weapon_def(state, name):
    return state.combat_data.get("weapons", {}).get(name or "", {})


@router.post("/api/combat/blow")
async def blow(request: Request, body: dict):
    """Resolve one blow (Core Ch.7 Table 7.1, Ch.8). The attacker's weapon
    damage is rolled here — or a total the player rolled is entered — then
    critical/reckless dice, rebating, armour and shield/parry are applied and
    the wound lands on the target. Every number is shown to the players."""
    state, cs = _active(request)
    return {"event": record_blow(state, cs, body)}


def record_blow(state, cs, body):
    attacker = _combatant(cs, body["attacker"]) if body.get("attacker") else None
    target = _combatant(cs, body["target"]) if body.get("target") else None
    weapon, expr = (body.get("weapon") or "").strip(), None
    if attacker is not None and body.get("attack") not in (None, ""):
        try:
            atk = attacker.attacks[int(body["attack"])]
        except (TypeError, ValueError, IndexError):
            bad("Unknown attack")
        weapon = atk["weapon"]
        expr = atk["damage"]
    rolled = body.get("damage")
    if rolled not in (None, ""):
        rolled, expr = to_int(rolled, "damage"), None      # a typed total wins
        if rolled < 0:
            bad("Damage can't be negative")
    elif expr:
        try:
            roll_notation(expr)
        except NotationError:
            bad(f"'{expr}' isn't dice — enter the damage rolled (e.g. a lance uses the horse's damage)")
    else:
        bad("Pick a weapon or enter the damage rolled")
    extra = (body.get("extra") or "").strip()
    wdef = _weapon_def(state, weapon)
    if body.get("vs_mail") and wdef.get("vs_mail"):
        extra = (extra + "+1D6") if extra else "1D6"     # Mace +1D6; Great Mace +3D6 replaces +2D6
    if extra:
        try:
            roll_notation(extra)
        except NotationError:
            bad(f"Can't read the extra damage '{extra}'")
    unarmed = bool(attacker and not wdef and weapon.lower() in ("fist", "punch", "unarmed", "brawling"))
    through = "strikes through shields" in (wdef.get("advantage", "").lower())

    shield_value = body.get("shield_value")
    shield_value = (to_int(shield_value, "shield") if shield_value not in (None, "")
                    else (target.shield if target else 0))
    b = resolve_blow(
        expr=expr, rolled=rolled, critical=bool(body.get("critical")), unarmed=unarmed,
        reckless=bool(body.get("reckless")), extra=extra, rebated=bool(body.get("rebated")),
        armour=target.armor_points if target else 0, shield=shield_value,
        shield_applies=bool(body.get("shield")), through_shields=through,
        knockdown=(target.knockdown if target else 0))
    if not target:
        b["armour"] = 0

    who = attacker.display_name if attacker else (body.get("attacker_name") or "").strip()
    what = weapon or ""
    hit = ("CRITICAL " if b["critical"] else "") + ("reckless " if b["reckless"] else "")
    head = f"{who}’s {what or 'blow'}" if who else (what or "A blow")
    breakdown = blow_breakdown(b)
    if target:
        tgt = Combatant.from_dict(target.to_dict())      # a copy, just for the text
        old, msg = tgt.apply_hp(-b["wound"]) if b["wound"] else (tgt.cur_hp, "")
        consequences = []
        if b["knockdown"] == "automatic":
            consequences.append(f"KNOCKED DOWN ({b['full']} > twice Knockdown {target.knockdown})")
        elif b["knockdown"] == "check":
            consequences.append(f"Knockdown check — DEX roll ({b['full']} > Knockdown {target.knockdown})")
        if b["shield_broken"]:
            consequences.append("shield broken")
        tail = (" — " + "; ".join(consequences)) if consequences else ""
        text = (f"{head} {hit}hits {target.log_name}: {breakdown}. "
                f"{old} → {tgt.cur_hp} Hit Points{msg}{tail}")
        if _is_foe(target):
            state_txt = ("slain!" if "Mortal" in msg else "a Major Wound — falls unconscious!" if "Major" in msg
                         else tgt.wound_state())
            table = f"{head} {hit}hits {target.display_name}: {breakdown}. {target.display_name}: {state_txt}{tail}"
        else:
            table = text
        title = f"{who + ' → ' if who else ''}{target.display_name}"
    else:
        text = table = f"{head} {hit}damage: {breakdown}"
        title = head
    data = {"cid": target.id if target else None, "delta": -b["wound"],
            "attacker": who, "weapon": what, "target": target.display_name if target else "",
            "blow": b, "breakdown": breakdown, "shield_broken": b["shield_broken"],
            "major": bool(target and "Major" in msg), "mortal": bool(target and "Mortal" in msg),
            "table_text": table}
    return state.record("combat.blow", text, title=title, data=data)


# -- an enemy attacks a knight: Table 7.1 from the two results ----------------

@router.post("/api/combat/attack")
async def attack(request: Request, body: dict):
    """After an enemy's attack roll (``event`` = that roll's id), the GM gives
    the knight's result; Table 7.1 decides whether the enemy's blow lands (and
    with +4D6 / shield) — if so its damage is rolled and applied."""
    state, cs = _active(request)
    roll = next((e for e in state.session.events if e["id"] == body.get("event")), None)
    if not roll or roll["type"] != "roll.check" or "attack" not in roll["data"]:
        bad("Roll the enemy's attack first")
    foe = _combatant(cs, roll["data"]["cid"])
    knight = _combatant(cs, body.get("target"))
    try:
        r = resolve_attack(roll["data"]["outcome"], body.get("knight"))
    except ValueError as exc:
        bad(str(exc))
    k_text = {"critical": "critical", "higher": "success (higher)", "equal": "success (equal)",
              "lower": "success (lower)", "failure": "failure", "fumble": "fumble"}[body["knight"]]
    verdict = {"foe": f"{foe.display_name} wins", "knight": f"{knight.display_name} wins",
               "tie": "tie — both strike", "none": "both miss"}[r["result"]]
    if r["result"] in ("knight", "tie"):
        verdict += f"; {foe.display_name} gets {'armour + shield' if r['knight_shield'] else 'armour only'}"
    for who in r["fumbled"]:
        verdict += f"; {(foe if who == 'foe' else knight).display_name} drops or breaks their weapon"
    ev = state.record("combat.attack",
                      f"{foe.display_name} {roll['data']['outcome']} vs {knight.display_name} {k_text} → {verdict}",
                      title=f"{foe.display_name} vs {knight.display_name}",
                      data={"verdict": verdict, "result": r["result"], "knight_shield": r["knight_shield"]})
    blow_ev = None
    if r["foe_strike"]:
        blow_ev = record_blow(state, state.combat_state(), {
            "attacker": foe.id, "attack": roll["data"]["attack"], "target": knight.id,
            **r["foe_strike"]})
    return {"event": ev, "blow": blow_ev, "result": r["result"], "knight_shield": r["knight_shield"]}

