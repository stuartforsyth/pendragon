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
    assert mo == {"n": 3, "faced": 3, "mod": -10, "limit": 3, "over": False}
    ok(client.post(f"/api/combat/{knife[3]['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{knife[4]['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{knife[5]['id']}/engage", json={"with": "Sir Bors"}))
    mo = _knight(ok(client.get("/api/combat"))["combat"], "Sir Bors")["mo"]      # six on him, only three can reach
    assert mo["over"] and mo["n"] == 6 and mo["faced"] == 3 and mo["mod"] == -10
    tb = next(c for c in ok(client.get("/api/table"))["combat"]["combatants"] if c["name"] == "Sir Bors")   # the players' chip stops at three too
    assert tb["mo_n"] == 3 and tb["mo_mod"] == -10
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
    assert all(f["wielding"] == 1 for f in foes)                         # the first melee weapon: a charge weapon only when charging
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


def test_acted_this_round_from_attack_rolls_and_by_hand(client):
    """A foe's attack roll ticks it as having acted; the GM can tick/untick by
    hand; Next round clears every tick. The Table shows the foes' ticks — and nothing for knights."""
    cs = _fight(client, "Pictish Knifemen", ("Sir Bors",))
    foes = _foes(cs)
    a, b = foes[0], foes[1]
    assert not a["acted"] and set(cs["to_act"]) == {f["id"] for f in foes}
    ok(client.post(f"/api/combat/{a['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{a['id']}/roll", json={"what": "attack"}))
    ok(client.post(f"/api/combat/{b['id']}/acted", json={"on": True}))
    cs = ok(client.get("/api/combat"))["combat"]
    by = {c["id"]: c for c in cs["combatants"]}
    assert by[a["id"]]["acted"] and by[b["id"]]["acted"]
    assert a["id"] not in cs["to_act"] and b["id"] not in cs["to_act"] and len(cs["to_act"]) == len(foes) - 2
    ok(client.post(f"/api/combat/{b['id']}/acted", json={"on": False}))
    assert b["id"] in ok(client.get("/api/combat"))["combat"]["to_act"]
    ok(client.post("/api/combat/round"))
    cs = ok(client.get("/api/combat"))["combat"]
    assert not any(c["acted"] for c in cs["combatants"]) and len(cs["to_act"]) == len(foes)
    ok(client.post(f"/api/combat/{b['id']}/acted", json={"on": True}))
    table = ok(client.get("/api/table"))["combat"]["combatants"]
    assert [c["acted"] for c in table if c["id"] == b["id"]] == [True]
    assert all("acted" not in c for c in table if c["side"] == "party")
    assert not [c for c in table if c["side"] != "party" and c["id"] != b["id"] and c["acted"]]


def test_table_sees_mounted_but_not_horse_attacks(client):
    cs = _fight(client, "Knights of Gorre", ("Sir Bors",))
    gorre = _foes(cs)[0]
    ok(client.post(f"/api/combat/{gorre['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{gorre['id']}/horse", json={"on": True}))
    rows = ok(client.get("/api/table"))["combat"]["combatants"]
    foe = next(r for r in rows if r["id"] == gorre["id"])
    assert foe["mounted"] is True and "attacks_horse" not in foe
    ok(client.post(f"/api/combat/{gorre['id']}/mounted", json={"mounted": False}))
    rows = ok(client.get("/api/table"))["combat"]["combatants"]
    assert next(r for r in rows if r["id"] == gorre["id"])["mounted"] is False


def _roll_until(client, cid, outcomes, tries=80):
    for _ in range(tries):
        roll = ok(client.post(f"/api/combat/{cid}/roll", json={"what": "attack", "key": 0}))["event"]
        if roll["data"]["outcome"] in outcomes:
            return roll
    raise AssertionError(f"no {outcomes} in {tries} rolls")


def test_defend_adds_ten_and_never_strikes(client):
    """Defend: Weapon Skill +10; a win or tie turns the blow, no damage either
    way; a loss means the knight hits as usual (core.combat.defensive-actions)."""
    cs = _fight(client, "Pictish Knifemen", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    assert ok(client.get("/api/combat"))["combat"]["combatants"][0].get("stance", "attack") == "attack"
    ev = ok(client.post("/api/combat/stance", json={"cid": foe["id"], "stance": "defend"}))["event"]
    assert ev["type"] == "combat.stance" and "+10" in ev["text"]
    roll = _roll_until(client, foe["id"], ("success",))
    assert roll["data"]["stance"] == "defend" and roll["data"]["modifier"] == 10 and "Defend +10" in roll["data"]["label"]
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "lower"}))
    assert r["result"] == "foe" and r["blow"] is None and r["held"] and "no damage either way" in r["event"]["data"]["verdict"]
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "equal"}))
    assert r["result"] == "tie" and r["blow"] is None and r["held"]
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "higher"}))
    assert r["result"] == "knight" and r["blow"] is None and not r["held"] and r["knight_shield"]
    # the Table hears the stance but not the mechanics
    t = ok(client.get("/api/table"))
    assert any(c["type"] == "combat.stance" and "defend" in c["text"] for c in t["feed"])


def test_evade_breaks_away_and_dodge_is_on_foot_only(client):
    cs = _fight(client, "Pictish Knifemen", ("Sir Bors", "Sir Cai"))
    bors = _knight(cs, "Sir Bors")
    foe = _foes(cs)[0]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    # evade rolls Movement Rate: (STR 8 + DEX 16) / 2 + 5 = 17
    ok(client.post("/api/combat/stance", json={"cid": foe["id"], "stance": "evade"}))
    roll = _roll_until(client, foe["id"], ("critical", "success"))
    assert roll["data"]["value"] == 17 and roll["data"]["label"].startswith("Evade (Movement)")
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "failure"}))
    assert r["held"] and "breaks away" in r["event"]["data"]["verdict"]
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == foe["id"])
    assert row["engaged_with"] == "" and row["linked"] == []
    # dodge: not for a rider; a type-wide stance skips riders; one roll skips the outnumbered penalty
    other = _foes(cs)[1]
    ok(client.post(f"/api/combat/{other['id']}/mounted", json={"mounted": True}))
    assert client.post("/api/combat/stance", json={"cid": other["id"], "stance": "dodge"}).status_code == 400
    ev = ok(client.post("/api/combat/stance", json={"type": "Pictish Knifemen", "stance": "dodge"}))["event"]
    assert other["id"] not in ev["data"]["cids"] and foe["id"] in ev["data"]["cids"]
    ok(client.post(f"/api/combat/{foe['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post("/api/combat/link", json={"cid": foe["id"], "knight": "Sir Cai"}))
    roll = ok(client.post(f"/api/combat/{foe['id']}/roll", json={"what": "attack", "key": 0}))["event"]
    assert roll["data"]["stance"] == "dodge" and roll["data"]["outnumbered"] == 0 and roll["data"]["value"] == 17
    # a dodge fumble: the foe falls and drops its weapon
    roll = _roll_until(client, foe["id"], ("fumble",), tries=400)
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "higher"}))
    assert "drops their weapon" in r["event"]["data"]["verdict"]
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == foe["id"])
    assert row["wielding"] == "brawl"


def test_prone_is_exclusive_with_mounted_and_follows_a_knockdown(client):
    cs = _fight(client, "Knights of Gorre", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    gorre = _foes(cs)[0]
    ok(client.post(f"/api/combat/{gorre['id']}/engage", json={"with": "Sir Bors"}))
    row = lambda cid: next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == cid)
    assert row(gorre["id"])["mounted"] and not row(gorre["id"])["prone"]
    # a knight marked prone: on foot and prone; mounting again stands them up
    ok(client.post(f"/api/combat/{bors['id']}/prone", json={"on": True}))
    assert row(bors["id"])["prone"] and not row(bors["id"])["mounted"]
    assert _attack_height(client, gorre["id"]) == 5                         # the rider stands over the fallen knight
    ok(client.post(f"/api/combat/{bors['id']}/mounted", json={"mounted": True}))
    assert not row(bors["id"])["prone"]
    # an automatic knockdown (damage > twice Knockdown) lays a mounted foe prone: a fall, 1D6, weapon dropped
    kd = row(gorre["id"])["knockdown"]
    hp_before = row(gorre["id"])["cur_hp"]
    ok(client.post("/api/combat/blow", json={"target": gorre["id"], "damage": 2 * kd + 1 + row(gorre["id"])["armor_total"]}))
    r = row(gorre["id"])
    if r["status"] == "active":
        assert r["prone"] and not r["mounted"] and r["wielding"] == "brawl"
        assert hp_before - r["cur_hp"] >= 2 * kd + 2                          # the blow plus at least 1 from the fall
    # the Table sees prone but no numbers
    t = ok(client.get("/api/table"))["combat"]["combatants"]
    assert all("prone" in c and "knockdown" not in c for c in t)


def test_rider_needs_a_spear_or_tramples_a_prone_knight(client):
    cs = _fight(client, "Knights of Gorre", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    gorre = _foes(cs)[0]
    ok(client.post(f"/api/combat/{gorre['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{bors['id']}/prone", json={"on": True}))
    weapons = [a["weapon"] for a in gorre["attacks"]]
    sword = next(i for i, w in enumerate(weapons) if "sword" in w.lower() and "spear" not in w.lower())
    r = client.post(f"/api/combat/{gorre['id']}/roll", json={"what": "attack", "key": sword})
    assert r.status_code == 400 and "Trample" in r.json()["detail"]
    spear = next((i for i, w in enumerate(weapons) if "spear" in w.lower() or "lance" in w.lower()), None)
    if spear is not None:
        ok(client.post(f"/api/combat/{gorre['id']}/roll", json={"what": "attack", "key": spear}))
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == gorre["id"])
    assert row["cant_strike_prone"] is (sword == row["wielding"])
    # trample: Horsemanship, no Height for the rider, the horse's 3D6 on a win
    ok(client.post("/api/combat/stance", json={"cid": gorre["id"], "stance": "trample"}))
    roll = _roll_until(client, gorre["id"], ("critical", "success"))
    assert roll["data"]["stance"] == "trample" and roll["data"]["height"] == 0 and roll["data"]["label"].startswith("Trample (Horsemanship)")
    assert roll["data"]["value"] == gorre["skills"]["Horsemanship"]
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "failure"}))
    assert r["result"] == "foe" and "tramples" in r["event"]["data"]["verdict"]
    assert r["blow"]["data"]["to_knight"] and "Trample" in r["blow"]["data"]["weapon"] and "3d6" in r["blow"]["text"].lower()
    # a dismounted foe can't trample
    ok(client.post(f"/api/combat/{gorre['id']}/mounted", json={"mounted": False}))
    assert client.post("/api/combat/stance", json={"cid": gorre["id"], "stance": "trample"}).status_code == 400


def test_barrage_loose_shield_penalty_and_horse(client):
    """A missile foe looses at the knight it faces: unopposed, the knight's shield
    penalty on the roll (large −10 by default), a hit lands on a mounted knight's
    horse on 1–4, damage against armour only; the barrage rounds come from the
    battle (or the GM) and gate melee in the UI."""
    cs = _fight(client, "Pictish Javeliniers", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    jav = _foes(cs)[0]
    assert jav["missile"] == 1                                             # Javelin (thrown), not Javelin (Melee)
    assert bors["shield_size"] == "large" and bors["missile_penalty"] == -10
    assert client.post(f"/api/combat/{jav['id']}/loose", json={}).status_code == 400    # not facing anyone
    ok(client.post(f"/api/combat/{jav['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post("/api/combat/barrage", json={"rounds": 2}))
    cs = ok(client.get("/api/combat"))["combat"]
    assert cs["barrage"] == {"rounds": 2, "active": True, "left": 2}
    seen = set()
    for _ in range(60):
        r = ok(client.post(f"/api/combat/{jav['id']}/loose", json={}))
        d = r["event"]["data"]
        assert d["missile"] and d["modifier"] == -10 and "shield −10" in d["label"] and d["value"] == 18
        if r["hit"]:
            seen.add(r["where"])
            assert r["blow"]["data"]["to_knight"] and "armour only" in r["blow"]["text"]
            if r["where"] == "mount":
                assert "horse" in r["blow"]["data"]["narrative"]
        if seen == {"mount", "rider"}:
            break
    assert "mount" in seen or "rider" in seen
    # a smaller shield, a knight on foot: no horse to hit
    ok(client.post(f"/api/combat/{bors['id']}/shield", json={"size": "medium"}))
    ok(client.post(f"/api/combat/{bors['id']}/mounted", json={"mounted": False}))
    r = ok(client.post(f"/api/combat/{jav['id']}/loose", json={"adjust": -5}))
    assert r["event"]["data"]["modifier"] == -10 and "shield −5" in r["event"]["data"]["label"]
    assert r["where"] in (None, "rider")
    # the whole line looses at once
    for f in _foes(cs)[1:3]:
        ok(client.post(f"/api/combat/{f['id']}/engage", json={"with": "Sir Bors"}))
    r = ok(client.post("/api/combat/loose-all", json={"type": "Pictish Javeliniers"}))
    assert r["shots"] == 3
    ok(client.post("/api/combat/round")); ok(client.post("/api/combat/round"))
    assert ok(client.get("/api/combat"))["combat"]["barrage"]["active"] is False
    # players see the barrage state, not the roll numbers
    t = ok(client.get("/api/table"))["combat"]
    assert t["barrage"]["rounds"] == 2 and all("missile_penalty" not in c for c in t["combatants"])


def test_volley_is_one_card_per_knight(client):
    """The archers facing a knight loose together: the shots are GM-only in the
    log; the players get one combat.volley card with each shot's fate."""
    cs = _fight(client, "Pictish Javeliniers", ("Sir Bors", "Sir Cai"))
    bors, cai = _knight(cs, "Sir Bors"), _knight(cs, "Sir Cai")
    foes = _foes(cs)
    for f in foes[:3]:
        ok(client.post(f"/api/combat/{f['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{foes[3]['id']}/engage", json={"with": "Sir Cai"}))
    assert client.post(f"/api/combat/{foes[0]['id']}/volley", json={}).status_code == 400     # aimed at a knight
    r = ok(client.post(f"/api/combat/{bors['id']}/volley", json={}))
    assert r["shots"] == 3 and r["event"]["type"] == "combat.volley"
    d = r["event"]["data"]
    assert d["knight"] == "Sir Bors" and len(d["shots"]) == 3 and d["count"] == 3
    assert d["rider_damage"] == sum(s["damage"] for s in d["shots"] if s["where"] == "rider")
    feed = ok(client.get("/api/table"))["feed"]
    assert feed[0]["type"] == "combat.volley" and set(feed[0]["data"]) == {"knight", "count", "weapon", "shots", "rider_damage", "mount_damage"}
    assert not any(c["type"] in ("roll.check", "combat.blow") for c in feed)        # the individual shots stay with the GM
    # the whole line: one volley per knight
    r = ok(client.post("/api/combat/loose-all", json={"type": "Pictish Javeliniers"}))
    assert r["shots"] == 4 and len(r["events"]) == 2
    assert {e["data"]["knight"] for e in r["events"]} == {"Sir Bors", "Sir Cai"}
    assert all(e["data"]["count"] in (1, 3) for e in r["events"])


def test_dividers_before_a_volley_and_by_hand(client):
    cs = _fight(client, "Pictish Javeliniers", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    ok(client.post(f"/api/combat/{_foes(cs)[0]['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{bors['id']}/volley", json={}))
    ok(client.post("/api/combat/divider", json={"text": "The gate falls"}))
    assert client.post("/api/combat/divider", json={"text": " "}).status_code == 400
    feed = ok(client.get("/api/table"))["feed"]
    kinds = [(c["type"], c["text"]) for c in feed[:3]]
    assert kinds[0] == ("divider", "The gate falls") and kinds[1][0] == "combat.volley" and kinds[2] == ("divider", "Volley at Sir Bors")
    assert feed[0]["data"]["kind"] == "gm" and feed[2]["data"]["kind"] == "volley"


def _roll_attack_until(client, cid, key, outcomes, tries=120):
    for _ in range(tries):
        roll = ok(client.post(f"/api/combat/{cid}/roll", json={"what": "attack", "key": key}))["event"]
        if roll["data"]["outcome"] in outcomes:
            return roll
    raise AssertionError(f"no {outcomes}")


def test_lance_breaks_on_the_charge(client):
    """core.combat.action-mounted-charge: a couched spear or lance breaks on a
    partial success or a tie; a fumble breaks it and rolls Table 7.2. Melee:
    a spear breaks on a fumble or a tie against a sword. Broken weapons leave
    the list; the foe takes up the next. The log and the Fray say so."""
    cs = _fight(client, "Knights of Gorre", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    gorre = _foes(cs)[0]
    charge = next(i for i, a in enumerate(gorre["attacks"]) if a["skill"] == "Charge")
    assert gorre["wielding"] != charge and not gorre["charging"]          # no countercharge: melee weapon in hand
    ok(client.post(f"/api/combat/{gorre['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post("/api/combat/wield", json={"cid": gorre["id"], "wield": charge}))
    assert next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == gorre["id"])["charging"]
    # partial success (foe succeeds, knight higher): the couched spear shatters
    roll = _roll_attack_until(client, gorre["id"], charge, ("success",))
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "higher"}))
    assert "shatters on the charge" in r["event"]["data"]["verdict"]
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == gorre["id"])
    assert charge in row["broken"] and row["wielding"] != charge and not row["charging"]
    assert client.post("/api/combat/wield", json={"cid": gorre["id"], "wield": charge}).status_code == 400
    feed = ok(client.get("/api/table"))["feed"]
    assert any(c["type"] == "combat.break" and "shatters" in c["text"] for c in feed)
    # melee spear: a tie breaks it against the knight's sword
    spear = next(i for i, a in enumerate(gorre["attacks"]) if a["skill"] == "Spear")
    ok(client.post("/api/combat/wield", json={"cid": gorre["id"], "wield": spear}))
    roll = _roll_attack_until(client, gorre["id"], spear, ("success",))
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "equal"}))
    assert "breaks against the knight's sword" in r["event"]["data"]["verdict"]
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == gorre["id"])
    assert spear in row["broken"] and row["attacks"][row["wielding"]]["skill"] == "Sword"
    # the sword never breaks, even on a fumble: it is dropped
    roll = _roll_attack_until(client, gorre["id"], row["wielding"], ("fumble",), tries=400)
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "higher"}))
    assert "drops their sword" in r["event"]["data"]["verdict"]


def test_knights_lance_and_table_72_prompt(client):
    cs = _fight(client, "Knights of Gorre", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    gorre = _foes(cs)[0]
    ok(client.post(f"/api/combat/{gorre['id']}/engage", json={"with": "Sir Bors"}))
    ok(client.post(f"/api/combat/{bors['id']}/lance", json={"on": True}))
    t = ok(client.get("/api/table"))
    assert next(k for k in t["knights"] if k["name"] == "Sir Bors")["effects"][-1]["label"] == "Lance couched"
    roll = _roll_attack_until(client, gorre["id"], gorre["wielding"], ("success",))
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "lower"}))
    assert "Sir Bors's lance shatters" in r["event"]["data"]["verdict"]
    assert not next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == bors["id"])["lance"]
    assert any(c["type"] == "combat.lance" and "shatters" in c["text"] for c in ok(client.get("/api/table"))["feed"])
    ok(client.post(f"/api/combat/{bors['id']}/lance", json={"on": True}))
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "fumble"}))
    assert r["prompt"] == {"kind": "table72", "name": "Sir Bors"}
    # next round lowers any lance still couched
    ok(client.post(f"/api/combat/{bors['id']}/lance", json={"on": True}))
    ok(client.post("/api/combat/round"))
    assert not next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == bors["id"])["lance"]


def test_foe_lance_fumble_rolls_table_72(client):
    cs = _fight(client, "Northern Prickers", ("Sir Bors",))
    bors = _knight(cs, "Sir Bors")
    pr = _foes(cs)[0]
    ok(client.post(f"/api/combat/{pr['id']}/engage", json={"with": "Sir Bors"}))
    lance = next(i for i, a in enumerate(pr["attacks"]) if a["weapon"] == "Lance")
    ok(client.post("/api/combat/wield", json={"cid": pr["id"], "wield": lance}))
    roll = _roll_attack_until(client, pr["id"], lance, ("fumble",), tries=400)
    r = ok(client.post("/api/combat/attack", json={"event": roll["id"], "target": bors["id"], "knight": "failure"}))
    assert "lance shatters on the charge" in r["event"]["data"]["verdict"]
    events = ok(client.get("/api/session"))["events"]
    t72 = [e for e in events if e["type"] == "combat.check" and e["data"].get("label") == "Table 7.2"]
    assert len(t72) == 1 and pr["display_name"] in t72[0]["text"]
    row = next(c for c in ok(client.get("/api/combat"))["combat"]["combatants"] if c["id"] == pr["id"])
    assert lance in row["broken"] and row["attacks"][row["wielding"]]["weapon"] == "Mace"
