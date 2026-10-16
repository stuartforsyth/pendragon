"""Encounter definitions: reusable recipes (which adversaries, how many, how
they scale with party size) that the tracker turns into a live fight."""

import copy

from core.combat import resolve_roster


def blank_encounter():
    return {
        "source": "user", "name": "", "description": "", "tags": [],
        "roster": [], "leader": None, "notes": "",
    }


def _fmt_count(v):
    """Display a count value: whole numbers without a trailing '.0'."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def to_editable(defn):
    """An editable copy in the self-scaling roster shape.

    New-shape definitions pass through. Legacy definitions are migrated: a global
    ``scaling`` block is folded into each roster line's own multiplier, and a
    legacy random pool (``core`` + ``per_player``) becomes explicit per-player
    roster lines.
    """
    if "roster" in defn:
        d = copy.deepcopy(blank_encounter())
        d.update(copy.deepcopy(defn))
        scaling = d.pop("scaling", None)
        factor = 1.0
        if isinstance(scaling, dict) and scaling.get("mode", "per_player") == "per_player":
            factor = scaling.get("per_player", 1.0)
        for line in d["roster"]:
            if "per_player" in line:
                continue  # already self-scaling
            if line.get("count") == "per_player":   # migrate legacy scaled line
                line["per_player"] = True
                line["count"] = factor
            else:                                   # migrate legacy fixed line
                line["per_player"] = False
        return d
    d = blank_encounter()
    d["name"] = defn.get("name", "")
    core = defn.get("core", [])
    # Legacy pool (per_player × players): split the factor across the pool's
    # members so the converted roster totals the same, not ×len(core).
    factor = defn.get("per_player", 1.0) / max(1, len(core))
    for adv in core:
        d["roster"].append({"adversary": adv, "count": factor,
                            "per_player": True, "promote": False})
    lead = defn.get("leader")
    if lead:
        d["leader"] = {"adversary": lead, "promote": True}
    return d


def preview_lines(defn, n_players):
    """Human-readable '4× Bandit' preview lines + total, for the editor."""
    counts = {}
    order = []
    for adv, n, promote in resolve_roster(defn, n_players):
        key = (adv, promote)
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + n
    lines = []
    for adv, promote in order:
        tag = " (promoted)" if promote else ""
        lines.append(f"{counts[(adv, promote)]}× {adv}{tag}")
    leader = defn.get("leader")
    total = sum(counts.values())
    if isinstance(leader, dict) and leader.get("adversary"):
        tag = " (promoted)" if leader.get("promote", True) else ""
        lines.append(f"1× {leader['adversary']} — leader{tag}")
        total += 1
    return lines, total


def roster_threat(defn, n_players, combat):
    """Total Glory and Hit Points across the resolved roster — a rough threat
    gauge, so a lone Dragon (1000 Glory) reads as more dangerous than a mob."""
    advs = combat.get("adversaries", {})
    glory = hp = 0
    rows = list(resolve_roster(defn, n_players))
    leader = defn.get("leader")
    if isinstance(leader, dict) and leader.get("adversary"):
        rows.append((leader["adversary"], 1, False))
    for adv, n, _promote in rows:
        a = advs.get(adv, {})
        glory += a.get("other", {}).get("glory", 0) * n
        hp += a.get("health", {}).get("hit_points", 0) * n
    return glory, hp
