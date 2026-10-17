"""The Feedback tab: send a report with where it came from; list recent ones
(with what became of them) for the panel. See web/feedback.py."""

from fastapi import APIRouter, Request

from web import feedback as FB
from web.routes.common import bad, st

router = APIRouter()


@router.post("/api/feedback")
async def send(request: Request, body: dict):
    try:
        item = FB.submit(st(request), body, request.headers.get("user-agent", ""))
    except ValueError as exc:
        bad(str(exc))
    return {"item": item}


@router.get("/api/feedback")
def recent(request: Request, limit: int = 8):
    items = FB.load(st(request).data_dir)
    return {"items": list(reversed(items))[:max(1, min(limit, 200))]}
