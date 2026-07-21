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
| [The Critical Bonus (Statistics over 20)](../../rules_corpus/core/02-game-system/critical-bonus.md) | 28, 30, 31 | `resolution`, `skill`, `trait`, `passion`, `critical`, `critical-bonus`, `fumble`, `opposed`, `mastery` |

### 5 — Skills

| Topic | Pages | Tags |
|-------|-------|------|
| [Horsemanship (Skill) + fumbling a Horsemanship roll](../../rules_corpus/core/05-skills/horsemanship.md) | 95, 106 | `skills`, `horsemanship`, `horse`, `riding`, `deed`, `inquiry`, `fumble` |
