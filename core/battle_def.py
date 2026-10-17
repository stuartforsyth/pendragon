"""Saved battle definitions: battle → days → turn scripts.

A definition is a template the GM prepares (or a quick battle made on the
spot). Launching a battle copies the whole definition into the session's
``battle.started`` event, so later edits to the template never change a battle
already fought. Only the Size is required; everything else has a default.
"""

import copy

from core.battle import OUTCOMES, SIZES

_SIDES = ("friendly", "enemy")


def blank_day(size="clash"):
    return {"intensity": {"mode": "roll"}, "turns": SIZES[size]["turns"],
            "first_charge": True, "no_charge": False,
            "commanders": {"friendly": None, "enemy": None},
            "deck": {"foes": [], "opportunities": []}, "notes": "", "scripts": []}


def blank_battle(size="clash"):
    size = size if size in SIZES else "clash"
    return {"source": "user", "name": "", "size": size, "where": "", "against": "", "notes": "",
            "outcome": None, "commander": None,
            "army_commanders": {"friendly": {"name": "", "battle": None},
                                "enemy": {"name": "", "battle": None}},
            "days": [blank_day(size)]}


def quick_battle(size, days=1, name="", where="", against="", notes=""):
    """A battle launched on the fly: Size (and days) are all it needs."""
    if size not in SIZES:
        raise ValueError("Choose a battle size")
    days = int(days or 1)
    if not 1 <= days <= 7:
        raise ValueError("A quick battle lasts 1 to 7 days")
    b = blank_battle(size)
    label = SIZES[size]["label"]
    b.update(name=(name or "").strip() or f"A {label}",
             where=(where or "").strip(), against=(against or "").strip(), notes=(notes or "").strip(), source="quick")
    b["days"] = [blank_day(size) for _ in range(days)]
    return b


def _int(v, name, lo=None, hi=None):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number") from None
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ValueError(f"{name} must be {lo}–{hi}" if hi is not None else f"{name} must be at least {lo}")
    return n


def _deck(d, known, warnings, where):
    d = d or {}
    out = {"foes": [str(k) for k in d.get("foes", []) if str(k).strip()],
           "opportunities": [str(k) for k in d.get("opportunities", []) if str(k).strip()]}
    for k in out["foes"] + out["opportunities"]:
        if known is not None and k not in known:
            warnings.append(f"{where}: '{k}' isn't in your encounters")
    return out


def clean_day(day, size, known=None, warnings=None, label="Day"):
    warnings = [] if warnings is None else warnings
    base = blank_day(size)
    day = day or {}
    out = copy.deepcopy(base)
    inten = day.get("intensity") or {"mode": "roll"}
    if inten.get("mode") == "fixed":
        out["intensity"] = {"mode": "fixed", "value": _int(inten.get("value"), f"{label} Intensity", 1, 40)}
    else:
        out["intensity"] = {"mode": "roll"}
    out["turns"] = _int(day.get("turns", base["turns"]), f"{label} turns", 1)
    # Mounted or on foot is the group's state, set at Mustering — not the template's.
    for k in ("first_charge", "no_charge"):
        out[k] = bool(day.get(k, base[k]))
    cmd = day.get("commanders") or {}
    for side in _SIDES:
        o = cmd.get(side)
        if o not in (None, "") and o not in OUTCOMES:
            raise ValueError(f"{label}: unknown commander outcome '{o}'")
        out["commanders"][side] = o or None
    out["deck"] = _deck(day.get("deck"), known, warnings, label)
    out["notes"] = str(day.get("notes") or "").strip()
    scripts = []
    for i, sc in enumerate(day.get("scripts") or [], 1):
        text = str(sc.get("text") or "").strip()
        if not text:
            raise ValueError(f"{label}, script {i}: write what happens")
        scripts.append({"turn": _int(sc.get("turn", 1), f"{label}, script {i} turn", 1), "text": text,
                        "if_intensity": bool(sc.get("if_intensity")),
                        "deck": _deck(sc["deck"], known, warnings, f"{label}, script {i}") if sc.get("deck") else None})
    out["scripts"] = scripts
    return out


def clean_battle(d, encounters=None):
    """Validate a definition; returns (clean, warnings). Raises ValueError."""
    d = d or {}
    size = d.get("size")
    if size not in SIZES:
        raise ValueError("Choose a battle size")
    known = set(encounters) if encounters is not None else None
    warnings = []
    out = blank_battle(size)
    for k in ("name", "where", "against", "notes"):
        out[k] = str(d.get(k) or "").strip()
    out["source"] = d.get("source") or "user"
    oc = d.get("outcome")
    if oc not in (None, ""):
        if size in ("fight", "skirmish", "clash"):
            raise ValueError("A preset outcome is only for Small battles and larger")
        from core.battle import OUTCOME_LABEL
        if oc not in OUTCOME_LABEL:
            raise ValueError("Unknown preset outcome")
        out["outcome"] = oc
    # The template is the scenario, the same for any group: who commands the
    # conroi is chosen when the battle is launched (Mustering), never stored here.
    out["commander"] = None
    ac = d.get("army_commanders") or {}
    for side in _SIDES:
        s = ac.get(side) or {}
        battle = s.get("battle")
        out["army_commanders"][side] = {"name": str(s.get("name") or "").strip(),
                                        "battle": None if battle in (None, "") else _int(battle, "Battle skill", 1, 40)}
    days = d.get("days") or []
    if not days:
        raise ValueError("A battle needs at least one day")
    out["days"] = [clean_day(day, size, known, warnings, f"Day {i}") for i, day in enumerate(days, 1)]
    return out, warnings
