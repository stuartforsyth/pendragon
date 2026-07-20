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
import re

CHAR_ORDER = ("SIZ", "DEX", "STR", "CON", "APP")

_EXPR_TOKEN = re.compile(r"([+-]?)(\d+)[dD](\d+)|([+-]?)(\d+)")


def roll_expr(expr):
    """Roll a dice expression like '2D6+4', '5D6', '1D6+10', or a plain '12'.

    Sums each NdM term and each constant, honouring + / - signs. Returns an int.
    """
    total = 0
    for m in _EXPR_TOKEN.finditer(str(expr).replace(" ", "")):
        if m.group(3):  # a dice term NdM
            sign = -1 if m.group(1) == "-" else 1
            n, faces = int(m.group(2)), int(m.group(3))
            total += sign * sum(random.randint(1, faces) for _ in range(n))
        elif m.group(5) is not None:  # a constant
            sign = -1 if m.group(4) == "-" else 1
            total += sign * int(m.group(5))
    return total

# Top-level keys every valid data file must provide.
REQUIRED_KEYS = (
    "trait_pairs", "religions", "culture_religion", "passions",
    "characteristics", "appearance", "directed_traits", "naming", "trait_manner",
)

# A trait value of 16+ is "Famous" — it may dictate how the character acts.
FAMOUS_THRESHOLD = 16


def _phrase_feature(category, feat):
    """Turn a bare distinctive feature into a readable phrase (hair/voice/build)."""
    low = feat.lower()
    if category == "Hair" and "hair" not in low and low not in ("bald", "balding"):
        return f"{feat} hair"
    if category == "Speech" and "accent" not in low and low not in ("lisp", "stutter"):
        return f"{feat} voice"
    if category == "Physique" and " " not in feat:
        return f"{feat} build"
    return feat


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

        tm = data["trait_manner"]
        self.demeanour_lefts = set(tm["layers"]["demeanour"])
        self.moral_lefts = set(tm["layers"]["moral"])
        self.trait_surface = tm["surface"]
        self.trait_at_heart = tm["at_heart"]
        self.manner_connectors = tm.get("connectors", ["but"])

        # Optional: social classes + skills.
        self.social_classes = data.get("social_classes", {})
        self.class_weights = data.get("class_weights", {})

        # Optional: combat data (loaded from data/combat.json by load_rules).
        self.combat = None
        self.data_dir = ""  # set by load_rules; where combat.json is written

    # -- social class + skills ---------------------------------------------

    def class_names(self):
        return list(self.social_classes)

    def class_allows(self, social_class, gender):
        """Is this class valid for the given gender? (empty/absent = any)."""
        allowed = self.social_classes.get(social_class, {}).get("genders")
        return not allowed or gender in allowed

    def classes_for(self, gender):
        """Class names valid for a gender (all if gender is None)."""
        if gender is None:
            return self.class_names()
        return [c for c in self.class_names() if self.class_allows(c, gender)]

    def roll_class(self, gender=None):
        """Pick a random social class valid for gender, weighted by class_weights."""
        classes = self.classes_for(gender)
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

        return stats, self.derive_stats(stats)

    @staticmethod
    def derive_stats(stats):
        """The derived stats computed from a set of characteristics (pure)."""
        siz, dex, str_, con = stats["SIZ"], stats["DEX"], stats["STR"], stats["CON"]
        hp = con + siz
        return {
            "Hit Points": hp,
            "Move": _rhu((str_ + dex) / 2 + 5),
            "Damage": f"{max(1, _rhu((str_ + siz) / 6))}d6",
            "Healing Rate": max(1, _rhu(con / 5)),
            "Major Wound": con,
            "Knockdown": siz,
            "Unconscious": _rhu(hp / 4),
        }

    def height_for(self, siz):
        if not self.siz_heights:
            return ""
        nearest = min(self.siz_heights, key=lambda k: abs(k - siz))
        return self.siz_heights[nearest]

    # -- appearance --------------------------------------------------------

    def random_appearance_feature(self):
        """One describable feature (e.g. 'a broken nose', 'flowing hair').

        Drawn from Face/Hair (the most 'defining' categories for a combatant)
        and phrased for readability.
        """
        cats = [c for c in ("Face", "Hair") if c in self.features] or list(self.features)
        if not cats:
            return ""
        cat = random.choice(cats)
        pools = self.features[cat]
        polarity = random.choice([p for p in ("positive", "negative") if pools.get(p)]
                                 or list(pools))
        pool = pools.get(polarity, [])
        if not pool:
            return ""
        return _phrase_feature(cat, random.choice(pool))

    def random_eye_colour(self):
        return random.choice(self.eye_colours) if self.eye_colours else ""

    def random_standout_features(self, n=2):
        """A few distinctive physical features so combatants don't all read alike.

        Draws across *every* category (Physique, Limbs, Hair, Face, Speech) —
        preferring distinct categories — rather than just Face/Hair, so you get
        build/limbs/voice variety too. Eye-colour descriptors are skipped because
        eye colour is rolled separately (avoids 'blue eyes, blue eyes').
        """
        buckets = [(cat, feat) for cat, pols in self.features.items()
                   for items in pols.values() for feat in items
                   if "eyes" not in feat.lower()]
        random.shuffle(buckets)
        chosen, used_cat = [], set()
        for cat, feat in buckets:
            if cat in used_cat:
                continue
            used_cat.add(cat)
            chosen.append(_phrase_feature(cat, feat))
            if len(chosen) >= n:
                break
        return chosen

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
        """Generate all 13 trait pairs by the rulebook Random Method.

        Roll 2D6+3 for each left-hand trait (Valorous 2D6+8); +3 if that trait
        is one of the religion's virtues, -3 if its opposite is. Right = 20-left.
        Returns a list of (left, left_value, right, right_value).
        """
        favoured = set(self.religions.get(religion, {}).get("favoured", []))
        profile = []
        for left, right in self.trait_pairs:
            val = _roll(2, 6) + (8 if left == "Valorous" else 3)
            if left in favoured:
                val += 3
            elif right in favoured:
                val -= 3
            val = _clamp(val, 0, 20)
            profile.append((left, val, right, 20 - val))
        return profile

    def compose_manner(self, profile):
        """Compound manner: a surface demeanour trait + an 'at heart' moral one."""
        def dominant(candidates):  # most pronounced pair -> (pole, deviation)
            best = None
            for left, lval, right, rval in candidates:
                pole = left if lval >= rval else right
                deviation = abs(lval - 10)
                if best is None or deviation > best[1]:
                    best = (pole, deviation)
            return best[0] if best else None

        surface_pole = dominant([p for p in profile if p[0] in self.demeanour_lefts])
        heart_pole = dominant([p for p in profile if p[0] in self.moral_lefts])

        surface = (random.choice(self.trait_surface[surface_pole])
                   if surface_pole in self.trait_surface else "")
        heart = (random.choice(self.trait_at_heart[heart_pole])
                 if heart_pole in self.trait_at_heart else "")

        if surface and heart:
            return f"{surface}, {random.choice(self.manner_connectors)} {heart} at heart"
        return surface or heart

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
    rules = Rules(data)
    rules.data_dir = os.path.dirname(path)  # where combat.json is written

    # Optional combat data (Encounter/Adversary tabs); absent = combat off.
    # The tracked baseline is examplecombat.json; the app copies it to a
    # git-ignored working combat.json on first edit (see the creator specs).
    # Prefer the working file, fall back to the baseline.
    data_dir = os.path.dirname(path)
    combat_path = _combat_path(data_dir)
    if os.path.isfile(combat_path):
        try:
            with open(combat_path, encoding="utf-8") as fh:
                rules.combat = json.load(fh)
        except json.JSONDecodeError as exc:
            raise RulesError(f"{combat_path} is not valid JSON: {exc}") from exc
        _unify_combat(rules.combat)

    return rules


# -- combat data: working/example paths, schema unification, writer -----------

def working_combat_path(data_dir):
    """The live, git-ignored working file (written by the creators)."""
    return os.path.join(data_dir, "combat.json")


def example_combat_path(data_dir):
    """The tracked, read-only baseline shipped with the app."""
    return os.path.join(data_dir, "examplecombat.json")


def _combat_path(data_dir):
    """Prefer the working file; fall back to the shipped baseline."""
    working = working_combat_path(data_dir)
    return working if os.path.isfile(working) else example_combat_path(data_dir)


def _unify_combat(combat):
    """Expose one canonical model regardless of legacy/new key names.

    Canonical keys are ``adversaries`` and ``encounters``. Files may still use
    the legacy ``enemy_templates`` / ``encounter_themes`` names; either way both
    names end up referring to the *same* dict objects, and every adversary gets
    default ``kind``/``category`` so generic/named and human/beast are explicit.
    """
    adv = combat.get("adversaries")
    if adv is None:
        adv = combat.get("enemy_templates", {})
    for entry in adv.values():
        entry.setdefault("kind", "generic")
        entry.setdefault("category", "human")
    combat["adversaries"] = adv
    combat["enemy_templates"] = adv          # back-compat alias (same object)

    enc = combat.get("encounters")
    if enc is None:
        enc = combat.get("encounter_themes", {})
    combat["encounters"] = enc
    combat["encounter_themes"] = enc         # back-compat alias (same object)


def save_combat(combat, data_dir):
    """Write combat data to the working file (never the tracked baseline).

    Drops the back-compat alias keys so the file stays single-sourced under the
    canonical ``adversaries``/``encounters`` names.
    """
    out = {k: v for k, v in combat.items()
           if k not in ("enemy_templates", "encounter_themes")}
    path = working_combat_path(data_dir)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return path


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
