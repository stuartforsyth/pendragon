"""The Table screen's view of a session — the only path to player eyes.

Filtering happens here, server-side, so nothing secret ever reaches the
shared browser window:

- GM-only events (notes) and struck events are dropped.
- A masked roll that hasn't been revealed becomes a sealed card: no result,
  and its label only if the GM chose to show it.
- Event builders may supply ``data.table_text`` — a player-safe line used
  instead of the GM log text (e.g. foe HP changes become a wound state).
- NPC cards carry only the name, subtitle and read-aloud description.
"""

from web.sessions import META_TYPES, flags

FEED_LIMIT = 40

# data keys that are safe to pass to the table per event type
_SAFE_DATA = {
    "roll.dice": ("expr", "terms", "total", "label"),
    "roll.check": ("label", "outcome", "roll", "kind", "actor", "shown", "value"),
    "combat.attack": ("verdict", "result"),
    "combat.blow": ("attacker", "weapon", "target", "blow", "breakdown", "major", "mortal",
                    "to_knight", "knight_shield", "narrative"),
    "roll.opposed": ("a", "b", "winner"),
    "roll.damage": ("label", "total", "critical", "rebated", "actor", "expr", "breakdown"),
    "narrate": ("text", "style", "image_url"),
    "rule.shown": ("rule_id", "title", "html", "pages", "book"),
    "combat.started": ("name",),
    "combat.round": ("round",),
    "combat.ended": ("name",),
    "combat.mounted": ("mounted",),
    "combat.captured": (),
    "glory.awarded": ("knight_name", "amount", "reason"),
    "glory.reassigned": ("knight_name", "foe", "amount"),
    "battle.started": (),
    "battle.deck": ("day", "add", "remove"),
    "battle.army_roll": ("side", "outcome"),
    "battle.day_started": ("day", "intensity"),
    "battle.mustered": ("day", "start", "passion"),
    "battle.commander": (),
    "battle.conroi": ("passion", "start"),
    "battle.morale_adjust": ("delta", "start", "reason"),
    "battle.script": ("text",),
    "battle.mounted": ("mounted",),
    "battle.position": ("position",),
    "battle.field": ("choice", "rear_choice"),
    "battle.rest": ("amount",),
    "battle.set": ("encounter", "flavour", "drawn", "forced"),
    "battle.charge": ("outcome", "engaged_last"),
    "battle.intensity": ("outcome",),
    "battle.pick": ("encounter", "crit"),
    "battle.select": ("encounter", "via"),
    "battle.morale": ("kind", "amount", "negated"),
    "battle.posture": ("posture", "amount"),
    "battle.passion": ("used", "name"),
    "battle.turn_ended": (),
    "battle.day_ended": (),
    "battle.finale": ("summary",),
    "battle.ended": (),
}


def _npc_card(npc):
    if not npc:
        return {}
    return {"full": npc.get("full", ""), "subtitle": npc.get("subtitle", ""),
            "description": npc.get("description", "")}


def card(ev, fl):
    """A player-safe card for one event, or None if it must not be shown."""
    if ev["type"] in META_TYPES or ev.get("visibility") == "gm":
        return None
    f = fl.get(ev["id"], {})
    if f.get("struck"):
        return None
    d = ev.get("data", {})
    base = {"id": ev["id"], "ts": ev["ts"], "type": ev["type"]}
    if ev.get("masked") and not f.get("revealed"):
        label = d.get("label") if d.get("show_label") else ""
        return {**base, "type": "sealed", "title": label or "",
                "text": "The GM rolls in secret…", "data": {}}
    data = {k: d[k] for k in _SAFE_DATA.get(ev["type"], ()) if k in d}
    if ev["type"].startswith("npc.") and "npc" in d:
        data["npc"] = _npc_card(d["npc"])
    return {**base, "title": d.get("table_title", ev.get("title", "")),
            "text": d.get("table_text", ev.get("text", "")),
            "revealed": bool(ev.get("masked") and f.get("revealed")),
            "data": data}


# The Table only shows what happened since it was last cleared: a (non-struck)
# "table.cleared" event, or the start of the session.
CUTOFF_TYPES = ("table.cleared", "session.started")


_NUM_WORD = {2: "two", 3: "three", 4: "four", 5: "five"}


_POSTURE = {"reckless": "Reckless", "valorous": "Valorous", "prudent": "Prudent", "cowardly": "Cowardly"}


def _effects(k, battle=None):
    """A knight's reminder chips — what the player applies on paper."""
    out = []
    if k.get("posture"):
        p = _POSTURE.get(k["posture"], k["posture"])
        lim = k["rounds"] + k.get("extra_rounds", 0)
        label = f"{p} · last round" if k.get("last_round") else f"{p} · withdraws" if k.get("withdraws") \
            else f"{p} · {lim} round{'s' if lim != 1 else ''}"
        out.append({"key": "posture", "label": label, "tone": "state"})
    if battle and k.get("mounted", True):
        cr = battle.get("charge_result")
        if cr == "may_charge_plus5":
            out.append({"key": "charge", "label": "Charge +5", "tone": "boon"})
        elif cr == "may_charge":
            out.append({"key": "charge", "label": "May charge", "tone": "boon"})
        elif cr == "first_charge":
            out.append({"key": "charge", "label": "First charge!", "tone": "boon"})
    if not k.get("mounted", True):
        out.append({"key": "on_foot", "label": "On foot", "tone": "state"})
    seen = set()
    for ch in k.get("height_chips", []):
        if ch["text"] in seen:
            continue
        seen.add(ch["text"])
        out.append({"key": "height", "label": ch["text"], "tone": "boon" if ch["text"].startswith("+") else "harm"})
    n = k.get("mo_n", 0)
    if n > 1:
        out.append({"key": "mo", "label": f"−{5 * (n - 1)} {_NUM_WORD.get(n, n)} foes", "tone": "harm"})
    return out


def knight_cards(events, fl, combat, battle=None):
    """The players' knight cards for the fight view (reusable by battles,
    feasts and hunts): Glory, reminder chips, the last things that happened
    to each knight, and their lane of foes. Built here so ``touches`` — the
    event-to-knight links — never leave the server."""
    if not combat:
        return []
    rows = combat["combatants"]
    start = combat.get("started_event") or 0
    linked = bool(battle and (combat.get("battle") or {}).get("id") == battle.get("id"))
    cards = []
    for k in (r for r in rows if r["side"] == "party"):
        pid = k.get("party_id")
        happened, last = [], None
        for ev in reversed(events):
            if len(happened) >= 3 and last is not None:
                break
            if ev["type"] in META_TYPES or ev.get("visibility") == "gm" or fl.get(ev["id"], {}).get("struck"):
                continue
            d = ev.get("data", {})
            if pid not in (d.get("touches") or []):
                continue
            if len(happened) < 3:
                happened.append(d.get("table_text", ev.get("text", "")))
            if last is None and d.get("glory_amount") and ev["id"] >= start:
                last = {"amount": d["glory_amount"], "text": d.get("table_text", "")}
        foes = [{"id": f["id"], "name": f["name"], "wound_state": f["wound_state"],
                 # No Height or horse chips: a foe going for the horse is the GM's secret
                 # (its Height chip would give it away); knights see their own Height.
                 "chips": ["Disarmed"] if f.get("disarmed") else []}
                for f in rows if f["side"] != "party" and f.get("engaged_with") == k["name"] and f["status"] == "active"]
        cards.append({"pid": pid, "name": k["name"], "player": k.get("player", ""), "mounted": k.get("mounted", True),
                      "status": k["status"],
                      "glory": {"value": ((battle or {}).get("glory") or {}).get(pid, 0) if linked
                                else (combat.get("glory") or {}).get(pid, 0), "scope": "battle" if linked else "fight", "last": last},
                      "effects": _effects(k, battle if linked else None), "happened": happened, "lane": {"foes": foes}})
    return cards


_ROUNDS = {"reckless": 3, "valorous": 2, "prudent": 1, "cowardly": 0}


def _battle_chips(k, battle):
    out = []
    if k.get("commander"):
        out.append({"key": "commander", "label": "Commander", "tone": "state"})
    cr = battle.get("charge_result")
    if cr == "enemy_charge" and not k.get("mounted", True):
        out.append({"key": "charge", "label": "Enemy charge — on foot", "tone": "harm"})
    elif k.get("mounted", True) and cr in ("may_charge_plus5", "may_charge", "first_charge"):
        out.append({"key": "charge", "label": {"may_charge_plus5": "Charge +5", "may_charge": "May charge",
                                               "first_charge": "First charge!"}[cr], "tone": "boon"})
    if not k.get("mounted", True):
        out.append({"key": "on_foot", "label": "On foot", "tone": "state"})
    if k.get("posture_now"):
        p = k["posture_now"]
        out.append({"key": "posture", "label": f"{_POSTURE[p]} · {_ROUNDS[p]} round{'s' if _ROUNDS[p] != 1 else ''}", "tone": "state"})
    elif k.get("prev_posture"):
        out.append({"key": "posture", "label": f"{_POSTURE[k['prev_posture']]} last turn", "tone": "state"})
    if k.get("passion_used"):
        out.append({"key": "passion", "label": f"Passion: {k.get('passion_name') or 'used'}", "tone": "state"})
    pos = k.get("position")
    if pos == "rear":
        out.append({"key": "pos", "label": "At the rear", "tone": "state"})
    elif pos == "alone":
        out.append({"key": "pos", "label": "Alone on the Field", "tone": "harm"})
    if any(r["kind"] == "minus5" for r in battle.get("results", [])):
        out.append({"key": "minus5", "label": "−5 Battle (army fumble)", "tone": "harm"})
    return out


def battle_knight_cards(events, fl, battle):
    """Knight cards for the battle view: battle Glory, battle chips, LAST."""
    cards = []
    for k in battle.pop("knights_raw", []):
        pid = k["pid"]
        happened, last = [], None
        for ev in reversed(events):
            if len(happened) >= 3:
                break
            if ev["type"] in META_TYPES or ev.get("visibility") == "gm" or fl.get(ev["id"], {}).get("struck"):
                continue
            d = ev.get("data", {})
            if pid in (d.get("touches") or []):
                happened.append(d.get("table_text", ev.get("text", "")))
                if last is None and d.get("glory_amount"):
                    last = {"amount": d["glory_amount"], "text": d.get("table_text", "")}
        cards.append({"pid": pid, "name": k["name"], "player": k["player"], "mounted": k.get("mounted", True),
                      "status": "active" if k.get("position", "conroi") in ("conroi", "alone") else "away",
                      "glory": {"value": battle.get("glory", {}).get(pid, 0), "scope": "battle", "last": last},
                      "effects": _battle_chips(k, battle), "happened": happened})
    return cards


def build(session, combat, pinned_mode="auto", battle=None):
    fl = flags(session.events)
    feed = []
    for ev in reversed(session.events):
        if ev["type"] in CUTOFF_TYPES and not fl.get(ev["id"], {}).get("struck"):
            break
        c = card(ev, fl)
        if c is not None:
            feed.append(c)
            if len(feed) >= FEED_LIMIT:
                break
    if combat and combat.get("active"):
        auto = "combat"
    elif battle and battle.get("status") in ("mustering", "turn", "rear", "paused", "aftermath"):
        auto = "battle"
    else:
        auto = "chronicle"
    mode = auto if pinned_mode == "auto" else pinned_mode
    return {"session": {"title": session.title, "scratch": session.scratch},
            "mode": mode, "pinned": pinned_mode, "feed": feed, "combat": combat, "battle": battle,
            "knights": knight_cards(session.events, fl, combat, battle),
            **({"battle_knights": battle_knight_cards(session.events, fl, battle)} if battle else {})}
