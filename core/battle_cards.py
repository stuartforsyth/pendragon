"""Opportunity cards as the table reads them: the printed faces.

``data/battle_cards.json`` holds a verbatim transcription of each shipped
Opportunity card — ``front`` faces (the instructions the players read),
``back`` faces (the stat blocks only the GM sees) and the Glory ``rewards``
printed on it. An Opportunity with no transcription (a card of the user's own)
gets a generated card from its description, rules text and roster.
"""

import json
import os

FILE = "battle_cards.json"


def load(data_dir, root=None):
    """The transcribed cards: the working data dir first, then the shipped copy."""
    for base in (data_dir, os.path.join(root, "data") if root else None):
        path = os.path.join(base, FILE) if base else None
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh).get("cards", {})
    return {}


def _stat_face(name, adv_name, adv):
    ch = adv.get("characteristics", {})
    health, other = adv.get("health", {}), adv.get("other", {})
    shield = other.get("shield")
    armour = f"{other.get('armor_points', 0)}+{shield}" if shield else str(other.get("armor_points", 0))
    lines = []
    if adv.get("armour_desc"):
        lines.append(["Armor", adv["armour_desc"]])
    for label, key in (("Traits", "traits"), ("Skills", "skills"), ("Passions", "passions")):
        if adv.get(key):
            lines.append([label, ", ".join(f"{k} {v}" for k, v in adv[key].items())])
    ransom = (adv.get("ransom") or [{}])[0].get("amount", "")
    return {"title": name, "subtitle": adv_name,
            "chars": [[k, str(ch[k])] for k in ("SIZ", "DEX", "STR", "CON") if k in ch],
            "attacks": [[a.get("weapon", ""), a.get("skill", ""), str(a.get("value", "")), a.get("damage", "")]
                        for a in adv.get("attacks", [])],
            "health": [["Hit Points", str(health.get("hit_points", ""))], ["Knockdown", str(health.get("knockdown", ""))],
                       ["Major Wound", str(health.get("major_wound", ""))], ["Unconscious", str(health.get("unconscious", ""))]],
            "other": [["Morale Loss", str(other.get("morale_loss", ""))], ["Armor Points", armour],
                      ["Glory Award", str(other.get("glory", ""))], ["Knight Value", str(other.get("knight_value", ""))]],
            "lines": lines, "ransom": ransom}


def faces(cards, name, encounter=None, adversaries=None):
    """``{"front": [...], "back": [...], "rewards": [...]}`` for one Opportunity."""
    card = cards.get(name)
    if card:
        return {"front": card.get("front", []), "back": card.get("back", []), "rewards": card.get("rewards", [])}
    enc = encounter or {}
    blocks = [{"p": line} for line in (enc.get("rules") or "").split("\n") if line.strip()]
    front = [{"title": name, "flavour": enc.get("description", ""), "blocks": blocks,
              "footer": {"label": "Morale Minimum", "value": str(enc.get("morale_minimum", ""))}
              if enc.get("morale_minimum") is not None else None}]
    back = []
    for line in enc.get("roster") or []:
        adv = (adversaries or {}).get(line.get("adversary"))
        if adv:
            back.append(_stat_face(name, line["adversary"], adv))
    return {"front": front, "back": back, "rewards": []}
