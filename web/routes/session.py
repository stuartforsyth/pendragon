"""Sessions, the event log, live updates, narration/notes, the Table feed, and
Chronicle export."""

import html
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse

from web import combat_state
from web.routes.common import bad, st
from web.rules_index import render_markdown
from web.sessions import META_TYPES, flags

router = APIRouter()


def _projected(session):
    """Events with their derived struck/revealed flags, for the GM console."""
    fl = flags(session.events)
    out = []
    for ev in session.events:
        f = fl.get(ev["id"], {})
        out.append({**ev, "struck": f.get("struck", False),
                    "revealed": f.get("revealed", False)})
    return out


# -- session lifecycle -----------------------------------------------------

@router.get("/api/session")
def get_session(request: Request):
    s = st(request).session
    return {"session": s.meta(), "events": _projected(s),
            "suggested_title": st(request).sessions.suggest_title()}


@router.get("/api/session/events")
def events_after(request: Request, after: int = 0):
    s = st(request).session
    return {"session": s.meta(), "events": [e for e in _projected(s) if e["id"] > after]}


@router.get("/api/sessions")
def list_sessions(request: Request):
    return {"sessions": st(request).sessions.list(), "active": st(request).session.id}


@router.post("/api/session/start")
async def start_session(request: Request, body: dict):
    state = st(request)
    if not state.session.scratch:
        state.end_session()
    s = state.sessions.start(body.get("title", ""))
    state.notify("session")
    return {"session": s.meta()}


@router.post("/api/session/end")
async def end_session(request: Request):
    state = st(request)
    s = state.end_session()
    state.notify("session")
    return {"session": s.meta()}


@router.post("/api/session/resume")
async def resume_session(request: Request, body: dict):
    state = st(request)
    if not state.session.scratch and state.session.id != body.get("id"):
        state.end_session()
    try:
        s = state.sessions.resume(body.get("id", ""))
    except (KeyError, OSError):
        bad("No such session", 404)
    state.notify("session")
    return {"session": s.meta()}


@router.delete("/api/sessions/{sid}")
async def delete_session(request: Request, sid: str):
    """Bin a saved session (test runs, false starts). It goes to
    ``sessions/.trash/``, not oblivion; the session in progress can't be binned."""
    state = st(request)
    try:
        state.sessions.delete(sid)
    except (KeyError, OSError):
        bad("No such session", 404)
    except ValueError as exc:
        bad(str(exc), 409)
    state.notify("session")
    return {"ok": True}


# -- corrections -----------------------------------------------------------

def _target(state, event_id):
    ev = next((e for e in state.session.events if e["id"] == event_id), None)
    if ev is None or ev["type"] in META_TYPES:
        bad("No such event", 404)
    return ev


@router.post("/api/events/{event_id}/strike")
async def strike(request: Request, event_id: int):
    state = st(request)
    ev = _target(state, event_id)
    state.record("meta.strike", f"Struck: {ev['text']}", data={"target": event_id},
                 visibility="gm")
    return {"ok": True}


@router.post("/api/events/{event_id}/unstrike")
async def unstrike(request: Request, event_id: int):
    state = st(request)
    ev = _target(state, event_id)
    state.record("meta.unstrike", f"Restored: {ev['text']}", data={"target": event_id},
                 visibility="gm")
    return {"ok": True}


@router.post("/api/events/{event_id}/reveal")
async def reveal(request: Request, event_id: int):
    state = st(request)
    ev = _target(state, event_id)
    if not ev.get("masked"):
        bad("That roll isn't secret")
    state.record("meta.reveal", f"Revealed: {ev['text']}", data={"target": event_id})
    return {"ok": True}


# -- narration & notes -----------------------------------------------------

@router.post("/api/narrate")
async def narrate(request: Request, body: dict):
    text = (body.get("text") or "").strip()
    style = body.get("style") or "read-aloud"
    image_url = (body.get("image_url") or "").strip()
    if style not in ("read-aloud", "scene", "image"):
        bad("Unknown narration style")
    if not text and not image_url:
        bad("Nothing to narrate")
    if image_url and not image_url.startswith(("https://", "http://")):
        bad("Image links must start with http(s)://")
    title = text if style == "scene" else ""
    ev = st(request).record("narrate", text or image_url, title=title,
                            data={"text": text, "style": style, "image_url": image_url})
    return {"event": ev}


@router.post("/api/note")
async def note(request: Request, body: dict):
    text = (body.get("text") or "").strip()
    if not text:
        bad("Empty note")
    ev = st(request).record("note", text, visibility="gm", data={"text": text})
    return {"event": ev}


# -- live updates & the Table ---------------------------------------------

@router.get("/api/stream")
async def stream(request: Request):
    hub = st(request).hub
    q = hub.subscribe()
    return StreamingResponse(hub.stream(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/api/table")
def table_feed(request: Request):
    return st(request).table_payload()


@router.post("/api/table/clear")
async def clear_table(request: Request):
    """Wipe the Table back to a blank page. Nothing is deleted — the log keeps
    everything, and striking this entry brings the old Table back."""
    ev = st(request).record("table.cleared", "Table cleared", visibility="gm")
    return {"event": ev}


TABLE_SCALES = (0.9, 1.0, 1.15, 1.3)


@router.post("/api/table/scale")
async def table_scale(request: Request, body: dict):
    """The Table's text size: a nudge on top of the window-fit scale, for when a stream makes it hard to read."""
    scale = body.get("scale")
    if scale not in TABLE_SCALES:
        bad(f"scale must be one of {', '.join(str(x) for x in TABLE_SCALES)}")
    state = st(request)
    state.table_scale = float(scale)
    state.notify("table")
    return {"scale": state.table_scale}


@router.post("/api/table/mode")
async def table_mode(request: Request, body: dict):
    mode = body.get("mode")
    if mode not in ("auto", "chronicle", "combat", "battle"):
        bad("mode must be auto, chronicle, combat or battle")
    state = st(request)
    state.table_mode = mode
    state.notify("table")
    return {"mode": mode}


@router.get("/api/combat")
def get_combat(request: Request):
    return {"combat": combat_state.serialise(st(request).combat_state(), "gm")}


# -- Chronicle export --------------------------------------------------------

def _session_for(request, sid):
    state = st(request)
    if not sid or sid == state.session.id:
        return state.session
    try:
        return state.sessions.load(sid)
    except (KeyError, OSError):
        bad("No such session", 404)


def chronicle_markdown(session):
    fl = flags(session.events)
    created = session.created[:10]
    out = [f"# {session.title}", f"*Pendragon session chronicle — {created}*", ""]
    for ev in session.events:
        if ev["type"] in META_TYPES or fl.get(ev["id"], {}).get("struck"):
            continue
        t, d = ev["type"], ev.get("data", {})
        stamp = ev["ts"][11:16]
        secret = ev.get("masked") and not fl.get(ev["id"], {}).get("revealed")
        if t in ("session.started", "session.resumed", "session.ended"):
            out += ["", "---", f"*{stamp} — {ev['text']}*", ""]
        elif t == "combat.started":
            out += ["", f"## ⚔ {d.get('name', 'Combat')}", "", f"- {stamp} {ev['text']}"]
        elif t == "narrate" and d.get("style") == "scene":
            out += ["", f"## {d.get('text')}", ""]
        elif t == "narrate":
            if d.get("text"):
                out += ["", f"> {d['text']}", ""]
            if d.get("image_url"):
                out += [f"![]({d['image_url']})", ""]
        elif t in ("npc.generated", "npc.presented"):
            npc = d.get("npc", {})
            out += ["", f"### {npc.get('full', ev['title'])}",
                    f"*{npc.get('subtitle', '')}*", "", f"> {npc.get('description', '')}", ""]
        elif t == "rule.shown":
            out += [f"- {stamp} 📜 Rule consulted: **{d.get('title', '')}**"]
        elif t == "note":
            out += [f"- {stamp} 🔒 *GM note:* {ev['text']}"]
        else:
            tag = " *(secret roll)*" if secret else ""
            out += [f"- {stamp} {ev['text']}{tag}"]
    return "\n".join(out).replace("\n\n\n", "\n\n") + "\n"


CHRONICLE_CSS = """
body{background:#efe4c8;color:#2b2118;font:18px/1.6 'EB Garamond',Georgia,serif;
max-width:46rem;margin:3rem auto;padding:0 1.25rem}
h1,h2,h3{font-family:'Cinzel',Georgia,serif;color:#6b1d1d;letter-spacing:.02em}
h1{font-size:2.2rem;border-bottom:2px solid #b08d57;padding-bottom:.3rem}
blockquote{border-left:3px solid #b08d57;margin:1rem 0;padding:.2rem 1rem;font-style:italic;
background:#f6efdc}
li{margin:.15rem 0}hr{border:0;border-top:1px solid #b08d57;margin:2rem 0}
img{max-width:100%;border:4px double #b08d57}
"""


@router.get("/api/session/chronicle.md", response_class=PlainTextResponse)
def chronicle_md(request: Request, id: str = ""):
    s = _session_for(request, id)
    return Response(chronicle_markdown(s), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{s.id}.md"'})


@router.get("/api/session/chronicle.html", response_class=HTMLResponse)
def chronicle_html(request: Request, id: str = ""):
    s = _session_for(request, id)
    body = render_markdown(chronicle_markdown(s))
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(s.title)}</title>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Cinzel:wght@600"
        "&family=EB+Garamond:ital@0;1&display=swap'>"
        f"<style>{CHRONICLE_CSS}</style></head><body>{body}</body></html>")


@router.get("/api/session/download")
def download(request: Request, id: str = ""):
    s = _session_for(request, id)
    return Response(json.dumps(s.to_json(), ensure_ascii=False, indent=1),
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{s.id}.json"'})
