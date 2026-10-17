"""The battle container (S6): saved battles, launch, mustering, army rolls,
Intensity, Morale overrides, live settings, pause and resume."""

import json

from tests.conftest import ok


def _party(client, *names):
    return [ok(client.post("/api/party", json={"name": n, "player": "P"}))["member"]["id"] for n in names]


def _battle(client):
    return ok(client.get("/api/battle"))["battle"]


def _quick(client, size="clash", days=1, **kw):
    return ok(client.post("/api/battle/start", json={"quick": {"size": size, "days": days, **kw}}))["event"]


def _muster(client, pids, start=21, commander=None, intensity=12):
    if intensity is not None:
        ok(client.post("/api/battle/day", json={"intensity": intensity}))
    return ok(client.post("/api/battle/muster", json={"start": start, "commander": commander or pids[0], "knights": pids}))


def _saved(client, name="Bedegraine", size="huge", days=2):
    b = ok(client.get(f"/api/battles/blank?size={size}"))["battle"]
    b["name"] = name
    b["days"] = [dict(b["days"][0], intensity={"mode": "fixed", "value": 14 + 4 * i}, turns=5) for i in range(days)]
    return ok(client.put("/api/battles", json={"battle": b}))


def test_battles_crud_writes_working_copy(client):
    data = client.tmp / "data"
    before = (data / "examplecombat.json").read_bytes()
    _saved(client)
    assert [b["key"] for b in ok(client.get("/api/battles"))["battles"]] == ["Bedegraine"]
    b = ok(client.get("/api/battles/Bedegraine"))["battle"]
    assert client.put("/api/battles", json={"battle": b}).status_code == 409
    assert "Bedegraine" in json.loads((data / "combat.json").read_text())["battles"]
    ok(client.delete("/api/battles/Bedegraine"))
    assert client.get("/api/battles/Bedegraine").status_code == 404
    assert (data / "examplecombat.json").read_bytes() == before


def test_quick_battle_start_carries_full_definition(client):
    _party(client, "Sir Bors")
    ev = _quick(client, "large", 2)
    d = ev["data"]["definition"]
    assert len(d["days"]) == 2 and d["days"][0]["turns"] == 8 and d["days"][0]["intensity"] == {"mode": "roll"}
    assert _battle(client)["status"] == "mustering"
    assert client.post("/api/battle/start", json={"quick": {"size": "clash"}}).status_code == 409


def test_live_settings_never_touch_template(client):
    _saved(client)
    ok(client.post("/api/battle/start", json={"key": "Bedegraine"}))
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"turns": 7}}))
    assert _battle(client)["definition"]["days"][0]["turns"] == 7
    assert ok(client.get("/api/battles/Bedegraine"))["battle"]["days"][0]["turns"] == 5


def test_past_day_settings_rejected(client):
    _saved(client)
    ok(client.post("/api/battle/start", json={"key": "Bedegraine"}))
    assert client.post("/api/battle/settings", json={"day": 0, "patch": {"turns": 3}}).status_code in (404, 409)
    ok(client.post("/api/battle/settings", json={"add_day": {"turns": 4}}))
    assert len(_battle(client)["definition"]["days"]) == 3


def test_muster_requires_commander_morale_intensity(client):
    pids = _party(client, "Sir Bors")
    _quick(client)
    assert client.post("/api/battle/muster", json={"start": 20, "commander": pids[0], "knights": pids}).status_code == 409
    ok(client.post("/api/battle/day", json={"intensity": 12}))
    assert client.post("/api/battle/muster", json={"start": 20, "commander": "nobody", "knights": pids}).status_code == 400
    assert client.post("/api/battle/muster", json={"start": 0, "commander": pids[0], "knights": pids}).status_code == 400


def test_muster_sets_status_turn_and_morale(client):
    pids = _party(client, "Sir Bors", "Sir Cai")
    _quick(client)
    _muster(client, pids, start=21)
    b = _battle(client)
    assert b["status"] == "turn" and b["turn"] == 1 and b["morale"]["current"] == 21 and b["band"] == "Steady"
    assert b["commander_name"] == "Sir Bors" and b["intensity_today"] == 12


def test_fixed_intensity_needs_no_entry(client):
    pids = _party(client, "Sir Bors")
    _saved(client)
    ok(client.post("/api/battle/start", json={"key": "Bedegraine"}))
    _muster(client, pids, intensity=None)
    assert _battle(client)["intensity_today"] == 14


def test_army_rolls_only_clash_and_up_and_tokens(client):
    pids = _party(client, "Sir Bors")
    _quick(client, "skirmish")
    assert client.post("/api/battle/army-roll", json={"side": "friendly", "outcome": "success"}).status_code == 400
    ok(client.post("/api/battle/pause"))
    _quick(client, "clash")
    ok(client.post("/api/battle/army-roll", json={"side": "friendly", "outcome": "failure"}))
    ok(client.post("/api/battle/army-roll", json={"side": "friendly", "outcome": "success"}))   # latest wins
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "outcome": "success"}))
    b = _battle(client)
    assert b["first_charge"] is True and b["tokens"]["force"] == "available" and b["tokens"]["negate"] == "none"
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "outcome": "fumble"}))
    assert _battle(client)["tokens"] == {"force": "none", "negate": "available"}
    r = ok(client.post("/api/battle/army-roll", json={"side": "friendly", "roll_for_me": {"mods": 5}}))
    assert r["event"]["data"]["roll"]["value_rolled"] is True


def test_preset_army_roll_recorded_at_muster(client):
    pids = _party(client, "Sir Bors")
    b = ok(client.get("/api/battles/blank?size=large"))["battle"]
    b["name"] = "Carlion"
    b["days"][0]["commanders"] = {"friendly": "success", "enemy": "failure"}
    ok(client.put("/api/battles", json={"battle": b}))
    ok(client.post("/api/battle/start", json={"key": "Carlion"}))
    _muster(client, pids)
    assert _battle(client)["army"]["1"] == {"friendly": "success", "enemy": "failure"}


def test_day_intensity_roll_for_me_in_range(client):
    _party(client, "Sir Bors")
    _quick(client, "large")
    for _ in range(10):
        v = ok(client.post("/api/battle/day", json={"roll_for_me": True}))["event"]["data"]["intensity"]
        assert 3 <= v <= 18


def test_morale_adjust_capped_and_start_edit(client):
    pids = _party(client, "Sir Bors")
    _quick(client)
    _muster(client, pids, start=20)
    ok(client.post("/api/battle/morale", json={"delta": -5, "reason": "ambush"}))
    ok(client.post("/api/battle/morale", json={"delta": 9, "reason": "rallying cry"}))
    m = _battle(client)["morale"]
    assert m["current"] == 20 and m["last"] == {"delta": 5, "reason": "rallying cry"}
    ok(client.post("/api/battle/morale", json={"start": 15, "reason": "fewer knights"}))
    assert _battle(client)["morale"] == {"start": 15, "current": 15, "last": m["last"]}
    assert client.post("/api/battle/morale", json={"delta": 2, "reason": ""}).status_code == 400


def test_pause_on_session_end_and_resume_in_new_session(client):
    pids = _party(client, "Sir Bors")
    a = ok(client.post("/api/session/start", json={"title": "Night one"}))["session"]["id"]
    _quick(client, "clash", 2, name="Ford")
    _muster(client, pids, start=18)
    ok(client.post("/api/battle/morale", json={"delta": -4, "reason": "arrows"}))
    final = _battle(client)
    ok(client.post("/api/session/end"))
    events = json.loads((client.tmp / "sessions" / f"{a}.json").read_text())["events"]
    assert any(e["type"] == "battle.paused" for e in events)
    ok(client.post("/api/session/start", json={"title": "Night two"}))
    paused = ok(client.get("/api/battle/paused"))["paused"]
    assert [(p["name"], p["morale"]) for p in paused] == [("Ford", [14, 18])]
    ok(client.post("/api/battle/resume", json={"battle_id": paused[0]["battle_id"], "session_id": a}))
    b = _battle(client)
    assert b["status"] == "turn" and b["morale"] == final["morale"] and b["id"] == final["id"]
    assert ok(client.get("/api/battle/paused"))["paused"] == []


def test_template_saves_live_definition(client):
    _party(client, "Sir Bors")
    _quick(client, "skirmish", 1, name="Improvised")
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"turns": 2}}))
    ok(client.post("/api/battle/template", json={"name": "Ford ambush"}))
    t = ok(client.get("/api/battles/Ford ambush"))["battle"]
    assert t["days"][0]["turns"] == 2 and t["source"] == "user"


def test_quick_encounter_saves_and_adds_to_deck(client):
    _party(client, "Sir Bors")
    _quick(client)
    enc = {"name": "Saxon outriders", "battle_role": "foe", "morale_minimum": 8, "morale_loss": "1D6",
           "roster": [{"adversary": "Saxon Warriors", "count": 1, "per_player": True}]}
    ok(client.post("/api/battle/quick-encounter", json={"definition": enc}))
    assert "Saxon outriders" in _battle(client)["definition"]["days"][0]["deck"]["foes"]
    assert ok(client.get("/api/encounters/Saxon outriders"))["encounter"]["battle_role"] == "foe"


def test_table_battle_mode_and_gauge(client):
    pids = _party(client, "Sir Bors")
    _quick(client, name="Ford")
    _muster(client, pids, start=20)
    ok(client.post("/api/battle/morale", json={"delta": -16, "reason": "rout"}))
    t = ok(client.get("/api/table"))
    assert t["mode"] == "battle" and t["battle"]["morale"]["band"] == "Breaking" and t["battle"]["intensity"] == 12


def test_table_never_sees_army_die_or_definition(client):
    pids = _party(client, "Sir Bors")
    b = ok(client.get("/api/battles/blank?size=clash"))["battle"]
    b["name"] = "Secret plan"
    b["days"][0]["scripts"] = [{"turn": 2, "text": "Lot's cavalry crests the hill", "if_intensity": True}]
    b["days"][0]["deck"] = {"foes": ["Knights of Gorre"], "opportunities": []}
    ok(client.put("/api/battles", json={"battle": b}))
    ok(client.post("/api/battle/start", json={"key": "Secret plan"}))
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "roll_for_me": {"battle": 15, "mods": 2}}))
    _muster(client, pids)
    raw = client.get("/api/table").text
    for secret in ("value_rolled", '"mods"', "crests the hill", "morale_minimum", "Knights of Gorre"):
        assert secret not in raw, secret


def test_settings_and_pause_events_gm_only(client):
    _party(client, "Sir Bors")
    _quick(client)
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"turns": 4}}))
    ok(client.post("/api/battle/pause"))
    types = [c["type"] for c in ok(client.get("/api/table"))["feed"]]
    assert "battle.settings" not in types and "battle.paused" not in types
