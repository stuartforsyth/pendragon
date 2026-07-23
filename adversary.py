#!/usr/bin/env python3
"""Adversary Creator for the Pendragon app.

A tab to search, edit, and add **adversaries** — the reusable stat blocks that
encounters are built from (see docs/adversary-creator-spec.md). Generic types
(e.g. "Bandit") and named individuals (e.g. "Sir Gawain the Valiant") live in
one ``adversaries`` map; this v1 covers **human** adversaries with weapon and
armour selection driven by the enriched combat tables.

Reuses the NPC Generator (`Generator` / `Rules`) for characteristics, derived
stats, skills, traits and passions, and `rules.save_combat` for persistence.
"""

import copy
import random
import re
import tkinter as tk
from tkinter import font as tkfont, messagebox, ttk

from rules import roll_expr, save_combat
from encounter import CHAR_FULL, bind_mousewheel

CHAR_ORDER = ("SIZ", "DEX", "STR", "CON", "APP")

# A default weapon per combat skill, used when seeding attacks from an NPC.
WEAPON_FOR_SKILL = {
    "Sword": "Sword", "Spear": "Spear", "Charge": "Lance", "Bow": "Self Bow",
    "Hafted": "Axe", "Two-Handed Hafted": "Great Axe", "Brawling": "Dagger",
    "Crossbow": "Light Crossbow",
}


# ---------------------------------------------------------------------------
# Model helpers (pure — no UI)
# ---------------------------------------------------------------------------

def _dice_count(expr):
    """Number of d6 in a damage string ('4d6' -> 4, '5D6+4' -> 5, '12' -> 0)."""
    m = re.match(r"\s*(\d+)\s*[dD]6", str(expr))
    return int(m.group(1)) if m else 0


def resolve_weapon_damage(wdef, base_damage):
    """The damage a weapon deals for a wielder whose Weapon Damage is base_damage.

    base_damage is a dice string like '4d6' (the adversary's derived Damage). Its
    die count is also the wielder's flat **Brawling Damage** — both equal
    (STR + SIZ) ÷ 6 (Core p.34). Handles the table's damage_base/damage_mod/
    damage_max model (Weapons Tables 8.1 & 8.2).
    """
    base = wdef.get("damage_base", "character")
    if base == "fixed":
        return wdef.get("damage_dice", str(base_damage))
    if base == "horse":
        return "Horse"
    flat = _dice_count(base_damage)
    m = re.match(r"\s*([+-])\s*(\d+)\s*[dD]6", wdef.get("damage_mod", "") or "")
    mod_dice = (1 if m.group(1) == "+" else -1) * int(m.group(2)) if m else 0
    if base == "brawling":
        # Brawling weapons (Dagger, Club, Javelin…) add their XD6 modifier to the
        # flat Brawling Damage number: Brawling +2D6 with Brawling 4 -> '2D6+4'
        # (Table 8.1) — NOT 6D6.
        if mod_dice <= 0:
            return str(max(1, flat))
        return f"{mod_dice}D6+{flat}" if flat else f"{mod_dice}D6"
    # character-based: dice = weapon-damage dice ± the modifier dice, then capped.
    n = flat + mod_dice
    cap = wdef.get("damage_max")
    if cap:
        n = min(n, _dice_count(cap))
    return f"{max(1, n)}D6"


def compute_armour(pieces, helmet, shield, combat):
    """(armor_points, shield_points) from selected body pieces + helmet + shield."""
    ap = sum(combat.get("armour_pieces", {}).get(p, {}).get("protection", 0)
             for p in pieces)
    if helmet:
        ap += combat.get("helmets", {}).get(helmet, {}).get("protection", 0)
    sp = combat.get("shields", {}).get(shield, {}).get("protection", 0) if shield else 0
    return ap, sp


def describe_armour(pieces, helmet, shield):
    """A readable armour description from the selection."""
    worn = list(pieces) + ([helmet] if helmet else [])
    desc = ", ".join(worn)
    if shield:
        desc = f"{desc} + {shield} shield" if desc else f"{shield} shield"
    return desc


def _match_shield(text, shield_names):
    t = text.strip().lower().replace("shield", "").strip()
    return shield_names.get(t, "")


def parse_armour_desc(desc, combat):
    """Derive (pieces, helmet, shield) from a free-text armour_desc.

    Legacy adversaries store armour only as text (e.g. "Haubergeon, aketon,
    open helm + kite shield") plus precomputed points; the editor needs the
    structured selection so the checkboxes/dropdowns reflect it.
    """
    pieces, helmet, shield = [], "", ""
    if not desc or desc.strip().lower() == "none":
        return pieces, helmet, shield
    desc = re.split(r"[;(]", desc)[0]  # drop trailing notes / parentheticals
    piece_names = {n.lower(): n for n in combat.get("armour_pieces", {})}
    helmet_names = {n.lower(): n for n in combat.get("helmets", {})}
    shield_names = {n.lower(): n for n in combat.get("shields", {})}
    body = desc
    if "+" in desc:
        body, shield_part = desc.split("+", 1)
        shield = _match_shield(shield_part, shield_names)
    for tok in re.split(r",|\band\b", body):
        t = tok.strip().lower()
        if not t:
            continue
        if t in piece_names:
            pieces.append(piece_names[t])
        elif t in helmet_names:
            helmet = helmet_names[t]
        else:
            s = _match_shield(t, shield_names)  # e.g. "Targe shield" in the body
            if s:
                shield = s
    return pieces, helmet, shield


def blank_adversary(kind="generic", category="human"):
    return {
        "kind": kind, "category": category, "source": "user",
        "name": "", "tier": "trained", "description": "",
        "characteristics": {"SIZ": 10, "DEX": 10, "STR": 10, "CON": 10, "APP": 10},
        "attacks": [],
        "armour": {"pieces": [], "helmet": "", "shield": ""},
        "health": {"hit_points": 20, "knockdown": 10, "major_wound": 10, "unconscious": 5},
        "other": {"movement": 10, "armor_points": 0, "shield": 0, "glory": 0, "healing_rate": 2},
        "skills": {}, "traits": {}, "passions": {},
        "armour_desc": "", "promotion_title": "Champion", "notes": "",
    }


def _npc_traits_map(pairs):
    """Keep the dominant side of each trait pair when it is notable (>= 13)."""
    out = {}
    for left, lval, right, rval in pairs:
        if lval >= rval and lval >= 13:
            out[left] = lval
        elif rval > lval and rval >= 13:
            out[right] = rval
    return out


def _npc_looks(r):
    a = r.get("appearance") or {}
    bits = [a.get("descriptor", "")]
    if a.get("features"):
        bits.append("; ".join(a["features"]))
    if a.get("eyes"):
        bits.append(f"{a['eyes']} eyes")
    return ", ".join(b for b in bits if b)


def draft_from_npc(r, combat):
    """Build a **named** human adversary draft from an NPC result dict (§6.1)."""
    adv = blank_adversary("named", "human")
    adv["name"] = r.get("full", "")
    adv["culture"] = r.get("culture", "")
    adv["religion"] = r.get("religion", "")
    adv["created_from_npc"] = True
    adv["description"] = _npc_looks(r)
    stats = r.get("stats") or {}
    if stats:
        adv["characteristics"] = {k: stats.get(k, 10) for k in CHAR_ORDER}
    d = r.get("derived") or {}
    base_damage = d.get("Damage", "1d6")
    adv["health"] = {
        "hit_points": d.get("Hit Points", 20), "knockdown": d.get("Knockdown", 10),
        "major_wound": d.get("Major Wound", 10), "unconscious": d.get("Unconscious", 5),
    }
    adv["other"] = {
        "movement": d.get("Move", 10), "armor_points": 0, "shield": 0,
        "glory": r.get("glory", 0), "healing_rate": d.get("Healing Rate", 2),
    }
    adv["skills"] = dict(r.get("skills") or {})
    adv["traits"] = _npc_traits_map(r.get("traits") or [])
    adv["passions"] = {n: v for n, v in (r.get("passions") or [])}
    weapons = combat.get("weapons", {})
    for skill, weapon in WEAPON_FOR_SKILL.items():
        if skill in adv["skills"] and weapon in weapons:
            adv["attacks"].append({
                "weapon": weapon, "skill": skill, "value": adv["skills"][skill],
                "damage": resolve_weapon_damage(weapons[weapon], base_damage),
            })
    return adv


def _map_to_text(m):
    return "\n".join(f"{k} {v}" for k, v in m.items())


def _text_to_map(s):
    """Parse 'Name value' lines into an ordered dict of {name: int}."""
    out = {}
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)[\s:]+(-?\d+)\s*$", line)
        if m:
            out[m.group(1).strip()] = int(m.group(2))
    return out


# ---------------------------------------------------------------------------
# GUI — the Adversary Creator tab
# ---------------------------------------------------------------------------

class AdversaryTab(ttk.Frame):
    def __init__(self, parent, generator, set_status, on_change=None):
        super().__init__(parent)
        self.generator = generator
        self.rules = generator.rules
        self.combat = self.rules.combat
        self.set_status = set_status
        # Called after the library is saved/deleted so other tabs (the Encounter
        # tracker's dropdowns) can pick up new/removed adversaries live.
        self.on_change = on_change
        self.draft = blank_adversary()
        self.draft_key = None          # library key being edited, or None if new
        self.attack_rows = []
        self.piece_vars = {}
        self._traits_snapshot = {}     # traits at last focus-in, for pair balancing
        self._build_ui()
        self._refresh_library()
        self._show(self.draft, None)

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        self.bold = tkfont.Font(family="TkDefaultFont", size=10, weight="bold")

        # Left: library. Right: editor.
        lib = ttk.LabelFrame(self, text="Adversary library")
        lib.pack(side="left", fill="y", padx=(10, 4), pady=10)

        srow = ttk.Frame(lib)
        srow.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(srow, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._refresh_library())
        ttk.Entry(srow, textvariable=self.search_var, width=20).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        frow = ttk.Frame(lib)
        frow.pack(fill="x", padx=6, pady=(0, 2))
        ttk.Label(frow, text="Kind:").pack(side="left")
        self.kind_filter = tk.StringVar(value="all")
        ttk.Combobox(frow, textvariable=self.kind_filter, width=8, state="readonly",
                     values=["all", "generic", "named"]).pack(side="left", padx=(4, 6))
        ttk.Label(frow, text="Category:").pack(side="left")
        self.category_filter = tk.StringVar(value="all")
        ttk.Combobox(frow, textvariable=self.category_filter, width=8, state="readonly",
                     values=["all", "human", "beast", "monster", "fae"]).pack(side="left", padx=(4, 0))
        self.kind_filter.trace_add("write", lambda *a: self._refresh_library())
        self.category_filter.trace_add("write", lambda *a: self._refresh_library())

        self.lib_list = tk.Listbox(lib, width=32, height=22, activestyle="dotbox")
        self.lib_list.pack(fill="both", expand=True, padx=6, pady=(2, 2))
        self.lib_list.bind("<<ListboxSelect>>", self._on_select)

        btns = ttk.Frame(lib)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btns, text="New generic", width=12,
                   command=lambda: self._new("generic")).grid(row=0, column=0, padx=1, pady=1)
        ttk.Button(btns, text="New named", width=12,
                   command=lambda: self._new("named")).grid(row=0, column=1, padx=1, pady=1)
        ttk.Button(btns, text="Duplicate", width=12,
                   command=self._duplicate).grid(row=1, column=0, padx=1, pady=1)
        ttk.Button(btns, text="Delete", width=12,
                   command=self._delete).grid(row=1, column=1, padx=1, pady=1)

        # Right: scrollable editor.
        outer = ttk.LabelFrame(self, text="Editor")
        outer.pack(side="left", fill="both", expand=True, padx=(4, 10), pady=10)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.ed = ttk.Frame(canvas)
        self.ed.bind("<Configure>",
                     lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.ed, anchor="nw")
        canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        bind_mousewheel(canvas)

        self._build_editor()

    def _section(self, title):
        f = ttk.LabelFrame(self.ed, text=title)
        f.pack(fill="x", padx=8, pady=(6, 0))
        return f

    def _build_editor(self):
        # Save bar
        bar = ttk.Frame(self.ed)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        self.header = ttk.Label(bar, text="New adversary", font=self.bold)
        self.header.pack(side="left")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="right", padx=(0, 6))

        # Identity
        idf = self._section("Identity")
        self.kind_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.tier_var = tk.StringVar()
        self.culture_var = tk.StringVar()
        self.religion_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.promo_var = tk.StringVar()
        r = 0
        ttk.Label(idf, text="Kind:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        ttk.Combobox(idf, textvariable=self.kind_var, width=10, state="readonly",
                     values=["generic", "named"]).grid(row=r, column=1, sticky="w")
        ttk.Label(idf, text="Category:").grid(row=r, column=2, sticky="e", padx=4)
        ttk.Combobox(idf, textvariable=self.category_var, width=10, state="readonly",
                     values=["human", "beast", "fae", "monster"]).grid(row=r, column=3, sticky="w")
        self.category_var.trace_add("write", self._toggle_category_ui)
        r += 1
        ttk.Label(idf, text="Name / type:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(idf, textvariable=self.name_var, width=28).grid(
            row=r, column=1, columnspan=3, sticky="w")
        r += 1
        ttk.Label(idf, text="Tier:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        ttk.Combobox(idf, textvariable=self.tier_var, width=10, state="readonly",
                     values=list(self.combat.get("tiers", {})) or
                     ["rabble", "trained", "veteran", "elite"]).grid(row=r, column=1, sticky="w")
        ttk.Label(idf, text="Promotion title:").grid(row=r, column=2, sticky="e", padx=4)
        ttk.Entry(idf, textvariable=self.promo_var, width=14).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(idf, text="Culture:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        ttk.Combobox(idf, textvariable=self.culture_var, width=14,
                     values=self.generator.culture_names()).grid(row=r, column=1, sticky="w")
        ttk.Label(idf, text="Religion:").grid(row=r, column=2, sticky="e", padx=4)
        ttk.Entry(idf, textvariable=self.religion_var, width=14).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(idf, text="Description:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(idf, textvariable=self.desc_var, width=48).grid(
            row=r, column=1, columnspan=3, sticky="we")

        # Characteristics + auto
        cf = self._section("Characteristics")
        self._char_frame = cf
        self.char_vars = {}
        for i, k in enumerate(CHAR_ORDER):
            ttk.Label(cf, text=f"{CHAR_FULL[k]}:").grid(row=0, column=2 * i, sticky="e", padx=(6, 1), pady=3)
            v = tk.StringVar()
            self.char_vars[k] = v
            e = ttk.Entry(cf, textvariable=v, width=5)
            e.grid(row=0, column=2 * i + 1, sticky="w")
            v.trace_add("write", lambda *a: self._recompute_derived())
        ttk.Button(cf, text="Roll characteristics", command=self._roll_characteristics).grid(
            row=1, column=0, columnspan=6, sticky="w", padx=6, pady=(0, 4))

        # Derived (auto)
        df = self._section("Derived (computed from characteristics)")
        self._derived_frame = df
        self.derived_lbl = ttk.Label(df, text="", justify="left")
        self.derived_lbl.pack(anchor="w", padx=6, pady=4)

        # Creature combat stats — explicit (beast/monster/fae). Unlike humans,
        # a creature's Move / Armour / Hit Points are *printed*, not derived, so
        # they are edited here directly. Shown only for non-human categories.
        self.cf_creature = self._section("Creature combat stats (printed, not derived)")
        self.creature_vars = {}
        cg = ttk.Frame(self.cf_creature)
        cg.pack(fill="x", padx=6, pady=4)
        specs = [("hit_points", "Hit Points"), ("major_wound", "Major Wound"),
                 ("knockdown", "Knockdown"), ("unconscious", "Unconscious"),
                 ("healing_rate", "Healing Rate"), ("movement", "Move"),
                 ("armor_points", "Natural Armor"), ("shield", "Shield"),
                 ("glory", "Glory Won"), ("valorous_modifier", "Valorous mod")]
        for i, (key, label) in enumerate(specs):
            r, cc = divmod(i, 3)
            ttk.Label(cg, text=f"{label}:").grid(row=r, column=cc * 2, sticky="e",
                                                 padx=(6, 1), pady=2)
            v = tk.StringVar()
            self.creature_vars[key] = v
            ttk.Entry(cg, textvariable=v, width=6).grid(row=r, column=cc * 2 + 1, sticky="w")

        # Attacks
        af = self._section("Attacks / weapons")
        self._attacks_section = af
        self.attacks_frame = ttk.Frame(af)
        self.attacks_frame.pack(fill="x", padx=6, pady=2)
        addbar = ttk.Frame(af)
        addbar.pack(fill="x", padx=6, pady=(0, 4))
        self.new_weapon_var = tk.StringVar()
        ttk.Combobox(addbar, textvariable=self.new_weapon_var, width=18, state="readonly",
                     values=list(self.combat.get("weapons", {}))).pack(side="left")
        ttk.Button(addbar, text="Add weapon",
                   command=self._add_selected_weapon).pack(side="left", padx=(6, 0))
        # A blank editable row for natural attacks (Claws, Bite, Gore…).
        ttk.Button(addbar, text="Add natural attack",
                   command=lambda: self._add_attack_row()).pack(side="left", padx=(6, 0))

        # Armour (human — worn pieces). Creatures use the Natural Armor field above.
        arf = self._section("Armour (worn — humans)")
        self._armour_frame = arf
        self.armour_pieces_frame = ttk.Frame(arf)
        self.armour_pieces_frame.pack(fill="x", padx=6, pady=2)
        for i, name in enumerate(self.combat.get("armour_pieces", {})):
            var = tk.BooleanVar()
            self.piece_vars[name] = var
            cb = ttk.Checkbutton(self.armour_pieces_frame, text=name, variable=var,
                                 command=self._recompute_armour)
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=4, pady=1)
        hs = ttk.Frame(arf)
        hs.pack(fill="x", padx=6, pady=2)
        ttk.Label(hs, text="Helmet:").pack(side="left")
        self.helmet_var = tk.StringVar()
        ttk.Combobox(hs, textvariable=self.helmet_var, width=18, state="readonly",
                     values=[""] + list(self.combat.get("helmets", {}))).pack(side="left", padx=(4, 10))
        self.helmet_var.trace_add("write", lambda *a: self._recompute_armour())
        ttk.Label(hs, text="Shield:").pack(side="left")
        self.shield_var = tk.StringVar()
        ttk.Combobox(hs, textvariable=self.shield_var, width=12, state="readonly",
                     values=[""] + list(self.combat.get("shields", {}))).pack(side="left", padx=(4, 0))
        self.shield_var.trace_add("write", lambda *a: self._recompute_armour())
        self.armour_lbl = ttk.Label(arf, text="")
        self.armour_lbl.pack(anchor="w", padx=6, pady=(0, 4))

        # Skills / traits / passions — a pick-and-add dropdown (autorolled value,
        # editable in the text; skipped if already listed) over an editable list.
        pickers = [
            ("skills_text", "Skills", self._skill_vocab(), self._roll_skill_value),
            ("traits_text", "Traits", self._trait_vocab(), self._roll_trait_value),
            ("passions_text", "Passions", self._passion_vocab(), self._roll_passion_value),
        ]
        for attr, title, vocab, rollfn in pickers:
            hint = " — pairs balance to 20" if attr == "traits_text" else ""
            sf = self._section(f"{title}  (one 'Name value' per line{hint})")
            t = tk.Text(sf, height=4, width=48, wrap="word", font=("TkDefaultFont", 10))
            prow = ttk.Frame(sf)
            prow.pack(fill="x", padx=6, pady=(4, 0))
            var = tk.StringVar()
            ttk.Combobox(prow, textvariable=var, width=22, state="readonly",
                         values=vocab).pack(side="left")
            if attr == "traits_text":
                cmd = lambda vv=var: self._add_trait(vv.get())
            else:
                cmd = lambda tw=t, vv=var, rf=rollfn: self._append_stat(tw, vv.get(), rf)
            ttk.Button(prow, text="Add", command=cmd).pack(side="left", padx=(6, 0))
            t.pack(fill="x", padx=6, pady=4)
            setattr(self, attr, t)

        # Keep trait pairs consistent after manual edits (snapshot on focus in,
        # balance on focus out).
        self.traits_text.bind("<FocusIn>", lambda e: self._snapshot_traits())
        self.traits_text.bind("<FocusOut>", self._normalise_traits)

        # Free-text notes for special mechanics (regeneration, immunities,
        # special attacks, etc.) that the structured fields don't capture.
        nf = self._section("Mechanics / notes")
        self.notes_text = tk.Text(nf, height=4, width=48, wrap="word",
                                  font=("TkDefaultFont", 10))
        self.notes_text.pack(fill="x", padx=6, pady=4)

        # Auto-generate all
        gf = self._section("Auto-generate from an NPC template")
        self.gen_gender = tk.StringVar(value="Male")
        self.gen_class = tk.StringVar(value="Random")
        ttk.Label(gf, text="Gender:").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        ttk.Combobox(gf, textvariable=self.gen_gender, width=8, state="readonly",
                     values=["Male", "Female"]).grid(row=0, column=1, sticky="w")
        ttk.Label(gf, text="Class:").grid(row=0, column=2, sticky="e", padx=4)
        ttk.Combobox(gf, textvariable=self.gen_class, width=14, state="readonly",
                     values=["Random"] + list(self.rules.social_classes)).grid(row=0, column=3, sticky="w")
        ttk.Button(gf, text="Auto-generate all", command=self._auto_generate).grid(
            row=0, column=4, padx=6)

    # -- library -----------------------------------------------------------

    def _adversaries(self):
        return self.combat.get("adversaries", {})

    def _refresh_library(self):
        self.lib_list.delete(0, "end")
        q = self.search_var.get().strip().lower()
        kind = self.kind_filter.get()
        category = self.category_filter.get()
        self._lib_keys = []
        for key, a in sorted(self._adversaries().items()):
            if kind != "all" and a.get("kind", "generic") != kind:
                continue
            cat = a.get("category", "human")
            if category != "all" and cat != category:
                continue
            hay = f"{key} {a.get('description', '')} {a.get('tier', '')} {cat}".lower()
            if q and q not in hay:
                continue
            # ✦ creature, ★ named, ▸ generic human.
            badge = "✦" if cat != "human" else ("★" if a.get("kind") == "named" else "▸")
            hp = a.get("health", {}).get("hit_points", "?")
            tail = a.get("tier") or (cat if cat != "human" else "")
            self.lib_list.insert("end", f"{badge} {key}   (HP {hp}, {tail})")
            self._lib_keys.append(key)

    def _on_select(self, _e):
        sel = self.lib_list.curselection()
        if not sel:
            return
        key = self._lib_keys[sel[0]]
        self.draft = copy.deepcopy(self._adversaries()[key])
        self.draft_key = key
        self._show(self.draft, key)

    def _new(self, kind):
        self.draft = blank_adversary(kind)
        self.draft_key = None
        self._show(self.draft, None)
        self.set_status(f"New {kind} adversary — fill in and Save.", "#1a5fb4")

    def _duplicate(self):
        if self.draft_key is None:
            return
        self.draft = copy.deepcopy(self._adversaries()[self.draft_key])
        self.draft["name"] = f"{self.draft_key} (copy)"
        self.draft["source"] = "user"
        self.draft_key = None
        self._show(self.draft, None)

    def _delete(self):
        if self.draft_key is None or self.draft_key not in self._adversaries():
            return
        if not messagebox.askyesno("Delete adversary",
                                   f"Delete '{self.draft_key}' from the working library?"):
            return
        del self._adversaries()[self.draft_key]
        save_combat(self.combat, self.rules.data_dir)
        self.set_status(f"Deleted {self.draft_key}.", "#a33")
        self.draft_key = None
        self._refresh_library()
        if self.on_change:
            self.on_change()
        self._new("generic")

    # -- editor load / collect ---------------------------------------------

    def _show(self, adv, key):
        self.header.config(text=(f"Editing: {key}" if key else "New adversary"))
        self.kind_var.set(adv.get("kind", "generic"))
        self.category_var.set(adv.get("category", "human"))
        self.name_var.set(adv.get("name", "") or key or "")
        self.tier_var.set(adv.get("tier", "trained"))
        self.promo_var.set(adv.get("promotion_title", ""))
        self.culture_var.set(adv.get("culture", ""))
        self.religion_var.set(adv.get("religion", ""))
        self.desc_var.set(adv.get("description", ""))
        ch = adv.get("characteristics", {})
        for k in CHAR_ORDER:
            self.char_vars[k].set(str(ch.get(k, 10)))
        # attacks
        for row in list(self.attack_rows):
            row["frame"].destroy()
        self.attack_rows = []
        for atk in adv.get("attacks", []):
            self._add_attack_row(atk)
        # armour — use the structured block if present, else parse the legacy
        # free-text armour_desc so built-in adversaries show their pieces.
        arm = adv.get("armour") or {}
        if arm.get("pieces") or arm.get("helmet") or arm.get("shield"):
            pieces, helmet, shield = (arm.get("pieces", []), arm.get("helmet", ""),
                                      arm.get("shield", ""))
        else:
            pieces, helmet, shield = parse_armour_desc(adv.get("armour_desc", ""), self.combat)
        for name, var in self.piece_vars.items():
            var.set(name in pieces)
        self.helmet_var.set(helmet)
        self.shield_var.set(shield)
        # skills/traits/passions
        self._set_text(self.skills_text, adv.get("skills", {}))
        self._set_text(self.traits_text, adv.get("traits", {}))
        self._set_text(self.passions_text, adv.get("passions", {}))
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", adv.get("notes", "") or "")
        # creature combat stats (from health/other)
        h, o = adv.get("health", {}), adv.get("other", {})
        src = {"hit_points": h.get("hit_points", ""), "major_wound": h.get("major_wound", ""),
               "knockdown": h.get("knockdown", ""), "unconscious": h.get("unconscious", ""),
               "healing_rate": o.get("healing_rate", ""), "movement": o.get("movement", ""),
               "armor_points": o.get("armor_points", ""), "shield": o.get("shield", ""),
               "glory": o.get("glory", ""), "valorous_modifier": o.get("valorous_modifier", "")}
        for k, var in self.creature_vars.items():
            var.set("" if src[k] == "" else str(src[k]))
        self._snapshot_traits()
        self._recompute_derived()
        self._recompute_armour()
        self._toggle_category_ui()

    def _creature_int(self, key):
        try:
            return int(float(self.creature_vars[key].get()))
        except (TypeError, ValueError):
            return 0

    def _toggle_category_ui(self, *_):
        """Humans show the derived-stats reference + worn-armour pieces; creatures
        show the explicit 'Creature combat stats' block instead (their Damage/Move
        are printed, so the human-formula 'Derived' line would only mislead).
        Anchored packs keep the human section order intact when toggling back."""
        human = self.category_var.get() == "human"
        self.cf_creature.pack_forget()
        self._derived_frame.pack_forget()
        self._armour_frame.pack_forget()
        if human:
            self._derived_frame.pack(fill="x", padx=8, pady=(6, 0), after=self._char_frame)
            self._armour_frame.pack(fill="x", padx=8, pady=(6, 0),
                                    after=self._attacks_section)
        else:
            self.cf_creature.pack(fill="x", padx=8, pady=(6, 0), after=self._char_frame)

    @staticmethod
    def _set_text(widget, m):
        widget.delete("1.0", "end")
        widget.insert("1.0", _map_to_text(m))

    # -- pick-and-add vocabularies + autoroll ------------------------------

    def _skill_vocab(self):
        names = set()
        for info in self.rules.social_classes.values():
            names |= set(info.get("skills", {}))
        names |= {w.get("skill") for w in self.combat.get("weapons", {}).values()
                  if w.get("skill")}
        return sorted(names)

    def _trait_vocab(self):
        # Show each trait with its balancing partner in brackets, e.g.
        # "Valorous (Cowardly)", so the pairing is easy to remember.
        opts = []
        for a, b in self.rules.trait_pairs:
            opts.append(f"{a} ({b})")
            opts.append(f"{b} ({a})")
        return sorted(opts)

    def _passion_vocab(self):
        return sorted(self.rules.passion_starts)

    @staticmethod
    def _roll_skill_value(_name):
        return roll_expr("2D6+5")            # a competent 7–17

    @staticmethod
    def _roll_trait_value(_name):
        return max(1, min(19, roll_expr("2D6+3")))   # rulebook base, 1–19

    def _roll_passion_value(self, name):
        base = self.rules.passion_starts.get(name)
        if base is not None:
            return max(1, min(25, base + random.randint(-2, 3)))
        return max(1, min(20, roll_expr("2D6+8")))

    @staticmethod
    def _append_line(widget, line):
        current = widget.get("1.0", "end").rstrip("\n")
        widget.delete("1.0", "end")
        widget.insert("1.0", (current + "\n" if current else "") + line)
        widget.see("end")

    def _append_stat(self, text_widget, name, roll_fn):
        """Add 'name value' (autorolled) to the list, unless already present."""
        name = name.strip()
        if not name:
            return
        if name in _text_to_map(text_widget.get("1.0", "end")):
            self.set_status(f"{name} is already listed.", "#a33")
            return
        line = f"{name} {roll_fn(name)}"
        self._append_line(text_widget, line)
        self.set_status(f"Added {line}.", "#2a7d2a")

    # -- trait pairs (balanced, sum to 20) ---------------------------------

    def _partner_of(self, trait):
        for a, b in self.rules.trait_pairs:
            if trait == a:
                return b
            if trait == b:
                return a
        return None

    def _add_trait(self, choice):
        """Add a trait. If its pair partner is listed, value = 20 - partner;
        otherwise roll the first of the pair. The dropdown shows 'Trait (Partner)'."""
        name = choice.split(" (")[0].strip()
        if not name:
            return
        current = _text_to_map(self.traits_text.get("1.0", "end"))
        if name in current:
            self.set_status(f"{name} is already listed.", "#a33")
            return
        partner = self._partner_of(name)
        if partner and partner in current:
            value = max(0, min(20, 20 - current[partner]))
            note = f"balanced against {partner} {current[partner]}"
        else:
            value = self._roll_trait_value(name)
            note = "rolled"
        self._append_line(self.traits_text, f"{name} {value}")
        self._snapshot_traits()
        self.set_status(f"Added {name} {value} ({note}).", "#2a7d2a")

    def _snapshot_traits(self):
        self._traits_snapshot = _text_to_map(self.traits_text.get("1.0", "end"))

    def _normalise_traits(self, *_):
        """After a manual edit, keep every listed pair summing to 20 without
        disturbing a score the user did not touch:

        - A pre-existing score is never changed just because its partner was
          added or given an out-of-range value; instead the added/invalid side
          is recalculated (= 20 - the kept side).
        - A valid edit (0..20) to an existing score wins, and its partner
          follows.
        """
        raw = _text_to_map(self.traits_text.get("1.0", "end"))
        if not raw:
            self._traits_snapshot = {}
            return
        order = list(raw)
        snap = getattr(self, "_traits_snapshot", {})
        m = {n: max(0, min(20, raw[n])) for n in order}
        in_range = lambda x: 0 <= raw[x] <= 20
        handled = set()
        for n in order:
            if n in handled:
                continue
            p = self._partner_of(n)
            if not p or p not in m:
                continue
            if (n in snap) != (p in snap):
                # One side was just added -> keep the side that already existed.
                auth = n if n in snap else p
            elif n in snap and p in snap:
                # Both existed -> a valid edit wins; an out-of-range edit yields
                # to the untouched partner instead of zeroing it.
                n_ch, p_ch = snap[n] != raw[n], snap[p] != raw[p]
                if n_ch and not p_ch:
                    auth = n if in_range(n) else p
                elif p_ch and not n_ch:
                    auth = p if in_range(p) else n
                else:
                    auth = n if order.index(n) < order.index(p) else p
            else:  # both newly added -> earlier-listed wins
                auth = n if order.index(n) < order.index(p) else p
            other = p if auth == n else n
            m[other] = max(0, min(20, 20 - m[auth]))
            handled.update((n, p))
        new = "\n".join(f"{k} {m[k]}" for k in order)
        if new != self.traits_text.get("1.0", "end").rstrip("\n"):
            self.traits_text.delete("1.0", "end")
            self.traits_text.insert("1.0", new)
            self.set_status("Balanced trait pairs (each sums to 20).", "#1a5fb4")
        self._traits_snapshot = dict(m)

    def _char_ints(self):
        out = {}
        for k in CHAR_ORDER:
            try:
                out[k] = int(self.char_vars[k].get())
            except (TypeError, ValueError):
                out[k] = 0
        return out

    def _collect(self):
        adv = blank_adversary(self.kind_var.get(), self.category_var.get())
        adv["name"] = self.name_var.get().strip()
        adv["tier"] = self.tier_var.get()
        adv["promotion_title"] = self.promo_var.get().strip() or "Champion"
        adv["culture"] = self.culture_var.get().strip()
        adv["religion"] = self.religion_var.get().strip()
        adv["description"] = self.desc_var.get().strip()
        adv["characteristics"] = self._char_ints()
        if self.category_var.get() == "human":
            # Humans: derive Hit Points/Move/etc. from characteristics; armour
            # from worn pieces.
            d = self.rules.derive_stats(adv["characteristics"])
            adv["health"] = {"hit_points": d["Hit Points"], "knockdown": d["Knockdown"],
                             "major_wound": d["Major Wound"], "unconscious": d["Unconscious"]}
            pieces = [n for n, v in self.piece_vars.items() if v.get()]
            ap, sp = compute_armour(pieces, self.helmet_var.get(), self.shield_var.get(),
                                    self.combat)
            adv["armour"] = {"pieces": pieces, "helmet": self.helmet_var.get(),
                             "shield": self.shield_var.get()}
            adv["armour_desc"] = describe_armour(pieces, self.helmet_var.get(),
                                                 self.shield_var.get())
            adv["other"] = {"movement": d["Move"], "armor_points": ap, "shield": sp,
                            "glory": adv["other"].get("glory", 0),
                            "healing_rate": d["Healing Rate"]}
        else:
            # Creatures: printed stats are the source of truth (never re-derive —
            # that would turn a Dragon's 16d6/Move 65 into human-formula values).
            cv = {k: self._creature_int(k) for k in self.creature_vars}
            adv["health"] = {"hit_points": cv["hit_points"], "knockdown": cv["knockdown"],
                             "major_wound": cv["major_wound"], "unconscious": cv["unconscious"]}
            adv["armour"] = {"pieces": [], "helmet": "", "shield": ""}
            adv["armour_desc"] = "Natural armour" + (" + shield" if cv["shield"] else "")
            adv["other"] = {"movement": cv["movement"], "armor_points": cv["armor_points"],
                            "shield": cv["shield"], "glory": cv["glory"],
                            "healing_rate": cv["healing_rate"]}
            if self.creature_vars["valorous_modifier"].get().strip():
                adv["other"]["valorous_modifier"] = cv["valorous_modifier"]
        adv["attacks"] = self._collect_attacks()
        adv["skills"] = _text_to_map(self.skills_text.get("1.0", "end"))
        adv["traits"] = _text_to_map(self.traits_text.get("1.0", "end"))
        adv["passions"] = _text_to_map(self.passions_text.get("1.0", "end"))
        adv["notes"] = self.notes_text.get("1.0", "end").strip()
        return adv

    # -- attacks -----------------------------------------------------------

    def _add_attack_row(self, atk=None):
        atk = atk or {"weapon": "", "skill": "", "value": 10, "damage": "1D6"}
        fr = ttk.Frame(self.attacks_frame)
        fr.pack(fill="x", pady=1)
        wv = tk.StringVar(value=atk.get("weapon", ""))
        sv = tk.StringVar(value=str(atk.get("value", 10)))
        dv = tk.StringVar(value=atk.get("damage", ""))
        # Editable (not readonly) so natural attacks — Claws, Bite, Gore… — can
        # be typed for creatures, while humans still pick from the weapon list.
        ttk.Combobox(fr, textvariable=wv, width=16, state="normal",
                     values=list(self.combat.get("weapons", {}))).pack(side="left")
        ttk.Label(fr, text="skill").pack(side="left", padx=(6, 1))
        ttk.Entry(fr, textvariable=sv, width=4).pack(side="left")
        ttk.Label(fr, text="dmg").pack(side="left", padx=(6, 1))
        ttk.Entry(fr, textvariable=dv, width=8).pack(side="left")
        ttk.Button(fr, text="✕", width=2,
                   command=lambda: self._remove_attack_row(row)).pack(side="left", padx=(6, 0))
        row = {"frame": fr, "weapon": wv, "value": sv, "damage": dv}
        self.attack_rows.append(row)
        return row

    def _remove_attack_row(self, row):
        row["frame"].destroy()
        self.attack_rows.remove(row)

    def _add_selected_weapon(self):
        weapon = self.new_weapon_var.get()
        if not weapon:
            return
        wdef = self.combat["weapons"][weapon]
        base_damage = self.rules.derive_stats(self._char_ints())["Damage"]
        self._add_attack_row({
            "weapon": weapon, "skill": wdef.get("skill", weapon),
            "value": self._char_ints().get("DEX", 10),
            "damage": resolve_weapon_damage(wdef, base_damage),
        })

    def _collect_attacks(self):
        out = []
        for row in self.attack_rows:
            weapon = row["weapon"].get()
            if not weapon:
                continue
            wdef = self.combat.get("weapons", {}).get(weapon, {})
            try:
                value = int(row["value"].get())
            except (TypeError, ValueError):
                value = 0
            out.append({"weapon": weapon, "skill": wdef.get("skill", weapon),
                        "value": value, "damage": row["damage"].get().strip()})
        return out

    # -- live recompute ----------------------------------------------------

    def _recompute_derived(self):
        d = self.rules.derive_stats(self._char_ints())
        self.derived_lbl.config(text=(
            f"Hit Points {d['Hit Points']}   Move {d['Move']}   Damage {d['Damage']}   "
            f"Healing {d['Healing Rate']}\nMajor Wound {d['Major Wound']}   "
            f"Knockdown {d['Knockdown']}   Unconscious {d['Unconscious']}"))

    def _recompute_armour(self):
        pieces = [n for n, v in self.piece_vars.items() if v.get()]
        ap, sp = compute_armour(pieces, self.helmet_var.get(), self.shield_var.get(), self.combat)
        total = ap + sp
        self.armour_lbl.config(text=(
            f"{describe_armour(pieces, self.helmet_var.get(), self.shield_var.get()) or '(none)'}"
            f"   →   {ap} armour + {sp} shield = {total} total"))

    # -- auto / roll -------------------------------------------------------

    def _roll_characteristics(self):
        culture = self.culture_var.get() or (self.generator.culture_names() or [""])[0]
        stats, _ = self.rules.roll_characteristics(culture)
        for k in CHAR_ORDER:
            self.char_vars[k].set(str(stats[k]))
        self._recompute_derived()

    def _auto_generate(self):
        culture = self.culture_var.get() or (self.generator.culture_names() or [""])[0]
        cls = None if self.gen_class.get() == "Random" else self.gen_class.get()
        r = self.generator.generate(culture, self.gen_gender.get(), cls)
        # keep the current identity; refresh combat-relevant fields from the NPC
        src = draft_from_npc(r, self.combat)
        for k in CHAR_ORDER:
            self.char_vars[k].set(str(src["characteristics"][k]))
        for row in list(self.attack_rows):
            row["frame"].destroy()
        self.attack_rows = []
        for atk in src["attacks"]:
            self._add_attack_row(atk)
        self._set_text(self.skills_text, src["skills"])
        self._set_text(self.traits_text, src["traits"])
        self._set_text(self.passions_text, src["passions"])
        self._snapshot_traits()
        if not self.culture_var.get():
            self.culture_var.set(culture)
        if not self.religion_var.get():
            self.religion_var.set(r.get("religion", ""))
        if not self.desc_var.get():
            self.desc_var.set(_npc_looks(r))
        self._recompute_derived()
        self.set_status(f"Auto-generated stats from a {culture} {r.get('social_class', '')}.",
                        "#2a7d2a")

    # -- save / revert -----------------------------------------------------

    def _revert(self):
        if self.draft_key and self.draft_key in self._adversaries():
            self.draft = copy.deepcopy(self._adversaries()[self.draft_key])
            self._show(self.draft, self.draft_key)
        else:
            self._show(blank_adversary(self.kind_var.get()), None)

    def _save(self):
        adv = self._collect()
        key = adv["name"]
        if not key:
            messagebox.showwarning("Name required",
                                   "Enter a name (named) or type name (generic) before saving.")
            return
        existing = self._adversaries()
        if key in existing and key != self.draft_key:
            if not messagebox.askyesno("Overwrite",
                                       f"An adversary named '{key}' exists. Overwrite it?"):
                return
        # renamed an existing entry -> drop the old key
        if self.draft_key and self.draft_key != key and self.draft_key in existing:
            del existing[self.draft_key]
        existing[key] = adv
        path = save_combat(self.combat, self.rules.data_dir)
        self.draft_key = key
        self._refresh_library()
        if self.on_change:
            self.on_change()
        self.set_status(f"Saved '{key}' to {path}.", "#2a7d2a")

    # -- external entry point (Create Adversary bridge from the NPC tab) ---

    def open_with_draft(self, draft):
        self.draft = copy.deepcopy(draft)
        self.draft_key = None
        self._show(self.draft, None)
        self.set_status("Adversary drafted from the NPC — review, pick armour, then Save.",
                        "#1a5fb4")
