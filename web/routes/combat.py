"""The combat tracker. Every change is an event (see web.combat_state); this
module validates a request, works out the log line (and a player-safe line for
the Table that never shows a foe's numbers), and records it."""

from fastapi import APIRouter, Request

from core import battle as B
from core.combat import (CHAR_FULL, CHAR_ORDER, Combatant, Encounter, blow_breakdown,
                         resolve_attack, resolve_blow, roll_ransom, surrender_check)
from core.dice import NotationError, roll_notation, skill_display
from core.encounter_def import to_editable
from web.routes.cast import cast_combatant, has_stats
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


def _engaged_knight(cs, c):
    """The knight a foe is fighting, or None."""
    return next((k for k in cs["combatants"] if not _is_foe(k)
                 and k.display_name == c.engaged_with), None) if c.engaged_with else None


def _height(cs, c):
    """Height Advantage on this foe's rolls against its engaged knight."""
    k = _engaged_knight(cs, c)
    if k is None or not _is_foe(c):
        return 0
    return B.height(c.mounted, k.mounted, c.height_override, c.attacks_horse)[0]


# -- Glory for defeated foes (derived on replay; see web.combat_state) --------

def _knight_pid(cs, name):
    k = next((k for k in cs["combatants"] if not _is_foe(k) and k.display_name == name), None)
    return k.party_id if k else None


def _defeat_note(cs, was_defeated, after):
    """When this change defeats a foe, the Table line names the Glory and the
    knight it goes to: (suffix, extra data)."""
    if not _is_foe(after) or was_defeated or not B.is_defeated(after.status):
        return "", {}
    pid = _knight_pid(cs, after.engaged_with)
    if not pid:
        return "", {}
    g = B.glory_for(after)
    return (f" — +{g} Glory, {after.engaged_with}" if g else ""), {"touches": [pid], "glory_amount": g}


def _who_defeated(state, cid, was_defeated):
    """A foe that fell while fighting nobody: ask the GM who gets its Glory."""
    if was_defeated:
        return None
    cs = state.combat_state()
    c = next((x for x in cs["combatants"] if x.id == cid), None) if cs else None
    if c is None or not _is_foe(c) or not B.is_defeated(c.status):
        return None
    if not any(not _is_foe(k) for k in cs["combatants"]):
        return None
    from web.combat_state import credit_of
    if credit_of(cs, c) is None and c.id not in cs.get("credits", {}):
        return {"kind": "who_defeated", "cid": cid, "name": c.display_name}
    return None


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
    """Close the combat."""
    state.record("combat.ended", f"Combat {reason}: {cs['name']}", title=cs["name"],
                 data={"name": cs["name"]})


# -- start / add / end -----------------------------------------------------

@router.post("/api/combat/start")
async def start(request: Request, body: dict):
    state, cs = _state(request)
    combat = state.combat_data
    defn = body.get("definition")
    name = (body.get("name") or "").strip()
    lone = None
    if not defn and body.get("cast"):               # a Cast NPC
        entry = state.cast.get(body["cast"])
        if entry is None or not has_stats(entry):
            bad("That NPC has no saved stats")
        lone = cast_combatant(state, entry, "n1")
        name = name or entry["npc"]["full"]
        defn = {"roster": []}
    if not defn and body.get("adversary"):          # a lone adversary
        adv = body["adversary"]
        if adv not in combat.get("adversaries", {}):
            bad("Unknown adversary")
        defn = {"roster": [{"adversary": adv, "count": 1, "per_player": False}]}
        name = name or adv
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
    if lone is not None:
        foes = [lone]
    knights = []
    mounted = body.get("knights_mounted", True) is not False
    for m in party:
        k = Combatant.from_party(m, mounted=mounted)
        k.id = f"p-{m['id']}"
        knights.append(k)
    if not foes and not knights:
        bad("That encounter has no combatants")

    if cs and cs["active"]:
        _end(state, cs, "abandoned")

    names = ", ".join(c.display_name for c in foes)
    lines = [f"Combat begins: {names}" if (body.get("adversary") or body.get("cast")) and not body.get("definition")
             else f"Launched '{name}' for {players} players: {names}"]
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
    if body.get("cast"):
        entry = state.cast.get(body["cast"])
        if entry is None or not has_stats(entry):
            bad("That NPC has no saved stats")
        n = sum(1 for c in cs["combatants"] if c.id.startswith("n")) + 1
        c = cast_combatant(state, entry, f"n{n}")
        if any(x.display_name == c.display_name for x in cs["combatants"]):
            c.label = f"{c.label} ({n})"
        ev = state.record("combat.added", f"Added {c.display_name}", title=c.display_name,
                          data={"combatant": c.to_dict(), "table_text": f"{c.display_name} joins the fray"})
        return {"event": ev}
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
    if not _is_foe(c):
        bad("Players keep their knights' Hit Points on their own sheets")
    delta = to_int(body.get("delta"), "delta")
    if not delta:
        bad("Enter damage as a negative number or healing as a positive one")
    was = B.is_defeated(c.status)
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
    suffix, extra = _defeat_note(cs, was, c)
    ev = state.record("combat.hp", text + suffix, title=c.display_name,
                      data={"cid": cid, "delta": delta, "table_text": table + suffix, **extra})
    return {"event": ev, "prompt": _who_defeated(state, cid, was)}


_STATUS_TEXT = {
    None: ("{n} brought back up", "{n} is back on their feet"),
    "unconscious": ("{n} knocked out (unconscious)", "{n} is knocked senseless"),
    "dead": ("{n} slain", "{n} is slain"),
    "fled": ("{n} flees the field — no longer active", "{n} flees the field"),
    "surrendered": ("{n} surrenders", "{n} surrenders"),
}


@router.post("/api/combat/{cid}/status")
async def status(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    out = body.get("out")
    if out not in _STATUS_TEXT:
        bad("Unknown status")
    if not _is_foe(c):                   # a knight: just the GM's down / out marker
        if out not in (None, "unconscious", "fled"):
            bad("A knight can only be marked down or out of the fight")
        line = {None: "{n} is back in the fight", "unconscious": "{n} is down",
                "fled": "{n} is out of the fight"}[out].format(n=c.display_name)
        ev = state.record("combat.status", line, title=c.display_name,
                          data={"cid": cid, "out": out, "table_text": line, "touches": [c.party_id]})
        return {"event": ev}
    if c.status == "fled" and out is None:
        log, table = "{n} resumes the fight — active again", "{n} returns to the fight"
    else:
        log, table = _STATUS_TEXT[out]
    was = B.is_defeated(c.status)
    after = Combatant.from_dict(c.to_dict())
    after.set_out(out)
    suffix, extra = _defeat_note(cs, was, after)
    ev = state.record("combat.status", log.format(n=c.log_name) + suffix, title=c.display_name,
                      data={"cid": cid, "out": out,
                            "table_text": table.format(n=c.display_name) + suffix, **extra})
    return {"event": ev, "prompt": _who_defeated(state, cid, was)}


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
    data = {"cid": cid, "with": who, "table_text": table}
    pid = _knight_pid(cs, who) if _is_foe(c) else None
    if pid:
        data["touches"] = [pid]
    ev = state.record("combat.engage", text, title=c.display_name, data=data)
    return {"event": ev}


# -- mounted pills, attacking the horse, Height override, captives (S2) -------

@router.post("/api/combat/{cid}/mounted")
async def mounted(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    on = bool(body.get("mounted"))
    if on == c.mounted:
        return {"event": None}
    line = f"{c.display_name} is {'mounted' if on else 'on foot'}"
    data = {"cid": cid, "mounted": on, "table_text": line}
    if not _is_foe(c):
        data["touches"] = [c.party_id]
    ev = state.record("combat.mounted", line, title=c.display_name, data=data)
    return {"event": ev}


@router.post("/api/combat/{cid}/horse")
async def horse(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("Only a foe can go for a knight's horse")
    on = bool(body.get("on"))
    if on == c.attacks_horse:
        return {"event": None}
    k = _engaged_knight(cs, c)
    line = (f"{c.display_name} goes for {k.display_name + chr(39) + 's' if k else 'the'} horse" if on
            else f"{c.display_name} turns from the horse to the rider")
    ev = state.record("combat.horse", line, title=c.display_name,
                      data={"cid": cid, "on": on, "table_text": line})
    return {"event": ev}


@router.post("/api/combat/{cid}/height")
async def height_override(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("Height is set on the foe")
    override = body.get("override")
    if override not in (None, "none"):
        bad("Height override is automatic or none")
    if override == c.height_override:
        return {"event": None}
    line = (f"{c.display_name}: no Height advantage (two-handed spear or halberd)" if override
            else f"{c.display_name}: Height worked out from who is mounted")
    ev = state.record("combat.height", line, title=c.display_name,
                      data={"cid": cid, "override": override, "table_text": line})
    return {"event": ev}


@router.post("/api/combat/{cid}/captured")
async def captured(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("A knight can't be taken captive here")
    if "by" in body and body["by"] is None:
        if not c.captured_by:
            return {"event": None}
        line = f"{c.display_name} is released"
        ev = state.record("combat.captured", line, title=c.display_name,
                          data={"cid": cid, "by": None, "table_text": line, "touches": [c.captured_by]})
        return {"event": ev}
    if c.status not in ("unconscious", "surrendered"):
        bad("Only an unconscious or surrendered foe can be taken captive")
    by = body.get("by")
    if by:
        k = next((x for x in cs["combatants"] if not _is_foe(x) and x.party_id == by), None)
        if k is None:
            bad("That knight isn't in the fight")
    else:
        k = _engaged_knight(cs, c)
        if k is None:
            bad("Say which knight took them captive")
    line = f"{c.display_name} is taken captive by {k.display_name}"
    ev = state.record("combat.captured", line, title=c.display_name,
                      data={"cid": cid, "by": k.party_id, "table_text": line, "touches": [k.party_id]})
    return {"event": ev}


@router.post("/api/combat/{cid}/credit")
async def credit(request: Request, cid: str, body: dict):
    """Give a defeated foe's Glory to a knight (or to nobody): the answer to
    "Who defeated them?" and the strip's "Reassign Glory"."""
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c) or not B.is_defeated(c.status):
        bad("Only a defeated foe's Glory can be credited")
    pid = body.get("knight")
    k = None
    if pid:
        k = next((x for x in cs["combatants"] if not _is_foe(x) and x.party_id == pid), None)
        if k is None:
            bad("That knight isn't in the fight")
    g = B.glory_for(c)
    line = (f"+{g} Glory · {k.display_name} defeated {c.display_name}" if k
            else f"No Glory for {c.display_name}")
    data = {"fight": cs["started_event"], "cid": cid, "knight": pid or None,
            "knight_name": k.display_name if k else "", "foe": c.display_name, "amount": g if k else 0,
            "table_text": line}
    if k:
        data.update(touches=[pid], glory_amount=g)
    ev = state.record("glory.reassigned", line, title="Glory", data=data)
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
            height = _height(cs, c)
            common["extra"].update(attack=int(key), height=height)
            label = atk["weapon"] + (f" (Height {height:+d})" if height else "")
            ev = record_check(state, label=label, value=atk["value"],
                              modifier=c.modifier + height, **common)
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
    k = _engaged_knight(cs, c)
    minus5 = -5 if (k is not None and k.mounted and not c.mounted) else 0
    roll_, outcome, line = surrender_check(c, modifier=minus5)
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
    target = _combatant(cs, body["target"]) if body.get("target") else None
    was = bool(target and B.is_defeated(target.status))
    ev = record_blow(state, cs, body)
    return {"event": ev, "prompt": _who_defeated(state, target.id, was) if target else None}


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

    if target is not None and not _is_foe(target):
        return _report_blow_on_knight(state, attacker, target, weapon, expr, rolled, extra, body)

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
    suffix, gextra = "", {}
    if target:
        tgt = Combatant.from_dict(target.to_dict())      # a copy, just for the text
        old, msg = tgt.apply_hp(-b["wound"]) if b["wound"] else (tgt.cur_hp, "")
        suffix, gextra = _defeat_note(cs, B.is_defeated(target.status), tgt)
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
            "table_text": table + suffix, **gextra}
    return state.record("combat.blow", text + suffix, title=title, data=data)


def _report_blow_on_knight(state, attacker, knight, weapon, expr, rolled, extra, body):
    """An enemy's blow on a player knight: roll and report its damage (+4D6 on
    a critical) and which protection applies. Nothing is applied — players
    keep their knights' Hit Points on paper."""
    b = resolve_blow(expr=expr, rolled=rolled, critical=bool(body.get("critical")),
                     reckless=bool(body.get("reckless")), extra=extra,
                     rebated=bool(body.get("rebated")))
    shield = bool(body.get("shield"))
    who = attacker.display_name if attacker else ""
    head = f"{who}’s {weapon or 'blow'}" if who else (weapon or "A blow")
    crit = "CRITICAL " if b["critical"] else ""
    protect = "armour + shield/parry apply" if shield else "armour only, no shield/parry"
    text = f"{head} {crit}hits {knight.display_name} for {b['damage']} damage ({blow_breakdown(b).rsplit(' → ', 1)[0]}) — {protect}"
    return state.record("combat.blow", text, title=f"{who + ' → ' if who else ''}{knight.display_name}",
                        data={"cid": knight.id, "delta": 0, "attacker": who, "weapon": weapon or "",
                              "target": knight.display_name, "blow": b, "to_knight": True,
                              "knight_shield": shield, "breakdown": blow_breakdown(b),
                              "table_text": text, "touches": [knight.party_id]})


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
    if _is_foe(knight):
        bad("Choose a player knight")
    try:
        r = resolve_attack(roll["data"]["outcome"], body.get("knight"))
    except ValueError as exc:
        bad(str(exc))
    both = roll["data"]["outcome"] == "success"
    k_text = {"critical": "critical", "higher": "success (higher roll)" if both else "success",
              "equal": "success (equal roll)" if both else "success",
              "lower": "success (lower roll)" if both else "success",
              "failure": "failure", "fumble": "fumble"}[body["knight"]]
    verdict = {"foe": f"{foe.display_name} wins", "knight": f"{knight.display_name} wins",
               "tie": "tie — both strike", "none": "both miss"}[r["result"]]
    if r["result"] in ("knight", "tie"):
        verdict += f"; {foe.display_name} gets {'armour + shield' if r['knight_shield'] else 'armour only'}"
    for who in r["fumbled"]:
        verdict += f"; {(foe if who == 'foe' else knight).display_name} drops or breaks their weapon"
    ev = state.record("combat.attack",
                      f"{foe.display_name} {roll['data']['outcome']} vs {knight.display_name} {k_text} → {verdict}",
                      title=f"{foe.display_name} vs {knight.display_name}",
                      data={"verdict": verdict, "result": r["result"], "knight_shield": r["knight_shield"],
                            "touches": [knight.party_id]})
    blow_ev = None
    if r["foe_strike"]:
        blow_ev = record_blow(state, state.combat_state(), {
            "attacker": foe.id, "attack": roll["data"]["attack"], "target": knight.id,
            **r["foe_strike"]})
    return {"event": ev, "blow": blow_ev, "result": r["result"], "knight_shield": r["knight_shield"]}

