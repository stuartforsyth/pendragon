"""The spotlight: the GM clicks a card and it is blown up over the Table so everyone reads it together.
Like a rule on the Table it is an overlay, not a Fray entry. The event stores only the card's name; the
Table's payload resolves what players may read (web.battle_state.table_card)."""

from fastapi import APIRouter, Request

from web import table
from web.routes.common import bad, st
from web.sessions import flags

router = APIRouter()


def _shown(state):
    return table.shown_spotlight(state.session.events, flags(state.session.events))


@router.get("/api/spotlight")
def spotlight_now(request: Request):
    sp = _shown(st(request))
    return {"spotlight": {"kind": sp["kind"], "name": sp["name"]} if sp else None}


@router.post("/api/spotlight")
async def spotlight(request: Request, body: dict):
    state = st(request)
    if body.get("kind", "card") != "card":
        bad("Only cards can be put on the Table so far")
    name = body.get("name") or ""
    if name not in state.combat_data.get("encounters", {}):
        bad("No such card", 404)
    ev = state.record("table.spotlight", f"On the Table: {name}", title=name, data={"kind": "card", "name": name})
    return {"event": ev}


@router.post("/api/spotlight/off")
async def spotlight_off(request: Request):
    state = st(request)
    if not _shown(state):
        bad("Nothing is spotlit", 409)
    ev = state.record("table.spotlight_off", "Card removed from the Table", visibility="gm", data={})
    return {"event": ev}
