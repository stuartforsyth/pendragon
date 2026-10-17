import pytest
import json

from core.combat import Combatant, Encounter, resolve_roster
from core.encounter_def import preview_lines, roster_threat, to_editable


def _foe(rules):
    e = Encounter(rules)
    return e.add_one(sorted(e.templates)[0])


def test_combatant_round_trips_through_json(rules):
    c = _foe(rules)
    c.modifier = -5
    c2 = Combatant.from_dict(json.loads(json.dumps(c.to_dict())))
    assert c2.to_dict() == c.to_dict()
    assert c2.status == "active"


def test_major_and_mortal_wounds(rules):
    c = _foe(rules)
    _, msg = c.apply_hp(-c.major_wound)
    assert "Major Wound" in msg and c.status == "unconscious"
    c = _foe(rules)
    _, msg = c.apply_hp(-c.max_hp)
    assert "Mortal Wound" in msg and c.status == "dead"


def test_healing_revives_unconscious(rules):
    c = _foe(rules)
    c.apply_hp(-c.major_wound)
    _, msg = c.apply_hp(c.max_hp)
    assert "revived" in msg and c.status == "active"


def test_wound_state_hides_numbers(rules):
    c = _foe(rules)
    assert c.wound_state() == "Unhurt"
    c.cur_hp = c.max_hp - 1
    assert c.wound_state() == "Wounded"
    c.cur_hp = c.max_hp // 2
    assert c.wound_state() == "Badly wounded"
    c.set_out("fled")
    assert c.wound_state() == "Fled"


def test_party_member_has_no_health():
    c = Combatant.from_party({"id": "p1", "name": "Sir Bors", "player": "Ann"})
    assert (c.side, c.status, c.wound_state()) == ("party", "active", "")
    with pytest.raises(ValueError):
        c.apply_hp(-50)                     # players keep knights' HP on paper
    c.set_out("unconscious")
    assert (c.status, c.wound_state()) == ("unconscious", "Down")
    c.set_out("fled")
    assert c.wound_state() == "Out of the fight"


def test_promote_is_deterministic_and_reversible(rules):
    c = _foe(rules)
    before = c.to_dict()
    c.promote({"skill_bonus": 5, "hp_multiplier": 1.5})
    assert c.elite and c.max_hp >= before["max_hp"]
    c.demote()
    assert not c.elite and c.max_hp == before["max_hp"]


def test_roster_scaling_and_preview(rules):
    defn = {"roster": [{"adversary": "A", "count": 1.5, "per_player": True},
                       {"adversary": "B", "count": 1, "per_player": False}],
            "leader": {"adversary": "C", "promote": True}}
    assert resolve_roster(defn, 4) == [("A", 6, False), ("B", 1, False)]
    lines, total = preview_lines(defn, 4)
    assert total == 8 and lines[-1].startswith("1× C")
    glory, hp = roster_threat(defn, 4, {"adversaries": {"A": {"health": {"hit_points": 10}}}})
    assert hp == 60


def test_every_library_encounter_builds(rules):
    e = Encounter(rules)
    for name, defn in e.themes.items():
        editable = to_editable(defn)
        if not editable["roster"] and not editable.get("leader") and defn.get("battle_role") == "opportunity":
            continue                     # an Opportunity may have nothing to fight (Rally the Division!)
        e.generate_from_definition(editable, 3)
        assert e.combatants, name


def test_per_player_counts_round_half_up():
    # Battle cards say "rounded normally": 1.5 per knight for 3 knights is 4.5 -> 5, not 4.
    defn = {"roster": [{"adversary": "A", "count": 1.5, "per_player": True}]}
    assert resolve_roster(defn, 3) == [("A", 5, False)]
    assert resolve_roster(defn, 7) == [("A", 11, False)]


def test_surrendered_status_and_word(rules):
    c = _foe(rules)
    c.set_out("surrendered")
    assert c.status == "surrendered" and c.down and c.wound_state() == "Surrendered"


def test_old_snapshot_without_new_fields_replays(rules):
    c = _foe(rules)
    old = c.to_dict()
    for k in ("mounted", "attacks_horse", "captured_by", "posture", "position"):
        old.pop(k, None)
    c2 = Combatant.from_dict(old)
    assert c2.mounted is False and c2.captured_by is None and c2.extra_rounds == 0
    assert Combatant.from_dict(c2.to_dict()).to_dict() == c2.to_dict()
