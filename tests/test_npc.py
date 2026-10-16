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
