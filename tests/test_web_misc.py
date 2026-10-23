"""API coverage for the Cast, Party, Rules and Sessions tools."""

from tests.conftest import ok


def _npc(client, **kw):
    return ok(client.post("/api/npc/generate", json={"culture": "Saxon", **kw}))["npc"]


def test_cast_keep_is_idempotent_by_uid(client):
    npc = _npc(client)
    a = ok(client.post("/api/cast", json={"npc": npc}))["entry"]
    b = ok(client.post("/api/cast", json={"npc": npc}))["entry"]
    assert a["id"] == b["id"] and len(ok(client.get("/api/cast"))["cast"]) == 1


def test_cast_import_export_and_remove(client):
    roster = [{**_npc(client), "notes": "owes a debt"}, _npc(client, gender="Female")]
    assert ok(client.post("/api/cast/import", json=roster))["added"] == 2
    cast = ok(client.get("/api/cast"))["cast"]
    assert "notes" not in cast[0]["npc"] and cast[0]["notes"] == "owes a debt"
    md = client.get("/api/cast/export.md").text
    assert roster[0]["full"] in md and "owes a debt" in md
    ok(client.delete(f"/api/cast/{cast[0]['id']}"))
    assert client.delete(f"/api/cast/{cast[0]['id']}").status_code == 404
    assert client.post("/api/cast/import", json=[{"nope": 1}]).status_code == 400


def test_party_is_a_plain_roster(client):
    m = ok(client.post("/api/party", json={"name": "Sir Kay", "player": "Sam", "max_hp": 30}))["member"]
    assert m["active"] is True and "max_hp" not in m and "cur_hp" not in m
    ok(client.patch(f"/api/party/{m['id']}", json={"active": False, "notes": "seneschal"}))
    assert ok(client.get("/api/party"))["party"][0]["notes"] == "seneschal"
    assert client.post(f"/api/party/{m['id']}/hp", json={"delta": 1}).status_code in (404, 405)
    assert client.post("/api/party", json={"player": "nobody"}).status_code == 400


def test_rules_browse_and_missing(client):
    allr = ok(client.get("/api/rules", params={"limit": 500}))["results"]
    assert len(allr) > 50 and all("chapter" in r for r in allr)
    assert client.get("/api/rules/no.such.rule").status_code == 404
    rule = ok(client.get(f"/api/rules/{allr[0]['id']}"))["rule"]
    assert rule["html"].startswith("<")


def test_sessions_list_and_resume_switches(client):
    a = ok(client.post("/api/session/start", json={"title": "First"}))["session"]
    b = ok(client.post("/api/session/start", json={"title": "Second"}))["session"]
    listing = ok(client.get("/api/sessions"))
    assert listing["active"] == b["id"] and {s["id"] for s in listing["sessions"]} == {a["id"], b["id"]}
    ok(client.post("/api/session/resume", json={"id": a["id"]}))
    listing = ok(client.get("/api/sessions"))
    assert listing["active"] == a["id"]
    second = next(s for s in listing["sessions"] if s["id"] == b["id"])
    assert second["ended"]
    assert client.post("/api/session/resume", json={"id": "../etc"}).status_code == 404


def test_pin_rules(client):
    rid = ok(client.get("/api/rules", params={"q": "knockdown"}))["results"][0]["id"]
    assert ok(client.post(f"/api/rules/{rid}/pin", json={"pinned": True}))["pinned"]
    assert [p["id"] for p in ok(client.get("/api/rules/pins"))["pins"]] == [rid]
    assert not ok(client.post(f"/api/rules/{rid}/pin", json={"pinned": False}))["pinned"]
    assert ok(client.get("/api/rules/pins"))["pins"] == []
    assert client.post("/api/rules/nope/pin", json={}).status_code == 404


def test_static_files_are_always_revalidated(client):
    r = client.get("/static/js/gm.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"


def test_unsaved_work_survives_a_server_restart(tmp_path):
    from web.sessions import SessionStore
    store = SessionStore(str(tmp_path))
    assert store.active.scratch
    store.active.append("roll.dice", "3d6: 11")
    again = SessionStore(str(tmp_path))                  # the server restarts with no session started
    assert again.active.scratch and [e["text"] for e in again.active.events] == ["3d6: 11"]
    assert not any(m["id"] == "scratch" for m in again.list())
    again.start("Session 2")                             # a real session leaves the scratch log behind
    again.end()
    assert SessionStore(str(tmp_path)).active.events == []


def test_feedback_queue_records_where_it_came_from(client):
    from web import feedback as FB
    ok(client.post("/api/combat/start", json={"encounter": "Pictish Knifemen"}))
    r = ok(client.post("/api/feedback", json={"kind": "bug", "message": "Attack does nothing",
                                              "page": {"route": "#/combat", "tool": "Combat", "picked": "Pictish Knifemen 2"}}))
    item = r["item"]
    assert item["id"] == 1 and item["status"] == "new" and item["page"]["picked"] == "Pictish Knifemen 2"
    assert item["where"]["combat"]["name"] and item["where"]["session"]["last_event"] >= 1
    assert client.post("/api/feedback", json={"message": "  "}).status_code == 400
    data = str(client.tmp / "data")
    assert FB.mark(data, [1], "done", "Fixed") == [1]
    mine = ok(client.get("/api/feedback"))["items"]
    assert mine[0]["status"] == "done" and mine[0]["note"] == "Fixed"


def test_healthz_reports_a_boot_id(client):
    assert len(client.get("/healthz").json()["boot"]) == 8
    assert client.get("/healthz").json()["viewers"] == 0            # launch.sh opens a browser when no tab is connected


def test_delete_session_bins_it_but_not_the_active_one(client):
    from tests.conftest import ok
    import os
    ok(client.post("/api/session/start", json={"title": "Test run"}))
    sid = ok(client.get("/api/session"))["session"]["id"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 409        # in progress
    ok(client.post("/api/session/end"))
    ok(client.post("/api/session/start", json={"title": "Real one"}))
    assert sid in [s["id"] for s in ok(client.get("/api/sessions"))["sessions"]]
    ok(client.delete(f"/api/sessions/{sid}"))
    assert sid not in [s["id"] for s in ok(client.get("/api/sessions"))["sessions"]]
    assert os.path.exists(client.tmp / "sessions" / ".trash" / f"{sid}.json")   # binned, not destroyed
    assert client.delete(f"/api/sessions/{sid}").status_code == 404
    assert client.delete("/api/sessions/../etc").status_code == 404
