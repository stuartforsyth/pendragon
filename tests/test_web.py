import shutil

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ROOT
from web.app import create_app


@pytest.fixture
def client(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for f in ("rules.json", "examplecombat.json", "rules_index.jsonl"):
        shutil.copy(f"{ROOT}/data/{f}", data / f)
    app = create_app(ROOT, sessions_dir=str(tmp_path / "sessions"), data_dir=str(data))
    with TestClient(app) as c:
        c.tmp = tmp_path
        yield c


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def test_pages_and_health(client):
    assert client.get("/healthz").json() == {"ok": True}
    assert "Pendragon" in client.get("/").text
    assert client.get("/table").status_code == 200


def test_session_lifecycle_persists(client):
    s = ok(client.get("/api/session"))
    assert s["session"]["scratch"]
    ok(client.post("/api/session/start", json={"title": "Night at Sarum"}))
    ok(client.post("/api/roll/dice", json={"expr": "3d6+2", "label": "Test"}))
    meta = ok(client.get("/api/session"))["session"]
    assert meta["title"] == "Night at Sarum" and meta["count"] == 2
    files = list((client.tmp / "sessions").glob("*.json"))
    assert len(files) == 1 and "night-at-sarum" in files[0].name
    ok(client.post("/api/session/end"))
    assert ok(client.get("/api/session"))["session"]["scratch"]
    ok(client.post("/api/session/resume", json={"id": meta["id"]}))
    assert ok(client.get("/api/session"))["session"]["count"] == 4


def test_masked_roll_is_sealed_until_revealed(client):
    ev = ok(client.post("/api/roll/check", json={"label": "Awareness", "value": 12,
                                                 "masked": True}))["event"]
    card = ok(client.get("/api/table"))["feed"][0]
    assert card["type"] == "sealed" and card["title"] == "" and "roll" not in str(card["data"])
    ok(client.post(f"/api/events/{ev['id']}/reveal"))
    card = next(c for c in ok(client.get("/api/table"))["feed"] if c["id"] == ev["id"])
    assert card["type"] == "roll.check" and card["revealed"]


def test_notes_never_reach_the_table(client):
    ok(client.post("/api/note", json={"text": "the Saxon is a spy"}))
    assert "spy" not in client.get("/api/table").text
    assert "spy" in client.get("/api/session").text


def test_strike_removes_from_table_and_state(client):
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush", "players": 3}))
    c = ok(client.get("/api/combat"))["combat"]["combatants"][0]
    ev = ok(client.post(f"/api/combat/{c['id']}/hp", json={"delta": -5}))["event"]
    after = ok(client.get("/api/combat"))["combat"]["combatants"][0]
    assert after["cur_hp"] == c["cur_hp"] - 5
    ok(client.post(f"/api/events/{ev['id']}/strike"))
    undone = ok(client.get("/api/combat"))["combat"]["combatants"][0]
    assert undone["cur_hp"] == c["cur_hp"]
    assert all(card["id"] != ev["id"] for card in ok(client.get("/api/table"))["feed"])


def test_table_hides_foe_numbers(client):
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush", "players": 2}))
    c = ok(client.get("/api/combat"))["combat"]["combatants"][0]
    ok(client.post(f"/api/combat/{c['id']}/hp", json={"delta": -3}))
    t = ok(client.get("/api/table"))
    assert t["mode"] == "combat"
    foe = t["combat"]["combatants"][0]
    assert "cur_hp" not in foe and foe["wound_state"] == "Wounded"
    assert "Hit Points" not in t["feed"][0]["text"]


def test_party_joins_combat_and_hp_carries_back(client):
    m = ok(client.post("/api/party", json={"name": "Sir Bors", "player": "Ann",
                                           "max_hp": 30, "major_wound": 14}))["member"]
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush"}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["players"] == 1
    knight = next(c for c in cs["combatants"] if c["side"] == "party")
    ok(client.post(f"/api/combat/{knight['id']}/hp", json={"delta": -4}))
    ok(client.post("/api/combat/end"))
    assert ok(client.get("/api/party"))["party"][0]["cur_hp"] == 26
    assert ok(client.get("/api/table"))["mode"] == "chronicle"
    assert m["id"]


def test_combat_rolls_and_round(client):
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush", "players": 2}))
    c = ok(client.get("/api/combat"))["combat"]["combatants"][0]
    for body in ({"what": "char", "key": "DEX"}, {"what": "attack", "key": 0},
                 {"what": "damage", "key": 0, "critical": True}):
        ok(client.post(f"/api/combat/{c['id']}/roll", json=body))
    ok(client.post(f"/api/combat/{c['id']}/surrender"))
    ok(client.post("/api/combat/round"))
    assert ok(client.get("/api/combat"))["combat"]["round"] == 2


def test_npc_generate_reroll_keep_present(client):
    r = ok(client.post("/api/npc/generate", json={"culture": "Cymri", "gender": "Male",
                                                  "social_class": "Knight"}))
    npc = r["npc"]
    assert npc["full_knight"] and r["formats"]["markdown"].startswith("## ")
    r2 = ok(client.post("/api/npc/reroll", json={"npc": npc, "field": "Appearance"}))
    entry = ok(client.post("/api/cast", json={"npc": {**r2["npc"], "notes": "secret"}}))["entry"]
    ok(client.patch(f"/api/cast/{entry['id']}", json={"notes": "his brother is a traitor"}))
    ok(client.post(f"/api/cast/{entry['id']}/present"))
    feed = client.get("/api/table").text
    assert npc["full"] in feed and "traitor" not in feed and "secret" not in feed


def test_adversary_and_encounter_crud(client):
    blank = ok(client.get("/api/adversaries/blank"))["adversary"]
    blank["name"] = "Test Brigand"
    blank["armour"] = {"pieces": [], "helmet": "", "shield": ""}
    saved = ok(client.put("/api/adversaries", json={"adversary": blank}))
    assert saved["adversary"]["health"]["hit_points"] > 0
    assert (client.tmp / "data" / "combat.json").exists()
    enc = {"name": "Brigands", "roster": [{"adversary": "Test Brigand", "count": 1,
                                           "per_player": True}]}
    ok(client.put("/api/encounters", json={"encounter": enc}))
    prev = ok(client.post("/api/encounters/preview", json={"encounter": enc, "players": 3}))
    assert prev["total"] == 3
    ok(client.post("/api/combat/start", json={"encounter": "Brigands", "players": 3}))
    assert len(ok(client.get("/api/combat"))["combat"]["combatants"]) == 3


def test_rules_search_and_show(client):
    res = ok(client.get("/api/rules", params={"q": "major wound"}))["results"]
    assert res
    ok(client.post(f"/api/rules/{res[0]['id']}/show"))
    assert ok(client.get("/api/table"))["feed"][0]["type"] == "rule.shown"


def test_chronicle_export(client):
    ok(client.post("/api/session/start", json={"title": "Chronicle test"}))
    ok(client.post("/api/narrate", json={"text": "Winter, 512", "style": "scene"}))
    ok(client.post("/api/roll/dice", json={"expr": "d20", "masked": True}))
    md = client.get("/api/session/chronicle.md").text
    assert "## Winter, 512" in md and "(secret roll)" in md
    assert "<h1>" in client.get("/api/session/chronicle.html").text


def test_bad_dice(client):
    assert client.post("/api/roll/dice", json={"expr": "lots"}).status_code == 400


def _start_with_knight(client):
    ok(client.post("/api/party", json={"name": "Sir Bors", "max_hp": 30, "major_wound": 14,
                                       "knockdown": 14, "armour": 10, "shield": 6}))
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush"}))
    cs = ok(client.get("/api/combat"))["combat"]["combatants"]
    knight = next(c for c in cs if c["side"] == "party")
    foe = next(c for c in cs if c["side"] == "foe")
    return knight, foe


def test_blow_from_foe_weapon_lands_on_knight(client):
    knight, foe = _start_with_knight(client)
    ev = ok(client.post("/api/combat/blow", json={"attacker": foe["id"], "attack": 0,
                                                  "target": knight["id"], "critical": True}))["event"]
    b = ev["data"]["blow"]
    assert b["armour"] == 10 and b["shield_blocked"] == 0 and len(b["terms"]) == 2
    after = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == knight["id"])
    assert after["cur_hp"] == knight["cur_hp"] - b["wound"]
    card = ok(client.get("/api/table"))["feed"][0]
    assert card["type"] == "combat.blow" and card["data"]["blow"]["full"] == b["full"]
    ok(client.post(f"/api/events/{ev['id']}/strike"))       # undo
    undone = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == knight["id"])
    assert undone["cur_hp"] == knight["cur_hp"]


def test_player_rolled_blow_on_foe_rebated_with_shield(client):
    knight, foe = _start_with_knight(client)
    ev = ok(client.post("/api/combat/blow", json={"attacker": knight["id"], "weapon": "Sword",
                                                  "damage": 30, "rebated": True, "shield": True,
                                                  "target": foe["id"]}))["event"]
    b = ev["data"]["blow"]
    assert b["full"] == 30 and b["damage"] == 15
    assert b["wound"] == max(0, 15 - foe["armor_points"] - foe["shield"])
    assert b["knockdown"] in ("check", "automatic")
    assert "Hit Points" not in ev["data"]["table_text"]          # foe HP stays hidden


def test_engaged_by_is_reported(client):
    knight, foe = _start_with_knight(client)
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": knight["display_name"]}))
    t = ok(client.get("/api/table"))["combat"]["combatants"]
    k = next(c for c in t if c["side"] == "party")
    assert k["engaged_by"] == [foe["display_name"]]


def test_combat_rolls_are_never_secret(client):
    knight, foe = _start_with_knight(client)
    ok(client.post(f"/api/combat/{foe['id']}/roll", json={"what": "attack", "key": 0, "masked": True}))
    card = ok(client.get("/api/table"))["feed"][0]
    assert card["type"] == "roll.check" and "value" in card["data"]


def test_enemy_attack_on_knight(client):
    knight, foe = _start_with_knight(client)
    hp = knight["cur_hp"]
    for _ in range(30):                     # until the enemy's attack succeeds
        roll = ok(client.post(f"/api/combat/{foe['id']}/roll", json={"what": "attack", "key": 0}))["event"]
        if roll["data"]["outcome"] == "success":
            break
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": knight["id"], "knight": "failure"}))
    assert r["result"] == "foe" and r["blow"]["data"]["blow"]["shield_blocked"] == 0
    after = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == knight["id"])
    assert after["cur_hp"] == hp - r["blow"]["data"]["blow"]["wound"]
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": knight["id"], "knight": "higher"}))
    assert r["result"] == "knight" and r["blow"] is None and r["knight_shield"]
