# Corpus Coverage Map

Audit of `rules_corpus/` against the two source books in `rulebooks/`. Page
numbers are **printed** pages; PDF page = printed + 3 for both books.

**Corpus size: 120 rule files** (96 pre-baseline + 25 imported from a parallel
corpus that had moved further ahead, 12 Sep 2026 — see `EXTRACTION-PLAN.md`
for the method and the ordered queue of what's left).

Status: ✅ covered · ⚠️ partial · ❌ not extracted

---

## Core Rulebook (258 pp., `rulebooks/corerulebook.pdf`) — essentially complete

| Ch. | Title | Pages | Status | Notes |
|---|---|---|---|---|
| 1 | Welcome to Camelot | 3–24 | ⚠️ | Ranks & mercenary pay extracted. **Not extracted:** *This Is Another World*, *Time Passes*, setting matter (pp. 3–11) — background, not rules. |
| 2 | The Game System | 25–38 | ✅ | 8 files |
| 3 | Creating Your Player-knight | 39–60 | ✅ | 9 files |
| 4 | Traits and Passions | 61–94 | ✅ | 7 files |
| 5 | Skills | 95–114 | ✅ | 4 files + horsemanship fumbles |
| 6 | Aspirations | 115–130 | ✅ | 6 files |
| 7 | Combat | 131–158 | ✅ | 32 files |
| 8 | Weapons | 159–168 | ✅ | 3 files + rebated damage |
| 9 | Armor | 169–178 | ✅ | 3 files + shield damage |
| 10 | Horses | 179–188 | ✅ | 3 files + horses taking damage |
| 11 | Injury & Health | 189–200 | ✅ | 4 files + falling from a horse |
| 12 | Wealth, Treasure, & Trade | 201–212 | ✅ | 4 files |
| 13 | Solo Scenarios | 213–220 | ✅ | 2 files |
| 14 | The Winter Phase | 221–236 | ✅ | 4 files |
| A | Notes on the New Edition | 237–240 | ❌ | 5th→6th conversion notes. Not rules for play. |
| B | Coat of Arms Generator | 241–247 | ✅ | 1 file |
| C | Pre-Generated Characters | 248–251 | ❌ | Six sample knights. Not rules. |

---

## GM Book (`rulebooks/gmhandbook.pdf`) — partly extracted

| Ch. | Title | Status | Notes |
|---|---|---|---|
| 1 | The Fabled Realm | ❌ | Geography, place names, hygiene, customs, "Which Arthur Is This?", Who's Who, Creating a Campaign, Sample Holding. |
| 2 | Running Pendragon | ❌ | Classic setting, the March of History, GM advice, How to Use Characteristics, Sessions/Scenarios/Campaigns, Tracking Time. |
| 3 | Arthurian Acts | ✅ | 11 files: feasting, tournaments, tournament melee & joust, hunting, races & chases, captivity, fine amor, intoxication, accommodations, seducing at court, visiting a foreign court. |
| 4 | (unassessed) | ❌ | Not yet audited against the corpus. |
| 5 | (unassessed) | ❌ | Not yet audited against the corpus. |
| 6 | Battle | ⚠️ | 8 files: running/fighting a battle, battlefield position & surrender, after the battle, countercharge, debilitated in battle, foe encounters (foot/mounted/tribal), plunder & encounters. |
| A | Glory | ✅ | 3 files: combat & adventure glory, passive glory & ladies, titles/offices & expenditure. |

Chapters 4–5 and the rest of the GM Book beyond what's listed have not been
individually audited chapter-by-chapter in this pass — treat any topic from
those chapters as ❌ (not extracted) unless a grep of the corpus turns it up.

---

**Battle Cards** (`rulebooks/battlecards.pdf`) and the **Feast Event Cards**
(`rulebooks/pendragon_printable_feast_cards.pdf`) feed `data/combat.json`
(battle-card conrois/bestiary) and the `feasting.md` card catalogue directly —
not tracked chapter-by-chapter here since they're tables, not prose chapters.

**Update this file's statuses and the count above whenever a queue item in
`EXTRACTION-PLAN.md` is completed**, and whenever `extract-rule` adds a file.
