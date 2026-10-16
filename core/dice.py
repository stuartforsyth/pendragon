"""Dice and roll resolution — the one roll engine every part of the app uses.

Rules sources (rules corpus):
- ``core.game-system.resolution`` — unopposed (critical / success / failure /
  fumble), opposed (win / partial / loss / tie / mutual failure), and
  characteristics being pass/fail only.
- ``core.game-system.critical-bonus`` — values over 20 are ``20 (+x)``; x is
  added to the roll, widening the critical range; 20+ can never fail or fumble;
  all criticals are equal (count as 20).
- Core Ch.7 Table 7.1 — a critical hit adds a flat +4D6 damage.

Every resolver accepts an optional pre-rolled die so tests are deterministic.
"""

import random
import re

from core.rules import roll_expr  # noqa: F401  (re-exported for callers)

CRITICAL_BONUS = "4D6"

OUTCOMES = ("critical", "success", "failure", "fumble")


def d20():
    return random.randint(1, 20)


def skill_display(value):
    """Pendragon notation for a skill/trait value: '20 (+2)' once it exceeds 20."""
    return f"20 (+{value - 20})" if value > 20 else str(value)


def resolve_skill(value, roll=None):
    """Roll d20 against a Skill/Trait/Passion value. Returns ``(roll, outcome)``.

    At or below 20: exact roll = critical, natural 20 = fumble, roll-under
    succeeds. Above 20 the critical bonus applies: never fails, criticals on any
    natural roll >= 20 - x.
    """
    roll = d20() if roll is None else roll
    if value >= 20:
        crit_floor = 20 - (value - 20)   # 20 -> 20; 22 -> 18; 25 -> 15
        return roll, ("critical" if roll >= crit_floor else "success")
    if roll == 20:
        return roll, "fumble"
    if roll == value:
        return roll, "critical"
    if roll < value:
        return roll, "success"
    return roll, "failure"


def resolve_characteristic(value, roll=None):
    """Characteristic roll: pass/fail only — no critical or fumble."""
    roll = d20() if roll is None else roll
    return roll, ("success" if roll <= value else "failure")


def roll_damage(damage_expr, critical=False, rebated=False):
    """Roll weapon damage. Returns ``(total, breakdown)``.

    ``critical`` adds a flat +4D6; ``rebated`` halves the result, rounded up.
    A rebated critical adds the +4D6 first, then halves.
    """
    base = roll_expr(damage_expr)
    total = base
    breakdown = f"{damage_expr} = {base}"
    if critical:
        bonus = roll_expr(CRITICAL_BONUS)
        total += bonus
        breakdown += f"  +critical {CRITICAL_BONUS} = {bonus}"
    if rebated:
        if critical:
            breakdown += f"  =  {total}"
        total = (total + 1) // 2
        breakdown += f"  rebated ½  ->  {total}"
    elif critical:
        breakdown += f"  ->  {total}"
    return total, breakdown


# ---------------------------------------------------------------------------
# Opposed resolution
# ---------------------------------------------------------------------------

def _size(value, roll, outcome):
    """How big a successful roll is for comparison. All criticals count as 20;
    a critical bonus is added to the roll."""
    if outcome == "critical":
        return 20
    return roll + max(0, value - 20)


def resolve_opposed(a_value, b_value, a_roll=None, b_roll=None):
    """Opposed roll between two Statistic values.

    Returns a dict with each side's ``roll``/``outcome`` (unopposed outcome)
    and ``result`` — one of win / partial / loss / tie / mutual failure — plus
    a one-line ``summary`` naming the winner side ("a", "b" or None).
    """
    a_roll, a_out = resolve_skill(a_value, a_roll)
    b_roll, b_out = resolve_skill(b_value, b_roll)
    a_ok = a_out in ("critical", "success")
    b_ok = b_out in ("critical", "success")

    if not a_ok and not b_ok:
        a_res = b_res = "mutual failure"
        winner = None
    elif a_ok and not b_ok:
        a_res, b_res, winner = "win", "loss", "a"
    elif b_ok and not a_ok:
        a_res, b_res, winner = "loss", "win", "b"
    else:
        a_size = _size(a_value, a_roll, a_out)
        b_size = _size(b_value, b_roll, b_out)
        if a_out == "critical" and b_out != "critical":
            a_res, b_res, winner = "win", "partial", "a"
        elif b_out == "critical" and a_out != "critical":
            a_res, b_res, winner = "partial", "win", "b"
        elif a_size == b_size:
            a_res = b_res = "tie"
            winner = None
        elif a_size > b_size:
            a_res, b_res, winner = "win", "partial", "a"
        else:
            a_res, b_res, winner = "partial", "win", "b"

    return {
        "a": {"value": a_value, "roll": a_roll, "outcome": a_out, "result": a_res},
        "b": {"value": b_value, "roll": b_roll, "outcome": b_out, "result": b_res},
        "winner": winner,
    }


# ---------------------------------------------------------------------------
# Free dice notation (the GM dice tray)
# ---------------------------------------------------------------------------

_TERM = re.compile(r"([+-])?\s*(?:(\d*)\s*[dD]\s*(\d+)|(\d+))")
MAX_DICE = 100
MAX_SIDES = 1000


class NotationError(ValueError):
    pass


def roll_notation(expr):
    """Roll free dice notation such as ``d20``, ``3d6+2``, ``2D6+3-1d4``.

    Returns ``{"expr", "terms": [{"sign", "count", "sides", "rolls", "subtotal"}
    or {"sign", "constant"}], "total"}``. Raises ``NotationError`` on anything
    that is not dice notation.
    """
    if re.search(r"[\dDd]\s+\d", expr or ""):
        raise NotationError(f"Missing + or - in '{expr}'")
    text = (expr or "").replace(" ", "")
    if not text:
        raise NotationError("Enter some dice, e.g. 3d6+2")
    pos, terms, total = 0, [], 0
    while pos < len(text):
        m = _TERM.match(text, pos)
        if not m or m.end() == pos:
            raise NotationError(f"Can't read '{expr}' as dice (try 2d6+3)")
        if terms and not m.group(1):
            raise NotationError(f"Missing + or - in '{expr}'")
        sign = -1 if m.group(1) == "-" else 1
        if m.group(3):
            count = int(m.group(2) or 1)
            sides = int(m.group(3))
            if not (1 <= count <= MAX_DICE and 2 <= sides <= MAX_SIDES):
                raise NotationError(f"Unreasonable dice in '{expr}'")
            rolls = [random.randint(1, sides) for _ in range(count)]
            sub = sign * sum(rolls)
            terms.append({"sign": sign, "count": count, "sides": sides,
                          "rolls": rolls, "subtotal": sub})
        else:
            sub = sign * int(m.group(4))
            terms.append({"sign": sign, "constant": int(m.group(4)), "subtotal": sub})
        total += sub
        pos = m.end()
    return {"expr": text.upper().replace("D", "d"), "terms": terms, "total": total}


def notation_breakdown(result):
    """'3d6 [4, 2, 6] + 2 = 14' — a readable trail for the log."""
    parts = []
    for i, t in enumerate(result["terms"]):
        op = ("- " if t["sign"] < 0 else "+ ") if i else ("-" if t["sign"] < 0 else "")
        if "constant" in t:
            parts.append(f"{op}{t['constant']}")
        else:
            parts.append(f"{op}{t['count']}d{t['sides']} [{', '.join(map(str, t['rolls']))}]")
    return f"{' '.join(parts)} = {result['total']}"
