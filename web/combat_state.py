"""Live combat state, rebuilt by replaying a session's (non-struck) events.

Randomness never happens here: a ``combat.started`` / ``combat.added`` event
carries full combatant snapshots (HP jitter, rolled looks… already decided),
and every later event is a deterministic change (an HP delta, a status
override, a promotion). So striking any event and replaying always gives the
correct state — that is how "undo" works.
"""

from core import battle as B
from core.combat import Combatant

DEFEATED = B.DEFEATED

COMBAT_STATE_TYPES = {
    "combat.started", "combat.added", "combat.hp", "combat.status",
    "combat.promote", "combat.modifier", "combat.engage", "combat.removed",
    "combat.round", "combat.ended", "combat.blow",
    "combat.mounted", "combat.horse", "combat.height", "combat.captured",
    "glory.reassigned", "glory.awarded", "battle.resumed", "battle.extra_round", "combat.distribute", "combat.wield", "combat.link",
}


def apply(state, ev, promotion_cfg=None):
    """Fold one event into the combat state and return the new state."""
    t, d = ev["type"], ev.get("data", {})
    if t not in COMBAT_STATE_TYPES:
        return state
    if t == "combat.started":
        return {"active": True, "name": d.get("name", "Encounter"),
                "round": 1, "players": d.get("players", 0),
                "descriptions": d.get("descriptions", []),
                "started_event": ev["id"], "credits": {}, "manual": {}, "battle": d.get("battle"),
                "combatants": [Combatant.from_dict(c) for c in d.get("combatants", [])]}
    if t == "battle.resumed":            # a fight carried over from a paused battle
        snap = (d.get("snapshot") or {}).get("combat")
        if not snap:
            return state
        return {"active": True, "name": snap.get("name", "Encounter"), "round": snap.get("round", 1),
                "players": snap.get("players", 0), "descriptions": snap.get("descriptions", []),
                "started_event": ev["id"], "credits": dict(snap.get("credits", {})),
                "manual": dict(snap.get("manual", {})), "battle": snap.get("battle"),
                "combatants": [Combatant.from_dict(c) for c in snap.get("combatants", [])]}
    if state is None or not state["active"]:
        return state
    if t == "combat.ended":
        state["active"] = False
        return state
    if t == "combat.round":
        state["round"] = d.get("round", state["round"] + 1)
        return state
    if t == "combat.added":
        state["combatants"].append(Combatant.from_dict(d["combatant"]))
        return state
    if t == "combat.link":                    # a knight joins (or leaves) foes others may be fighting
        k = d.get("knight", "")
        for c in state["combatants"]:
            if c.id in (d.get("add") or []) and k not in c.linked():
                if c.engaged_with:
                    c.engaged_also = [*c.engaged_also, k]
                else:
                    c.engaged_with = k
            if c.id in (d.get("remove") or []) and k in c.linked():
                rest = [n for n in c.linked() if n != k]
                c.engaged_with, c.engaged_also = (rest[0], rest[1:]) if rest else ("", [])
        return state
    if t == "combat.wield":
        for c in state["combatants"]:
            if c.id in (d.get("cids") or []):
                c.wielding = d["wield"]
        return state
    if t == "combat.distribute":              # one action, many engagements
        for c in state["combatants"]:
            if c.id in (d.get("assignments") or {}):
                c.engaged_with = d["assignments"][c.id]
        return state
    if t.startswith("glory."):
        if d.get("fight") != state["started_event"]:
            return state
        if t == "glory.reassigned":
            state.setdefault("credits", {})[d.get("cid")] = d.get("knight")
        elif d.get("knight"):
            manual = state.setdefault("manual", {})
            manual[d["knight"]] = manual.get(d["knight"], 0) + int(d.get("amount", 0))
        return state
    c = next((x for x in state["combatants"] if x.id == d.get("cid")), None)
    if c is None:
        return state
    was_defeated = c.status in DEFEATED
    if getattr(c, "side", "foe") == "party" and t in ("combat.hp", "combat.blow"):
        return state                    # knights' health is the players' business
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
    elif t == "combat.engage":                # moves the foe: one knight, or none
        c.engaged_with = d.get("with", "")
        c.engaged_also = []
    elif t == "combat.removed":
        state["combatants"].remove(c)
    elif t == "combat.mounted":
        c.mounted = bool(d.get("mounted"))
    elif t == "combat.horse":
        c.attacks_horse = bool(d.get("on"))
    elif t == "combat.height":
        c.height_override = d.get("override")
    elif t == "combat.captured":
        c.captured_by = d.get("by")
    elif t == "battle.extra_round":
        c.extra_rounds = (c.extra_rounds or 0) + 1
    # Glory credit (Q10, derived): remember who the foe was fighting when it
    # fell; striking the defeating event replays without it.
    if getattr(c, "side", "foe") != "party" and state["combatants"].count(c):
        now = c.status in DEFEATED
        if now and not was_defeated:
            c.defeated_with = c.engaged_with
        elif was_defeated and not now:
            c.defeated_with = ""
    return state


def reduce(events, promotion_cfg=None):
    """Fold live events into ``{"active", "name", "round", "combatants": [Combatant]}``
    for the most recent combat (or ``None`` if the session has had none)."""
    state = None
    for ev in events:
        state = apply(state, ev, promotion_cfg)
    return state


def gm_view(c):
    """Everything the GM console needs for one combatant row."""
    d = c.to_dict()
    d.pop("_base", None)
    d.update(status=c.status, down=c.down, display_name=c.display_name,
             log_name=c.log_name, armor_total=c.armor_total(),
             armour_text=c.describe_armour(), looks=c.describe_looks(),
             wound_state=c.wound_state(), side=getattr(c, "side", "foe"), linked=c.linked())
    if d["side"] != "party":
        key, _ = c.wielded()
        d.update(wielding=key, brawl=c.brawl())
    return d


def table_view(c):
    """What players may see: no foe numbers, just a described wound state."""
    side = getattr(c, "side", "foe")
    out = {"id": c.id, "name": c.display_name, "side": side, "status": c.status,
           "wound_state": c.wound_state(), "elite": c.elite,
           "named": getattr(c, "named", False), "npc": getattr(c, "npc", False),
           "category": getattr(c, "category", "human"),
           "engaged_with": c.engaged_with, "linked": c.linked()}
    if side == "party":
        out.update(player=getattr(c, "player", ""), party_id=getattr(c, "party_id", None))
    else:
        out.update(disarmed=c.wielding == "brawl")         # attacks_horse stays GM-only
    return out


def _types(combatants):
    """One stat header per foe type (the GM's shared block): taken from a
    non-elite foe of that type where there is one, since champions differ."""
    out, seen = [], {}
    for c in combatants:
        if getattr(c, "side", "foe") == "party":
            continue
        if c.type not in seen or (out[seen[c.type]]["_elite"] and not c.elite):
            entry = {"type": c.type, "characteristics": {k: v for k, v in c.characteristics.items() if k != "APP"},
                     "attacks": c.attacks, "armour_text": c.describe_armour(),
                     "description": c.description.strip(), "notes": c.notes.strip(), "_elite": c.elite}
            if c.type in seen:
                out[seen[c.type]] = entry
            else:
                seen[c.type] = len(out)
                out.append(entry)
    for e in out:
        e.pop("_elite")
    return out


def _height_word(foe_mod, knight_mod, foe, knight):
    """The foe-line Height chip, in words: blank when the pair is level and
    nothing was cancelled, so routine fights stay uncluttered."""
    if foe.height_override == "none" and knight is not None and foe.mounted != knight.mounted:
        return "No Height"
    if foe_mod:
        return f"{foe_mod:+d} Height".replace("-", "−")
    if knight_mod and foe.attacks_horse:
        return "No Height"
    return ""


def credit_of(state, c):
    """Who a defeated foe's Glory goes to: a reassignment, else the knight it
    was fighting when it fell, else nobody. Returns (party_id, name) or None."""
    if getattr(c, "side", "foe") == "party" or c.status not in DEFEATED:
        return None
    knights = [k for k in state["combatants"] if getattr(k, "side", "foe") == "party"]
    credits = state.get("credits", {})
    if c.id in credits:
        pid = credits[c.id]
        k = next((k for k in knights if k.party_id == pid), None)
        return (pid, k.display_name) if pid and k else None
    k = next((k for k in knights if k.display_name == c.defeated_with), None) if c.defeated_with else None
    return (k.party_id, k.display_name) if k else None


def glory_tally(state):
    """Glory earned this fight per knight: defeated foes credited to them plus
    manual awards made during the fight."""
    tally = {k.party_id: 0 for k in state["combatants"] if getattr(k, "side", "foe") == "party"}
    for c in state["combatants"]:
        cr = credit_of(state, c)
        if cr:
            tally[cr[0]] = tally.get(cr[0], 0) + B.glory_for(c)
    for pid, n in state.get("manual", {}).items():
        tally[pid] = tally.get(pid, 0) + n
    return tally


def _derive(state, rows, view):
    """Height per engaged pair, Multiple Opponents per knight, captor names —
    computed from the pills on every serialise, never stored."""
    cs = state["combatants"]
    knights = {c.display_name: c for c in cs if getattr(c, "side", "foe") == "party"}
    by_id = {r["id"]: r for r in rows}
    for c in cs:
        r = by_id[c.id]
        if getattr(c, "side", "foe") == "party":
            mine = [f for f in cs if getattr(f, "side", "foe") != "party"
                    and f.status == "active" and c.display_name in f.linked()]
            n = len(mine)
            limit = B.mo_limit(any(f.mounted for f in mine))
            chips = []
            for f in mine:
                _, k = B.height(f.mounted, c.mounted, f.height_override, f.attacks_horse)
                if k:
                    chips.append({"foe": f.display_name, "mod": k})
            r["mounted"] = c.mounted
            if c.rounds is not None:
                limit = c.rounds + (c.extra_rounds or 0)
                r.update(posture=c.posture, rounds=c.rounds, extra_rounds=c.extra_rounds or 0, position=c.position,
                         last_round=state["round"] == limit, withdraws=state["round"] > limit)
            if view == "gm":
                r.update(mo={"n": n, "mod": B.multiple_opponents(n), "limit": limit, "over": n > limit},
                         height_chips=chips)
            else:
                r.update(mo_mod=B.multiple_opponents(n), mo_n=n,
                         height_chips=[{"foe": ch["foe"], "text": f"{ch['mod']:+d} Height".replace("-", "−")} for ch in chips])
            continue
        on_me = [knights[n] for n in c.linked() if n in knights and knights[n].status == "active"]
        r["outnumbered"] = -5 * (len(on_me) - 1) if len(on_me) > 1 else 0     # core p.148
        knight = knights.get(c.engaged_with)
        if knight is not None:
            fm, km = B.height(c.mounted, knight.mounted, c.height_override, c.attacks_horse)
        else:
            fm = km = 0
        cr = credit_of(state, c)
        r["credit"] = {"knight": cr[0], "name": cr[1], "glory": B.glory_for(c)} if cr else None
        captor = next((k.display_name for k in knights.values()
                       if getattr(k, "party_id", None) == c.captured_by), None) if c.captured_by else None
        r["mounted"] = c.mounted
        if view == "gm":                       # "No Height" would betray a foe going for the horse
            r["height_chip"] = _height_word(fm, km, c, knight)
        r["captured_by_name"] = captor
        if view == "gm":
            r["height"] = {"foe": fm, "knight": km}
            r["knight_mounted"] = knight.mounted if knight is not None else None


def serialise(state, view):
    if state is None:
        return None
    fn = gm_view if view == "gm" else table_view
    rows = [fn(c) for c in state["combatants"]]
    _derive(state, rows, view)
    for r in rows:   # who is fighting each combatant (the reverse of engaged_with)
        me = r["display_name"] if view == "gm" else r["name"]
        r["engaged_by"] = [o["display_name"] if view == "gm" else o["name"] for o in rows
                           if o is not r and me in (o.get("linked") or []) and o["status"] == "active"]
    out = {"active": state["active"], "name": state["name"], "round": state["round"],
           "started_event": state.get("started_event"), "battle": state.get("battle"),
           "players": state.get("players", 0),
           "descriptions": state.get("descriptions", []) if view == "gm" else [],
           "combatants": rows}
    if view == "gm":
        knights = {c.display_name for c in state["combatants"] if getattr(c, "side", "foe") == "party"}
        foes = [c for c in state["combatants"] if getattr(c, "side", "foe") != "party"]
        out.update(
            types=_types(state["combatants"]),
            gm_notes=next((d["text"] for d in out["descriptions"] if d.get("type") == "GM notes"), ""),
            defeated=[c.id for c in foes if c.status in DEFEATED],
            pool=[c.id for c in foes if c.status == "active" and not any(n in knights for n in c.linked())],
            uncredited=[c.id for c in foes if c.status in DEFEATED and credit_of(state, c) is None
                        and c.id not in state.get("credits", {})])
    out["glory"] = glory_tally(state)
    return out
