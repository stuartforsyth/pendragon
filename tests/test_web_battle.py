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


# -- S7: the turn loop ------------------------------------------------------------

DECK = ["Pictish Knifemen", "Pictish Javeliniers", "Knights of Gorre", "Clash of Champions", "Rally the Division!"]


def _step(client, step, **kw):
    return ok(client.post("/api/battle/step", json={"step": step, **kw}))


def _running(client, size="clash", days=1, start=21, turns=None):
    pids = _party(client, "Sir Bors", "Sir Cai")
    _quick(client, size, days)
    if turns:
        for d in range(1, days + 1):
            ok(client.post("/api/battle/settings", json={"day": d, "patch": {"turns": turns}}))
    for d in range(1, days + 1):
        ok(client.post("/api/battle/deck", json={"day": d, "add": DECK}))
    _muster(client, pids, start=start)
    return pids


def _postures(client, pids, posture="valorous", amount=None):
    for p in pids:
        _step(client, "posture", knight=p, posture=posture, **({"amount": amount} if amount else {}))


def _cur(client):
    return _battle(client)["step"]["current"]


def test_turn_loop_without_fight(client):
    pids = _running(client)
    assert _cur(client) == "set"
    _step(client, "set", encounter="Pictish Knifemen")
    assert _cur(client) == "intensity"                       # turn 1: no charge roll (Q29)
    _step(client, "intensity", outcome="success")
    assert _cur(client) == "morale"
    _step(client, "morale", kind="loss", amount=3)
    _postures(client, pids)
    assert _cur(client) in ("end", "fight")
    _step(client, "end_turn")
    b = _battle(client)
    assert b["turn"] == 2 and b["morale"]["current"] == 18 and b["step"]["current"] == "set"


def test_turn1_skips_charge(client):
    _running(client)
    items = {i["key"]: i for i in _battle(client)["step"]["items"]}
    assert items["charge"]["state"] == "skipped" and "turn 1" in items["charge"]["reason"]


def test_step_out_of_order_409(client):
    _running(client)
    r = client.post("/api/battle/step", json={"step": "morale", "kind": "loss", "amount": 2})
    assert r.status_code == 409 and "Not now" in r.text


def test_draw_picks_a_deck_foe_not_opportunity(client):
    _running(client)
    ev = _step(client, "set", draw=True)["events"][0]
    assert ev["data"]["encounter"] in DECK[:3] and ev["data"]["drawn"]


def _to_morale(client, encounter):
    _step(client, "set", encounter=encounter)
    _step(client, "intensity", outcome="success")


def test_forced_retire_below_minimum(client):
    _running(client, start=10)
    _to_morale(client, "Knights of Gorre")                  # Minimum 13
    assert client.post("/api/battle/step", json={"step": "morale", "kind": "loss", "amount": 1}).status_code == 400
    _step(client, "morale", kind="forced_retire")
    assert _cur(client) == "rest"
    _step(client, "rest", amount=2)
    _step(client, "end_turn")
    b = _battle(client)
    assert b["status"] == "rear" and b["morale"]["current"] == 10


def test_morale_zero_only_retire(client):
    _running(client, start=5)
    ok(client.post("/api/battle/morale", json={"delta": -5, "reason": "rout"}))
    assert client.post("/api/battle/step", json={"step": "set", "encounter": "Pictish Knifemen"}).status_code == 409
    _step(client, "retire")
    assert _cur(client) == "rest"


def test_rest_capped_at_start(client):
    _running(client, start=20)
    ok(client.post("/api/battle/morale", json={"delta": -3, "reason": "arrows"}))
    _step(client, "retire")
    _step(client, "rest", amount=6)
    assert _battle(client)["morale"]["current"] == 20
    _step(client, "end_turn")
    _step(client, "rear", choice="return")
    assert _battle(client)["status"] == "turn" and _cur(client) == "set"


def test_opportunity_pick_needs_crit_and_is_once_per_battle(client):
    pids = _running(client, days=2, turns=2)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="failure")
    assert client.post("/api/battle/step", json={"step": "pick", "knight": pids[0], "encounter": "Clash of Champions", "crit": False}).status_code == 400
    _step(client, "pick", knight=pids[0], encounter="Clash of Champions", crit=True)
    _step(client, "pick", knight=pids[1], encounter="Pictish Javeliniers")
    assert client.post("/api/battle/step", json={"step": "select", "encounter": "Pictish Javeliniers"}).status_code == 400
    _step(client, "select", encounter="Clash of Champions")
    _step(client, "morale", kind="loss", amount=0)
    _postures(client, pids)
    _step(client, "end_turn")
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "charge", outcome="failure", engaged_last=True)
    _step(client, "intensity", outcome="failure")
    r = client.post("/api/battle/step", json={"step": "pick", "knight": pids[0], "encounter": "Clash of Champions", "crit": True})
    assert r.status_code == 400 and "already played" in r.text
    assert "Clash of Champions" in _battle(client)["spent_opportunities"]


def test_force_token_skips_intensity_and_picks_and_expires_at_day_end(client):
    pids = _party(client, "Sir Bors")
    _quick(client, "clash", 2)
    for d in (1, 2):
        ok(client.post("/api/battle/settings", json={"day": d, "patch": {"turns": 1}}))
        ok(client.post("/api/battle/deck", json={"day": d, "add": DECK}))
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "outcome": "success"}))
    _muster(client, pids)
    _step(client, "set", encounter="Knights of Gorre", forced=True)
    items = {i["key"]: i["state"] for i in _battle(client)["step"]["items"]}
    assert items["intensity"] == "skipped" and items["picks"] == "skipped" and _cur(client) == "morale"
    assert _battle(client)["tokens"]["force"] == "spent"
    _step(client, "morale", kind="loss", amount=2)
    _postures(client, pids)
    _step(client, "end_day")
    b = _battle(client)
    assert b["status"] == "mustering" and b["day"] == 2 and b["tokens"]["force"] == "none"


def test_negate_token_zeroes_loss_not_minimum(client):
    pids = _party(client, "Sir Bors")
    _quick(client, "clash")
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK}))
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "outcome": "fumble"}))
    _muster(client, pids, start=14)
    _to_morale(client, "Knights of Gorre")
    _step(client, "morale", kind="loss", negate=True)
    b = _battle(client)
    assert b["morale"]["current"] == 14 and b["tokens"]["negate"] == "spent"


def test_negate_cannot_bypass_minimum(client):
    pids = _party(client, "Sir Bors")
    _quick(client, "clash")
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK}))
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "outcome": "fumble"}))
    _muster(client, pids, start=10)
    _to_morale(client, "Knights of Gorre")
    assert client.post("/api/battle/step", json={"step": "morale", "kind": "loss", "negate": True}).status_code == 400


def test_posture_deltas_and_first_charge_limit(client):
    pids = _party(client, "Sir Bors", "Sir Cai")
    _quick(client, "clash")
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK}))
    ok(client.post("/api/battle/army-roll", json={"side": "friendly", "outcome": "success"}))
    _muster(client, pids, start=20)
    _to_morale(client, "Pictish Knifemen")
    _step(client, "morale", kind="loss", amount=5)
    assert client.post("/api/battle/step", json={"step": "posture", "knight": pids[0], "posture": "prudent", "amount": 2}).status_code == 400
    _step(client, "posture", knight=pids[0], posture="reckless", amount=3)
    _step(client, "posture", knight=pids[1], posture="valorous")
    assert _battle(client)["morale"]["current"] == 18


def test_duplicate_posture_409(client):
    pids = _running(client)
    _to_morale(client, "Pictish Knifemen")
    _step(client, "morale", kind="loss", amount=1)
    _step(client, "posture", knight=pids[0], posture="valorous")
    assert client.post("/api/battle/step", json={"step": "posture", "knight": pids[0], "posture": "valorous"}).status_code == 409


def test_cowardly_moves_knight_to_rear(client):
    pids = _running(client)
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"first_charge": False}}))
    _to_morale(client, "Pictish Knifemen")
    _step(client, "morale", kind="loss", amount=1)
    _step(client, "posture", knight=pids[0], posture="cowardly", above_half=True, amount=4)
    b = _battle(client)
    assert b["knights"][pids[0]]["position"] == "rear" and b["morale"]["current"] == 16


def test_cascade_undo_single_strike_event(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="success")
    _step(client, "morale", kind="loss", amount=3)
    prev = ok(client.get("/api/battle/undo-preview?step=intensity"))
    assert len(prev["targets"]) == 2 and not prev["locked"]
    strike = ok(client.post("/api/battle/undo", json={"step": "intensity"}))["event"]
    assert strike["type"] == "meta.strike" and len(strike["data"]["targets"]) == 2
    b = _battle(client)
    assert b["step"]["current"] == "intensity" and b["morale"]["current"] == 21
    ok(client.post(f"/api/battle/undo/{strike['id']}/restore"))
    assert _battle(client)["morale"]["current"] == 18


def test_undo_locked_before_resume(client):
    pids = _party(client, "Sir Bors")
    a = ok(client.post("/api/session/start", json={"title": "One"}))["session"]["id"]
    _quick(client)
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK}))
    _muster(client, pids)
    _step(client, "set", encounter="Pictish Knifemen")
    ok(client.post("/api/battle/pause"))
    bid = _battle(client)["id"]
    ok(client.post("/api/battle/resume", json={"battle_id": bid, "session_id": a}))
    r = client.post("/api/battle/undo", json={"step": "set"})
    assert r.status_code == 409


def test_single_strike_marks_inconsistent(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    iev = _step(client, "intensity", outcome="failure")["events"][0]
    _step(client, "pick", knight=pids[0], encounter="Pictish Javeliniers")
    ok(client.post(f"/api/events/{iev['id']}/strike"))
    b = _battle(client)
    assert b["step"]["current"] == "intensity" and [x["type"] for x in b["inconsistent"]] == ["battle.pick"]


def test_every_public_battle_event_has_table_text(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="failure")
    _step(client, "pick", knight=pids[0], encounter="Pictish Javeliniers")
    _step(client, "select", encounter="Pictish Javeliniers")
    _step(client, "morale", kind="loss", roll_for_me=True)
    _postures(client, pids)
    _step(client, "passion", knight=pids[0], used=True, name="Love (Family)")
    _step(client, "end_turn")
    events = ok(client.get("/api/session/events"))["events"]
    for e in events:
        if e["type"].startswith("battle.") and e.get("visibility") != "gm":
            assert e["data"].get("table_text"), e["type"]


def test_table_never_sees_min_loss_or_intensity_die(client):
    pids = _running(client)
    _step(client, "set", encounter="Knights of Gorre")
    _step(client, "intensity", roll_for_me=True)
    raw = client.get("/api/table").text
    assert "morale_minimum" not in raw and "Minimum" not in raw and "1D6+3" not in raw
    feed = ok(client.get("/api/table"))["feed"]
    inten = next(c for c in feed if c["type"] == "battle.intensity")
    assert "roll" not in inten["data"] and "rolled" not in inten["text"]
