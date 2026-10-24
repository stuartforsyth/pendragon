"""Condense a session log into per-turn facts for the ``/recap`` skill.

Reads one session file (honouring strikes), keeps only what the players saw
(``visibility: public``), and prints Markdown: for each battle turn, the beats
in order, the notable moments (criticals, fumbles, foes slain or felled,
grievous blows to a knight, horses hit) and the Glory won. The narrator (Opus)
writes from this file, never from the raw log, so every name and number in the
recap traces back to a line here.

    .venv/bin/python -m core.recap_facts sessions/<id>.json
    .venv/bin/python -m core.recap_facts latest
"""

import json
import os
import re
import sys

from web.sessions import live_events

GRIEVOUS_DAMAGE = 25   # a single hit this big on a knight counts as grievous; the log records no Major Wound state for knights

BEATS = {
    "battle.set", "battle.charge", "battle.intensity", "battle.pick", "battle.select", "battle.morale",
    "battle.posture", "battle.barrage", "battle.countercharge", "battle.field", "battle.rest",
    "battle.day_ended", "battle.day_started", "battle.ended", "battle.mustered", "combat.started", "combat.distribute",
    "combat.engage", "combat.mounted", "combat.wield", "combat.break", "combat.status", "combat.ended",
}


def _text(ev):
    return ev["data"].get("table_text") or ev["text"]


def _clean(s):
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


def _blow_tags(ev):
    d, b = ev["data"], ev["data"].get("blow", {})
    tags = []
    if b.get("critical"):
        tags.append("CRITICAL")
    if d.get("mortal"):
        tags.append("SLAIN")
    elif d.get("major"):
        tags.append("MAJOR WOUND")
    elif "unconscious" in _text(ev):
        tags.append("FELLED (unconscious)")
    if d.get("to_knight"):
        tags.append("KNIGHT HIT")
        if d.get("at_horse"):
            tags.append("MOUNT HIT")
        elif b.get("critical") or b.get("full", 0) >= GRIEVOUS_DAMAGE:
            tags.append("GRIEVOUS")
    if d.get("glory_amount"):
        tags.append(f"+{d['glory_amount']} Glory to {ev['data']['attacker']}")
    return tags


def _notable(ev):
    """(tags, line) for a notable event, else None."""
    t, d = ev["type"], ev["data"]
    if t == "combat.blow":
        tags = _blow_tags(ev)
        if any(x in tags for x in ("CRITICAL", "SLAIN", "MAJOR WOUND", "FELLED (unconscious)", "GRIEVOUS", "MOUNT HIT")):
            return tags, _clean(_text(ev))
    elif t == "combat.attack" and re.search(r"critical|fumble", ev["text"]):
        return ["ATTACK ROLL"], _clean(ev["text"])
    elif t == "combat.note" and "fumble" in ev["text"]:
        return ["FUMBLE"], _clean(ev["text"])
    elif t == "combat.break":
        return ["WEAPON BREAKS"], _clean(_text(ev))
    elif t == "combat.status":
        return ["KNIGHT DOWN"], _clean(_text(ev))
    return None


def _descriptions(ev):
    out = []
    for desc in ev["data"].get("descriptions", []):
        out.append(f"{desc['type']}: {_clean(desc['text'].split('Mechanics:')[0]).rstrip('· ').strip()}")
    return out


def sections(events):
    """Split public events into turns, each closed by its ``battle.turn_ended``."""
    out, cur = [], []
    for ev in events:
        if ev.get("visibility") != "public":
            continue
        cur.append(ev)
        if ev["type"] == "battle.turn_ended":
            b = ev["data"]["battle"]
            out.append({"day": b["day"], "turn": b["turn"], "events": cur})
            cur = []
    if cur:
        out.append({"day": None, "turn": None, "events": cur})
    return out


def scripts(events):
    """{(day, turn): text} from the battle's scripted story, read off the definition the log carries."""
    for ev in events:
        definition = ev["data"].get("snapshot", {}).get("battle", {}).get("definition")
        if definition:
            return {(i, sc["turn"]): _clean(sc["text"])
                    for i, day in enumerate(definition.get("days", []), 1) for sc in day.get("scripts", [])}
    return {}


def facts(session):
    events = live_events(session["events"])
    story = scripts(events)
    lines = [f"# Facts: {session['title']}", ""]
    glory_seen, glory_final = {}, {}
    for sec in sections(events):
        head = "Closing" if sec["turn"] is None else f"Day {sec['day']}, Turn {sec['turn']}"
        lines += [f"## {head}", ""]
        beats, notes, desc, glory_gain, started = [], [], [], {}, None
        for ev in sec["events"]:
            t, d = ev["type"], ev["data"]
            if t == "combat.started":
                desc += _descriptions(ev)
            if t == "battle.set" and d.get("flavour"):
                desc.append(f"{d['encounter']}: {_clean(d['flavour'])}")
            if t == "combat.engage":
                desc.append(_clean(_text(ev)))
            if t == "battle.finale":
                s = d.get("summary", {})
                line = f"The battle ends: {s.get('outcome_label', '')} ({s.get('line', '')})"
                if line not in beats:      # the GM can re-save the finale; say it once
                    beats.append(line)
                continue
            if t in BEATS and t != "combat.engage":
                beats.append(_clean(_text(ev)))
            n = _notable(ev)
            if n:
                notes.append(f"[{' | '.join(n[0])}] {n[1]}")
            if t == "combat.blow" and d.get("glory_amount"):
                glory_gain[d["attacker"]] = glory_gain.get(d["attacker"], 0) + d["glory_amount"]
            if t == "combat.tally" and d.get("final"):
                glory_final.update({r["name"]: r["glory"] for r in d["ranking"]})
        if (sec["day"], sec["turn"]) in story:
            lines += ["Scripted story for this turn (the battle's own history; flavour only, the knights' part in it is\n"
                      "not recorded unless a beat below says so): " + story[(sec["day"], sec["turn"])], ""]
        lines += ["Beats, in order:"] + [f"- {b}" for b in beats] + [""]
        if desc:
            lines += ["Who was met (colour you may use):"] + [f"- {x}" for x in dict.fromkeys(desc)] + [""]
        lines += ["Notable moments:"] + ([f"- {x}" for x in notes] or ["- (none)"]) + [""]
        if glory_gain:
            lines += ["Glory logged this turn for foes defeated: " + ", ".join(f"{k} +{v}" for k, v in glory_gain.items()), ""]
    lines += ["## Glory from foes defeated (running total; battle Glory is not calculated yet)", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(glory_final.items(), key=lambda kv: -kv[1])]
    return "\n".join(lines) + "\n"


def _resolve(arg, directory="sessions"):
    if arg != "latest":
        return arg
    files = [f for f in os.listdir(directory) if f.endswith(".json")]
    return os.path.join(directory, max(files, key=lambda f: os.path.getmtime(os.path.join(directory, f))))


if __name__ == "__main__":
    path = _resolve(sys.argv[1] if len(sys.argv) > 1 else "latest")
    with open(path, encoding="utf-8") as fh:
        print(facts(json.load(fh)), end="")
