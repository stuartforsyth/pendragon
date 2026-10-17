"""The live battle: launch, muster, army rolls, Intensity, Morale, settings,
decks, pause and resume (S6). The turn loop's outcomes arrive through one
entry point, ``record_outcome`` (``POST /api/battle/step``, S7) — a future
player-dice source calls the same function.

Every route validates, builds a player-safe ``table_text``, and records an
event; ``web.battle_state`` replays them.
"""

import copy
import secrets

from fastapi import APIRouter, Request

from core import battle as B
from core import battle_def as BD
from core.dice import resolve_skill
from core.rules import roll_expr
from web import battle_state as BS
from web.routes.common import bad, st, to_int
from web.sessions import live_events

router = APIRouter()


def _live(request):
    state = st(request)
    b = state.battle_state()
    if not BS.is_live(b):
        bad("No battle in progress", 409)
    return state, b


def _link(b, step=None):
    return {"id": b["id"], "day": b["day"], "turn": b["turn"], "step": step}


def _name(b):
    return b["definition"].get("name") or "The battle"


def _party_name(state, pid):
    if pid == "gm":
        return "the GM"
    m = state.party.get(pid or "")
    return m["name"] if m else "a knight"


def _card(state, key):
    """A battle encounter's card, snapshotted into events for replay."""
    d = state.combat_data.get("encounters", {}).get(key)
    if not d or not d.get("battle_role"):
        bad(f"'{key}' isn't a battle encounter")
    from core.encounter_def import to_editable
    advs = state.combat_data.get("adversaries", {})
    ed = to_editable(d)
    mm, loss = B.default_morale(ed, advs)
    return {"role": d["battle_role"], "description": d.get("description", ""),
            "morale_minimum": d.get("morale_minimum") if d.get("morale_minimum") is not None else mm,
            "morale_loss": d.get("morale_loss") or loss, "missile": bool(d.get("missile")),
            "countercharge": B.has_countercharge(ed, advs), "mounted_charge": B.mounted_charge_card(ed, advs),
            "has_roster": bool(ed["roster"] or ed.get("leader")), "rules": d.get("rules", "")}


# -- reading -------------------------------------------------------------------

@router.get("/api/battle")
def get_battle(request: Request):
    state = st(request)
    return {"battle": BS.gm_view(state.battle_state(), state.party.items)}


@router.get("/api/battle/paused")
def paused(request: Request):
    state = st(request)
    return {"paused": BS.paused_battles(state.sessions, state.session.id)}


# -- launch, pause, resume ---------------------------------------------------------

def _no_running(state):
    if BS.is_live(state.battle_state()):
        bad("A battle is running — pause or finish it first", 409)


@router.post("/api/battle/start")
async def start(request: Request, body: dict):
    state = st(request)
    _no_running(state)
    key = body.get("key")
    if key:
        saved = state.combat_data.get("battles", {}).get(key)
        if saved is None:
            bad("No such battle", 404)
        definition = copy.deepcopy(saved)
    else:
        q = body.get("quick") or {}
        try:
            definition = BD.quick_battle(q.get("size"), q.get("days", 1), q.get("name", ""),
                                         q.get("where", ""), q.get("against", ""), q.get("notes", ""))
        except ValueError as exc:
            bad(str(exc))
    knights = [m["id"] for m in state.party.items if m.get("active", True)]
    size = B.SIZES[definition["size"]]["label"]
    days = len(definition["days"])
    name = definition["name"] or "The battle"
    line = f"{name} begins — {size}, {days} day{'s' if days != 1 else ''}"
    bid = secrets.token_hex(4)
    ev = state.record("battle.started", line, title=name,
                      data={"id": bid, "definition": definition, "source_key": key or None, "knights": knights,
                            "table_text": line, "battle": {"id": bid, "day": 1, "turn": 0, "step": None}})
    return {"event": ev}


@router.post("/api/battle/pause")
async def pause(request: Request):
    state, b = _live(request)
    m = b["morale"]
    ev = state.record("battle.paused", f"Battle paused: {_name(b)}", title="Battle paused", visibility="gm",
                      data={"summary": {"name": _name(b), "day": b["day"], "turn": b["turn"],
                                        "morale": [m["current"], m["start"]] if m else None},
                            "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/resume")
async def resume(request: Request, body: dict):
    """Carry a paused battle into this session: its state (and any fight in
    progress) rebuilt from the session where it was paused, as a snapshot."""
    state = st(request)
    _no_running(state)
    sid, bid = body.get("session_id"), body.get("battle_id")
    if sid == state.session.id:
        b = state.battle_state()
        if not b or b["id"] != bid or b["status"] != "paused":
            bad("No such paused battle", 404)
        events = live_events(state.session.events)
    else:
        try:
            src = state.sessions.load(sid or "")
        except (KeyError, OSError):
            bad("No such session", 404)
        events = live_events(src.events)
        b = BS.reduce(events)
        if not b or b["id"] != bid or b["status"] != "paused":
            bad("No such paused battle", 404)
    from web import combat_state
    cs = combat_state.reduce(events, state.rules.combat.get("promotion", {}))
    snap = BS.snapshot(b, cs)
    ev = state.record("battle.resumed", f"Battle resumed: {_name(b)} — Day {b['day']}, Turn {b['turn']}",
                      title="Battle resumed", visibility="gm",
                      data={"snapshot": snap, "from_session": sid, "battle": _link(b)})
    return {"event": ev}


# -- mustering -------------------------------------------------------------------

def _mustering(request):
    state, b = _live(request)
    if b["status"] != "mustering":
        bad("The conroi has already mustered", 409)
    return state, b


@router.post("/api/battle/army-roll")
async def army_roll(request: Request, body: dict):
    state, b = _mustering(request)
    size = b["definition"]["size"]
    if not B.SIZES[size]["army_rolls"]:
        bad("Army Commander rolls are for a Clash or larger")
    side = body.get("side")
    if side not in ("friendly", "enemy"):
        bad("Which side — friendly or enemy?")
    roll = None
    if body.get("roll_for_me") is not None:
        rf = body["roll_for_me"] or {}
        rolled = rf.get("battle") in (None, "")
        value = roll_expr(B.DEFAULT_BATTLE) if rolled else to_int(rf["battle"], "Battle")
        mods = to_int(rf.get("mods") or 0, "modifiers")
        die, outcome = resolve_skill(value + mods)
        roll = {"value": value, "value_rolled": rolled, "mods": mods, "roll": die}
    else:
        outcome = body.get("outcome")
        if outcome not in B.OUTCOMES:
            bad("Choose Critical, Success, Failure or Fumble")
    return {"event": _record_army(state, b, side, outcome, roll)}


_ARMY_TEXT = {
    ("friendly", "critical"): "turn 1 opens with a mounted charge", ("friendly", "success"): "turn 1 opens with a mounted charge",
    ("friendly", "failure"): "no opening charge", ("friendly", "fumble"): "no opening charge, and the army is −5 Battle on turn 1",
    ("enemy", "critical"): "the enemy may force one Encounter today", ("enemy", "success"): "the enemy may force one Encounter today",
    ("enemy", "failure"): "no advantage to the enemy", ("enemy", "fumble"): "the conroi may shrug off one Encounter's Morale loss today",
}


def _record_army(state, b, side, outcome, roll=None):
    names = b["definition"].get("army_commanders", {})
    who = (names.get(side) or {}).get("name") or ("The friendly commander" if side == "friendly" else "The enemy commander")
    line = f"{who}'s Battle roll: {outcome.capitalize()} — {_ARMY_TEXT[(side, outcome)]}"
    gm = line + (f" (Battle {roll['value']}{roll['mods']:+d}, rolled {roll['roll']})" if roll else "")
    return state.record("battle.army_roll", gm, title="Army Commander",
                        data={"day": b["day"], "side": side, "outcome": outcome, "roll": roll,
                              "table_text": line, "battle": _link(b)})


@router.post("/api/battle/day")
async def day(request: Request, body: dict):
    """Today's Intensity: entered, or rolled from the Size (Table 6.1)."""
    state, b = _mustering(request)
    size = b["definition"]["size"]
    if body.get("roll_for_me"):
        dice = B.SIZES[size]["intensity"]
        value, rolled = roll_expr(dice), True
    else:
        value, rolled, dice = to_int(body.get("intensity"), "Intensity"), False, None
        if not 1 <= value <= 40:
            bad("Intensity is 1 to 40")
    line = f"Day {b['day']} — Intensity {value}"
    ev = state.record("battle.day_started", line, title=_name(b),
                      data={"day": b["day"], "intensity": value, "rolled": rolled, "dice": dice,
                            "table_text": line, "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/muster")
async def muster(request: Request, body: dict):
    state, b = _mustering(request)
    knights = [p for p in body.get("knights") or [] if state.party.get(p)]
    if not knights:
        bad("Choose the knights in the conroi")
    commander = body.get("commander")
    if commander != "gm" and commander not in knights:
        bad("Choose a commander from the conroi, or the GM")
    start_m = to_int(body.get("start"), "starting Morale")
    if start_m < 1:
        bad("Enter the starting Morale the players worked out")
    if str(b["day"]) not in b["intensity"]:
        fixed = (BS._day_def(b).get("intensity") or {})
        if fixed.get("mode") == "fixed" and fixed.get("value"):
            state.record("battle.day_started", f"Day {b['day']} — Intensity {fixed['value']}", title=_name(b),
                         data={"day": b["day"], "intensity": int(fixed["value"]), "rolled": False, "dice": None,
                               "table_text": f"Day {b['day']} — Intensity {fixed['value']}", "battle": _link(b)})
        else:
            bad("Set today's Intensity", 409)
    if B.SIZES[b["definition"]["size"]]["army_rolls"]:
        presets = BS._day_def(b).get("commanders") or {}
        answered = b["army"].get(str(b["day"]), {})
        for side in ("friendly", "enemy"):
            if presets.get(side) and side not in answered:
                _record_army(state, b, side, presets[side])
    passion = (body.get("passion") or "").strip()
    who = _party_name(state, commander)
    line = f"The conroi musters — Morale {start_m}" + (f" ({passion})" if passion else "") + f", led by {who}"
    ev = state.record("battle.mustered", line, title=_name(b),
                      data={"day": b["day"], "start": start_m, "passion": passion, "commander": commander,
                            "knights": knights, "table_text": line, "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/commander")
async def commander(request: Request, body: dict):
    state, b = _live(request)
    c = body.get("commander")
    if c != "gm" and c not in b["conroi"]:
        bad("Choose a knight in the conroi, or the GM")
    line = f"{_party_name(state, c).capitalize() if c == 'gm' else _party_name(state, c)} now leads the conroi"
    ev = state.record("battle.commander", line, title=_name(b),
                      data={"commander": c, "table_text": line, "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/morale")
async def morale(request: Request, body: dict):
    """The GM's Morale override: a change (capped at the starting value) or a
    new starting value — always with a reason, always logged."""
    state, b = _live(request)
    if not b["morale"]:
        bad("Muster the conroi first", 409)
    reason = (body.get("reason") or "").strip()
    if not reason:
        bad("Say why Morale changes")
    m = b["morale"]
    if body.get("start") not in (None, ""):
        new_start = to_int(body["start"], "starting Morale")
        if new_start < 1:
            bad("Starting Morale must be at least 1")
        line = f"Starting Morale set to {new_start} · {reason}"
        data = {"delta": None, "start": new_start}
    else:
        delta = to_int(body.get("delta"), "change")
        if not delta:
            bad("Enter a change, e.g. +2 or −3")
        after = B.apply_morale(m["current"], m["start"], delta)
        capped = " (capped)" if after != m["current"] + delta else ""
        line = f"Morale {delta:+d} · {reason} ({after} of {m['start']}){capped}"
        data = {"delta": delta, "start": None}
    ev = state.record("battle.morale_adjust", line, title="Morale",
                      data={**data, "reason": reason, "table_text": line, "battle": _link(b)})
    return {"event": ev}


# -- live edits ---------------------------------------------------------------------

_PATCH_KEYS = ("intensity", "turns", "first_charge", "on_foot", "no_charge", "commanders", "notes", "scripts", "deck")


@router.post("/api/battle/settings")
async def settings(request: Request, body: dict):
    state, b = _live(request)
    size = b["definition"]["size"]
    encs = state.combat_data.get("encounters", {})
    if body.get("add_day"):
        try:
            new_day = BD.clean_day(body["add_day"], size, encs, [], "New day")
        except ValueError as exc:
            bad(str(exc))
        data = {"add_day": new_day}
        line = f"Battle settings: Day {len(b['definition']['days']) + 1} added"
    else:
        d = to_int(body.get("day", b["day"]), "day")
        if d < 1:
            bad("No such day", 404)
        if d < b["day"]:
            bad("Past days are locked", 409)
        if d > len(b["definition"]["days"]):
            bad("No such day", 404)
        patch = {k: v for k, v in (body.get("patch") or {}).items() if k in _PATCH_KEYS}
        merged = {**b["definition"]["days"][d - 1], **patch}
        try:
            clean = BD.clean_day(merged, size, encs, [], f"Day {d}")
        except ValueError as exc:
            bad(str(exc))
        data = {"day": d, "patch": {k: clean[k] for k in patch}}
        line = f"Battle settings: Day {d} — " + ", ".join(patch) if patch else f"Battle settings: Day {d}"
    ev = state.record("battle.settings", line, title="Battle settings", visibility="gm",
                      data={**data, "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/deck")
async def deck(request: Request, body: dict):
    state, b = _live(request)
    d = to_int(body.get("day") or b["day"], "day")
    if d < b["day"]:
        bad("Past days are locked", 409)
    add = [k for k in body.get("add") or []]
    remove = [k for k in body.get("remove") or []]
    cards = {k: _card(state, k) for k in add}
    names = ", ".join(add)
    line = (f"New foes join the field: {names}" if add else f"Withdrawn from the field: {', '.join(remove)}")
    ev = state.record("battle.deck", line, title=_name(b),
                      data={"day": d, "add": add, "remove": remove, "cards": cards,
                            "table_text": line, "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/quick-encounter")
async def quick_encounter(request: Request, body: dict):
    """+ New encounter mid-battle: saved to the library and added to today's deck."""
    state, b = _live(request)
    from web.routes.library import _clean_encounter
    defn = body.get("definition") or {}
    d = _clean_encounter(defn, state.combat_data.get("adversaries", {}))
    if not d["name"]:
        bad("Give the encounter a name")
    if not d.get("battle_role"):
        bad("Mark it as a Foe or an Opportunity")
    encs = state.combat_data.setdefault("encounters", {})
    if d["name"] in encs:
        bad(f"An encounter named '{d['name']}' exists", 409)
    encs[d["name"]] = d
    state.save_combat_data()
    state.notify("library")
    return await deck(request, {"day": b["day"], "add": [d["name"]]})


@router.post("/api/battle/template")
async def template(request: Request, body: dict):
    """Save as template: the live definition (no live state) into Battles."""
    state, b = _live(request)
    name = (body.get("name") or "").strip()
    if not name:
        bad("Name the template")
    bs = state.combat_data.setdefault("battles", {})
    if name in bs and not body.get("overwrite"):
        bad(f"A battle named '{name}' exists", 409)
    d = copy.deepcopy(b["definition"])
    d.update(name=name, source="user")
    try:
        clean, _ = BD.clean_battle(d, state.combat_data.get("encounters", {}))
    except ValueError as exc:
        bad(str(exc))
    bs[name] = clean
    state.save_combat_data()
    state.notify("library")
    return {"key": name}


@router.post("/api/battle/script")
async def script(request: Request, body: dict):
    """Show an unconditional turn script on the Table (Q20)."""
    state, b = _live(request)
    d = to_int(body.get("day") or b["day"], "day")
    i = to_int(body.get("index"), "script")
    scripts = BS._day_def(b, d).get("scripts", [])
    if not 0 <= i < len(scripts):
        bad("No such script", 404)
    if any(s.get("day") == d and s.get("index") == i for s in b["revealed_scripts"]):
        bad("Already shown", 409)
    text = scripts[i]["text"]
    ev = state.record("battle.script", text, title=_name(b),
                      data={"day": d, "index": i, "text": text, "table_text": text, "battle": _link(b)})
    return {"event": ev}


@router.post("/api/battle/knight/{pid}")
async def knight(request: Request, pid: str, body: dict):
    state, b = _live(request)
    if pid not in b["knights"]:
        bad("That knight isn't in this battle", 404)
    name = _party_name(state, pid)
    if "mounted" in body:
        on = bool(body["mounted"])
        line = f"{name} is {'mounted' if on else 'on foot'}"
        ev = state.record("battle.mounted", line, title=name,
                          data={"pid": pid, "mounted": on, "table_text": line, "touches": [pid], "battle": _link(b)})
        return {"event": ev}
    pos = body.get("position")
    if pos not in ("conroi", "rear", "alone", "left"):
        bad("Position is with the conroi, at the rear, alone on the field, or left the field")
    words = {"conroi": "rides with the conroi", "rear": "is at the rear", "alone": "is alone on the field",
             "left": "has left the field"}
    line = f"{name} {words[pos]}"
    ev = state.record("battle.position", line, title=name,
                      data={"pid": pid, "position": pos, "table_text": line, "touches": [pid], "battle": _link(b)})
    return {"event": ev}


# -- the turn loop's single outcome entry point (S7 fills it in) ---------------------

def record_outcome(state, step, payload, source="gm"):
    """Every outcome a player reports goes through here — the GM today, a
    dice source in a later phase (``source="dice"``)."""
    bad("The turn loop arrives in the next build", 501)


@router.post("/api/battle/step")
async def step(request: Request, body: dict):
    state, b = _live(request)
    return record_outcome(state, body.get("step"), body, source="gm")
