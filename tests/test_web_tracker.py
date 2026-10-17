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


def _knight(cs, name):
    return next(c for c in cs["combatants"] if c["display_name"] == name)


def _attack_height(client, cid):
    ev = ok(client.post(f"/api/combat/{cid}/roll", json={"what": "attack", "key": 0}))["event"]
    return ev["data"]["height"]


def test_knights_mounted_default_and_off(client):
    cs = _fight(client)
    assert all(c["mounted"] for c in cs["combatants"] if c["side"] == "party")
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush", "knights_mounted": False}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert not any(c["mounted"] for c in cs["combatants"] if c["side"] == "party")


def test_height_applied_to_foe_attack(client):
    cs = _fight(client, knights=("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    gorre = _foes(cs)[0]
    ok(client.post(f"/api/combat/{gorre['id']}/engage", json={"with": "Sir Bors"}))
    assert _attack_height(client, gorre["id"]) == 0                       # both mounted
    ok(client.post(f"/api/combat/{bors['id']}/mounted", json={"mounted": False}))
    assert _attack_height(client, gorre["id"]) == 5                       # rider vs footman
    ok(client.post(f"/api/combat/{gorre['id']}/height", json={"override": "none"}))
    assert _attack_height(client, gorre["id"]) == 0
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush"}))
    cs = ok(client.get("/api/combat"))["combat"]
    bandit = _foes(cs)[0]
    assert _attack_height(client, bandit["id"]) == 0                      # not engaged
    ok(client.post(f"/api/combat/{bandit['id']}/engage", json={"with": "Sir Bors"}))
    assert _attack_height(client, bandit["id"]) == -5                     # footman vs rider
    ok(client.post(f"/api/combat/{bandit['id']}/horse", json={"on": True}))
    assert _attack_height(client, bandit["id"]) == 0                      # going for the horse
    cs = ok(client.get("/api/combat"))["combat"]
    assert _knight(cs, "Sir Bors")["height_chips"] == [{"foe": bandit["display_name"], "mod": 5}]


def test_height_not_applied_to_characteristic_rolls(client):
    cs = _fight(client, encounter="Bandit ambush", knights=("Sir Bors",))
    bandit = _foes(cs)[0]
    ok(client.post(f"/api/combat/{bandit['id']}/engage", json={"with": "Sir Bors"}))
    ev = ok(client.post(f"/api/combat/{bandit['id']}/roll", json={"what": "char", "key": "DEX"}))["event"]
    assert ev["data"]["modifier"] == 0 and "height" not in ev["data"]


def test_surrender_minus5_from_pills(client):
    cs = _fight(client, encounter="Bandit ambush", knights=("Sir Bors",))
    bandit = _foes(cs)[0]
    ok(client.post(f"/api/combat/{bandit['id']}/engage", json={"with": "Sir Bors"}))
    ev = ok(client.post(f"/api/combat/{bandit['id']}/surrender"))["event"]
    assert "on foot vs a mounted knight" in ev["text"]


def test_mo_chip_counts_and_limit(client):
    cs = _fight(client, encounter="Pictish Knifemen", knights=("Sir Bors", "Sir Cai"))
    knife = _foes(cs)
    for f in knife[:3]:
        ok(client.post(f"/api/combat/{f['id']}/engage", json={"with": "Sir Bors"}))
    mo = _knight(ok(client.get("/api/combat"))["combat"], "Sir Bors")["mo"]
    assert mo == {"n": 3, "mod": -10, "limit": 3, "over": False}
    ok(client.post(f"/api/combat/{knife[3]['id']}/engage", json={"with": "Sir Bors"}))
    assert _knight(ok(client.get("/api/combat"))["combat"], "Sir Bors")["mo"]["over"]
    cs = _fight(client, knights=())                          # restart with Gorre (mounted)
    gorre = _foes(cs)[:2]
    for f in gorre:
        ok(client.post(f"/api/combat/{f['id']}/engage", json={"with": "Sir Bors"}))
    assert _knight(ok(client.get("/api/combat"))["combat"], "Sir Bors")["mo"]["limit"] == 2


def test_captured_defaults_to_engaged_knight(client):
    cs = _fight(client, knights=("Sir Bors",))
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    assert client.post(f"/api/combat/{foe['id']}/captured", json={}).status_code == 400   # still fighting
    ok(client.post(f"/api/combat/{foe['id']}/status", json={"out": "surrendered"}))
    ok(client.post(f"/api/combat/{foe['id']}/captured", json={}))
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == foe["id"])
    assert row["captured_by_name"] == "Sir Bors"


def test_table_shows_height_chip_not_numbers(client):
    cs = _fight(client, encounter="Bandit ambush", knights=("Sir Bors",))
    bandit = _foes(cs)[0]
    ok(client.post(f"/api/combat/{bandit['id']}/engage", json={"with": "Sir Bors"}))
    t = next(c for c in ok(client.get("/api/table"))["combat"]["combatants"] if c["id"] == bandit["id"])
    assert t["height_chip"] == "−5 Height"
    for secret in ("cur_hp", "max_hp", "attacks", "height"):
        assert secret not in t


def test_adversary_editor_keeps_flags(client):
    adv = ok(client.get("/api/adversaries/Bandit"))["adversary"]
    adv.update(mounted=True, countercharge=True, attacks_horse=True)
    ok(client.put("/api/adversaries", json={"adversary": adv, "original": "Bandit"}))
    back = ok(client.get("/api/adversaries/Bandit"))["adversary"]
    assert back["mounted"] and back["countercharge"] and back["attacks_horse"]
