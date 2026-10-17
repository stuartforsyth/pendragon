"""The combat tracker's lanes: surrender, retargeting, the GM-only type headers."""

from tests.conftest import ok


def _fight(client, encounter="Knights of Gorre", knights=("Sir Bors", "Sir Cai")):
    for k in knights:
        ok(client.post("/api/party", json={"name": k, "player": "P"}))
    ok(client.post("/api/combat/start", json={"encounter": encounter}))
    return ok(client.get("/api/combat"))["combat"]


def _foes(cs):
    return [c for c in cs["combatants"] if c["side"] != "party"]


def test_foe_can_surrender_knight_cannot(client):
    cs = _fight(client)
    foe = _foes(cs)[0]
    knight = next(c for c in cs["combatants"] if c["side"] == "party")
    ok(client.post(f"/api/combat/{foe['id']}/status", json={"out": "surrendered"}))
    assert client.post(f"/api/combat/{knight['id']}/status", json={"out": "surrendered"}).status_code == 400
    t = next(c for c in ok(client.get("/api/table"))["combat"]["combatants"] if c["id"] == foe["id"])
    assert t["wound_state"] == "Surrendered"
    assert foe["id"] in ok(client.get("/api/combat"))["combat"]["defeated"]


def test_retarget_to_pool_and_lane(client):
    cs = _fight(client)
    foe = _foes(cs)[0]
    assert foe["id"] in cs["pool"]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert foe["id"] not in cs["pool"]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": ""}))
    assert foe["id"] in ok(client.get("/api/combat"))["combat"]["pool"]


def test_types_deduplicated_in_gm_view_only(client):
    cs = _fight(client)
    assert [t["type"] for t in cs["types"]] == ["Knights of Gorre"]
    assert "APP" not in cs["types"][0]["characteristics"]
    raw = client.get("/api/table").text
    assert '"types"' not in raw and '"gm_notes"' not in raw
