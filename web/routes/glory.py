"""Glory awarded by hand — an Opportunity's reward, a deed, a correction.

Defeated foes' Glory is worked out automatically (web.combat_state); this is
for everything else. An award made during a fight also counts in that fight's
tally; it is always logged."""

from fastapi import APIRouter, Request

from web.routes.common import bad, st, to_int

router = APIRouter()


@router.post("/api/glory")
async def award(request: Request, body: dict):
    state = st(request)
    pid = body.get("knight")
    member = state.party.get(pid or "")
    if member is None:
        bad("Choose a knight")
    amount = to_int(body.get("amount"), "amount")
    if not amount:
        bad("Enter the Glory to award")
    reason = (body.get("reason") or "").strip()
    if not reason:
        bad("Say what the Glory is for")
    cs = state.combat_state()
    fight = cs["started_event"] if cs and cs.get("active") else None
    name = member["name"]
    line = f"{amount:+d} Glory · {name} — {reason}"
    ev = state.record("glory.awarded", line, title="Glory",
                      data={"knight": pid, "knight_name": name, "amount": amount, "reason": reason,
                            "fight": fight, "battle": None, "source": "manual",
                            "table_text": line, "touches": [pid], "glory_amount": amount})
    return {"event": ev}
