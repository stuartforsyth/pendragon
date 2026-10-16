"""Live combat state, rebuilt by replaying a session's (non-struck) events.

Randomness never happens here: a ``combat.started`` / ``combat.added`` event
carries full combatant snapshots (HP jitter, rolled looks… already decided),
and every later event is a deterministic change (an HP delta, a status
override, a promotion). So striking any event and replaying always gives the
correct state — that is how "undo" works.
"""

from core.combat import Combatant

COMBAT_STATE_TYPES = {
    "combat.started", "combat.added", "combat.hp", "combat.status",
    "combat.promote", "combat.modifier", "combat.engage", "combat.removed",
    "combat.round", "combat.ended", "combat.blow",
}


def reduce(events, promotion_cfg=None):
    """Fold live events into ``{"active", "name", "round", "combatants": [Combatant]}``
    for the most recent combat (or ``None`` if the session has had none)."""
    state = None
    for ev in events:
        t, d = ev["type"], ev.get("data", {})
        if t not in COMBAT_STATE_TYPES:
            continue
        if t == "combat.started":
            state = {"active": True, "name": d.get("name", "Encounter"),
                     "round": 1, "players": d.get("players", 0),
                     "descriptions": d.get("descriptions", []),
                     "started_event": ev["id"],
                     "combatants": [Combatant.from_dict(c) for c in d.get("combatants", [])]}
            continue
        if state is None or not state["active"]:
            continue
        if t == "combat.ended":
            state["active"] = False
            continue
        if t == "combat.round":
            state["round"] = d.get("round", state["round"] + 1)
            continue
        if t == "combat.added":
            state["combatants"].append(Combatant.from_dict(d["combatant"]))
            continue
        c = next((x for x in state["combatants"] if x.id == d.get("cid")), None)
        if c is None:
            continue
        if getattr(c, "side", "foe") == "party" and t in ("combat.hp", "combat.blow"):
            continue                    # knights' health is the players' business
        if t == "combat.hp":
            c.apply_hp(int(d.get("delta", 0)))
        elif t == "combat.blow":
            if d.get("delta"):
                c.apply_hp(int(d["delta"]))
            if d.get("shield_broken"):
                c.shield = 0
        elif t == "combat.status":
            c.set_out(d.get("out"))
        elif t == "combat.promote":
            if d.get("promote"):
                c.promote(d.get("cfg") or promotion_cfg or {})
            else:
                c.demote()
        elif t == "combat.modifier":
            c.modifier = int(d.get("value", 0))
        elif t == "combat.engage":
            c.engaged_with = d.get("with", "")
        elif t == "combat.removed":
            state["combatants"].remove(c)
    return state


def gm_view(c):
    """Everything the GM console needs for one combatant row."""
    d = c.to_dict()
    d.pop("_base", None)
    d.update(status=c.status, down=c.down, display_name=c.display_name,
             log_name=c.log_name, armor_total=c.armor_total(),
             armour_text=c.describe_armour(), looks=c.describe_looks(),
             wound_state=c.wound_state(), side=getattr(c, "side", "foe"))
    return d


def table_view(c):
    """What players may see: no foe numbers, just a described wound state."""
    side = getattr(c, "side", "foe")
    out = {"id": c.id, "name": c.display_name, "side": side, "status": c.status,
           "wound_state": c.wound_state(), "elite": c.elite,
           "named": getattr(c, "named", False),
           "category": getattr(c, "category", "human"),
           "engaged_with": c.engaged_with}
    if side == "party":
        out.update(player=getattr(c, "player", ""))
    return out


def serialise(state, view):
    if state is None:
        return None
    fn = gm_view if view == "gm" else table_view
    rows = [fn(c) for c in state["combatants"]]
    for r in rows:   # who is fighting each combatant (the reverse of engaged_with)
        r["engaged_by"] = [o["display_name"] if view == "gm" else o["name"] for o in rows
                           if o is not r and o.get("engaged_with") and
                           o["engaged_with"] == (r["display_name"] if view == "gm" else r["name"])
                           and o["status"] == "active"]
    return {"active": state["active"], "name": state["name"], "round": state["round"],
            "players": state.get("players", 0),
            "descriptions": state.get("descriptions", []) if view == "gm" else [],
            "combatants": rows}
