"""NPC generation and statblock/description formatting (no UI)."""

import datetime
import random
import re

# ---------------------------------------------------------------------------
# Culture-specific naming rules
# ---------------------------------------------------------------------------
#
# Naming/flavour data (Roman nomen & honorifics, bynames, pronunciation hints,
# naming notes, manner) now lives in data/rules.json and is read via the Rules
# object. Only the feminisation logic stays in code.


def _feminise_roman(name):
    """Turn a Roman male name into its feminine 'ia' form (Arcavius -> Arcavia)."""
    return re.sub(r"(ius|us|is|os|a)$", "", name) + "ia"


# ---------------------------------------------------------------------------
# Name + character generation
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self, cultures, rules=None):
        self.cultures = cultures
        self.rules = rules

    def culture_names(self):
        return sorted(self.cultures.keys())

    def _name_pool(self, culture, gender):
        data = self.cultures[culture]
        pool = list(data.get(gender, []))

        if culture == "Roman" and gender == "Female":
            fem = [_feminise_roman(n) for n in data["Male"]
                   if not n.lower().endswith("rix")]
            pool = fem or pool

        if culture == "Pict" and gender == "Female" and not pool:
            for other in ("Cymri", "Irish"):
                if other in self.cultures:
                    pool.extend(self.cultures[other]["Female"])

        return pool

    def _surname(self, culture, gender):
        data = self.cultures[culture]

        if culture in ("Cymri", "Pict"):
            particle = ("ap" if culture == "Cymri" else "mab") if gender == "Male" else "ferch"
            fathers = data["Male"] or self.cultures.get("Cymri", {}).get("Male", [])
            if fathers:
                return f"{particle} {random.choice(fathers)}"
            return ""

        if culture == "Irish":
            if data["clans"]:
                return random.choice(data["clans"])
            return ""

        if culture == "Roman":
            if not (self.rules and self.rules.roman_nomen):
                return ""  # no nomen data without rules
            nomen = random.choice(self.rules.roman_nomen)
            if gender == "Female":  # Julius -> Julia, etc.
                nomen = _feminise_roman(nomen)
            parts = [nomen]
            if self.rules.roman_honorifics and random.random() < 0.5:
                parts.append(random.choice(self.rules.roman_honorifics))
            return " ".join(parts)

        if self.rules and self.rules.bynames and random.random() < 0.7:
            return random.choice(self.rules.bynames)
        return ""

    def _pronunciation(self, culture, name):
        if not self.rules:
            return []
        hints, seen = [], set()
        for cluster, note in self.rules.pronunciation.get(culture, []):
            if cluster in name.lower() and note not in seen:
                hints.append(note)
                seen.add(note)
        return hints

    def _fill_name(self, r):
        """(Re)roll the name fields of a result dict in place."""
        culture, gender = r["culture"], r["gender"]
        pool = self._name_pool(culture, gender)
        if not pool:
            raise ValueError(f"No {gender} names available for {culture}.")
        given = random.choice(pool)
        surname = self._surname(culture, gender)
        full = f"{given} {surname}".strip()
        r.update(
            given=given, surname=surname, full=full,
            pronunciation=self._pronunciation(culture, full),
        )

    def _fill_characteristics(self, r):
        """(Re)roll characteristics and everything derived from them."""
        stats, derived = self.rules.roll_characteristics(r["culture"])
        r["stats"] = stats
        r["derived"] = derived
        r["height"] = self.rules.height_for(stats["SIZ"])
        r["appearance"] = self.rules.roll_appearance(
            stats["APP"], stats["SIZ"], stats["STR"],
            r.get("culture", ""), r.get("religion", ""),
            include_negative=r.get("include_negative_appearance", True))

    def _resolve_class(self, gender, requested):
        """Reconcile gender and a requested class before anything else.

        A specific single-gender class dictates the gender (a Lady is female);
        otherwise a class valid for the gender is rolled. Returns (gender, cls).
        """
        classes = self.rules.social_classes
        if requested and requested in classes:  # a specific class was chosen
            cls = requested
            if not self.rules.class_allows(cls, gender):
                gender = classes[cls]["genders"][0]  # e.g. Lady -> Female
        else:  # "Random" / None -> a class valid for this gender
            cls = self.rules.roll_class(gender)
        return gender, cls

    def _fill_class(self, r, cls=None):
        """(Re)roll the social class and its skills/Glory in place."""
        if not (self.rules and self.rules.social_classes):
            return
        if cls is None:  # reroll: pick a class valid for the current gender
            cls = self.rules.roll_class(r["gender"])
        r["social_class"] = cls
        self._fill_skills(r)

    def _fill_attire(self, r):
        """Compose period-accurate clothing for the description. Knights get both
        battle gear and a court outfit; everyone else a single clothing clause.
        Depends on religion (for Clergy), so call after religion is set."""
        cls = r.get("social_class")
        if not (self.rules and self.rules.social_classes and cls):
            return
        attire = self.rules.roll_attire(cls, r["gender"], r["culture"],
                                        r.get("religion"))
        if isinstance(attire, dict):  # Knight: court dress + battle gear
            r["attire"] = attire.get("court", "")
            r["battle_gear"] = attire.get("battle", "")
        else:
            r["attire"] = attire
            r.pop("battle_gear", None)

    def _fill_skills(self, r):
        rolled = self.rules.roll_skills(r.get("social_class"))
        if rolled:
            r["skills"] = rolled["skills"]
            r["glory"] = rolled["glory"]

    def generate(self, culture, gender, social_class=None, religion=None,
                 include_negative_appearance=True):
        cls = None
        if self.rules and self.rules.social_classes:
            gender, cls = self._resolve_class(gender, social_class)

        result = {"culture": culture, "gender": gender,
                  "include_negative_appearance": include_negative_appearance}
        self._fill_name(result)

        if self.rules is not None:
            result["naming_note"] = self.rules.naming_notes.get(culture, "")
            if self.rules.social_classes:
                self._fill_class(result, cls)
            # A specific religion overrides the culture's default roll.
            if not (religion and religion in self.rules.religions):
                religion = self.rules.religion_for(culture)
            result["religion"] = religion
            self._fill_attire(result)  # after religion (Clergy garb follows faith)
            self._fill_characteristics(result)
            result["traits"] = self.rules.roll_traits(religion)
            result["manner"] = self.rules.compose_manner(result["traits"])
            result["passions"] = self.rules.roll_passions(religion)
            result["directed"] = self.rules.roll_directed_trait()
            # Full Cymric-knight creation (Core Ch.3) overrides the class-level
            # skills/Glory/passions with the rules-accurate sheet.
            if (result.get("social_class") == "Knight" and culture == "Cymri"
                    and self.rules.character_creation):
                self._apply_full_knight(result)

        return result

    def _apply_full_knight(self, r):
        """Replace the class-level skills/Glory/passions with a full rules-accurate
        Cymric knight (Core Ch.3): Table 3.5 skills + cultural/family/training,
        inherited Glory via family history, the complete passion set, plus age,
        homeland and family lore."""
        skills, family = self.rules.roll_full_skills(r["stats"], r["culture"])
        r["skills"] = skills
        r["family_talent"] = family
        glory, parent_glory, lore = self.rules.roll_inherited_glory()
        r["glory"] = glory
        r["parent_glory"] = parent_glory
        r["family_lore"] = lore
        r["passions"] = self.rules.roll_full_passions(r["religion"])
        defaults = self.rules.character_creation.get("defaults", {})
        r["age"] = defaults.get("age", 21)
        r["born"] = defaults.get("year", 508) - r["age"]
        r["homeland"] = defaults.get("homeland", "")
        r["residence"] = defaults.get("residence", "")
        r["full_knight"] = True
        r["ideals"] = self.rules.assess_ideals(r)
        r["squire"] = self._make_squire(r)

    def _make_squire(self, knight):
        """A young supporting-NPC squire attending the knight (Squire class,
        same culture/faith, a few years younger)."""
        sq = self.generate(
            knight.get("culture", "Cymri"), "Male", "Squire",
            knight.get("religion"),
            include_negative_appearance=knight.get(
                "include_negative_appearance", True))
        sq["age"] = max(15, knight.get("age", 21) - random.randint(3, 6))
        return sq

    # Fields the GUI can reroll individually, mapped to how to reroll them.
    def reroll_fields(self):
        if self.rules is None:
            return ["Name"]
        fields = [
            "Name", "Religion", "Characteristics", "Appearance",
            "Personality Traits", "Passions", "Directed Trait", "Manner",
        ]
        if self.rules.social_classes:
            fields[1:1] = ["Class", "Skills", "Attire"]  # right after Name
            fields.append("Squire")            # full Cymric knights only
        return fields

    def _full_knight_context(self, r):
        return (r.get("social_class") == "Knight" and r.get("culture") == "Cymri"
                and self.rules and self.rules.character_creation)

    def reroll_field(self, r, field):
        """Reroll a single component of an existing result in place."""
        if field == "Name":
            self._fill_name(r)
            return
        if self.rules is None:
            return
        full = bool(r.get("full_knight"))
        if field == "Attire":
            self._fill_attire(r)
            return
        if field == "Class":
            self._fill_class(r)
            self._fill_attire(r)             # clothing scales with the new class
            if self._full_knight_context(r):
                self._apply_full_knight(r)   # became (or stayed) a Cymric knight
            elif full:                       # no longer a Cymric knight
                for k in ("full_knight", "family_talent", "family_lore",
                          "parent_glory", "age", "homeland", "residence",
                          "ideals", "squire"):
                    r.pop(k, None)
        elif field == "Skills":
            if full:
                r["skills"], r["family_talent"] = \
                    self.rules.roll_full_skills(r["stats"], r["culture"])
            else:
                self._fill_skills(r)
        elif field == "Manner":  # re-phrase from the current traits
            r["manner"] = self.rules.compose_manner(r["traits"])
        elif field == "Religion":
            r["religion"] = self.rules.religion_for(r["culture"])
            r["traits"] = self.rules.roll_traits(r["religion"])
            r["manner"] = self.rules.compose_manner(r["traits"])
            r["passions"] = (self.rules.roll_full_passions(r["religion"]) if full
                             else self.rules.roll_passions(r["religion"]))
            if r.get("social_class") == "Clergy":  # vestments follow the faith
                self._fill_attire(r)
        elif field == "Characteristics":
            self._fill_characteristics(r)
            if full:  # skills derive from stats, so re-roll the full set too
                r["skills"], r["family_talent"] = \
                    self.rules.roll_full_skills(r["stats"], r["culture"])
        elif field == "Appearance":
            s = r["stats"]
            r["appearance"] = self.rules.roll_appearance(
                s["APP"], s["SIZ"], s["STR"],
                r.get("culture", ""), r.get("religion", ""),
                include_negative=r.get("include_negative_appearance", True))
        elif field == "Personality Traits":
            r["traits"] = self.rules.roll_traits(r["religion"])
            r["manner"] = self.rules.compose_manner(r["traits"])
        elif field == "Passions":
            r["passions"] = (self.rules.roll_full_passions(r["religion"]) if full
                             else self.rules.roll_passions(r["religion"]))
        elif field == "Directed Trait":
            r["directed"] = self.rules.roll_directed_trait()
        elif field == "Squire":
            if full:
                r["squire"] = self._make_squire(r)
            return
        # Ideals derive from the current traits/passions/skills — keep them fresh.
        if r.get("full_knight"):
            r["ideals"] = self.rules.assess_ideals(r)


# ---------------------------------------------------------------------------
# Statblock formatting (shared by the display and the clipboard)
# ---------------------------------------------------------------------------

FAMOUS = 16   # a trait value of 16–19 is Famous
EXALTED = 20  # a trait value of 20+ is Exalted


def _trait_entry(left, lval, right, rval):
    return f"{left} {lval}/{right} {rval}"


def _traits_str(traits):
    """All 13 pairs; Famous ones wrapped in ** (renders bold in Markdown/Discord)."""
    parts = []
    for left, lval, right, rval in traits:
        entry = _trait_entry(left, lval, right, rval)
        parts.append(f"**{entry}**" if max(lval, rval) >= FAMOUS else entry)
    return ", ".join(parts)


def _passions_str(passions):
    return ", ".join(f"{n} {v}" for n, v in passions)


def _skills_str(skills):
    return ", ".join(f"{k} {v}" for k, v in
                     sorted(skills.items(), key=lambda kv: (-kv[1], kv[0])))


def _ideal_gaps(ideal):
    """Short 'label current/needed' strings for an Ideal's unmet requirements."""
    return [f"{x['label'].split('(')[0].strip()} {x['current']}/{x['needed']}"
            for x in ideal["requirements"] if not x["ok"]]


def _ideals_summary(ideals):
    """One-line standing: the Ideals met, or the nearest one and its shortfalls."""
    met = [a["name"] for a in ideals if a["met"]]
    if met:
        return "qualifies for " + _natural_join(met)
    nearest = max(ideals, key=lambda a: sum(x["ok"] for x in a["requirements"]))
    return (f"none yet — nearest {nearest['name']} "
            f"(needs {'; '.join(_ideal_gaps(nearest))})")


def _squire_summary(sq):
    """One-line summary of the knight's attending squire."""
    sk = sq.get("skills", {})
    keyed = ", ".join(f"{k} {sk[k]}" for k in ("Sword", "Horsemanship", "Spear")
                      if k in sk)
    tail = f" — {keyed}" if keyed else ""
    glory = f"; Glory {sq['glory']}" if sq.get("glory") is not None else ""
    return (f"{sq['full']} ({sq.get('culture', '')} squire, "
            f"age {sq.get('age', '?')}){tail}{glory}")


def subtitle_str(r):
    """The '<gender> <class> · <culture> · <religion>' summary line."""
    sub = r["gender"]
    if r.get("social_class"):
        sub += f" {r['social_class']}"
    sub += f" · {r['culture']}"
    if r.get("religion"):
        sub += f" · {r['religion']}"
    return sub


# -- read-aloud description --------------------------------------------------

_SIZE_WORD = [(8, "slight"), (11, ""), (14, "tall"), (17, "powerfully built"),
              (99, "towering")]

_LOOKS_WORD = {
    "Infirm": "frail", "Unseemly": "unsightly", "Ill-favored": "plain-featured",
    "Plain": "plain", "Fair": "fair-featured", "Elegant": "elegant",
}

_ROLE_NOUN = {"Clergy": "cleric"}  # others use the class name lowercased


def _size_word(siz):
    if siz is None:
        return ""
    for threshold, word in _SIZE_WORD:
        if siz <= threshold:
            return word
    return ""


def _looks_word(descriptor, gender):
    if descriptor == "Surpassing":
        return "strikingly beautiful" if gender == "Female" else "strikingly handsome"
    return _LOOKS_WORD.get(descriptor, "")


def _natural_join(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


_FACE_ADJECTIVES = ("rough", "bright-eyed", "clean-shaven")


def _feature_phrase(category, feat):
    """Turn a bare Distinctive Feature into a readable noun phrase."""
    low = feat.lower()
    if category == "Hair" and "hair" not in low and \
            low not in ("bald", "balding", "thinning", "mangy", "patchy"):
        return f"{feat} hair"
    if category == "Speech" and "accent" not in low and low not in ("lisp", "stutter"):
        return f"{feat} voice"
    if category == "Physique" and " " not in feat:
        return f"{feat} figure"
    return feat


def _articled(phrase, category):
    """Prefix 'a'/'an' where it reads well; skip plurals, hair, and adjectives."""
    low = phrase.lower()
    if category is None or low.startswith(("a ", "an ", "the ")):
        return phrase
    if phrase.endswith(("s", "teeth")) or "hair" in low:  # plural or uncountable
        return phrase
    noun_like = (low.endswith(("figure", "voice")) or category == "Speech"
                 or (category == "Face" and low not in _FACE_ADJECTIVES))
    if not noun_like:
        return phrase
    return ("an " if low[0] in "aeiou" else "a ") + phrase


def build_description(r):
    """A short read-aloud paragraph pulling together all generated detail."""
    gender = r["gender"]
    subj = "She" if gender == "Female" else "He"
    role = _ROLE_NOUN.get(r.get("social_class"),
                          (r["social_class"].lower() if r.get("social_class")
                           else ("woman" if gender == "Female" else "man")))

    appearance = r.get("appearance") or {}
    stats = r.get("stats") or {}
    # Prefer the SIZ+STR build phrase ('large and heavily muscled') as the lead
    # adjective, but only when it reads as one after 'a ' — noun-phrase builds
    # ('a towering frame', 'of middling build') fall back to the SIZ-only word.
    build = appearance.get("build", "")
    lead_build = build if (build and not build.startswith(("a ", "an ", "of "))
                           and not build.endswith(("frame", "stature", "build"))) \
        else _size_word(stats.get("SIZ"))
    adjs = _natural_join([
        lead_build,
        _looks_word(appearance.get("descriptor"), gender),
    ])

    lead = f"You see a {adjs} {r['culture']} {role}" if adjs else \
           f"You see a {r['culture']} {role}"
    if r.get("attire"):
        lead += f", wearing {r['attire']}"
    sentences = [lead + "."]
    # Knights: the attire above is their court/feast dress; add the battle gear.
    if r.get("battle_gear"):
        sentences.append(f"Armed for war, {subj.lower()} wears {r['battle_gear']}.")

    details = appearance.get("feature_details") or \
        [[None, f] for f in appearance.get("features", [])]
    detail_items = ([f"{appearance['eyes']} eyes"] if appearance.get("eyes") else [])
    detail_items += [_articled(_feature_phrase(cat, feat), cat) for cat, feat in details]
    if detail_items:
        sentences.append(f"{subj} has {_natural_join(detail_items)}.")
    if r.get("manner"):
        sentences.append(f"{subj} seems {r['manner']}.")

    return " ".join(sentences)


def format_statblock(r):
    """Render a result dict as a plain-text statblock for the clipboard."""
    lines = [r["full"], subtitle_str(r), "", build_description(r), ""]

    if r.get("appearance"):
        a = r["appearance"]
        height = f", ~{r['height']} tall" if r.get("height") else ""
        build = f"{a['build']}; " if a.get("build") else ""
        lines.append(f"Appearance: {build}{a['descriptor']}{height}; {a['eyes']} eyes")
        if a["features"]:
            lines.append("Distinctive Features: " + "; ".join(a["features"]))

    if r.get("manner"):
        lines.append(f"Manner: {r['manner']}")
    if r.get("traits"):
        lines.append("Personality Traits: " + _traits_str(r["traits"]))
    if r.get("passions"):
        lines.append("Passions: " + _passions_str(r["passions"]))
    if r.get("directed"):
        lines.append(f"{r['directed']['kind']}: {r['directed']['text']}")

    if r.get("stats"):
        st = r["stats"]
        lines.append("  ".join(f"{k} {st[k]}" for k in ("SIZ", "DEX", "STR", "CON", "APP")))
        d = r["derived"]
        lines.append(
            f"HP {d['Hit Points']} · Move {d['Move']} · Damage {d['Damage']} · "
            f"Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
            f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}"
        )
    if r.get("skills"):
        lines.append("Skills: " + _skills_str(r["skills"]))
    if r.get("glory") is not None:
        lines.append(f"Glory: {r['glory']}")

    if r.get("full_knight"):
        if r.get("homeland"):
            res = f" ({r['residence']})" if r.get("residence") else ""
            lines.append(f"Age {r.get('age', 21)}, of {r['homeland']}{res}.")
        if r.get("family_talent"):
            lines.append("Family talent (+3): " + ", ".join(r["family_talent"]))
        if r.get("parent_glory"):
            lines.append(f"Inherited Glory from a parent of {r['parent_glory']:,} Glory.")
        if r.get("family_lore"):
            lines.append("Family lore: "
                         + "; ".join(f"an ancestor {ln}" for ln in r["family_lore"]))
        if r.get("ideals"):
            lines.append("Ideals: " + _ideals_summary(r["ideals"]))
        if r.get("squire"):
            lines.append("Squire: " + _squire_summary(r["squire"]))

    if r.get("naming_note"):
        lines.append(f"Naming: {r['naming_note']}")
    if r.get("pronunciation"):
        lines.append("Pronunciation: " + "; ".join(r["pronunciation"]))

    if r.get("notes", "").strip():
        lines.append("")
        lines.append("GM Notes:")
        lines.append(r["notes"].rstrip())

    return "\n".join(lines)


def format_statblock_markdown(r):
    """Render a result dict as a Markdown block for game notes."""
    lines = [f"## {r['full']}", f"*{subtitle_str(r)}*", "",
             f"> {build_description(r)}", ""]

    def bullet(label, value):
        lines.append(f"- **{label}:** {value}")

    if r.get("appearance"):
        a = r["appearance"]
        height = f", ~{r['height']} tall" if r.get("height") else ""
        bullet("Appearance", f"{a['descriptor']}{height}; {a['eyes']} eyes")
        if a["features"]:
            bullet("Distinctive Features", "; ".join(a["features"]))
    if r.get("manner"):
        bullet("Manner", r["manner"])
    if r.get("traits"):
        bullet("Personality Traits", _traits_str(r["traits"]))
    if r.get("passions"):
        bullet("Passions", _passions_str(r["passions"]))
    if r.get("directed"):
        bullet(r["directed"]["kind"], r["directed"]["text"])
    if r.get("stats"):
        st = r["stats"]
        bullet("Characteristics",
               "  ".join(f"{k} {st[k]}" for k in ("SIZ", "DEX", "STR", "CON", "APP")))
        d = r["derived"]
        bullet("Derived",
               f"HP {d['Hit Points']} · Move {d['Move']} · Damage {d['Damage']} · "
               f"Healing {d['Healing Rate']} · Major Wound {d['Major Wound']} · "
               f"Knockdown {d['Knockdown']} · Unconscious {d['Unconscious']}")
    if r.get("skills"):
        bullet("Skills", _skills_str(r["skills"]))
    if r.get("glory") is not None:
        bullet("Glory", r["glory"])
    if r.get("full_knight"):
        if r.get("homeland"):
            res = f" ({r['residence']})" if r.get("residence") else ""
            bullet("Age / Home", f"{r.get('age', 21)} · {r['homeland']}{res}")
        if r.get("family_talent"):
            bullet("Family talent", "+3 " + ", ".join(r["family_talent"]))
        if r.get("family_lore"):
            bullet("Family lore",
                   "; ".join(f"an ancestor {ln}" for ln in r["family_lore"]))
        if r.get("ideals"):
            bullet("Ideals", _ideals_summary(r["ideals"]))
            for a in r["ideals"]:
                mark = "✓" if a["met"] else "✗"
                gaps = _ideal_gaps(a)
                detail = "" if a["met"] else " — needs " + "; ".join(gaps)
                lines.append(f"    - {mark} {a['name']}{detail}")
        if r.get("squire"):
            bullet("Squire", _squire_summary(r["squire"]))
    if r.get("naming_note"):
        bullet("Naming", r["naming_note"])
    if r.get("pronunciation"):
        bullet("Pronunciation", "; ".join(r["pronunciation"]))

    if r.get("notes", "").strip():
        lines.append("")
        lines.append("**GM Notes:**")
        lines.append("")
        lines.append(r["notes"].rstrip())

    return "\n".join(lines)


def format_roster_markdown(roster):
    """Render a whole session roster as one Markdown document."""
    today = datetime.date.today().isoformat()
    count = len(roster)
    header = [
        "# Pendragon NPC Roster",
        f"*{count} NPC{'s' if count != 1 else ''} — {today}*",
        "",
    ]
    blocks = [format_statblock_markdown(r) for r in roster]
    return "\n".join(header) + "\n" + "\n\n".join(blocks) + "\n"


def build_image_prompt(r):
    """Build a period-accurate image-generation prompt from the NPC."""
    social = f"{r['social_class'].lower()} " if r.get("social_class") else ""
    subject = f"{r['gender'].lower()} {r['culture']} {social}person".replace("  ", " ")
    parts = [f"character portrait of a {subject}"]

    a = r.get("appearance")
    if a:
        if a.get("features"):
            parts.append(", ".join(a["features"]))
        parts.append(f"{a['eyes']} eyes")
        parts.append(f"{a['descriptor'].lower()}-looking")
    if r.get("height"):
        parts.append(f"about {r['height']} tall")

    attire = r.get("attire") or "period Dark Ages clothing"
    style = (
        f"sub-Roman Britain, 5th-6th century, Dark Ages, wearing {attire}, "
        "no plate armour, historically grounded, muted natural colours, "
        "overcast light, painterly, detailed face, head and shoulders"
    )
    negative = (
        "Negative prompt: plate armour, full helm, gothic castle, renaissance, "
        "modern clothing, anime, cartoon, text, watermark, deformed"
    )
    return ", ".join(p for p in parts if p) + ". " + style + "\n" + negative
