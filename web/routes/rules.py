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
