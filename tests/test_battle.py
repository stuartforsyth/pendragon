from fractions import Fraction

import pytest

from core import battle as B


def test_sizes_table():
    assert B.SIZES["large"]["turns"] == 8
    assert B.SIZES["large"]["intensity"] == "3D6"
    assert B.SIZES["large"]["participation"] == 45
    assert not B.SIZES["fight"]["army_rolls"] and not B.SIZES["skirmish"]["army_rolls"]
    assert B.SIZES["clash"]["army_rolls"]


def test_army_effects():
    assert B.army_effects("friendly", "success") == {"first_charge": True}
    assert B.army_effects("friendly", "fumble") == {"first_charge": False, "minus5": True}
    assert B.army_effects("enemy", "critical") == {"force_token": True}
    assert B.army_effects("enemy", "fumble") == {"negate_token": True}
    assert B.army_effects("enemy", "failure") == {}


def test_charge_opportunity_table():
    # Table 6.3: (outcome, engaged last round) -> result
    assert B.charge_opportunity("critical", True) == "may_charge"
    assert B.charge_opportunity("critical", False) == "may_charge_plus5"
    assert B.charge_opportunity("success", True) == "no_charge"
    assert B.charge_opportunity("success", False) == "may_charge"
    assert B.charge_opportunity("failure", True) == "no_charge"
    assert B.charge_opportunity("failure", False) == "no_charge"
    assert B.charge_opportunity("fumble", True) == "enemy_charge"
    assert B.charge_opportunity("fumble", False) == "enemy_charge"


def test_charge_lines_for_foot_knights():
    assert B.charge_line("may_charge_plus5", True) == "Charges +5"
    assert B.charge_line("may_charge", False) == "On foot — no charge"
    assert "Set Spear" in B.charge_line("enemy_charge", False)
    assert B.charge_line("enemy_charge", True) == "Enemy knights charge!"


def test_posture_delta():
    assert B.posture_delta("reckless", 2) == 2
    assert B.posture_delta("valorous") == 0
    assert B.posture_delta("prudent", 3) == -3
    assert B.posture_delta("cowardly", 4) == 0
    assert B.posture_delta("cowardly", 4, above_half=True) == -4
    with pytest.raises(ValueError):
        B.posture_delta("reckless", 4)
    with pytest.raises(ValueError):
        B.posture_delta("cowardly", 0, above_half=True)


def test_intensity_result():
    assert [B.intensity_result(o) for o in B.OUTCOMES] == ["doubled", "stands", "choose", "opportunity"]


def test_barrage_and_reach():
    assert [B.barrage_rounds(o) for o in B.OUTCOMES] == [0, 1, 2, 3]
    assert not B.reaches(1, 0, 2)
    assert not B.reaches(2, 0, 2)
    assert B.reaches(3, 0, 2)
    assert B.reaches(2, 1, 2)
    assert B.reaches(1, 0, 0)


def test_countercharge():
    assert B.countercharge(True, 6)
    assert B.countercharge(False, 1) and B.countercharge(False, 2)
    assert not any(B.countercharge(False, r) for r in (3, 4, 5, 6))


def test_height_cases():
    assert B.height(True, False) == (5, -5)
    assert B.height(False, True) == (-5, 5)
    assert B.height(False, True, attacks_horse=True) == (0, 5)
    assert B.height(True, True) == (0, 0)
    assert B.height(False, False) == (0, 0)
    assert B.height(False, True, override="none") == (0, 0)


def test_multiple_opponents_and_limit():
    assert B.multiple_opponents(1) == 0
    assert B.multiple_opponents(2) == -5
    assert B.multiple_opponents(3) == -10
    assert B.mo_limit(False) == 3 and B.mo_limit(True) == 2


def test_parse_kv_glyphs():
    assert B.parse_kv("1") == 1
    assert B.parse_kv("½") == Fraction(1, 2)
    assert B.parse_kv("¼") == Fraction(1, 4)
    assert B.parse_kv("⅛") == Fraction(1, 8)
    assert B.parse_kv("¾") == Fraction(3, 4)
    assert B.parse_kv("1/16") == Fraction(1, 16)
    assert B.parse_kv("3/4") == Fraction(3, 4)
    assert B.parse_kv("") == 0


def test_kv_morale_gain_rounds_half_up_per_encounter():
    e = Fraction(1, 8)
    assert B.kv_morale_gain([[e] * 3]) == 0
    assert B.kv_morale_gain([[e] * 4]) == 1
    assert B.kv_morale_gain([[1, e, e, e]]) == 1
    assert B.kv_morale_gain([[e] * 4, [e] * 4]) == 2


def test_outcome_thresholds_and_zero_ruling():
    assert B.outcome(4, 1) == "decisive_victory"
    assert B.outcome(Fraction(39, 10), 1) == "victory"
    assert B.outcome(2, 1) == "victory"
    assert B.outcome(Fraction(45, 100), 1) == "defeat"
    assert B.outcome(Fraction(1, 2), 1) == "indecisive"
    assert B.outcome(Fraction(1, 5), 1) == "decisive_defeat"
    assert B.outcome(2, 1, "we") == "decisive_victory"
    assert B.outcome(5, 0) == "decisive_victory"
    assert B.outcome(0, 0) == "indecisive"


def test_conroi_losses():
    assert B.conroi_losses("fumble", 10) == {"killed": 3, "captured": 2}
    assert B.conroi_losses("critical", 10) == {"killed": 0, "captured": 0}


def test_participation_glory():
    assert B.participation_glory("large", 2, "victory") == 135
    assert B.participation_glory("clash", 1, "victory", "conroi") == 35
    assert B.participation_glory("skirmish", 1, "victory", "conroi") == 8   # leader ignored


def test_plunder():
    assert B.plunder("feudal", "victory", size="large") == 2
    assert B.plunder("feudal", "decisive_victory", 4, "we", "conroi") == 4
    assert B.plunder("feudal", "defeat") == 0
    assert B.plunder("feudal", "victory", role="bataille", size="large") == 18
    assert B.plunder("feudal", "victory", role="army", size="clash") == Fraction(8, 3)  # no size mult


def test_apply_morale_caps_and_floors():
    assert B.apply_morale(20, 21, 4) == 21
    assert B.apply_morale(3, 21, -5) == 0
    assert B.apply_morale(10, 21, -2) == 8


def test_morale_band_edges():
    assert B.morale_band(16, 20) == "Steady"
    assert B.morale_band(15, 20) == "Shaken"
    assert B.morale_band(10, 20) == "Bloodied"
    assert B.morale_band(5, 20) == "Breaking"


def test_scale_roster_doubles_resolved_count():
    defn = {"roster": [{"adversary": "Knights of Lothian", "count": 1.5, "per_player": True}]}
    assert B.scale_roster(defn, 3) == [("Knights of Lothian", 5, False)]
    assert B.scale_roster(defn, 3, doubled=True) == [("Knights of Lothian", 10, False)]


def test_forced_retire():
    assert B.forced_retire(0, None)
    assert B.forced_retire(4, 5)
    assert not B.forced_retire(5, 5)


def test_default_morale_mixed_roster():
    advs = {"A": {"morale_minimum": 8, "other": {"morale_loss": "1D6"}},
            "B": {"morale_minimum": 13, "other": {"morale_loss": "2D6"}}}
    defn = {"roster": [{"adversary": "A"}, {"adversary": "B"}]}
    assert B.default_morale(defn, advs) == (13, "1D6")


def test_mounted_charge_card():
    advs = {"K": {"mounted": True, "countercharge": True}, "P": {}}
    assert B.mounted_charge_card({"roster": [{"adversary": "K"}]}, advs)
    assert not B.mounted_charge_card({"roster": [{"adversary": "P"}]}, advs)


def test_leader_default():
    assert B.leader_default(["a", "b", "b"]) == "b"
    assert B.leader_default(["a", "b"]) == "a"
    assert B.leader_default(["gm", None]) is None
