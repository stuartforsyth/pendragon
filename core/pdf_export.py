#!/usr/bin/env python3
"""Export a generated Cymric knight to the official fillable character-sheet PDF.

Optional feature: it needs **pypdf** (pure-Python, ``pip install pypdf``). The
rest of the app is stdlib-only, so the NPC Generator gates the "Export sheet
PDF" button on ``PDF_AVAILABLE`` and works fine without it. The template lives
in the (git-ignored) ``rulebooks/`` folder next to the other PDFs.
"""

import os
import re

try:
    import pypdf
    PDF_AVAILABLE = True
except ImportError:                       # pragma: no cover - optional dep
    pypdf = None
    PDF_AVAILABLE = False

SHEET_FILENAME = "pendragon_-_character_sheet_-_fillable.pdf"

# Generated skill name -> sheet field name, only where they differ.
_SKILL_FIELD = {
    "Singing": "Sing", "Thrown": "Thrown Weapon", "Two-Handed Hafted": "2H Hafted",
}

# Passion name -> sheet field (the ones with a dedicated slot). Devotion and Hate
# are handled separately (deity substitution / the Fervor "Other" slot).
_PASSION_FIELD = {
    "Honor": "Honor", "Homage (Lord)": "Fidelitas Homage",
    "Love (Family)": "Fervor Love Family", "Hospitality": "Civilitas Hospitality",
    "Station": "Civilitas Station",
}


def sheet_template_path(base_dir):
    """Where the fillable sheet is expected (rulebooks/ beside the script)."""
    return os.path.join(base_dir, "rulebooks", SHEET_FILENAME)


def safe_filename(name):
    """A filesystem-safe base name for the export (no extension)."""
    name = re.sub(r'[/\\:*?"<>|]', "", name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name or "knight"


def _dice_count(expr):
    m = re.match(r"\s*(\d+)\s*[dD]6", str(expr))
    return m.group(1) if m else str(expr)


def build_field_values(r):
    """Map a generated knight result dict to {sheet field name: string value}.

    Only Phase-1 fields (identity, characteristics, derived, skills, traits,
    passions, Glory) — equipment/horses/coat-of-arms are left blank.
    """
    v = {}
    st = r.get("stats") or {}
    d = r.get("derived") or {}
    a = r.get("appearance") or {}

    # Identity
    v["Name"] = r.get("full", "")
    v["Class"] = r.get("social_class", "")
    v["Culture"] = r.get("culture", "")
    v["Homeland"] = r.get("homeland", "")
    # Identity faith is "Religion Name"; the bare "Religion" field is the Religion
    # *skill* (filled from the skills loop below).
    v["Religion Name"] = r.get("religion", "")
    if r.get("born") is not None:
        v["Born"] = str(r["born"])
    # Family talent (+3 skill) and parents.
    if r.get("family_talent"):
        v["Family Characteristic"] = ", ".join(r["family_talent"])
    if r.get("parent_glory"):
        v["Parents Glory 1"] = str(r["parent_glory"])
    # Father's name from a patronymic surname ("ap Nai" -> "Nai").
    m = re.match(r"^(?:ap|ferch|map)\s+(.*)$", (r.get("surname") or "").strip(), re.I)
    if m:
        v["Parents Name 1"] = m.group(1)

    # Distinctive Features (two lines on the sheet).
    feats = list(a.get("features", []))
    if a.get("eyes"):
        feats = [f"{a['eyes']} eyes"] + feats
    if feats:
        v["Distinctive Features 1"] = feats[0]
    if len(feats) > 1:
        v["Distinctive Features 2"] = "; ".join(feats[1:])

    # Characteristics
    for k in ("SIZ", "DEX", "STR", "CON", "APP"):
        if st.get(k) is not None:
            v[k] = str(st[k])
    # Derived
    dmap = {
        "Total Hit Points": "Hit Points", "Current HP": "Hit Points",
        "Movement Rate": "Move", "Healing Rate": "Healing Rate",
        "Major Wound": "Major Wound", "Knockdown": "Knockdown",
        "Unconscious": "Unconscious",
    }
    for field, key in dmap.items():
        if d.get(key) is not None:
            v[field] = str(d[key])
    # Both damage fields want the (STR+SIZ)/6 number — the sheet prints the "D6"
    # after Weapon Damage itself.
    if d.get("Damage"):
        v["Weapon Damage"] = _dice_count(d["Damage"])
        v["Brawling Damage"] = _dice_count(d["Damage"])

    # Glory
    if r.get("glory") is not None:
        v["Glory"] = str(r["glory"])
        v["Total Glory 01"] = str(r["glory"])

    # Skills
    for name, val in (r.get("skills") or {}).items():
        v[_SKILL_FIELD.get(name, name)] = str(val)

    # Traits — both sides of each pair.
    for left, lval, right, rval in (r.get("traits") or []):
        v[left] = str(lval)
        v[right] = str(rval)

    # Passions
    for name, val in (r.get("passions") or []):
        if name in _PASSION_FIELD:
            v[_PASSION_FIELD[name]] = str(val)
        elif name.startswith("Devotion"):
            v["Adoratio Devotion Deity"] = str(val)
        elif name.startswith("Hate"):
            v["Fervor Other 1"] = str(val)
            who = re.search(r"\((.*)\)", name)
            if who:
                v["Fervor Other Who 1"] = who.group(1)
    return v


def export_sheet(r, template_path, out_path):
    """Fill the fillable sheet for knight ``r`` and write it to out_path.

    Returns the number of fields filled. Raises if pypdf is unavailable or the
    template is missing/unreadable.
    """
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF export needs pypdf (pip install pypdf).")
    if not os.path.isfile(template_path):
        raise FileNotFoundError(template_path)

    reader = pypdf.PdfReader(template_path)
    fields = reader.get_fields() or {}
    values = build_field_values(r)
    to_fill = {k: val for k, val in values.items()
               if k in fields and val not in (None, "")}

    writer = pypdf.PdfWriter()
    writer.append(reader)
    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, to_fill, auto_regenerate=False)
        except Exception:
            # A stray field type (e.g. a choice) shouldn't abort the export;
            # fill this page's fields one at a time and skip any that object.
            for key, val in to_fill.items():
                try:
                    writer.update_page_form_field_values(page, {key: val},
                                                          auto_regenerate=False)
                except Exception:
                    pass
    # Ask viewers to render the values (we don't build appearance streams).
    try:
        writer.set_need_appearances_writer(True)
    except Exception:
        pass
    with open(out_path, "wb") as fh:
        writer.write(fh)
    return len(to_fill)
