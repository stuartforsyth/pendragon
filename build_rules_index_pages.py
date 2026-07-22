#!/usr/bin/env python3
"""Generate docs/rules-index/*.md from data/rules_index.jsonl.

Human-browsable page index of the rules corpus: a master index plus dedicated
per-system pages for combat, feasts, and battle. Derived from the JSONL index —
re-run after `build_rules_index.py` whenever the corpus changes.
"""
import json, os, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "rules-index")
os.makedirs(OUT, exist_ok=True)

rows = []
with open(os.path.join(ROOT, "data", "rules_index.jsonl")) as f:
    for line in f:
        rows.append(json.loads(line))
by_id = {r["id"]: r for r in rows}


def rel(source):
    # source is repo-relative e.g. rules_corpus/core/07-combat/x.md
    # link is from docs/rules-index/  -> ../../<source>
    return "../../" + source


def pp(pages):
    return ", ".join(str(p) for p in pages)


def key_tags(r, drop=("combat", "action"), n=3):
    kept = [t for t in r["tags"] if t not in drop] or list(r["tags"])
    return ", ".join("`" + t + "`" for t in kept[:n])


def row_line(r):
    return (f"| [{r['title']}]({rel(r['source'])}) | {pp(r['pages'])} | "
            f"{key_tags(r)} |")


def table(ids):
    out = ["| Topic | Core pp. | Key tags |", "|-------|----------|----------|"]
    for i in ids:
        out.append(row_line(by_id[i]))
    return "\n".join(out)


# ---- Combat ---------------------------------------------------------------
combat_groups = [
    ("The Combat Round & Resolution", [
        "core.combat.combat-round",
        "core.combat.resolution-matrix",
        "core.combat.winners-outcome",
        "core.combat.damage-and-wounds",
        "core.combat.knockdown",
        "core.combat.dropped-broken-weapon",
        "core.combat.combat-movement",
    ]),
    ("Actions — Attack, Defend & Utility", [
        "core.combat.actions-overview",
        "core.combat.action-attack",
        "core.combat.defensive-actions",
        "core.combat.action-disarm",
        "core.combat.action-hook",
        "core.combat.action-self-sacrifice",
        "core.combat.action-call-squire",
        "core.combat.utility-actions",
    ]),
    ("Grappling & Brawling", [
        "core.combat.brawling",
        "core.combat.action-grapple",
    ]),
    ("Mounted Combat", [
        "core.combat.mounted-combat",
        "core.combat.mounted-utility-actions",
        "core.combat.action-mounted-charge",
        "core.combat.charge-distance",
        "core.combat.action-set-spear",
        "core.combat.action-trample",
        "core.combat.action-zigzag",
    ]),
    ("Distances, Missiles & Re-Arming", [
        "core.combat.melee-distances",
        "core.combat.missile-distances",
        "core.combat.missile-weapons",
        "core.combat.re-arming",
    ]),
    ("Modifiers & Protection", [
        "core.combat.combat-modifiers",
        "core.combat.multiple-opponents",
        "core.combat.protection",
    ]),
    ("Worked Example", [
        "core.combat.example-full-combat",
    ]),
]

# completeness check
covered = {i for _, ids in combat_groups for i in ids}
all_combat = {r["id"] for r in rows if r["id"].startswith("core.combat.")}
missing = all_combat - covered
extra = covered - all_combat
assert not missing, f"combat topics not in any group: {missing}"
assert not extra, f"grouped ids that don't exist: {extra}"

combat_md = [
    "# Combat — rules index",
    "",
    "The full melee/mounted/missile combat system from **Core Rulebook, "
    "Chapter 7 — Combat**. Every extracted topic is listed below with its "
    "printed page citation; click a title to open the corpus file.",
    "",
    "> Page numbers are **printed** core-rulebook pages. PDF page = printed + 3.",
    "",
    f"**{len(all_combat)} topics** · source book: `core` · "
    "[← all game systems](README.md)",
    "",
]
for name, ids in combat_groups:
    combat_md += [f"## {name}", "", table(ids), ""]
with open(os.path.join(OUT, "combat.md"), "w") as f:
    f.write("\n".join(combat_md).rstrip() + "\n")


# ---- Feasts ---------------------------------------------------------------
# Feast index = the Feasts & Banquets Arthurian Act (GM book). A `feast` tag on a
# core rule (e.g. the Glory Roll) is feast-relevant but belongs to its own system.
feast_ids = [r["id"] for r in rows
             if r["book"] == "gm" and "feast" in r["tags"]]
feast_md = [
    "# Feasting — rules index",
    "",
    "The **Feasts & Banquets** Arthurian Act from the **GM Handbook, "
    "Chapter 3 — Arthurian Acts**: seating by precedence, the geniality "
    "track, Event Cards, and the Glory awards for hosting and attending.",
    "",
    "> Page numbers are **printed** GM-handbook pages. PDF page = printed + 3.",
    "",
    f"**{len(feast_ids)} topic(s)** · source book: `gm` · "
    "[← all game systems](README.md)",
    "",
    "| Topic | GM Handbook pp. | Tags |",
    "|-------|-----------------|------|",
]
for i in feast_ids:
    r = by_id[i]
    feast_md.append(
        f"| [{r['title']}]({rel(r['source'])}) | {pp(r['pages'])} | "
        f"{', '.join('`'+t+'`' for t in r['tags'])} |"
    )
feast_md += [
    "",
    "## Related data",
    "",
    "- The Feast **Event Card** deck catalogue lives in the app data "
    "(`data/combat.json`), added alongside this rule.",
    "",
]
with open(os.path.join(OUT, "feasts.md"), "w") as f:
    f.write("\n".join(feast_md).rstrip() + "\n")


# ---- Battle ---------------------------------------------------------------
# Battle system = the GM Handbook "Battle" chapter + the Battle Cards book. A
# `battle` tag on a core rule (e.g. using Passions in battle) is battle-relevant
# but belongs to its own system, so it is excluded here.
battle_ids = [r["id"] for r in rows
              if r["book"] == "battlecards"
              or (r["book"] == "gm" and "Battle" in r["chapter"])]
battle_md = [
    "# Battle — rules index",
    "",
    "The mass-combat **Battle system** (GM Handbook, Chapter 6 — Battle): "
    "conrois & Morale, the Army Commander's roll, Battle Turns and Encounters, "
    "and casualties/Glory. The **Battle Cards** deck is a separate source.",
    "",
    "> Page numbers are **printed** GM-handbook pages. PDF page = printed + 3.",
    "",
    f"**{len(battle_ids)} topic(s)** · [← all game systems](README.md)",
    "",
]
if battle_ids:
    battle_md += ["| Topic | Pages | Tags |", "|-------|-------|------|"]
    for i in battle_ids:
        r = by_id[i]
        battle_md.append(
            f"| [{r['title']}]({rel(r['source'])}) | {pp(r['pages'])} | "
            f"{', '.join('`'+t+'`' for t in r['tags'])} |")
    battle_md.append("")
else:
    battle_md += [
        "> **Status: not yet extracted.** Sources: `rulebooks/gmhandbook.pdf` "
        "(Battle chapter) and `rulebooks/battlecards.pdf` (the deck).",
        "",
    ]
with open(os.path.join(OUT, "battles.md"), "w") as f:
    f.write("\n".join(battle_md).rstrip() + "\n")


# ---- Master index (all game systems) --------------------------------------
other = [r for r in rows
         if not r["id"].startswith("core.combat.")
         and "feast" not in r["id"]]
other_by_chapter = collections.OrderedDict()
for r in sorted(other, key=lambda r: r["id"]):
    other_by_chapter.setdefault(r["chapter"], []).append(r)

master = [
    "# Pendragon — rules index",
    "",
    "A page index of every game system extracted into the rules corpus "
    "(`rules_corpus/**`). Each **system** has its own index page; individual "
    "topics link straight to their corpus file with printed-page citations.",
    "",
    "> Prose rules live in `rules_corpus/**/*.md`; the derived full-text index "
    "is `data/rules_index.jsonl` (regenerate with `python build_rules_index.py`). "
    "Page numbers are **printed** book pages — PDF page = printed + 3.",
    "",
    "## Systems",
    "",
    "| System | Book | Topics | Index |",
    "|--------|------|--------|-------|",
    f"| **Combat** | Core, ch. 7 | {len(all_combat)} | [combat.md](combat.md) |",
    f"| **Feasting** | GM Handbook, ch. 3 | {len(feast_ids)} | [feasts.md](feasts.md) |",
    f"| **Battle** | GM Handbook, ch. 6 | {len(battle_ids)} | [battles.md](battles.md) |",
    "",
    "## Other extracted topics",
    "",
    "Standalone rules not (yet) belonging to a multi-topic system index:",
    "",
]
for chapter, rs in other_by_chapter.items():
    master.append(f"### {chapter}")
    master.append("")
    master.append("| Topic | Pages | Tags |")
    master.append("|-------|-------|------|")
    for r in rs:
        master.append(
            f"| [{r['title']}]({rel(r['source'])}) | {pp(r['pages'])} | "
            f"{', '.join('`'+t+'`' for t in r['tags'])} |")
    master.append("")

with open(os.path.join(OUT, "README.md"), "w") as f:
    f.write("\n".join(master).rstrip() + "\n")

print("wrote:", sorted(os.listdir(OUT)))
