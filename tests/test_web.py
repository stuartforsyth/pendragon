from tests.conftest import ok


def test_pages_and_health(client):
    assert client.get("/healthz").json()["ok"] is True
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


def test_knights_join_combat_without_health(client):
    ok(client.post("/api/party", json={"name": "Sir Bors", "player": "Ann"}))
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush"}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["players"] == 1
    knight = next(c for c in cs["combatants"] if c["side"] == "party")
    assert client.post(f"/api/combat/{knight['id']}/hp", json={"delta": -4}).status_code == 400
    assert client.post(f"/api/combat/{knight['id']}/status", json={"out": "dead"}).status_code == 400
    ok(client.post(f"/api/combat/{knight['id']}/status", json={"out": "unconscious"}))
    t = next(c for c in ok(client.get("/api/table"))["combat"]["combatants"] if c["side"] == "party")
    assert t["wound_state"] == "Down" and "cur_hp" not in t
    ok(client.post(f"/api/combat/{knight['id']}/status", json={"out": None}))
    ok(client.post("/api/combat/end"))
    assert "cur_hp" not in ok(client.get("/api/party"))["party"][0]
    assert ok(client.get("/api/table"))["mode"] == "chronicle"


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


def test_rules_search_show_overlay_and_hide(client):
    """A shown rule is an overlay on the Table (never a Fray card) until the GM
    takes it off, clears the Table or starts a session."""
    res = ok(client.get("/api/rules", params={"q": "major wound"}))["results"]
    assert res
    assert client.post("/api/rules/hide").status_code == 409
    ok(client.post(f"/api/rules/{res[0]['id']}/show"))
    t = ok(client.get("/api/table"))
    assert t["rule"]["rule_id"] == res[0]["id"] and t["rule"]["html"] and t["rule"]["title"]
    assert all(c["type"] != "rule.shown" for c in t["feed"])
    assert ok(client.get("/api/rules/shown"))["shown"]["rule_id"] == res[0]["id"]
    ok(client.post("/api/rules/hide"))
    assert ok(client.get("/api/table"))["rule"] is None
    assert ok(client.get("/api/rules/shown"))["shown"] is None
    ok(client.post(f"/api/rules/{res[0]['id']}/show"))
    ok(client.post("/api/table/clear"))
    assert ok(client.get("/api/table"))["rule"] is None
    ok(client.post(f"/api/rules/{res[0]['id']}/show"))
    ok(client.post("/api/session/start", json={"title": "Next"}))
    assert ok(client.get("/api/table"))["rule"] is None


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
    ok(client.post("/api/party", json={"name": "Sir Bors", "player": "Ann"}))
    ok(client.post("/api/combat/start", json={"encounter": "Bandit ambush"}))
    cs = ok(client.get("/api/combat"))["combat"]["combatants"]
    knight = next(c for c in cs if c["side"] == "party")
    foe = next(c for c in cs if c["side"] == "foe")
    return knight, foe


def test_blow_on_knight_is_reported_not_applied(client):
    knight, foe = _start_with_knight(client)
    ev = ok(client.post("/api/combat/blow", json={"attacker": foe["id"], "attack": 0,
                                                  "target": knight["id"], "critical": True}))["event"]
    b = ev["data"]["blow"]
    assert ev["data"]["to_knight"] and len(b["terms"]) == 2 and b["damage"] == b["full"]
    assert f"for {b['damage']} damage" in ev["text"] and "armour only" in ev["text"]
    assert "slain" not in ev["text"].lower() and "Hit Points" not in ev["text"]
    after = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == knight["id"])
    assert after["status"] == "active"
    card = ok(client.get("/api/table"))["feed"][0]
    assert card["type"] == "combat.blow" and card["data"]["to_knight"]


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
    for _ in range(50):                     # until the enemy's attack succeeds
        roll = ok(client.post(f"/api/combat/{foe['id']}/roll", json={"what": "attack", "key": 0}))["event"]
        if roll["data"]["outcome"] == "success":
            break
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": knight["id"], "knight": "failure"}))
    assert r["result"] == "foe" and r["blow"]["data"]["to_knight"]
    assert "armour only" in r["blow"]["text"] and "slain" not in r["blow"]["text"].lower()
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": knight["id"], "knight": "lower"}))
    assert r["result"] == "foe" and "shield/parry apply" in r["blow"]["text"]
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": knight["id"], "knight": "higher"}))
    assert r["result"] == "knight" and r["blow"] is None and r["knight_shield"]


def test_enemy_failed_attack_wording(client):
    knight, foe = _start_with_knight(client)
    for _ in range(80):
        roll = ok(client.post(f"/api/combat/{foe['id']}/roll", json={"what": "attack", "key": 0}))["event"]
        if roll["data"]["outcome"] == "failure":
            break
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": knight["id"], "knight": "higher"}))
    assert r["result"] == "knight" and not r["knight_shield"]
    assert "(higher roll)" not in r["event"]["text"]


def test_start_combat_with_a_single_adversary(client):
    ok(client.post("/api/combat/start", json={"adversary": "Bandit"}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["name"] == "Bandit" and [c["type"] for c in cs["combatants"]] == ["Bandit"]
    assert client.post("/api/combat/start", json={"adversary": "Nobody"}).status_code == 400


def test_fight_a_cast_npc(client):
    npc = ok(client.post("/api/npc/generate", json={"culture": "Saxon", "gender": "Male",
                                                    "social_class": "Knight"}))["npc"]
    entry = ok(client.post("/api/cast", json={"npc": npc}))["entry"]
    listed = ok(client.get("/api/cast/fightable"))["npcs"]
    assert listed[0]["cast_id"] == entry["id"] and listed[0]["kind"] == "npc"
    adv = ok(client.get(f"/api/cast/{entry['id']}/adversary"))["adversary"]
    assert adv["name"] == npc["full"] and adv["health"]["hit_points"] == npc["derived"]["Hit Points"]
    ok(client.post("/api/combat/start", json={"cast": entry["id"]}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["name"] == npc["full"] and cs["combatants"][0]["npc"]
    ok(client.post("/api/combat/add", json={"cast": entry["id"]}))
    names = [c["display_name"] for c in ok(client.get("/api/combat"))["combat"]["combatants"]]
    assert len(names) == 2 and len(set(names)) == 2
    t = ok(client.get("/api/table"))["combat"]["combatants"]
    assert t[0]["npc"] and "cur_hp" not in t[0]


def test_clear_table_and_session_start(client):
    ok(client.post("/api/roll/dice", json={"expr": "d20"}))
    assert ok(client.get("/api/table"))["feed"]
    ev = ok(client.post("/api/table/clear"))["event"]
    assert ok(client.get("/api/table"))["feed"] == []
    assert any(e["type"] == "roll.dice" for e in ok(client.get("/api/session"))["events"])  # log keeps it
    ok(client.post("/api/narrate", json={"text": "After the clear"}))
    assert [c["type"] for c in ok(client.get("/api/table"))["feed"]] == ["narrate"]
    ok(client.post(f"/api/events/{ev['id']}/strike"))                 # undo the clear
    assert len(ok(client.get("/api/table"))["feed"]) == 2
    ok(client.post("/api/session/start", json={"title": "Fresh"}))
    assert ok(client.get("/api/table"))["feed"] == []


def test_flags_targets_list():
    from web.sessions import flags
    evs = [{"id": 1, "type": "x"}, {"id": 2, "type": "y"},
           {"id": 3, "type": "meta.strike", "data": {"targets": [1, 2]}},
           {"id": 4, "type": "meta.unstrike", "data": {"targets": [2]}},
           {"id": 5, "type": "meta.strike", "data": {"target": 2}}]
    f = flags(evs)
    assert f[1]["struck"] and f[2]["struck"]
    assert not flags(evs[:4])[2]["struck"]
