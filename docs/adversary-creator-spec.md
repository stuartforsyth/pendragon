# Specification — Adversary Creator (new tab)

Status: **v1 IMPLEMENTED** (`adversary.py` `AdversaryTab` + NPC "Create
Adversary" bridge). Groundwork steps 1–3 done (persistence, enriched tables,
unified schema). v1 simplifications noted in §12.

**Locked decisions:**
- **Persistence (§4):** ship `data/examplecombat.json` (tracked); copy to a
  git-ignored `data/combat.json` on first edit; app reads/writes that one file.
- **Data model (§3):** unify — `enemy_templates → adversaries` (with `kind`
  generic/named + `category`) and `encounter_themes → encounters`, with
  load-time aliases so the existing Encounter tab is unaffected.
- **Weapon/armour data:** enrich the weapon (damage) and armour (points) tables
  in the baseline **first**, so pickers auto-fill (§10.1).
- **Build order:** Adversary Creator **before** Encounter Creator; the
  weapon/armour enrichment is part of its groundwork.

A new tab to **search for, edit, and add adversaries** — the reusable stat
blocks that encounters are built from. Human adversaries exist today; the
design must extend cleanly to **beasts, fae, and monsters** later. The
Adversary Creator **inherits from the NPC Generator** for characteristics,
skills, traits and passions, and the NPC Generator gains a **Create
Adversary** button that saves the current NPC as a named adversary.

> Companion spec: `docs/encounter-creator-spec.md` (encounters compose
> adversaries). Build the Adversary Creator **first** — see §11.

---

## 1. Goals & scope

- **Search** the adversary library (built-in + user-created), with filters.
- **Edit** any adversary; **add** new ones from scratch or from an NPC.
- **Enter or auto-generate** every field (characteristics, derived stats,
  skills, traits, passions) — reusing the NPC Generator wherever possible.
- **Select weapons and armour** for human adversaries (drives attacks, damage,
  and armour points) rather than typing raw dice/points.
- Differentiate **generic** adversaries (e.g. "Knight") from **named** ones
  (e.g. "Sir Gawain the Valiant").
- Persist user adversaries durably and separately from the shipped data.
- A schema that **future-proofs** beasts/fae/monsters.

### Non-goals (this spec)
- Running a fight (that stays in the Encounter tab tracker).
- Full bestiary content for beasts/fae/monsters — only the **schema hooks**
  and editor extensibility for them (content is a later spec).
- Encounter composition (that is the Encounter Creator spec).

---

## 2. Reuse of existing code (Rule 1 — do not recreate)

| Reuse | For |
|---|---|
| `Generator.generate()` / `_fill_characteristics` / `_fill_class` / `roll_appearance` | Auto-rolling characteristics, derived stats, skills, appearance |
| `Rules.roll_traits` / `roll_passions` / `roll_directed_trait` | Auto traits/passions (religion-aware for named) |
| `Rules` derived formulas (HP=CON+SIZ, Knockdown=SIZ, Major Wound=CON, Unconscious=HP/4, Move, Damage) | Recomputing derived stats when characteristics change |
| `rules.roll_expr` | Dice fields (APP, damage) |
| `encounter.resolve_skill` / `roll_damage` | The **Auto/roll** buttons and click-to-roll |
| `encounter.CHAR_FULL` | Spelled-out characteristic labels (see naming spec) |
| `data/combat.json` weapons / shields / armour / tiers | Weapon & armour pickers |
| Roster JSON save/load pattern (`json.dump`/`asksaveasfilename`) | The user-library writer |
| GM-notes / status-bar helpers | Feedback & logging |

**Conventions this tab must follow:**
- `docs/characteristic-naming-spec.md` — characteristics spelled out, no acronyms.
- `docs/click-to-roll-spec.md` — any displayed characteristic/skill/damage/
  passion/trait renders as a click-to-roll link.

---

## 3. Adversary data model (unified `adversaries` map)

Today `combat.json` has `enemy_templates` keyed by type name. This spec
generalises them into an **`adversaries`** collection so generic and named
foes, of any category, live in one place:

```jsonc
"adversaries": {
  "Bandit": {
    "kind": "generic",              // generic | named
    "category": "human",            // human | beast | fae | monster (future)
    "source": "builtin",            // builtin | user | generated
    "tier": "rabble",
    "description": "Curs and dogs, the lot of them",
    "characteristics": { "SIZ":12,"DEX":10,"STR":12,"CON":12,"APP":"1D6+5" },
    "attacks":  [ { "weapon":"Spear","skill":"Spear","value":8,"damage":"4D6" } ],
    "armour":   { "pieces":["Gambeson"], "shield":null },   // NEW: structured
    "health":   { "hit_points":24,"knockdown":12,"major_wound":12,"unconscious":6 },
    "other":    { "movement":16,"armor_points":4,"shield":0,"glory":10,"healing_rate":2 },
    "skills":   { "Awareness":18,"Hunting":16 },
    "traits":   { "Valorous":8 },
    "passions": { "Hate (Knights)":12 },
    "promotion_title": "Gang Leader"
    // optional unit fields: morale_minimum, morale_loss, knight_value, ransom
  },

  "Sir Gawain the Valiant": {
    "kind": "named",
    "category": "human",
    "source": "user",
    "base_type": "Average Knight",   // inherit a generic block, then override
    "name": "Sir Gawain the Valiant",
    "culture": "Cymric", "religion": "British Christian",
    "created_from_npc": true,
    "glory": 4200,
    // any overridden characteristics/attacks/armour/skills/traits/passions here
  }
}
```

- **`kind`** — `generic` (a type: "Knight", "Bandit") vs `named` (an
  individual: "Sir Gawain"). Named adversaries carry a `name` and usually a
  `base_type` they inherit from; generics are keyed by their type name.
- **`category`** — drives which editor fields appear (§7.5). Humans use
  weapons + armour pieces; future categories add their own field manifest.
- **`armour`** becomes **structured** (`pieces` + `shield`) so the editor can
  auto-total `armor_points`/`shield` from the tables; the free-text
  `armour_desc` is derived from it (still editable).
- **Provenance** (`source`, `created_from_npc`) so the UI can badge built-in
  vs user content and protect the former.

### Backward compatibility
The loader treats existing `enemy_templates` as `adversaries` with
`kind:"generic"`, `category:"human"` (aliased on load), and the current
`armor_points`/`shield`/`armour_desc` remain valid. **Nothing in the existing
Encounter tab breaks.** New writes use the unified map.

---

## 4. Persistence — example baseline + a single working file (AGREED)

One source of truth at runtime, protected from `git pull`:

- **`data/examplecombat.json`** — tracked, shipped defaults (adversaries,
  encounters, weapons, armour, …). Read-only; future updates arrive via
  `git pull`; works on a fresh clone.
- **`data/combat.json`** — the **live working file**; **git-ignored**. Created
  by **copying** `examplecombat.json` on the **first edit**. From then on the
  app reads **and** writes only this file.
- **Load order:** if `data/combat.json` exists, use it; otherwise fall back to
  `data/examplecombat.json`.
- Because `combat.json` is git-ignored, `git pull` can deliver a new
  `examplecombat.json` **without touching** the user's working file.

This gives a **single file to edit** — built-ins and user content are the same
document, so anything that came from the baseline can be freely changed — while
keeping user work safe across updates.

**Accepted trade-off:** once `combat.json` exists, new built-in content from a
later `examplecombat.json` is **not** auto-merged (the working file is
authoritative). Optional future helpers: **Reset to example** (discard the
working file, fall back to the baseline) and **Import new examples** (copy in
only the baseline keys the working file lacks).

**Migration (at implementation time, not now):** `git mv data/combat.json
data/examplecombat.json`; add `data/combat.json` to `.gitignore`; update
`rules.load_rules` to prefer the working file and fall back to the example.
Safe to do because the app has never written `combat.json` — it is still the
pristine baseline. The writer mirrors the roster save
(`json.dump(..., indent=2, ensure_ascii=False)`) and stamps `schema_version`.

---

## 5. Generic vs named — the rule

- **Generic** = a reusable type; encounters spawn N of them ("4× Bandit").
  Keyed by type name; no personal identity.
- **Named** = a specific individual; encounters usually include exactly one
  ("Sir Gawain leads them"). Has `name`, optional `base_type`, and typically
  culture/religion/glory. A named adversary may be **promoted** in an
  encounter just like a generic.
- The library list badges each (`▸ generic` / `★ named`) and can filter by kind.
- **Create Adversary** on the NPC tab always produces a **named** adversary
  (an individual NPC); the user may later "Save as generic type" to strip the
  identity into a reusable template.

---

## 6. NPC → Adversary bridge

### 6.1 "Create Adversary" button (NPC Generator tab)
Placed with the other result actions (near Copy Statblock). Enabled once an
NPC is generated. On click it opens the Adversary Creator **prefilled** as a
**named, human** adversary built from `_current`:

| NPC result field | Adversary field |
|---|---|
| `full` | `name` |
| `culture`, `religion`, `social_class` | identity + `tier` hint |
| `stats` (SIZ…APP) | `characteristics` |
| `derived` Hit Points / Major Wound / Knockdown / Unconscious | `health.*` |
| `derived` Move / Healing Rate | `other.movement` / `other.healing_rate` |
| `derived` Damage (`Xd6`) | base damage for generated attacks |
| `skills` (Sword, Spear, Horsemanship…) | `skills`; combat skills seed **attacks** |
| `traits`, `passions` | `traits`, `passions` |
| `glory` | `glory` |
| `appearance` (descriptor, features, eyes) | `description` flavour |

**What the NPC lacks and the user must set:** the actual **weapon & armour
selection** (an NPC has attire/appearance but no chosen weapons or armour
points). The bridge pre-selects sensible defaults from the NPC's combat skills
(e.g. a Sword skill → a Sword attack) and leaves armour for the user to pick,
then the Adversary Creator opens on the **Weapons/Armour** section so the user
completes it.

### 6.2 Reuse, don't fork
The bridge is a pure mapping over the existing `generate()` result — the
Adversary Creator does not re-implement characteristic/skill/trait rolling; it
calls the same `Rules`/`Generator` methods for its **Auto** buttons.

---

## 7. UI — the Adversary Creator tab

Two-pane layout: **library (left)** · **editor (right)**.

### 7.1 Library pane (search & select)
- **Search box** with incremental filter (matches name, type, description).
- **Filter chips / dropdowns:** kind (generic/named), category (human/beast/
  fae/monster), tier, culture, source (built-in/user).
- **List** of adversaries with a one-line summary (tier · HP · key attack ·
  ★named/▸generic · source badge).
- Buttons: **New generic**, **New named**, **New from NPC…**, **Duplicate**,
  **Delete** (user entries only; built-ins are "Duplicate to edit").

### 7.2 Editor pane — sections (collapsible or sub-tabs)
1. **Identity** — kind, name (named) / type name (generic), category, tier,
   description, culture & religion (named), promotion title.
2. **Characteristics** — Size/Dexterity/Strength/Constitution/Appeal, each an
   editable number with a per-field **Auto** (roll) and a click-to-roll link;
   an **Auto all** rolls the set via the NPC generator's method.
3. **Derived** — Hit Points, Move, Damage, Healing Rate, Major Wound,
   Knockdown, Unconscious. **Auto-computed** from characteristics (with a
   **Recompute** button); editable to override. Damage is click-to-roll.
4. **Weapons / Attacks** — a table of attacks: **Add weapon** picks from the
   weapons table; skill and damage default from the weapon (once the table is
   enriched, §10) and from the adversary's derived Damage; per-row skill value,
   damage, and reach/ranged/mounted flags. Remove/reorder. Skill values are
   click-to-roll; damage is click-to-roll.
5. **Armour** — multi-select **armour pieces** + a **shield** dropdown →
   auto-sums `armor_points` and `shield`; the `armour_desc` text is generated
   ("Hauberk, aketon, nasal helm + kite shield") and editable.
6. **Skills** — editable list; add from a known-skills vocabulary; **Auto**
   seeds defaults for the tier/class. Click-to-roll.
7. **Traits & Passions** — editable; **Auto** rolls via `roll_traits`/
   `roll_passions` (religion-aware for named). Click-to-roll.
8. **Unit/loot (optional)** — glory, morale (`morale_minimum`, `morale_loss`,
   `knight_value`), ransom table — shown for unit/battle-card foes.
9. **Save / Revert**, with validation (§8).

### 7.5 Category extensibility (beasts/fae/monsters)
The editor renders fields from a small **per-category manifest** so new
categories slot in without rewriting the tab:
- **human** — weapons + armour pieces + shield (as above).
- **beast/monster (future)** — natural attacks (claw/bite), natural armour
  value, **Size categories** beyond human range, special abilities/notes,
  no shield.
- **fae (future)** — as beast plus glamour/vulnerability notes.
Unknown categories fall back to the raw stat fields, so data is never lost.

---

## 8. Validation
- A **generic** needs a unique type name; a **named** needs a name (+ a
  `base_type` or a complete stat block).
- Warn on: no attacks, an attack with no damage, characteristics out of a sane
  range, armour pieces not in the table.
- Saving over a built-in is blocked → offer **Duplicate as user copy**.

---

## 9. Acceptance criteria
- [x] Search/filter the adversary library and open any entry.
- [x] Create a new generic adversary from scratch; save to the working library.
- [x] Create a named adversary; it is distinguished from generics in the list
      (★ named / ▸ generic).
- [x] Characteristics can be typed **or** rolled; derived stats recompute live.
- [x] Weapons chosen from the table populate attacks (skill + auto damage).
- [x] Armour chosen from pieces + helmet + shield auto-totals armour/shield
      points and generates the armour description.
- [x] Traits and passions can be typed or auto-generated (from a rolled NPC).
- [x] "Create Adversary" on the NPC tab drafts the current NPC as a named
      adversary, reusing its stats/skills/traits/passions/attacks.
- [x] Saved adversaries persist to the working `combat.json` and instantiate
      correctly in the Encounter tab.
- [x] The schema carries `kind` + `category`; the editor shows human weapon/
      armour fields, with category hooks for beast/fae/monster later.
- [ ] *(v1 gap, §12)* In-editor per-field **click-to-roll** and spelled-out
      display for skills; the editor uses editable fields + roll buttons for now.

## 12. v1 simplifications (revisit)
- Skills/traits/passions are edited as plain "Name value" text lines (parsed on
  save), not click-to-roll rows. Characteristics use editable entries with a
  "Roll characteristics" button rather than per-field click-to-roll.
- Auto-generation seeds from a full NPC roll; there is not yet per-field Auto
  for skills alone.
- Built-in adversaries are editable in place (the working file supersedes the
  baseline, matching the single-working-file decision), rather than being
  locked with a "duplicate to edit" gate.
- Unit/loot fields (glory/morale/ransom) are carried through if present but not
  yet surfaced as dedicated editor controls.

---

## 10. Suggestions to the design (for discussion)

1. **Data prerequisite — enrich the weapons & armour tables first.** The
   weapons table currently stores only `skill` + flags (no damage, hands,
   reach); `armour_pieces` has just Gambeson. To let users *select* a weapon
   and get its damage, or *select* armour pieces and get points, we should
   transcribe **Table 8.1 (weapon damage)** and **Table 9.x (armour points)**
   into `combat.json`. Recommend doing this small data task **before** the
   editor, otherwise users must hand-type damage/points.
2. **Persistence (agreed, §4):** ship `data/examplecombat.json` (tracked) and
   copy it to a git-ignored `data/combat.json` on first edit — one working file,
   safe across `git pull`.
3. **Unify terminology** (`enemy_templates` → `adversaries`, `kind`/`category`)
   with load-time aliases so the current Encounter tab is unaffected.
4. **Category manifest** now (even if only "human" is populated) so beasts/fae/
   monsters are additive later, not a refactor.
5. **Named ⇄ generic conversions**: "Save named as generic type" and
   "Instantiate generic as named" to move between the two cheaply.
6. **Per-adversary import/export** as JSON for sharing single stat blocks.
7. **Balance hint**: show a rough threat score (glory / tier / attack output)
   so designers gauge difficulty while editing.
8. **Reuse the NPC roster ⇄ adversary link both ways** later: optionally
   "promote a roster NPC to an adversary" in bulk.

---

## 11. Sign-off status
1. **Persistence — DECIDED (§4):** `examplecombat.json` (tracked) copied to a
   git-ignored `combat.json` on first edit; single working file.
2. **Terminology/migration — DECIDED:** unify into `adversaries` / `encounters`
   with back-compat aliases (§3).
3. **Weapon/armour data — DECIDED:** enrich the tables first (§10.1).
4. **Build order — DECIDED:** Adversary Creator before Encounter Creator.

Minor UI defaults (assumed unless you say otherwise, not blocking):
5. **Create Adversary** from an NPC always produces a **named** adversary (with
   a later "save as generic type" option).
6. Editor uses **collapsible sections** (§7.2) for the tall form.
