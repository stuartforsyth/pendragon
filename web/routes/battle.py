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
    return {"battle": state.gm_battle()}


@router.get("/api/battle/paused")
def paused(request: Request):
    state = st(request)
    return {"paused": BS.paused_battles(state.sessions, state.session.id)}


# -- launch, pause, resume ---------------------------------------------------------

def _no_running(state):
    b = state.battle_state()
    if BS.is_live(b):
        where = "at Mustering" if b["status"] == "mustering" else f"Day {b['day']}, Turn {b['turn']}"
        bad(f"A battle is already running: {_name(b)} ({where})", 409)


def _close_current(state, b):
    """Close the running battle so another can launch: one still at Mustering
    is called off (nothing was played); one that has begun is paused, so it
    can be resumed later from the Battle tool."""
    if b["status"] == "mustering":
        state.record("battle.ended", f"{_name(b)} is called off before it began", title=_name(b), visibility="gm",
                     data={"abandoned": True, "battle": _link(b)})
    else:
        m = b["morale"]
        state.record("battle.paused", f"Battle paused: {_name(b)}", title="Battle paused", visibility="gm",
                     data={"summary": {"name": _name(b), "day": b["day"], "turn": b["turn"],
                                       "morale": [m["current"], m["start"]] if m else None},
                           "battle": _link(b)})


@router.post("/api/battle/start")
async def start(request: Request, body: dict):
    state = st(request)
    running = state.battle_state()
    if BS.is_live(running) and body.get("close_current"):
        _close_current(state, running)
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
    knights = [m["id"] for m in state.present_party()]
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


@router.post("/api/battle/abandon")
async def abandon(request: Request):
    """Call off a battle that never got past Mustering (launched by mistake,
    or to test): it ends there and then, and the Battle tool is free again."""
    state, b = _live(request)
    if b["status"] != "mustering":
        bad("The battle has begun — pause it, or play it out to the aftermath", 409)
    ev = state.record("battle.ended", f"{_name(b)} is called off before it began", title=_name(b), visibility="gm",
                      data={"abandoned": True, "battle": _link(b)})
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


@router.post("/api/battle/duplicate")
async def duplicate(request: Request, body: dict):
    """Copy a paused battle's saved session to a new one (its own battle id): the original stays as it is,
    the copy is there to be tried, played and deleted."""
    state = st(request)
    sid, bid = body.get("session_id"), body.get("battle_id")
    try:
        src = state.sessions.load(sid or "")
    except (KeyError, OSError):
        bad("No such session", 404)
    b = BS.reduce(live_events(src.events))
    if not b or b["id"] != bid or b["status"] != "paused":
        bad("No such paused battle", 404)
    try:
        copy = state.sessions.duplicate(sid, body.get("title"), bid)
    except ValueError as exc:
        bad(str(exc), 409)
    state.notify("session")
    return {"session": copy.meta()}


# -- mustering -------------------------------------------------------------------

def _mustering(request):
    state, b = _live(request)
    if b["status"] != "mustering":
        bad("The conroi has already mustered", 409)
    return state, b


@router.post("/api/battle/army-roll")
async def army_roll(request: Request, body: dict):
    state, b = _live(request)            # correctable all day, not only at Mustering
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
    """Today's Intensity: entered, or rolled from the Size (Table 6.1) —
    and overridable at any time during the day (piece 1, U5)."""
    state, b = _live(request)
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


@router.post("/api/battle/conroi")
async def conroi(request: Request, body: dict):
    """Edit the muster after Begin: who rides in the conroi, the Passion, the
    starting Morale. Everything stays editable while the battle runs."""
    state, b = _live(request)
    if b["status"] == "mustering":
        bad("Set these on the Mustering screen", 409)
    data, bits = {}, []
    if "knights" in body:
        knights = [p for p in body.get("knights") or [] if state.party.get(p)]
        if not knights:
            bad("The conroi needs at least one knight")
        data["knights"] = knights
        bits.append("rides with " + ", ".join(_party_name(state, p) for p in knights))
    if "passion" in body:
        data["passion"] = (body.get("passion") or "").strip()
        bits.append(f"Passion {data['passion'] or '—'}")
    if body.get("start") not in (None, ""):
        data["start"] = to_int(body["start"], "starting Morale")
        if data["start"] < 1:
            bad("Starting Morale must be at least 1")
        bits.append(f"starting Morale {data['start']}")
    if not data:
        bad("Nothing to change")
    line = "The conroi: " + "; ".join(bits)
    ev = state.record("battle.conroi", line, title="The conroi", data={**data, "table_text": line, "battle": _link(b)})
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

_PATCH_KEYS = ("intensity", "turns", "first_charge", "no_charge", "commanders", "notes", "scripts", "deck")


@router.post("/api/battle/settings")
async def settings(request: Request, body: dict):
    state, b = _live(request)
    size = b["definition"]["size"]
    encs = state.combat_data.get("encounters", {})
    if body.get("battle_patch"):
        bp = body["battle_patch"]
        patch = {k: str(bp[k] or "").strip() for k in ("name", "where", "against", "notes") if k in bp}
        if "size" in bp:
            if bp["size"] not in B.SIZES:
                bad("Choose a battle size")
            patch["size"] = bp["size"]
        if "name" in patch and not patch["name"]:
            bad("The battle needs a name")
        ev = state.record("battle.settings", "Battle settings: " + ", ".join(f"{k} → {v}" for k, v in patch.items()),
                          title="Battle settings", visibility="gm", data={"battle_patch": patch, "battle": _link(b)})
        return {"event": ev}
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


@router.post("/api/battle/mounted")
async def all_mounted(request: Request, body: dict):
    """All on foot / all mounted, at Mustering: one event for the listed knights."""
    state, b = _live(request)
    on = bool(body.get("mounted"))
    pids = [p for p in (body.get("pids") or b["conroi"]) if p in b["knights"] and b["knights"][p]["mounted"] != on]
    if not pids:
        return {"event": None}
    line = f"The conroi {'mounts up' if on else 'fights on foot'}"
    ev = state.record("battle.mounted", line, title="The conroi",
                      data={"pids": pids, "mounted": on, "table_text": line, "touches": pids, "battle": _link(b)})
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


# -- the turn loop: one outcome entry point ---------------------------------------

_POSTURE_WORD = {"reckless": "Reckless", "valorous": "Valorous", "prudent": "Prudent", "cowardly": "Cowardly"}


def _today_deck(state, b, role="foe"):
    """Today's (script-restricted) deck; empty means every battle encounter."""
    deck = BS.effective_deck(b, state.combat_data.get("encounters", {}))
    return deck["opportunities"] if role == "opportunity" else deck["foes"]


_STEP_TITLE = {"field": "The conroi", "set": "This turn", "charge": "The charge", "intensity": "Intensity",
               "picks": "A pick", "select": "The commander's choice", "morale": "Morale", "opportunity": "The Opportunity", "postures": "Posture",
               "rest": "At the rear", "fight": "The fight", "end": "End of the turn"}


def _rec(state, b, etype, text, step, data, table=None, title=None, visibility="public"):
    title = title or (_STEP_TITLE.get(step) if step else None) or ("Passion" if etype == "battle.passion" else _name(b))
    return state.record(etype, text, title=title, visibility=visibility,
                        data={**data, "table_text": table or text, "battle": _link(b, step)})


def _not_now(why):
    bad(f"Not now: {why}", 409)


def _pid_name(state, pid):
    return _party_name(state, pid)


def record_outcome(state, step, payload, source="gm"):
    """Every outcome a player reports goes through here — the GM today, a
    dice source in a later phase (``source="dice"``). Validates against the
    step machine and records one event (two for End day)."""
    b = state.battle_state()
    if not BS.is_live(b) or b["status"] == "mustering":
        bad("No turn in progress", 409)
    cur = BS.current_step(b)
    t = b["t"]
    m = b["morale"] or {"current": 0, "start": 0}
    src = {"source": source}
    evs = []

    def rec(etype, text, st, data, **kw):
        evs.append(_rec(state, b, etype, text, st, {**data, **src}, **kw))

    if step == "retire":
        if b["status"] != "turn" or cur != "set":
            _not_now("the conroi retires at the start of a turn")
        rec("battle.field", "The conroi retires to the rear", "field", {"choice": "retire"})
    elif step == "rear":
        choice = payload.get("choice")
        if b["status"] != "rear" or cur != "field":
            _not_now("the conroi isn't at the rear")
        if choice not in ("rest", "return", "leave"):
            bad("Rest, return or leave")
        words = {"rest": "The conroi rests another turn", "return": "The conroi returns to the field",
                 "leave": "The conroi leaves the field"}
        rec("battle.field", words[choice], "field", {"rear_choice": choice})
    elif step == "rest":
        if cur != "rest":
            _not_now("rest comes after retiring")
        rolled = bool(payload.get("roll_for_me"))
        amount = roll_expr("1D6") if rolled else to_int(payload.get("amount"), "rest roll")
        if not 1 <= amount <= 6:
            bad("A rest roll is 1D6: 1 to 6")
        after = B.apply_morale(m["current"], m["start"], amount)
        line = f"Rest at the rear: Morale +{after - m['current']} ({after} of {m['start']})"
        rec("battle.rest", line, "rest", {"amount": amount, "rolled": rolled})
    elif step == "set":
        if cur != "set" or b["status"] != "turn":
            _not_now("the Encounter is set at the start of a turn")
        if m["current"] <= 0:
            _not_now("Morale is 0 — the conroi must retire to the rear")
        deck = _today_deck(state, b)
        if payload.get("draw"):
            import random
            if not deck:
                bad("No foes in today's deck")
            key, drawn = random.choice(deck), True
        else:
            key, drawn = payload.get("encounter"), False
            if key not in deck:
                bad(f"'{key}' isn't a Foe in today's deck")
        forced = bool(payload.get("forced"))
        if forced and BS.tokens(b)["force"] != "available":
            bad("No Force Encounter token available")
        card = _card(state, key)
        flavour = (payload.get("flavour") or card.get("description") or "").strip()
        line = f"This turn: {key}" + (f" — {flavour}" if flavour else "")
        gm = line + (" (drawn)" if drawn else "") + (" — forced by the enemy commander" if forced else "")
        rec("battle.set", gm, "set", {"encounter": key, "card": card, "flavour": flavour, "drawn": drawn, "forced": forced},
            table=line + (" — the enemy forces the issue!" if forced else ""))
    elif step == "charge":
        if cur != "charge":
            _not_now("the charge roll comes after the Encounter is set")
        if payload.get("skip"):                   # no charge possible this turn (terrain, all on foot…): don't roll
            rec("battle.charge", "Charge: not rolled — no charge possible this turn", "charge",
                {"outcome": None, "engaged_last": None, "result": "no_charge", "skipped": True, "lines": []},
                table="No charge this turn")
            return {"events": evs, "battle": state.gm_battle()}
        outcome = payload.get("outcome")
        if outcome not in B.OUTCOMES:
            bad("Choose Critical, Success, Failure or Fumble")
        engaged = bool(payload.get("engaged_last"))
        result = B.charge_opportunity(outcome, engaged)
        if result == "enemy_charge":
            eligible = [k for k in _today_deck(state, b) if _card(state, k)["mounted_charge"]]
            if not eligible:
                result = "no_charge"              # no mounted knights in the enemy army: a simple failure
        lines = []
        for pid in BS.conroi_ids(b):
            lines.append(f"{_pid_name(state, pid)}: {B.charge_line(result, b['knights'][pid]['mounted'])}")
        head = {"may_charge_plus5": "Charge! (+5)", "may_charge": "Mounted knights may charge", "no_charge": "No charge",
                "enemy_charge": "Enemy knights charge you!"}[result]
        rec("battle.charge", f"Charge roll: {outcome.capitalize()} — {head}", "charge",
            {"outcome": outcome, "engaged_last": engaged, "result": result, "lines": lines},
            table=f"{head} — " + "; ".join(lines) if lines else head)
    elif step == "intensity":
        if cur != "intensity":
            _not_now("the Intensity roll comes after the charge")
        roll = None
        if payload.get("roll_for_me"):
            value = b["intensity"].get(str(b["day"]))
            die, outcome = resolve_skill(int(value))
            roll = {"roll": die, "value": value}
        else:
            outcome = payload.get("outcome")
            if outcome not in B.OUTCOMES:
                bad("Choose Critical, Success, Failure or Fumble")
        words = {"critical": "Critical — the Encounter stands, and the foes are doubled!",
                 "success": "Success — the Encounter stands", "failure": "Failure — the knights may choose their fate",
                 "fumble": "Fumble — an Opportunity, at the GM's choice"}
        line = f"Intensity roll: {words[outcome]}"
        rec("battle.intensity", line + (f" (rolled {roll['roll']} vs {roll['value']})" if roll else ""), "intensity",
            {"outcome": outcome, "roll": roll}, table=line)
    elif step == "pick":
        if cur != "picks":
            _not_now("picks follow a failed Intensity roll")
        pid = payload.get("knight")
        if pid not in BS.conroi_ids(b):
            bad("Only knights with the conroi pick")
        key = payload.get("encounter")
        crit = bool(payload.get("crit"))
        card = None
        if key:
            card = _card(state, key)
            if card["role"] == "opportunity":
                if not crit:
                    bad("An Opportunity needs a critical Battle roll")
                if key in b["spent_opportunities"]:
                    bad(f"{key} was already played in this battle")
                if key not in _today_deck(state, b, "opportunity"):
                    bad(f"'{key}' isn't in today's deck")
            elif key not in _today_deck(state, b):
                bad(f"'{key}' isn't in today's deck")
        who = _pid_name(state, pid)
        line = (f"{who}{' (critical)' if crit else ''} picks {key}{' ★' if card and card['role'] == 'opportunity' else ''}"
                if key else f"{who} withdraws their pick")
        rec("battle.pick", line, "picks", {"knight": pid, "encounter": key, "card": card, "crit": crit, "touches": [pid]})
    elif step == "select":
        if cur not in ("select", "picks"):
            _not_now("the commander chooses after the picks")
        via = payload.get("via", "commander")
        key = payload.get("encounter")
        set_key = t["set"]["encounter"]
        if via == "keep":
            if t["picks"]:
                bad("Knights have picked — choose one of them or the set Encounter")
            key = set_key
        elif via == "fumble":
            if (t["intensity"] or {}).get("outcome") != "fumble":
                bad("Only an Intensity fumble brings an Opportunity")
            key = key or set_key
            if key != set_key:
                if key not in _today_deck(state, b, "opportunity") or key in b["spent_opportunities"]:
                    bad("Choose an unplayed Opportunity from today's deck")
        elif via == "enemy_charge":
            if not BS._enemy_charge_locked(b):
                bad("No enemy charge this turn")
            if not _card(state, key)["mounted_charge"]:
                bad("Enemy knights charging must be a mounted-knight Encounter")
        else:
            options = {set_key} | {p["encounter"] for p in t["picks"].values()}
            if key not in options:
                bad("Choose the set Encounter or one the knights picked")
            if any(state.combat_data.get("encounters", {}).get(p["encounter"], {}).get("battle_role") == "opportunity"
                   for p in t["picks"].values()):
                opp = [p["encounter"] for p in t["picks"].values()
                       if state.combat_data.get("encounters", {}).get(p["encounter"], {}).get("battle_role") == "opportunity"]
                if key not in opp:
                    bad(f"An Opportunity was picked — it must be played ({opp[0]})")
        card = _card(state, key)
        if via == "keep" or key == set_key:
            line = "No picks — the set Encounter stands" if via == "keep" else f"The commander keeps {key}"
        elif via == "enemy_charge":
            line = f"{key} charge the conroi!"
        else:
            line = f"The commander chooses {key}"
        rec("battle.select", line, "select", {"encounter": key, "card": card, "via": via})
    elif step == "morale":
        if cur != "morale":
            _not_now("Morale comes once the Encounter is chosen")
        enc, card = BS.chosen(b)
        kind = payload.get("kind", "loss")
        minimum = card.get("morale_minimum")
        if kind == "forced_retire":
            if not B.forced_retire(m["current"], minimum):
                bad("The conroi has the Morale to engage")
            rec("battle.morale", f"Not enough Morale for {enc} — Retire to the Rear", "morale",
                {"kind": "forced_retire", "amount": None, "rolled": False, "negated": False,
                 "reason": "zero" if m["current"] == 0 else "minimum"},
                table="Not enough Morale — Retire to the Rear")
        else:
            if B.forced_retire(m["current"], minimum):
                bad("Below this Encounter's Minimum Morale — the conroi must retire")
            if payload.get("negate"):
                if BS.tokens(b)["negate"] != "available":
                    bad("No Negate token available")
                rec("battle.morale", f"The enemy commander's blunder — no Morale lost to {enc}", "morale",
                    {"kind": "loss", "amount": 0, "rolled": False, "negated": True, "reason": None})
            else:
                rolled = bool(payload.get("roll_for_me"))
                dice = card.get("morale_loss") or ""
                if rolled:
                    amount = roll_expr(dice) if dice else 0
                else:
                    amount = to_int(payload.get("amount") or 0, "Morale loss")
                    if amount < 0:
                        bad("Morale loss can't be negative")
                after = B.apply_morale(m["current"], m["start"], -amount)
                line = f"Morale −{amount} · {enc} ({after} of {m['start']})" if amount else f"No Morale lost to {enc}"
                rec("battle.morale", line + (f" (rolled {dice})" if rolled else ""), "morale",
                    {"kind": "loss", "amount": amount, "rolled": rolled, "negated": False, "reason": None}, table=line)
    elif step == "posture":
        if cur != "postures":
            _not_now("postures come after Morale")
        pid = payload.get("knight")
        if pid not in BS.conroi_ids(b):
            bad("Only knights with the conroi take a posture")
        if pid in t["postures"]:
            bad("Already chosen this turn — reopen Postures to change it", 409)
        posture = payload.get("posture")
        if posture not in B.POSTURES:
            bad("Reckless, Valorous, Prudent or Cowardly")
        if BS.first_charge_turn(b) and posture not in B.FIRST_CHARGE_POSTURES:
            bad("The first charge allows only Reckless or Valorous")
        P = B.POSTURES[posture]
        above = payload.get("above_half")
        amount, rolled = None, False
        if P["dice"] and (posture != "cowardly" or above):
            if payload.get("roll_for_me"):
                amount, rolled = roll_expr(P["dice"]), True
            else:
                amount = to_int(payload.get("amount"), f"{P['dice']} roll")
            try:
                delta = B.posture_delta(posture, amount, bool(above))
            except ValueError as exc:
                bad(str(exc))
        else:
            delta = 0
        who = _pid_name(state, pid)
        line = f"{who} rides {_POSTURE_WORD[posture]} ({P['rounds']} round{'s' if P['rounds'] != 1 else ''})"
        if posture == "cowardly":
            line = f"{who} holds back — Cowardly, and rides to the rear"
        if delta:
            line += f" — Morale {delta:+d}"
        rec("battle.posture", line, "postures", {"knight": pid, "posture": posture, "amount": amount, "rolled": rolled,
                                                 "above_half": above, "touches": [pid]})
    elif step == "passion":
        pid = payload.get("knight")
        if pid not in b["conroi"]:
            bad("That knight isn't in the conroi")
        used = bool(payload.get("used", True))
        name = (payload.get("name") or "").strip()
        who = _pid_name(state, pid)
        line = f"{who} draws on {name or 'a Passion'}" if used else f"{who}'s Passion is unmarked"
        rec("battle.passion", line, None, {"knight": pid, "used": used, "name": name, "touches": [pid]})
    elif step == "barrage":
        enc, card = BS.chosen(b)
        if cur not in ("fight", "end") or not card.get("missile"):
            _not_now("a barrage is for a missile Encounter, before the fight")
        outcome = payload.get("outcome")
        if outcome not in B.OUTCOMES:
            bad("Choose Critical, Success, Failure or Fumble")
        rounds = B.barrage_rounds(outcome)
        lines = []
        for pid in BS.conroi_ids(b):
            p_ = t["postures"].get(pid, {}).get("posture")
            r = B.POSTURES.get(p_, {}).get("rounds", 0)
            lines.append(f"{_pid_name(state, pid)} " + ("reaches the archers" if B.reaches(r, 0, rounds)
                                                        else f"endures {min(r, rounds)} round{'s' if min(r, rounds) != 1 else ''}, turns back"))
        head = "The archers loose — no barrage, straight into contact" if not rounds else \
            f"The archers loose — {rounds} round{'s' if rounds != 1 else ''} of arrows before contact"
        rec("battle.barrage", f"{head}: " + "; ".join(lines), "fight", {"outcome": outcome, "rounds": rounds, "lines": lines})
    elif step == "countercharge":
        enc, card = BS.chosen(b)
        if cur not in ("fight", "end") or not card.get("countercharge"):
            _not_now("only lance-armed foes countercharge")
        if b["turn"] == 1:
            _not_now("on the day's first turn they always countercharge")
        rolled = bool(payload.get("roll_for_me"))
        roll = roll_expr("1D6") if rolled else to_int(payload.get("roll"), "1D6")
        if not 1 <= roll <= 6:
            bad("1D6: 1 to 6")
        yes = B.countercharge(False, roll)
        line = "They countercharge!" if yes else "No countercharge — their lances are spent"
        rec("battle.countercharge", f"{line} (1D6: {roll})", "fight", {"roll": roll, "rolled": rolled}, table=line)
    elif step == "opportunity_glory":
        if cur != "opportunity":
            _not_now("the Opportunity is being played")
        amount = to_int(payload.get("amount"), "Glory")
        if not amount:
            bad("Enter the Glory to award")
        reason = (payload.get("reason") or "").strip()
        if not reason:
            bad("Say what the Glory is for")
        who = BS.conroi_ids(b) if payload.get("knights") == "all" else list(payload.get("knights") or [])
        if not who or any(pid not in b["conroi"] for pid in who):
            bad("Choose the knights to award")
        for pid in who:
            name = _pid_name(state, pid)
            line = f"{amount:+d} Glory · {name} — {reason}"
            rec("glory.awarded", line, "opportunity",
                {"knight": pid, "knight_name": name, "amount": amount, "reason": reason, "fight": None,
                 "touches": [pid], "glory_amount": amount}, title="Glory")
    elif step == "opportunity_done":
        if cur != "opportunity":
            _not_now("the Opportunity is being played")
        enc = BS.chosen(b)[0]
        rec("battle.opportunity_done", f"{enc} is resolved", "opportunity", {"encounter": enc},
            table="The Opportunity is resolved")
    elif step == "extra_round":
        cs = state.combat_state()
        if not cs or not cs.get("active") or (cs.get("battle") or {}).get("id") != b["id"]:
            _not_now("no battle fight is running")
        pid = payload.get("knight")
        if not any(getattr(c, "party_id", None) == pid for c in cs["combatants"]):
            bad("That knight isn't in the fight")
        who = _pid_name(state, pid)
        rec("battle.extra_round", f"{who} fights on — one more round", "fight", {"knight": pid, "cid": f"p-{pid}", "touches": [pid]})
    elif step in ("end_turn", "end_day"):
        if cur != "end" and cur != "fight":
            _not_now("finish the turn's steps first")
        last = b["turn"] >= (BS._day_def(b).get("turns") or 1)
        if step == "end_turn" and last and b["status"] == "turn":
            bad("This is the day's last turn — End day")
        cs = state.combat_state()
        if cs and cs.get("active") and (cs.get("battle") or {}).get("id") == b["id"]:
            _not_now("end the fight first")
        gain = BS.kv_gain(b)
        after = B.apply_morale(m["current"], m["start"], gain)
        line = f"End of Turn {b['turn']}"
        if gain:
            line += f" — Morale +{after - m['current']} for foes defeated ({after} of {m['start']})"
        rec("battle.turn_ended", line, "end", {"kv_preview": gain})
        if step == "end_day":
            b2 = state.battle_state()
            days = len(b2["definition"]["days"])
            dline = f"Day {b['day']} ends" + ("" if b["day"] < days else " — the battle is done")
            evs.append(state.record("battle.day_ended", dline, title=_name(b),
                                    data={"table_text": dline, "battle": {**_link(b, "end")}, **src}))
    else:
        bad("Unknown step")
    return {"events": evs, "battle": state.gm_battle()}


@router.post("/api/battle/fight")
async def fight(request: Request):
    """⑨ Begin the fight: an ordinary tracked fight, linked to this turn,
    scaled to the knights with the conroi (Cowardly ones don't count) and
    doubled on an Intensity critical. Knights Alone on the Field get a lane."""
    state, b = _live(request)
    enc, card = BS.chosen(b)
    if (card or {}).get("role") == "opportunity":
        bad("An Opportunity is played at the table, then its Glory is awarded here", 409)
    if not BS.conroi_ids(b):
        _not_now("no knights are with the conroi")
    if BS.current_step(b) not in ("fight", "end") \
            or not all(pid in b["t"]["postures"] for pid in BS.conroi_ids(b)):
        _not_now("choose postures first")
    t = b["t"]
    if card.get("missile") and not t.get("barrage"):
        _not_now("record the commander's barrage roll first")
    if card.get("countercharge") and b["turn"] != 1 and not t.get("countercharge"):
        _not_now("check whether they countercharge first")
    if card.get("countercharge") and b["turn"] == 1 and not t.get("countercharge"):
        state.record("battle.countercharge", "They countercharge! (first turn of the day)", title=_name(b),
                     data={"roll": None, "rolled": False, "table_text": "They countercharge!", "battle": _link(b, "fight")})
    fighting = [pid for pid in BS.conroi_ids(b) if t["postures"].get(pid, {}).get("posture") != "cowardly"]
    alone = [pid for pid in b["conroi"] if b["knights"].get(pid, {}).get("position") == "alone"]
    overrides = {}
    cr = (t.get("charge") or {}).get("result") or ("first_charge" if BS.first_charge_turn(b) else None)
    may_charge = cr in ("may_charge", "may_charge_plus5", "first_charge")
    for pid in fighting + alone:
        k = b["knights"][pid]
        p_ = t["postures"].get(pid, {}).get("posture")
        overrides[pid] = {"mounted": k["mounted"], "posture": p_, "rounds": B.POSTURES.get(p_, {}).get("rounds"),
                          "extra_rounds": 0, "position": k.get("position", "conroi"),
                          "lance": bool(may_charge and k["mounted"])}          # couched for the charge
    doubled = (t.get("intensity") or {}).get("outcome") == "critical"
    from web.routes.combat import start as combat_start
    link = {"id": b["id"], "day": b["day"], "turn": b["turn"], "step": "fight", "encounter": enc, "doubled": doubled,
            "barrage": (t.get("barrage") or {}).get("rounds") or 0}
    cc = t.get("countercharge") or ({"yes": True} if card.get("countercharge") and b["turn"] == 1 else {})
    return await combat_start(request, {"encounter": enc, "players": max(1, len(fighting)), "_battle": link,
                                        "_countercharge": bool(cc.get("yes")),
                                        "_knights": fighting + alone, "_knight_overrides": overrides,
                                        "_multiplier": 2 if doubled else 1,
                                        "_prefix": f"Day {b['day']}, Turn {b['turn']}: "})


@router.post("/api/battle/step")
async def step(request: Request, body: dict):
    state, b = _live(request)
    return record_outcome(state, body.get("step"), body, source="gm")


# -- aftermath and finale ------------------------------------------------------------

_AFTER_KEYS = {"enemy_kv", "friendly_pk_losses", "gm_knights", "gm_losses_roll", "gm_losses_override", "outnumber",
               "outcome_choice", "roles", "days_fought", "opponents", "decisive_roll", "decisive_rolled"}


def _aftermath(request):
    state = st(request)
    b = state.battle_state()
    if not b or b["status"] != "aftermath":
        bad("The battle isn't over yet", 409)
    return state, b


@router.post("/api/battle/aftermath")
async def aftermath(request: Request, body: dict):
    state, b = _aftermath(request)
    patch = {k: v for k, v in (body.get("patch") or {}).items() if k in _AFTER_KEYS}
    if "outnumber" in patch and patch["outnumber"] not in ("none", "we", "they"):
        bad("Outnumbering is none, we, or they")
    if patch.get("outcome_choice") and patch["outcome_choice"] not in B.OUTCOME_LABEL:
        bad("Unknown outcome")
    if patch.get("opponents") and patch["opponents"] not in B.PLUNDER_BASE:
        bad("Unknown opponents")
    if patch.get("gm_losses_roll") and patch["gm_losses_roll"] not in B.OUTCOMES:
        bad("Unknown roll outcome")
    for pid, role in (patch.get("roles") or {}).items():
        if role not in (None, "conroi", "bataille", "army"):
            bad("Role is conroi, bataille or army")
    ev = state.record("battle.aftermath", "Aftermath: " + ", ".join(f"{k} → {v}" for k, v in patch.items()),
                      title="Aftermath", visibility="gm", data={"patch": patch, "battle": _link(b, "aftermath")})
    nb = state.battle_state()
    return {"event": ev, "aftermath": BS.aftermath_view(nb, state.party.items)}


@router.post("/api/battle/aftermath/roll")
async def aftermath_roll(request: Request, body: dict):
    state, b = _aftermath(request)
    if BS.aftermath_view(b, state.party.items)["outcome"] != "decisive_victory":
        bad("The +£2D3 is for a Decisive Victory", 409)
    n = roll_expr("2D3")
    ev = state.record("battle.aftermath", f"Decisive Victory plunder: +£{n} (2D3)", title="Aftermath", visibility="gm",
                      data={"patch": {"decisive_roll": n, "decisive_rolled": True}, "battle": _link(b, "aftermath")})
    return {"event": ev}


@router.post("/api/battle/ransom")
async def battle_ransom(request: Request, body: dict):
    """Roll a captive's ransom after the battle (their fight has ended)."""
    from core.combat import roll_ransom
    from web import combat_state as CS
    state = st(request)
    fight_id, cid = body.get("fight"), body.get("cid")
    cs = None
    for ev in live_events(state.session.events):
        if ev["type"] == "combat.started" and ev["id"] == fight_id:
            cs = CS.apply(None, ev)
        elif cs is not None:
            cs = CS.apply(cs, ev)
            if ev["type"] == "combat.ended":
                break
    c = next((x for x in (cs or {}).get("combatants", []) if x.id == cid), None)
    if c is None or not c.ransom:
        bad("No ransom table for that captive", 404)
    roll_, line = roll_ransom(c)
    ev = state.record("combat.check", line, title=f"{c.display_name} — Ransom",
                      data={"cid": cid, "roll": roll_, "label": "Ransom", "fight": fight_id})
    return {"event": ev}


@router.post("/api/battle/finale")
async def finale(request: Request):
    state, b = _aftermath(request)
    a = BS.aftermath_view(b, state.party.items)
    ransoms = {}
    for ev in live_events(state.session.events):
        d = ev.get("data") or {}
        if ev["type"] == "combat.check" and d.get("label") == "Ransom" and d.get("fight"):
            ransoms[(d["fight"], d["cid"])] = ev["text"].split(": ", 1)[-1]
    knights = []
    for k in a["knights"]:
        rs = [{"captive": c["name"], "amount": ransoms.get((c["fight"], c["cid"]), "")} for c in a["captives"] if c["captor"] == k["pid"]]
        knights.append({"pid": k["pid"], "name": k["name"], "encounter_glory": k["encounter_glory"], "participation": k["participation"],
                        "role_label": {"conroi": "commander", "bataille": "bataille leader", "army": "army leader"}.get(k["role"], ""),
                        "total": k["total"], "plunder": k["plunder"], "ransoms": rs})
    summary = {"outcome": a["outcome"], "outcome_label": a["outcome_label"], "line": a["line"], "name": _name(b), "knights": knights}
    line = f"{a['outcome_label']} — " + ", ".join(f"{k['name']} {k['total']} Glory" for k in knights)
    ev = state.record("battle.finale", line, title=_name(b),
                      data={"summary": summary, "table_text": line, "battle": _link(b, "aftermath")})
    return {"event": ev}


@router.post("/api/battle/end")
async def end_battle(request: Request):
    state, b = _aftermath(request)
    ev = state.record("battle.ended", f"{_name(b)} is over", title=_name(b),
                      data={"table_text": "The battle is over", "battle": _link(b, "aftermath")})
    return {"event": ev}


# -- cascade undo ------------------------------------------------------------------

def _undo_targets(state, b, step_key):
    idx = BS.STEP_ORDER.index(step_key)
    events = live_events(state.session.events)
    resumed = max((e["id"] for e in events if e["type"] == "battle.resumed"), default=0)
    out, in_fight = [], False
    fight_idx = BS.STEP_ORDER.index("fight")
    for ev in events:
        d = ev.get("data") or {}
        link = d.get("battle") or {}
        this_turn = link.get("id") == b["id"] and link.get("day") == b["day"] and link.get("turn") == b["turn"]
        if ev["type"] == "combat.started":
            in_fight = this_turn and idx <= fight_idx
        if in_fight and (ev["type"].startswith("combat.") or ev["type"].startswith("glory.") or
                         (ev["type"].startswith("roll.") and d.get("cid"))):
            out.append(ev)                         # the turn's linked fight goes with it
            if ev["type"] == "combat.ended":
                in_fight = False
            continue
        if not this_turn:
            continue
        st_ = link.get("step")
        if st_ is None or st_ not in BS.STEP_ORDER:
            continue
        if BS.STEP_ORDER.index(st_) >= idx or st_ == "rest":
            out.append(ev)
    return out, any(e["id"] < resumed for e in out)


@router.get("/api/battle/undo-preview")
def undo_preview(request: Request, step: str):
    state, b = _live(request)
    if step not in BS.STEP_ORDER:
        bad("Unknown step")
    targets, locked = _undo_targets(state, b, step)
    if not targets:
        bad("That step isn't done", 404)
    return {"targets": [{"id": e["id"], "type": e["type"], "text": e["text"]} for e in targets], "locked": locked}


@router.post("/api/battle/undo")
async def undo(request: Request, body: dict):
    """Reopen a step: strike it and every later step of this turn in one
    undoable event (Q12)."""
    state, b = _live(request)
    step_key = body.get("step")
    if step_key not in BS.STEP_ORDER:
        bad("Unknown step")
    targets, locked = _undo_targets(state, b, step_key)
    if not targets:
        bad("That step isn't done", 404)
    if locked:
        bad("Those steps were made before the battle was resumed", 409)
    ev = state.record("meta.strike", f"Undone from {step_key} of Turn {b['turn']} ({len(targets)} event{'s' if len(targets) != 1 else ''})",
                      visibility="gm", data={"targets": [e["id"] for e in targets],
                                             "cascade": {"battle": b["id"], "day": b["day"], "turn": b["turn"], "step": step_key}})
    return {"event": ev}


@router.post("/api/battle/undo/{strike_id}/restore")
async def undo_restore(request: Request, strike_id: int):
    state = st(request)
    ev = next((e for e in state.session.events if e["id"] == strike_id), None)
    if not ev or ev["type"] != "meta.strike" or not (ev.get("data") or {}).get("cascade"):
        bad("Not an undone step", 404)
    r = state.record("meta.unstrike", f"Restored: {ev['text']}", visibility="gm",
                     data={"targets": ev["data"]["targets"]})
    return {"event": r}
