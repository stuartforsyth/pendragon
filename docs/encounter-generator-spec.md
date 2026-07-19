# Specification 1 — Encounter Generator (human encounters)

Status: **implemented** (v1). A new "Encounter" tab in the existing
Pendragon app for quickly building and running **human** combat encounters
scaled to the number of players. Beasts/creatures are a later specification.

---

## 1. Goals & scope

- Quickly generate groups of human enemies (bandits, thieves, highwaymen,
  spearmen, conrois of knights, Saxon raiders, etc.) scaled to party size.
- Run the fight with a lightweight tracker: current HP, who each enemy is
  engaged with, and dice rolls for skills and damage (with correct criticals).
- Keep a **readable combat log** for recap, plus a free-text **GM notes** box
  for the GM's own account of the fight.

### Non-goals (out of scope for this spec)
- Beasts and creatures (future spec).
- Initiative / turn order, movement, positioning. **(F1: HP + rolls only.)**
- Tracking player-characters (this tab is enemy-facing).
- Auto-applying damage to HP. **(F2: HP is adjusted manually.)**
- Persisting the live encounter between sessions. **(F5: session-only;** only
  the exported log persists.)

---

## 2. Decisions (from Q&A)

| # | Decision |
|---|----------|
| F1 | Tracker does **HP + rolls only** — no initiative/turn order. |
| F2 | Damage rolls **display only**; the GM applies a **typed HP delta** (`-10` = take 10 damage, `5` = heal 5) so damage is reflected accurately. |
| F3 | Default **1 enemy per player**, with easy **add/remove** of combatants. |
| F4 | Combat data lives in a **separate `data/combat.json`**. |
| F5 | Encounter is **session-only**; a **combat log** is kept and can be exported (clipboard/file). |
| F6 | Combatants are **randomised** (roll the template's APP die; light HP variance) so repeats aren't identical. |

---

## 3. Reuse of existing code (Rule 1 — do not recreate)

- **`rules.py` loader / `Rules`** — extend to also load `data/combat.json`
  (generalise `load_rules`, see §9.1). Do not fork a second loader.
- **Dice helpers** `_roll`, `_rhu`, `_clamp` in `rules.py` — reuse; add a
  `roll_expr("XdY+Z")` helper for APP/damage strings (see §9.4).
- **`Generator._fill_name`** — reuse to name notable enemies (e.g. a bandit
  leader) by culture.
- **Notebook + shared status bar** (already added) — the encounter tab slots in
  as a second `ttk.Notebook` page.
- **Roster export pattern** (`format_roster_markdown`, save-to-file dialog) —
  mirror it for the **combat log export**.
- **GM-notes widget + unsaved-notes prompt** (from the NPC tab) — reuse the same
  pattern for the encounter's GM Notes box (§7), rather than building a new one.
- **Derived-stat formulas** (HP=CON+SIZ, Knockdown=SIZ, Major Wound=CON,
  Unconscious=HP/4, Move) — reuse only when a stat is randomised; otherwise use
  the template's fixed values.

---

## 4. Combat rules to extract into `data/combat.json` (Rule 2)

Parsed from the Core Rulebook (Ch.2 & 7) and validated against the app's data.

### 4.1 Resolution (the d20 core)
- **Success:** `d20 ≤ skill`.
- **Critical:** `d20 == (modified) skill` (Blackjack — as high as possible
  without going over). If `skill ≥ 20`, a roll of 20 is a critical.
- **Fumble:** natural **20**, *unless* `skill ≥ 20` (then no fumble).
- **Opposed (melee):** both roll; higher **successful** roll wins and deals
  damage. **Tie** = equal successful rolls (or both crit) → both strike.
  **Partial success** = you succeed but roll lower than the winner → you gain
  your shield/parry protection.
- **Damage application:** winner's weapon damage − defender's Armour Points
  (+shield when applicable) → off Hit Points.

### 4.1a Wounds & unconsciousness (Core Ch.11, verified)
Two independent routes to unconsciousness:
1. **Current HP below the Unconscious value** (= Total HP / 4) — e.g. from
   several minor wounds. Falls unconscious.
2. **Major Wound** — a **single blow ≥ CON** (the Major Wound value). The
   character **immediately falls unconscious**, *even if HP is still above the
   Unconscious threshold*. (Also Debilitated + a Characteristic-loss roll — out
   of scope for the tracker.)

**Mortal Wound** — a single blow ≥ **Total HP** — is lethal (unconscious/dying).
**Knockdown** (total damage ≥ SIZ) knocks prone — noted, not modelled in v1.

Because HP is applied as a typed delta (F2), the tracker treats **each applied
damage delta** as one blow: a damage delta ≥ CON triggers a **Major Wound →
unconscious**; ≥ Total HP triggers a **Mortal Wound → dead**. Healing back above
the Unconscious value clears a Major-Wound KO.

### 4.2 Critical hits (Rule: "accurately account for criticals")
- A **critical hit** rolls the weapon's damage dice **plus the attacker's base
  Damage dice again** (worked example: `5D6` → `5D6+4D6`). Exact wording to be
  transcribed verbatim from Ch.7 "Winner's Outcome" at implementation.
- A **critical skill roll** with no damage (e.g. Awareness) simply reports
  "critical".

### 4.3 Tables to transcribe
- **Weapons** (Table 8.1): weapon → skill used, damage dice, hands, foot/mounted,
  reach. Enough to show each enemy's attacks and roll their damage.
- **Armour** (Table 9.x): armour type → points (Gambeson 4, Aketon, Hauberk,
  Haubergeon, Nasal/Open helm, etc.).
- **Shields** (Table 9.4): Round, Kite (~6), Targe (~4), etc.

> These numeric tables are **implementation transcription**, not design — the
> schema below defines where they live.

---

## 5. Enemy templates (Rule 3 — types & common stats)

Transcribed from the GM Handbook "Foes" bestiary (human foes). Each has the same
fields (see §6.2). Captured values so far:

| Template | Tier | HP | Armour(+shield) | Key attack (skill) | Damage | Glory |
|---|---|---|---|---|---|---|
| **Bandit** | rabble | 24 | 4 | Spear 8 / Bow 8 / Dagger 8 | 4D6 / 3D6 / 2D6+4 | 10 |
| **Bowman** | trained | 23 | 5 | Self Bow 15 | 3D6 | 25 |
| **Crossbowman** | trained | 22 | 5 | Light Crossbow 15 | 1D6+10 | 25 |
| **Spearman** | trained | 26 | 7+6 | Spear 15 / Sword 12 | 4D6 | 25 |
| **Veteran Spearman** | veteran | 29 | 10+6 | Spear 15 / Sword 12 | 5D6 | 50 |
| **Hill Man** | trained | 25 | 0+4 | Longbow 14 / Spear 12 | 4D6 | 25 |
| **Mounted Sergeant** | trained | 26 | 10+6 | Spear 15 / Sword 12 | 4D6 | 25 |
| **Saxon Ceorl** | rabble | 26 | 0+6 | Spear 10 / Seax 10 | 4D6 / 2D6+5 | 10 |
| **Rich Ceorl** | trained | 30 | 7+6 | Spear 12 / Axe 10 | 5D6 | 25 |
| **Heorthgeneat** | veteran | 31 | ~9+6 | Axe 16 / Spear 15 | 5D6 | 25 |
| **Saxon Knight** | elite | 27 | 9+6 | Sword 15 / Charge 12 | 5D6 | 25 |
| **Ætheling** (chieftain) | elite | 31 | — | Sword 20 / Axe 16 / Spear 16 | 5D6 | — |

Still to transcribe: **Foot Soldier**, **Berserk** (GM Handbook / Core). The
list is data-driven, so adding more later is "add a key."

### 5.2 Battle Cards (unit conrois)
The **Battle Cards** add 12 themed foe conrois — Knights of Gorre / Lothian /
Malahaut / Cornwall, Northern Prickers, Pictish Pikemen / Javeliniers /
Knifemen, Saxon Warriors, Irish Kerns, Cambrian Archers, Breton Mercenary
Knights. Each is both an **enemy template** and an **encounter theme** carrying
the card's own **per-player scaling** (e.g. javeliniers ×3, Saxons ×2, Lothian
×1.5), a **Morale** value (`morale_minimum` + `morale_loss`), a **Knight Value**,
and a **Ransom** table (1D6 → knight type → £). These extra fields are optional
on a template, so the base bestiary is unaffected.

### Skill tiers (user story: differentiate skill)
Templates already span a skill range; group them by a `tier` field:
**rabble** (skill ~8–10) → **trained** (~12–15) → **veteran** (~15) →
**elite/knight** (~15–20). Optionally an **encounter-wide veterancy modifier**
(±skill) for fine-tuning; **default off**.

### 5.1 Promotion to champion / elite (per-combatant)
Any combatant can be **promoted** to a tougher, more dangerous champion —
e.g. a Bandit → **Gang Leader**, a Knight → **Elite Commander**. This is a
per-combatant transform (not a new template), driven by a `promotion` block in
`combat.json` so the boost is tunable:

- **Combat skills** +`skill_bonus` (default **+5**).
- **Hit Points** ×`hp_multiplier` (default **×1.5**), with Knockdown/Major
  Wound/Unconscious recomputed from the new totals.
- **Weapon damage** +`damage_bonus_dice` (default **+1D6**).
- **Armour** +`armour_bonus` (default **+2**), reflecting better gear.
- **Glory** ×`glory_multiplier` (default **×3**).
- **Key Trait bump** (e.g. Valorous +3) for flavour.
- **Title:** from the template's `promotion_title` (Bandit → "Gang Leader",
  Knight → "Elite Commander"); fallback `title_default` = "Champion".

Promotion is **reversible** (demote restores the base stats — store the
original block). A promoted combatant is flagged `elite = true` and rendered
**visually prominent** (see §7), the opposite of the greyed-out downed rows.
Promotion is logged (§10).

---

## 6. Data model (new `encounter.py`)

### 6.1 Classes
- **`EnemyTemplate`** — loaded from `combat.json`; static stat block + tier.
- **`Combatant`** — one instance in the fight:
  - `type` (template name), `label` (e.g. "Bandit 2"), `engaged_with` (free text)
  - `characteristics` (SIZ/DEX/STR/CON/APP — APP rolled)
  - `attacks` (list: weapon, skill_name, skill_value, damage_expr)
  - `armour_points`, `shield_points`, `max_hp`, `cur_hp`
  - thresholds: `knockdown`, `major_wound`, `unconscious`
  - `status` (computed): `active` → `unconscious` (cur_hp < unconscious) →
    `dead` (cur_hp ≤ 0). A manual "slain/unconscious" override is allowed.
  - `elite` (bool) + `base_stats` snapshot for reversible promotion (§5.1).
- **`Encounter`** — `list[Combatant]`; `add(template, n)`, `remove(idx)`,
  `scale_to_players(n)`.
- **`CombatLog`** — ordered list of readable event lines + a `gm_notes` string
  (the free-text GM box); `to_markdown()` renders both (events, then a
  `## GM Notes` section) so a saved log contains the GM's account too.

### 6.2 `combat.json` schema (sketch)
```jsonc
{
  "resolution": { "critical": "roll == skill", "fumble": 20, "...": "notes" },
  "critical_hit": { "bonus": "add base Damage dice again" },
  "promotion": {
    "title_default": "Champion",
    "skill_bonus": 5, "hp_multiplier": 1.5, "damage_bonus_dice": 1,
    "armour_bonus": 2, "glory_multiplier": 3, "trait_bonus": { "Valorous": 3 }
  },
  "weapons":  { "Spear": { "skill": "Spear", "damage": "…", "reach": true } },
  "armour":   { "Gambeson": 4, "Hauberk": 10, "…": 0 },
  "shields":  { "Kite": 6, "Round": 6, "Targe": 4 },
  "tiers":    { "rabble": {}, "trained": {}, "veteran": {}, "elite": {} },
  "enemy_templates": {
    "Bandit": {
      "description": "Curs and dogs, the lot of them",
      "tier": "rabble",
      "characteristics": { "SIZ":12,"DEX":10,"STR":12,"CON":12,"APP":"1D6+5" },
      "attacks": [
        { "weapon":"Spear","skill":"Spear","value":8,"damage":"4D6" },
        { "weapon":"Self Bow","skill":"Bow","value":8,"damage":"3D6" },
        { "weapon":"Dagger","skill":"Brawling","value":8,"damage":"2D6+4" }
      ],
      "health": { "hit_points":24,"knockdown":12,"major_wound":12,"unconscious":6 },
      "other":  { "movement":16,"armor_points":4,"shield":0,"glory":10,"healing_rate":2 },
      "promotion_title": "Gang Leader"
    }
  },
  "encounter_themes": {
    "Bandit ambush": { "core": ["Bandit"], "leader": "Bandit", "per_player": 1.0 },
    "Conroi of knights": { "core": ["Knight"], "per_player": 1.0 },
    "Highwaymen": { "core": ["Bowman","Spearman"], "per_player": 1.0 },
    "Saxon raiders": { "core": ["Saxon Ceorl"], "leader": "Heorthgeneat", "per_player": 1.0 }
  }
}
```

---

## 7. UI — the Encounter tab

**Setup row:** number of players (spinbox) · encounter theme (dropdown) ·
difficulty/veterancy (optional) · **Generate encounter** · **Add enemy**
(type dropdown + button) · **Clear**. **Clear** starts a new session: it
**prompts to save** if the log/notes are unsaved (Yes = save / No = discard /
Cancel), then clears combatants, the **combat log**, and the **GM notes**.

**Combatant tracker** (a scrollable list; one row per combatant):
- `Label` (editable, e.g. "Bandit 2") · **Engaged with** (editable text field).
- **HP `cur / max`** with a **delta box + Apply** — type `-10` to take 10
  damage or `5` to heal 5 (Enter or Apply). The applied damage is the single
  blow for the Major/Mortal Wound checks (§4.1a). A **KO/Revive** toggle knocks
  a combatant out or brings them back independent of HP.
- Compact stats: main attack(s) `skill` + `damage`, Armour(+shield),
  Major Wound, Knockdown.
- **Roll Skill** (per weapon) and **Roll Damage** (per weapon) buttons; result
  shown inline and appended to the log.
- **Stat detail lines** under each row: characteristics, each attack (skill +
  damage), skills, Major Wound, Morale; plus a line with the **armour worn**
  (e.g. "Hauberk, aketon, open helm + kite shield") and a rolled **defining
  physical feature** + eye colour — so the GM can describe how each combatant is
  armed and what they look like. The armour and look are also in the saved
  combatants summary.
- The **"engaged with"** name is **logged when set** and listed in the saved
  log's combatants summary (see §10), so the pairing is recorded.
- **Actions menu** per row → **Promote/Demote** (champion/elite, §5.1),
  **Knock out/Revive**, and for battle-card foes **Roll ransom** (1D6 on the
  card's table) and **Morale check** (d20 vs Morale — holds or flees). Promoted
  rows are **visually prominent** (bold + a ★ and title).
- **Status styling:** `unconscious` and `dead` rows are **greyed out and
  struck-through**, visually distinct from active combatants. A quick
  "down/slay" toggle is available. (Downed elites still grey out.)

**Combat log panel:** read-only text of auto-generated events; **Copy log** and
**Save log…** (reuse the roster export pattern).

**GM Notes box:** an editable free-text field for the GM's **overarching**
account (reuses the NPC tab's GM-notes widget). Written into the log file when
the log is saved (§10). Prompted before an action that would discard unsaved
notes.

**Round note (transient):** a single-line note box + **"Add to log"** button.
Typing a note and clicking the button **writes it into the log at that point
and clears the box** — for capturing a specific round/moment inline in the
event stream. (GM Notes = overarching; round note = inline, chronological.)

---

## 8. Rolling behaviour

- **Roll Skill(weapon):** `d20` vs `skill_value` → success / **critical**
  (== value) / failure / **fumble** (nat 20, unless value ≥ 20). Report outcome;
  log it.
- **Roll Damage(weapon):** roll the weapon's damage dice. A **"critical" toggle**
  (or the last skill roll being a crit) adds the crit bonus dice (§4.2). Show
  the total and its breakdown; log it. **No auto-subtraction** (F2).
- Reuse the dice helpers; add `roll_expr`.

---

## 9. Randomisation (F6)
- Roll each combatant's **APP** from its template die (`1D6+5`, `2D6+3`, …).
- Apply **light HP variance** (default: re-derive from CON+SIZ with a small
  ±jitter, or ±1D3) so repeated enemies differ; keep it modest to stay balanced.
- Auto-number duplicate labels ("Bandit 1", "Bandit 2", …).

---

## 10. Combat log (F5)
Session-only encounter, but a persistent readable log. Log entries include:
- Encounter generated (theme, party size, roster of combatants).
- "Bandit 2 engaged with Sir Kay" (from the engaged-with field).
- Skill rolls: "Bandit 2 (Sir Kay) rolls Spear (8): 5 — success" — combat-action
  lines name the engaged combatant (`(Sir Kay)`) for readability.
- Damage rolls: "Bandit 2 Spear damage 4D6 = 14 (critical: +4D6)".
- HP/status changes: "Bandit 2: 24 → 6 (unconscious)", "Sir Kay's foe slain".
- Promotions: "Bandit 2 promoted to Gang Leader (elite)".
- **Engaged-with:** logged when set ("Bandit 2 engaged with Sir Kay"), and a
  **`## Combatants` summary** in the saved log lists each combatant with HP,
  status, and who they're engaged with.
- **Round notes:** transient notes added via the "Add to log" button appear
  inline in the event stream at the moment they're added.
- **GM notes:** the overarching GM Notes box (§7). **When the log is saved to
  file, these are written into it** as a `## GM Notes` section, so the recap has
  the event log, the combatants, and the GM's narrative account.
- Export: **Copy log** / **Save log…** to Markdown (mirrors roster export).

---

## 11. Refactors / contradictions to address (called out per instruction)
1. **Single-file loader.** `load_rules` currently loads only `data/rules.json`.
   Generalise it to also load `data/combat.json` into the same `Rules` object
   (or a sibling), backward-compatible (combat features optional if absent).
2. **NPC "social class" vs enemy "template".** Both name a "Knight" but are
   different concepts (NPC classes roll characteristics; enemy templates are
   fixed bestiary blocks). Keep separate; a future "promote NPC → combatant"
   bridge is possible but out of scope.
3. **Fixed vs derived stats.** Enemies use template HP/thresholds as-is for
   authenticity; only recompute when a stat is randomised.
4. **APP/damage as dice strings.** New `roll_expr` handles `"2D6+3"` etc.;
   reused for APP and weapon damage.
5. **"Leader" unified with promotion.** The earlier idea of a theme "leader"
   template is replaced by generating the leader as an **auto-promoted**
   combatant of the leader type (§5.1) — one mechanism, not two.

---

## 12. Acceptance criteria (maps to user stories)
- [ ] Generate a group of human enemies scaled to N players from a theme.
- [ ] Add/remove combatants mid-encounter in one click.
- [ ] Enemy skill levels differ by template tier (bandit ≪ knight).
- [ ] Each combatant shows cur/max HP; GM can adjust HP up/down manually.
- [ ] Each combatant has an editable "engaged with" field.
- [ ] Roll a combatant's weapon skill (d20) with correct success/critical/fumble.
- [ ] Roll a combatant's weapon damage, correctly adding critical bonus dice.
- [ ] Any combatant can be promoted to a champion/elite (Gang Leader, Elite
      Commander…): HP, skills, damage, armour and Glory all increase, and it is
      visually prominent and reversible.
- [ ] Downed (unconscious/dead) combatants are greyed out and struck-through.
- [ ] A readable combat log records combatants, engagements, rolls, and damage,
      and can be copied/saved.
- [ ] A GM Notes box lets the GM capture key moments, wounds, and events during
      the encounter; those notes are written into the log file when it is saved.
- [ ] The "engaged with" name is logged and appears in the saved log's
      combatants summary.
- [ ] A single blow ≥ CON (Major Wound) drops a combatant unconscious even above
      the HP/4 threshold; ≥ total HP is a Mortal Wound (dead).
- [ ] Each combatant row shows basic characteristics, attacks, and skills.
- [ ] A transient round-note box writes the note into the log inline and clears.
- [ ] Combat-action log lines name the engaged combatant, e.g. "Bandit 1 (Jason)".
- [ ] Clear prompts to save unsaved log/notes, then clears combatants, the log,
      and the GM notes to start a new session.

---

## 13. Future (later specs)
- Beasts & creatures (Specification 2).
- Optional: save/reload live encounters; initiative; auto-apply damage;
  promote a generated NPC into a combatant.
