"""Bring new example content from the shipped baseline into the user's library.

The app reads only the working ``combat.json`` once it exists, so fixes and
new cards added to ``examplecombat.json`` never reach the user by themselves.
These helpers compare the two and add what is missing — whole entries, and
fields a same-named entry lacks — without ever overwriting the user's values.
Replacing one entry with the shipped version is a separate, confirmed action.
"""

import copy

KINDS = ("adversaries", "encounters", "battles")
# Scaling keys differ in shape between legacy and roster encounters; adding
# one into the other would corrupt the definition.
_SKIP_FIELDS = {"roster", "core", "scaling", "per_player"}


def _differs_tracked(entry):
    return bool(entry.get("battle_card") or entry.get("battle_role"))


def _missing_fields(working_entry, base_entry):
    out = [k for k in base_entry if k not in working_entry and k not in _SKIP_FIELDS]
    w_other, b_other = working_entry.get("other"), base_entry.get("other")
    if isinstance(w_other, dict) and isinstance(b_other, dict):
        out += [f"other.{k}" for k in b_other if k not in w_other]
    return out


def examples_report(working, baseline):
    """What the baseline has that the working library doesn't.

    ``missing``: whole entries by kind. ``fields``: fields a same-named entry
    lacks. ``differs``: shipped battle cards / battle encounters whose shared
    fields differ from the user's copy (candidates for "Restore shipped card").
    """
    missing = {k: [] for k in KINDS}
    fields, differs = [], []
    for kind in KINDS:
        w, b = working.get(kind) or {}, baseline.get(kind) or {}
        for key, base_entry in b.items():
            if key not in w:
                missing[kind].append(key)
                continue
            mf = _missing_fields(w[key], base_entry)
            if mf:
                fields.append({"kind": kind, "key": key, "fields": mf})
            if _differs_tracked(base_entry):
                diff = [f for f in base_entry if f in w[key] and w[key][f] != base_entry[f]]
                if diff:
                    differs.append({"kind": kind, "key": key, "fields": diff})
    return {"missing": missing, "fields": fields, "differs": differs}


def merge_missing(working, baseline):
    """Insert missing entries and missing fields only. Returns the counts."""
    added = {"adversaries": 0, "encounters": 0, "battles": 0, "fields": 0}
    for kind in KINDS:
        b = baseline.get(kind) or {}
        if not b:
            continue
        w = working.setdefault(kind, {})
        for key, base_entry in b.items():
            if key not in w:
                w[key] = copy.deepcopy(base_entry)
                added[kind] += 1
                continue
            entry = w[key]
            for f in base_entry:
                if f not in entry and f not in _SKIP_FIELDS:
                    entry[f] = copy.deepcopy(base_entry[f])
                    added["fields"] += 1
            w_other, b_other = entry.get("other"), base_entry.get("other")
            if isinstance(w_other, dict) and isinstance(b_other, dict):
                for f in b_other:
                    if f not in w_other:
                        w_other[f] = copy.deepcopy(b_other[f])
                        added["fields"] += 1
    return added


def restore_entry(working, baseline, kind, key):
    """Replace one entry with a deep copy of the shipped version."""
    if kind not in KINDS or key not in (baseline.get(kind) or {}):
        raise KeyError(f"{key} is not in the shipped {kind}")
    working.setdefault(kind, {})[key] = copy.deepcopy(baseline[kind][key])
    return working[kind][key]
