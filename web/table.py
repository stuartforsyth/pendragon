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
                    "to_knight", "knight_shield"),
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
    "battle.morale_adjust": ("delta", "start", "reason"),
    "battle.script": ("text",),
    "battle.mounted": ("mounted",),
    "battle.position": ("position",),
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


def _effects(k):
    """A knight's reminder chips — what the player applies on paper."""
    out = []
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


def knight_cards(events, fl, combat):
    """The players' knight cards for the fight view (reusable by battles,
    feasts and hunts): Glory, reminder chips, the last things that happened
    to each knight, and their lane of foes. Built here so ``touches`` — the
    event-to-knight links — never leave the server."""
    if not combat:
        return []
    rows = combat["combatants"]
    start = combat.get("started_event") or 0
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
                 "chips": [x for x in (f.get("height_chip"), "⇣ horse" if f.get("attacks_horse") and k.get("mounted") else "") if x]}
                for f in rows if f["side"] != "party" and f.get("engaged_with") == k["name"] and f["status"] == "active"]
        cards.append({"pid": pid, "name": k["name"], "player": k.get("player", ""), "mounted": k.get("mounted", True),
                      "status": k["status"],
                      "glory": {"value": (combat.get("glory") or {}).get(pid, 0), "scope": "fight", "last": last},
                      "effects": _effects(k), "happened": happened, "lane": {"foes": foes}})
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
            "knights": knight_cards(session.events, fl, combat)}
