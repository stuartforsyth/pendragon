# Battles: compiled design (stage 3)

Status: **APPROVED by the user 2026-10-17** (§13 resolved, all recommendations accepted), compiled 2026-10-17 from `breakdown.md` and
`pieces/01–09`. Those piece files hold the user's decisions and win any conflict
with this document. Anything here that no piece decided is either marked
*implementation choice* (no effect on what the user sees) or asked in
**§13 Questions for the user**.

Step numbers in this document follow **piece 5's ten-step stepper** (①–⑩). Pieces 3
and 4 numbered the steps differently, so piece 4's "step ②" (charge) is **③** here, and
piece 3/4's "step ⑥" (Morale) is **⑦** here.

---

## 1. Summary and play modes

The app runs King Arthur Pendragon battles (GM Book ch. 6) for the GM. It tracks
conroi **Morale**, the battle's days and turns, the Encounter decks, per-knight Glory
and the aftermath. It also shows players a battle-card board. It is **not a VTT**:
players roll physical dice and work out their own results; the GM enters only the
outcomes and amounts that change tracked state; the app enforces caps, minimums and
what each outcome allows.

| Mode | What it is | Where | Status |
|---|---|---|---|
| **Random fight** | Draw any encounter from the library, optionally filtered by tags (separate from battle decks) | Combat tool launcher | new (P1 d5) |
| **Set encounter** | Launch a chosen encounter | Combat tool launcher | exists |
| **Battle** | A container of many encounter fights plus battle state: days → turns → stepper, Morale, decks, Glory ledger, aftermath | new **Battle** tool (play) + **Battles** tool (prep) | new |

Several things work in **every fight**, not only in battles: the redesigned tracker
(lanes by knight), the Mounted pill with automatic Height, attacks-horse, Multiple
Opponents chip, retargeting, the Defeated strip, captives and the Glory ledger.

Scope boundary (all pieces): no player-knight profiles. Knights' skills, Passions, HP,
trait checks, Honor, First Aid, money and lifetime Glory stay on paper. Opportunity
cards and card special rules are **text played at the table**. Behaviour comes only
from small flags: `mounted`, `countercharge`, `attacks_horse`, `missile`, battle role,
Morale Minimum/Loss.

---

## 2. Data model

### 2.1 Saved battle definition: `combat.json` → `battles` (P1 d1, P9 K4)

Keyed by name, the same way as `encounters`. The app reads and writes only
`data/combat.json`. Examples ship in `data/examplecombat.json`.

```json
"battles": {
  "Bedegraine": {
    "source": "example",                 // "example" | "user"
    "name": "Bedegraine",
    "size": "large",                     // fight|skirmish|clash|small|medium|large|huge (Table 6.1)
    "where": "", "against": "", "notes": "",
    "outcome": null,                     // optional preset for Small+ (P7 d2)
    "days": [
      {
        "intensity": {"mode": "fixed", "value": 14},   // or {"mode": "roll"} = Table 6.1 dice for size
        "turns": 5,                       // hint shown when > Table 6.1 max (scenario override, not blocked)
        "first_charge": true,             // P1, P4 d6
        "on_foot": false,                 // "Conroi starts on foot" (P4 d6)
        "no_charge": false,               // "No charge this day" — skips step ③ all day
        "commanders": {"friendly": null, "enemy": null},  // preset outcome: critical|success|failure|fumble|null (P4 d1)
        "deck": {"foes": ["Pictish Pikemen", "..."], "opportunities": ["..."]},
        "notes": "",
        "scripts": [
          {"turn": 2, "text": "short paraphrase", "if_intensity": false,
           "deck": null}                  // or {"foes": [...], "opportunities": [...]} restriction
        ]
      }
    ]
  }
}
```

- A quick battle is the same shape built in place: size, days × `{"intensity": {"mode": "roll"}, "turns": Table 6.1 max}`,
  empty decks. `battle.started` always carries a **full copy** of the definition. The live copy is edited by events; the
  library template is never touched (P1 d3).
- "Save as template" writes the live definition, with no live state, to `battles` (P1 UI).

### 2.2 Encounter definition additions (P3 d1, d3, d11; P6 d7)

| Field | Type | Default | Notes |
|---|---|---|---|
| `battle_role` | `"foe"` \| `"opportunity"` \| `null` | `null` | `null` = not selectable in battles |
| `morale_minimum` | int | from roster cards (see Q23) | GM-only. Battle-card encounters already carry it |
| `morale_loss` | dice string, e.g. `"1D6+3"` | from roster cards | GM-only. Optional for Opportunities |
| `missile` | bool | false | Cambrian Archers, Pictish Javeliniers: barrage at fight start |
| `rules` | text | `""` | Opportunity rewards/rules, played at the table |
| `description` | text | exists | Card flavour (a Table-safe line) |
| `roster` | list | exists | Optional for Opportunities ("only when there's something to fight") |

**Opportunity** = an encounter with `battle_role: "opportunity"`: name, description,
`morale_minimum`, optional `morale_loss`, `rules` text, optional roster. There is no
per-card logic. The app enforces only RAW structure: once per battle (see Q15), reachable
on a Battle critical pick or by the GM's choice on an Intensity fumble, and it must be
played once chosen (P3 d3).

The legacy battle-card encounters (`core` + `per_player`) are already migrated to the
roster shape on read by `core.encounter_def.to_editable`. The data slice saves them in
roster shape (§9).

### 2.3 Adversary flags (P1 d4, P3 d11, P6 d1, d8)

| Field | Meaning | Set on (data fix) |
|---|---|---|
| `mounted` | foe's default Mounted pill | Gorre, Lothian, Malahaut, Cornwall, Breton, Northern Prickers (+ Mounted Sergeant, GM's call on the other knights) |
| `countercharge` | lance-armed: may countercharge | the five knight cards, Northern Prickers, Mounted Sergeant |
| `attacks_horse` | default for the foe's "Attacking the horse" toggle | Pictish Knifemen |
| `description` / `notes` | card flavour / card rules text (shown behind ⓘ in the type header) | all 12 cards (§9) |

*Implementation choice:* use the existing `description` (flavour) and `notes` (rules)
fields for card text rather than adding new fields. The adversary editor must keep the
new flags when it saves, the same way it already keeps battle data (commit d135cec).

### 2.4 Combatant additions (`core.combat.Combatant`, every fight)

| Field | Set by | Used for |
|---|---|---|
| `mounted` | adversary flag / knight's battle pill / `combat.mounted` | Height ±5, MO limit (3 on foot / 2 mounted), board chips |
| `attacks_horse` | adversary flag / `combat.horse`; cleared when the knight is on foot | cancels the foe's −5 Height (knight keeps +5) |
| `height_override` | `combat.height` (`null` = auto, `"none"` = negated) | two-handed spear/halberd and similar cases |
| `countercharge` | adversary flag | countercharge banner |
| `captured_by` | `combat.captured` | captives → ransom, enemy KV losses |
| status `surrendered` | `combat.status` (new `out` value) | Defeated strip fate; Glory trigger |
| (battle fights) `posture`, `rounds`, `extra_rounds` on knight rows | snapshot at fight start / `battle.extra_round` | "Round n of N · Posture", "withdraws" flag |

### 2.5 Live battle state (the battle reducer's output)

```text
battle = {
  id, name, status: mustering | turn | rear | aftermath | ended | paused,
  definition,                         # live copy (days, decks, scripts, switches)
  day, turn, turns_today,
  intensity: {value, rolled: bool},   # today's Intensity
  morale: {start, current, passion, history: [{delta, reason, event}]},   # current ≤ start, floored at 0 (Q13)
  commander: party_id | "gm",
  knights: {pid: {name, mounted, position: conroi|rear|alone|left,
                  posture, passion_used, passion_name, fought_days: [d...]}},
  army: {friendly: outcome|null, enemy: outcome|null},
  tokens: {force_encounter: available|spent|none, negate_loss: ...},
  reminders: {minus5_battle_turn1: bool},
  deck: {foes: [...], opportunities: [...]}, spent_opportunities: [...],
  step: {index, done: {①..⑩: event ids}, set, flavour, charge, intensity, picks, selected,
         loss, postures, barrage, countercharge, fight_id, script_reveals, inconsistent: [...]},
  fights: [{combat_event, day, turn, encounter, doubled}],
  defeated: [{cid, name, type, fate, glory, kv, credited_to, captured_by, day, fight}],
  glory: {pid: {fights: {fight_id: n}, by_day: {d: n}, manual: n, total}},
  aftermath: {inputs..., computed...}   # inputs from events, computed on replay
}
```

Nothing derived is stored in events. Morale `current` is the start plus entered deltas,
with cap and floor applied in order on replay. Charge results, barrage rounds, reach,
outcome and Glory are looked up from `core.battle` on replay.

---

## 3. Events and replay

### 3.1 Principles (P9 K1–K3)

- Events store **what was entered**: an amount with its reason, an outcome, a pick, a
  posture, an award, a pill, a position. They never store a capped or derived result.
  The battle reducer applies the rules on replay.
- Every battle-related event carries `data.battle = {id, day, turn, step}`. Combat
  events of a linked fight belong to it through the `combat.started` link.
- Every event has a GM `text` and a player-safe `data.table_text` (P8 interface).
  Mechanics-bearing payload keys are never in `_SAFE_DATA` (§7).
- Dice: "roll for me" rolls happen in the route through `core.dice`. The event stores
  the rolled number as the entered amount, so replay never re-rolls.

### 3.2 Battle-only events

| Type | Vis. | `data` (besides `battle`) | Replay effect |
|---|---|---|---|
| `battle.started` | public | `definition`, `source_key\|null`, `knights: [pid]` | new battle state, status `mustering`, day 1 |
| `battle.settings` | gm | `day`, `patch` (switches, turns, intensity, scripts, notes; current/future days only) | patch definition. Past days locked (route rejects) |
| `battle.deck` | public* | `day`, `add: [keys]`, `remove: [keys]` | edit day deck. *Table gets names only |
| `battle.mustered` | public | `day`, `start`, `passion`, `commander`, `knights: [pid]` | set Morale start=current, commander, membership. Reset Passions and positions for the day (scenario rule) |
| `battle.commander` | public | `commander` | change commander (P2 d1) |
| `battle.army_roll` | public | `day`, `side: friendly\|enemy`, `outcome`, `roll: {value, roll}\|null` | tokens/switches: friendly success/crit → first charge on; failure → off; fumble → off + −5 reminder; enemy success/crit → Force token; enemy fumble → Negate token (P4 d2) |
| `battle.day_started` | public | `day`, `intensity`, `rolled: bool` | today's Intensity; on-foot switch → all pills On foot |
| `battle.field` | public | `choice: field\|retire` (step ①) or `rear_choice: rest\|return\|leave` | status `turn`/`rear`; `leave` → aftermath |
| `battle.rest` | public | `amount` (1D6 entered/rolled) | Morale += amount (capped) |
| `battle.set` | public | `encounter`, `flavour`, `drawn: bool`, `forced: bool` | ② set Encounter. `forced` spends the Force token and skips ④ ⑤ |
| `battle.charge` | public | `outcome`, `engaged_last: bool` | ③ Table 6.3 per knight from Mounted pills |
| `battle.intensity` | public | `outcome`, `roll\|null` (die kept off the Table) | ④ stands / doubled / Opportunity / choose |
| `battle.pick` | public | `knight`, `encounter`, `crit: bool` | ⑤ a successful knight's pick (failed rolls are not entered) |
| `battle.select` | public | `encounter` | ⑥ commander's choice. An Opportunity is marked spent |
| `battle.morale` | public | `kind: loss\|forced_retire`, `amount\|null`, `negated: bool` | ⑦ minimum check; Loss applied (or 0 if negated, which spends the token) |
| `battle.posture` | public | `knight`, `posture`, `amount\|null` (1D3 / 1D6) | ⑧ R +amount, P −amount, C −amount (if above half HP) and knight → rear |
| `battle.passion` | public | `knight`, `used`, `name` | ⑧ toggle; second use in a day = warning |
| `battle.barrage` | public | `outcome` | ⑨ barrage rounds 0/1/2/3 → per-knight reach |
| `battle.countercharge` | public | `roll\|null` (null = first turn of day, automatic) | ⑨ "They countercharge!" if first turn or roll ≤ 2 |
| `battle.extra_round` | public | `knight` | Energetic+Valorous "+1 round" |
| `battle.position` | public | `knight`, `position` | chip; only `conroi` knights count for scaling and postures |
| `battle.mounted` | public | `knight`, `mounted` | pill change outside a fight (rear remount) |
| `battle.morale_adjust` | public | `delta`, `reason` | logged GM override (P1 d6, P2 UI) |
| `battle.turn_ended` | public | — | ⑩ KV Morale gain from that turn's fight(s) (capped), turn += 1 |
| `battle.day_ended` | public | — | next day → `mustering`; last day → `aftermath` |
| `battle.aftermath` | gm | `patch` (enemy KV edits, friendly losses, GM-knight helper inputs, outnumber, chosen outcome, roles, days-fought edits, opponent type, decisive £2D3 roll) | aftermath inputs; computed on replay |
| `battle.finale` | public | `summary` (published copy for the Table) | finale scene (P7 d6) |
| `battle.ended` | public | — | status `ended` |
| `battle.paused` | gm | — | status `paused` (written at session end, P9 K3) |
| `battle.resumed` | gm | `snapshot: {battle, combat\|null}`, `from_session` | **replace** state with snapshot |

### 3.3 Events used in every fight

| Type | New/changed | `data` | Notes |
|---|---|---|---|
| `combat.started` | changed | + `battle: {id, day, turn, encounter, doubled}`; knight snapshots carry `mounted`, `posture`, `rounds` | step ⑨ launches an ordinary combat (P6 d3) |
| `combat.mounted` | new | `cid`, `mounted` | any combatant. The battle reducer copies party pills into `knights` |
| `combat.horse` | new | `cid`, `on` | attacks-horse toggle |
| `combat.height` | new | `cid`, `override` | Height override |
| `combat.captured` | new | `cid`, `by\|null` | defaults to engaged knight (P6 d6) |
| `combat.status` | changed | `out` adds `"surrendered"` | |
| `combat.engage` | reused | `cid`, `with` | **retargeting** (drag or chip), unchanged (P6 d14) |
| `glory.awarded` | new | `knight`, `amount`, `reason`, `cid\|null`, `source: defeat\|manual`, `battle\|null` | auto on defeat (P1 d7) or the "Award Glory" action (P3 d3). Usable with no fight or battle |
| `glory.reassigned` | new | `award` (event id), `knight` | from the Defeated strip |

`combat_state.reduce` gains `combat.mounted/horse/height/captured` and treats
`battle.resumed.snapshot.combat` like a `combat.started`. It keeps folding only the
most recent combat. *Implementation choice:* `combat_state` gets an
`apply(state, ev)` step that the battle reducer reuses to fold each linked fight,
so the battle can collect `defeated` across all its fights.

### 3.4 How the battle reducer replays

`web/battle_state.py: reduce(live_events) → battle | None` (latest battle):

1. `battle.started` creates the state. `battle.resumed` **replaces** it with the snapshot.
2. Each stepper event is checked against the current step. If an event does not fit,
   for example because the GM struck an earlier step in the log, it goes in
   `step.inconsistent` and the stepper flags it. The reducer never guesses (P9 K2).
3. Morale: `current = clamp(current + delta, 0, start)` after each delta (rest, loss,
   posture, KV gain, override). The reason is kept for the Table animation.
4. Fight folding: from a linked `combat.started` to its `combat.ended`. Foes whose
   status becomes unconscious/dead/fled/surrendered are recorded in `defeated` with
   card Glory, KV and `captured_by`.
5. Glory: `glory.awarded` adds to the credited knight (per fight, per day and total).
   `glory.reassigned` moves it. An auto award whose foe is no longer defeated at the
   end of the fight fold does **not** count (see Q10).
6. `battle.turn_ended`: Morale += Σ KV of foes defeated in that turn's fight (see Q3/Q4),
   capped. `fought_days` updates for knights who were `conroi` at ⑨ (see Q27).
7. Aftermath: computed by `core.battle` from `defeated` (dead or captured → enemy KV)
   plus `battle.aftermath` inputs.

### 3.5 Undo

- **Single strike** from the session log works as today. Replay reflects it; the
  stepper flags a turn that no longer adds up.
- **Cascade (P9 K2):** reopening a finished step strikes that step and **every later
  battle-linked event of the same turn**: the later steps, the linked fight's
  `combat.*` events, its Glory events, and `battle.turn_ended`. A confirmation lists
  them first. Unrelated events (narration, dice tray, notes) are not struck. Cost:
  one `meta.strike` per event (see Q12).
- **Pause/resume (P9 K3):** at session end with a running battle the server writes
  `battle.paused`, allowed anywhere including mid-fight. Resume writes
  `battle.resumed` with the full snapshot (battle plus any fight in progress). Session
  files stand alone. Undo reaches back to the resume, never into the previous session
  (cascade interaction: Q11).
- The paused-battles list is built by scanning session files for a battle whose
  latest event is `battle.paused`, with no `battle.resumed` or `battle.ended` for
  the same id in a later session. *Implementation choice:* scan rather than add an
  index file. If the GM reopens the same session, it resumes the battle in place
  (snapshot still written, harmless).

---

## 4. `core/` vs `web/`

### `core/battle.py` (new, pure and tested)

| Function / data | Rule | Corpus |
|---|---|---|
| `SIZES` (turns, Intensity dice, participation base, plunder size mult) | Tables 6.1, 6.6, 6.10 | gm.battle.running-a-battle, after-the-battle, plunder-and-encounters |
| `charge_opportunity(outcome, engaged_last)` → may_charge / +5 / none / enemy_charge | Table 6.3 | gm.battle.fighting-the-battle |
| `POSTURES` → rounds 3/2/1/0, Morale dice 1D3 / — / 1D3 / 1D6 | Postures | gm.battle.fighting-the-battle |
| `barrage_rounds(outcome)`, `reaches(rounds, extra, barrage)` | Missile foes | gm.battle.fighting-the-battle |
| `countercharge(first_turn, roll)` | Chance of Countercharge | gm.battle.plunder-and-encounters |
| `height(foe_mounted, knight_mounted, override, attacks_horse)` → (foe_mod, knight_mod) | Height Advantage; attacking a horse | core.combat.combat-modifiers, core.combat.action-attack |
| `multiple_opponents(n)` → −5×(n−1); `mo_limit(mounted)` 3 foot / 2 mounted | Multiple Opponents | core.combat.multiple-opponents |
| `parse_kv("⅛")` → Fraction; `kv_total(foes)` | Knight Value | gm.battle.after-the-battle |
| `outcome(enemy_kv, friendly_kv, outnumber)` → label (zero ruling) | Outcome ratio | gm.battle.after-the-battle |
| `conroi_losses(outcome, n_gm_knights)` | Table 6.5 helper | gm.battle.after-the-battle |
| `participation_glory(size, days, outcome, role)` | Tables 6.6–6.8 | gm.battle.after-the-battle |
| `plunder(opponents, outcome, decisive_roll, outnumber, role, size)` | Tables 6.9–6.10 | gm.battle.plunder-and-encounters |
| `glory_for(foe)` = card Glory (×promotion); `is_defeated(status)` | Table A.1 trigger | gm.glory-awards.combat-and-adventure |
| `apply_morale(current, start, delta)` | cap, floor | gm.battle.running-a-battle |
| `scale_roster(defn, n_knights, doubled)` | per-knight counts, crit doubling | cards; Intensity crit |
| `selectable(deck, morale, picks)` / `forced_retire(...)` | Minimum Morale | gm.battle.running-a-battle, battlefield-position-and-surrender |

`core/combat.py`: Combatant gains the new fields (§2.4), the `surrendered` status, and
roll modifiers from Height. `core/encounter_def.py`: blank and editable shapes carry the
battle fields.

### `web/`

| Module | Role |
|---|---|
| `web/battle_state.py` (new) | reducer (§3.4), `gm_view`, `table_view` |
| `web/routes/battle.py` (new) | live battle routes; builds events, `table_text` |
| `web/routes/library.py` | `/api/battles` CRUD; encounter battle fields; deck lists |
| `web/routes/combat.py` | new pill/horse/height/captured/glory routes; random fight; linked start |
| `web/combat_state.py` | new event types; `apply` refactor; snapshot restore |
| `web/table.py` | battle projection, battle/fight views, filtering (§7) |
| `web/state.py` | `battle_state()`, table payload includes battle |
| `web/routes/session.py` | end session → `battle.paused` |

---

## 5. API routes

### Prep (library edits, not logged, as for encounters)

| Method | Path | Body | Effect |
|---|---|---|---|
| GET | `/api/battles` | — | list saved battles (name, size, days, source) |
| GET | `/api/battles/blank` | — | blank definition |
| GET | `/api/battles/{key}` | — | one definition |
| PUT | `/api/battles` | `{definition, overwrite?}` | save to `combat.json` `battles` |
| DELETE | `/api/battles/{key}` | — | remove |
| GET | `/api/battle-decks` | `?role=foe\|opportunity` | battle-approved encounters with Min/Loss/KV (GM) |

### Live battle

Every player-reported outcome goes through **one entry point**,
`POST /api/battle/step`, so VTT player dice can plug in later (§11).

| Method | Path | Body | Event(s) |
|---|---|---|---|
| GET | `/api/battle` | — | GM view of the live battle (or null) |
| GET | `/api/battle/paused` | — | paused battles across sessions |
| POST | `/api/battle/start` | `{key}` or `{quick: {size, days, name, where, against, notes}}` | `battle.started` |
| POST | `/api/battle/resume` | `{battle_id, session_id}` | `battle.resumed` (snapshot) |
| POST | `/api/battle/pause` | — | `battle.paused` |
| POST | `/api/battle/settings` | `{day, patch}` | `battle.settings` |
| POST | `/api/battle/deck` | `{day, add, remove}` | `battle.deck` |
| POST | `/api/battle/quick-encounter` | `{definition}` | saves a battle encounter to library + `battle.deck` (P3 d5) |
| POST | `/api/battle/template` | `{name}` | copies the live definition to `battles` |
| POST | `/api/battle/muster` | `{start, passion, commander, knights}` | `battle.mustered` |
| POST | `/api/battle/commander` | `{commander}` | `battle.commander` |
| POST | `/api/battle/army-roll` | `{side, outcome}` or `{side, roll_for_me: {battle, mods}}` | `battle.army_roll` |
| POST | `/api/battle/day` | `{intensity}` or `{roll_for_me: true}` | `battle.day_started` |
| POST | `/api/battle/step` | `{step, ...}` (field, rear, rest, set, draw, charge, intensity, pick, select, morale, posture, passion, barrage, countercharge, extra_round, end_turn, end_day) | matching `battle.*` |
| GET | `/api/battle/undo-preview` | `?step=` | list of events a cascade would strike |
| POST | `/api/battle/undo` | `{step}` | `meta.strike` × N |
| POST | `/api/battle/fight` | `{}` (uses the selected Encounter, conroi knights, doubling) | `combat.started` (linked) |
| POST | `/api/battle/morale` | `{delta, reason}` | `battle.morale_adjust` |
| POST | `/api/battle/knight/{pid}` | `{position?}` `{mounted?}` | `battle.position` / `battle.mounted` |
| POST | `/api/battle/aftermath` | `{patch}` | `battle.aftermath` |
| POST | `/api/battle/finale` | — | `battle.finale` |
| POST | `/api/battle/end` | — | `battle.ended` |

### Every fight

| Method | Path | Body | Event |
|---|---|---|---|
| POST | `/api/combat/random` | `{tags?: [...], players?}` | draws an encounter, then as `/api/combat/start` |
| POST | `/api/combat/start` | + `knights_mounted?` (Q28) | `combat.started` |
| POST | `/api/combat/{cid}/mounted` | `{mounted}` | `combat.mounted` |
| POST | `/api/combat/{cid}/horse` | `{on}` | `combat.horse` |
| POST | `/api/combat/{cid}/height` | `{override}` | `combat.height` |
| POST | `/api/combat/{cid}/captured` | `{by}` | `combat.captured` |
| POST | `/api/combat/{cid}/status` | `out` adds `surrendered` | `combat.status` (+ auto `glory.awarded` or a "Who defeated them?" prompt) |
| POST | `/api/combat/{cid}/engage` | `{with}` (unchanged) | `combat.engage` (retarget) |
| POST | `/api/combat/{cid}/roll` | unchanged | modifier now includes Height |
| POST | `/api/glory` | `{knight, amount, reason, cid?}` | `glory.awarded` |
| POST | `/api/glory/{event_id}/reassign` | `{knight}` | `glory.reassigned` |

Defeat triggers (hp, blow, status) that leave a foe defeated with no engaged knight
return `{prompt: "who_defeated", cid}`. The GM's answer calls `/api/glory`.

---

## 6. GM UI

### 6.1 Navigation and shared components

Rail: **Battle** (play group, after Combat, icon `banner`) and **Battles** (prep group,
after Encounters). Shared components, each built once:

| Component | Used in |
|---|---|
| **Outcome chips** Crit / Success / Fail / Fumble (+ optional "roll for me") | army rolls, charge, Intensity, barrage, picks |
| **Amount entry** number + "roll for me" (dice hint) | rest, Loss, posture amounts, countercharge, Intensity value, plunder £2D3 |
| **Deck picker** checklist, Foes / Opportunities tabs, Min/Loss/KV columns | saved-battle day card, live deck edit, turn-script restriction |
| **Morale strip** | Battle tool header, tracker battle frame |
| **Knight chip** (shield, name, Mounted pill, position, posture) | Mustering, stepper, tracker lane header |
| **Day card** | Battles editor, live Battle settings drawer |

Navigation: Battle ⇄ Combat via "Begin the fight" (step ⑨) and "Back to battle" (the
tracker's battle frame). Battles editor "Launch" → Battle tool. Battle settings drawer
"Edit deck" opens the deck picker in place.

### 6.2 Battle tool, idle: launch panel (P1 UI)

- **Paused battles**: name, day/turn, Morale `14 / 21`, session. **Resume**.
- **Quick battle**: Size chips (each shows max turns and the Intensity dice), Days
  stepper, Name, folded flavour (where / against / notes). **Launch**: 2 clicks.
- **Saved battles**: list → **Launch**.

### 6.3 Battles tool (prep): saved-battle editor

Uses the Encounters pattern: list + form + Launch. Header: name, Size, where, against,
notes, optional preset outcome (Small+). One **day card** per day:
- Intensity: roll-from-Size or fixed.
- Turns stepper, with a hint when over the Table 6.1 max.
- Switches: First charge / Conroi starts on foot / No charge this day.
- Commander outcome presets.
- Deck picker.
- Notes.
- Turn scripts: turn #, text, restricted deck, "only if Intensity succeeds".

Then **Add day**.

### 6.4 Mustering (Turn 0, and each new day) (P2, P4)

- Knights in the conroi: checklist from the active Party (Q22).
- Commander chips: each knight + "GM".
- **Starting Morale** number. On a new day it is pre-filled with yesterday's start.
- Optional Passion name.
- Clash+: an **Army Commanders** block with friendly and enemy outcome chips,
  optional "roll for me" (Battle value, default 2D6+10, and a Table 6.2 ticklist),
  and a folded Table 6.2 reference. Pre-filled from the saved battle.
- Day Intensity: "roll for me" or entered.
- **Begin Turn 1** stays disabled until there is a commander and a Morale.

### 6.5 Running battle: Morale strip and stepper (P2, P4, P5)

**Morale strip** (pinned): `current / start`, ± adjust (logged override, asks for a
reason), commander (click to change), and tokens **Force Encounter** / **Negate Morale
loss** until spent (click to use at ② / ⑦). Header: `Day N · Turn t of T`, Intensity,
Battle settings drawer.

**Vertical stepper.** Done steps collapse to a one-line result that can be reopened
(cascade undo with a confirm list). The current step is expanded. Steps that do not
apply are greyed.

| Step | GM sees / does | Skipped when |
|---|---|---|
| ① Field or rear | "Take the field" / "Retire to the Rear". At the rear: Rest another turn / Return / Leave the field + **Rest roll** entry + reminders (First Aid 14+1D6, remount → flip pill) | — |
| ② Set Encounter | today's turn scripts (GM text). Pick from the deck (or a restricted deck), or **Draw** (random Foe, not Morale-filtered). Editable flavour line. Force token here | — |
| ③ Charge | commander outcome chips + "engaged last round" (pre-filled: fought → engaged; rested / first turn of the day → unengaged) → per-knight Table 6.3 line. "Enemy knights charge you!" locks to mounted-knight Encounters (Q17) and skips ④ ⑤, with the on-foot prompt (enemy +5 Height; Set Spear) | turn 1 first charge; "No charge this day"; see Q29 |
| ④ Intensity | roll for me / outcome: stands · crit doubles foes · fumble → GM may choose an Opportunity · fails → ⑤ | forced Encounter; enemy charge |
| ⑤ Picks | per successful knight: card + crit flag (an Opportunity only on a crit) | Intensity succeeded |
| ⑥ Commander's choice | the set card or one of the picks; a chosen Opportunity must be played | no picks |
| ⑦ Morale | minimum check → **forced retire** (no fight), or Loss (roll for me / entered), or Negate token | — |
| ⑧ Postures | per conroi knight R/V/P/C chips (rounds shown; first-charge turns R/V only) + amount entry for R/P/C + Passion toggle (optional name; a second use in a day warns) + Trait/Honor board reminders | — |
| ⑨ Fight | missile → barrage outcome chips; lance foes → countercharge (auto/roll); **Begin the fight** → tracker | — |
| ⑩ End turn | KV Morale gain preview → **End turn**; on the last turn **End day** → re-muster or aftermath | — |

### 6.6 Combat tracker, redesigned (every fight) (P6 d9–d15)

```
┌ battle frame (battle-linked only): Bedegraine · Day 1 · Turn 2 · Knights of Gorre
│ Morale 14/21 [tokens] · [Back to battle] · banner: "They countercharge!" / "Barrage: 2 rounds"
├ GM notes ▸ (one collapsed line)
├ Sir Erik ▾ [Mounted] Valorous · Round 1 of 2 · with the conroi · Glory 50/120 · ⚠ 2 foes −5 each · [Down][Out]
│   ┌ Knights of Gorre  SIZ15 DEX11 STR15 CON15 · Charge 17 · Spear 15 · Sword 17 · 7+6 ⓘ
│   │ Gorre 1  ████████░░ 24/30  Wounded   [+5 Ht][horse] → Sir Erik   [Hit][±HP][⋯]
│   │ Gorre 2  ██████████ 30/30  Unhurt                  → Sir Erik   [Hit][±HP][⋯]
├ Sir Bors ▾ ...
├ Not engaged (pool)
└ Defeated: Gorre 3 — surrendered · +50 Sir Bors · captured by Sir Bors [undo][reassign]
```

- **Lanes by knight.** The lane header has the Mounted pill, posture/rounds
  ("withdraws" when done, never blocking, "+1 round"), position chip, Glory this
  fight/battle, Down/Out, and the Multiple Opponents chip (warns beyond 3 on foot / 2
  mounted attackers).
- **Type header per adversary type** with clickable attacks and ⓘ (deduplicated card
  rules). **One line per foe**: name, HP bar with numbers, wound state, chips (Height,
  horse), target chip, Hit, ±HP, ⋯. Click the name to expand it.
- **Retarget**: drag a foe to a lane or the pool, or use the target chip → `combat.engage`.
- **Defeated strip** for unconscious/dead/fled/surrendered: fate, Glory credit,
  captured; click to undo or reassign.
- Plain fights show the same tracker with no battle frame.

### 6.7 Aftermath panel (P7)

Three columns, every number editable, then **Post to Table**:
- **Outcome**: enemy KV pre-filled from dead + captured; friendly losses (PKs × 1 +
  Table 6.5 helper); outnumbering none / 2:1 / 1:2; computed result. Small+: GM
  chooses, with the computed result as a suggestion.
- **Glory**: per knight Encounter Glory + participation (base × days × (outcome +
  role)); role dropdown conroi ×2 / bataille ×3 / army ×5.
- **Spoils**: opponent type (Table 6.9), Decisive +£2D3 (roll for me), outnumber and
  commander modifiers → £ per knight; captives with "Roll ransom" against the captor.

### 6.8 Session log (P9 UI)

Battle events are grouped under `Day N · Turn t` headers. A **Battle** filter chip
joins the existing filters.

---

## 7. Table projection

### 7.1 Modes

`auto` = **fight view** if a combat is active, otherwise **battle view** if a battle is
running or paused-in-session, otherwise **chronicle**. The GM can pin a mode; "Battle"
is added to the pin chips.

### 7.2 Battle view (between fights) (P8 J1)

- **Title band**: battle, where/against, Day/Turn, **Intensity number** (RAW, P3 d7).
- **Morale gauge**: big number "of N", draining fill, frame colour green-gold → deep
  red **and** texture clean → bloodied **and** a word (Steady · Shaken · Bloodied ·
  Breaking; bands Q21). Each change animates with its reason ("−4 · Knights of Gorre").
  No thresholds.
- **This turn** slot: the set card flips in from the deck. Picked cards carry the
  knight's shield token. Opportunities have a gold border and ★.
- **Deck spread**: today's Foes and Opportunities rows, **names only**; additions
  appear; spent Opportunities greyed.
- **Knights row**: Glory counter (fight / battle, ticking with "+50 · Sir Erik …"),
  Mounted, effect chips (+5 Height, −5 two foes, −5 Battle army fumble, Charge +5, On
  foot, Reckless 2/3, Passion used, At the rear), and a "happened to you" line (last 2–3
  events touching that knight).
- **Step results**: Intensity result word, charge result per knight, enemy charge,
  barrage/countercharge, "Not enough Morale — Retire to the Rear", revealed
  conditional turn scripts, the turn-1 "−5 Battle" reminder.
- **Fray** feed: `table_text` of each event.
- Opening title card on `battle.started` / `battle.day_started`. Finale on `battle.finale`.

### 7.3 Fight view (during an Encounter)

Header band: battle/day/turn/encounter, Morale bar, Glory per knight. Lanes by knight
mirror the GM tracker: foe names and **wound-state words only**, target, Height/horse
chips. Defeated strip: fate, Glory credit (after defeat), captured. Plain fights use
the same lanes without the battle header.

### 7.4 Filtered server-side in `web/table.py` (never sent)

| Never on the Table | How it is kept off |
|---|---|
| Morale Minimum and Morale Loss values or dice (RAW GM p.126) | not in battle `table_view`; `battle.morale` `_SAFE_DATA` = amount only; **a "roll for me" Loss is recorded as `battle.morale`, not a public `roll.*`**, so the dice expression never reaches the Fray |
| Raw Intensity die (P3 d7) | `battle.intensity` safe keys = `outcome` only |
| Foe stats, HP numbers, card rules, Glory before defeat | existing `table_view` (wound words); type headers are GM-only; Glory only via `glory.awarded` after defeat |
| KV (deck picker, aftermath inputs) | not in `table_view`; `battle.aftermath` is `gm` |
| GM notes, encounter notes | `gm` / not projected |
| Unrevealed turn scripts; script restrictions | definition never projected; only `if_intensity` scripts after a successful ④ (Q20 for the others) |
| Deck card details | deck spread = names + role + spent flag only |
| `battle.settings`, `battle.paused`, `battle.resumed` | `visibility: gm` |
| Army commander die and modifiers | `battle.army_roll` safe keys = `side`, `outcome` |

What players do see: current Morale and cap, drops after the fact with reason, the
Intensity number and results, cards played, postures and Passions, positions, charge,
barrage and countercharge results, Glory after defeat, the finale.

---

## 8. Rules coverage map

App = enforced/tracked · Assist = prompt/reference/computed suggestion · Table = played
at the table/paper. **SR** = scenario rule (Sword Campaign), **GR** = GM ruling. Both
are labelled in the UI.

| Rule | Handling | Where | Corpus |
|---|---|---|---|
| Battle Size: max turns, random Intensity | App (hint, not block, over max) | Battles editor, quick launch | gm.battle.running-a-battle (6.1) |
| Army commander Battle 2D6+10 if unknown | Assist (roll for me) | Mustering | running-a-battle |
| Table 6.2 modifiers | Assist (reference/ticklist only) | Mustering | running-a-battle |
| Commander results → first charge / −5 / force / negate | App (tokens, switch, reminder) | Mustering, strip | running-a-battle |
| Commander rolls only Clash+ | App (hidden for Fight/Skirmish) | Mustering | running-a-battle |
| **Commander rolls repeated each day** | App, **SR extension** (P4 d3) | Mustering | — |
| Two decks; Foes recur, Opportunities once, crit only | App | deck, ⑤ ⑥ | running-a-battle, plunder-and-encounters |
| Conroi Morale: average Passion +5 same | Table (GM enters number) | Mustering | running-a-battle |
| Morale ≤ start | App (cap on replay) | reducer | running-a-battle |
| Minimum Morale → Retire | App | ⑦ | running-a-battle, battlefield-position-and-surrender |
| Must retire at Morale 0 | **Gap** (Q1) | — | battlefield-position-and-surrender |
| Turn ① Set Encounter, Battle Events | App (text scripts) | ② | fighting-the-battle |
| Table 6.3 Mounted Charge Opportunity | App (per knight from pills) | ③ | fighting-the-battle |
| First Charge (R/V only) | App | ③ ⑧ | fighting-the-battle |
| **Mixed conroi first charge** | **GR** (P4 d7) | ⑧, tracker | — (RAW silent) |
| Enemy knights charge you → on-foot prompt, Set Spear | App + Assist | ③ | gm.battle.countercharge, core.combat.action-set-spear |
| Intensity roll and results; visible to players | App | ④, Table | fighting-the-battle; P3 (GM p.122) |
| Battle roll picks | App (outcome only) | ⑤ | fighting-the-battle; P3 (GM pp.128–129) |
| Reduce Morale by Encounter Loss | App | ⑦ | fighting-the-battle |
| Postures: rounds and Morale effects | App (amounts entered) | ⑧ | fighting-the-battle |
| Trait checks, −1 Honor (Cowardly) | Table (board reminder) | ⑧ | fighting-the-battle |
| Passions once per battle | App (toggle + warning); **per-day reset SR** | ⑧ | fighting-the-battle |
| Fight posture rounds; fresh foe; Energetic+Valorous extra round | Assist (round counter, never blocks) | tracker | fighting-the-battle |
| No aiding allies without Evade | Table | — | fighting-the-battle |
| Glory per defeated foe | App (ledger) | tracker | fighting-the-battle; gm.glory-awards.combat-and-adventure |
| Morale + KV of defeated foes | App | ⑩ | fighting-the-battle |
| Missile barrage rounds, reach | App; per-round hit location Table | ⑨ | fighting-the-battle |
| Shield Missile Penalty, no Zigzag | Table | — | fighting-the-battle |
| Countercharge (turn 1 always, later 1D6 1–2); **"first turn of a day" = SR extension** | App | ⑨ | plunder-and-encounters |
| Height ±5; negation; attacking the horse | App (auto + override + toggle) | tracker | core.combat.combat-modifiers, core.combat.action-attack |
| Large shield −2 mounted | Assist (reminder chip) | tracker | core.armor (armor-and-helmets) |
| Multiple Opponents −5/extra; 3 foot / 2 mounted | Assist (chip, warning) | tracker | core.combat.multiple-opponents |
| Squire roll (lance, horse, escort, bear wounded) | Table (pill flip if remounted) | ⑩ | fighting-the-battle |
| Capture and ransom; escort misses next turn | App (captured flag, position chip); escort rolls Table | tracker | fighting-the-battle |
| Retire: ≥1 turn, +1D6, +1D6/turn, return or Leave | App | ① rear | battlefield-position-and-surrender |
| First Aid at rear; remount | Table (reminder) | ① rear | battlefield-position-and-surrender |
| Alone on the Field | Assist (chip + reminder; optional linked fight, Q16) | tracker | battlefield-position-and-surrender |
| Surrender check (Valorous at ½ HP) | App (exists); −5 on foot vs mounted: Q24 | tracker | battlefield-position-and-surrender |
| Fleeing contests | Table | — | battlefield-position-and-surrender |
| Disobeying orders | Table | — | fighting-the-battle |
| Mid-fight retreat | Table (marked retired next turn) | ① | battlefield-position-and-surrender |
| KV tally (killed or captured) | App (pre-fill, editable) | aftermath | after-the-battle (6.4) |
| Table 6.5 conroi losses | Assist (helper) | aftermath | after-the-battle |
| Outcome ratio ×2 / ×½ | App (Fight/Skirmish/Clash), Assist (Small+) | aftermath | after-the-battle |
| **Zero friendly losses** | **GR** (P7) | aftermath | — (RAW divides by 0) |
| Participation × (outcome + leader) | App | aftermath | after-the-battle (6.6–6.8) |
| **Participation per day fought** | App, **SR** (P7 d1; not labelled in P7, see Review) | aftermath | — |
| Plunder 6.9, Decisive +£2D3, 6.10 | App (computed, not stored) | aftermath | plunder-and-encounters |
| Division/Army leader plunder | **Gap** (Q8) | — | plunder-and-encounters |
| **Days, per-day Intensity, per-day re-muster** | App, **SR** (P1 d2) | battle | after-the-battle ("or the scenario") |
| Opportunities pp.143–148 | Table (card text) | — | **not in corpus** (COVERAGE.md gap) |

---

## 9. Data fixes required (one build slice, S0)

Baseline `data/examplecombat.json` (tracked):

| Fix | Source |
|---|---|
| Irish Kerns: armour 4 / shield 0 → **armour 0, shield 4** (Targe, "unarmored") | P3 audit |
| Cambrian Archers: "a third injured" → "seriously injured" | P3 audit |
| `mounted: true` on Gorre, Lothian, Malahaut, Cornwall, Breton, Northern Prickers | P3 audit |
| `countercharge: true` on the five knight cards, Northern Prickers, Mounted Sergeant | P6 d8 |
| `attacks_horse: true` on Pictish Knifemen | P6 d1 |
| Card flavour + rules text on all 12 cards (special rules and weapon footnotes as text; Q18 paraphrase) | P3 d11 |
| Battle-card encounters: `battle_role: "foe"`, `morale_loss` from card, roster shape, `missile` on Archers and Javeliniers | P3 d1, P6 d7 |
| The **5 Opportunity cards** as Opportunity encounters (minimal shape) | P3 d11 |
| Example battles **Bedegraine** (2 days, Intensity 14/18, 5 turns/day, per-day decks, scripts, day 2 on foot) and **Carlion** (GM commander), scripts as short paraphrases | P1, P4 d6, P9 K4 |

User's `data/combat.json` (git-ignored, **never overwritten**): the app reads only
this file, so baseline fixes and examples do not reach it automatically (Q19). Known
damage: hand-edited **Knights of Lothian** lost `battle_card`, `morale_minimum`,
`per_player`, `ransom`, `morale_loss`, KV, Glory (0 vs 50), HP 30 vs 31. It needs a
targeted repair, done only with the user's consent.

Already done, so no action is needed: per-player rounding now rounds half up
(`_rhu`, commit bece26f). The adversary editor keeps battle data (d135cec) and must be
extended to the new flags.

---

## 10. Build order (shippable slices)

| # | Slice | Depends on | Usable result |
|---|---|---|---|
| S0 | Data fixes + flags + `core/battle.py` tables with tests | — | correct cards; tested rules functions |
| S1 | Tracker redesign: lanes by knight, type headers, one-line foes, Defeated strip, drag/chip retarget, `surrendered` | — | every fight |
| S2 | Mounted pill, auto Height in foe rolls, attacks-horse, Height override, MO chip, captured flag | S1 | every fight |
| S3 | Glory ledger: auto award, "Who defeated them?", reassign, Award Glory, per-fight tally; Table counters and fight-view lanes | S1 | every fight |
| S4 | Random fight with tag filter | — | Combat launcher |
| S5 | Encounter battle role, Morale Min/Loss, missile, Opportunity shape in the Encounters editor; deck lists | S0 | prep |
| S6 | Battle container: Battles editor, launch panel, `battle.started`, Mustering, Morale strip, commander, army rolls + tokens, day Intensity, settings drawer, deck edit/quick-create, pause/resume, Table title card + Morale gauge | S5 | battles can be set up, mustered, paused |
| S7 | Turn stepper ①–⑧ ⑩, rest/rear, cascade undo, inconsistency flags | S6 | full turn loop without the fight |
| S8 | Step ⑨: linked fight, scaling + doubling, postures/rounds in lanes, barrage, countercharge, positions, KV Morale at End turn, Alone on the Field | S2, S3, S7 | battles play end to end |
| S9 | Table battle view: cards, deck spread, knights row chips, "happened to you", Fray, fight-view battle header | S7 (S8 for fight view) | players' board |
| S10 | Aftermath + finale | S8 | battle closes |
| S11 | Log grouping + Battle filter; example battles Bedegraine/Carlion | S6+ | polish |

---

## 11. Future

- **VTT player dice phase**: players roll in the app. Every outcome already goes
  through `POST /api/battle/step` (and the existing combat attack/blow routes), so a
  dice source can feed the same entry point without new event types.
- **Real card art**: local-only images extracted from the user's own PDF (git-ignored),
  dropped into the card frame. Not in v1.
- **Feasts** and other mechanics reuse the pattern: a definition in the library →
  `*.started` with a full copy → stepper of entered outcomes → reducer → Table view
  with server-side filtering, plus the shared Outcome chips, Amount entry and
  token/strip components.

---

## 12. Review findings

What was checked: every piece decision against the corpus (`gm.battle.*` all 8 files +
`gm.battle.countercharge`, `gm.glory-awards.combat-and-adventure`,
`core.combat.multiple-opponents/combat-modifiers/action-attack/action-set-spear`,
`core.armor` large shield), against each other, and against the current code
(`combat_state`, `routes/combat.py`, `table.py`, `sessions.py`, `state.py`,
`core/combat.py`, `encounter_def.py`, `rules.py` load path, tracker/Table JS).

**Rules: consistent with RAW**
- Turn order, minimum check before Loss (step 4 before 5), Table 6.3, postures,
  barrage, Height and attacking the horse, MO, Glory triggers ("surrendered, killed,
  disabled, driven from the fight") and Glory tables all match the corpus.
- Retire to the Rear: piece 5's per-turn rest entry reproduces "+1D6 on retiring,
  +1D6/turn while disengaged, capped".
- Enemy KV "killed or captured" matches. Fled and uncaptured unconscious foes are
  correctly excluded.
- Morale Minimum/Loss secrecy and Intensity visibility rely on the GM Book pages
  recorded in pieces 3/8. The corpus doesn't hold that text, so they are accepted as
  recorded.

**Rules: departures, all labelled except one**
- SR (labelled): days, per-day Intensity and engagement reset, Passions per day,
  commander rolls per day.
- SR extension (**should be labelled**): countercharge "first turn of a day" (P6 d8)
  follows from the per-day reset but no piece labels it. Also "participation Glory ×
  days fought" (P7 d1) is a Sword Campaign figure; P7 lists only the zero-loss ruling
  under rulings. This design labels both as SR.
- GR (labelled): mixed-conroi first charge; zero friendly losses.
- Outcome ratio bands have gaps in RAW (1.9–2, 3.9–4, 0.4–0.5). *Implementation
  reading:* thresholds ≥4 / ≥2 / ≥0.5 / ≥0.25 / below, so 0.45 counts as Defeat.
  The user sees the result, so it is asked as Q26.

**Rules issues for the rules-issues queue (corpus, not design)**
- The barrage example in `gm.battle.fighting-the-battle` (p.130) calls the Reckless
  knight "2 rounds, but a 3rd on a successful Energetic+Valorous", which contradicts
  Reckless = 3 rounds. The outcome is the same either way. Check the transcription
  against the PDF (see Q25).
- The KV discrepancy in the mounted foes (1/2 vs Table 6.4 1/4, etc.) is already noted
  in the corpus. The app uses card KV consistently.
- The Opportunities (pp.143–148) and the Battle Cards deck are still not in the corpus.

**Contradictions and gaps between pieces** (each one is a question in §13)
- Step numbering differs between pieces 3/4 and 5 (reconciled above).
- Morale 0 outside step ⑦ (Q1).
- Whether a forced-retire turn counts as the first rest turn (Q2).
- Fractional KV Morale (Q3), and what "defeated" means for KV Morale (Q4).
- Crit doubling vs scaling (Q5), Cowardly knights vs scaling (Q6).
- Multi-day outcome and leader (Q7), plunder for bataille/army roles (Q8).
- Glory on retarget (Q9), Glory events vs derivation (Q10).
- Cascade vs resume (Q11), cascade strike volume (Q12).
- Morale override vs cap (Q13), Negate token scope (Q14).
- Once-per-battle items in multi-day battles (Q15).
- Alone fight with the single active combat (Q16).
- "Mounted-knight Encounter" definition (Q17).
- How baseline data reaches `combat.json` (Q19).
- Unconditional scripts on the board (Q20), membership (Q22).
- Turn-1 charge roll when the first charge is off (Q29).

**Simpler alternatives found:** Q10 (derive auto-Glory), Q12 (one strike event for a
cascade), Q16 (Alone fight as a lane in the same tracker), Q24 (apply the surrender −5
from pills).

**Implementation choices (no user-facing consequence):**
- card text in the existing `description`/`notes` fields;
- `combat_state.apply` refactor reused by the battle reducer;
- paused-battle discovery by scanning session files;
- `battle.mounted` outside fights plus `combat.mounted` inside them, both read by the
  battle reducer;
- battle id = random hex at `battle.started`.

---

## 13. Questions for the user — RESOLVED

**2026-10-17: the user accepted every recommendation below (all 29).** Treat each **Rec.** as a decision; the two scenario-rule extensions flagged in §12 (countercharge on each day's first turn; participation Glory × days fought) are confirmed as labelled scenario rules.

1. **Morale reaching 0 outside step ⑦.** RAW: "must retire when Morale hits 0"
   (gm.battle.battlefield-position-and-surrender). Only the step ⑦ minimum check
   forces a retire, so a Loss, a Prudent/Cowardly loss or an Alone drain can take
   Morale to 0 without one. **Rec.:** floor Morale at 0. If it is 0 after the ⑦ Loss,
   retire is forced (no fight). If it reaches 0 later, the next turn's ① allows only
   "Retire".
2. **Does the forced-retire turn count as the first rest turn?** **Rec.:** yes. A
   retire at ① or ⑦ asks for the 1D6 then and ends the turn; the next turn opens at
   the rear (RAW "≥1 Battle Turn, +1D6 on retiring").
3. **Fractional KV Morale gain** (3 Kerns = ⅜). RAW is silent on rounding. **Rec.:**
   sum each Encounter's defeated KV and round half up, labelled **GM ruling**.
4. **Which defeats count for KV Morale?** **Rec.:** the same set as Glory
   (unconscious, dead, fled, surrendered). The aftermath KV tally stays dead + captured
   (RAW "killed or captured").
5. **Intensity crit doubling × per-knight scaling.** **Rec.:** double the resolved
   count (1.5 × 3 knights = 5 → 10), every roster line included (RAW "doubles foes").
6. **Cowardly knights and scaling.** Foes are scaled at ⑨, after ⑧. **Rec.:** exclude
   Cowardly knights (they "don't engage" and are already at the rear).
7. **Multi-day aftermath: outcome and leader.** There is one outcome for the whole
   battle × days fought. The commander can change mid-battle. **Rec.:** keep one
   outcome (P7 d1). Default the leader role to the knight who commanded the most days,
   editable per knight. Label "× days fought" as a scenario rule.
8. **Plunder for bataille/army roles.** The Glory dropdown has ×3/×5, but plunder
   applies only the conroi +⅓. **Rec.:** apply Table 6.10's Division (×3 × size mult)
   and Army (×10 × size mult) from the same dropdown (RAW, cheap).
9. **Glory credit after retargeting.** **Rec.:** credit the knight the foe is engaged
   with *at the moment of defeat*, regardless of who wounded it earlier. Prompt if it
   is in the pool. Reassign from the Defeated strip.
10. **Auto-Glory as stored events vs derived.** A stored `glory.awarded` outlives a
    struck killing blow (orphan award), and a re-defeat would award twice. **Rec.:**
    derive auto awards on replay from defeat + engagement. Keep events only for prompt
    answers, reassignments and manual "Award Glory". Undo stays exact. The decision
    "each award undoable/reassignable" is still met. (If kept as events, the reducer
    must drop awards whose foe is no longer defeated, as §3.4 describes.)
11. **Cascade undo across a resume.** Steps done before `battle.resumed` are in the
    previous session and can't be struck. **Rec.:** show them locked ("before resume").
    Correct them by logged Morale override or by striking everything since the resume.
12. **Cascade strike volume.** A fight can mean 50–150 strikes. **Rec.:** one
    `meta.strike` with `targets: [...]`: one log line, one unstrike. This needs a small
    `flags()` change.
13. **Morale override vs cap.** **Rec.:** the cap stays enforced. To exceed it, the GM
    edits the starting Morale (logged). Floor at 0.
14. **Negate token scope.** **Rec.:** it negates only an Encounter's Morale Loss at ⑦.
    It does not cover posture effects and cannot bypass the Minimum.
15. **"Once per battle" in multi-day battles** (Force and Negate tokens, each
    Opportunity). Passions are already per day. **Rec.:** tokens expire at day end,
    since commanders roll again each day (scenario-rule extension). Opportunities stay
    once per battle (RAW), so a spent card stays spent on later days.
16. **Alone on the Field fight.** The tracker holds one active combat: a separate fight
    would abandon the conroi's fight. **Rec.:** put the alone knight's foes in their own
    lane in the same tracker, tagged "Alone" (P6 d5's "separate small fight" becomes a
    lane).
17. **"Enemy knights charge you!" eligible cards.** **Rec.:** encounters with a foe
    that is both `mounted` and `countercharge` (knights, sergeants, prickers). If none
    is in the deck, treat it as a simple failure (P4 d4).
18. **Card and Opportunity text in the tracked baseline.** **Rec.:** short paraphrases
    (as P9 K4 does for scripts). The user may paste the full text into their own
    `combat.json`.
19. **Getting fixes, Opportunities and examples into `combat.json`.** The app loads the
    baseline only when `combat.json` is absent. **Rec.:** an "Add missing examples"
    action that inserts absent keys only (never overwrites), and a separate
    user-confirmed targeted repair of Knights of Lothian.
20. **Unconditional turn scripts on the board.** Piece 5 reveals only "if Intensity
    succeeds" scripts. **Rec.:** others stay GM-only, with a "Show on Table" button per
    script (public event).
21. **Morale word bands.** **Rec.:** by fraction of start: Steady > 75 %, Shaken > 50 %,
    Bloodied > 25 %, Breaking ≤ 25 %.
22. **Conroi membership.** **Rec.:** a Mustering checklist defaulting to active Party
    knights, editable at each muster (logged).
23. **Morale Minimum/Loss defaults for mixed rosters.** **Rec.:** default Minimum =
    highest card Minimum and Loss = the first card's, both editable.
24. **Surrender −5 from pills.** RAW gives the Surrender check −5 if on foot vs a
    mounted PK. **Rec.:** apply it automatically from the Mounted pills (cheap, RAW).
25. **Does the "+1 round" (Energetic+Valorous) count toward reaching archers?**
    **Rec.:** yes (rounds + extra > barrage), matching the corpus example's result. File
    a corpus check of the example's wording.
26. **Outcome ratio gaps** (RAW bands skip 0.4–0.5, 1.9–2, 3.9–4). **Rec.:** thresholds
    ≥4 Decisive Victory / ≥2 Victory / ≥0.5 Indecisive / ≥0.25 Defeat / below Decisive
    Defeat.
27. **Who "fought ≥1 Encounter" on a day.** **Rec.:** derived as "with the conroi at ⑨
    in any fight that day and not Cowardly", editable in the aftermath.
28. **Knights' Mounted default in plain fights.** **Rec.:** a "Knights mounted" toggle
    on the Combat launcher, default on. In battles the day's switch decides (P4 d6).
29. **Turn-1 charge roll when the first charge is off** (friendly failure/fumble or the
    switch). RAW: the Table 6.3 roll happens "except turn 1". **Rec.:** step ③ is
    always skipped on turn 1. With the first charge off, turn 1 has no charge.
