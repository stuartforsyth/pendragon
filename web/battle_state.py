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
             "commander_by_day": {}, "t": new_turn(), "prev_postures": {}, "fought_last": False,
             "spent_opportunities": [], "inconsistent": [], "retired_last": False}
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
    if t == "battle.ended" and d.get("abandoned"):     # called off before the first turn
        b["status"] = "ended"
        return b
    if b["status"] == "aftermath":
        if t == "battle.aftermath":
            b.setdefault("aftermath_patch", {}).update(copy.deepcopy(d.get("patch") or {}))
        elif t == "battle.finale":
            b["finale"] = copy.deepcopy(d.get("summary"))
        elif t == "battle.ended":
            b["status"] = "ended"
        return b
    if b["status"] not in LIVE:
        return b
    if t == "battle.settings":
        days = b["definition"].setdefault("days", [])
        if d.get("battle_patch"):
            b["definition"].update(copy.deepcopy(d["battle_patch"]))
        elif d.get("add_day"):
            days.append(copy.deepcopy(d["add_day"]))
        else:
            i = int(d.get("day", b["day"])) - 1
            if 0 <= i < len(days):
                days[i].update(copy.deepcopy(d.get("patch") or {}))
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
        if b["status"] == "mustering":
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
        b["status"] = "turn"
        b["turn"] = 1
        b["t"] = new_turn()
        b["fought_last"] = False
    elif t == "battle.conroi":
        if "knights" in d:
            b["conroi"] = list(d["knights"])
            for pid in b["conroi"]:
                _knight(b, pid)
        if "passion" in d:
            b["passion"] = d["passion"]
        if d.get("start") is not None and b["morale"]:
            b["morale"]["start"] = int(d["start"])
            b["morale"]["current"] = min(b["morale"]["current"], b["morale"]["start"])
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
    elif t in STEP_EVENTS:
        _apply_step(b, ev)
    elif t == "battle.mounted":
        for pid in d.get("pids") or [d.get("pid") or d.get("knight")]:
            k = _knight(b, pid)
            k["mounted"] = bool(d.get("mounted"))
            k["on_foot_since"] = None if k["mounted"] else (b["day"], b["turn"])
    elif t == "battle.position":
        _knight(b, d.get("pid") or d.get("knight"))["position"] = d.get("position") or "conroi"
    return b


# ----------------------------------------------------------------- the turn

STEP_ORDER = ("field", "set", "charge", "intensity", "picks", "select", "morale", "postures", "fight", "rest", "end")
STEP_EVENTS = {"battle.field", "battle.rest", "battle.set", "battle.charge", "battle.intensity", "battle.pick",
               "battle.select", "battle.morale", "battle.posture", "battle.passion", "battle.turn_ended",
               "battle.day_ended", "battle.fight", "battle.barrage", "battle.countercharge"}
EVENT_STEP = {"battle.field": "field", "battle.rest": "rest", "battle.set": "set", "battle.charge": "charge",
              "battle.intensity": "intensity", "battle.pick": "picks", "battle.select": "select",
              "battle.morale": "morale", "battle.posture": "postures", "battle.turn_ended": "end",
              "battle.day_ended": "end", "battle.fight": "fight", "battle.barrage": "fight",
              "battle.countercharge": "fight"}


def new_turn():
    return {"retired": False, "set": None, "charge": None, "intensity": None, "picks": {}, "select": None,
            "morale": None, "postures": {}, "rest": None, "rear_choice": None, "fight": None, "ended": False,
            "barrage": None, "countercharge": None, "events": {}}


def effective_deck(b, library=None, with_script=True):
    """Today's deck — narrowed by this turn's script restriction. An empty day
    deck means every battle Foe and Opportunity in the library (piece 3)."""
    dd = _day_def(b)
    deck = dd.get("deck") or {}
    if with_script:
        for sc in dd.get("scripts", []):
            if sc.get("turn") == b["turn"] and sc.get("deck"):
                deck = sc["deck"]
    foes, opps = list(deck.get("foes", [])), list(deck.get("opportunities", []))
    if not foes and not opps and library is not None:
        foes = sorted(k for k, e in library.items() if e.get("battle_role") == "foe")
        opps = sorted(k for k, e in library.items() if e.get("battle_role") == "opportunity")
    return {"foes": foes, "opportunities": opps, "all": not deck.get("foes") and not deck.get("opportunities")}


def chosen(b):
    """The Encounter this turn is fought against, and its card."""
    t = b["t"]
    pick = t["select"] or t["set"]
    return (pick["encounter"], pick["card"]) if pick else (None, None)


def _enemy_charge_locked(b):
    c = b["t"]["charge"]
    return bool(c and c.get("result") == "enemy_charge")


def conroi_ids(b):
    return [pid for pid in b["conroi"] if b["knights"].get(pid, {}).get("position", "conroi") == "conroi"]


def first_charge_turn(b):
    return b["turn"] == 1 and first_charge(b)


def steps(b):
    """The turn's steps with their state (done / current / skipped / todo) —
    what the GM stepper shows and what routes and replay validate against."""
    t = b["t"]
    items = []
    if b["status"] == "rear":
        items.append(("field", "done" if t["rear_choice"] else None, "", "At the rear: rest, return or leave"))
        if t["rear_choice"] in ("rest",):
            items.append(("rest", "done" if t["rest"] is not None else None, "", ""))
            items.append(("end", "done" if t["ended"] else None, "", ""))
        return _states(items)
    if t["retired"] and not t["set"]:
        items.append(("field", "done", "", "Retired to the Rear"))
        items.append(("rest", "done" if t["rest"] is not None else None, "", ""))
        items.append(("end", "done" if t["ended"] else None, "", ""))
        return _states(items)
    dd = _day_def(b)
    forced = bool(t["set"] and t["set"].get("forced"))
    items.append(("set", "done" if t["set"] else None, "", ""))
    if b["turn"] == 1:
        items.append(("charge", "skipped", "No charge roll on turn 1", ""))
    elif dd.get("no_charge"):
        items.append(("charge", "skipped", "No charge this day", ""))
    elif forced:
        items.append(("charge", "skipped", "Encounter forced by the enemy commander", ""))
    else:
        items.append(("charge", "done" if t["charge"] else None, "", ""))
    locked = _enemy_charge_locked(b)
    if forced or locked:
        items.append(("intensity", "skipped", "Forced Encounter" if forced else "Enemy knights charge — no choice", ""))
    else:
        items.append(("intensity", "done" if t["intensity"] else None, "", ""))
    io = (t["intensity"] or {}).get("outcome")
    if io == "failure" and not forced and not locked:
        items.append(("picks", "done" if t["select"] else None, "", ""))
    else:
        items.append(("picks", "skipped", "The Intensity roll held" if io in ("success", "critical") else "No choosing this turn" if io else "", ""))
    needs_select = locked or io in ("failure", "fumble")
    if needs_select and not forced:
        items.append(("select", "done" if t["select"] else None, "", ""))
    else:
        items.append(("select", "skipped", "The set Encounter stands", ""))
    m = t["morale"]
    items.append(("morale", "done" if m else None, "", ""))
    if m and m.get("kind") == "forced_retire":
        items.append(("postures", "skipped", "Not enough Morale — retired", ""))
        items.append(("fight", "skipped", "Retired to the Rear", ""))
        items.append(("rest", "done" if t["rest"] is not None else None, "", ""))
    else:
        # Every knight with the conroi has a posture — vacuously true when nobody
        # is left with it (all at the rear, Alone or gone), so the turn can end.
        done_p = all(pid in t["postures"] for pid in conroi_ids(b))
        items.append(("postures", "done" if done_p else None, "", ""))
        f = t["fight"]
        if f:
            items.append(("fight", "done" if not f.get("active") else None, "", ""))
        elif not conroi_ids(b):
            items.append(("fight", "skipped", "No knights with the conroi", ""))
        else:
            items.append(("fight", None, "", ""))
    items.append(("end", "done" if t["ended"] else None, "", ""))
    return _states(items)


def _states(items):
    out, current = [], None
    for key, st, reason, summary in items:
        if st in ("done", "skipped"):
            state = st
        elif st == "optional":
            state = "optional"
        elif current is None:
            state, current = "current", key
        else:
            state = "todo"
        out.append({"key": key, "state": state, "reason": reason, "summary": summary})
    if current is None:
        current = next((i["key"] for i in out if i["state"] == "optional"), None)
    return {"items": out, "current": current}


def current_step(b):
    return steps(b)["current"] if b and b["status"] in ("turn", "rear") else None


def _misfit(b, ev, reason):
    b["inconsistent"].append({"event": ev["id"], "type": ev["type"], "reason": reason})


def _apply_step(b, ev):
    """Turn-loop events, checked against the step machine on replay: an event
    that no longer fits (an earlier step was struck) is listed, not applied."""
    t_type, d = ev["type"], ev.get("data", {})
    if b["status"] not in ("turn", "rear"):
        return _misfit(b, ev, "No turn in progress")
    t = b["t"]
    cur = current_step(b)
    step = EVENT_STEP.get(t_type)
    m = b["morale"]
    if t_type == "battle.passion":
        k = _knight(b, d.get("knight"))
        k["passion_used"] = bool(d.get("used"))
        k["passion_name"] = d.get("name", "")
        return
    if t_type == "battle.field":
        if d.get("rear_choice"):
            if b["status"] != "rear" or t["rear_choice"]:
                return _misfit(b, ev, "Not at the rear")
            t["rear_choice"] = d["rear_choice"]
            if d["rear_choice"] == "return":
                b["status"] = "turn"
                b["t"] = new_turn()
            elif d["rear_choice"] == "leave":
                b["status"] = "aftermath"
        else:
            if cur != "set" or t["set"]:
                return _misfit(b, ev, "Retire is chosen at the start of a turn")
            t["retired"] = True
        return
    if t_type == "battle.barrage":
        t["barrage"] = {"outcome": d["outcome"], "rounds": B.barrage_rounds(d["outcome"])}
        return
    if t_type == "battle.countercharge":
        first = b["turn"] == 1
        t["countercharge"] = {"roll": d.get("roll"), "yes": B.countercharge(first, d.get("roll"))}
        return
    if step == "fight":
        return
    if t_type == "battle.day_ended":
        days = len(b["definition"].get("days", []))
        b["t"] = new_turn()
        if b["day"] >= days:
            b["status"] = "aftermath"
        else:
            b["day"] += 1
            b["turn"] = 0
            b["status"] = "mustering"
            b["fought_last"] = False           # knights keep yesterday's horses: set at Mustering
        return
    if step == "end":
        if cur not in ("end", "fight"):           # End turn is offered on the fight step too
            return _misfit(b, ev, "The turn isn't finished")
        if t_type == "battle.turn_ended":
            gain = kv_gain(b)
            for f in turn_fights(b):
                for pid in f["knights"]:
                    days_ = b.setdefault("fought_days", {}).setdefault(pid, [])
                    if b["day"] not in days_:
                        days_.append(b["day"])
            if gain and m:
                before = m["current"]
                m["current"] = B.apply_morale(m["current"], m["start"], gain)
                m["last"] = {"delta": m["current"] - before, "reason": "foes defeated"}
            retired = t["retired"] or (t["morale"] or {}).get("kind") == "forced_retire" or b["status"] == "rear"
            b["prev_postures"] = {pid: p["posture"] for pid, p in t["postures"].items()} or b["prev_postures"]
            b["fought_last"] = bool(t["fight"]) or bool(t["postures"])
            b["retired_last"] = retired
            b["turn"] += 1
            b["status"] = "rear" if retired and b["status"] != "aftermath" else ("turn" if b["status"] != "aftermath" else "aftermath")
            b["t"] = new_turn()
        return
    if step != cur and not (step == "select" and cur == "picks"):
        return _misfit(b, ev, f"Out of step ({step} while {cur or 'nothing'} is open)")
    if t_type == "battle.rest":
        if m:
            before = m["current"]
            m["current"] = B.apply_morale(m["current"], m["start"], int(d.get("amount") or 0))
            m["last"] = {"delta": m["current"] - before, "reason": "rest at the rear"}
        t["rest"] = int(d.get("amount") or 0)
    elif t_type == "battle.set":
        t["set"] = {"encounter": d["encounter"], "card": d.get("card") or {}, "flavour": d.get("flavour", ""),
                    "drawn": bool(d.get("drawn")), "forced": bool(d.get("forced"))}
        if d.get("forced"):
            b["tokens_spent"].setdefault(str(b["day"]), {})["force"] = True
    elif t_type == "battle.charge":
        if d.get("skipped"):                       # the GM ruled a charge impossible: not rolled
            t["charge"] = {"outcome": None, "engaged_last": None, "result": "no_charge", "skipped": True}
        else:
            t["charge"] = {"outcome": d["outcome"], "engaged_last": bool(d.get("engaged_last")),
                           "result": d.get("result") or B.charge_opportunity(d["outcome"], bool(d.get("engaged_last")))}
    elif t_type == "battle.intensity":
        t["intensity"] = {"outcome": d["outcome"], "result": B.intensity_result(d["outcome"])}
    elif t_type == "battle.pick":
        pid = d.get("knight")
        if d.get("encounter"):
            t["picks"][pid] = {"encounter": d["encounter"], "card": d.get("card") or {}, "crit": bool(d.get("crit"))}
        else:
            t["picks"].pop(pid, None)
    elif t_type == "battle.select":
        t["select"] = {"encounter": d["encounter"], "card": d.get("card") or {}, "via": d.get("via", "commander")}
        if (d.get("card") or {}).get("role") == "opportunity" and d["encounter"] not in b["spent_opportunities"]:
            b["spent_opportunities"].append(d["encounter"])
    elif t_type == "battle.morale":
        t["morale"] = {"kind": d.get("kind", "loss"), "amount": d.get("amount"), "negated": bool(d.get("negated"))}
        if d.get("negated"):
            b["tokens_spent"].setdefault(str(b["day"]), {})["negate"] = True
        elif d.get("kind") == "loss" and m:
            before = m["current"]
            m["current"] = B.apply_morale(m["current"], m["start"], -int(d.get("amount") or 0))
            enc, _ = chosen(b)
            m["last"] = {"delta": m["current"] - before, "reason": enc or "Encounter"}
    elif t_type == "battle.posture":
        pid = d.get("knight")
        if pid in t["postures"]:
            return _misfit(b, ev, "Posture already chosen this turn")
        t["postures"][pid] = {"posture": d["posture"], "amount": d.get("amount"), "above_half": d.get("above_half")}
        k = _knight(b, pid)
        k["posture"] = d["posture"]
        delta = B.posture_delta(d["posture"], d.get("amount") or None, bool(d.get("above_half"))) if d.get("amount") or d["posture"] == "valorous" else 0
        if delta and m:
            before = m["current"]
            m["current"] = B.apply_morale(m["current"], m["start"], delta)
            m["last"] = {"delta": m["current"] - before, "reason": f"{d['posture']} posture"}
        if d["posture"] == "cowardly":
            k["position"] = "rear"
    t["events"].setdefault(step, []).append(ev["id"])


def reduce(events):
    """The most recent battle in these (live) events, or None. Fights linked
    to the battle are folded alongside it (``web.combat_state``) so the battle
    knows each fight's defeats, KV and Glory — kept as plain summaries, so
    a snapshot stays JSON."""
    from web import combat_state as CS
    b, fight = None, None
    for ev in events:
        t = ev["type"]
        b = apply(b, ev)
        if t == "glory.awarded" and b and not (ev.get("data") or {}).get("fight"):
            link = (ev.get("data") or {}).get("battle") or {}
            if link.get("id") == b["id"]:
                mg = b.setdefault("manual_glory", {})
                pid = ev["data"].get("knight")
                mg[pid] = mg.get(pid, 0) + int(ev["data"].get("amount", 0))
            continue
        if t == "combat.started":
            link = (ev.get("data") or {}).get("battle")
            fight = CS.apply(None, ev) if b and link and link.get("id") == b["id"] else None
        elif t == "battle.resumed":
            fight = CS.apply(None, ev) if ((ev.get("data") or {}).get("snapshot") or {}).get("combat") else None
        elif fight is not None and (t.startswith("combat.") or t.startswith("glory.") or t == "battle.extra_round"):
            fight = CS.apply(fight, ev)
        else:
            continue
        if b and fight and (fight.get("battle") or {}).get("id") == b["id"]:
            _summarise(b, fight)
    return b


def _summarise(b, fight):
    """One linked fight as the battle sees it: defeats, KV, Glory, who fought."""
    from web import combat_state as CS
    link = fight["battle"]
    link.setdefault("fid", fight["started_event"])
    foes = [c for c in fight["combatants"] if getattr(c, "side", "foe") != "party"]
    knights = [c for c in fight["combatants"] if getattr(c, "side", "foe") == "party"]
    down = [c for c in foes if c.status in B.DEFEATED]
    lost = [c for c in foes if c.status == "dead" or (c.captured_by and c.status in ("unconscious", "surrendered"))]
    summary = {"day": link.get("day"), "turn": link.get("turn"), "encounter": link.get("encounter") or fight["name"],
               "lost_kvs": [str(B.parse_kv(getattr(c, "knight_value", ""))) for c in lost],
               "captives": [{"fight": fight["started_event"], "cid": c.id, "name": c.display_name, "captor": c.captured_by,
                             "ransom": bool(getattr(c, "ransom", None))}
                            for c in foes if c.captured_by and c.status in ("unconscious", "surrendered")],
               "active": fight["active"], "foes": len(foes), "defeated": len(down),
               "kvs": [str(B.parse_kv(getattr(c, "knight_value", ""))) for c in down],
               "glory": CS.glory_tally(fight),
               "knights": [k.party_id for k in knights if getattr(k, "position", None) in (None, "conroi")
                           and getattr(k, "posture", None) != "cowardly"]}
    b.setdefault("fights", {})[str(link["fid"])] = summary
    if summary["day"] == b["day"] and summary["turn"] == b["turn"] and b["status"] in ("turn", "rear"):
        b["t"]["fight"] = {"fid": link["fid"], **summary}


def turn_fights(b, day=None, turn=None):
    day, turn = day or b["day"], turn or b["turn"]
    return [f for f in b.get("fights", {}).values() if f["day"] == day and f["turn"] == turn]


def kv_gain(b):
    """Morale regained at End turn: the KV of foes defeated in this turn's
    fights, each rounded half up (GM ruling), capped by the reducer."""
    from fractions import Fraction
    return B.kv_morale_gain([[Fraction(k) for k in f["kvs"]] for f in turn_fights(b)])


_OUTCOME_LINE = {"decisive_victory": "The enemy is destroyed", "victory": "The enemy breaks and flies the field",
                 "indecisive": "Neither host gives way", "defeat": "The conroi is driven back",
                 "decisive_defeat": "A rout — the day is lost"}
_FRAC = {(1, 3): "⅓", (2, 3): "⅔", (1, 2): "½", (1, 4): "¼", (3, 4): "¾", (1, 8): "⅛", (3, 8): "⅜", (5, 8): "⅝", (7, 8): "⅞"}


def fmt_frac(f, money=False):
    from fractions import Fraction
    f = Fraction(f)
    whole, frac = int(f), f - int(f)
    g = _FRAC.get((frac.numerator, frac.denominator), f"{frac.numerator}/{frac.denominator}") if frac else ""
    txt = (str(whole) if whole or not g else "") + (" " if whole and g and money else "") + g
    return ("£" if money else "") + (txt or "0")


def _parse_amount(v):
    """"6 3/8", "6⅜", "2" or a number → Fraction."""
    from fractions import Fraction
    if isinstance(v, (int, float)):
        return Fraction(v).limit_denominator(64)
    s_ = str(v or "0").strip()
    total = Fraction(0)
    for part in s_.split():
        total += B.parse_kv(part)
    return total


def aftermath_view(b, party):
    """The aftermath (Outcome / Glory / Spoils), computed from the battle and
    the GM's edits; every figure is overridable."""
    from fractions import Fraction
    names = _names(party)
    patch = b.get("aftermath_patch", {})
    size = b["definition"].get("size", "clash")
    fights = list(b.get("fights", {}).values())
    enemy_default = sum((Fraction(k) for f in fights for k in f.get("lost_kvs", [])), Fraction(0))
    enemy = _parse_amount(patch["enemy_kv"]) if patch.get("enemy_kv") not in (None, "") else enemy_default
    pk = int(patch.get("friendly_pk_losses") or 0)
    gm_n = int(patch.get("gm_knights") or 0)
    gm_losses = patch.get("gm_losses_override") or (B.conroi_losses(patch["gm_losses_roll"], gm_n)
                                                    if patch.get("gm_losses_roll") and gm_n else {"killed": 0, "captured": 0})
    friendly = Fraction(pk + gm_losses["killed"] + gm_losses["captured"])
    outnumber = patch.get("outnumber") or "none"
    computed = B.outcome(enemy, friendly, outnumber)
    ratio = None if friendly == 0 else float(enemy / friendly * {"we": 2, "they": Fraction(1, 2)}.get(outnumber, 1))
    small_plus = size not in ("fight", "skirmish", "clash")
    chosen_outcome = patch.get("outcome_choice") or (b["definition"].get("outcome") if small_plus else None) or computed
    leader = B.leader_default([b["commander_by_day"].get(str(d)) for d in range(1, b["day"] + 1)])
    roles = {pid: (patch.get("roles") or {}).get(pid, "conroi" if pid == leader else None) for pid in b["conroi"]}
    days_fought = {pid: int((patch.get("days_fought") or {}).get(pid, len(b.get("fought_days", {}).get(pid, []))))
                   for pid in b["conroi"]}
    glory = battle_glory(b)
    opponents = patch.get("opponents") or "feudal"
    decisive = patch.get("decisive_roll")
    knights = []
    base = B.SIZES[size]["participation"]
    for pid in b["conroi"]:
        role, days = roles[pid], days_fought[pid]
        part = B.participation_glory(size, days, chosen_outcome, role) if days else 0
        mult = B.OUTCOME_MULT[chosen_outcome] + (B.LEADER_MULT[role] if role and size not in ("fight", "skirmish") else 0)
        working = f"{base}{f' × {days} days' if days > 1 else ''} × {fmt_frac(mult)} = {part}" if days else "did not fight"
        pl = B.plunder(opponents, chosen_outcome, decisive, outnumber, role, size)
        knights.append({"pid": pid, "name": names.get(pid, {}).get("name", "A knight"), "role": role, "days": days,
                        "encounter_glory": glory.get(pid, 0), "participation": part, "working": working,
                        "total": glory.get(pid, 0) + part, "plunder": fmt_frac(pl, money=True) if pl else "",
                        "plunder_value": float(pl)})
    captives = [dict(c, captor_name=names.get(c["captor"], {}).get("name", "")) for f in fights for c in f.get("captives", [])]
    return {"size": size, "size_label": B.SIZES[size]["label"], "days": len(b["definition"].get("days", [])),
            "enemy_kv": fmt_frac(enemy), "enemy_kv_default": fmt_frac(enemy_default), "friendly_pk_losses": pk,
            "gm_knights": gm_n, "gm_losses_roll": patch.get("gm_losses_roll"), "gm_losses": gm_losses,
            "friendly_kv": fmt_frac(friendly), "outnumber": outnumber, "ratio": round(ratio, 2) if ratio is not None else None,
            "computed": computed, "small_plus": small_plus, "outcome": chosen_outcome,
            "outcome_label": B.OUTCOME_LABEL[chosen_outcome], "line": _OUTCOME_LINE[chosen_outcome],
            "zero_ruling": friendly == 0, "opponents": opponents, "decisive_roll": decisive,
            "knights": knights, "captives": captives, "finale": b.get("finale")}


def battle_glory(b):
    """Glory per knight across the battle: every linked fight, plus awards
    made during the battle outside a fight."""
    tally = {}
    for f in b.get("fights", {}).values():
        for pid, n in f["glory"].items():
            tally[pid] = tally.get(pid, 0) + n
    for pid, n in b.get("manual_glory", {}).items():
        tally[pid] = tally.get(pid, 0) + n
    return tally


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


def gm_view(b, party, library=None):
    if b is None:
        return None
    if b["status"] in ("turn", "rear", "mustering"):
        deck_now = effective_deck(b, library)
    else:
        deck_now = None
    if b["status"] in ("turn", "rear"):
        b = copy.deepcopy(b)
        b["step"] = steps(b)
        enc, card = chosen(b)
        b["chosen"] = {"encounter": enc, "card": card} if enc else None
        b["first_charge_turn"] = first_charge_turn(b)
        b["conroi_now"] = conroi_ids(b)
        b["kv_gain"] = kv_gain(b)
    b = {**b, "glory_battle": battle_glory(b), "deck_now": deck_now}
    if b["status"] == "aftermath":
        b["aftermath"] = aftermath_view(b, party)
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


_BANNER = {"critical": ("The foe comes on in strength — doubled!", "harm"), "success": ("The Encounter stands", "state"),
           "fumble": ("Fortune smiles — an Opportunity?", "boon"), "failure": ("Intensity fails · choose your fate", "harm")}


def table_view(b, party, library=None):
    """What players may see (the battle view). Never: Loss, KV, the cards'
    rules, the definition, unrevealed scripts, dice or tokens. A card's
    Minimum Morale is shown — the players need it to choose."""
    if b is None:
        return None
    names = _names(party)
    size = b["definition"].get("size", "clash")
    m = b["morale"]
    t = b.get("t") or new_turn()
    nm = lambda pid: names.get(pid, {}).get("name", "A knight")
    out = {"id": b["id"], "name": b["definition"].get("name", "Battle"), "where": b["definition"].get("where", ""),
           "against": b["definition"].get("against", ""), "size_label": B.SIZES.get(size, {}).get("label", size),
           "status": b["status"], "day": b["day"], "days": len(b["definition"].get("days", [])),
           "turn": b["turn"], "turns_today": _day_def(b).get("turns"),
           "intensity": b["intensity"].get(str(b["day"])),
           "morale": {"current": m["current"], "start": m["start"], "band": B.morale_band(m["current"], m["start"]),
                      "last": m.get("last")} if m else None,
           "commander_name": "GM" if b["commander"] == "gm" else names.get(b["commander"], {}).get("name"),
           "title_card": {"id": b.get("last_title_event")} if b.get("last_title_event") else None,
           "charge_result": (t.get("charge") or {}).get("result")
                            or ("first_charge" if b["status"] == "turn" and first_charge_turn(b) else None),
           "glory": battle_glory(b),
           "barrage": (t.get("barrage") or {}).get("rounds"),
           "countercharge": (t.get("countercharge") or {}).get("yes"),
           "finale": b.get("finale")}
    # the turn's story
    banner = None
    if (t.get("morale") or {}).get("kind") == "forced_retire":
        banner = {"text": "Not enough Morale — Retire to the Rear", "tone": "harm"}
    elif (t.get("charge") or {}).get("result") == "enemy_charge" and not t.get("select"):
        banner = {"text": "Enemy knights charge you!", "tone": "harm"}
    elif t.get("intensity") and not t.get("morale"):
        text, tone = _BANNER[t["intensity"]["outcome"]]
        banner = {"text": text, "tone": tone}
    elif b["status"] == "rear":
        banner = {"text": "The conroi rests at the rear", "tone": "state"}
    out["banner"] = banner
    card_flav = lambda c: (c or {}).get("description", "")
    is_opp = lambda c: (c or {}).get("role") == "opportunity"
    mn = lambda c: (c or {}).get("morale_minimum")
    out["this_turn"] = {
        "set": {"name": t["set"]["encounter"], "flavour": t["set"].get("flavour") or card_flav(t["set"].get("card")),
                "opportunity": False, "minimum": mn(t["set"].get("card"))} if t.get("set") else None,
        "picks": [{"name": p["encounter"], "flavour": card_flav(p.get("card")), "opportunity": is_opp(p.get("card")),
                   "minimum": mn(p.get("card")), "knight_name": nm(pid), "crit": bool(p.get("crit"))} for pid, p in (t.get("picks") or {}).items()],
        "selected": (t.get("select") or {}).get("encounter"),
        "selected_card": {"name": t["select"]["encounter"], "flavour": card_flav(t["select"].get("card")),
                          "opportunity": is_opp(t["select"].get("card")), "minimum": mn(t["select"].get("card")),
                          "via": t["select"].get("via")} if t.get("select") else None}
    dd = _day_def(b)
    deck_eff = effective_deck(b, library, with_script=False)
    in_play = {x for x in [(t.get("set") or {}).get("encounter"), (t.get("select") or {}).get("encounter")] if x}
    in_play |= {p["encounter"] for p in (t.get("picks") or {}).values()}
    out["deck"] = {"foes": [{"name": k, "in_play": k in in_play} for k in deck_eff["foes"]],
                   "opportunities": [{"name": k, "in_play": k in in_play, "spent": k in b.get("spent_opportunities", [])}
                                     for k in deck_eff["opportunities"]]}
    out["options"] = _table_options(b, t, deck_eff, library, in_play, m)
    results = []
    if (t.get("intensity") or {}).get("outcome") in ("success", "critical"):
        for sc in dd.get("scripts", []):
            if sc.get("turn") == b["turn"] and sc.get("if_intensity"):
                results.append({"kind": "script", "text": sc["text"]})
    for sc in b["revealed_scripts"]:
        if sc.get("day") == b["day"]:
            results.append({"kind": "script", "text": sc["text"]})
    if b["turn"] == 1 and b["army"].get(str(b["day"]), {}).get("friendly") == "fumble":
        results.append({"kind": "minus5", "text": "−5 Battle this turn for the whole army"})
    out["results"] = results
    out["revealed_scripts"] = [r["text"] for r in results if r["kind"] == "script"]
    out["knights_raw"] = [{"pid": pid, "name": nm(pid), "player": names.get(pid, {}).get("player", ""),
                           "commander": pid == b["commander"], **{k: v for k, v in b["knights"].get(pid, {}).items()
                                                                if k in ("mounted", "position", "posture", "passion_used", "passion_name")},
                           "posture_now": (t.get("postures") or {}).get(pid, {}).get("posture"),
                           "prev_posture": b.get("prev_postures", {}).get(pid)}
                          for pid in b["conroi"]]
    return out


def _card_info(b, library, key):
    """What the players may read off a card: its flavour and the Morale it
    needs. Loss, KV and rules stay with the GM."""
    snap = (b.get("cards") or {}).get(key) or {}
    lib = (library or {}).get(key) or {}
    return {"flavour": lib.get("description") or snap.get("description", ""),
            "minimum": lib.get("morale_minimum") if lib.get("morale_minimum") is not None else snap.get("morale_minimum"),
            "role": lib.get("battle_role") or snap.get("role", "foe"),
            "mounted_charge": bool(snap.get("mounted_charge"))}


def _table_options(b, t, deck_eff, library, in_play, m):
    """The battlefield as the players may choose from it this step — only the
    cards the rules allow, each saying the Morale it needs and whether the
    conroi has it. Before the Intensity roll: the whole deck. Fumble: the set
    card or an Opportunity. Failure: anything (the knights pick). Success or
    an enemy charge: the card in play alone. After the choice: that card."""
    if b["status"] == "mustering":                     # the day's battlefield, laid out for all to see
        t = new_turn()
    elif b["status"] != "turn":
        return None
    spent = set(b.get("spent_opportunities", []))
    set_key = (t.get("set") or {}).get("encounter")
    io = (t.get("intensity") or {}).get("outcome")
    chosen_key = (t.get("select") or {}).get("encounter")
    locked = _enemy_charge_locked(b)
    foes, opps = deck_eff["foes"], [k for k in deck_eff["opportunities"] if k not in spent or k in in_play]
    if chosen_key:
        keys = [chosen_key]
    elif locked:
        keys = [k for k in foes if _card_info(b, library, k)["mounted_charge"]] or ([set_key] if set_key else [])
    elif io in ("success", "critical"):
        keys = [set_key] if set_key else []
    elif io == "fumble":
        keys = ([set_key] if set_key else []) + [k for k in opps if k != set_key]
    elif io == "failure":
        keys = foes + opps
    else:
        keys = foes + opps
    if t.get("morale") or not set_key and io is None and t.get("retired"):
        keys = [chosen_key or set_key] if (chosen_key or set_key) else []
    cur = m["current"] if m else 0
    out = []
    for k in dict.fromkeys(keys):
        info = _card_info(b, library, k)
        need = info["minimum"]
        out.append({"name": k, "flavour": info["flavour"], "opportunity": info["role"] == "opportunity",
                    "minimum": need, "playable": (need is None or cur >= need) and (k not in spent or k in in_play),
                    "spent": k in spent and k not in in_play, "in_play": k in in_play})
    return out


def snapshot(b, combat):
    """A battle (and any fight in progress) frozen for ``battle.resumed``."""
    snap = {"battle": copy.deepcopy(b), "combat": None}
    if combat and combat.get("active"):
        snap["combat"] = {"name": combat["name"], "round": combat["round"], "players": combat.get("players", 0),
                          "descriptions": combat.get("descriptions", []),
                          "credits": combat.get("credits", {}), "manual": combat.get("manual", {}),
                          "battle": combat.get("battle"), "acted": sorted(combat.get("acted") or []),
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
