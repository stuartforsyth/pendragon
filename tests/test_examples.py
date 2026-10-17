import copy
import json
import os
import shutil

from core import examples as X
from core.combat import Encounter
from core.encounter_def import to_editable
from core.rules import load_rules
from tests.conftest import ROOT, ok

BASELINE = os.path.join(ROOT, "data", "examplecombat.json")
KNIGHT_CARDS = ("Knights of Gorre", "Knights of Lothian", "Knights of Malahaut",
                "Knights of Cornwall", "Breton Mercenary Knights")
OPPORTUNITIES = ("Capture the Banner", "Fight Enemy Commander", "Rescue Captive Knights",
                 "Rally the Division!", "Clash of Champions")


def _baseline():
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)


def test_baseline_cards_fixed():
    d = _baseline()
    advs, encs = d["adversaries"], d["encounters"]
    kerns = advs["Irish Kerns"]["other"]
    assert (kerns["armor_points"], kerns["shield"]) == (0, 4)
    for k in KNIGHT_CARDS + ("Northern Prickers", "Mounted Sergeant"):
        assert advs[k].get("mounted") and advs[k].get("countercharge"), k
    assert advs["Pictish Knifemen"].get("attacks_horse")
    foes = [k for k, e in encs.items() if e.get("battle_role") == "foe"]
    assert len(foes) == 12
    for k in foes:
        assert "roster" in encs[k] and "core" not in encs[k], k
        assert encs[k].get("morale_minimum") and encs[k].get("morale_loss"), k
    assert {k for k, e in encs.items() if e.get("missile")} == {"Cambrian Archers", "Pictish Javeliniers"}
    opps = {k for k, e in encs.items() if e.get("battle_role") == "opportunity"}
    assert opps == set(OPPORTUNITIES)


def test_every_baseline_encounter_builds(tmp_path):
    shutil.copy(os.path.join(ROOT, "data", "rules.json"), tmp_path / "rules.json")
    shutil.copy(BASELINE, tmp_path / "examplecombat.json")
    rules = load_rules(str(tmp_path))
    for key, defn in rules.combat["encounters"].items():
        editable = to_editable(defn)
        if not editable["roster"]:
            assert defn.get("battle_role") == "opportunity", key
            continue
        foes = Encounter(rules).generate_from_definition(editable, 3)
        assert foes, key


def test_merge_inserts_absent_only():
    base = {"adversaries": {"A": {"glory": 50, "mounted": True, "other": {"glory": 50, "knight_value": "1"}},
                            "B": {"glory": 10}},
            "encounters": {}}
    working = {"adversaries": {"A": {"glory": 0, "other": {"glory": 0}}}}
    added = X.merge_missing(working, base)
    a = working["adversaries"]["A"]
    assert a["glory"] == 0 and a["other"]["glory"] == 0          # user's values untouched
    assert a["mounted"] is True and a["other"]["knight_value"] == "1"
    assert working["adversaries"]["B"] == {"glory": 10}
    assert added == {"adversaries": 1, "encounters": 0, "battles": 0, "fields": 2}


def test_merge_skips_roster_on_legacy_encounters():
    base = {"encounters": {"E": {"roster": [{"adversary": "A"}], "battle_role": "foe", "per_player": 1}}}
    working = {"encounters": {"E": {"core": ["A"], "per_player": 1.0}}}
    X.merge_missing(working, base)
    e = working["encounters"]["E"]
    assert "roster" not in e and e["core"] == ["A"] and e["battle_role"] == "foe"


def test_report_lists_missing_fields_and_differences():
    base = {"adversaries": {"A": {"battle_card": True, "glory": 50, "mounted": True}, "N": {}}}
    working = {"adversaries": {"A": {"battle_card": True, "glory": 0}}}
    r = X.examples_report(working, base)
    assert r["missing"]["adversaries"] == ["N"]
    assert r["fields"] == [{"kind": "adversaries", "key": "A", "fields": ["mounted"]}]
    assert r["differs"] == [{"kind": "adversaries", "key": "A", "fields": ["glory"]}]


def test_restore_replaces_one_entry():
    base = {"adversaries": {"A": {"glory": 50}, "B": {"glory": 5}}}
    working = {"adversaries": {"A": {"glory": 0}, "B": {"glory": 1}}}
    X.restore_entry(working, base, "adversaries", "A")
    assert working["adversaries"] == {"A": {"glory": 50}, "B": {"glory": 1}}
    working["adversaries"]["A"]["glory"] = 7
    assert base["adversaries"]["A"]["glory"] == 50                 # a copy, not shared


def test_examples_routes_write_working_copy_only(client):
    data = client.tmp / "data"
    before = (data / "examplecombat.json").read_bytes()
    # Simulate an older working library: drop a card and a flag.
    ok(client.delete("/api/adversaries/Bandit"))
    working = json.loads((data / "combat.json").read_text())
    report = ok(client.get("/api/library/examples"))
    assert "Bandit" in report["missing"]["adversaries"]
    added = ok(client.post("/api/library/examples/merge", json={}))["added"]
    assert added["adversaries"] >= 1
    after = json.loads((data / "combat.json").read_text())
    assert "Bandit" in after["adversaries"] and "Bandit" not in working["adversaries"]
    assert (data / "examplecombat.json").read_bytes() == before
    report = ok(client.get("/api/library/examples"))
    assert not any(report["missing"].values()) and not report["fields"]


def test_examples_restore_route(client):
    adv = copy.deepcopy(ok(client.get("/api/adversaries/Knights of Gorre"))["adversary"])
    adv["description"] = "My own Gorre"
    ok(client.put("/api/adversaries", json={"adversary": adv, "original": "Knights of Gorre"}))
    r = ok(client.post("/api/library/examples/restore", json={"kind": "adversaries", "key": "Knights of Gorre"}))
    assert r["entry"]["description"] != "My own Gorre"
    assert client.post("/api/library/examples/restore",
                       json={"kind": "adversaries", "key": "Nobody"}).status_code == 404


def test_example_battles_valid():
    from core.battle_def import clean_battle
    d = _baseline()
    for key, b in d["battles"].items():
        clean, warnings = clean_battle(b, d["encounters"])
        assert not warnings, (key, warnings)
    bed = d["battles"]["The Battle of Bedegraine"]
    assert bed["size"] == "huge" and bed["days"][1]["on_foot"] and bed["days"][1]["no_charge"]
    assert [x["intensity"]["value"] for x in bed["days"]] == [14, 18]
    assert all(b["commander"] is None for b in d["battles"].values())   # chosen at launch, never in the template


def test_examples_merge_adds_battles():
    base = {"battles": {"B": {"size": "clash"}}}
    working = {"adversaries": {}}
    assert X.merge_missing(working, base)["battles"] == 1 and "B" in working["battles"]
