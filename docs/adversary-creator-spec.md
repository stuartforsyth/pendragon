# Specification — Adversary Creator (new tab)

Status: **DRAFT — awaiting sign-off. No code until approved.**

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

## 4. Persistence — a writable user library (NEW infrastructure)

`combat.json` is currently **read-only** at runtime. Editing/adding
adversaries needs a writer. **Proposed:** keep the shipped baseline immutable
and store user content in a separate file:

- `data/combat.json` — shipped baseline (never written by the app).
- `data/library.user.json` — user adversaries **and** encounters (see the
  Encounter Creator spec), same schema, **layered over** the baseline at load:
  a user key with the same name **overrides** the built-in; new keys **add**.
- Writer mirrors the roster save (`json.dump(..., indent=2, ensure_ascii=False)`)
  with a `schema_version` for migration.
- **Reset/Revert to built-in** is possible because the baseline is untouched.

Rationale: app updates that ship new `combat.json` never clobber user work;
user content is portable and diff-friendly; a single library file keeps
adversaries and their encounters together.

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

## 9. Acceptance criteria (draft)
- [ ] Search/filter the adversary library and open any entry.
- [ ] Create a new generic adversary from scratch; save to the user library.
- [ ] Create a named adversary; it is distinguished from generics in the list.
- [ ] Every characteristic/skill/derived value can be typed **or** auto-rolled.
- [ ] Weapons chosen from the table populate attacks (skill + damage).
- [ ] Armour chosen from pieces + shield auto-totals armour/shield points and
      generates the armour description.
- [ ] Traits and passions can be typed or auto-rolled (religion-aware).
- [ ] "Create Adversary" on the NPC tab writes the current NPC as a named
      adversary, reusing its stats/skills/traits/passions.
- [ ] User adversaries persist across restarts, separate from `combat.json`,
      and appear in the Encounter tab / Encounter Creator adversary pickers.
- [ ] Characteristics are spelled out; rollable values are click-to-roll.
- [ ] The schema carries a `category` and the editor shows human weapon/armour
      fields, with hooks for beast/fae/monster later.

---

## 10. Suggestions to the design (for discussion)

1. **Data prerequisite — enrich the weapons & armour tables first.** The
   weapons table currently stores only `skill` + flags (no damage, hands,
   reach); `armour_pieces` has just Gambeson. To let users *select* a weapon
   and get its damage, or *select* armour pieces and get points, we should
   transcribe **Table 8.1 (weapon damage)** and **Table 9.x (armour points)**
   into `combat.json`. Recommend doing this small data task **before** the
   editor, otherwise users must hand-type damage/points.
2. **One writable user library** (`data/library.user.json`) layered over the
   baseline (§4) — protects user work across updates and is shareable.
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

## 11. Open questions for sign-off
1. **Persistence:** one `library.user.json` layered over `combat.json` (§4), or
   write directly into `combat.json`, or per-file exports only?
2. **Terminology/migration:** adopt the unified `adversaries` map (with
   back-compat aliases), or keep `enemy_templates` and add a parallel map?
3. **Weapon/armour data:** enrich the tables first (§10.1), or ship the editor
   with free-text damage/points for now and enrich later?
4. **Build order:** Adversary Creator before Encounter Creator? (recommended.)
5. **Create Adversary default:** always **named** from an NPC (recommended), or
   prompt named/generic each time?
6. **Editor layout:** collapsible sections (recommended for a tall form) vs
   sub-tabs within the editor pane?
