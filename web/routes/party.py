"""The Party: lightweight tracking records for the player knights. They join
combats automatically and their size scales encounters."""

from fastapi import APIRouter, Request

from web.routes.common import bad, st, to_int

router = APIRouter()

INT_FIELDS = ("max_hp", "cur_hp", "major_wound", "unconscious", "knockdown",
              "armour", "shield", "move")
TEXT_FIELDS = ("name", "player", "armour_desc", "notes")


def _clean(body, partial=False):
    out = {}
    for k in TEXT_FIELDS:
        if k in body:
            out[k] = str(body[k] or "").strip()
    for k in INT_FIELDS:
        if k in body:
            v = body[k]
            out[k] = None if v in (None, "") else to_int(v, k)
    if "active" in body:
        out["active"] = bool(body["active"])
    if "values" in body:
        vals = body["values"] or {}
        out["values"] = {str(n).strip(): to_int(v, n) for n, v in vals.items() if str(n).strip()}
    if not partial:
        if not out.get("name"):
            bad("A knight needs a name")
        out.setdefault("active", True)
        if out.get("cur_hp") is None:
            out["cur_hp"] = out.get("max_hp")
    return out


@router.get("/api/party")
def list_party(request: Request):
    return {"party": st(request).party.items}


@router.post("/api/party")
async def add(request: Request, body: dict):
    return {"member": st(request).party.add(_clean(body))}


@router.patch("/api/party/{member_id}")
async def update(request: Request, member_id: str, body: dict):
    try:
        return {"member": st(request).party.update(member_id, _clean(body, partial=True))}
    except KeyError:
        bad("No such knight", 404)


@router.delete("/api/party/{member_id}")
async def remove(request: Request, member_id: str):
    try:
        return {"member": st(request).party.remove(member_id)}
    except KeyError:
        bad("No such knight", 404)


@router.post("/api/party/{member_id}/hp")
async def hp(request: Request, member_id: str, body: dict):
    """Out-of-combat HP change (healing, a fall…) — logged to the session."""
    state = st(request)
    m = state.party.get(member_id)
    if m is None:
        bad("No such knight", 404)
    delta = to_int(body.get("delta"), "delta")
    old = m.get("cur_hp") if m.get("cur_hp") is not None else (m.get("max_hp") or 0)
    new = min(old + delta, m.get("max_hp") or old + delta)
    state.party.update(member_id, {"cur_hp": new})
    reason = (body.get("reason") or "").strip()
    why = f" ({reason})" if reason else ""
    ev = state.record("party.hp", f"{m['name']}: {old} → {new} Hit Points ({delta:+d}){why}",
                      title=m["name"], data={"member": member_id, "delta": delta})
    return {"member": state.party.get(member_id), "event": ev}
