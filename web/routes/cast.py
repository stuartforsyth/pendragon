"""The Cast: NPCs kept across sessions, with private GM notes. Replaces the
desktop app's per-session roster (old roster JSON files can be imported)."""

import datetime

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response

from core.npc import format_roster_markdown
from web.routes.common import bad, st
from web.routes.npc import _public, decorate

router = APIRouter()


def _entry(npc, notes=""):
    npc = decorate(dict(npc))
    npc.pop("notes", None)
    return {"npc": npc, "notes": notes or "",
            "kept": datetime.datetime.now().isoformat(timespec="seconds")}


@router.get("/api/cast")
def list_cast(request: Request):
    return {"cast": st(request).cast.items}


@router.post("/api/cast")
async def keep(request: Request, body: dict):
    npc = body.get("npc")
    if not npc or not npc.get("full"):
        bad("No NPC to keep")
    cast = st(request).cast
    existing = next((c for c in cast.items if c["npc"].get("uid") == npc.get("uid")), None)
    if existing:
        return {"entry": cast.update(existing["id"], {"npc": _entry(npc)["npc"]})}
    return {"entry": cast.add(_entry(npc, body.get("notes", "")))}


@router.patch("/api/cast/{entry_id}")
async def update(request: Request, entry_id: str, body: dict):
    fields = {}
    if "notes" in body:
        fields["notes"] = str(body["notes"])
    if "npc" in body and body["npc"]:
        fields["npc"] = _entry(body["npc"])["npc"]
    try:
        return {"entry": st(request).cast.update(entry_id, fields)}
    except KeyError:
        bad("No such cast member", 404)


@router.delete("/api/cast/{entry_id}")
async def remove(request: Request, entry_id: str):
    try:
        return {"entry": st(request).cast.remove(entry_id)}
    except KeyError:
        bad("No such cast member", 404)


@router.post("/api/cast/{entry_id}/present")
async def present(request: Request, entry_id: str):
    state = st(request)
    entry = state.cast.get(entry_id)
    if entry is None:
        bad("No such cast member", 404)
    npc = entry["npc"]
    ev = state.record("npc.presented", f"Presented to the table: {npc['full']}",
                      title=npc["full"], data={"npc": _public(npc), "cast_id": entry_id})
    return {"event": ev}


@router.post("/api/cast/import")
async def import_roster(request: Request, body: list = Body(...)):
    """Import a desktop-app roster file (a JSON list of NPC dicts with notes)."""
    if not isinstance(body, list) or not all(isinstance(n, dict) and n.get("full") for n in body):
        bad("That isn't a saved roster")
    cast = st(request).cast
    added = [cast.add(_entry(n, n.get("notes", ""))) for n in body]
    return {"added": len(added)}


@router.get("/api/cast/export.md")
def export_md(request: Request):
    roster = [{**c["npc"], "notes": c.get("notes", "")} for c in st(request).cast.items]
    return Response(format_roster_markdown(roster), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="pendragon-cast.md"'})
