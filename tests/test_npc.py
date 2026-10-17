import copy
import json
import os

from core.adversary import draft_from_npc, finalise, normalise_traits
from core.npc import build_description, build_image_prompt, format_statblock_markdown


def test_generate_and_format_every_culture(generator):
    for culture in generator.culture_names():
        for gender in ("Male", "Female"):
            r = generator.generate(culture, gender)
            assert r["full"]
            assert build_description(r).startswith("You see")
            assert format_statblock_markdown(r).startswith(f"## {r['full']}")
            assert "Negative prompt" in build_image_prompt(r)


def test_full_cymric_knight(generator):
    r = generator.generate("Cymri", "Male", "Knight")
    assert r["full_knight"] and r["squire"] and r["ideals"]


def test_reroll_every_field(generator):
    r = generator.generate("Cymri", "Male", "Knight")
    for field in generator.reroll_fields():
        generator.reroll_field(r, field)
    assert r["full"]


def test_npc_to_adversary_round_trip(generator, rules):
    r = generator.generate("Saxon", "Male", "Knight")
    draft = draft_from_npc(r, rules.combat)
    adv = finalise(draft, rules, rules.combat)
    assert adv["kind"] == "named" and adv["health"]["hit_points"] > 0


def test_trait_pairs_balance(rules):
    a, b = rules.trait_pairs[0]
    out = normalise_traits(rules, {a: 15, b: 3}, {a: 15})
    assert out == {a: 15, b: 5}


def test_women_never_get_facial_hair(rules):
    import re
    for _ in range(400):
        a = rules.roll_appearance(18, gender="Female")
        assert not any(re.search("beard|mustache|moustache", f, re.I) for f in a["features"])


def test_finalise_keeps_dice_characteristics(rules):
    adv = finalise({"name": "Conroi", "characteristics": {"SIZ": 12, "DEX": 10, "STR": 12,
                    "CON": 12, "APP": "1d6+5"}}, rules, rules.combat)
    assert adv["characteristics"]["APP"] == "1D6+5" and adv["health"]["hit_points"] > 0


def test_finalise_keeps_battle_card_data(rules):
    # Saving a battle card in the editor must not strip its battle fields or
    # re-derive its printed stats (Knights of Lothian: card HP 31, formula 30).
    path = os.path.join(os.path.dirname(__file__), "..", "data", "examplecombat.json")
    with open(path, encoding="utf-8") as fh:
        card = json.load(fh)["adversaries"]["Knights of Lothian"]
    card["name"] = "Knights of Lothian"
    adv = finalise(copy.deepcopy(card), rules, rules.combat)
    for k in ("battle_card", "morale_minimum", "per_player", "ransom"):
        assert adv[k] == card[k]
    for k in ("hit_points", "knockdown", "major_wound", "unconscious"):
        assert adv["health"][k] == card["health"][k]
    for k in ("armor_points", "shield", "glory", "morale_loss", "knight_value"):
        assert adv["other"][k] == card["other"][k]
    assert adv["armour_desc"] == card["armour_desc"]
