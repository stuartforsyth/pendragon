# Pendragon — rules index

A page index of every game system extracted into the rules corpus (`rules_corpus/**`). Each **system** has its own index page; individual topics link straight to their corpus file with printed-page citations.

> Prose rules live in `rules_corpus/**/*.md`; the derived full-text index is `data/rules_index.jsonl` (regenerate with `python build_rules_index.py`). Page numbers are **printed** book pages — PDF page = printed + 3.

## Systems

| System | Book | Topics | Index |
|--------|------|--------|-------|
| **Combat** | Core, ch. 7 | 32 | [combat.md](combat.md) |
| **Feasting** | GM Handbook, ch. 3 | 1 | [feasts.md](feasts.md) |
| **Battle** | Core / GM / Battle Cards | 0 (pending) | [battles.md](battles.md) |

## Other extracted topics

Standalone rules not (yet) belonging to a multi-topic system index:

### 2 — The Game System

| Topic | Pages | Tags |
|-------|-------|------|
| [Characteristics (SIZ, DEX, STR, CON, APP) & Derived values](../../rules_corpus/core/02-game-system/characteristics.md) | 33, 34 | `characteristics`, `siz`, `dex`, `str`, `con`, `app`, `derived`, `knockdown`, `hit-points`, `damage`, `healing-rate`, `movement-rate`, `major-wound` |
| [Core Concepts & Dice (Statistics, Values, Roll vs Check)](../../rules_corpus/core/02-game-system/concepts-and-dice.md) | 25, 26, 27 | `concepts`, `statistic`, `value`, `trait`, `passion`, `dice`, `d20`, `d6`, `roll`, `check`, `rounding`, `quick-values` |
| [The Critical Bonus (Statistics over 20)](../../rules_corpus/core/02-game-system/critical-bonus.md) | 28, 30, 31 | `resolution`, `skill`, `trait`, `passion`, `critical`, `critical-bonus`, `fumble`, `opposed`, `mastery` |
| [Experience Checks](../../rules_corpus/core/02-game-system/experience-checks.md) | 32, 33 | `experience`, `check`, `improvement`, `winter-phase`, `trait`, `passion`, `skill`, `glory` |
| [The Glory Roll](../../rules_corpus/core/02-game-system/glory-roll.md) | 34 | `glory`, `glory-roll`, `feast`, `social`, `opposed` |
| [Modifiers (Bonuses, Penalties, Reflexive) & Table 2.1](../../rules_corpus/core/02-game-system/modifiers.md) | 29, 30, 31, 32 | `modifiers`, `bonus`, `penalty`, `reflexive`, `skill-modifiers`, `values-below-one`, `fumble-range`, `damage-modifier` |
| [Movement — Rate, Speed Multipliers & Overland Travel](../../rules_corpus/core/02-game-system/movement.md) | 34, 35, 37 | `movement`, `movement-rate`, `speed`, `overland`, `travel`, `forced-march`, `horse`, `exhaustion`, `roads`, `weather` |
| [Resolution — Unopposed, Opposed & Fixed](../../rules_corpus/core/02-game-system/resolution.md) | 27, 28, 29 | `resolution`, `roll-under`, `success`, `critical`, `failure`, `fumble`, `opposed`, `partial-success`, `tie`, `mutual-failure`, `fixed-opposition` |

### 5 — Skills

| Topic | Pages | Tags |
|-------|-------|------|
| [Horsemanship (Skill) + fumbling a Horsemanship roll](../../rules_corpus/core/05-skills/horsemanship.md) | 95, 106 | `skills`, `horsemanship`, `horse`, `riding`, `deed`, `inquiry`, `fumble` |
