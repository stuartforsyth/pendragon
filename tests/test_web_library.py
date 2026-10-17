from tests.conftest import ok


def test_resave_keeps_dice_characteristics(client):
    adv = ok(client.get("/api/adversaries/Bandit"))["adversary"]
    assert isinstance(adv["characteristics"]["APP"], str)
    saved = ok(client.put("/api/adversaries", json={"adversary": adv, "original": "Bandit"}))
    assert saved["adversary"]["characteristics"]["APP"] == adv["characteristics"]["APP"].upper()
    assert saved["adversary"]["armour"]["pieces"] == ["Gambeson"]


def test_rename_and_overwrite_guard(client):
    adv = ok(client.get("/api/adversaries/Bandit"))["adversary"]
    adv["name"] = "Bowman"
    assert client.put("/api/adversaries", json={"adversary": adv, "original": "Bandit"}).status_code == 409
    ok(client.put("/api/adversaries", json={"adversary": adv, "original": "Bandit", "overwrite": True}))
    keys = [a["key"] for a in ok(client.get("/api/adversaries"))["adversaries"]]
    assert "Bandit" not in keys and "Bowman" in keys


def test_creature_keeps_printed_stats(client):
    blank = ok(client.get("/api/adversaries/blank?category=monster"))["adversary"]
    blank.update(name="Test Wyrm", health={"hit_points": 120, "major_wound": 40, "knockdown": 60, "unconscious": 30},
                 other={"movement": 65, "armor_points": 15, "shield": 0, "glory": 1000, "healing_rate": 8})
    a = ok(client.put("/api/adversaries", json={"adversary": blank}))["adversary"]
    assert a["health"]["hit_points"] == 120 and a["other"]["movement"] == 65


def test_editor_helpers(client):
    c = ok(client.post("/api/adversaries/compute", json={
        "characteristics": {"SIZ": 15, "DEX": 12, "STR": 14, "CON": 13, "APP": 10},
        "armour": {"pieces": ["Hauberk"], "helmet": "", "shield": ""}}))
    assert c["derived"]["Hit Points"] == 28 and c["armor_points"] == 6
    w = ok(client.post("/api/adversaries/weapon", json={"weapon": "Sword",
                                                        "characteristics": {"SIZ": 15, "STR": 14}}))
    assert w["attack"]["skill"] == "Sword" and w["attack"]["damage"].endswith("D6")
    t = ok(client.post("/api/adversaries/stat-value", json={"kind": "trait", "name": "Valorous (Cowardly)",
                                                             "current": {"Cowardly": 6}}))
    assert (t["name"], t["value"]) == ("Valorous", 14)
    assert client.post("/api/adversaries/stat-value", json={"kind": "skill", "name": "Sword",
                                                            "current": {"Sword": 3}}).status_code == 400
    b = ok(client.post("/api/adversaries/balance-traits", json={
        "traits": {"Valorous": 16, "Cowardly": 6}, "before": {"Valorous": 14, "Cowardly": 6}}))
    assert b["traits"] == {"Valorous": 16, "Cowardly": 4}
    auto = ok(client.post("/api/adversaries/auto", json={"culture": "Saxon", "gender": "Male"}))
    assert auto["draft"]["characteristics"]["SIZ"] > 0


def test_encounter_leader_preview_and_launch_definition(client):
    enc = {"name": "Ambush at the ford", "tags": "river, saxon",
           "roster": [{"adversary": "Bandit", "count": "0.5", "per_player": True}],
           "leader": {"adversary": "Bowman", "promote": True}}
    p = ok(client.post("/api/encounters/preview", json={"encounter": enc, "players": 4}))
    assert p["total"] == 3 and p["lines"][-1].startswith("1× Bowman")
    saved = ok(client.put("/api/encounters", json={"encounter": enc}))["encounter"]
    assert saved["tags"] == ["river", "saxon"]
    ok(client.post("/api/combat/start", json={"definition": saved, "name": saved["name"], "players": 4}))
    combat = ok(client.get("/api/combat"))["combat"]
    assert combat["name"] == "Ambush at the ford" and len(combat["combatants"]) == 3
    ok(client.delete("/api/encounters/Ambush at the ford"))
    assert client.get("/api/encounters/Ambush at the ford").status_code == 404
