"""resolve_blow against the corpus rules, with fixed dice."""

import pytest

from core.combat import blow_breakdown, resolve_blow

FIXED = {"4D6": 14, "5D6": 18, "2D6": 7, "6D6": 21, "1D6": 4}


def fake_roll(expr):
    total = FIXED[expr.upper()]
    return {"expr": expr.upper(), "terms": [{"rolls": [total]}], "total": total}


def blow(**kw):
    return resolve_blow(roll_fn=fake_roll, **kw)


def test_normal_hit_minus_armour_only():
    b = blow(expr="5D6", armour=10, shield=6, shield_applies=False)
    assert (b["full"], b["wound"]) == (18, 8)


def test_partial_success_adds_shield():
    b = blow(expr="5D6", armour=10, shield=6, shield_applies=True)
    assert b["wound"] == 2


def test_critical_adds_flat_4d6():
    b = blow(expr="5D6", critical=True, armour=10)
    assert (b["full"], b["wound"]) == (32, 22)


def test_unarmed_critical_adds_2d6():
    assert blow(expr="2D6", critical=True, unarmed=True)["full"] == 14


def test_rebated_critical_halves_after_bonus_and_knockdown_uses_full():
    b = blow(expr="5D6", critical=True, rebated=True, armour=10, knockdown=14)
    assert (b["full"], b["damage"], b["wound"], b["knockdown"]) == (32, 16, 6, "automatic")


def test_rebated_rounds_up():
    assert blow(rolled=15, rebated=True)["damage"] == 8


def test_knockdown_check_vs_automatic():
    assert blow(rolled=15, knockdown=14)["knockdown"] == "check"
    assert blow(rolled=14, knockdown=14)["knockdown"] is None
    assert blow(rolled=29, knockdown=14)["knockdown"] == "automatic"


def test_reckless_bonus_and_no_shield():
    b = blow(expr="5D6", reckless=True, armour=5, shield=6, shield_applies=True)
    assert (b["full"], b["shield_blocked"], b["wound"]) == (25, 0, 20)
    assert blow(expr="5D6", reckless=True, critical=True)["full"] == 39   # +6D6, not +4D6


@pytest.mark.parametrize("d6,blocked,broken", [(4, 4, False), (1, 1, True), (6, 5, False)])
def test_axe_through_shield(d6, blocked, broken):
    b = blow(rolled=20, shield=5, shield_applies=True, through_shields=True, d6=d6)
    assert (b["shield_blocked"], b["shield_broken"], b["wound"]) == (blocked, broken, 20 - blocked)


def test_extra_dice_vs_mail_and_breakdown():
    b = blow(expr="4D6", extra="1D6", armour=10)
    assert b["full"] == 18 and blow_breakdown(b).endswith("→ 8 damage")


def test_armour_never_heals():
    assert blow(rolled=3, armour=10)["wound"] == 0


def test_blow_narrative_is_one_sentence():
    from core.combat import blow_narrative
    n = lambda **k: blow_narrative(attacker="Sir Erik the Cruel", weapon="Sword", target="Pictish Knifemen 7", amount=23, to_knight=False, **k)
    assert n(fate="Slain", knockdown="automatic") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who is knocked down and slain!"
    assert n(fate="Slain", knockdown="check") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who is slain."
    assert n(fate="Wounded", knockdown="check") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who is wounded and must roll DEX or be knocked down."
    assert n(fate="Wounded") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who is wounded."
    assert n(fate="Major Wound") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who falls with a Major Wound."
    assert n(fate="Unconscious", knockdown="automatic") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who is knocked down and out cold!"
    assert n(fate="", knockdown="automatic") == "Sir Erik the Cruel’s sword inflicts 23 points of damage on Pictish Knifemen 7, who is knocked down!"
    k = blow_narrative(attacker="Pictish Knifemen 7", weapon="Dagger", target="Sir Erik the Cruel", amount=9, to_knight=True, knockdown="check")
    assert k == "Pictish Knifemen 7’s dagger inflicts 9 points of damage on Sir Erik the Cruel, who must roll DEX or be knocked down."
    assert blow_narrative(attacker="Sir Erik the Cruel", weapon="Sword", target="Pictish Knifemen 7", amount=0, to_knight=False) \
        == "Sir Erik the Cruel’s sword strikes Pictish Knifemen 7, but armour turns the blow aside."
