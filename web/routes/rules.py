"""Rules lookup over the corpus index; a rule can be shown on the Table."""

from fastapi import APIRouter, Request

from web.routes.common import bad, st

router = APIRouter()


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
