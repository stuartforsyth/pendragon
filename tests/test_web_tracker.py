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


def test_table_hides_foe_numbers_and_horse_secrets(client):
    cs = _fight(client, encounter="Bandit ambush", knights=("Sir Bors",))
    bandit = _foes(cs)[0]
    ok(client.post(f"/api/combat/{bandit['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{bandit['id']}/horse", json={"on": True}))
    t = next(c for c in ok(client.get("/api/table"))["combat"]["combatants"] if c["id"] == bandit["id"])
    for secret in ("cur_hp", "max_hp", "attacks", "height", "height_chip", "attacks_horse"):
        assert secret not in t
    table = ok(client.get("/api/table"))
    assert not any("horse" in (c.get("text") or "") for c in table["feed"])        # the GM's secret
    assert all(not f["chips"] for k in table["knights"] for f in k["lane"]["foes"])
    gm = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == bandit["id"])
    assert gm["attacks_horse"] and gm["height_chip"] == "No Height"                 # the GM still sees it
    # the reveal: the blow lands on the horse
    blow = ok(client.post("/api/combat/blow", json={"attacker": bandit["id"], "attack": 0, "target": _knight(cs, "Sir Bors")["id"]}))["event"]
    assert "Sir Bors’s horse" in blow["data"]["narrative"]


def test_adversary_editor_keeps_flags(client):
    adv = ok(client.get("/api/adversaries/Bandit"))["adversary"]
    adv.update(mounted=True, countercharge=True, attacks_horse=True)
    ok(client.put("/api/adversaries", json={"adversary": adv, "original": "Bandit"}))
    back = ok(client.get("/api/adversaries/Bandit"))["adversary"]
    assert back["mounted"] and back["countercharge"] and back["attacks_horse"]


def _save_enc(client, name, tags, roster=True, role=None):
    enc = ok(client.get("/api/encounters/blank"))["encounter"]
    enc.update(name=name, tags=tags)
    if roster:
        enc["roster"] = [{"adversary": "Bandit", "count": 2, "per_player": False, "promote": False}]
    if role:
        enc["battle_role"] = role
    ok(client.put("/api/encounters", json={"encounter": enc}))


def test_random_fight_filters_by_all_tags(client):
    _save_enc(client, "Both", ["xtag", "ytag"])
    _save_enc(client, "One", ["xtag"])
    for _ in range(6):
        ok(client.post("/api/combat/random", json={"tags": ["xtag", "ytag"]}))
        assert ok(client.get("/api/combat"))["combat"]["name"] == "Both"


def test_random_fight_excludes_opportunities_and_empty(client):
    _save_enc(client, "Opp", ["ztag"], role="opportunity")
    _save_enc(client, "Empty", ["ztag"], roster=False)
    _save_enc(client, "Real", ["ztag"])
    for _ in range(6):
        ok(client.post("/api/combat/random", json={"tags": ["ztag"]}))
        assert ok(client.get("/api/combat"))["combat"]["name"] == "Real"


def test_random_fight_no_match_400(client):
    assert client.post("/api/combat/random", json={"tags": ["no-such-tag"]}).status_code == 400


# -- Distribute foes equally -------------------------------------------------------

def test_even_split_keeps_engaged_foes_and_balances():
    from types import SimpleNamespace as N
    from web.routes.combat import even_split
    foes = [N(id=f"f{i}", engaged_with=w) for i, w in enumerate(["A", "A", "A", "A", "", "", "B", "", "", ""])]
    moves = even_split(foes, ["A", "B", "C"])
    load = {"A": 0, "B": 0, "C": 0}
    for f in foes:
        load[moves.get(f.id, f.engaged_with)] += 1
    assert sorted(load.values()) == [3, 3, 4]
    assert all(f.id not in moves for f in foes[:3])          # A keeps three of its four
    assert "f6" not in moves                                  # B keeps its foe


def _lanes(client):
    cs = ok(client.get("/api/combat"))["combat"]
    by = {}
    for c in _foes(cs):
        if c["status"] == "active":
            by.setdefault(c["engaged_with"], []).append(c["id"])
    return cs, by


def test_distribute_foes_active_only_and_undoable(client):
    cs = _fight(client, "Pictish Knifemen", knights=("Sir Bors", "Sir Cai", "Dame Lynet"))
    foes = _foes(cs)
    assert len(foes) >= 5
    # one foe falls to Sir Bors: he must keep it (and its Glory) after the share-out
    fallen = foes[0]
    ok(client.post(f"/api/combat/{fallen['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{fallen['id']}/status", json={"out": "unconscious"}))
    ev = ok(client.post("/api/combat/distribute"))["event"]
    assert ev["type"] == "combat.distribute" and fallen["id"] not in ev["data"]["assignments"]
    cs, by = _lanes(client)
    assert "" not in by                                       # nobody left in the pool
    counts = sorted(len(by.get(k, [])) for k in ("Sir Bors", "Sir Cai", "Dame Lynet"))
    assert counts[-1] - counts[0] <= 1
    assert next(c for c in cs["combatants"] if c["id"] == fallen["id"])["engaged_with"] == "Sir Bors"
    # already even: nothing to do
    assert ok(client.post("/api/combat/distribute"))["event"] is None
    # one strike undoes the whole share-out
    ok(client.post(f"/api/events/{ev['id']}/strike"))
    assert set(_lanes(client)[1]) == {""}


def test_distribute_skips_downed_knights(client):
    cs = _fight(client, knights=("Sir Bors", "Sir Cai"))
    bors = _knight(cs, "Sir Bors")
    ok(client.post(f"/api/combat/{bors['id']}/status", json={"out": "unconscious"}))
    ok(client.post("/api/combat/distribute"))
    assert set(_lanes(client)[1]) == {"Sir Cai"}


# -- weapons in hand, Disarmed, Brawling -------------------------------------------

def test_default_brawling_rules():
    from core.adversary import brawling_damage, default_brawling
    ch = {"STR": 15, "SIZ": 15}
    assert brawling_damage(ch) == 5 and brawling_damage({"STR": 8, "SIZ": 8}) == 3     # 16/6 = 2.67 -> 3
    assert default_brawling("Knights of Gorre", "human", ch, [{"skill": "Sword", "value": 17}]) == (10, "STR ÷ 2, at least 10 for a knight")
    assert default_brawling("Bandit", "human", {"STR": 13}, [])[0] == 7                  # 6.5 rounds up
    assert default_brawling("Bandit", "human", ch, [{"skill": "Brawling", "value": 8, "weapon": "Dagger"}]) == (8, "Dagger")
    assert default_brawling("Bear", "beast", ch, []) == (None, "")
    assert default_brawling("X", "human", ch, [], {"Brawling": 14})[0] == 14


def test_wield_type_and_disarm_then_brawl_attack(client):
    cs = _fight(client, knights=("Sir Bors", "Sir Cai", "Dame Lynet"))
    ok(client.post("/api/combat/distribute"))
    foes = _foes(ok(client.get("/api/combat"))["combat"])
    assert all(f["wielding"] == 0 for f in foes)                         # the card's first weapon
    ev = ok(client.post("/api/combat/wield", json={"type": "Knights of Gorre", "wield": 2}))["event"]
    assert len(ev["data"]["cids"]) == 3
    f = foes[0]
    ok(client.post("/api/combat/wield", json={"cid": f["id"], "wield": "brawl"}))
    row = next(c for c in _foes(ok(client.get("/api/combat"))["combat"]) if c["id"] == f["id"])
    assert row["wielding"] == "brawl" and row["brawl"]["value"] == 10 and row["brawl"]["damage"] == "5"
    roll = ok(client.post(f"/api/combat/{f['id']}/roll", json={"what": "attack"}))["event"]      # no key: the weapon in hand
    assert roll["data"]["label"].startswith("Brawling") and roll["data"]["attack"] == "brawl"
    knight = _knight(cs, row["engaged_with"])
    blow = ok(client.post("/api/combat/blow", json={"attacker": f["id"], "attack": "brawl", "target": knight["id"], "critical": True}))["event"]
    terms = blow["data"]["blow"]
    crit = next(x for x in terms["terms"] if x["label"] == "critical")
    assert blow["data"]["weapon"] == "Brawling" and crit["expr"].lower() == "2d6"   # unarmed critical: +2D6, not +4D6
    t = ok(client.get("/api/table"))
    assert any("Disarmed" in x["chips"] for k in t["knights"] for x in k["lane"]["foes"])
    # strike the disarm: back to the sword
    ok(client.post(f"/api/events/{_last_id(client, 'combat.wield')}/strike"))
    row = next(c for c in _foes(ok(client.get("/api/combat"))["combat"]) if c["id"] == f["id"])
    assert row["wielding"] == 2


def _last_id(client, t):
    evs = ok(client.get("/api/session/events"))["events"]
    return [e for e in evs if e["type"] == t][-1]["id"]


def test_brawling_override_saved_and_used(client):
    adv = ok(client.get("/api/adversaries/Knights of Gorre"))["adversary"]
    adv["brawling"] = 13
    ok(client.put("/api/adversaries", json={"adversary": adv, "original": "Knights of Gorre"}))
    assert ok(client.get("/api/adversaries/Knights of Gorre"))["adversary"]["brawling"] == 13
    _fight(client)
    f = _foes(ok(client.get("/api/combat"))["combat"])[0]
    assert f["brawl"]["value"] == 13
    r = ok(client.post("/api/adversaries/brawling", json={"name": "Knights of Gorre", "category": "human",
                                                          "characteristics": {"STR": 15, "SIZ": 15}}))
    assert r == {"default": 10, "source": "STR ÷ 2, at least 10 for a knight", "damage": 5}


def test_knights_share_a_foe_outnumbered_automatic_and_adjust(client):
    cs = _fight(client, knights=("Sir Bors", "Sir Cai", "Dame Lynet"))
    foe = _foes(cs)[0]
    ok(client.post("/api/combat/link", json={"cid": foe["id"], "knight": "Sir Bors"}))      # nobody on it: engages
    ok(client.post("/api/combat/link", json={"cid": foe["id"], "knight": "Sir Cai"}))
    ok(client.post("/api/combat/link", json={"cid": foe["id"], "knight": "Dame Lynet"}))
    row = next(c for c in _foes(ok(client.get("/api/combat"))["combat"]) if c["id"] == foe["id"])
    assert row["linked"] == ["Sir Bors", "Sir Cai", "Dame Lynet"] and row["outnumbered"] == -10
    knights = {k["display_name"]: k for k in ok(client.get("/api/combat"))["combat"]["combatants"] if k["side"] == "party"}
    assert all(foe["display_name"] in k["engaged_by"] for k in knights.values())
    ev = ok(client.post(f"/api/combat/{foe['id']}/roll", json={"what": "attack", "key": 1, "adjust": 3}))["event"]
    assert "−10 outnumbered" in ev["data"]["label"] and "+3" in ev["data"]["label"]
    # the players' board shows the foe in each knight's lane
    t = ok(client.get("/api/table"))
    assert sum(1 for k in t["knights"] for f in k["lane"]["foes"] if f["id"] == foe["id"]) == 3
    # one knight breaks off: −5
    ok(client.post("/api/combat/unlink", json={"knight": "Sir Bors"}))
    row = next(c for c in _foes(ok(client.get("/api/combat"))["combat"]) if c["id"] == foe["id"])
    assert row["linked"] == ["Sir Cai", "Dame Lynet"] and row["outnumbered"] == -5 and row["engaged_with"] == "Sir Cai"
    # Distribute never splits a shared foe; moving it (engage) leaves one knight
    ok(client.post("/api/combat/distribute"))
    assert next(c for c in _foes(ok(client.get("/api/combat"))["combat"]) if c["id"] == foe["id"])["linked"] == ["Sir Cai", "Dame Lynet"]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    assert next(c for c in _foes(ok(client.get("/api/combat"))["combat"]) if c["id"] == foe["id"])["linked"] == ["Sir Bors"]
