#!/usr/bin/env python3
"""
Rules data + NPC mechanics for the Pendragon name generator.

The source of truth is ``data/rules.json`` — a single structured file holding
every table the generator needs (Traits, Passions, Religion, Characteristics,
Distinctive Features, Directed Traits, and naming data). Adding new sourcebook
material is just a matter of adding keys to that file; the human-readable
``rules/*.md`` documents are reference only and are no longer parsed.

This module loads and validates the JSON, then exposes a ``Rules`` object whose
methods roll up the mechanical parts of an NPC.
"""

import json
import math
import os
import random

CHAR_ORDER = ("SIZ", "DEX", "STR", "CON", "APP")

# Top-level keys every valid data file must provide.
REQUIRED_KEYS = (
    "trait_pairs", "religions", "culture_religion", "passions",
    "characteristics", "appearance", "directed_traits", "naming", "manner",
)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _rhu(x):
    """Round half up, as the rulebook instructs (0.5 and above rounds up)."""
    return int(math.floor(x + 0.5))


def _roll(n, sides):
    return sum(random.randint(1, sides) for _ in range(n))


def _clamp(v, lo=1, hi=20):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Rules container + generation
# ---------------------------------------------------------------------------

class Rules:
    def __init__(self, data):
        self.data = data

        self.trait_pairs = [tuple(p) for p in data["trait_pairs"]]
        self.religions = data["religions"]
        self.culture_religion = data["culture_religion"]

        passions = data["passions"]
        self.passion_starts = passions["starting_values"]
        self.courts = passions["courts"]
        self.passion_targets = passions["targets"]

        self.char_cfg = data["characteristics"]
        self.siz_heights = {int(k): v for k, v in
                            self.char_cfg["siz_heights"].items()}

        appearance = data["appearance"]
        self.app_table = [tuple(row) for row in appearance["app_table"]]
        self.features = appearance["features"]
        self.eye_colours = appearance["eye_colours"]

        directed = data["directed_traits"]
        self.obsessions = [tuple(o) for o in directed["obsessions"]]
        self.obsession_objects = directed["obsession_objects"]
        self.directed_common = directed["common"]
        self.directed_fallback = directed["fallback"]

        naming = data["naming"]
        self.roman_nomen = naming["roman_nomen"]
        self.roman_honorifics = naming["roman_honorifics"]
        self.bynames = naming["bynames"]
        self.naming_notes = naming["notes"]
        self.pronunciation = naming["pronunciation"]

        self.manner = data["manner"]

        # Optional: social classes + skills.
        self.social_classes = data.get("social_classes", {})
        self.class_weights = data.get("class_weights", {})

    # -- social class + skills ---------------------------------------------

    def class_names(self):
        return list(self.social_classes)

    def roll_class(self):
        """Pick a random social class, weighted by class_weights."""
        classes = self.class_names()
        if not classes:
            return None
        weights = [self.class_weights.get(c, 1) for c in classes]
        return random.choices(classes, weights=weights)[0]

    def roll_skills(self, social_class):
        """Return {'skills': {name: value}, 'glory': int} for a class, or None."""
        info = self.social_classes.get(social_class)
        if not info:
            return None
        skills = {name: random.randint(lo, hi)
                  for name, (lo, hi) in info["skills"].items()}
        glory = random.randint(*info["glory"])
        return {"skills": skills, "glory": glory}

    # -- religion ----------------------------------------------------------

    def religion_for(self, culture):
        opts = self.culture_religion.get(culture)
        if opts:
            return random.choice(opts)
        return random.choice(list(self.religions)) if self.religions else "Pagan"

    def deity_for(self, religion):
        return self.religions.get(religion, {}).get("deity", "their god")

    # -- characteristics ---------------------------------------------------

    def roll_characteristics(self, culture):
        n, sides = self.char_cfg["roll_dice"]
        bonus = self.char_cfg["roll_bonus"]
        stats = {s: _roll(n, sides) + bonus for s in CHAR_ORDER}
        for stat, mod in self.char_cfg["cultural_modifiers"].get(culture, {}).items():
            stats[stat] = stats.get(stat, 0) + mod

        siz, dex, str_, con = stats["SIZ"], stats["DEX"], stats["STR"], stats["CON"]
        hp = con + siz
        derived = {
            "Hit Points": hp,
            "Move": _rhu((str_ + dex) / 2 + 5),
            "Damage": f"{max(1, _rhu((str_ + siz) / 6))}d6",
            "Healing Rate": max(1, _rhu(con / 5)),
            "Major Wound": con,
            "Knockdown": siz,
            "Unconscious": _rhu(hp / 4),
        }
        return stats, derived

    def height_for(self, siz):
        if not self.siz_heights:
            return ""
        nearest = min(self.siz_heights, key=lambda k: abs(k - siz))
        return self.siz_heights[nearest]

    # -- appearance --------------------------------------------------------

    def _app_row(self, app):
        for lo, hi, desc, npos, nneg, special in self.app_table:
            if lo <= app <= hi:
                return desc, npos, nneg, special
        return "Plain", 1, 1, None

    def _draw_features(self, polarity, n):
        """Return up to n (category, feature) pairs, preferring distinct categories."""
        if n <= 0:
            return []
        buckets = [(cat, feat) for cat, d in self.features.items()
                   for feat in d.get(polarity, [])]
        random.shuffle(buckets)
        chosen, used_cat, seen = [], set(), set()
        for cat, feat in buckets:  # prefer distinct categories first
            if cat not in used_cat:
                chosen.append((cat, feat))
                used_cat.add(cat)
                seen.add(feat)
            if len(chosen) >= n:
                return chosen
        for cat, feat in buckets:
            if feat not in seen:
                chosen.append((cat, feat))
                seen.add(feat)
            if len(chosen) >= n:
                break
        return chosen[:n]

    def roll_appearance(self, app):
        desc, npos, nneg, special = self._app_row(app)
        details = list(self._draw_features("positive", npos))
        details += self._draw_features("negative", nneg)
        if special:
            details.append((None, special.lower()))
        return {
            "descriptor": desc,
            "features": [feat for _cat, feat in details],
            "feature_details": [[cat, feat] for cat, feat in details],
            "eyes": random.choice(self.eye_colours),
        }

    # -- traits ------------------------------------------------------------

    def roll_traits(self, religion):
        if not self.trait_pairs:
            return []
        favoured = set(self.religions.get(religion, {}).get("favoured", []))
        chosen, used = [], set()

        # A defining religious virtue (16-19 on the favoured side).
        fav_pairs = [p for p in self.trait_pairs if favoured & {p[0], p[1]}]
        if fav_pairs:
            pair = random.choice(fav_pairs)
            virtue = pair[0] if pair[0] in favoured else pair[1]
            other = pair[1] if virtue == pair[0] else pair[0]
            val = random.randint(16, 19)
            chosen.append((virtue, val, other, 20 - val))
            used.add(pair)

        # A second, random personality trait (13-18 on a random side).
        remaining = [p for p in self.trait_pairs if p not in used]
        if remaining:
            left, right = random.choice(remaining)
            dominant, sub = random.choice([(left, right), (right, left)])
            val = random.randint(13, 18)
            chosen.append((dominant, val, sub, 20 - val))
        return chosen

    # -- passions ----------------------------------------------------------

    def _motivating_passion(self, exclude):
        # Prefer the dramatic Fervor/Fidelitas passions that take a target,
        # skipping the universals already on the block (Homage, Love (Family)).
        skip = {"Homage (Lord)", "Fealty", "Love (Family)"}
        pool = [p for court in ("Fervor", "Fidelitas")
                for p in self.courts.get(court, []) if p not in skip]
        random.shuffle(pool or ["Loyalty (Group)"])
        for template in (pool or ["Loyalty (Group)"]):
            name = template.replace("(Person or Group)",
                                    f"({random.choice(self.passion_targets)})")
            name = name.replace("(Group)", f"({random.choice(self.passion_targets)})")
            if name not in exclude:
                return name, random.randint(13, 18)
        return f"Hate ({random.choice(self.passion_targets)})", random.randint(13, 18)

    def roll_passions(self, religion):
        s = self.passion_starts
        deity = self.deity_for(religion)
        passions = [
            ("Honor", _clamp(s.get("Honor", 15) + random.randint(-2, 3))),
            ("Homage (Lord)", _clamp(s.get("Homage (Lord)", 15) + random.randint(-3, 2))),
            ("Love (Family)", _clamp(s.get("Love (Family)", 10) + random.randint(-2, 5))),
            (f"Devotion ({deity})", _clamp(s.get("Devotion (Deity)", 5) + random.randint(0, 6))),
        ]
        name, val = self._motivating_passion({n for n, _ in passions})
        passions.append((name, _clamp(val)))
        return passions

    # -- directed traits ---------------------------------------------------

    def roll_directed_trait(self):
        """Return a dict {'kind', 'text'} for a grudge/fear/obsession, or None."""
        if self.obsessions and random.random() < 0.25:
            name, _base = random.choice(self.obsessions)
            objects = self.obsession_objects.get(name, self.passion_targets)
            return {"kind": "Obsession", "text": f"{name} ({random.choice(objects)})"}

        pool = list(self.directed_common) + list(self.directed_fallback)
        if not pool:
            return None
        trait = random.choice(pool)
        target = random.choice(self.passion_targets)
        mod = random.choice([3, 5, 5, 5, 10])
        return {"kind": "Directed Trait", "text": f"*{trait} ({target}) +{mod}"}


# ---------------------------------------------------------------------------
# loading + validation
# ---------------------------------------------------------------------------

class RulesError(ValueError):
    """Raised when the data file exists but is malformed."""


def _validate(data):
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise RulesError(f"data/rules.json is missing keys: {', '.join(missing)}")
    if not data["trait_pairs"]:
        raise RulesError("data/rules.json has no trait_pairs")
    if not data["religions"]:
        raise RulesError("data/rules.json has no religions")
    if not data["appearance"].get("features"):
        raise RulesError("data/rules.json has no appearance.features")


def load_rules(path):
    """Load and validate the rules data.

    ``path`` may be the ``data/`` directory or the JSON file itself. Returns a
    ``Rules`` object, or ``None`` if the file is absent (name-only mode). Raises
    ``RulesError`` if the file exists but is invalid, so problems fail loudly.
    """
    if os.path.isdir(path):
        path = os.path.join(path, "rules.json")
    if not os.path.isfile(path):
        return None

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise RulesError(f"{path} is not valid JSON: {exc}") from exc

    _validate(data)
    return Rules(data)


if __name__ == "__main__":  # quick self-test
    here = os.path.dirname(os.path.abspath(__file__))
    rules = load_rules(os.path.join(here, "data"))
    if rules is None:
        print("data/rules.json not found.")
        raise SystemExit(1)
    print("schema_version:", rules.data.get("schema_version"))
    print("trait pairs:", len(rules.trait_pairs))
    print("religions:", list(rules.religions))
    print("feature categories:", {k: (len(v["positive"]), len(v["negative"]))
                                   for k, v in rules.features.items()})
    rel = rules.religion_for("Saxon")
    stats, derived = rules.roll_characteristics("Cymri")
    print("religion:", rel, "| stats:", stats)
    print("derived:", derived)
    print("appearance:", rules.roll_appearance(stats["APP"]))
    print("traits:", rules.roll_traits(rel))
    print("passions:", rules.roll_passions(rel))
    print("directed:", [rules.roll_directed_trait() for _ in range(3)])
