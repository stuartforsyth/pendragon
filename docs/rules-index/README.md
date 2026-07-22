# Pendragon — rules index

A page index of every game system extracted into the rules corpus (`rules_corpus/**`). Each **system** has its own index page; individual topics link straight to their corpus file with printed-page citations.

> Prose rules live in `rules_corpus/**/*.md`; the derived full-text index is `data/rules_index.jsonl` (regenerate with `python build_rules_index.py`). Page numbers are **printed** book pages — PDF page = printed + 3.

## Systems

| System | Book | Topics | Index |
|--------|------|--------|-------|
| **Combat** | Core, ch. 7 | 32 | [combat.md](combat.md) |
| **Feasting** | GM Handbook, ch. 3 | 1 | [feasts.md](feasts.md) |
| **Battle** | Core / GM / Battle Cards | 1 (pending) | [battles.md](battles.md) |

## Other extracted topics

Standalone rules not (yet) belonging to a multi-topic system index:

### 9 — Armor

| Topic | Pages | Tags |
|-------|-------|------|
| [Armor & Helmets (Tables 9.1, 9.2 & 9.3)](../../rules_corpus/core/09-armor/armor-and-helmets.md) | 171, 173, 175, 176, 177 | `armor`, `helmets`, `mail`, `plate`, `textile`, `aketon`, `hauberk`, `coat-of-plates`, `closed-helm`, `tables` |
| [Armoring Up, Stacking & Armor Penalties](../../rules_corpus/core/09-armor/armoring-up-and-penalties.md) | 169, 170 | `armor`, `donning`, `squire`, `stacking`, `penalties`, `heat`, `sleeping`, `protection` |
| [Shields (Types & Table 9.4)](../../rules_corpus/core/09-armor/shields.md) | 176, 177 | `shields`, `buckler`, `targe`, `kite`, `round`, `scutum`, `simple`, `missile-penalty`, `table-9-4` |

### 6 — Aspirations

| Topic | Pages | Tags |
|-------|-------|------|
| [Character Progression & "Winning the Game"](../../rules_corpus/core/06-aspirations/character-progression.md) | 115 | `progression`, `advancement`, `ranks`, `retirement`, `winning` |
| [Glory — Distribution (Table 6.1), Gaining, Benchmarks & Challenges](../../rules_corpus/core/06-aspirations/glory.md) | 123, 124, 125 | `glory`, `prestige-reward`, `precedence`, `benchmarks`, `challenge`, `distribution`, `table-6-1` |
| [Honor — Nature, Ranges, Gaining & Oaths](../../rules_corpus/core/06-aspirations/honor.md) | 116, 117, 118, 119 | `honor`, `public-honor`, `private-honor`, `oaths`, `gaining-honor`, `defending-honor`, `passion` |
| [Ideals — Chivalrous, Religious & Romantic Knight](../../rules_corpus/core/06-aspirations/ideals.md) | 126, 127 | `ideals`, `chivalrous-knight`, `religious-knight`, `romantic-knight`, `chivalry`, `devotion`, `adoration`, `benefits` |
| [Losing Honor — Violations, Accusation, Grievous Dishonor & Flight](../../rules_corpus/core/06-aspirations/losing-honor.md) | 119, 120, 121, 122, 125 | `honor`, `losing-honor`, `grievous-dishonor`, `accusation`, `false-claims`, `prisoner`, `flight` |
| [Knight of the Round Table](../../rules_corpus/core/06-aspirations/round-table.md) | 128, 129 | `round-table`, `siege`, `arthur`, `benefits`, `requirements`, `expulsion`, `honor`, `glory` |

### 3 — Creating Your Player-knight

| Topic | Pages | Tags |
|-------|-------|------|
| [Beginner's Luck — Knights' Luck Benefits (Table 3.9)](../../rules_corpus/core/03-character-creation/beginners-luck.md) | 58, 59 | `beginners-luck`, `heirloom`, `relic`, `family`, `character-creation`, `glory` |
| [Generating Characteristics (Table 3.3) & Distinctive Features (Table 3.4)](../../rules_corpus/core/03-character-creation/characteristics-generation.md) | 45, 46, 47 | `characteristics`, `siz`, `dex`, `str`, `con`, `app`, `cultural-modifier`, `cultural-maximum`, `distinctive-features` |
| [Creation Methods, Culture/Gender/Name & Starting Religion (Table 3.2)](../../rules_corpus/core/03-character-creation/creation-methods-and-personal-info.md) | 42, 43, 44, 45 | `creation`, `pregenerated`, `constructed`, `random`, `culture`, `gender`, `name`, `religion` |
| [Ranks (Page/Squire/Knight) & Training and Practice](../../rules_corpus/core/03-character-creation/knighthood-ranks-and-training.md) | 39, 52, 53 | `knighthood`, `page`, `squire`, `knight`, `esquire`, `ranks`, `training`, `qualification`, `age` |
| [Parent's Glory, Inherited Glory & Quick Family History (Table 3.1)](../../rules_corpus/core/03-character-creation/parents-glory.md) | 40, 41 | `glory`, `inherited-glory`, `family`, `heroic-events`, `parent` |
| [Starting Equipment & Horses (Tables 3.7 & 3.8)](../../rules_corpus/core/03-character-creation/starting-equipment-and-horses.md) | 51, 57, 58 | `equipment`, `gear`, `armor`, `shield`, `horses`, `charger`, `rouncy`, `sumpter`, `squire`, `character-creation` |
| [Starting Passions (Courts, Honor & Inherited Passions)](../../rules_corpus/core/03-character-creation/starting-passions.md) | 50, 51 | `passions`, `courts`, `fidelitas`, `fervor`, `adoratio`, `civilitas`, `honor`, `homage`, `inherited-passions` |
| [Starting Skills (Table 3.5 & 3.6) — Beginning Values, Cultural & Family bonuses](../../rules_corpus/core/03-character-creation/starting-skills.md) | 51, 52 | `skills`, `beginning-values`, `cultural-skill-modifier`, `family-characteristic`, `personal-skill-additions`, `knightly-skills` |
| [Starting Personality Traits & Religious Virtues](../../rules_corpus/core/03-character-creation/starting-traits.md) | 49, 50 | `traits`, `trait-pairs`, `religious-virtues`, `valorous`, `christian`, `pagan`, `character-creation` |

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

### Appendix B — Coat of Arms Generator

| Topic | Pages | Tags |
|-------|-------|------|
| [Random Coat of Arms Generator (Tables B.1–B.3)](../../rules_corpus/core/appendix-heraldry/coat-of-arms-generator.md) | 241, 242, 243, 244, 245, 246 | `heraldry`, `coat-of-arms`, `blazon`, `tincture`, `charge`, `shield`, `generator`, `tables` |

### 10 — Horses

| Topic | Pages | Tags |
|-------|-------|------|
| [Horse Colors, Personality, Care & Armor (Tables 10.5–10.7)](../../rules_corpus/core/10-horses/colors-care-and-armor.md) | 185, 186, 187 | `horses`, `colors`, `passive-glory`, `personality`, `care`, `horse-armor`, `caparison`, `first-aid`, `tables` |
| [Horse Speeds, Exhaustion (Table 10.1) & Training](../../rules_corpus/core/10-horses/horse-speeds-exhaustion-and-training.md) | 181, 182, 184, 185 | `horses`, `gaits`, `speed`, `exhaustion`, `riding-to-death`, `training`, `breeding`, `table-10-1` |
| [Horse Types & Stats (Tables 10.2–10.4)](../../rules_corpus/core/10-horses/types-and-stats.md) | 180, 183, 184 | `horses`, `charger`, `courser`, `rouncy`, `sumpter`, `mule`, `stats`, `tables`, `tack`, `charge-damage` |

### 11 — Injury & Health

| Topic | Pages | Tags |
|-------|-------|------|
| [Aggravation (Table 11.2) & Deterioration](../../rules_corpus/core/11-injury-health/aggravation-and-deterioration.md) | 192, 193, 194 | `aggravation`, `deterioration`, `activity`, `chirurgery`, `debilitated`, `table-11-2` |
| [Environmental Damage — Cold, Falling, Fire, Suffocation & Poison (Table 11.3)](../../rules_corpus/core/11-injury-health/environmental-damage.md) | 193, 194, 195, 196 | `cold`, `disease`, `falling`, `falling-objects`, `fire`, `suffocation`, `poison`, `potency`, `table-11-3` |
| [Healing & Recovery — Natural Healing, Chirurgery & First Aid](../../rules_corpus/core/11-injury-health/healing-recovery.md) | 198, 199 | `healing`, `recovery`, `natural-healing`, `chirurgery`, `first-aid`, `healing-rate`, `sunday` |
| [States of Health & Wounds (Minor/Major/Mortal, Unconscious, Near Death)](../../rules_corpus/core/11-injury-health/states-of-health-and-wounds.md) | 189, 190, 191, 192, 196, 197 | `health`, `debilitated`, `wounds`, `minor-wound`, `major-wound`, `mortal-wound`, `unconscious`, `near-death`, `table-11-1` |

### 5 — Skills

| Topic | Pages | Tags |
|-------|-------|------|
| [Horsemanship (Skill) + fumbling a Horsemanship roll](../../rules_corpus/core/05-skills/horsemanship.md) | 95, 106 | `skills`, `horsemanship`, `horse`, `riding`, `deed`, `inquiry`, `fumble` |
| [Skill Groups (Combat, Courtly, Knightly, Ladies, Woodcraft…)](../../rules_corpus/core/05-skills/skill-groups.md) | 96, 97 | `skills`, `groups`, `combat`, `courtly`, `minsterly`, `knightly`, `non-knightly`, `ladies`, `woodcraft`, `app-cap`, `honor` |
| [Skill Uses — Deeds, Inquiry & Parlance](../../rules_corpus/core/05-skills/skill-uses.md) | 95, 96, 113 | `skills`, `deeds`, `inquiry`, `parlance`, `roll-results`, `leader`, `improving` |
| [Skills Defined (non-combat) — with Tables 5.1, 5.2 & 5.3](../../rules_corpus/core/05-skills/skills-defined.md) | 98, 99, 101, 102, 107, 111 | `skills`, `awareness`, `chirurgery`, `falconry`, `fashion`, `geniality`, `industry`, `hunting`, `stewardship`, `tables` |

### 13 — Solo Scenarios

| Topic | Pages | Tags |
|-------|-------|------|
| [Other Solos — Lost in the Woods, Madness & Pilgrimage](../../rules_corpus/core/13-solo-scenarios/other-solos-and-pilgrimage.md) | 215, 216, 217, 219 | `solo`, `lost-in-the-woods`, `madness`, `pilgrimage`, `miracles`, `table-13-3`, `table-13-4` |
| [Standard Activity Solos (Tables 13.1 & 13.2)](../../rules_corpus/core/13-solo-scenarios/standard-activity-solos.md) | 213, 214 | `solo`, `missed-year`, `household-duties`, `court`, `checks`, `table-13-1`, `table-13-2` |

### 4 — Traits and Passions

| Topic | Pages | Tags |
|-------|-------|------|
| [Afflictions — Madness, Melancholy & Misery](../../rules_corpus/core/04-traits-passions/afflictions.md) | 79, 80, 81 | `afflictions`, `madness`, `melancholy`, `misery`, `curing`, `out-of-game`, `glory`, `adoration` |
| [Directed Traits & Obsessions (Avarice, Fear, Jealousy — Table 4.1)](../../rules_corpus/core/04-traits-passions/directed-traits-and-obsessions.md) | 67, 68, 69, 71 | `directed-traits`, `obsession`, `avarice`, `fear`, `jealousy`, `misery`, `table-4-1` |
| [The Passion Roll — Inspiration, Impassionment & Passion Crisis (Table 4.2)](../../rules_corpus/core/04-traits-passions/passion-roll-inspiration-and-crisis.md) | 74, 76, 77 | `passion-roll`, `inspiration`, `impassioned`, `inspired`, `passion-crisis`, `melancholy`, `madness`, `internal-conflict`, `table-4-2` |
| [Passions of Fervor, Adoratio & Civilitas (Love/Hate, Adoration/Devotion, Chivalry/Hospitality/Station)](../../rules_corpus/core/04-traits-passions/passions-fervor-adoratio-civilitas.md) | 86, 87, 88, 89, 90, 91, 93 | `passions`, `fervor`, `love`, `hate`, `adoratio`, `adoration`, `devotion`, `civilitas`, `chivalry`, `hospitality`, `station` |
| [Passions of Fidelitas (Duty, Fealty, Homage, Loyalty)](../../rules_corpus/core/04-traits-passions/passions-fidelitas.md) | 82, 83, 84, 85 | `passions`, `fidelitas`, `duty`, `fealty`, `homage`, `loyalty`, `liege`, `vassal`, `oath` |
| [Passions — Nature, Levels, Courts, Raising/Lowering & Battle Use](../../rules_corpus/core/04-traits-passions/passions-overview.md) | 71, 73, 74, 78 | `passions`, `courts`, `levels`, `directed-passions`, `raising`, `lowering`, `violating`, `battle`, `gaining` |
| [Traits & Trait Rolls (Decision/Test/Hint, Valorous Roll, Religious Virtues)](../../rules_corpus/core/04-traits-passions/traits-and-trait-rolls.md) | 61, 62, 63, 64, 65, 67 | `traits`, `trait-roll`, `opposing-trait`, `decision-roll`, `test-roll`, `valorous`, `religious-virtues`, `influence`, `famous`, `exalted` |

### 12 — Wealth, Treasure & Trade

| Topic | Pages | Tags |
|-------|-------|------|
| [Coinage & Sources of Treasure](../../rules_corpus/core/12-wealth/coinage-and-treasure.md) | 201, 203 | `coinage`, `libra`, `denarius`, `money`, `treasure`, `loot`, `value`, `standard-of-living` |
| [Favors (Table 12.6)](../../rules_corpus/core/12-wealth/favors.md) | 204, 205, 206 | `favors`, `reciprocity`, `honor`, `table-12-6`, `value` |
| [Price Lists & Supporting Characters (Squires, Table 12.7)](../../rules_corpus/core/12-wealth/prices-and-supporting-characters.md) | 207, 208, 210, 211 | `prices`, `market`, `horses`, `weapons`, `armor`, `squire`, `supporting-characters`, `table-12-7` |
| [Ransom (Tables 12.1–12.5)](../../rules_corpus/core/12-wealth/ransom.md) | 201, 202, 203, 204 | `ransom`, `prisoner`, `tables`, `knight`, `noble`, `soldier`, `clergy`, `tribal`, `broker` |

### 8 — Weapons

| Topic | Pages | Tags |
|-------|-------|------|
| [Table 8.1 — Melee & Brawling Weapons](../../rules_corpus/core/08-weapons/melee-weapons.md) | 161, 162, 163, 164, 165 | `weapons`, `melee`, `table-8-1`, `sword`, `axe`, `mace`, `spear`, `lance`, `dagger`, `rebated`, `shield-breaking` |
| [Table 8.2 — Missile & Thrown Weapons](../../rules_corpus/core/08-weapons/missile-thrown-weapons.md) | 166, 167 | `weapons`, `missile`, `thrown`, `bow`, `crossbow`, `longbow`, `warbow`, `javelin`, `table-8-2`, `damage-cap` |
| [Weapon Skills, Parry Protection & Breakage](../../rules_corpus/core/08-weapons/weapon-skills.md) | 159, 160, 161 | `weapons`, `weapon-skills`, `charge`, `sword`, `spear`, `hafted`, `flail`, `brawling`, `bow`, `crossbow`, `thrown`, `parry`, `breakage`, `handedness` |

### 14 — The Winter Phase

| Topic | Pages | Tags |
|-------|-------|------|
| [Winter Phase — Economic Circumstances & Aging (Steps 4–5)](../../rules_corpus/core/14-winter-phase/economic-and-aging.md) | 227, 228, 229, 230 | `economic`, `standard-of-living`, `maintenance`, `aging`, `senescence`, `infirmity`, `decrepitude`, `death`, `tables-14-2-14-4` |
| [Winter Phase — Family & Childbirth (Step 11, Tables 14.8–14.12)](../../rules_corpus/core/14-winter-phase/family-childbirth.md) | 233, 234, 235 | `family`, `childbirth`, `conception`, `tragedy`, `child-survival`, `multiple-birth`, `blessed-birth`, `midwifery`, `tables-14-8-14-12` |
| [Winter Phase — Steps, Personal Events & Experience Rolls](../../rules_corpus/core/14-winter-phase/overview.md) | 221, 227, 230 | `winter-phase`, `procedure`, `personal-events`, `experience-rolls`, `checks`, `table-14-1` |
| [Winter Phase — Squires, Horses, Training, Glory & Prestige (Steps 6–10)](../../rules_corpus/core/14-winter-phase/stable-training-glory-prestige.md) | 230, 231, 232, 233 | `squire`, `maiden`, `horse-survival`, `training-practice`, `glory`, `prestige-reward`, `getting-fat`, `tables-14-5-14-7` |
