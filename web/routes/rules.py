"""Rules lookup over the corpus index; a rule can be shown on the Table, and
pinned for quick access (pins persist in data/pinned_rules.json)."""

import json
import os

from fastapi import APIRouter, Request

from web.routes.common import bad, st

router = APIRouter()


def _pins_path(state):
    return os.path.join(state.data_dir, "pinned_rules.json")


def _read_pins(state):
    try:
        with open(_pins_path(state), encoding="utf-8") as fh:
            return [p for p in json.load(fh) if isinstance(p, str)]
    except (OSError, ValueError):
        return []


@router.get("/api/rules/pins")
def pins(request: Request):
    state = st(request)
    rules = [state.rules_index.get(i) for i in _read_pins(state)]
    return {"pins": [{k: r[k] for k in ("id", "title", "book", "chapter", "pages")} for r in rules if r]}


@router.post("/api/rules/{rule_id}/pin")
async def pin(request: Request, rule_id: str, body: dict):
    state = st(request)
    if state.rules_index.get(rule_id) is None:
        bad("No such rule", 404)
    ids = [i for i in _read_pins(state) if i != rule_id]
    if body.get("pinned", True):
        ids.append(rule_id)
    with open(_pins_path(state), "w", encoding="utf-8") as fh:
        json.dump(ids, fh, indent=1)
    return {"pinned": rule_id in ids}


@router.get("/api/rules/shown")
def shown(request: Request):
    """The rule on the Table right now (title and id), or null."""
    from web.sessions import flags
    from web.table import shown_rule
    state = st(request)
    r = shown_rule(state.session.events, flags(state.session.events))
    return {"shown": {k: r[k] for k in ("rule_id", "title", "book", "pages")} if r else None}


@router.post("/api/rules/hide")
async def hide(request: Request):
    """Take the rule off the Table: the group has read it, play goes on."""
    from web.sessions import flags
    from web.table import shown_rule
    state = st(request)
    r = shown_rule(state.session.events, flags(state.session.events))
    if r is None:
        bad("No rule is on the Table", 409)
    ev = state.record("rule.hidden", f"Rule taken off the Table: {r['title']}", title=r["title"], visibility="gm",
                      data={"rule_id": r["rule_id"]})
    return {"event": ev}


@router.get("/api/rules")
def search(request: Request, q: str = "", limit: int = 30):
    return {"results": st(request).rules_index.search(q, limit)}


@router.get("/api/rules/{rule_id}")
def get_rule(request: Request, rule_id: str):
    r = st(request).rules_index.get(rule_id)
    if r is None:
        bad("No such rule", 404)
    return {"rule": r}


@router.post("/api/rules/{rule_id}/show")
async def show(request: Request, rule_id: str):
    state = st(request)
    r = state.rules_index.get(rule_id)
    if r is None:
        bad("No such rule", 404)
    pages = ", ".join(map(str, r["pages"]))
    ev = state.record("rule.shown", f"Rule: {r['title']} ({r['book']} p.{pages})",
                      title=r["title"],
                      data={"rule_id": rule_id, "title": r["title"], "html": r["html"],
                            "pages": r["pages"], "book": r["book"]})
    return {"event": ev}
