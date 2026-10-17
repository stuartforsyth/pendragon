"""Feedback queue: the GM console's Feedback tab (right edge) sends a bug,
change or idea with where it came from (the tool, the session and its newest
event, the fight and round, the battle day/turn, any token open, selected
text). Stored in ``data/feedback.json`` (the GM's own file, git-ignored); the
``/feedback`` skill reads it, reproduces each report on a copy of that
session, fixes or plans it, and marks it done with a note shown in the panel.

CLI (for the skill)::

    .venv/bin/python -m web.feedback list [--status new|all] [--json]
    .venv/bin/python -m web.feedback mark 3,4 --status done --note "Fixed in a1b2c3d"
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

KINDS = ("bug", "change", "idea", "question")
STATUSES = ("new", "planned", "done", "wontfix")
MAX_LEN = 4000


def _path(data_dir):
    return os.path.join(data_dir, "feedback.json")


def load(data_dir):
    p = _path(data_dir)
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _save(data_dir, items):
    p = _path(data_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def app_version(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=3).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def snapshot(state):
    """Where the app was when the report was sent: enough to reload that
    session and replay to the same moment."""
    s = state.session
    out = {"session": {"id": s.id, "title": s.meta().get("title"), "scratch": bool(getattr(s, "scratch", False)),
                       "last_event": s.events[-1]["id"] if s.events else 0}}
    try:
        cs = state.combat_state()
        if cs and cs.get("active"):
            out["combat"] = {"name": cs.get("name"), "round": cs.get("round"),
                             "battle": (cs.get("battle") or {}).get("id")}
    except Exception:                       # a report must never fail because state is odd
        pass
    try:
        b = state.battle_state()
        if b:
            out["battle"] = {"name": (b.get("definition") or {}).get("name"), "status": b.get("status"),
                             "day": b.get("day"), "turn": b.get("turn")}
    except Exception:
        pass
    return out


def submit(state, body, user_agent=""):
    msg = str(body.get("message") or "").strip()
    if not msg:
        raise ValueError("Write something first.")
    if len(msg) > MAX_LEN:
        raise ValueError(f"That's too long (the limit is {MAX_LEN} characters).")
    items = load(state.data_dir)
    page = body.get("page") or {}
    item = {
        "id": max((i["id"] for i in items), default=0) + 1,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kind": body.get("kind") if body.get("kind") in KINDS else "bug",
        "message": msg,
        "page": {k: str(page.get(k) or "")[:300] for k in ("route", "tool", "heading", "selected", "open", "picked", "viewport")},
        "where": snapshot(state),
        "app_version": app_version(state.root),
        "user_agent": (user_agent or "")[:200],
        "status": "new",
        "note": "",
    }
    items.append(item)
    _save(state.data_dir, items)
    return item


def mark(data_dir, ids, status, note=None):
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    items = load(data_dir)
    hit = []
    for i in items:
        if i["id"] in ids:
            i["status"] = status
            if note is not None:
                i["note"] = note
            i["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            hit.append(i["id"])
    _save(data_dir, items)
    return hit


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="python -m web.feedback")
    ap.add_argument("--data-dir", default=os.environ.get("PENDRAGON_DATA_DIR")
                    or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="the queue")
    ls.add_argument("--status", default="new", help="new, planned, done, wontfix or all")
    ls.add_argument("--json", action="store_true")
    mk = sub.add_parser("mark", help="set status (and the note shown in the panel)")
    mk.add_argument("ids", help="comma-separated ids")
    mk.add_argument("--status", required=True)
    mk.add_argument("--note")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        items = [i for i in load(a.data_dir) if a.status == "all" or i["status"] == a.status]
        if a.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        elif not items:
            print("No feedback waiting.")
        else:
            for i in items:
                w, p = i.get("where", {}), i.get("page", {})
                print(f"#{i['id']} [{i['kind']}] {i['status']} {i['created_at']} · {p.get('route')} {p.get('heading')}")
                print(f"   {i['message']}")
                print(f"   session {w.get('session', {}).get('id')} @event {w.get('session', {}).get('last_event')}"
                      + (f" · combat {w['combat']['name']} r{w['combat']['round']}" if w.get("combat") else "")
                      + (f" · battle {w['battle']['name']} {w['battle']['status']} d{w['battle']['day']} t{w['battle']['turn']}" if w.get("battle") else ""))
    else:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
        print("Marked:", mark(a.data_dir, ids, a.status, a.note))


if __name__ == "__main__":
    sys.exit(_cli())
