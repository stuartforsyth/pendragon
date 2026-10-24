"""The Party: the player knights by name (players keep their own sheets —
no Hit Points here). Active knights join combats as opponents to choose and
set encounter scaling; optional key values are click-to-roll."""

from fastapi import APIRouter, Request

from web.routes.common import bad, st

router = APIRouter()

TEXT_FIELDS = ("name", "player", "notes")


def _clean(body, partial=False):
    out = {}
    for k in TEXT_FIELDS:
        if k in body:
            out[k] = str(body[k] or "").strip()
    if "active" in body:
        out["active"] = bool(body["active"])
    if not partial:
        if not out.get("name"):
            bad("A knight needs a name")
        out.setdefault("active", True)
    return out


@router.get("/api/party")
def list_party(request: Request):
    state = st(request)
    away = state.away_ids()
    return {"party": [{**m, "away": m["id"] in away} for m in state.party.items]}


@router.post("/api/party/{member_id}/away")
async def set_away(request: Request, member_id: str, body: dict):
    """Away for this session only: an event, so a new session starts with everyone back."""
    state = st(request)
    m = state.party.get(member_id)
    if not m:
        bad("No such knight", 404)
    away = bool(body.get("away", True))
    line = f"{m['name']} is away tonight" if away else f"{m['name']} is back"
    state.record("party.away", line, visibility="gm", data={"pid": member_id, "away": away})
    return {"member": {**m, "away": away}}


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
