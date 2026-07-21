# Specification — Encounter Creator (new tab)

Status: **v1 IMPLEMENTED** (`encounter_creator.py` `EncounterCreatorTab` +
`encounter.generate_from_definition` / `resolve_roster` + Send-to-tracker).

**Locked decisions (shared with the Adversary Creator spec):** unify the data
model (`encounter_themes → encounters`, back-compat adapter); persistence via
`examplecombat.json` → git-ignored `combat.json`; this tab is built **after**
the Adversary Creator (it composes adversaries).

A new tab to **create, edit, and manage encounter definitions** — the reusable
recipes the Encounter tab turns into a live fight. Today these recipes are the
`encounter_themes` in `combat.json` (`{core, leader, per_player}`); this tab
gives them a proper editor and a richer schema. Encounters are built from
**adversaries** (human today; beasts/fae/monsters later).

> Companion spec: `docs/adversary-creator-spec.md`. Encounters **compose**
> adversaries, so build the Adversary Creator first (shared library +
> persistence come from there).

---

## 1. Terminology (important)
- **Encounter definition** (this tab) — a reusable, saved recipe: which
  adversaries, how many, how it scales to the party, plus flavour. Supersedes
  today's `encounter_themes`.
- **Live encounter** (existing Encounter tab) — an *instance* generated from a
  definition and then run (HP tracking, rolls, log). Unchanged.

This tab edits **definitions**; the Encounter tab runs **instances**. A
"**Send to tracker**" action bridges the two.

---

## 2. Goals & scope
- **Search & select** existing encounter definitions (built-in + user).
- **Modify** an existing definition (roster, counts, scaling, leader, notes).
- **Add** new definitions from known adversaries.
- **Preview** what a definition produces for N players before saving.
- Persist user definitions durably (shared `library.user.json`, §7).
- Extend to non-human adversaries automatically (it just references the
  adversary library, which gains categories).

### Non-goals
- Running the fight (Encounter tab).
- Authoring the adversaries themselves (Adversary Creator).

---

## 3. Reuse of existing code (Rule 1)
| Reuse | For |
|---|---|
| `Encounter.generate_from_theme` scaling math (`per_player`, `core`, `leader`, `promote`) | The live **Preview** and "Send to tracker" |
| `data/combat.json` `encounter_themes` | Seed/back-compat for definitions |
| Adversary library (Adversary Creator spec) | The roster's adversary picker |
| Roster JSON save/load pattern | The user-library writer (shared, §7) |
| `EncounterTab` | Target of "Send to tracker" (generate + switch tab) |
| Search/list + status-bar patterns | UI |

Conventions: same as the other tabs (characteristic naming + click-to-roll
where any rollable value is shown).

---

## 4. Encounter definition schema (supersedes `encounter_themes`)

```jsonc
"encounters": {
  "Bandit ambush": {
    "source": "builtin",           // builtin | user
    "name": "Bandit ambush",
    "description": "Cutthroats spring from the treeline.",
    "tags": ["human", "wilderness", "low"],
    "roster": [
      { "adversary": "Bodyguards", "count": 1.5, "per_player": true,  "promote": false },
      { "adversary": "King Lot",   "count": 1,   "per_player": false, "promote": true  }
    ],
    "leader": { "adversary": "Bandit", "promote": true },     // optional
    "notes": "Terrain: dense woods (−5 to Bow)."
  }
}
```

- **`roster`** — the list of adversary lines. **Scaling is per line**: with
  `per_player: true` the line's `count` is a multiplier of the party size
  (fractions allowed, e.g. `1.5` × players); with `per_player: false` the
  `count` is a fixed integer (e.g. `1` King Lot). There is **no** global
  `scaling` block — each line scales itself.
- **`leader`** — optional single adversary, auto-promoted (mirrors today's
  theme leader = one auto-promoted combatant).
- **`tags`** — free classification (category, terrain, difficulty band) for
  search/filter.
- Morale/ransom/knight-value come from the **adversaries** themselves, not the
  encounter (no duplication).

### Backward compatibility
Older definitions are migrated on load (`to_editable`): a legacy global
`scaling` block is folded into each line's own multiplier, and a legacy random
pool (`{core, leader, per_player}`, today's `encounter_themes`) becomes explicit
per-player roster lines. `resolve_roster` still understands the legacy
`count: "per_player"` + `scaling` form, so nothing needs rewriting on disk.

---

## 5. UI — the Encounter Creator tab

Two-pane layout: **library (left)** · **editor (right)**.

### 5.1 Library pane (search & select)
- **Search box** (incremental filter on name, description, tag, or contained
  adversary — "show every encounter that uses Saxon Ceorl").
- **Filter chips:** category/tag, difficulty band, source (built-in/user).
- **List** with a one-line summary (roster size · scaling · source badge).
- Buttons: **New**, **Duplicate**, **Delete** (user entries; built-ins →
  "Duplicate to edit").

### 5.2 Editor pane
- **Name · description · tags.**
- **Scaling** — per-player multiplier (spinbox) or fixed counts (toggle).
- **Roster builder** — a table, one row per adversary line:
  - **Adversary** — searchable dropdown from the adversary library (shows
    tier/HP/key attack to aid balance).
  - **Count** — integer, or **×players** toggle.
  - **Promote?** — mark this line as a champion/leader.
  - **Notes** — per-line note.
  - Add row · remove row · reorder.
- **Leader** — optional single adversary (auto-promoted), or "first promoted
  roster line acts as leader".
- **Live Preview** — "For **N** players this generates: 4× Bandit, 1× Gang
  Leader (promoted)", computed with the **same** scaling logic the tracker
  uses, plus a rough **threat estimate** vs party size.
- **Save / Revert.**

### 5.3 Bridge to the live tracker
- **Send to tracker** — generates a live encounter from this definition (for
  the players spinbox value) and switches to the Encounter tab. This is the
  one-click "run it now" path and keeps the two tabs in sync (the Encounter
  tab's theme dropdown reads the same `encounters` map).

---

## 6. Difficulty / balance aid (suggested)
Show an at-a-glance estimate while editing: total adversary count for N
players, aggregate threat (sum of tiers / glory / attack output), and a
simple band (Easy / Standard / Hard / Deadly) relative to party size. Purely
advisory — Pendragon is deadly by design — but it helps a GM tune a fight.

---

## 7. Persistence
Shares the persistence model agreed in the Adversary Creator spec (§4):
`data/examplecombat.json` (tracked baseline) is copied to a git-ignored
`data/combat.json` on first edit, and the app then reads/writes that single
working file. Encounter definitions live under an `encounters` key **alongside**
`adversaries` in the same file, so a user's custom foes and the encounters that
use them travel together and are safe across `git pull`.

---

## 8. Acceptance criteria
- [x] Search/filter encounter definitions and open any for editing.
- [x] Create a new definition from known adversaries; save to the working library.
- [x] Edit an existing definition's roster, counts, scaling, and leader.
- [x] Add/remove roster lines; each line picks an adversary and a count (fixed or
      ×players) and can be marked promoted; plus an optional auto-promoted leader.
- [x] Live preview shows exactly what will spawn for N players, matching the
      tracker's generation (shared `resolve_roster`).
- [x] "Send to tracker" generates the live encounter and switches tabs.
- [x] Saved definitions persist to the working `combat.json` and appear in the
      Encounter tab's theme picker (after `refresh_themes`).
- [x] Non-human adversaries (once they exist) can be added with no UI change
      (roster references the adversary library).
- [ ] *(v1 gap)* Roster line **reorder** and the advisory difficulty band (§6)
      are not yet implemented; counts are int or ×players (no dice ranges).

---

## 9. Suggestions to the design (for discussion)
1. **Build after the Adversary Creator** — it depends on the adversary library
   and the shared writable persistence.
2. **Supersede `encounter_themes` with `encounters`** (back-compat adapter) so
   there is one place for encounter recipes and the existing tab keeps working.
3. **Unify the Encounter tab's theme dropdown** to read the same `encounters`
   map, so a saved definition is immediately runnable — no second source.
4. **Threat/difficulty estimate** (§6) to make balancing tangible.
5. **Roster count expressions** could later support ranges/dice (e.g.
   "2D6 Bandits") for random-size ambushes; start with int/×players.
6. **Import/export** a single encounter (with the adversaries it references)
   as one JSON bundle for sharing.
7. **Terrain/modifier notes** as structured optional fields later (e.g. "−5
   Bow in woods") that the tracker could surface; free-text `notes` for now.

---

## 10. Open questions for sign-off
1. **Merge with the existing Encounter tab?** Keep Creator (definitions) and
   Encounter (run) as **separate tabs** with a "Send to tracker" bridge
   (recommended), or fold definition-editing into the existing tab?
2. **Schema — DECIDED:** adopt the richer `encounters` map with a back-compat
   adapter (part of the unify decision).
3. **Counts:** integer + ×players only to start, or include dice ranges now?
4. **Difficulty estimate:** include the advisory band (§6) in v1, or defer?
5. **Persistence — DECIDED:** shares the `examplecombat.json` → git-ignored
   `combat.json` working-file model (Adversary Creator spec §4).
