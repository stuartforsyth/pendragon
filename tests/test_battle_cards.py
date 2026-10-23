"""The shipped Opportunity card transcription, and the generated fallback."""

import json
import os

from core import battle_cards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = ["Capture the Banner", "Fight Enemy Commander", "Rescue Captive Knights", "Rally the Division!", "Clash of Champions"]


def _data():
    return json.load(open(os.path.join(ROOT, "data", "examplecombat.json"), encoding="utf-8"))


def test_every_shipped_opportunity_has_a_transcribed_card():
    cards, d = battle_cards.load(os.path.join(ROOT, "data")), _data()
    for name in SHIPPED:
        f = battle_cards.faces(cards, name, d["encounters"][name], d["adversaries"])
        assert f["front"] and all(face.get("blocks") for face in f["front"]), name
        minimum = next(x["footer"]["value"] for x in f["front"] if x.get("footer") and x["footer"]["label"] == "Morale Minimum") \
            if name != "Rally the Division!" else "12"
        assert int(minimum) == d["encounters"][name]["morale_minimum"], name
    assert not battle_cards.faces(cards, "Rally the Division!")["back"]


def test_rewards_are_the_printed_glory():
    cards = battle_cards.load(os.path.join(ROOT, "data"))
    rw = {n: {r["label"]: r["amount"] for r in cards[n]["rewards"]} for n in SHIPPED}
    assert rw["Capture the Banner"]["Banner carrier (banner brought to the lines)"] == 100
    assert rw["Fight Enemy Commander"]["Killed or captured the Commander"] == 150
    assert max(rw["Rescue Captive Knights"].values()) == 350 and rw["Rally the Division!"] == {}


def test_unknown_opportunity_falls_back_to_a_generated_card():
    d = _data()
    enc = dict(d["encounters"]["Capture the Banner"], rules="One.\nTwo.", description="Flavour.")
    f = battle_cards.faces({}, "Capture the Banner", enc, d["adversaries"])
    assert [b["p"] for b in f["front"][0]["blocks"]] == ["One.", "Two."] and f["front"][0]["flavour"] == "Flavour."
    assert f["back"][0]["subtitle"] == "Banner Guard" and f["back"][0]["other"][2] == ["Glory Award", "50"]
    assert f["rewards"] == []


FOES = ["Knights of Gorre", "Knights of Lothian", "Knights of Malahaut", "Knights of Cornwall", "Northern Prickers", "Pictish Pikemen",
        "Pictish Javeliniers", "Pictish Knifemen", "Saxon Warriors", "Irish Kerns", "Cambrian Archers", "Breton Mercenary Knights"]


def test_every_shipped_foe_has_front_and_back_matching_the_library():
    cards, d = battle_cards.load(os.path.join(ROOT, "data")), _data()
    for name in FOES:
        f = battle_cards.faces(cards, name, d["encounters"][name], d["adversaries"])
        front, back = f["front"][0], f["back"][0]
        assert front["title"] == name and front["flavour"] and front["blocks"], name
        assert int(front["footer"]["value"]) == d["encounters"][name]["morale_minimum"], name
        other = dict(back["other"])
        assert other["Morale Loss"].replace("–", "-") == d["encounters"][name]["morale_loss"].replace("–", "-"), name
        assert back["health"][0][0] == "Hit Points" and len(back["chars"]) == 4 and back["attacks"], name
