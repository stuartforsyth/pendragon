"""Live combat state, rebuilt by replaying a session's (non-struck) events.

Randomness never happens here: a ``combat.started`` / ``combat.added`` event
carries full combatant snapshots (HP jitter, rolled looks… already decided),
and every later event is a deterministic change (an HP delta, a status
override, a promotion). So striking any event and replaying always gives the
correct state — that is how "undo" works.
"""

from core import battle as B
from core.combat import Combatant, is_spear as B_is_spear, missile_attack, SHIELD_MISSILE_PENALTY, is_charge

DEFEATED = B.DEFEATED

COMBAT_STATE_TYPES = {
    "combat.started", "combat.added", "combat.hp", "combat.status",
    "combat.promote", "combat.modifier", "combat.engage", "combat.removed",
    "combat.round", "combat.ended", "combat.blow",
    "combat.mounted", "combat.horse", "combat.height", "combat.captured",
    "glory.reassigned", "glory.awarded", "battle.resumed", "battle.extra_round", "combat.distribute", "combat.wield", "combat.link",
    "roll.check", "combat.acted", "combat.stance", "combat.prone", "combat.barrage", "combat.shield", "combat.break", "combat.lance",
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
                "acted": set(), "barrage": (d.get("battle") or {}).get("barrage") or 0,
                "combatants": [Combatant.from_dict(c) for c in d.get("combatants", [])]}
    if t == "battle.resumed":            # a fight carried over from a paused battle
        snap = (d.get("snapshot") or {}).get("combat")
        if not snap:
            return state
        return {"active": True, "name": snap.get("name", "Encounter"), "round": snap.get("round", 1),
                "players": snap.get("players", 0), "descriptions": snap.get("descriptions", []),
                "started_event": ev["id"], "credits": dict(snap.get("credits", {})),
                "manual": dict(snap.get("manual", {})), "battle": snap.get("battle"),
                "acted": set(snap.get("acted") or []), "barrage": snap.get("barrage") or 0,
                "combatants": [Combatant.from_dict(c) for c in snap.get("combatants", [])]}
    if state is None or not state["active"]:
        return state
    if t == "combat.ended":
        state["active"] = False
        return state
    # Who has acted this round (derived, GM-only): a foe's attack roll marks it
    # done; the GM can also tick or untick by hand; Next round clears the lot.
    acted = state.setdefault("acted", set())
    if t == "roll.check":
        if d.get("cid") and "attack" in d:
            acted.add(d["cid"])
        return state
    if t == "combat.acted":
        (acted.add if d.get("on") else acted.discard)(d.get("cid"))
        return state
    if t == "combat.round":
        state["round"] = d.get("round", state["round"] + 1)
        acted.clear()
        for c in state["combatants"]:                 # a charge is one round: lances are lowered, foes take up melee weapons
            if getattr(c, "side", "foe") == "party":
                c.lance = False
            elif c.attacks and is_charge(c.attack_for(c.wielded()[0])) if c.wielded()[0] != "brawl" else False:
                nxt = c.next_weapon()
                c.wielding = nxt if nxt is not None else "brawl"
        return state
    if t == "combat.break":                       # a weapon breaks: struck from the list, the next one comes up
        for c in state["combatants"]:
            if c.id == d.get("cid"):
                if d.get("key") not in (None, "brawl"):
                    c.broken = sorted(set(getattr(c, "broken", []) or []) | {int(d["key"])})
                    if c.wielded()[0] == int(d["key"]):
                        nxt = c.next_weapon()
                        c.wielding = nxt if nxt is not None else "brawl"
        return state
    if t == "combat.lance":                       # a knight couches (or lowers) a lance for a charge
        for c in state["combatants"]:
            if c.id == d.get("cid"):
                c.lance = bool(d.get("on"))
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
    if t == "combat.barrage":                 # rounds of missile fire before the lines meet
        state["barrage"] = int(d.get("rounds") or 0)
        return state
    if t == "combat.shield":                  # the shield a knight raises against missiles
        for c in state["combatants"]:
            if c.id == d.get("cid"):
                c.shield_size = d.get("size") or "none"
        return state
    if t == "combat.stance":                  # attack / defend / evade / dodge this round
        for c in state["combatants"]:
            if c.id in (d.get("cids") or []):
                c.stance = d["stance"]
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
    if t in ("combat.mounted", "combat.prone") and getattr(c, "side", "foe") == "party":
        c.mounted = bool(d.get("mounted")) if t == "combat.mounted" else (False if d.get("on") else c.mounted)
        c.prone = bool(d.get("on")) if t == "combat.prone" else (False if c.mounted else getattr(c, "prone", False))
        return state
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
        if c.mounted:
            c.prone = False                      # nobody is prone in the saddle
    elif t == "combat.prone":
        c.prone = bool(d.get("on"))
        if c.prone:
            c.mounted = False                    # a rider knocked prone has left the saddle
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
            c.fell_round = state["round"]                # for the players' tally
        elif was_defeated and not now:
            c.defeated_with = ""
            c.fell_round = None
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
    d.update(status=c.status, down=c.down, display_name=c.display_name, prone=getattr(c, "prone", False), lance=bool(getattr(c, "lance", False)),
             shield_size=getattr(c, "shield_size", "large" if getattr(c, "side", "foe") == "party" else "none"),
             log_name=c.log_name, armor_total=c.armor_total(),
             armour_text=c.describe_armour(), looks=c.describe_looks(),
             wound_state=c.wound_state(), side=getattr(c, "side", "foe"), linked=c.linked())
    if d["side"] != "party":
        key, _ = c.wielded()
        ma = missile_attack(c)
        d.update(wielding=key, brawl=c.brawl(), stance=getattr(c, "stance", "attack"), missile=ma[0] if ma else None,
                 broken=list(getattr(c, "broken", []) or []), charging=bool(key != "brawl" and is_charge(c.attack_for(key))),
                 movement_rate=c.movement_rate(), horse_move=c.movement_rate(mounted_horse=True))
    return d


def table_view(c):
    """What players may see: no foe numbers, just a described wound state."""
    side = getattr(c, "side", "foe")
    out = {"id": c.id, "name": c.display_name, "side": side, "status": c.status,
           "wound_state": c.wound_state(), "elite": c.elite,
           "named": getattr(c, "named", False), "npc": getattr(c, "npc", False),
           "category": getattr(c, "category", "human"),
           "engaged_with": c.engaged_with, "linked": c.linked(),
           "mounted": bool(getattr(c, "mounted", True)),          # a rider is plain to see
           "prone": bool(getattr(c, "prone", False)), "lance": bool(getattr(c, "lance", False)) if side == "party" else None,
           "stance": getattr(c, "stance", "attack") if side != "party" else None}
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


FATE_WORD = {"dead": "slain", "fled": "fled", "surrendered": "surrendered", "unconscious": "unconscious"}


def defeats(state):
    """Every defeated foe in this fight with who gets the credit and the round
    it fell — the players' running tally. [{cid, name, fate, knight, knight_name, round, glory}]"""
    out = []
    for c in state["combatants"]:
        cr = credit_of(state, c)
        if cr is None:
            continue
        out.append({"cid": c.id, "name": c.display_name, "fate": FATE_WORD.get(c.status, c.status),
                    "knight": cr[0], "knight_name": cr[1], "round": getattr(c, "fell_round", None),
                    "glory": B.glory_for(c)})
    return out


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
                _, k = B.height(f.mounted, c.mounted, f.height_override, f.attacks_horse, getattr(f, "prone", False), getattr(c, "prone", False))
                if k:
                    chips.append({"foe": f.display_name, "mod": k})
            r["mounted"] = c.mounted
            r["prone"] = getattr(c, "prone", False)
            if view == "gm":
                r["missile_penalty"] = SHIELD_MISSILE_PENALTY.get(getattr(c, "shield_size", "large"), 0)
            # a rider can only reach a prone foe with a spear or lance — or Trample
            r["prone_foes"] = [f.display_name for f in mine if getattr(f, "prone", False)] if c.mounted else []
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
            fm, km = B.height(c.mounted, knight.mounted, c.height_override, c.attacks_horse,
                              getattr(c, "prone", False), getattr(knight, "prone", False))
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
            r["knight_prone"] = getattr(knight, "prone", False) if knight is not None else False
            _, wpn = c.wielded()
            r["cant_strike_prone"] = bool(knight is not None and c.mounted and r["knight_prone"]
                                          and getattr(c, "stance", "attack") != "trample" and not B_is_spear(wpn.get("weapon")))


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
    rounds = int(state.get("barrage") or 0)
    out = {"active": state["active"], "name": state["name"], "round": state["round"],
           "started_event": state.get("started_event"), "battle": state.get("battle"),
           "barrage": {"rounds": rounds, "active": state["round"] <= rounds, "left": max(0, rounds - state["round"] + 1)} if rounds else None,
           "players": state.get("players", 0),
           "descriptions": state.get("descriptions", []) if view == "gm" else [],
           "combatants": rows}
    if view == "gm":
        knights = {c.display_name for c in state["combatants"] if getattr(c, "side", "foe") == "party"}
        foes = [c for c in state["combatants"] if getattr(c, "side", "foe") != "party"]
        acted = state.get("acted") or set()
        for r in rows:
            r["acted"] = r["id"] in acted
        out.update(
            to_act=[c.id for c in foes if c.status == "active" and c.id not in acted],
            types=_types(state["combatants"]),
            gm_notes=next((d["text"] for d in out["descriptions"] if d.get("type") == "GM notes"), ""),
            defeated=[c.id for c in foes if c.status in DEFEATED],
            pool=[c.id for c in foes if c.status == "active" and not any(n in knights for n in c.linked())],
            uncredited=[c.id for c in foes if c.status in DEFEATED and credit_of(state, c) is None
                        and c.id not in state.get("credits", {})])
    out["glory"] = glory_tally(state)
    return out
