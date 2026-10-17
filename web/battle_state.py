"""Live battle state, rebuilt by replaying a session's (non-struck) events.

Like combat state, nothing here rolls: events carry what the GM entered (an
outcome, an amount, a choice) and the rules from ``core.battle`` are applied
on replay — so a capped Morale gain recomputes correctly when an earlier event
is struck. ``battle.resumed`` carries a full snapshot and replaces the state,
so each session file stands on its own.
"""

import copy

from core import battle as B
from web.sessions import live_events

LIVE = ("mustering", "turn", "rear")


def _knight(b, pid):
    return b["knights"].setdefault(pid, {"mounted": True, "position": "conroi", "posture": None,
                                         "passion_used": False, "on_foot_since": None})


def _day_def(b, day=None):
    days = b["definition"]["days"]
    i = (day or b["day"]) - 1
    return days[i] if 0 <= i < len(days) else days[-1]


def apply(b, ev):
    """Fold one battle event into the state and return it."""
    t, d = ev["type"], ev.get("data", {})
    if not t.startswith("battle."):
        return b
    if t == "battle.started":
        knights = {}
        b = {"id": d.get("id") or str(ev["id"]), "started_event": ev["id"],
             "definition": copy.deepcopy(d.get("definition") or {}), "source_key": d.get("source_key"),
             "status": "mustering", "day": 1, "turn": 0, "intensity": {}, "army": {},
             "tokens_spent": {}, "morale": None, "commander": None, "conroi": list(d.get("knights", [])),
             "passion": "", "knights": knights, "revealed_scripts": [], "last_title_event": ev["id"],
             "closed": {"defeated": [], "glory": {}, "kv_by_turn": {}}, "paused_from": None,
             "commander_by_day": {}}
        for pid in d.get("knights", []):
            _knight(b, pid)
        return b
    if t == "battle.resumed":
        snap = copy.deepcopy((d.get("snapshot") or {}).get("battle"))
        if snap:
            snap["status"] = snap.get("paused_from") or snap.get("status", "mustering")
            if snap["status"] == "paused":
                snap["status"] = "mustering"
            snap["paused_from"] = None
        return snap
    if b is None:
        return b
    if t == "battle.paused":
        if b["status"] in LIVE:
            b["paused_from"] = b["status"]
        b["status"] = "paused"
        return b
    if b["status"] not in LIVE:
        return b
    if t == "battle.settings":
        days = b["definition"].setdefault("days", [])
        if d.get("add_day"):
            days.append(copy.deepcopy(d["add_day"]))
        else:
            i = int(d.get("day", b["day"])) - 1
            if 0 <= i < len(days):
                days[i].update(copy.deepcopy(d.get("patch") or {}))
                if (d.get("patch") or {}).get("on_foot") and i + 1 == b["day"]:
                    for k in b["knights"].values():
                        k["mounted"] = False
    elif t == "battle.deck":
        deck = _day_def(b, int(d.get("day", b["day"])))["deck"]
        cards = d.get("cards") or {}
        for key in d.get("add", []):
            role = (cards.get(key) or {}).get("role", "foe")
            lst = deck["opportunities"] if role == "opportunity" else deck["foes"]
            if key not in lst:
                lst.append(key)
        for key in d.get("remove", []):
            for lst in (deck["foes"], deck["opportunities"]):
                if key in lst:
                    lst.remove(key)
        b.setdefault("cards", {}).update(copy.deepcopy(cards))
    elif t == "battle.army_roll":
        b["army"].setdefault(str(d.get("day", b["day"])), {})[d["side"]] = d["outcome"]
    elif t == "battle.day_started":
        b["intensity"][str(d.get("day", b["day"]))] = int(d["intensity"])
        b["last_title_event"] = ev["id"]
    elif t == "battle.mustered":
        b["morale"] = {"start": int(d["start"]), "current": int(d["start"]), "last": None}
        b["passion"] = d.get("passion", "")
        b["commander"] = d.get("commander")
        b["commander_by_day"][str(b["day"])] = d.get("commander")
        b["conroi"] = list(d.get("knights", b["conroi"]))
        for pid in b["conroi"]:
            k = _knight(b, pid)
            k["passion_used"] = False          # scenario rule: each day is its own engagement
            k["position"] = "conroi"
        if _day_def(b).get("on_foot"):
            for pid in b["conroi"]:
                b["knights"][pid]["mounted"] = False
        b["status"] = "turn"
        b["turn"] = 1
    elif t == "battle.commander":
        b["commander"] = d.get("commander")
        b["commander_by_day"][str(b["day"])] = d.get("commander")
    elif t == "battle.morale_adjust":
        m = b["morale"]
        if m is not None:
            if d.get("start") is not None:
                m["start"] = int(d["start"])
                m["current"] = min(m["current"], m["start"])
            else:
                before = m["current"]
                m["current"] = B.apply_morale(m["current"], m["start"], int(d.get("delta") or 0))
                m["last"] = {"delta": m["current"] - before, "reason": d.get("reason", "")}
    elif t == "battle.script":
        b["revealed_scripts"].append({"day": d.get("day"), "index": d.get("index"), "text": d.get("text", "")})
    elif t == "battle.mounted":
        k = _knight(b, d["pid"])
        k["mounted"] = bool(d.get("mounted"))
        k["on_foot_since"] = None if k["mounted"] else (b["day"], b["turn"])
    elif t == "battle.position":
        _knight(b, d["pid"])["position"] = d.get("position") or "conroi"
    return b


def reduce(events):
    """The most recent battle in these (live) events, or None."""
    b = None
    for ev in events:
        b = apply(b, ev)
    return b


def is_live(b):
    return bool(b) and b["status"] in LIVE


# ----------------------------------------------------------------- views

def tokens(b):
    """Force Encounter / Negate Morale loss for the current day (Q15: they
    expire at the end of the day)."""
    army = b["army"].get(str(b["day"]), {})
    eff = B.army_effects("enemy", army["enemy"]) if army.get("enemy") else {}
    spent = b["tokens_spent"].get(str(b["day"]), {})
    def state(key, token):
        if not eff.get(key):
            return "none"
        return "spent" if spent.get(token) else "available"
    return {"force": state("force_token", "force"), "negate": state("negate_token", "negate")}


def first_charge(b, day=None):
    """Is turn 1 of this day a mounted charge? The day's switch, unless the
    friendly Army Commander roll says otherwise (Clash and up)."""
    day = day or b["day"]
    dd = _day_def(b, day)
    if dd.get("no_charge"):
        return False
    army = b["army"].get(str(day), {})
    if army.get("friendly"):
        return B.army_effects("friendly", army["friendly"])["first_charge"]
    return bool(dd.get("first_charge", True))


def _names(party):
    return {m["id"]: m for m in party}


def gm_view(b, party):
    if b is None:
        return None
    names = _names(party)
    size = b["definition"].get("size", "clash")
    dd = _day_def(b)
    m = b["morale"]
    out = copy.deepcopy(b)
    out.update(
        size_label=B.SIZES.get(size, {}).get("label", size), army_rolls=B.SIZES.get(size, {}).get("army_rolls", False),
        size_turns=B.SIZES.get(size, {}).get("turns"), size_dice=B.SIZES.get(size, {}).get("intensity"),
        days=len(b["definition"].get("days", [])), turns_today=dd.get("turns"),
        intensity_today=b["intensity"].get(str(b["day"])), day_def=copy.deepcopy(dd),
        tokens=tokens(b), first_charge=first_charge(b),
        minus5=bool(b["army"].get(str(b["day"]), {}).get("friendly") == "fumble"),
        band=B.morale_band(m["current"], m["start"]) if m else None,
        commander_name="GM" if b["commander"] == "gm" else names.get(b["commander"], {}).get("name"),
        knight_list=[{"pid": pid, "name": names.get(pid, {}).get("name", "A knight"),
                      "player": names.get(pid, {}).get("player", ""), **b["knights"].get(pid, {})}
                     for pid in (b["conroi"] or list(b["knights"]))])
    return out


def table_view(b, party):
    """What players may see: never the definition, decks' mechanics or dice."""
    if b is None:
        return None
    names = _names(party)
    size = b["definition"].get("size", "clash")
    m = b["morale"]
    return {"id": b["id"], "name": b["definition"].get("name", "Battle"), "where": b["definition"].get("where", ""),
            "against": b["definition"].get("against", ""), "size_label": B.SIZES.get(size, {}).get("label", size),
            "status": b["status"], "day": b["day"], "days": len(b["definition"].get("days", [])),
            "turn": b["turn"], "turns_today": _day_def(b).get("turns"),
            "intensity": b["intensity"].get(str(b["day"])),
            "morale": {"current": m["current"], "start": m["start"], "band": B.morale_band(m["current"], m["start"]),
                       "last": m.get("last")} if m else None,
            "commander_name": "GM" if b["commander"] == "gm" else names.get(b["commander"], {}).get("name"),
            "title_card": {"id": b.get("last_title_event")} if b.get("last_title_event") else None,
            "revealed_scripts": [s["text"] for s in b["revealed_scripts"] if s.get("day") == b["day"]]}


def snapshot(b, combat):
    """A battle (and any fight in progress) frozen for ``battle.resumed``."""
    snap = {"battle": copy.deepcopy(b), "combat": None}
    if combat and combat.get("active"):
        snap["combat"] = {"name": combat["name"], "round": combat["round"], "players": combat.get("players", 0),
                          "descriptions": combat.get("descriptions", []),
                          "credits": combat.get("credits", {}), "manual": combat.get("manual", {}),
                          "combatants": [c.to_dict() for c in combat["combatants"]]}
    return snap


def paused_battles(store, active_id=None):
    """Battles paused in saved sessions and not resumed since (design §3.5).
    Sessions are read oldest first, so a battle paused, resumed and paused
    again is listed once, from where it was last paused."""
    latest = {}
    for meta in reversed(store.list()):
        try:
            s = store.load(meta["id"])
        except (OSError, ValueError, KeyError):
            continue
        events = live_events(s.events)
        for ev in events:
            if ev["type"] == "battle.resumed":
                rid = ((ev.get("data") or {}).get("snapshot") or {}).get("battle", {}).get("id")
                if rid:
                    latest[rid] = None
        b = reduce(events)
        if b and b["status"] == "paused" and meta["id"] != active_id:
            m = b["morale"]
            latest[b["id"]] = {"battle_id": b["id"], "session_id": meta["id"], "session_title": meta.get("title", ""),
                               "name": b["definition"].get("name", "Battle"), "day": b["day"], "turn": b["turn"],
                               "morale": [m["current"], m["start"]] if m else None}
    return [p for p in latest.values() if p]
