"""Table 7.1 (Core p.133): every cell, with fixed rolls. Side a = the foe,
side b = the player knight, both on skill 15 unless noted."""

import pytest

from core.combat import resolve_exchange

SPEAR = ("Spear", {"skill": "Spear"})
SWORD = ("Sword", {"skill": "Sword"})


def ex(ar, br, av=15, bv=15, aw=SPEAR, bw=SWORD):
    return resolve_exchange(av, bv, ar, br, aw, bw)


@pytest.mark.parametrize("ar,br,strikes", [
    # knight critical vs foe: crit beats success/fail/fumble -> knight strikes +4D6
    (10, 15, [{"by": "b", "critical": True, "shield": True}]),    # foe success -> partial, keeps shield
    (18, 15, [{"by": "b", "critical": True, "shield": False}]),   # foe fails -> no shield
    (20, 15, [{"by": "b", "critical": True, "shield": False}]),   # foe fumbles
    (15, 15, [{"by": "a", "critical": False, "shield": True},     # crit vs crit: tie, no +4D6
              {"by": "b", "critical": False, "shield": True}]),
    # knight success
    (8, 12, [{"by": "b", "critical": False, "shield": True}]),    # knight higher: wins, foe partial
    (12, 8, [{"by": "a", "critical": False, "shield": True}]),    # knight lower: foe wins, knight partial
    (9, 9, [{"by": "a", "critical": False, "shield": True},       # equal: tie, both strike
            {"by": "b", "critical": False, "shield": True}]),
    (18, 12, [{"by": "b", "critical": False, "shield": False}]),  # foe fails
    (15, 12, [{"by": "a", "critical": True, "shield": True}]),    # foe crits: knight partial
    # knight fails / fumbles
    (12, 18, [{"by": "a", "critical": False, "shield": False}]),
    (15, 18, [{"by": "a", "critical": True, "shield": False}]),
    (12, 20, [{"by": "a", "critical": False, "shield": False}]),
    (18, 19, []),                                                 # both fail: nobody hurt
    (20, 20, []),
])
def test_table_7_1(ar, br, strikes):
    assert ex(ar, br)["strikes"] == strikes


def test_fumbles_drop_or_break():
    r = ex(12, 20)                       # knight (sword) fumbles: drops it
    assert r["weapons"] == [{"side": "b", "what": "drops", "weapon": "Sword"}]
    r = ex(20, 12)                       # foe (spear) fumbles: breaks it
    assert r["weapons"] == [{"side": "a", "what": "breaks", "weapon": "Spear"}]
    r = ex(18, 20)                       # both fail, knight fumbles: still drops
    assert r["strikes"] == [] and r["weapons"][0]["side"] == "b"


def test_sword_breaks_sword_on_crit_vs_fumble():
    r = ex(20, 15, aw=SWORD, bw=SWORD)   # foe fumbles, knight crits with a sword
    assert r["weapons"] == [{"side": "a", "what": "breaks", "weapon": "Sword"}]


def test_sword_breaks_other_weapons_on_a_tie():
    r = ex(9, 9)                         # spear vs sword tie
    assert r["weapons"] == [{"side": "a", "what": "breaks", "weapon": "Spear"}]
    assert ex(9, 9, aw=("Dagger", {"skill": "Brawling"}))["weapons"] == []


def test_critical_bonus_value_over_20():
    r = resolve_exchange(23, 15, 17, 14)   # 20(+3): 17 is a critical
    assert r["strikes"] == [{"by": "a", "critical": True, "shield": True}]
