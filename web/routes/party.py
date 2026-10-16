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
