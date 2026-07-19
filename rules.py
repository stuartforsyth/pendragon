#!/usr/bin/env python3
"""
Rules data + NPC mechanics for the Pendragon name generator.

This module reads the Markdown reference files in ``rules/`` (extracted from the
Pendragon 5e Core Rulebook and Gamemaster's Handbook) and turns them into data
the GUI can use to roll up Personality Traits, Passions, Religion,
Characteristics, and Distinctive Features (appearance).

Editing the Markdown files changes what the generator produces; nothing here is
hard-coded from the rulebooks beyond the fixed derived-statistic formulas.
"""

import math
import os
import random
import re

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4}

# Which deity a Devotion Passion names, per religion.
DEITY = {
    "British Christian": "God",
    "Roman Christian": "God",
    "Pagan": "the Gods",
    "Wodinic": "Wodin",
}

# Eye colours drawn from the Face Distinctive Features list.
EYE_COLOURS = ["blue", "grey", "black", "brown", "hazel", "green", "pale blue"]

# Concrete objects used to fill in generic Passion templates like
# "Hate (Person or Group)".
PASSION_TARGETS = [
    "Saxons", "the King", "their lord", "a lost love", "their kin",
    "a rival house", "the Picts", "a fallen comrade", "a hated neighbour",
]


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


def _split_list(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def _table_rows(lines):
    """Yield column lists for each Markdown table row (skipping separators)."""
    for line in lines:
        s = line.strip()
        if s.startswith("|") and "---" not in s:
            yield [c.strip() for c in s.strip("|").split("|")]


def _simplify_religion(name):
    """'Wodinic / Wotanic (Saxon Heathenry)' -> 'Wodinic'."""
    name = name.split("(")[0].split("/")[0]
    return name.strip()


# ---------------------------------------------------------------------------
# parsers (one per reference file)
# ---------------------------------------------------------------------------

def _parse_trait_pairs(lines):
    pairs = []
    for cols in _table_rows(lines):
        if len(cols) == 2:
            left, right = cols
            if re.fullmatch(r"[A-Za-z]+", left) and re.fullmatch(r"[A-Za-z]+", right):
                pairs.append((left, right))
    return pairs


def _parse_religions(lines):
    religions = {}
    culture_map = {}
    current = None
    for line in lines:
        s = line.strip()
        if s.startswith("### "):
            current = _simplify_religion(s[4:])
            religions[current] = {"favoured": [], "benefit": "", "full": s[4:].strip()}
        elif current and s.startswith("- **Favoured Traits:**"):
            body = s.split("**Favoured Traits:**", 1)[1]
            religions[current]["favoured"] = _split_list(body)
        elif current and "benefit:**" in s:
            religions[current]["benefit"] = s.split("benefit:**", 1)[1].strip()
        elif s.startswith("|") and "---" not in s:
            cols = [c.strip() for c in s.strip("|").split("|")]
            if len(cols) == 2 and re.match(r"^[A-Za-z]", cols[0]) and "Culture" not in cols[0]:
                opts = [_simplify_religion(x) for x in re.split(r"\bor\b", cols[1])]
                culture_map[cols[0]] = [o for o in opts if o]
    return religions, culture_map


def _parse_passion_starts(lines):
    starts = {}
    for cols in _table_rows(lines):
        if len(cols) == 2 and re.fullmatch(r"\d+", cols[1]):
            name = re.sub(r"\s*[—-].*$", "", cols[0]).strip()
            starts[name] = int(cols[1])
    return starts


def _parse_courts(lines):
    courts = {}
    current = None
    for line in lines:
        s = line.strip()
        if s.startswith("### "):
            current = s[4:].split("(")[0].strip()
            courts[current] = []
        elif current and s.startswith("- **"):
            m = re.match(r"- \*\*(.+?)\*\*", s)
            if m:
                courts[current].append(m.group(1).strip())
    return courts


def _parse_app_table(lines):
    """Return list of (lo, hi, descriptor, n_positive, n_negative, special)."""
    rows = []
    for cols in _table_rows(lines):
        if len(cols) >= 3 and re.search(r"\d", cols[0]) and "APP" not in cols[0]:
            lo, hi = _parse_range(cols[0])
            npos, nneg, special = _parse_counts(cols[2])
            rows.append((lo, hi, cols[1], npos, nneg, special))
    return rows


def _parse_range(text):
    text = text.replace("–", "-").replace("—", "-")
    nums = re.findall(r"\d+", text)
    if "less" in text and nums:
        return 0, int(nums[0])
    if "+" in text and nums:
        return int(nums[0]), 99
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if nums:
        return int(nums[0]), int(nums[0])
    return 0, 99


def _parse_counts(desc):
    pos = neg = 0
    for m in re.finditer(r"(one|two|three|four)\s+(positive|negative)", desc.lower()):
        if m.group(2) == "positive":
            pos += WORDNUM[m.group(1)]
        else:
            neg += WORDNUM[m.group(1)]
    special = desc if (pos == 0 and neg == 0) else None
    return pos, neg, special


def _parse_features(lines):
    """Parse the Physique/Limbs/Hair/Face/Speech word lists (they wrap lines)."""
    features = {}
    cat = mode = None
    buf = []

    def flush():
        if cat and mode and buf:
            features.setdefault(cat, {"positive": [], "negative": []})
            features[cat][mode].extend(_split_list(" ".join(buf)))

    for line in lines:
        s = line.strip()
        if s.startswith("### "):
            flush(); buf, mode = [], None
            cat = s[4:].strip()
        elif s.startswith("**Positive:**"):
            flush(); buf, mode = [s[len("**Positive:**"):].strip()], "positive"
        elif s.startswith("**Negative:**"):
            flush(); buf, mode = [s[len("**Negative:**"):].strip()], "negative"
        elif s.startswith("#") or s.startswith("|") or s == "" or s.startswith("**"):
            flush(); buf, mode = [], None
            if s.startswith("## "):
                cat = None
        elif mode:
            buf.append(s)
    flush()
    return features


def _parse_siz_table(lines):
    """Return {SIZ: height_string} from the SIZ -> height/weight table."""
    heights = {}
    for cols in _table_rows(lines):
        if len(cols) >= 3 and re.fullmatch(r"\d+", cols[0]):
            heights[int(cols[0])] = cols[2]
    return heights


# ---------------------------------------------------------------------------
# Rules container + generation
# ---------------------------------------------------------------------------

class Rules:
    def __init__(self, trait_pairs, religions, culture_religion, passion_starts,
                 courts, app_table, features, siz_heights):
        self.trait_pairs = trait_pairs
        self.religions = religions
        self.culture_religion = culture_religion
        self.passion_starts = passion_starts
        self.courts = courts
        self.app_table = app_table
        self.features = features
        self.siz_heights = siz_heights

    # -- religion ----------------------------------------------------------

    def religion_for(self, culture):
        opts = self.culture_religion.get(culture)
        if opts:
            return random.choice(opts)
        return random.choice(list(self.religions)) if self.religions else "Pagan"

    # -- characteristics ---------------------------------------------------

    def roll_characteristics(self, culture):
        stats = {s: _roll(2, 6) + 5 for s in ("SIZ", "DEX", "STR", "CON", "APP")}
        if culture == "Cymri":  # documented cultural modifier
            stats["CON"] += 3
        siz, dex, str_, con, app = (stats[k] for k in ("SIZ", "DEX", "STR", "CON", "APP"))
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
        if n <= 0:
            return []
        buckets = [(cat, feat) for cat, d in self.features.items()
                   for feat in d.get(polarity, [])]
        random.shuffle(buckets)
        chosen, used_cat = [], set()
        for cat, feat in buckets:  # prefer distinct categories first
            if cat not in used_cat:
                chosen.append(feat); used_cat.add(cat)
            if len(chosen) >= n:
                return chosen
        for cat, feat in buckets:
            if feat not in chosen:
                chosen.append(feat)
            if len(chosen) >= n:
                break
        return chosen[:n]

    def roll_appearance(self, app):
        desc, npos, nneg, special = self._app_row(app)
        features = list(self._draw_features("positive", npos))
        features += self._draw_features("negative", nneg)
        if special:
            features.append(special.lower())
        return {
            "descriptor": desc,
            "features": features,
            "eyes": random.choice(EYE_COLOURS),
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
            name = re.sub(r"\((Person or Group|Group)\)",
                          f"({random.choice(PASSION_TARGETS)})", template)
            if name not in exclude:
                return name, random.randint(13, 18)
        return f"Hate ({random.choice(PASSION_TARGETS)})", random.randint(13, 18)

    def roll_passions(self, religion):
        s = self.passion_starts
        deity = DEITY.get(religion, "their god")
        passions = [
            ("Honor", _clamp(s.get("Honor", 15) + random.randint(-2, 3))),
            ("Homage (Lord)", _clamp(s.get("Homage (Lord)", 15) + random.randint(-3, 2))),
            ("Love (Family)", _clamp(s.get("Love (Family)", 10) + random.randint(-2, 5))),
            (f"Devotion ({deity})", _clamp(s.get("Devotion (Deity)", 5) + random.randint(0, 6))),
        ]
        name, val = self._motivating_passion({n for n, _ in passions})
        passions.append((name, _clamp(val)))
        return passions


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.readlines()


def load_rules(rules_dir):
    """Load and parse all reference files; return a Rules object or None."""
    files = {
        "traits": os.path.join(rules_dir, "traits.md"),
        "religion": os.path.join(rules_dir, "religion.md"),
        "passions": os.path.join(rules_dir, "passions.md"),
        "characteristics": os.path.join(rules_dir, "characteristics.md"),
        "appearance": os.path.join(rules_dir, "appearance.md"),
    }
    if not all(os.path.isfile(p) for p in files.values()):
        return None

    trait_pairs = _parse_trait_pairs(_read(files["traits"]))
    religions, culture_religion = _parse_religions(_read(files["religion"]))
    passion_lines = _read(files["passions"])
    passion_starts = _parse_passion_starts(passion_lines)
    courts = _parse_courts(passion_lines)
    appearance_lines = _read(files["appearance"])
    app_table = _parse_app_table(appearance_lines)
    features = _parse_features(appearance_lines)
    siz_heights = _parse_siz_table(_read(files["characteristics"]))

    if not (trait_pairs and religions and app_table and features):
        return None

    return Rules(trait_pairs, religions, culture_religion, passion_starts,
                 courts, app_table, features, siz_heights)


if __name__ == "__main__":  # quick self-test
    here = os.path.dirname(os.path.abspath(__file__))
    rules = load_rules(os.path.join(here, "rules"))
    if rules is None:
        print("Failed to load rules.")
        raise SystemExit(1)
    print("trait pairs:", len(rules.trait_pairs))
    print("religions:", list(rules.religions))
    print("culture->religion:", rules.culture_religion)
    print("passion starts:", rules.passion_starts)
    print("feature categories:", {k: (len(v["positive"]), len(v["negative"]))
                                   for k, v in rules.features.items()})
    print("app rows:", rules.app_table)
    rel = rules.religion_for("Saxon")
    stats, derived = rules.roll_characteristics("Cymri")
    print("sample religion:", rel)
    print("stats:", stats, derived)
    print("appearance:", rules.roll_appearance(stats["APP"]))
    print("traits:", rules.roll_traits(rel))
    print("passions:", rules.roll_passions(rel))
