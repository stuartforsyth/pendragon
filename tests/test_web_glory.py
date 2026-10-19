"""The Glory ledger: automatic credit for defeated foes, reassigning, manual
awards, and the players' knight cards."""

from tests.conftest import ok


def _fight(client, encounter="Knights of Gorre", knights=("Sir Bors", "Sir Cai")):
    pids = [ok(client.post("/api/party", json={"name": k, "player": "P"}))["member"]["id"] for k in knights]
    ok(client.post("/api/combat/start", json={"encounter": encounter}))
    return ok(client.get("/api/combat"))["combat"], pids


def _cs(client):
    return ok(client.get("/api/combat"))["combat"]


def _foes(cs):
    return [c for c in cs["combatants"] if c["side"] != "party"]


def _slay(client, cid):
    return ok(client.post(f"/api/combat/{cid}/status", json={"out": "dead"}))


def test_auto_glory_to_engaged_knight(client):
    cs, (bors, _) = _fight(client)
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    r = _slay(client, foe["id"])
    assert r["prompt"] is None
    cs = _cs(client)
    assert cs["glory"][bors] == foe["glory"] == 50
    assert "+50 Glory, Sir Bors" in client.get("/api/table").text


def test_strike_removes_auto_glory(client):
    cs, (bors, _) = _fight(client)
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    ev = _slay(client, foe["id"])["event"]
    ok(client.post(f"/api/events/{ev['id']}/strike"))
    assert _cs(client)["glory"][bors] == 0


def test_retarget_after_defeat_keeps_credit(client):
    cs, (bors, cai) = _fight(client)
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    _slay(client, foe["id"])
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Cai"}))
    cs = _cs(client)
    assert cs["glory"][bors] == 50 and cs["glory"][cai] == 0


def test_unengaged_defeat_prompts_and_credit_route(client):
    cs, (bors, _) = _fight(client)
    foe, other = _foes(cs)[:2]
    r = _slay(client, foe["id"])
    assert r["prompt"]["kind"] == "who_defeated" and r["prompt"]["cid"] == foe["id"]
    assert foe["id"] in _cs(client)["uncredited"]
    ok(client.post(f"/api/combat/{foe['id']}/credit", json={"knight": bors}))
    cs = _cs(client)
    assert cs["glory"][bors] == 50 and foe["id"] not in cs["uncredited"]
    _slay(client, other["id"])
    ok(client.post(f"/api/combat/{other['id']}/credit", json={"knight": None}))
    cs = _cs(client)
    assert cs["glory"][bors] == 50 and other["id"] not in cs["uncredited"]


def test_reassign_moves_credit(client):
    cs, (bors, cai) = _fight(client)
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    _slay(client, foe["id"])
    ok(client.post(f"/api/combat/{foe['id']}/credit", json={"knight": cai}))
    cs = _cs(client)
    assert cs["glory"][bors] == 0 and cs["glory"][cai] == 50


def test_redefeat_does_not_double_count(client):
    cs, (bors, _) = _fight(client)
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    _slay(client, foe["id"])
    ok(client.post(f"/api/combat/{foe['id']}/status", json={"out": None}))
    assert _cs(client)["glory"][bors] == 0
    _slay(client, foe["id"])
    assert _cs(client)["glory"][bors] == 50


def test_manual_award_without_fight(client):
    bors = ok(client.post("/api/party", json={"name": "Sir Bors"}))["member"]["id"]
    ev = ok(client.post("/api/glory", json={"knight": bors, "amount": 100, "reason": "rescued the abbess"}))["event"]
    assert ev["data"]["fight"] is None
    card = ok(client.get("/api/table"))["feed"][0]
    assert card["data"] == {"knight_name": "Sir Bors", "amount": 100, "reason": "rescued the abbess"}
    assert client.post("/api/glory", json={"knight": bors, "amount": 0, "reason": "x"}).status_code == 400
    assert client.post("/api/glory", json={"knight": bors, "amount": 5, "reason": ""}).status_code == 400


def test_manual_award_counts_in_active_fight(client):
    cs, (bors, _) = _fight(client)
    ok(client.post("/api/glory", json={"knight": bors, "amount": 25, "reason": "seized the standard"}))
    assert _cs(client)["glory"][bors] == 25


def test_glory_hidden_before_defeat(client):
    cs, _ = _fight(client)
    foe = _foes(cs)[0]
    t = next(c for c in ok(client.get("/api/table"))["combat"]["combatants"] if c["id"] == foe["id"])
    assert "glory" not in t and t["credit"] is None


def test_knight_card_last_line_and_no_touches_leak(client):
    cs, (bors, _) = _fight(client)
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    _slay(client, foe["id"])
    t = ok(client.get("/api/table"))
    card = next(k for k in t["knights"] if k["pid"] == bors)
    assert "+50 Glory, Sir Bors" in card["happened"][0]
    assert card["glory"]["value"] == 50 and card["glory"]["last"]["amount"] == 50
    assert len(card["lane"]["foes"]) == 0
    assert "touches" not in client.get("/api/table").text


def test_old_session_without_glory_events_replays(client):
    from web.combat_state import reduce
    events = [{"id": 1, "type": "combat.started", "data": {"name": "Old", "combatants": []}},
              {"id": 2, "type": "combat.round", "data": {"round": 2}}]
    state = reduce(events)
    assert state["round"] == 2 and state["credits"] == {}


def test_glory_tally_written_before_round_and_end(client):
    cs, (bors, cai) = _fight(client)
    ok(client.post("/api/glory", json={"knight": cai, "amount": 30, "reason": "a deed"}))
    ok(client.post("/api/glory", json={"knight": bors, "amount": 10, "reason": "a lesser deed"}))
    ok(client.post("/api/combat/round"))
    feed = list(reversed(ok(client.get("/api/table"))["feed"]))
    types = [c["type"] for c in feed]
    i = types.index("combat.tally")
    assert types[i + 1] == "combat.round"                      # the tally lands before the new round
    rows = feed[i]["data"]["ranking"]
    assert [(r["name"], r["glory"], r["winner"]) for r in rows] == [("Sir Cai", 30, True), ("Sir Bors", 10, False)]
    ok(client.post("/api/combat/end"))
    feed = list(reversed(ok(client.get("/api/table"))["feed"]))
    types = [c["type"] for c in feed]
    last = len(types) - 1 - types[::-1].index("combat.tally")
    assert types[last + 1] == "combat.ended" and feed[last]["data"]["final"] is True
