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
    assert "Bedegraine" in [b["key"] for b in ok(client.get("/api/battles"))["battles"]]
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
    for secret in ("value_rolled", '"mods"', "crests the hill", "morale_minimum", "1D6+3"):
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
    _step(client, "opportunity_done")
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
    assert "morale_minimum" not in raw and "morale_loss" not in raw and "1D6+3" not in raw
    feed = ok(client.get("/api/table"))["feed"]
    inten = next(c for c in feed if c["type"] == "battle.intensity")
    assert "roll" not in inten["data"] and "rolled" not in inten["text"]


# -- S8: the linked fight --------------------------------------------------------

def _to_fight(client, pids, encounter, intensity="success", postures=None, turn1=True):
    _step(client, "set", encounter=encounter)
    if not turn1:
        _step(client, "charge", outcome="failure", engaged_last=True)
    _step(client, "intensity", outcome=intensity)
    _step(client, "morale", kind="loss", amount=1)
    for p, pos in zip(pids, postures or ["valorous"] * len(pids)):
        _step(client, "posture", knight=p, posture=pos, **({"amount": 1} if pos in ("reckless", "prudent") else {}),
              **({"above_half": False} if pos == "cowardly" else {}))


def _no_first_charge(client):
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"first_charge": False}}))


def _three(client, start=21, turns=None):
    pids = _party(client, "Sir Bors", "Sir Cai", "Sir Kay")
    _quick(client, "clash")
    _no_first_charge(client)
    if turns:
        ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"turns": turns}}))
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK + ["Knights of Lothian", "Cambrian Archers", "Irish Kerns"]}))
    _muster(client, pids, start=start)
    return pids


def _foes(client):
    return [c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["side"] != "party"]


def test_fight_scaled_to_conroi_knights(client):
    pids = _three(client)
    _to_fight(client, pids, "Knights of Lothian")
    ok(client.post("/api/battle/fight"))
    assert len(_foes(client)) == 5                         # 1.5 × 3, half up
    ok(client.post("/api/combat/end"))
    _step(client, "end_turn")
    _to_fight(client, pids, "Knights of Lothian", postures=["valorous", "valorous", "cowardly"], turn1=False)
    _step(client, "countercharge", roll=4)
    ok(client.post("/api/battle/fight"))
    assert len(_foes(client)) == 3                         # the Cowardly knight doesn't count


def test_intensity_crit_doubles_resolved_count(client):
    pids = _three(client)
    _to_fight(client, pids, "Knights of Lothian", intensity="critical")
    ok(client.post("/api/battle/fight"))
    cs = ok(client.get("/api/combat"))["combat"]
    assert len(_foes(client)) == 10 and cs["battle"]["doubled"]


def test_knight_snapshots_carry_pill_posture_rounds(client):
    pids = _three(client)
    ok(client.post(f"/api/battle/knight/{pids[2]}", json={"mounted": False}))
    _to_fight(client, pids, "Pictish Knifemen", postures=["reckless", "valorous", "prudent"])
    ok(client.post("/api/battle/fight"))
    ks = {c["party_id"]: c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["side"] == "party"}
    assert (ks[pids[0]]["posture"], ks[pids[0]]["rounds"]) == ("reckless", 3)
    assert ks[pids[2]]["mounted"] is False and ks[pids[2]]["rounds"] == 1


def test_countercharge_auto_first_turn_and_roll_later(client):
    pids = _three(client, turns=3)
    _to_fight(client, pids, "Knights of Gorre")
    ok(client.post("/api/battle/fight"))
    assert any(e["type"] == "battle.countercharge" for e in ok(client.get("/api/session/events"))["events"])
    ok(client.post("/api/combat/end"))
    _step(client, "end_turn")
    _to_fight(client, pids, "Knights of Gorre", turn1=False)
    assert client.post("/api/battle/fight").status_code == 409            # check the countercharge first
    _step(client, "countercharge", roll=5)
    assert _battle(client)["t"]["countercharge"]["yes"] is False
    ok(client.post("/api/battle/fight"))


def test_barrage_required_for_missile_card_and_reach_lines(client):
    pids = _three(client)
    _to_fight(client, pids, "Cambrian Archers", postures=["reckless", "valorous", "prudent"])
    assert client.post("/api/battle/fight").status_code == 409
    ev = _step(client, "barrage", outcome="failure")["events"][0]
    assert ev["data"]["rounds"] == 2
    assert "reaches the archers" in ev["data"]["lines"][0] and "turns back" in ev["data"]["lines"][1]
    ok(client.post("/api/battle/fight"))


def test_end_turn_applies_kv_gain_half_up(client):
    pids = _three(client, start=21)
    _to_fight(client, pids, "Irish Kerns")
    ok(client.post("/api/battle/fight"))
    kerns = _foes(client)
    for c in kerns[:4]:                                     # 4 × KV ⅛ = ½ → +1
        ok(client.post(f"/api/combat/{c['id']}/status", json={"out": "dead"}))
    assert client.post("/api/battle/step", json={"step": "end_turn"}).status_code == 409   # end the fight first
    ok(client.post("/api/combat/end"))
    assert _battle(client)["kv_gain"] == 1
    _step(client, "end_turn")
    assert _battle(client)["morale"]["current"] == 21      # 21 − 1 + 1, capped at 21


def test_fought_days_and_cowardly_excluded(client):
    pids = _three(client)
    _to_fight(client, pids, "Pictish Knifemen", postures=["valorous", "valorous", "cowardly"])
    ok(client.post("/api/battle/fight"))
    ok(client.post("/api/combat/end"))
    _step(client, "end_turn")
    fd = _battle(client)["fought_days"]
    assert fd.get(pids[0]) == [1] and pids[2] not in fd


def test_cascade_undo_strikes_linked_fight_and_its_glory(client):
    pids = _three(client)
    _to_fight(client, pids, "Pictish Knifemen")
    ok(client.post("/api/battle/fight"))
    foe = _foes(client)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{foe['id']}/status", json={"out": "dead"}))
    ok(client.post("/api/combat/end"))
    assert _battle(client)["glory_battle"][pids[0]] == 5
    prev = ok(client.get("/api/battle/undo-preview?step=postures"))["targets"]
    assert {"combat.started", "combat.status", "combat.ended"} <= {t["type"] for t in prev}
    ok(client.post("/api/battle/undo", json={"step": "postures"}))
    b = _battle(client)
    assert b["step"]["current"] == "postures" and b["glory_battle"].get(pids[0], 0) == 0
    assert not (ok(client.get("/api/combat"))["combat"] or {}).get("active")


def test_resume_mid_fight_restores_combat_and_glory_once(client):
    pids = _party(client, "Sir Bors", "Sir Cai")
    a = ok(client.post("/api/session/start", json={"title": "One"}))["session"]["id"]
    _quick(client, "clash")
    _no_first_charge(client)
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK}))
    _muster(client, pids)
    _to_fight(client, pids, "Pictish Knifemen")
    ok(client.post("/api/battle/fight"))
    foe = _foes(client)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{foe['id']}/hp", json={"delta": -3}))
    ok(client.post(f"/api/combat/{foe['id']}/status", json={"out": "dead"}))
    before = _battle(client)["glory_battle"]
    ok(client.post("/api/session/end"))
    ok(client.post("/api/session/start", json={"title": "Two"}))
    p = ok(client.get("/api/battle/paused"))["paused"][0]
    ok(client.post("/api/battle/resume", json={"battle_id": p["battle_id"], "session_id": a}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["active"] and next(c for c in cs["combatants"] if c["id"] == foe["id"])["status"] == "dead"
    assert _battle(client)["glory_battle"] == before


def test_alone_knight_gets_lane_not_scaling(client):
    pids = _three(client)
    ok(client.post(f"/api/battle/knight/{pids[2]}", json={"position": "alone"}))
    _to_fight(client, pids[:2], "Knights of Lothian")
    ok(client.post("/api/battle/fight"))
    cs = ok(client.get("/api/combat"))["combat"]
    assert len(_foes(client)) == 3                           # 1.5 × 2 knights with the conroi
    assert any(c.get("party_id") == pids[2] and c.get("position") == "alone" for c in cs["combatants"])


def test_table_fight_view_battle_header_has_no_numbers(client):
    pids = _three(client)
    _to_fight(client, pids, "Knights of Gorre")
    ok(client.post("/api/battle/fight"))
    t = ok(client.get("/api/table"))
    assert t["mode"] == "combat" and t["combat"]["battle"]["id"] == t["battle"]["id"]
    raw = client.get("/api/table").text
    for secret in ("morale_minimum", "cur_hp", "knight_value", "kvs"):
        assert secret not in raw, secret
    card = t["knights"][0]
    assert card["glory"]["scope"] == "battle" and any(e["key"] == "posture" for e in card["effects"])


# -- S9: the players' battle view ----------------------------------------------------

def _tb(client):
    return ok(client.get("/api/table"))


def test_table_battle_view_cards_and_deck_names_only(client):
    pids = _running(client)
    _step(client, "set", encounter="Knights of Gorre", flavour="stern northerners on chargers")
    t = _tb(client)
    assert t["battle"]["this_turn"]["set"] == {"name": "Knights of Gorre", "flavour": "stern northerners on chargers", "opportunity": False, "minimum": 13}
    for c in t["battle"]["deck"]["foes"] + t["battle"]["deck"]["opportunities"]:
        assert set(c) <= {"name", "in_play", "spent"}
    # the battlefield the players choose from: name, flavour, the Morale needed, playable
    for c in t["battle"]["options"]:
        assert set(c) == {"name", "flavour", "opportunity", "minimum", "playable", "spent", "in_play"}
    raw = client.get("/api/table").text
    for secret in ("morale_minimum", "morale_loss", '"kv', "has_roster", "definition", "mounted_charge"):
        assert secret not in raw, secret


def test_table_options_follow_the_route(client):
    """Before Intensity: the whole deck. Success: the set card alone. Fumble:
    the set card or an unplayed Opportunity. Failure: everything. Each card
    says the Morale it needs; below it, the card is not playable."""
    pids = _running(client, start=12)                     # Morale 12: Gorre (13) out of reach, Knifemen (5) fine
    opts = lambda: {c["name"]: c for c in _tb(client)["battle"]["options"]}
    o = opts()
    assert "Knights of Gorre" in o and "Pictish Knifemen" in o and "Clash of Champions" in o
    assert o["Knights of Gorre"]["minimum"] == 13 and not o["Knights of Gorre"]["playable"]
    assert o["Pictish Knifemen"]["playable"] and o["Clash of Champions"]["opportunity"]
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="success")
    assert list(opts()) == ["Pictish Knifemen"]
    _step(client, "morale", kind="loss", amount=1)
    _postures(client, pids)
    _step(client, "end_turn")
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "charge", outcome="failure")
    _step(client, "intensity", outcome="fumble")
    names = list(opts())
    assert names[0] == "Pictish Knifemen" and all(opts()[n]["opportunity"] for n in names[1:]) and "Knights of Gorre" not in names
    _step(client, "select", via="fumble")                # keeps the Knifemen
    assert list(opts()) == ["Pictish Knifemen"]


def test_table_shows_the_commanders_chosen_opportunity(client):
    _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="fumble")
    _step(client, "select", encounter="Clash of Champions", via="fumble")
    tt = _tb(client)["battle"]["this_turn"]
    assert tt["selected_card"]["name"] == "Clash of Champions" and tt["selected_card"]["opportunity"]


def test_spent_opportunity_flag_on_table(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="failure")
    _step(client, "pick", knight=pids[0], encounter="Clash of Champions", crit=True)
    _step(client, "select", encounter="Clash of Champions")
    opp = next(c for c in _tb(client)["battle"]["deck"]["opportunities"] if c["name"] == "Clash of Champions")
    assert opp["spent"] and opp["in_play"]


def test_picks_carry_knight_names_and_crit(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="failure")
    _step(client, "pick", knight=pids[1], encounter="Clash of Champions", crit=True)
    pk = _tb(client)["battle"]["this_turn"]["picks"][0]
    assert pk["knight_name"] == "Sir Cai" and pk["crit"] and pk["opportunity"]
    assert _tb(client)["battle"]["banner"]["text"].startswith("Intensity fails")


def _scripted(client, if_intensity):
    pids = _party(client, "Sir Bors")
    b = ok(client.get("/api/battles/blank?size=clash"))["battle"]
    b["name"] = "Scripted"
    b["days"][0]["deck"] = {"foes": ["Pictish Knifemen"], "opportunities": []}
    b["days"][0]["scripts"] = [{"turn": 1, "text": "The wolves howl in the wood", "if_intensity": if_intensity}]
    ok(client.put("/api/battles", json={"battle": b}))
    ok(client.post("/api/battle/start", json={"key": "Scripted"}))
    _muster(client, pids)
    return pids


def test_if_intensity_script_revealed_only_after_success(client):
    _scripted(client, True)
    _step(client, "set", encounter="Pictish Knifemen")
    assert "wolves" not in client.get("/api/table").text
    _step(client, "intensity", outcome="success")
    assert "wolves" in client.get("/api/table").text
    ok(client.post("/api/battle/undo", json={"step": "intensity"}))
    _step(client, "intensity", outcome="failure")
    assert "wolves" not in client.get("/api/table").text


def test_unconditional_script_only_after_show(client):
    _scripted(client, False)
    assert "wolves" not in client.get("/api/table").text
    ok(client.post("/api/battle/script", json={"day": 1, "index": 0}))
    assert "wolves" in client.get("/api/table").text


def test_knight_chips_from_battle_state(client):
    pids = _running(client)
    _step(client, "passion", knight=pids[0], used=True, name="Love (Family)")
    ok(client.post(f"/api/battle/knight/{pids[1]}", json={"position": "rear"}))
    cards = {k["pid"]: k for k in _tb(client)["battle_knights"]}
    labels0 = [e["label"] for e in cards[pids[0]]["effects"]]
    assert "Commander" in labels0 and "Passion: Love (Family)" in labels0
    assert "At the rear" in [e["label"] for e in cards[pids[1]]["effects"]]


def test_last_line_from_battle_events(client):
    pids = _running(client)
    _step(client, "passion", knight=pids[0], used=True, name="Honor")
    card = next(k for k in _tb(client)["battle_knights"] if k["pid"] == pids[0])
    assert card["happened"][0] == "Sir Bors draws on Honor"


def test_banner_follows_latest_step(client):
    pids = _running(client, start=10)
    _step(client, "set", encounter="Knights of Gorre")
    _step(client, "intensity", outcome="success")
    assert _tb(client)["battle"]["banner"]["text"] == "The Encounter stands"
    _step(client, "morale", kind="forced_retire")
    assert _tb(client)["battle"]["banner"]["text"] == "Not enough Morale — Retire to the Rear"


# -- S10: aftermath and finale ----------------------------------------------------------

def _one_turn_battle(client, size="clash", encounter="Knights of Gorre"):
    pids = _party(client, "Sir Bors", "Sir Cai")
    _quick(client, size)
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"turns": 1, "first_charge": False}}))
    ok(client.post("/api/battle/deck", json={"day": 1, "add": DECK}))
    _muster(client, pids)
    _to_fight(client, pids, encounter)
    ok(client.post("/api/battle/fight"))
    return pids


def _aftermath(client):
    ok(client.post("/api/combat/end"))
    _step(client, "end_day")
    b = _battle(client)
    assert b["status"] == "aftermath"
    return b["aftermath"]


def test_aftermath_enemy_kv_dead_plus_captured_only(client):
    pids = _one_turn_battle(client)
    gorre = _foes(client)
    ok(client.post(f"/api/combat/{gorre[0]['id']}/status", json={"out": "dead"}))
    ok(client.post(f"/api/combat/{gorre[1]['id']}/status", json={"out": "fled"}))
    ok(client.post(f"/api/combat/{gorre[0]['id']}/credit", json={"knight": pids[0]}))
    a = _aftermath(client)
    assert a["enemy_kv"] == "1"                              # the fled knight doesn't count


def test_aftermath_captured_counts(client):
    pids = _one_turn_battle(client)
    g = _foes(client)[0]
    ok(client.post(f"/api/combat/{g['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{g['id']}/status", json={"out": "surrendered"}))
    ok(client.post(f"/api/combat/{g['id']}/captured", json={}))
    a = _aftermath(client)
    assert a["enemy_kv"] == "1" and a["captives"][0]["captor_name"] == "Sir Bors"


def test_aftermath_outcome_computed_and_small_plus_choice(client):
    _one_turn_battle(client)
    for g in _foes(client)[:2]:
        ok(client.post(f"/api/combat/{g['id']}/status", json={"out": "dead"}))
    _aftermath(client)
    a = ok(client.post("/api/battle/aftermath", json={"patch": {"friendly_pk_losses": 1}}))["aftermath"]
    assert a["outcome"] == "victory" and a["ratio"] == 2.0
    a = ok(client.post("/api/battle/aftermath", json={"patch": {"outnumber": "we"}}))["aftermath"]
    assert a["outcome"] == "decisive_victory"


def test_zero_friendly_losses_ruling(client):
    _one_turn_battle(client)
    ok(client.post(f"/api/combat/{_foes(client)[0]['id']}/status", json={"out": "dead"}))
    a = _aftermath(client)
    assert a["zero_ruling"] and a["outcome"] == "decisive_victory"


def test_participation_per_days_fought_and_roles(client):
    pids = _one_turn_battle(client)
    a = _aftermath(client)
    k = {x["pid"]: x for x in a["knights"]}
    assert k[pids[0]]["role"] == "conroi" and k[pids[0]]["days"] == 1
    # Clash base 10 × (Indecisive 1 + conroi 2) = 30; the other knight 10 × 1 = 10
    assert a["outcome"] == "indecisive" and k[pids[0]]["participation"] == 30 and k[pids[1]]["participation"] == 10
    a = ok(client.post("/api/battle/aftermath", json={"patch": {"days_fought": {pids[1]: 0}}}))["aftermath"]
    assert {x["pid"]: x for x in a["knights"]}[pids[1]]["participation"] == 0


def test_plunder_only_on_victory_and_decisive_roll(client):
    pids = _one_turn_battle(client)
    a = _aftermath(client)
    assert all(not k["plunder"] for k in a["knights"])
    assert client.post("/api/battle/aftermath/roll", json={"what": "decisive"}).status_code == 409
    a = ok(client.post("/api/battle/aftermath", json={"patch": {"outcome_choice": None, "enemy_kv": "4", "friendly_pk_losses": 1}}))["aftermath"]
    assert a["outcome"] == "decisive_victory"
    ok(client.post("/api/battle/aftermath/roll", json={"what": "decisive"}))
    a = _battle(client)["aftermath"]
    assert 2 <= a["decisive_roll"] <= 6 and all(k["plunder"] for k in a["knights"])


def test_aftermath_is_gm_only(client):
    _one_turn_battle(client)
    _aftermath(client)
    ok(client.post("/api/battle/aftermath", json={"patch": {"friendly_pk_losses": 1}}))
    raw = client.get("/api/table").text
    assert "enemy_kv" not in raw and "friendly_pk_losses" not in raw


def test_finale_summary_on_table_then_ended(client):
    pids = _one_turn_battle(client)
    g = _foes(client)[0]
    ok(client.post(f"/api/combat/{g['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{g['id']}/status", json={"out": "dead"}))
    _aftermath(client)
    ok(client.post("/api/battle/finale"))
    t = ok(client.get("/api/table"))
    f = t["battle"]["finale"]
    assert f["outcome_label"] == "Decisive Victory" and f["knights"][0]["total"] == 50 + 10 * 4
    ok(client.post("/api/battle/end"))
    t = ok(client.get("/api/table"))
    assert t["mode"] == "chronicle" and t["feed"][0]["type"] == "battle.ended"
    assert _battle(client)["status"] == "ended"


def test_leave_the_field_goes_to_aftermath(client):
    _running(client)
    _step(client, "retire")
    _step(client, "rest", amount=1)
    _step(client, "end_turn")
    _step(client, "rear", choice="leave")
    assert _battle(client)["status"] == "aftermath"


# -- S11: example battles ----------------------------------------------------------

def test_launch_bedegraine_day2_on_foot(client):
    pids = _party(client, "Sir Bors", "Sir Cai")
    ok(client.post("/api/battle/start", json={"key": "The Battle of Bedegraine"}))
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"turns": 1}}))
    _muster(client, pids, commander="gm", intensity=None)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="success")
    _step(client, "morale", kind="loss", amount=1)
    _postures(client, pids)
    _step(client, "end_day")
    b = _battle(client)
    assert b["status"] == "mustering" and b["day"] == 2
    assert all(b["knights"][p]["mounted"] for p in pids)          # horses carry over; the template doesn't decide
    ev = ok(client.post("/api/battle/mounted", json={"mounted": False, "pids": pids}))["event"]
    assert all(not _battle(client)["knights"][p]["mounted"] for p in pids)
    ok(client.post(f"/api/events/{ev['id']}/strike"))
    assert all(_battle(client)["knights"][p]["mounted"] for p in pids)
    ok(client.post("/api/battle/mounted", json={"mounted": False, "pids": pids}))
    _muster(client, pids, commander="gm", intensity=None)
    assert all(not _battle(client)["knights"][p]["mounted"] for p in pids)
    b = _battle(client)
    assert b["intensity_today"] == 18 and b["step"]["items"][1]["state"] == "skipped"   # no charge this day


def test_quick_battle_empty_deck_means_every_battle_encounter(client):
    pids = _party(client, "Sir Bors")
    _quick(client, "clash")
    _muster(client, pids)
    deck = _battle(client)["deck_now"]
    assert deck["all"] and "Pictish Knifemen" in deck["foes"] and "Clash of Champions" in deck["opportunities"]
    _step(client, "set", encounter="Knights of Gorre")
    assert _battle(client)["t"]["set"]["encounter"] == "Knights of Gorre"
    assert "Pictish Knifemen" in [c["name"] for c in ok(client.get("/api/table"))["battle"]["deck"]["foes"]]


# -- everything stays editable while the battle runs -------------------------------

def test_edit_everything_mid_battle(client):
    pids = _running(client)                                  # Sir Bors, Sir Cai; Intensity 12
    third = _party(client, "Dame Lynet")[0]
    _step(client, "set", encounter="Pictish Knifemen")
    ok(client.post("/api/battle/day", json={"intensity": 15}))                           # override Intensity
    ok(client.post("/api/battle/army-roll", json={"side": "enemy", "outcome": "success"}))  # correct an army roll
    ok(client.post("/api/battle/conroi", json={"knights": pids + [third], "passion": "Honor", "start": 18}))
    ok(client.post("/api/battle/settings", json={"battle_patch": {"name": "The Ford", "where": "the Trent", "size": "small"}}))
    b = _battle(client)
    assert b["intensity_today"] == 15 and b["tokens"]["force"] == "available"
    assert b["conroi"] == pids + [third] and b["passion"] == "Honor" and b["morale"] == {"start": 18, "current": 18, "last": None}
    assert b["definition"]["name"] == "The Ford" and b["definition"]["size"] == "small"
    assert b["step"]["current"] == "intensity"               # the turn carries on where it was
    ok(client.post("/api/battle/commander", json={"commander": third}))
    assert _battle(client)["commander_name"] == "Dame Lynet"


def test_nobody_with_the_conroi_turn_can_still_end(client):
    """Every knight away (at the rear, Alone or gone) once the fight is over:
    Postures counts as done, the fight is skipped, and End turn is offered —
    the stepper never waits for a posture nobody can take."""
    pids = _running(client)
    _to_morale(client, "Pictish Knifemen")
    _step(client, "morale", kind="loss", amount=1)
    _postures(client, pids)
    assert _cur(client) == "fight"
    for p in pids:
        ok(client.post(f"/api/battle/knight/{p}", json={"position": "rear"}))
    b = _battle(client)
    states = {i["key"]: i for i in b["step"]["items"]}
    assert states["postures"]["state"] == "done"
    assert states["fight"]["state"] == "skipped" and "conroi" in states["fight"]["reason"]
    assert b["step"]["current"] == "end"
    r = client.post("/api/battle/fight")
    assert r.status_code == 409 and "conroi" in r.json()["detail"]
    _step(client, "end_turn")
    assert _battle(client)["turn"] == 2


def test_abandon_only_before_the_first_turn(client):
    pids = _party(client, "Sir Bors")
    _quick(client)
    ok(client.post("/api/battle/abandon"))
    assert _battle(client)["status"] == "ended"
    _quick(client)                                        # the tool is free again
    _muster(client, pids)
    assert client.post("/api/battle/abandon").status_code == 409


def test_launch_can_close_the_running_battle(client):
    pids = _party(client, "Sir Bors")
    _quick(client, "clash")
    r = client.post("/api/battle/start", json={"key": None, "quick": {"size": "skirmish"}})
    assert r.status_code == 409 and "at Mustering" in r.json()["detail"]
    # still at Mustering: called off, and the new one launches
    ok(client.post("/api/battle/start", json={"quick": {"size": "skirmish"}, "close_current": True}))
    b = _battle(client)
    assert b["status"] == "mustering" and b["definition"]["size"] == "skirmish"
    assert ok(client.get("/api/battle/paused"))["paused"] == []
    # begun: paused instead, so it can be resumed later
    _muster(client, pids)
    r = client.post("/api/battle/start", json={"quick": {"size": "clash"}})
    assert r.status_code == 409 and "Turn 1" in r.json()["detail"]
    ok(client.post("/api/battle/start", json={"quick": {"size": "clash"}, "close_current": True}))
    assert _battle(client)["definition"]["size"] == "clash"
    sess = ok(client.get("/api/session"))["session"]["id"]
    events = ok(client.get("/api/session"))["events"]
    assert any(e["type"] == "battle.paused" for e in events)


def test_charge_can_be_skipped_without_a_roll(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="success")
    _step(client, "morale", kind="loss", amount=1)
    _postures(client, pids)
    _step(client, "end_turn")
    _step(client, "set", encounter="Pictish Knifemen")
    assert _cur(client) == "charge"
    r = _step(client, "charge", skip=True)
    assert r["events"][0]["data"]["table_text"] == "No charge this turn"
    b = _battle(client)
    assert b["t"]["charge"] == {"outcome": None, "engaged_last": None, "result": "no_charge", "skipped": True}
    assert b["step"]["current"] == "intensity"
    t = ok(client.get("/api/table"))["battle"]
    assert t["charge_result"] == "no_charge"


def test_players_tally_per_knight_across_the_battle(client):
    """Each knight card on the Table carries a running tally of the foes they
    defeated — name, fate, day, turn, round — across every fight of the battle."""
    pids = _three(client)
    _to_fight(client, pids, "Pictish Knifemen")
    ok(client.post("/api/battle/fight"))
    f = _foes(client)
    ok(client.post(f"/api/combat/{f[0]['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{f[0]['id']}/status", json={"out": "dead"}))
    ok(client.post("/api/combat/round"))
    ok(client.post(f"/api/combat/{f[1]['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{f[1]['id']}/status", json={"out": "surrendered"}))
    t = ok(client.get("/api/table"))
    bors = next(k for k in t["knights"] if k["name"] == "Sir Bors")
    assert [(e["fate"], e["day"], e["turn"], e["round"]) for e in bors["tally"]] == [("surrendered", 1, 1, 2), ("slain", 1, 1, 1)]
    assert bors["tally"][0]["name"] == f[1]["display_name"]
    assert all(not k["tally"] for k in t["knights"] if k["name"] != "Sir Bors")
    ok(client.post("/api/combat/end"))
    _step(client, "end_turn")
    # between fights: the battle view's cards still carry the tally
    t = ok(client.get("/api/table"))
    bors = next(k for k in t["battle_knights"] if k["name"] == "Sir Bors")
    assert len(bors["tally"]) == 2
    # a second fight adds to it, with its own turn
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "charge", outcome="failure")
    _step(client, "intensity", outcome="success")
    _step(client, "morale", kind="loss", amount=1)
    _postures(client, pids)
    ok(client.post("/api/battle/fight"))
    g = _foes(client)[0]
    ok(client.post(f"/api/combat/{g['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{g['id']}/status", json={"out": "fled"}))
    bors = next(k for k in ok(client.get("/api/table"))["knights"] if k["name"] == "Sir Bors")
    assert len(bors["tally"]) == 3 and bors["tally"][0]["turn"] == 2 and bors["tally"][0]["fate"] == "fled"


def test_battle_fight_carries_the_barrage(client):
    pids = _three(client)
    _to_fight(client, pids, "Cambrian Archers")
    _step(client, "barrage", outcome="failure")                   # 2 rounds
    ok(client.post("/api/battle/fight"))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["barrage"] == {"rounds": 2, "active": True, "left": 2}


def test_battle_fight_couches_lances_and_countercharges(client):
    pids = _three(client)
    ok(client.post("/api/battle/settings", json={"day": 1, "patch": {"first_charge": True}}))
    _to_fight(client, pids, "Knights of Lothian")                   # turn 1: first charge, and they always countercharge
    ok(client.post("/api/battle/fight"))
    cs = ok(client.get("/api/combat"))["combat"]
    knights = [c for c in cs["combatants"] if c["side"] == "party"]
    foes = [c for c in cs["combatants"] if c["side"] != "party"]
    assert all(k["lance"] for k in knights)
    assert all(f["charging"] and f["attacks"][f["wielding"]]["skill"] == "Charge" for f in foes)
    ok(client.post("/api/combat/round"))
    cs = ok(client.get("/api/combat"))["combat"]
    assert not any(c["lance"] for c in cs["combatants"] if c["side"] == "party")
    assert not any(c["charging"] for c in cs["combatants"] if c["side"] != "party")


def test_resume_without_a_fight_ends_the_earlier_one():
    """A fight still open earlier in the session must not outlive a resume whose
    battle has none — the Table would keep showing it instead of the battle."""
    from web import combat_state
    started = {"id": 1, "type": "combat.started", "data": {"name": "Old fight", "combatants": []}}
    resumed = {"id": 2, "type": "battle.resumed", "data": {"snapshot": {"battle": {}, "combat": None}}}
    assert combat_state.reduce([started])["active"]
    assert combat_state.reduce([started, resumed]) is None


def _play_opportunity(client, pids, name="Clash of Champions"):
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="fumble")
    _step(client, "select", encounter=name, via="fumble")
    _step(client, "morale", kind="loss", amount=0)


def test_opportunity_replaces_postures_and_fight_and_awards_glory(client):
    pids = _running(client)
    _play_opportunity(client, pids)
    assert _cur(client) == "opportunity"
    steps = {i["key"]: i["state"] for i in _battle(client)["step"]["items"]}
    assert steps["postures"] == "skipped" and steps["fight"] == "skipped"
    assert client.post("/api/battle/fight").status_code == 409
    assert client.post("/api/battle/step", json={"step": "posture", "knight": pids[0], "posture": "valorous"}).status_code == 409
    assert client.post("/api/battle/step", json={"step": "end_turn"}).status_code == 409
    _step(client, "opportunity_glory", knights=[pids[0]], amount=50, reason="Champion defeated")
    _step(client, "opportunity_glory", knights="all", amount=10, reason="Every knight")
    g = _battle(client)["glory_battle"]
    assert g[pids[0]] == 60 and g[pids[1]] == 10
    assert [a["amount"] for a in _battle(client)["opportunity"]["awards"]] == [50, 10, 10]
    assert client.post("/api/battle/step", json={"step": "opportunity_glory", "knights": "all", "amount": 0, "reason": "x"}).status_code == 400
    assert client.post("/api/battle/step", json={"step": "opportunity_glory", "knights": "all", "amount": 5, "reason": ""}).status_code == 400
    _step(client, "opportunity_done")
    assert _cur(client) == "end"
    _step(client, "end_turn")
    b = _battle(client)
    assert b["turn"] == 2 and b["fought_last"] and 1 in b["fought_days"][pids[0]]


def test_opportunity_glory_undo_with_the_step(client):
    pids = _running(client)
    _play_opportunity(client, pids)
    _step(client, "opportunity_glory", knights=[pids[0]], amount=50, reason="Champion defeated")
    ok(client.post("/api/battle/undo", json={"step": "morale"}))
    assert _battle(client)["glory_battle"].get(pids[0], 0) == 0 and _cur(client) == "morale"


def test_table_gets_only_the_title_box_after_morale(client):
    pids = _running(client)
    _step(client, "set", encounter="Pictish Knifemen")
    _step(client, "intensity", outcome="fumble")
    _step(client, "select", encounter="Clash of Champions", via="fumble")
    assert _tb(client)["battle"]["opportunity"] is None
    _step(client, "morale", kind="loss", amount=0)
    tb = _tb(client)["battle"]["opportunity"]
    assert tb["name"] == "Clash of Champions" and tb["title"] == "Clash of Champions" and tb["flavour"].startswith("The enemy parts")
    assert set(tb) == {"name", "title", "flavour"}              # nothing of the instructions or stats
    assert "conroi commander" not in json.dumps(_tb(client)["battle"])
    gm = _battle(client)["opportunity"]
    assert gm["back"][0]["subtitle"] == "Champion" and gm["rewards"][0]["amount"] == 50
