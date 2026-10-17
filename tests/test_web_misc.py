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
