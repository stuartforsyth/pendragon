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


def build(session, combat, pinned_mode="auto"):
    fl = flags(session.events)
    feed = []
    for ev in reversed(session.events):
        c = card(ev, fl)
        if c is not None:
            feed.append(c)
            if len(feed) >= FEED_LIMIT:
                break
    auto = "combat" if combat and combat.get("active") else "chronicle"
    mode = auto if pinned_mode == "auto" else pinned_mode
    return {"session": {"title": session.title, "scratch": session.scratch},
            "mode": mode, "pinned": pinned_mode, "feed": feed, "combat": combat}
