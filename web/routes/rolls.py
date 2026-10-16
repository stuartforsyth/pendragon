"""The GM dice tray and every click-to-roll: one engine (core.dice), one way of
logging. Combat rolls reuse these builders so they read the same in the log."""

from fastapi import APIRouter, Request

from core.dice import (NotationError, notation_breakdown, resolve_characteristic,
                       resolve_opposed, resolve_skill, roll_damage, roll_notation,
                       skill_display)
from web.routes.common import bad, st, to_int

router = APIRouter()


def _shown(value, modifier, characteristic):
    disp = str if characteristic else skill_display
    if not modifier:
        return disp(value)
    return f"{disp(value)} {modifier:+d} = {disp(value + modifier)}"


def record_check(state, *, label, value, kind="skill", actor="", modifier=0,
                 masked=False, show_label=False, extra=None):
    """Roll d20 against a value (with an optional situational modifier) and log it."""
    characteristic = kind == "characteristic"
    eff = value + modifier
    roll, outcome = (resolve_characteristic(eff) if characteristic
                     else resolve_skill(eff))
    shown = _shown(value, modifier, characteristic)
    who = f"{actor} rolls " if actor else ""
    text = f"{who}{label} ({shown}): {roll} — {outcome.upper()}"
    title = f"{actor} — {label}" if actor else label
    data = {"label": label, "value": value, "modifier": modifier, "effective": eff,
            "shown": shown, "roll": roll, "outcome": outcome, "kind": kind,
            "actor": actor, "show_label": show_label, **(extra or {})}
    return state.record("roll.check", text, title=title, data=data, masked=masked)


def record_damage(state, *, label, expr, critical=False, rebated=False, actor="",
                  masked=False, show_label=False, extra=None):
    try:
        total, breakdown = roll_damage(expr, critical=critical, rebated=rebated)
    except (TypeError, ValueError):
        bad(f"Can't roll damage '{expr}'")
    who = f"{actor} " if actor else ""
    text = f"{who}{label} damage: {breakdown}"
    data = {"label": label, "expr": expr, "total": total, "breakdown": breakdown,
            "critical": critical, "rebated": rebated, "actor": actor,
            "show_label": show_label, **(extra or {})}
    title = f"{actor} — {label}" if actor else label
    return state.record("roll.damage", text, title=title, data=data, masked=masked)


@router.post("/api/roll/dice")
async def roll_dice(request: Request, body: dict):
    try:
        result = roll_notation(body.get("expr", ""))
    except NotationError as exc:
        bad(str(exc))
    label = (body.get("label") or "").strip()
    text = f"{label + ': ' if label else ''}{notation_breakdown(result)}"
    ev = st(request).record(
        "roll.dice", text, title=label or result["expr"],
        data={**result, "label": label, "show_label": bool(body.get("show_label"))},
        masked=bool(body.get("masked")))
    return {"event": ev}


@router.post("/api/roll/check")
async def roll_check(request: Request, body: dict):
    label = (body.get("label") or "").strip() or "Check"
    kind = body.get("kind") or "skill"
    if kind not in ("skill", "trait", "passion", "characteristic"):
        bad("Unknown roll kind")
    ev = record_check(st(request), label=label, value=to_int(body.get("value")),
                      kind=kind, actor=(body.get("actor") or "").strip(),
                      modifier=to_int(body.get("modifier") or 0, "modifier"),
                      masked=bool(body.get("masked")),
                      show_label=bool(body.get("show_label")))
    return {"event": ev}


@router.post("/api/roll/opposed")
async def roll_opposed(request: Request, body: dict):
    a, b = body.get("a") or {}, body.get("b") or {}
    a_label = (a.get("label") or "").strip() or "Side A"
    b_label = (b.get("label") or "").strip() or "Side B"
    r = resolve_opposed(to_int(a.get("value"), "A's value"), to_int(b.get("value"), "B's value"))
    r["a"]["label"], r["b"]["label"] = a_label, b_label
    if r["winner"]:
        w = r[r["winner"]]
        verdict = f"{w['label']} wins"
    else:
        verdict = r["a"]["result"].upper()
    text = (f"Opposed — {a_label} ({skill_display(r['a']['value'])}): {r['a']['roll']} "
            f"{r['a']['outcome']} vs {b_label} ({skill_display(r['b']['value'])}): "
            f"{r['b']['roll']} {r['b']['outcome']} → {verdict}")
    ev = st(request).record(
        "roll.opposed", text, title=f"{a_label} vs {b_label}",
        data={**r, "verdict": verdict, "label": f"{a_label} vs {b_label}",
              "show_label": bool(body.get("show_label"))},
        masked=bool(body.get("masked")))
    return {"event": ev}


@router.post("/api/roll/damage")
async def damage(request: Request, body: dict):
    expr = (body.get("expr") or "").strip()
    if not expr:
        bad("Enter a damage expression, e.g. 4d6")
    ev = record_damage(st(request), label=(body.get("label") or "").strip() or "Damage",
                       expr=expr, critical=bool(body.get("critical")),
                       rebated=bool(body.get("rebated")),
                       actor=(body.get("actor") or "").strip(),
                       masked=bool(body.get("masked")),
                       show_label=bool(body.get("show_label")))
    return {"event": ev}
