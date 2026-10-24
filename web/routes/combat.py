"""The combat tracker. Every change is an event (see web.combat_state); this
module validates a request, works out the log line (and a player-safe line for
the Table that never shows a foe's numbers), and records it."""

import random

from fastapi import APIRouter, Request

from core.rules import roll_expr

from core import battle as B
from web import battle_state as BS, combat_state as CS
from core.combat import (blow_narrative, CHAR_FULL, CHAR_ORDER, Combatant, Encounter, blow_breakdown, STANCES, DEFEND_BONUS, DEFENSIVE, HORSE_DAMAGE, is_spear,
                         missile_attack, SHIELD_MISSILE_PENALTY, SHIELD_WORD, weapon_fate, is_charge, is_couched,
                         resolve_attack, resolve_blow, roll_ransom, surrender_check)
from core.dice import NotationError, resolve_skill, roll_notation, skill_display
from core.encounter_def import to_editable
from web.routes.cast import cast_combatant, has_stats
from web.routes.common import bad, st, to_int
from web.routes.rolls import record_check, record_damage

router = APIRouter()


def _state(request):
    state = st(request)
    cs = state.combat_state()
    return state, cs


def _active(request):
    state, cs = _state(request)
    if not cs or not cs["active"]:
        bad("No combat in progress", 409)
    return state, cs


def _combatant(cs, cid):
    c = next((x for x in cs["combatants"] if x.id == cid), None)
    if c is None:
        bad("No such combatant", 404)
    return c


def _is_foe(c):
    return getattr(c, "side", "foe") != "party"


def _engaged_knight(cs, c):
    """The knight a foe is fighting, or None."""
    return next((k for k in cs["combatants"] if not _is_foe(k)
                 and k.display_name == c.engaged_with), None) if c.engaged_with else None


def _height(cs, c, knight=None):
    """Height Advantage on this foe's rolls against its engaged knight (or the one given)."""
    k = knight if knight is not None else _engaged_knight(cs, c)
    if k is None or not _is_foe(c):
        return 0
    return B.height(c.mounted, k.mounted, c.height_override, c.attacks_horse,
                    getattr(c, "prone", False), getattr(k, "prone", False))[0]


# -- Glory for defeated foes (derived on replay; see web.combat_state) --------

def _knight_pid(cs, name):
    k = next((k for k in cs["combatants"] if not _is_foe(k) and k.display_name == name), None)
    return k.party_id if k else None


def _defeat_note(cs, was_defeated, after):
    """When this change defeats a foe, the Table line names the Glory and the
    knight it goes to: (suffix, extra data)."""
    if not _is_foe(after) or was_defeated or not B.is_defeated(after.status):
        return "", {}
    pid = _knight_pid(cs, after.engaged_with)
    if not pid:
        return "", {}
    g = B.glory_for(after)
    return (f" — +{g} Glory, {after.engaged_with}" if g else ""), {"touches": [pid], "glory_amount": g}


def _who_defeated(state, cid, was_defeated):
    """A foe that fell while fighting nobody: ask the GM who gets its Glory."""
    if was_defeated:
        return None
    cs = state.combat_state()
    c = next((x for x in cs["combatants"] if x.id == cid), None) if cs else None
    if c is None or not _is_foe(c) or not B.is_defeated(c.status):
        return None
    if not any(not _is_foe(k) for k in cs["combatants"]):
        return None
    from web.combat_state import credit_of
    if credit_of(cs, c) is None and c.id not in cs.get("credits", {}):
        return {"kind": "who_defeated", "cid": cid, "name": c.display_name}
    return None


def _descriptions(combatants):
    seen, out = set(), []
    for c in combatants:
        if c.type in seen or not _is_foe(c):
            continue
        seen.add(c.type)
        parts = []
        if c.description.strip():
            parts.append(c.description.strip())
        if c.notes.strip() and c.notes.strip() != c.description.strip():
            parts.append(f"Mechanics: {c.notes.strip()}")
        if parts:
            out.append({"type": c.type, "text": "   ·   ".join(parts)})
    return out


def _active_party(state):
    return state.present_party()


def _glory_tally(state, cs, final):
    """Write each knight's Glory, highest first, to the log and the Fray —
    before a round turns over or the fight closes. The figures match the
    knight cards: the battle's running Glory when the fight is part of one."""
    b = state.battle_state() if (cs.get("battle") or {}).get("id") else None
    glory = BS.battle_glory(b) if b and b.get("id") == cs["battle"]["id"] else CS.glory_tally(cs)
    knights = [c for c in cs["combatants"] if getattr(c, "side", "foe") == "party"]
    if not knights:
        return None
    rows = sorted(({"pid": k.party_id, "name": k.display_name, "glory": int(glory.get(k.party_id, 0))} for k in knights),
                  key=lambda r: (-r["glory"], r["name"]))
    top = rows[0]["glory"]
    rank = 0
    for i, r in enumerate(rows):
        if i == 0 or r["glory"] != rows[i - 1]["glory"]:
            rank = i + 1
        r["rank"], r["winner"] = rank, top > 0 and r["glory"] == top
    winners = [r["name"] for r in rows if r["winner"]]
    head = "Final Glory" if final else f"Glory after round {cs['round']}"
    line = f"{head}: " + ", ".join(f"{r['name']} {r['glory']}" for r in rows) + (f" — {' & '.join(winners)} leads" if winners else "")
    return state.record("combat.tally", line, title=head,
                        data={"round": cs["round"], "final": final, "ranking": rows, "table_text": line})


def _end(state, cs, reason="ended"):
    """Close the combat."""
    state.record("combat.ended", f"Combat {reason}: {cs['name']}", title=cs["name"],
                 data={"name": cs["name"]})


# -- start / add / end -----------------------------------------------------

@router.post("/api/combat/start")
async def start(request: Request, body: dict):
    state, cs = _state(request)
    combat = state.combat_data
    defn = body.get("definition")
    name = (body.get("name") or "").strip()
    lone = None
    if not defn and body.get("cast"):               # a Cast NPC
        entry = state.cast.get(body["cast"])
        if entry is None or not has_stats(entry):
            bad("That NPC has no saved stats")
        lone = cast_combatant(state, entry, "n1")
        name = name or entry["npc"]["full"]
        defn = {"roster": []}
    if not defn and body.get("adversary"):          # a lone adversary
        adv = body["adversary"]
        if adv not in combat.get("adversaries", {}):
            bad("Unknown adversary")
        defn = {"roster": [{"adversary": adv, "count": 1, "per_player": False}]}
        name = name or adv
    if not defn:
        key = body.get("encounter", "")
        if key not in combat.get("encounters", {}):
            bad("Choose an encounter to launch")
        defn = combat["encounters"][key]
        name = name or key
    defn = to_editable(defn)
    name = name or defn.get("name") or "Encounter"
    party = _active_party(state) if body.get("include_party", True) else []
    link = body.get("_battle")                 # a battle's linked fight (POST /api/battle/fight)
    if link:
        party = [state.party.get(pid) for pid in body.get("_knights", []) if state.party.get(pid)]
    players = to_int(body.get("players") or len(party) or 4, "players")
    if players < 1:
        bad("At least one player")

    enc = Encounter(state.rules)
    foes = enc.generate_from_definition(defn, players, int(body.get("_multiplier") or 1))
    if lone is not None:
        foes = [lone]
    knights = []
    mounted = body.get("knights_mounted", True) is not False
    overrides = body.get("_knight_overrides") or {}
    for m in party:
        k = Combatant.from_party(m, mounted=overrides.get(m["id"], {}).get("mounted", mounted))
        for key, v in overrides.get(m["id"], {}).items():
            setattr(k, key, v)
        k.id = f"p-{m['id']}"
        knights.append(k)
    # A foe's charge weapon is only in hand when it charges (a countercharge);
    # otherwise it starts with its first melee weapon.
    charging = bool(body.get("_countercharge"))
    for f in foes:
        if any(is_charge(a) for a in f.attacks or []):
            nxt = f.next_weapon(charge_ok=charging) if charging else f.next_weapon()
            if charging:
                nxt = next((i for i, a in enumerate(f.attacks) if is_charge(a)), nxt)
            if nxt is not None:
                f.wielding = nxt
    if not foes and not knights:
        bad("That encounter has no combatants")

    if cs and cs["active"]:
        _end(state, cs, "abandoned")

    names = ", ".join(c.display_name for c in foes)
    lines = [f"Combat begins: {names}" if (body.get("adversary") or body.get("cast")) and not body.get("definition")
             else f"Launched '{name}' for {players} players: {names}"]
    lines[0] = body.get("_prefix", "") + lines[0]
    if defn.get("description", "").strip():
        lines.append(defn["description"].strip())
    descriptions = _descriptions(foes)
    if defn.get("notes", "").strip():
        descriptions.insert(0, {"type": "GM notes", "text": defn["notes"].strip()})
    ev = state.record(
        "combat.started", " — ".join(lines), title=name,
        data={"name": name, "players": players, "descriptions": descriptions,
              "combatants": [c.to_dict() for c in knights + foes], **({"battle": link} if link else {}),
              "table_text": (f"{len(foes)} foe{'s' if len(foes) != 1 else ''} take the field: {names}"
                             + (f". {defn['description'].strip()}" if defn.get("description", "").strip() else ""))})
    return {"event": ev}


@router.post("/api/combat/random")
async def random_fight(request: Request, body: dict):
    """Draw a random encounter from the library — only those carrying every
    chosen tag, never an Opportunity or an empty recipe — and launch it."""
    state = st(request)
    tags = {t.strip().lower() for t in body.get("tags") or [] if t.strip()}
    pool = []
    for key, defn in state.combat_data.get("encounters", {}).items():
        if defn.get("battle_role") == "opportunity":
            continue
        d = to_editable(defn)
        if not d["roster"] and not d.get("leader"):
            continue
        if tags <= {t.lower() for t in defn.get("tags", [])}:
            pool.append(key)
    if not pool:
        bad("No encounter has all those tags")
    key = random.choice(pool)
    return await start(request, {**body, "encounter": key, "_prefix": f"Random fight: drew '{key}' — "})


@router.post("/api/combat/add")
async def add(request: Request, body: dict):
    state, cs = _active(request)
    if body.get("cast"):
        entry = state.cast.get(body["cast"])
        if entry is None or not has_stats(entry):
            bad("That NPC has no saved stats")
        n = sum(1 for c in cs["combatants"] if c.id.startswith("n")) + 1
        c = cast_combatant(state, entry, f"n{n}")
        if any(x.display_name == c.display_name for x in cs["combatants"]):
            c.label = f"{c.label} ({n})"
        ev = state.record("combat.added", f"Added {c.display_name}", title=c.display_name,
                          data={"combatant": c.to_dict(), "table_text": f"{c.display_name} joins the fray"})
        return {"event": ev}
    adv = body.get("adversary", "")
    if adv not in state.combat_data.get("adversaries", {}):
        bad("Unknown adversary")
    enc = Encounter(state.rules)
    enc._counts = {}
    for c in cs["combatants"]:
        if _is_foe(c):
            enc._counts[c.type] = enc._counts.get(c.type, 0) + 1
    enc._seq = max([int(c.id[1:]) for c in cs["combatants"]
                    if c.id[:1] == "c" and c.id[1:].isdigit()] + [0])
    c = enc.add_one(adv)
    ev = state.record("combat.added", f"Added {c.display_name}", title=c.display_name,
                      data={"combatant": c.to_dict(),
                            "table_text": f"{c.display_name} joins the fray"})
    return {"event": ev}


@router.post("/api/combat/add-party")
async def add_party(request: Request, body: dict):
    state, cs = _active(request)
    m = state.party.get(body.get("member_id", ""))
    if m is None:
        bad("No such knight", 404)
    if any(getattr(c, "party_id", None) == m["id"] for c in cs["combatants"]):
        bad(f"{m['name']} is already in the fight")
    k = Combatant.from_party(m)
    k.id = f"p-{m['id']}"
    ev = state.record("combat.added", f"{k.display_name} joins the fight", title=k.display_name,
                      data={"combatant": k.to_dict()})
    return {"event": ev}


@router.post("/api/combat/round")
async def next_round(request: Request):
    state, cs = _active(request)
    n = cs["round"] + 1
    _glory_tally(state, cs, False)
    ev = state.record("combat.round", f"Round {n}", title=f"Round {n}", data={"round": n})
    return {"event": ev}


@router.post("/api/combat/end")
async def end(request: Request):
    state, cs = _active(request)
    _glory_tally(state, cs, True)
    _end(state, cs)
    return {"ok": True}


@router.post("/api/combat/note")
async def combat_note(request: Request, body: dict):
    state, _cs = _active(request)
    text = (body.get("text") or "").strip()
    if not text:
        bad("Empty note")
    ev = state.record("combat.note", f"— {text}", data={"text": text})
    return {"event": ev}


# -- per-combatant changes -------------------------------------------------

@router.post("/api/combat/{cid}/hp")
async def hp(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("Players keep their knights' Hit Points on their own sheets")
    delta = to_int(body.get("delta"), "delta")
    if not delta:
        bad("Enter damage as a negative number or healing as a positive one")
    was = B.is_defeated(c.status)
    old, msg = c.apply_hp(delta)          # on the replayed copy, just for the text
    text = f"{c.log_name}: {old} → {c.cur_hp} Hit Points ({delta:+d}){msg}"
    if _is_foe(c):
        if "Mortal" in msg:
            table = f"{c.display_name} is struck down — slain!"
        elif "Major" in msg:
            table = f"{c.display_name} takes a terrible wound and falls unconscious!"
        elif "revived" in msg:
            table = f"{c.display_name} stirs — revived"
        elif delta < 0:
            table = f"{c.display_name} is hit — {c.wound_state()}"
        else:
            table = f"{c.display_name} recovers — {c.wound_state()}"
    else:
        table = text
    suffix, extra = _defeat_note(cs, was, c)
    ev = state.record("combat.hp", text + suffix, title=c.display_name,
                      data={"cid": cid, "delta": delta, "table_text": table + suffix, **extra})
    return {"event": ev, "prompt": _who_defeated(state, cid, was)}


_STATUS_TEXT = {
    None: ("{n} brought back up", "{n} is back on their feet"),
    "unconscious": ("{n} knocked out (unconscious)", "{n} is knocked senseless"),
    "dead": ("{n} slain", "{n} is slain"),
    "fled": ("{n} flees the field — no longer active", "{n} flees the field"),
    "surrendered": ("{n} surrenders", "{n} surrenders"),
}


@router.post("/api/combat/{cid}/status")
async def status(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    out = body.get("out")
    if out not in _STATUS_TEXT:
        bad("Unknown status")
    if not _is_foe(c):                   # a knight: just the GM's down / out marker
        if out not in (None, "unconscious", "fled"):
            bad("A knight can only be marked down or out of the fight")
        line = {None: "{n} is back in the fight", "unconscious": "{n} is down",
                "fled": "{n} is out of the fight"}[out].format(n=c.display_name)
        ev = state.record("combat.status", line, title=c.display_name,
                          data={"cid": cid, "out": out, "table_text": line, "touches": [c.party_id]})
        return {"event": ev}
    if c.status == "fled" and out is None:
        log, table = "{n} resumes the fight — active again", "{n} returns to the fight"
    else:
        log, table = _STATUS_TEXT[out]
    was = B.is_defeated(c.status)
    after = Combatant.from_dict(c.to_dict())
    after.set_out(out)
    suffix, extra = _defeat_note(cs, was, after)
    ev = state.record("combat.status", log.format(n=c.log_name) + suffix, title=c.display_name,
                      data={"cid": cid, "out": out,
                            "table_text": table.format(n=c.display_name) + suffix, **extra})
    return {"event": ev, "prompt": _who_defeated(state, cid, was)}


@router.post("/api/combat/{cid}/acted")
async def acted(request: Request, cid: str, body: dict):
    """Tick (or untick) a combatant as having acted this round by hand — an
    attack roll ticks it automatically; Next round clears every tick."""
    state, cs = _active(request)
    c = _combatant(cs, cid)
    on = bool(body.get("on", True))
    line = f"{c.display_name} has acted this round" if on else f"{c.display_name} is yet to act this round"
    ev = state.record("combat.acted", line, title=c.display_name, visibility="gm", data={"cid": cid, "on": on})
    return {"event": ev}


@router.post("/api/combat/{cid}/promote")
async def promote(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if c.elite:
        text = f"{c.display_name} demoted to a common {c.type}"
        data = {"cid": cid, "promote": False, "table_text": f"{c.label} is no champion after all"}
    else:
        text = f"{c.label} promoted to {c.promotion_title} (elite)"
        data = {"cid": cid, "promote": True,
                "cfg": state.combat_data.get("promotion", {}),
                "table_text": f"{c.label} is revealed as {c.promotion_title}!"}
    ev = state.record("combat.promote", text, title=c.label, data=data)
    return {"event": ev}


@router.post("/api/combat/{cid}/modifier")
async def modifier(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    value = to_int(body.get("value") or 0, "modifier")
    if value == c.modifier:
        return {"event": None}
    text = (f"{c.display_name} situational modifier set to {value:+d}" if value
            else f"{c.display_name} situational modifier cleared")
    ev = state.record("combat.modifier", text, title=c.display_name, visibility="gm",
                      data={"cid": cid, "value": value})
    return {"event": ev}


@router.post("/api/combat/{cid}/engage")
async def engage(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    who = (body.get("with") or "").strip()
    if who == c.engaged_with:
        return {"event": None}
    if who:
        looks = c.describe_looks()
        text = f"{c.display_name} engaged with {who}" + (f" — {looks}" if looks else "")
        table = f"{c.display_name} engages {who}" + (f" — {looks}" if looks else "")
    else:
        text = table = f"{c.display_name} no longer engaged"
    data = {"cid": cid, "with": who, "table_text": table}
    pid = _knight_pid(cs, who) if _is_foe(c) else None
    if pid:
        data["touches"] = [pid]
    ev = state.record("combat.engage", text, title=c.display_name, data=data)
    return {"event": ev}


# -- mounted pills, attacking the horse, Height override, captives (S2) -------

@router.post("/api/combat/{cid}/mounted")
async def mounted(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    on = bool(body.get("mounted"))
    if on == c.mounted:
        return {"event": None}
    line = f"{c.display_name} is {'mounted' if on else 'on foot'}"
    data = {"cid": cid, "mounted": on, "table_text": line}
    if not _is_foe(c):
        data["touches"] = [c.party_id]
    ev = state.record("combat.mounted", line, title=c.display_name, data=data)
    return {"event": ev}


@router.post("/api/combat/divider")
async def divider(request: Request, body: dict):
    """A divider the GM drops by hand — "The gate falls", "Nightfall"."""
    state = st(request)
    text = (body.get("text") or "").strip()
    if not text:
        bad("Say what the divider marks")
    return {"event": _divider(state, text, kind="gm")}


@router.post("/api/combat/{cid}/lance")
async def lance(request: Request, cid: str, body: dict):
    """A knight couches a lance for a charge this round (or lowers it). With it
    set, the charge's weapon rules apply to them: a partial success or tie
    breaks the lance, a fumble breaks it and calls for Table 7.2."""
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if _is_foe(c):
        bad("Foes charge by taking up their charge weapon")
    on = bool(body.get("on"))
    if on == bool(getattr(c, "lance", False)):
        return {"event": None}
    line = f"{c.display_name} couches a lance and charges" if on else f"{c.display_name} lowers the lance"
    ev = state.record("combat.lance", line, title=c.display_name, data={"cid": cid, "on": on, "table_text": line, "touches": [c.party_id]})
    return {"event": ev}


def _table_72(state, c, roll_fn):
    """Table 7.2 for a foe who fumbled a couched lance: Horsemanship decides
    splinters, a fall or a horse brought down. Armour does not protect."""
    horsemanship = int((c.skills or {}).get("Horsemanship") or 10)
    die, outcome = resolve_skill(horsemanship)
    fn = c.display_name
    text = {"critical": f"{fn} keeps the saddle — the broken lance does no further harm",
            "success": f"{fn} is struck by flying splinters",
            "failure": f"the tip buries itself and launches {fn} from the saddle",
            "fumble": f"the tip buries itself and brings down {fn} and horse together"}[outcome]
    dmg = {"critical": 0, "success": roll_fn("1D6"), "failure": roll_fn("2D6"), "fumble": roll_fn("3D6")}[outcome]
    state.record("combat.check", f"{fn} — Table 7.2 (Horsemanship {horsemanship}): {die} — {outcome.upper()}: {text}" + (f", {dmg} damage (armour does not protect)" if dmg else ""),
                 title=f"{fn} — Lance fumble", data={"cid": c.id, "roll": die, "outcome": outcome, "label": "Table 7.2", "table_text": f"{fn}: {text}"})
    if dmg:
        state.record("combat.hp", f"{fn} takes {dmg} from the lance fumble", title=fn, data={"cid": c.id, "delta": -dmg, "table_text": f"{fn} is hurt by the broken lance"})
    if outcome in ("failure", "fumble"):
        state.record("combat.prone", f"{fn} is thrown — prone", title=fn, data={"cid": c.id, "on": True, "table_text": f"{fn} is thrown from the saddle"})
    return outcome


@router.post("/api/combat/barrage")
async def barrage(request: Request, body: dict):
    """Rounds of missile fire before the lines meet (a battle's barrage sets
    this itself; in free play the GM sets it). 0 clears it."""
    state, cs = _active(request)
    n = to_int(body.get("rounds") or 0, "rounds")
    if not 0 <= n <= 6:
        bad("0 to 6 rounds")
    line = f"Barrage: {n} round{'s' if n != 1 else ''} of missile fire before contact" if n else "No barrage — straight into contact"
    ev = state.record("combat.barrage", line, title="Barrage", data={"rounds": n, "table_text": line})
    return {"event": ev}


@router.post("/api/combat/{cid}/shield")
async def shield_size(request: Request, cid: str, body: dict):
    """The shield a knight raises against missiles: its size sets the Missile
    Attack Penalty on the archer (none / small 0, medium −5, large −10)."""
    state, cs = _active(request)
    c = _combatant(cs, cid)
    size = body.get("size")
    if size not in SHIELD_MISSILE_PENALTY:
        bad("Shield is none, small, medium or large")
    pen = SHIELD_MISSILE_PENALTY[size]
    line = f"{c.display_name} carries a {SHIELD_WORD[size]}" + (f" — archers at {pen:+d}".replace("-", "−") if pen else "") if size != "none" else f"{c.display_name} has no shield"
    ev = state.record("combat.shield", line, title=c.display_name, data={"cid": cid, "size": size, "table_text": line, **({"touches": [c.party_id]} if not _is_foe(c) else {})})
    return {"event": ev}


def _loose(state, cs, c, body, gm_only=False):
    """One missile shot at the knight this foe faces (core.combat.missile-weapons):
    an unopposed roll at the archer's skill less the knight's shield penalty and
    any range or wind modifier the GM adds; on a hit, a mounted knight's horse
    takes it on 1–4 of 1D6; damage goes against armour alone."""
    ma = missile_attack(c)
    if not ma:
        bad(f"{c.display_name} has no missile weapon")
    key, atk = ma
    knight = _engaged_knight(cs, c)
    if knight is None:
        bad(f"{c.display_name} isn't facing a knight — engage one first")
    pen = SHIELD_MISSILE_PENALTY.get(getattr(knight, "shield_size", "large"), 0)
    adjust = to_int(body.get("adjust") or 0, "modifier")
    bits = ([f"shield {pen}".replace("-", "−")] if pen else []) + ([f"{adjust:+d}".replace("-", "−")] if adjust else [])
    label = atk["weapon"] + (f" ({', '.join(bits)})" if bits else "")
    roll = record_check(state, label=label, value=atk["value"], modifier=c.modifier + pen + adjust, actor=c.log_name,
                        extra={"cid": c.id, "attack": key, "missile": True, "shield_penalty": pen, "adjust": adjust, "target": knight.id},
                        visibility="gm" if gm_only else "public")
    out = {"event": roll, "blow": None, "hit": False, "where": None, "archer": c.display_name, "weapon": atk["weapon"],
           "outcome": roll["data"]["outcome"], "damage": 0}
    oc = roll["data"]["outcome"]
    if oc in ("critical", "success"):
        where = "rider"
        if knight.mounted:
            d6 = roll_expr("1D6")
            where = "mount" if d6 <= 4 else "rider"
        out.update(hit=True, where=where)
        out["blow"] = record_blow(state, cs, {"attacker": c.id, "attack": key, "target": knight.id,
                                               "critical": oc == "critical", "shield": False, "at_horse": where == "mount",
                                               "_gm_only": gm_only})
        out["damage"] = (out["blow"]["data"].get("blow") or {}).get("damage", 0)
    elif not gm_only:
        miss = f"{c.log_name}'s {atk['weapon'].lower()} misses {knight.display_name}" + (" — a fumble" if oc == "fumble" else "")
        out["miss"] = state.record("combat.note", miss, title=c.display_name, data={"text": miss, "table_text": miss, "touches": [knight.party_id]})
    return out


def _divider(state, text, **extra):
    """A thin rule in the log and the Fray: the start of something new."""
    return state.record("divider", text, title="", data={"text": text, "table_text": text, **extra})


def _volley(state, knight, archers, body):
    """Every archer facing one knight looses together. The shots are rolled
    one by one for the GM's log, but the players get a single card: how many
    came, what hit the rider, what hit the horse, what missed."""
    _divider(state, f"Volley at {knight.display_name}", kind="volley", touches=[knight.party_id])
    shots = []
    for c in archers:
        shots.append(_loose(state, state.combat_state(), c, body, gm_only=True))
    rider = [s_ for s_ in shots if s_["hit"] and s_["where"] == "rider"]
    mount = [s_ for s_ in shots if s_["hit"] and s_["where"] == "mount"]
    missed = [s_ for s_ in shots if not s_["hit"]]
    kn = knight.display_name
    n = len(shots)
    what = shots[0]["weapon"].lower() if shots else "missile"
    plural = what if what.endswith("s") else what + "s"
    parts = []
    if rider:
        parts.append(f"{len(rider)} strike{'s' if len(rider) == 1 else ''} {kn} for {' + '.join(str(s_['damage']) for s_ in rider)} damage")
    if mount:
        parts.append(f"{len(mount)} hit{'s' if len(mount) == 1 else ''} the horse for {' + '.join(str(s_['damage']) for s_ in mount)}")
    if missed:
        parts.append(f"{len(missed)} miss{'es' if len(missed) == 1 else ''}")
    head = f"{n} {plural if n != 1 else what} fl{'y' if n != 1 else 'ies'} at {kn}: " if n else f"No shots at {kn}"
    text = head + "; ".join(parts) + ("." if parts else "")
    if rider or mount:
        text += " Armour only — no shield."
    total = sum(s_["damage"] for s_ in rider)
    ev = state.record("combat.volley", text, title=f"Volley at {kn}",
                      data={"cid": knight.id, "knight": kn, "count": n, "weapon": shots[0]["weapon"] if shots else "",
                            "shots": [{"archer": s_["archer"], "outcome": s_["outcome"], "where": s_["where"] if s_["hit"] else None,
                                       "damage": s_["damage"], "critical": s_["outcome"] == "critical"} for s_ in shots],
                            "rider_damage": total, "mount_damage": sum(s_["damage"] for s_ in mount),
                            "table_text": text, "touches": [knight.party_id]})
    return {"event": ev, "shots": n, "hits": len(rider) + len(mount), "mounts": len(mount), "rider_damage": total}


@router.post("/api/combat/{cid}/volley")
async def volley(request: Request, cid: str, body: dict):
    """The archers facing one knight loose at them together — one card for the players."""
    state, cs = _active(request)
    knight = _combatant(cs, cid)
    if _is_foe(knight):
        bad("A volley is aimed at a knight")
    archers = [c for c in cs["combatants"] if _is_foe(c) and not c.down and missile_attack(c) and _engaged_knight(cs, c) is knight]
    if not archers:
        bad(f"No archer is facing {knight.display_name}")
    return _volley(state, knight, archers, body)


@router.post("/api/combat/{cid}/loose")
async def loose(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("Knights' shots are the players' business")
    return _loose(state, cs, c, body)


@router.post("/api/combat/loose-all")
async def loose_all(request: Request, body: dict):
    """The whole line looses: every foe of the type still fighting and facing a knight."""
    state, cs = _active(request)
    foes = [c for c in cs["combatants"] if _is_foe(c) and not c.down and c.type == body.get("type")
            and missile_attack(c) and _engaged_knight(cs, c) is not None]
    if not foes:
        bad(f"No {body.get('type')} with a missile weapon is facing a knight")
    by_knight = {}
    for c in foes:
        by_knight.setdefault(_engaged_knight(cs, c).id, []).append(c)
    results = [_volley(state, _combatant(cs, kid), archers, body) for kid, archers in by_knight.items()]
    return {"shots": sum(r["shots"] for r in results), "hits": sum(r["hits"] for r in results),
            "mounts": sum(r["mounts"] for r in results), "events": [r["event"] for r in results]}


@router.post("/api/combat/{cid}/prone")
async def prone(request: Request, cid: str, body: dict):
    """Knocked prone, or back on their feet. Prone and mounted are exclusive:
    a rider knocked prone has left the saddle (standing up takes their action
    — the GM's call when to clear it)."""
    state, cs = _active(request)
    c = _combatant(cs, cid)
    on = bool(body.get("on"))
    if on == getattr(c, "prone", False):
        return {"event": None}
    line = f"{c.display_name} is knocked prone" if on else f"{c.display_name} is back on their feet"
    if on and c.mounted:
        line = f"{c.display_name} is down from the saddle, prone"
    data = {"cid": cid, "on": on, "table_text": line}
    if not _is_foe(c):
        data["touches"] = [c.party_id]
    ev = state.record("combat.prone", line, title=c.display_name, data=data)
    return {"event": ev}


def _after_knockdown(state, cs, blow_ev):
    """An automatic knockdown lays a foe prone (core.combat.knockdown); from the
    saddle it also means a fall — 1D6 and the weapon dropped. The DEX-check
    case is the GM's: mark prone by hand if the roll fails."""
    d = (blow_ev or {}).get("data") or {}
    if (d.get("blow") or {}).get("knockdown") != "automatic" or not d.get("cid"):
        return []
    c = next((x for x in cs["combatants"] if x.id == d["cid"]), None)
    if c is None or not _is_foe(c) or getattr(c, "prone", False) or c.down:
        return []
    out = []
    if c.mounted:
        dmg = roll_expr("1D6")
        out.append(state.record("combat.prone", f"{c.display_name} is thrown from the saddle — prone", title=c.display_name,
                                data={"cid": c.id, "on": True, "table_text": f"{c.display_name} is thrown from the saddle"}))
        out.append(state.record("combat.hp", f"{c.display_name} takes {dmg} from the fall", title=c.display_name,
                                data={"cid": c.id, "delta": -dmg, "table_text": f"{c.display_name} is hurt in the fall"}))
        if c.wielding != "brawl":
            out.append(state.record("combat.wield", f"{c.display_name} drops their weapon in the fall — fights on with Brawling", title=c.display_name,
                                    data={"cids": [c.id], "wield": "brawl", "table_text": f"{c.display_name} drops their weapon"}))
    else:
        out.append(state.record("combat.prone", f"{c.display_name} is knocked prone", title=c.display_name,
                                data={"cid": c.id, "on": True, "table_text": f"{c.display_name} is knocked prone"}))
    return out


@router.post("/api/combat/{cid}/horse")
async def horse(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("Only a foe can go for a knight's horse")
    on = bool(body.get("on"))
    if on == c.attacks_horse:
        return {"event": None}
    k = _engaged_knight(cs, c)
    line = (f"{c.display_name} goes for {k.display_name + chr(39) + 's' if k else 'the'} horse" if on
            else f"{c.display_name} turns from the horse to the rider")
    ev = state.record("combat.horse", line, title=c.display_name, visibility="gm",   # a surprise for the players
                      data={"cid": cid, "on": on})
    return {"event": ev}


@router.post("/api/combat/{cid}/height")
async def height_override(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("Height is set on the foe")
    override = body.get("override")
    if override not in (None, "none"):
        bad("Height override is automatic or none")
    if override == c.height_override:
        return {"event": None}
    line = (f"{c.display_name}: no Height advantage (two-handed spear or halberd)" if override
            else f"{c.display_name}: Height worked out from who is mounted")
    ev = state.record("combat.height", line, title=c.display_name,
                      data={"cid": cid, "override": override, "table_text": line})
    return {"event": ev}


@router.post("/api/combat/{cid}/captured")
async def captured(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c):
        bad("A knight can't be taken captive here")
    if "by" in body and body["by"] is None:
        if not c.captured_by:
            return {"event": None}
        line = f"{c.display_name} is released"
        ev = state.record("combat.captured", line, title=c.display_name,
                          data={"cid": cid, "by": None, "table_text": line, "touches": [c.captured_by]})
        return {"event": ev}
    if c.status not in ("unconscious", "surrendered"):
        bad("Only an unconscious or surrendered foe can be taken captive")
    by = body.get("by")
    if by:
        k = next((x for x in cs["combatants"] if not _is_foe(x) and x.party_id == by), None)
        if k is None:
            bad("That knight isn't in the fight")
    else:
        k = _engaged_knight(cs, c)
        if k is None:
            bad("Say which knight took them captive")
    line = f"{c.display_name} is taken captive by {k.display_name}"
    ev = state.record("combat.captured", line, title=c.display_name,
                      data={"cid": cid, "by": k.party_id, "table_text": line, "touches": [k.party_id]})
    return {"event": ev}


@router.post("/api/combat/{cid}/credit")
async def credit(request: Request, cid: str, body: dict):
    """Give a defeated foe's Glory to a knight (or to nobody): the answer to
    "Who defeated them?" and the strip's "Reassign Glory"."""
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not _is_foe(c) or not B.is_defeated(c.status):
        bad("Only a defeated foe's Glory can be credited")
    pid = body.get("knight")
    k = None
    if pid:
        k = next((x for x in cs["combatants"] if not _is_foe(x) and x.party_id == pid), None)
        if k is None:
            bad("That knight isn't in the fight")
    g = B.glory_for(c)
    line = (f"+{g} Glory · {k.display_name} defeated {c.display_name}" if k
            else f"No Glory for {c.display_name}")
    data = {"fight": cs["started_event"], "cid": cid, "knight": pid or None,
            "knight_name": k.display_name if k else "", "foe": c.display_name, "amount": g if k else 0,
            "table_text": line}
    if k:
        data.update(touches=[pid], glory_amount=g)
    ev = state.record("glory.reassigned", line, title="Glory", data=data)
    return {"event": ev}


@router.post("/api/combat/link")
async def link(request: Request, body: dict):
    """A knight joins a foe (dragged onto it). A foe nobody fights is simply
    engaged; one already fighting another knight now fights both."""
    state, cs = _active(request)
    foe = _combatant(cs, body.get("cid"))
    knight = next((k for k in cs["combatants"] if not _is_foe(k) and k.display_name == body.get("knight")), None)
    if not _is_foe(foe) or knight is None:
        bad("Drag a knight onto a foe")
    if knight.display_name in foe.linked():
        return {"event": None}
    if not foe.engaged_with:
        return await engage(request, foe.id, {"with": knight.display_name})
    others = " and ".join(foe.linked())
    line = f"{knight.display_name} joins {others} against {foe.display_name}"
    ev = state.record("combat.link", line, title=foe.display_name,
                      data={"knight": knight.display_name, "add": [foe.id], "table_text": line,
                            "touches": [k.party_id for k in cs["combatants"] if not _is_foe(k) and k.display_name in [*foe.linked(), knight.display_name]]})
    return {"event": ev}


@router.post("/api/combat/unlink")
async def unlink(request: Request, body: dict):
    """A knight leaves one foe (``cid``) or every foe (dragged onto empty ground)."""
    state, cs = _active(request)
    name = body.get("knight") or ""
    foes = [c for c in cs["combatants"] if _is_foe(c) and name in c.linked()
            and (not body.get("cid") or c.id == body["cid"])]
    if not foes:
        return {"event": None}
    line = f"{name} breaks off from {', '.join(f.display_name for f in foes)}"
    ev = state.record("combat.link", line, title=name,
                      data={"knight": name, "remove": [f.id for f in foes], "table_text": line})
    return {"event": ev}


@router.post("/api/combat/wield")
async def wield(request: Request, body: dict):
    """Change the weapon in hand: one foe (``cid``), or every foe of a type still
    fighting (``type``) — e.g. all Knights of Gorre drop lances for swords.
    ``wield`` is an attack index, or "brawl" for a disarmed foe."""
    state, cs = _active(request)
    w = body.get("wield")
    if body.get("type"):
        if w == "brawl":
            bad("Disarm foes one at a time")
        targets = [c for c in cs["combatants"] if _is_foe(c) and c.type == body["type"] and not c.down]
        if not targets:
            bad(f"No {body['type']} still fighting")
    else:
        targets = [_combatant(cs, body.get("cid"))]
    try:
        atk = targets[0].attack_for(w)
    except LookupError:
        bad("Unknown weapon")
    w = w if w == "brawl" else int(w)
    if w != "brawl" and any(w in (getattr(c, "broken", []) or []) for c in targets):
        bad(f"That {atk['weapon'].lower()} is broken")
    targets = [c for c in targets if c.wielding != w]
    if not targets:
        return {"event": None}
    if w == "brawl":
        text = f"{targets[0].display_name} is disarmed — fights on with Brawling"
        title = targets[0].display_name
    else:
        names = targets[0].display_name if len(targets) == 1 else f"{len(targets)} {targets[0].type}"
        was_brawl = len(targets) == 1 and targets[0].wielding == "brawl"
        text = f"{names} {'recovers a weapon:' if was_brawl else 'switch to' if len(targets) > 1 else 'switches to'} {atk['weapon']}"
        title = names
    ev = state.record("combat.wield", text, title=title,
                      data={"cids": [c.id for c in targets], "wield": w, "table_text": text})
    return {"event": ev}


_STANCE_TEXT = {"attack": "{n} {v} to attack", "defend": "{n} {v} on the defensive (+10, no damage either way)",
                "evade": "{n} {v} to evade — breaking away", "dodge": "{n} {v} to dodge",
                "trample": "{n} {v} to ride down the fallen — Trample"}
_STANCE_TABLE = {"attack": "{n} attack", "defend": "{n} defend", "evade": "{n} try to evade", "dodge": "{n} dodge",
                 "trample": "{n} ride down the fallen"}


@router.post("/api/combat/stance")
async def stance(request: Request, body: dict):
    """What a foe does when the knight comes at it this round: attack (the
    default), defend, evade or dodge — one foe (``cid``) or every foe of a
    type still fighting (``type``). Dodge is for foes on their feet."""
    state, cs = _active(request)
    st_ = body.get("stance")
    if st_ not in STANCES:
        bad("Stance is attack, defend, evade or dodge")
    if body.get("type"):
        targets = [c for c in cs["combatants"] if _is_foe(c) and c.type == body["type"] and not c.down]
        if st_ == "dodge":
            targets = [c for c in targets if not c.mounted]
        if st_ == "trample":
            targets = [c for c in targets if c.mounted]
        if not targets:
            bad(f"No {body['type']} still fighting" + (" on foot" if st_ == "dodge" else ""))
    else:
        c = _combatant(cs, body.get("cid"))
        if not _is_foe(c):
            bad("Knights' actions are the players' business")
        if st_ == "dodge" and c.mounted:
            bad("Dodge is for foes on their feet — a rider evades instead")
        if st_ == "trample" and not c.mounted:
            bad("Only a rider can trample")
        targets = [c]
    targets = [c for c in targets if getattr(c, "stance", "attack") != st_]
    if not targets:
        return {"event": None}
    one = len(targets) == 1
    names = targets[0].display_name if one else f"{len(targets)} {targets[0].type}"
    verb = {"attack": "turns" if one else "turn", "defend": "goes" if one else "go",
            "evade": "turns" if one else "turn", "dodge": "sets" if one else "set", "trample": "wheels" if one else "wheel"}[st_]
    text = _STANCE_TEXT[st_].format(n=names, v=verb) if st_ != "dodge" else f"{names} {'braces' if one else 'brace'} to dodge"
    ev = state.record("combat.stance", text, title=names,
                      data={"cids": [c.id for c in targets], "stance": st_, "table_text": _STANCE_TABLE[st_].format(n=names)})
    return {"event": ev}


def even_split(foes, knights):
    """Spread active foes evenly over the knights (names), keeping any foe on
    its current knight while that knight is under its share. Returns
    {cid: knight_name} for the foes that move."""
    n, k = len(foes), len(knights)
    share = {name: n // k + (1 if i < n % k else 0) for i, name in enumerate(knights)}
    load = {name: 0 for name in knights}
    keep, moving = [], []
    for c in foes:
        if c.engaged_with in load and load[c.engaged_with] < share[c.engaged_with]:
            load[c.engaged_with] += 1
            keep.append(c)
        else:
            moving.append(c)
    out = {}
    for c in moving:
        name = min(knights, key=lambda x: (load[x] - share[x], knights.index(x)))
        load[name] += 1
        if c.engaged_with != name:
            out[c.id] = name
    return out


@router.post("/api/combat/distribute")
async def distribute(request: Request):
    """Distribute foes equally: active foes only — defeated foes stay with the
    knight they fell to, so their Glory still counts for him."""
    state, cs = _active(request)
    knights = [c for c in cs["combatants"] if not _is_foe(c) and c.status == "active"]
    foes = [c for c in cs["combatants"] if _is_foe(c) and c.status == "active" and not c.engaged_also]   # never split a shared foe
    if not knights:
        bad("No knights in the fight to share the foes")
    if not foes:
        bad("No foes still fighting")
    moves = even_split(foes, [k.display_name for k in knights])
    if not moves:
        return {"event": None}
    per = len(foes) // len(knights)
    line = (f"The foes spread out — {per} on each knight" if len(foes) % len(knights) == 0
            else f"The foes spread out — {per}–{per + 1} on each knight")
    pids = sorted({k.party_id for k in knights if k.display_name in moves.values()})
    ev = state.record("combat.distribute", f"{line} ({len(moves)} moved)", title="Foes distributed",
                      data={"assignments": moves, "table_text": line, "touches": pids})
    return {"event": ev}


@router.post("/api/combat/{cid}/remove")
async def remove(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    ev = state.record("combat.removed", f"{c.display_name} removed from the encounter",
                      title=c.display_name, visibility="gm", data={"cid": cid})
    return {"event": ev}


# -- rolls -------------------------------------------------------------------

@router.post("/api/combat/{cid}/roll")
async def roll(request: Request, cid: str, body: dict):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    what, key = body.get("what"), body.get("key")
    masked = False      # combat rolls are always public — players see every roll
    # the knight this roll is against: chosen in the attack pane, else the one engaged
    target = _combatant(cs, body["target"]) if body.get("target") else None
    if target is not None and _is_foe(target):
        bad("The target must be a knight")
    actor = f"{c.display_name} ({target.display_name})" if target is not None else c.log_name
    common = dict(actor=actor, masked=masked, extra={"cid": cid, **({"target": target.id} if target is not None else {})})
    if what == "char":
        if key not in CHAR_ORDER:
            bad("Unknown characteristic")
        ev = record_check(state, label=CHAR_FULL[key], value=c.characteristics[key],
                          kind="characteristic", modifier=c.modifier, **common)
    elif what in ("attack", "damage"):
        if key in (None, ""):
            key = c.wielded()[0]                 # the weapon in hand
        try:
            atk = c.attack_for(key)
        except LookupError:
            bad("Unknown attack")
        if atk.get("value") is None:
            bad(f"{c.display_name} has no Brawling skill — set one in the Adversaries editor")
        key = key if key == "brawl" else int(key)
        if what == "attack":
            stance_ = getattr(c, "stance", "attack") if _is_foe(c) else "attack"
            height = _height(cs, c, target)
            # Outnumbered by knights: −5 per knight after the first (core p.148), counted
            # from the links; plus the GM's one-roll ± for anything else. A Dodge is one
            # roll against every attacker and skips the outnumbered penalty.
            on_it = [k for k in cs["combatants"] if not _is_foe(k) and k.status == "active" and k.display_name in c.linked()]
            outnumbered = -5 * (len(on_it) - 1) if len(on_it) > 1 and stance_ != "dodge" else 0
            adjust = to_int(body.get("adjust") or 0, "modifier")
            defend = DEFEND_BONUS if stance_ == "defend" else 0
            common["extra"].update(attack=key, height=height, outnumbered=outnumbered, adjust=adjust, stance=stance_)
            bits = ([f"Defend +{defend}"] if defend else []) + ([f"Height {height:+d}"] if height else []) \
                + ([f"−{-outnumbered} outnumbered"] if outnumbered else []) + ([f"{adjust:+d}".replace("-", "−")] if adjust else [])
            knight_ = target if target is not None else _engaged_knight(cs, c)
            knight_prone = bool(knight_ is not None and getattr(knight_, "prone", False))
            if stance_ == "attack" and c.mounted and knight_prone and not is_spear(atk["weapon"]):
                bad(f"A rider can't strike a prone foe with a {atk['weapon'].lower()} — only a spear or lance reaches; set the stance to Trample instead")
            if stance_ in ("evade", "dodge"):                 # Movement Rate vs the knight's action
                value = c.movement_rate(mounted_horse=stance_ == "evade" and c.mounted)
                base_label = f"{stance_.capitalize()} (Movement{' — horse' if stance_ == 'evade' and c.mounted else ''})"
            elif stance_ == "trample":                        # Horsemanship; the horse won't tread on things: no Height for the rider
                if not c.mounted:
                    bad("Only a rider can trample")
                if not knight_prone:
                    bad(f"{knight_.display_name if knight_ else 'The knight'} isn't prone — Trample is for the fallen")
                value = int(c.skills.get("Horsemanship") or 10)
                height = min(height, 0)
                common["extra"]["height"] = height
                bits = [b_ for b_ in bits if not b_.startswith("Height")] + ["the knight's action −5"]
                base_label = "Trample (Horsemanship)" + ("" if c.skills.get("Horsemanship") else " — no skill listed, 10 assumed")
            else:
                value, base_label = atk["value"], atk["weapon"]
            label = base_label + (f" ({', '.join(bits)})" if bits else "")
            ev = record_check(state, label=label, value=value,
                              modifier=c.modifier + height + outnumbered + adjust + defend, **common)
        else:
            ev = record_damage(state, label=atk["weapon"], expr=atk["damage"],
                               critical=bool(body.get("critical")),
                               rebated=bool(body.get("rebated")),
                               actor=c.log_name, masked=masked, extra={"cid": cid})
    elif what == "skill":
        if key not in c.skills:
            bad("Unknown skill")
        ev = record_check(state, label=key, value=c.skills[key], modifier=c.modifier, **common)
    else:
        bad("Unknown roll")
    return {"event": ev}


@router.post("/api/combat/{cid}/surrender")
async def surrender(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    k = _engaged_knight(cs, c)
    minus5 = -5 if (k is not None and k.mounted and not c.mounted) else 0
    roll_, outcome, line = surrender_check(c, modifier=minus5)
    ev = state.record("combat.check", line, title=f"{c.display_name} — Surrender check",
                      data={"cid": cid, "roll": roll_, "outcome": outcome,
                            "label": "Surrender check"})
    return {"event": ev}


@router.post("/api/combat/{cid}/ransom")
async def ransom(request: Request, cid: str):
    state, cs = _active(request)
    c = _combatant(cs, cid)
    if not c.ransom:
        bad("No ransom table for this combatant")
    roll_, line = roll_ransom(c)
    ev = state.record("combat.check", line, title=f"{c.display_name} — Ransom",
                      data={"cid": cid, "roll": roll_, "label": "Ransom"})
    return {"event": ev}


# -- blows: damage → rebate → protection → wound ------------------------------

def _weapon_def(state, name):
    return state.combat_data.get("weapons", {}).get(name or "", {})


@router.post("/api/combat/blow")
async def blow(request: Request, body: dict):
    """Resolve one blow (Core Ch.7 Table 7.1, Ch.8). The attacker's weapon
    damage is rolled here — or a total the player rolled is entered — then
    critical/reckless dice, rebating, armour and shield/parry are applied and
    the wound lands on the target. Every number is shown to the players."""
    state, cs = _active(request)
    target = _combatant(cs, body["target"]) if body.get("target") else None
    was = bool(target and B.is_defeated(target.status))
    ev = record_blow(state, cs, body)
    _after_knockdown(state, state.combat_state(), ev)
    return {"event": ev, "prompt": _who_defeated(state, target.id, was) if target else None}


def record_blow(state, cs, body):
    attacker = _combatant(cs, body["attacker"]) if body.get("attacker") else None
    target = _combatant(cs, body["target"]) if body.get("target") else None
    weapon, expr = (body.get("weapon") or "").strip(), (body.get("expr") or None)
    unarmed = False
    if attacker is not None and body.get("attack") not in (None, ""):
        try:
            atk = attacker.attack_for(body["attack"])
        except LookupError:
            bad("Unknown attack")
        weapon = atk["weapon"]
        expr = atk["damage"]
        unarmed = bool(atk.get("unarmed"))
    rolled = body.get("damage")
    if rolled not in (None, ""):
        rolled, expr = to_int(rolled, "damage"), None      # a typed total wins
        if rolled < 0:
            bad("Damage can't be negative")
    elif expr:
        try:
            roll_notation(expr)
        except NotationError:
            bad(f"'{expr}' isn't dice — enter the damage rolled (e.g. a lance uses the horse's damage)")
    else:
        bad("Pick a weapon or enter the damage rolled")
    extra = (body.get("extra") or "").strip()
    wdef = _weapon_def(state, weapon)
    if body.get("vs_mail") and wdef.get("vs_mail"):
        extra = (extra + "+1D6") if extra else "1D6"     # Mace +1D6; Great Mace +3D6 replaces +2D6
    if extra:
        try:
            roll_notation(extra)
        except NotationError:
            bad(f"Can't read the extra damage '{extra}'")
    unarmed = unarmed or bool(attacker and not wdef and weapon.lower() in ("fist", "punch", "unarmed", "brawling"))
    through = "strikes through shields" in (wdef.get("advantage", "").lower())

    if target is not None and not _is_foe(target):
        return _report_blow_on_knight(state, attacker, target, weapon, expr, rolled, extra, body, unarmed)

    shield_value = body.get("shield_value")
    shield_value = (to_int(shield_value, "shield") if shield_value not in (None, "")
                    else (target.shield if target else 0))
    b = resolve_blow(
        expr=expr, rolled=rolled, critical=bool(body.get("critical")), unarmed=unarmed,
        reckless=bool(body.get("reckless")), extra=extra, rebated=bool(body.get("rebated")),
        armour=target.armor_points if target else 0, shield=shield_value,
        shield_applies=bool(body.get("shield")), through_shields=through,
        knockdown=(target.knockdown if target else 0))
    if not target:
        b["armour"] = 0

    who = attacker.display_name if attacker else (body.get("attacker_name") or "").strip()
    if not who and target is not None and _is_foe(target):
        who = target.engaged_with or ""          # a knight's blow: the knight this foe fights
    what = weapon or ""
    hit = ("CRITICAL " if b["critical"] else "") + ("reckless " if b["reckless"] else "")
    head = f"{who}’s {what or 'blow'}" if who else (what or "A blow")
    breakdown = blow_breakdown(b)
    suffix, gextra = "", {}
    if target:
        tgt = Combatant.from_dict(target.to_dict())      # a copy, just for the text
        old, msg = tgt.apply_hp(-b["wound"]) if b["wound"] else (tgt.cur_hp, "")
        suffix, gextra = _defeat_note(cs, B.is_defeated(target.status), tgt)
        consequences = []
        if b["knockdown"] == "automatic":
            consequences.append(f"KNOCKED DOWN ({b['full']} > twice Knockdown {target.knockdown})")
        elif b["knockdown"] == "check":
            consequences.append(f"Knockdown check — DEX roll ({b['full']} > Knockdown {target.knockdown})")
        if b["shield_broken"]:
            consequences.append("shield broken")
        tail = (" — " + "; ".join(consequences)) if consequences else ""
        text = (f"{head} {hit}hits {target.log_name}: {breakdown}. "
                f"{old} → {tgt.cur_hp} Hit Points{msg}{tail}")
        fate = "Slain" if "Mortal" in msg else "Major Wound" if "Major" in msg else tgt.wound_state()
        table = blow_narrative(attacker=who, weapon=what, target=target.display_name, amount=b["wound"],
                               to_knight=False, fate=fate, critical=b["critical"], unarmed=unarmed,
                               knockdown=b["knockdown"])
        if b["shield_broken"]:
            table += f" {target.display_name}’s shield breaks!"
        title = f"{who + ' → ' if who else ''}{target.display_name}"
    else:
        text = table = f"{head} {hit}damage: {breakdown}"
        title = head
    data = {"cid": target.id if target else None, "delta": -b["wound"],
            "attacker": who, "weapon": what, "target": target.display_name if target else "",
            "blow": b, "breakdown": breakdown, "shield_broken": b["shield_broken"],
            "major": bool(target and "Major" in msg), "mortal": bool(target and "Mortal" in msg),
            "table_text": table, "narrative": table, **gextra}
    return state.record("combat.blow", text + suffix, title=title, data=data)


def _report_blow_on_knight(state, attacker, knight, weapon, expr, rolled, extra, body, unarmed=False):
    """An enemy's blow on a player knight: roll and report its damage (+4D6 on
    a critical, +2D6 bare-handed) and which protection applies. Nothing is
    applied — players keep their knights' Hit Points on paper."""
    b = resolve_blow(expr=expr, rolled=rolled, critical=bool(body.get("critical")), unarmed=unarmed,
                     reckless=bool(body.get("reckless")), extra=extra,
                     rebated=bool(body.get("rebated")))
    shield = bool(body.get("shield"))
    who = attacker.display_name if attacker else ""
    head = f"{who}’s {weapon or 'blow'}" if who else (weapon or "A blow")
    crit = "CRITICAL " if b["critical"] else ""
    protect = "armour + shield/parry apply" if shield else "armour only, no shield/parry"
    at_horse = bool(body.get("at_horse")) or bool(attacker is not None and attacker.attacks_horse and knight.mounted)   # the players' surprise
    text = f"{head} {crit}hits {knight.display_name}{chr(8217) + 's horse' if at_horse else ''} for {b['damage']} damage ({blow_breakdown(b).rsplit(' → ', 1)[0]}) — {protect}"
    story = blow_narrative(attacker=who, weapon=weapon, target=f"{knight.display_name}’s horse" if at_horse else knight.display_name,
                           amount=b["damage"],
                           to_knight=True, critical=b["critical"], unarmed=unarmed)
    return state.record("combat.blow", text, title=f"{who + ' → ' if who else ''}{knight.display_name}",
                        visibility="gm" if body.get("_gm_only") else "public",
                        data={"cid": knight.id, "delta": 0, "attacker": who, "weapon": weapon or "",
                              "target": knight.display_name, "blow": b, "to_knight": True, "at_horse": at_horse,
                              "knight_shield": shield, "breakdown": blow_breakdown(b),
                              "table_text": story, "narrative": story, "touches": [knight.party_id]})


# -- an enemy attacks a knight: Table 7.1 from the two results ----------------

@router.post("/api/combat/attack")
async def attack(request: Request, body: dict):
    """After an enemy's attack roll (``event`` = that roll's id), the GM gives
    the knight's result; Table 7.1 decides whether the enemy's blow lands (and
    with +4D6 / shield) — if so its damage is rolled and applied."""
    state, cs = _active(request)
    roll = next((e for e in state.session.events if e["id"] == body.get("event")), None)
    if not roll or roll["type"] != "roll.check" or "attack" not in roll["data"]:
        bad("Roll the enemy's attack first")
    foe = _combatant(cs, roll["data"]["cid"])
    knight = _combatant(cs, body.get("target"))
    if _is_foe(knight):
        bad("Choose a player knight")
    stance_ = roll["data"].get("stance", "attack")
    try:
        r = resolve_attack(roll["data"]["outcome"], body.get("knight"), stance_)
    except ValueError as exc:
        bad(str(exc))
    both = roll["data"]["outcome"] == "success"
    k_text = {"critical": "critical", "higher": "success (higher roll)" if both else "success",
              "equal": "success (equal roll)" if both else "success",
              "lower": "success (lower roll)" if both else "success",
              "failure": "failure", "fumble": "fumble"}[body["knight"]]
    fn, kn = foe.display_name, knight.display_name
    after = []                                   # follow-on events a defensive action causes
    if stance_ in ("attack", "trample"):
        verdict = {"foe": f"{fn} wins", "knight": f"{kn} wins", "tie": "tie — both strike", "none": "both miss"}[r["result"]]
        if stance_ == "trample" and r["result"] in ("foe", "tie"):
            verdict += f" — the horse tramples {kn}"
        if r["result"] in ("knight", "tie"):
            verdict += f"; {fn} gets {'armour + shield' if r['knight_shield'] else 'armour only'}"
    elif r.get("held"):                          # the defensive action worked: no damage either way
        verdict = {"defend": f"{fn} holds — no damage either way",
                   "evade": f"{fn} evades — no damage, and breaks away",
                   "dodge": f"{fn} dodges — no damage" + (", ready next round" if roll["data"]["outcome"] == "critical"
                                                              else ", but starts next round on the ground")}[stance_]
        if stance_ == "evade":
            after.append(("combat.engage", f"{fn} breaks away from {kn}", {"cid": foe.id, "with": "", "table_text": f"{fn} breaks away"}))
        if stance_ == "dodge" and roll["data"]["outcome"] != "critical":
            after.append(("combat.prone", f"{fn} is on the ground", {"cid": foe.id, "on": True, "table_text": f"{fn} is on the ground"}))
    elif r["result"] == "knight":
        verdict = f"{kn} wins — {fn} {'defends' if stance_ == 'defend' else stance_ + 's'} and fails"
        verdict += f"; {fn} gets {'armour + shield' if r['knight_shield'] else 'armour only'}"
        if stance_ == "dodge":
            verdict += "; starts next round on the ground"
            after.append(("combat.prone", f"{fn} is on the ground", {"cid": foe.id, "on": True, "table_text": f"{fn} is on the ground"}))
    else:
        verdict = "both miss"
    # what befalls the weapons (core.combat.action-mounted-charge, core.weapons.weapon-skills)
    prompt = None
    if stance_ in ("attack", "trample") and roll["data"].get("attack") is not None:
        atk = foe.attack_for(roll["data"]["attack"])
        fate = weapon_fate(atk, roll["data"]["outcome"], r["result"]) if stance_ == "attack" else None
        if fate in ("breaks", "breaks+t72"):
            how = "shatters on the charge" if is_charge(atk) else "breaks" + (" against the knight's sword" if r["result"] == "tie" and roll["data"]["outcome"] != "fumble" else "")
            verdict += f"; {fn}'s {atk['weapon'].lower()} {how}"
            after.append(("combat.break", f"{fn}'s {atk['weapon']} {how}", {"cid": foe.id, "key": roll["data"]["attack"], "table_text": f"{fn}'s {atk['weapon'].lower()} {how}!", "touches": [knight.party_id]}))
            if fate == "breaks+t72":
                after.append(("__t72__", "", {}))
        elif fate == "dropped":
            verdict += f"; {fn} drops their {atk['weapon'].lower()}"
            if foe.wielding != "brawl":
                after.append(("combat.wield", f"{fn} drops their {atk['weapon']} — fights on with Brawling", {"cids": [foe.id], "wield": "brawl", "table_text": f"{fn} drops their weapon"}))
    if getattr(knight, "lance", False) and stance_ == "attack":
        k_fate = None
        if body["knight"] == "fumble":
            k_fate = "breaks+t72"
        elif body["knight"] == "equal" or (body["knight"] == "lower" and roll["data"]["outcome"] in ("critical", "success")):
            k_fate = "breaks"
        if k_fate:
            verdict += f"; {kn}'s lance shatters" + (" — roll Horsemanship on Table 7.2" if k_fate == "breaks+t72" else "")
            after.append(("combat.lance", f"{kn}'s lance shatters on the charge!" + (" Roll Horsemanship (Table 7.2)." if k_fate == "breaks+t72" else ""),
                          {"cid": knight.id, "on": False, "broken": True, "table_text": f"{kn}'s lance shatters!", "touches": [knight.party_id]}))
            if k_fate == "breaks+t72":
                prompt = {"kind": "table72", "name": kn}
        if roll["data"]["outcome"] == "critical" and body["knight"] == "critical" and is_charge(foe.attack_for(roll["data"]["attack"])):
            verdict += "; both critical — the horses crash, each takes the other's Charge Damage"
    for who in r["fumbled"]:
        if who == "knight":
            if not getattr(knight, "lance", False):
                verdict += f"; {kn} drops or breaks their weapon"
        elif stance_ == "attack":
            pass                                   # said above, weapon by weapon
        elif stance_ == "dodge":                 # falls, weapon dropped
            verdict += f"; {fn} falls and drops their weapon"
            if not any(e[0] == "combat.prone" for e in after):
                after.append(("combat.prone", f"{fn} falls", {"cid": foe.id, "on": True, "table_text": f"{fn} falls"}))
            if foe.wielding != "brawl":
                after.append(("combat.wield", f"{fn} drops their weapon — fights on with Brawling",
                              {"cids": [foe.id], "wield": "brawl", "table_text": f"{fn} drops their weapon"}))
        elif stance_ == "evade":                 # falls; from the saddle, 1D6
            if foe.mounted:
                dmg = roll_expr("1D6")
                verdict += f"; {fn} falls from the horse ({dmg} damage)"
                after.append(("combat.prone", f"{fn} is thrown from the saddle — prone", {"cid": foe.id, "on": True, "table_text": f"{fn} is thrown from the saddle"}))
                after.append(("combat.hp", f"{fn} takes {dmg} from the fall", {"cid": foe.id, "delta": -dmg, "table_text": f"{fn} is hurt in the fall"}))
            else:
                verdict += f"; {fn} falls"
                after.append(("combat.prone", f"{fn} falls", {"cid": foe.id, "on": True, "table_text": f"{fn} falls"}))
    ev = state.record("combat.attack",
                      f"{fn} {roll['data']['outcome']} vs {kn} {k_text} → {verdict}",
                      title=f"{fn} vs {kn}",
                      data={"verdict": verdict, "result": r["result"], "knight_shield": r["knight_shield"], "stance": stance_,
                            "touches": [knight.party_id]})
    for etype, text, data in after:
        if etype == "__t72__":
            _table_72(state, foe, roll_expr)
            continue
        state.record(etype, text, title=kn if etype == "combat.lance" else fn, data=data)
    blow_ev = None
    if r["foe_strike"]:
        strike = {"attacker": foe.id, "target": knight.id, **r["foe_strike"]}
        if stance_ == "trample":
            strike.update(weapon="Trample — the horse", expr=HORSE_DAMAGE)
        else:
            strike["attack"] = roll["data"]["attack"]
        blow_ev = record_blow(state, state.combat_state(), strike)
    return {"event": ev, "blow": blow_ev, "result": r["result"], "knight_shield": r["knight_shield"], "held": bool(r.get("held")), "prompt": prompt}

