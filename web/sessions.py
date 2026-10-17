"""Sessions and the append-only event log.

Every action in the app becomes an **event**. A session's events, in order,
are the single source of truth: the GM log, the Table screen, and the saved
session file are all views of them, and live combat state is rebuilt by
replaying them (see ``web.combat_state``).

An event is a JSON object::

    {"id": 17, "ts": "2026-10-16T19:02:11", "type": "roll.check",
     "visibility": "public" | "gm", "masked": false,
     "title": "Sir Bors — Valorous", "text": "Valorous 15: rolled 12 — SUCCESS",
     "data": {...type-specific...}}

Corrections never delete: a ``meta.strike`` event strikes its target (it
vanishes from the Table and stops affecting state), ``meta.unstrike`` undoes
that, and ``meta.reveal`` turns a masked roll into its real result.

Each session is one file, ``sessions/<id>.json``, rewritten atomically after
every event. With no session started, events go to an unsaved scratch log so
the dice and Table still work.
"""

import datetime
import json
import os
import re

META_TYPES = ("meta.strike", "meta.unstrike", "meta.reveal")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or "session"


class Session:
    def __init__(self, sid, title, created=None, ended=None, events=None, path=None, backup=None):
        self.id = sid
        self.title = title
        self.created = created or _now()
        self.ended = ended
        self.events = events or []
        self.path = path            # None = unsaved scratch log
        self.backup = backup        # scratch only: kept on disk so a server restart loses nothing

    @property
    def scratch(self):
        return self.path is None

    @property
    def next_id(self):
        return (self.events[-1]["id"] + 1) if self.events else 1

    def meta(self):
        return {"id": self.id, "title": self.title, "created": self.created,
                "ended": self.ended, "scratch": self.scratch,
                "count": len(self.events)}

    def to_json(self):
        return {"id": self.id, "title": self.title, "created": self.created,
                "ended": self.ended, "events": self.events}

    def save(self):
        target = self.path or self.backup
        if target is None:
            return
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, ensure_ascii=False, indent=1)
        os.replace(tmp, target)

    def append(self, etype, text, *, title="", data=None, visibility="public",
               masked=False):
        ev = {"id": self.next_id, "ts": _now(), "type": etype,
              "visibility": visibility, "masked": bool(masked),
              "title": title, "text": text, "data": data or {}}
        self.events.append(ev)
        self.save()
        return ev


def flags(events):
    """{event id: {"struck": bool, "revealed": bool}} from the meta events."""
    out = {}
    for ev in events:
        if ev["type"] not in META_TYPES:
            continue
        d = ev.get("data") or {}
        targets = d.get("targets") or [d.get("target")]     # a cascade undo strikes many at once
        for target in targets:
            f = out.setdefault(target, {"struck": False, "revealed": False})
            if ev["type"] == "meta.strike":
                f["struck"] = True
            elif ev["type"] == "meta.unstrike":
                f["struck"] = False
            elif ev["type"] == "meta.reveal":
                f["revealed"] = True
    return out


def live_events(events):
    """The non-meta events that still count (not struck), in order."""
    fl = flags(events)
    return [ev for ev in events if ev["type"] not in META_TYPES
            and not fl.get(ev["id"], {}).get("struck")]


class SessionStore:
    """All session files under one directory, plus the single active session."""

    def __init__(self, directory):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.active = self._scratch()
        sid = self._read_pointer()
        if sid and os.path.isfile(self._path(sid)):
            self.active = self.load(sid)

    # -- files -------------------------------------------------------------

    def _path(self, sid):
        return os.path.join(self.dir, f"{sid}.json")

    def _pointer(self):
        return os.path.join(self.dir, ".active")

    def _read_pointer(self):
        try:
            with open(self._pointer(), encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""

    def _write_pointer(self, sid):
        if sid:
            with open(self._pointer(), "w", encoding="utf-8") as fh:
                fh.write(sid)
        elif os.path.exists(self._pointer()):
            os.remove(self._pointer())

    def _scratch_path(self):
        return os.path.join(self.dir, ".scratch.json")

    def _scratch(self, fresh=False):
        """The no-session log. Not a session file (never listed or resumable),
        but backed up on disk so restarting the server doesn't wipe a fight or
        battle run without a session. Starting or ending a session clears it."""
        path = self._scratch_path()
        if fresh and os.path.exists(path):
            os.remove(path)
        events = []
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    events = json.load(fh).get("events", [])
            except (OSError, ValueError):
                events = []
        return Session("scratch", "Unsaved — no session started", events=events, backup=path)

    def load(self, sid):
        if not re.fullmatch(r"[a-z0-9-]+", sid or ""):
            raise KeyError(sid)
        path = self._path(sid)
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return Session(d["id"], d["title"], d.get("created"), d.get("ended"),
                       d.get("events", []), path)

    def list(self):
        out = []
        for name in os.listdir(self.dir):
            if not name.endswith(".json"):
                continue
            try:
                s = self.load(name[:-5])
            except (OSError, ValueError, KeyError):
                continue
            out.append(s.meta())
        out.sort(key=lambda m: m["created"], reverse=True)
        return out

    def suggest_title(self):
        n = len(self.list()) + 1
        return f"Session {n} — {datetime.date.today().strftime('%-d %b %Y')}"

    # -- lifecycle -----------------------------------------------------------

    def start(self, title):
        title = (title or "").strip() or self.suggest_title()
        base = f"{datetime.date.today().isoformat()}-{slugify(title)}"
        sid, n = base, 2
        while os.path.exists(self._path(sid)):
            sid, n = f"{base}-{n}", n + 1
        self._scratch(fresh=True)                   # the scratch log is left behind
        self.active = Session(sid, title, path=self._path(sid))
        self.active.append("session.started", f"Session begins: {title}", title=title)
        self._write_pointer(sid)
        return self.active

    def end(self):
        s = self.active
        if s.scratch:
            return s
        s.append("session.ended", f"Session ends: {s.title}", title=s.title)
        s.ended = _now()
        s.save()
        self._write_pointer("")
        self.active = self._scratch(fresh=True)
        return s

    def resume(self, sid):
        if not self.active.scratch and self.active.id != sid:
            self.end()
        if self.active.scratch:
            self._scratch(fresh=True)
        s = self.load(sid)
        s.ended = None
        s.append("session.resumed", f"Session resumes: {s.title}", title=s.title)
        self.active = s
        self._write_pointer(sid)
        return s
