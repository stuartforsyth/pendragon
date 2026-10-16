"""Table 7.1 (Core p.133) for an enemy attacking a player knight."""

import pytest

from core.combat import resolve_attack

S = lambda crit, shield: {"critical": crit, "shield": shield}  # noqa: E731


@pytest.mark.parametrize("foe,knight,result,strike,kshield", [
    ("critical", "critical", "tie", S(False, True), True),     # crit vs crit: tie, no +4D6
    ("critical", "higher", "foe", S(True, True), False),       # knight's success is a partial
    ("critical", "lower", "foe", S(True, True), False),
    ("critical", "failure", "foe", S(True, False), False),     # no shield/parry
    ("critical", "fumble", "foe", S(True, False), False),
    ("success", "critical", "knight", None, True),             # foe's success is a partial
    ("success", "higher", "knight", None, True),
    ("success", "equal", "tie", S(False, True), True),
    ("success", "lower", "foe", S(False, True), False),
    ("success", "failure", "foe", S(False, False), False),
    ("success", "fumble", "foe", S(False, False), False),
    ("failure", "critical", "knight", None, False),            # foe failed: no shield
    ("failure", "lower", "knight", None, False),               # any knight success wins
    ("failure", "failure", "none", None, False),
    ("fumble", "higher", "knight", None, False),
    ("fumble", "fumble", "none", None, False),
])
def test_table_7_1(foe, knight, result, strike, kshield):
    r = resolve_attack(foe, knight)
    assert (r["result"], r["foe_strike"], r["knight_shield"]) == (result, strike, kshield)


def test_fumbles_reported():
    assert resolve_attack("fumble", "fumble")["fumbled"] == ["foe", "knight"]
    assert resolve_attack("success", "fumble")["fumbled"] == ["knight"]
