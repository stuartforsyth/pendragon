import pytest

from core.dice import (NotationError, notation_breakdown, resolve_characteristic,
                       resolve_opposed, resolve_skill, roll_notation, skill_display)


@pytest.mark.parametrize("value,roll,outcome", [
    (12, 12, "critical"), (12, 5, "success"), (12, 13, "failure"),
    (12, 20, "fumble"), (20, 20, "critical"), (20, 19, "success"),
    (22, 18, "critical"), (22, 17, "success"), (22, 1, "success"),
])
def test_resolve_skill(value, roll, outcome):
    assert resolve_skill(value, roll) == (roll, outcome)


def test_characteristic_is_pass_fail_only():
    assert resolve_characteristic(10, 10) == (10, "success")
    assert resolve_characteristic(10, 20) == (20, "failure")


def test_skill_display():
    assert skill_display(15) == "15"
    assert skill_display(23) == "20 (+3)"


@pytest.mark.parametrize("a,b,ar,br,ares,bres,winner", [
    (15, 15, 10, 8, "win", "partial", "a"),        # both succeed, higher wins
    (15, 15, 9, 9, "tie", "tie", None),            # same roll
    (15, 15, 15, 14, "win", "partial", "a"),       # critical beats success
    (10, 15, 10, 15, "tie", "tie", None),          # both critical
    (15, 15, 10, 18, "win", "loss", "a"),          # only one succeeds
    (5, 5, 10, 12, "mutual failure", "mutual failure", None),
    (1, 15, 1, 14, "win", "partial", "a"),  # a value-1 critical still wins
    (23, 15, 14, 14, "win", "partial", "a"),       # +3 bonus makes it 17 > 14
])
def test_opposed(a, b, ar, br, ares, bres, winner):
    r = resolve_opposed(a, b, ar, br)
    assert (r["a"]["result"], r["b"]["result"], r["winner"]) == (ares, bres, winner)


def test_notation_rolls_in_range():
    for _ in range(200):
        r = roll_notation("3d6+2")
        assert 5 <= r["total"] <= 20
        assert len(r["terms"][0]["rolls"]) == 3


def test_notation_bare_die_and_subtraction():
    r = roll_notation("d20-1d4+3")
    assert [t.get("count") for t in r["terms"]] == [1, 1, None]
    assert r["terms"][1]["sign"] == -1
    assert notation_breakdown(r).endswith(f"= {r['total']}")


@pytest.mark.parametrize("bad", ["", "hello", "3d", "2d6 3", "1000d6", "d1"])
def test_notation_rejects_garbage(bad):
    with pytest.raises(NotationError):
        roll_notation(bad)
