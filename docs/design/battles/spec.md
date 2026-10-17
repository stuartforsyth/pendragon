# Battles — build spec (stage 4)

Status: **draft, awaiting approval**, written 2026-10-17.

The spec is built from these sources, in this order of authority:

1. `pieces/01–09` (the user's decisions)
2. `design.md` (APPROVED, §13 all Rec. = decisions; §14 UX pass APPROVED)
3. `mockups/battles-ux-mockups.html` (APPROVED: the build must match it) and `mockups/walkthrough.md`
4. the code as it stands at `ec919a0`

Each slice can ship on its own and follows design.md §10. Where the code or the sources disagree, the
spec follows the order above, and the **Open points** section at the end lists each case.

Mockup frames are cited by their id in `battles-ux-mockups.html`:

| Frame id | Screen |
|---|---|
| `#gm-turn` | GM turn stepper |
| `#gm-muster` | Mustering |
| `#gm-fight` | Combat tracker |
| `#gm-after` | Aftermath |
| `#t-battle` | Table battle view |
| `#t-fight` | Table fight view |
| `#t-finale` | Table finale |

Screens with no mockup (the Battles editor, launch panel, settings drawer, Encounters battle fields,
examples dialog) follow design.md §6 and reuse existing patterns.

---

## 0. Conventions (apply to every slice)

**Events**
- Names: `battle.*` for battle state, `combat.*` for any fight, and `glory.*` for the Glory ledger. Every
  event is appended through `AppState.record()`. Events are never edited. Undo is done by `meta.strike` /
  `meta.unstrike`.
- Every battle-linked event carries `data.battle = {"id": str, "day": int, "turn": int, "step": str|null}`.
  The step keys are, in order:
  `field`①, `set`②, `charge`③, `intensity`④, `picks`⑤, `select`⑥, `morale`⑦, `postures`⑧, `fight`⑨, `end`⑩.
  Events outside the stepper (muster, settings, adjust…) use `step: null`.
- **Entered values only.** An event stores the amount, outcome, pick, posture, award, pill or position.
  It never stores a capped or derived result. "Roll for me" rolls in the route through `core.dice` and
  stores the number as the entered amount (with `rolled: true`). Reducers never roll.
- **Card snapshots for replay determinism** (*implementation choice*, nothing the user sees):
  `battle.deck`, `battle.set`, `battle.pick` and `battle.select` carry
  `card = {role, description, morale_minimum, morale_loss, missile, countercharge, mounted_charge, has_roster, rules}`
  for each encounter they name. The reducer reads the card from the event, never from the library, so
  editing the library later can't change a replayed battle. `card` is never in `_SAFE_DATA`.
- Every **public** event sets `data.table_text`, and `data.table_title` when the GM title isn't
  player-safe. `web/table.py` falls back to the GM `text` when `table_text` is missing, so a missing
  `table_text` would leak GM text. A test asserts this for every public `battle.*` / `glory.*` event (S7).
- Events about a knight carry `data.touches = [party_id, …]`. `table.py` reads it server-side to build
  the knight's "LAST" line, and it is never sent to the Table.

**Where rules live**
- **`core/battle.py`** holds every battle rule as a pure function or table, and each one cites its
  corpus id in its docstring. Pure tests go in `tests/test_battle.py`.
- **`core/battle_def.py`** holds the shapes of saved battle definitions (blank, quick, clean).
- **`core/combat.py`** gets the new Combatant fields.
- **Reducers** apply the rules on replay: `web/combat_state.py` for every fight and `web/battle_state.py`
  (new) for battles.
- **Routes** validate the request, roll "roll for me" dice, build `text` / `table_text`, and record.
- The UI labels departures from the book. Scenario rules show `<span class="tag or rule-sr">Scenario rule</span>`
  and GM rulings show `<span class="tag purpure rule-gr">GM ruling</span>`, each with a hover title giving
  the book rule they replace.

**One outcome-capture entry point.** Every outcome a player reports (charge, Intensity, picks,
selection, Loss, postures and their amounts, rest, barrage, countercharge, extra round, end turn/day)
goes through `POST /api/battle/step`. The route dispatches to `web/routes/battle.py: record_outcome(state, step, payload, source="gm")`.
A future dice source calls `record_outcome` with `source="dice"`. `source` is stored in `data.source`,
which is an invisible *implementation choice*. Combat attack and blow capture keeps its existing routes.

**Secret filtering.** The Table sees only `web/table.py` output:
- event cards, filtered by `_SAFE_DATA`
- `combat_state.serialise(…, "table")`
- `battle_state.table_view()`

Each slice that adds data the players must not see adds a test asserting that the secret is absent from
`GET /api/table` (the raw response text).

**Tests**
- Web tests use the HTTP `client` fixture, which runs against copies of `rules.json` and
  `examplecombat.json` in `tmp_path`, with sessions in `tmp_path/sessions`.
- *Implementation choice:* S0 moves the duplicated `client`/`ok` fixtures from `test_web.py`,
  `test_web_misc.py` and `test_web_library.py` into `tests/conftest.py`, and new files reuse them.
- The session-scoped `rules` fixture in `conftest.py` loads `ROOT/data`, which is the **user's**
  `combat.json`. Data assertions must load `data/examplecombat.json` explicitly instead.
- Run the suite with `.venv/bin/python -m pytest -q`. The whole suite must pass after each slice.

**Throwaway instance (acceptance checks)**
```bash
T=$(mktemp -d); mkdir -p $T/data $T/sessions
cp data/rules.json data/examplecombat.json $T/data/         # baseline only
cp data/combat.json data/party.json $T/data/ 2>/dev/null    # optional: the user's content, copied
PENDRAGON_DATA_DIR=$T/data PENDRAGON_SESSIONS_DIR=$T/sessions .venv/bin/python -m web --port 8021
```
Open `http://127.0.0.1:8021/` (GM) and `/table` (Table, 1280×720 window).

**UX acceptance per slice** (design-mechanic stage 5):
1. Put the throwaway instance in a realistic state, using the real party copied in.
2. Screenshot the GM console at 1440×900 and the Table at 1280×720.
3. Compare the screenshots with the cited mockup frames and fix what differs or reads badly.
4. Show the screenshots to the user before calling the slice done.

**Docs:** each slice updates `docs/web-app.md` (its Events list and Combat section) and ticks itself off
in this file.

**Shared GM components.** These are built once in `web/static/js/components.js` (new), with their CSS
in `web/static/css/tools.css`:

| Component | Signature | First slice | Behaviour |
|---|---|---|---|
| Outcome chips | `outcomeChips({value, onPick, rollForMe?, keys: true})` | S6 | Crit / Success / Fail / Fumble. C/S/F/X keys while the owning step is open. |
| Amount entry | `amountEntry({dice, min, max, onEnter, rollForMe})` | S6 | A number field (Enter submits) plus a "roll for me (1D6)" button. |
| Deck picker | `deckPicker({decks, selected, onChange, tabs})` | S5 | Foes / Opportunities tabs, checklist rows with GM-only Min / Loss / KV columns. |
| Morale strip | `moraleStrip(view, {onAdjust, onCommander, onToken})` | S6 | — |
| Knight chip | `knightChip(k, {onMounted, onPosition})` | S6 | Shield, name, Mounted pill, position, posture. |
| Day card | `dayCard(day, size, {readOnly, onChange, decks})` | S6 | — |

**Reusable Table components (piece 8).** Feasts and hunts will reuse these, so they live in
`web/static/js/board.js` (new ES module imported by `table.js`), with their CSS in
`web/static/css/board.css` (new, linked from `templates/table.html`):

| Component | Renders |
|---|---|
| `knightCard(k, {compact})` | Shield, name, player, a slot for Glory, chips and the LAST line. |
| `gloryCounter(g)` | The big number with a tick animation and "+n · reason". |
| `effectChips(list)` | Effect chips in tones `harm` (gules), `boon` (vert) and `state` (grey). |
| `happenedLine(items)` | The "LAST" line. |
| `moraleGauge(m, {compact})` | The Morale gauge. |
| `cardFrame(c)` | A battle card: parchment, border, ★ for Opportunities, shield token. |

The server builds every knight-card dict (`web/table.py: knight_cards()`). The front end only renders it.

---

## S0 — Data fixes, flags, `core/battle.py` rules (size **M**)

**Goal.** The battle cards are correct and carry the new flags. Every battle rule is a tested pure
function. The user can pull new example content into their own `combat.json` without anything being
overwritten.

### Files
| File | Change |
|---|---|
| `core/battle.py` (new) | rules tables and functions (below) |
| `core/examples.py` (new) | `examples_report(working, baseline)`, `merge_missing(working, baseline)`, `restore_entry(working, baseline, kind, key)` |
| `data/examplecombat.json` | fixes below |
| `web/routes/library.py` | 3 routes for examples |
| `web/static/js/tools/encounters.js` | "Examples…" header button + dialog |
| `tests/conftest.py` | hoist `client`, `ok` |
| `tests/test_battle.py` (new), `tests/test_examples.py` (new) | tests |
| *(no corpus change)* | `rules_corpus/` is a read-only symlink to ttrpg-parser (CLAUDE.md). The battle cards and Opportunities (GM pp.143–148) are already queued in ttrpg-parser's rules-issues; card text for `examplecombat.json` is paraphrased from the local PDF. Any new corpus gap found → file a rules-issues entry, never write the corpus. |

### `core/battle.py`
All functions are pure. Fractions use `fractions.Fraction`, and rounding uses `core.rules._rhu` (round half up).

| Name | Signature → result | Rule (corpus id) |
|---|---|---|
| `SIZES` | `{"fight": {label:"Fight", turns:1, intensity:"1D6+2", participation:5, plunder_mult:None, army_rolls:False}, "skirmish": {3,"2D6",5,None,False}, "clash": {5,"2D6+1",10,None,True}, "small": {6,"2D6+2",20,1,True}, "medium": {7,"2D6+3",30,2,True}, "large": {8,"3D6",45,3,True}, "huge": {8,"3D6+1",60,4,True}}` | Tables 6.1/6.6/6.10 (gm.battle.running-a-battle, after-the-battle, plunder-and-encounters) |
| `OUTCOMES` | `("critical","success","failure","fumble")` | |
| `army_effects(side, outcome)` | `friendly`: crit/success → `{"first_charge": True}`; failure → `{"first_charge": False}`; fumble → `{"first_charge": False, "minus5": True}`. `enemy`: crit/success → `{"force_token": True}`; fumble → `{"negate_token": True}`; failure → `{}` | running-a-battle |
| `DEFAULT_BATTLE` | `"2D6+10"` | running-a-battle |
| `TABLE_6_2` | list of `{label, mod}` rows for the ticklist | running-a-battle |
| `charge_opportunity(outcome, engaged_last)` | `"may_charge_plus5"` (crit, unengaged) · `"may_charge"` (crit engaged; success unengaged) · `"no_charge"` (success engaged; failure) · `"enemy_charge"` (fumble) | Table 6.3, gm.battle.fighting-the-battle |
| `charge_line(result, mounted)` | one per-knight line: `"Charges +5"`, `"May charge"`, `"No charge"`, `"On foot — no charge"`, `"Enemy knights charge!"`, `"Charged on foot — enemy +5 Height; Set Spear possible"` | Table 6.3, gm.battle.countercharge, core.combat.action-set-spear |
| `POSTURES` | `{"reckless": {rounds:3, dice:"1D3", sign:+1}, "valorous": {2, None, 0}, "prudent": {1,"1D3",-1}, "cowardly": {0,"1D6",-1}}` | fighting-the-battle |
| `FIRST_CHARGE_POSTURES` | `("reckless","valorous")` | fighting-the-battle |
| `posture_delta(posture, amount, above_half=False)` | R +amount; V 0; P −amount; C −amount if `above_half` else 0. Raises `ValueError` if amount is out of the die's range | fighting-the-battle |
| `intensity_result(outcome)` | `"doubled"` / `"stands"` / `"opportunity"` / `"choose"` | fighting-the-battle |
| `barrage_rounds(outcome)` | crit 0, success 1, failure 2, fumble 3 | fighting-the-battle |
| `reaches(rounds, extra, barrage)` | `rounds + extra > barrage` (Q25) | fighting-the-battle (worked example) |
| `countercharge(first_turn_of_day, roll)` | `True` if first turn (**scenario-rule extension**), else `roll in (1, 2)` | gm.battle.plunder-and-encounters |
| `height(foe_mounted, knight_mounted, override=None, attacks_horse=False)` | `(foe_mod, knight_mod)`. Override `"none"` → (0,0). Foe up, knight down → (+5,−5). Knight up, foe down → (0,+5) if `attacks_horse`, else (−5,+5). Level → (0,0) | core.combat.combat-modifiers, core.combat.action-attack |
| `multiple_opponents(n)` | `0` if n ≤ 1, else `-5*(n-1)` | core.combat.multiple-opponents |
| `mo_limit(attackers_mounted)` | `2` if any attacker is mounted, else `3` (see Open point 10) | core.combat.multiple-opponents |
| `parse_kv(s)` | `Fraction`: `"1"`, `"½"`, `"¼"`, `"⅛"`, `"¾"`, `"1/16"`, `"3/4"`, `""`→0 | gm.battle.after-the-battle |
| `kv_total(kvs)` | `Fraction` sum | after-the-battle |
| `kv_morale_gain(per_encounter)` | `Σ _rhu(sum(kvs))` over a list of per-encounter KV lists (Q3, **GM ruling**) | fighting-the-battle |
| `outcome(enemy_kv, friendly_kv, outnumber)` | `outnumber` ∈ `none\|we\|they` (×2 / ×½). If `friendly_kv == 0`: enemy > 0 → `decisive_victory`, both 0 → `indecisive` (**GM ruling**). Otherwise the ratio uses thresholds ≥4 / ≥2 / ≥0.5 / ≥0.25 (Q26) | after-the-battle |
| `OUTCOME_LABEL`, `OUTCOME_MULT` | DV ×2, V ×1½, I ×1, D ×¾, DD ×½ | Table 6.7 |
| `LEADER_MULT` | conroi 2, bataille 3, army 5 | Table 6.8 |
| `conroi_losses(outcome, n_gm_knights)` | `{"killed", "captured"}`, half-up of n × (0/0, 0/10%, 10%/10%, 30%/20%) | Table 6.5 |
| `participation_glory(size, days, outcome, role)` | `_rhu(base × days × (OUTCOME_MULT + (LEADER_MULT[role] if role and size not in ("fight","skirmish") else 0)))`. "× days" is a **scenario rule** | Tables 6.6–6.8 |
| `PLUNDER_BASE` | `feudal 2, inferior 1.5, saxons 1, cymric 0.5, picts_irish 0.25` | Table 6.9 |
| `plunder(opponents, outcome, decisive_roll, outnumber, role, size)` | Returns `Fraction` £ per knight. 0 unless V/DV. Base (+2D3 roll on DV), then ×½ (`we`) / ×2 (`they`), then role: conroi ×4/3; bataille ×3×mult; army ×10×mult. With no size multiplier (below Small), bataille and army fall back to conroi (Open point 13) | Tables 6.9–6.10 (Q8) |
| `DEFEATED` | `{"unconscious","dead","fled","surrendered"}` | Table A.1 (gm.glory-awards.combat-and-adventure) |
| `is_defeated(status)`, `glory_for(c)` | `glory_for` returns `int(c.glory)`, which is already ×promotion | Table A.1 |
| `apply_morale(current, start, delta)` | `max(0, min(start, current + delta))` | running-a-battle (Q1/Q13) |
| `morale_band(current, start)` | Steady > 75 % · Shaken > 50 % · Bloodied > 25 % · Breaking (Q21) | — |
| `scale_roster(defn, n_knights, doubled)` | `resolve_roster(defn, n)` with each count ×2 when doubled (Q5) | Intensity crit |
| `forced_retire(morale, minimum)` | `morale == 0 or morale < (minimum or 0)` | running-a-battle; battlefield-position-and-surrender |
| `default_morale(defn, adversaries)` | `(highest card morale_minimum, first card's morale_loss)` (Q23) | cards |
| `mounted_charge_card(defn, adversaries)` | Any roster adversary that is both `mounted` and `countercharge` (Q17) | — |
| `has_countercharge(defn, adversaries)` | Any roster adversary with `countercharge` | plunder-and-encounters |
| `leader_default(commander_by_day)` | The party id that commanded most days (ties go to the earliest), or None (Q7) | — |

### `data/examplecombat.json` (tracked baseline). Exact changes:
| Entry | Change |
|---|---|
| `adversaries["Irish Kerns"].other` | `armor_points: 4 → 0`, `shield: 0 → 4`; `armour_desc` says Targe, "unarmored" |
| `adversaries["Cambrian Archers"]` | text "a third injured" → "seriously injured" (in `description`/`notes`) |
| `adversaries` Gorre, Lothian, Malahaut, Cornwall, Breton Mercenary Knights, Northern Prickers, **Mounted Sergeant** | `"mounted": true` (other knights left to the GM, §2.3) |
| the five knight cards, Northern Prickers, Mounted Sergeant | `"countercharge": true` |
| `adversaries["Pictish Knifemen"]` | `"attacks_horse": true` |
| all 12 battle-card adversaries | `description` = a Table-safe flavour paraphrase; `notes` = card special rules + weapon footnotes as a paraphrase (Q18), from `battlecards.pdf` |
| the 12 battle-card **encounters** | Rewritten in roster shape (`to_editable` output: `roster: [{adversary, count: <per_player>, per_player: true, promote: false}]`, `leader: null`) plus `battle_role: "foe"`, the existing `morale_minimum`, `morale_loss` = the card's `other.morale_loss`, `missile: true` on **Cambrian Archers** and **Pictish Javeliniers**, `rules: ""`, `description` = the adversary's flavour line, `tags: ["battle-card"]` |
| 5 new **Opportunity** encounters (names from `battlecards.pdf`: Clash of Champions, Rally the Division!, Rescue Captive Knights, + 2) | `{"name", "description", "tags": ["battle-card","opportunity"], "battle_role": "opportunity", "morale_minimum": n, "morale_loss": "…"\|"", "rules": "<paraphrase>", "roster": [] or lines, "leader": null, "notes": ""}` |

Example battles are **not** in S0 (Open point 6). They ship in S11.

### Examples merge (Q19). The user's `combat.json` is never overwritten wholesale.
- `examples_report(working, baseline)` returns:
  - `{missing: {adversaries:[k], encounters:[k], battles:[k]}, fields: [{kind, key, fields:[…]}], differs: [{kind, key, fields:[…]}]}`
  - `fields`: top-level keys (and keys inside `other`) that a same-named baseline entry has and the
    working entry lacks. It skips `roster`, `core`, `scaling` and `per_player`.
  - `differs`: baseline entries with `battle_card: true` or `battle_role` whose shared keys differ in value.
- `merge_missing(working, baseline)` inserts the missing entries and missing fields only. It returns the counts.
- `restore_entry(working, baseline, kind, key)` replaces **one** entry with a deep copy of the baseline.
  The user confirms each one.

### Routes (`web/routes/library.py`)
| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| GET | `/api/library/examples` | — | `examples_report(...)` | — |
| POST | `/api/library/examples/merge` | `{}` | `{added: {adversaries:n, encounters:n, battles:n, fields:n}}` | — |
| POST | `/api/library/examples/restore` | `{kind: "adversaries"\|"encounters", key}` | `{key, entry}` | 404 if not in the baseline |

Both POSTs write `state.save_combat_data()` (which writes `combat.json`) and then call `state.notify("library")`.

### UI: Encounters tool (`encounters.js`, `css/tools/encounters.css`)
- The header gets an **"Examples…"** button that opens a modal with three sections:
  - "New in the app's examples" (counts and names) with **Add missing**
  - "New fields for your cards" (e.g. "Knights of Gorre: mounted, countercharge")
  - "Cards that differ from the shipped card", one row each with **Restore shipped card**. Each
    restore asks first: "Replace your Knights of Gorre with the shipped card? Your edits to it are lost."
- When there is nothing to add, the modal shows "Your library has everything."

### Tests
**`tests/test_battle.py`** (pure):

| Test | Asserts |
|---|---|
| `test_sizes_table` | `SIZES["large"]["turns"]==8`, intensity `"3D6"`, participation 45; fight/skirmish `army_rolls` False |
| `test_charge_opportunity_table` | all 8 cells of Table 6.3 |
| `test_charge_lines_for_foot_knights` | |
| `test_posture_delta` | R+, P−, C only when above half, ranges raise |
| `test_barrage_and_reach` | `reaches(1,0,2)` F, `(2,0,2)` F, `(3,0,2)` T, `(2,1,2)` T, `(1,0,0)` T |
| `test_countercharge` | first turn True regardless of roll; rolls 1,2 True, 3–6 False |
| `test_height_cases` | the six combinations, including attacks-horse and override |
| `test_multiple_opponents_and_limit` | |
| `test_parse_kv_glyphs` | |
| `test_kv_morale_gain_rounds_half_up_per_encounter` | `[⅛]*3` → 0; `[⅛]*4` → 1; `[1,⅛,⅛,⅛]` → 1; two encounters `[[⅛]*4, [⅛]*4]` → 2 |
| `test_outcome_thresholds_and_zero_ruling` | 4 → DV, 3.9 → V, 2 → V, 0.45 → D, 0.5 → I, 0.2 → DD, `we` doubles, (5,0) → DV, (0,0) → I |
| `test_conroi_losses` | `("fumble",10)` → killed 3 / captured 2 |
| `test_participation_glory` | `("large",2,"victory",None)` → 135; `("clash",1,"victory","conroi")` → 35; `("skirmish",1,"victory","conroi")` → 8, leader ignored |
| `test_plunder` | `("feudal","victory",None,"none",None,"large")` → 2; DV with roll 4, `we`, conroi → 4; defeat → 0; bataille on Large ×3×3 |
| `test_apply_morale_caps_and_floors`, `test_morale_band_edges`, `test_scale_roster_doubles_resolved_count` | the last one: Lothian 1.5 × 3 → 5, doubled → 10 |
| `test_forced_retire`, `test_default_morale_mixed_roster`, `test_mounted_charge_card` | |

**`tests/test_examples.py`:**

| Test | Asserts |
|---|---|
| `test_baseline_cards_fixed` | Loads `data/examplecombat.json` directly: Kerns armour 0 / shield 4; flags on the listed cards; 12 foe encounters have `battle_role` "foe" and roster shape; Archers and Javeliniers `missile`; 5 opportunities |
| `test_every_baseline_encounter_builds` | Builds every baseline encounter, Opportunities with an empty roster excepted, via `Encounter.generate_from_definition` |
| `test_merge_inserts_absent_only` | A working dict missing a card and a flag gains them; an existing differing value is untouched |
| `test_merge_skips_roster_on_legacy_encounters` | |
| `test_restore_replaces_one_entry` | |

**Web:**
- `test_examples_routes_write_working_copy_only`: merge in the client, then `combat.json` exists in tmp and `examplecombat.json` is byte-identical.

Existing tests must still pass. `test_every_library_encounter_builds` uses the user's data and is untouched.

### Acceptance
1. Run the throwaway instance with the user's `combat.json` copied in, open Encounters → Examples….
2. Check that the 5 Opportunities and the new flags are listed. Add missing, then reopen: "everything".
3. Check that the copied `combat.json` gained keys only (`git diff --no-index` against the original copy).
4. UX acceptance: no mockup exists for this dialog. Screenshot it and check it against the existing modal style.

---

## S1 — Tracker redesign: lanes by knight, type headers, one-line foes, Defeated strip, retarget, `surrendered` (size **L**)

**Goal.** Every fight reads as one lane per knight. Each knight's foes sit under them, a shared stat
header shows per foe type, every foe takes one line, and defeated foes collapse into a strip. Foes can
be retargeted by dragging or with their target chip.

### Files
| File | Change |
|---|---|
| `core/combat.py` | `Combatant`: status `surrendered`; class-level defaults for the new fields (below) so old snapshots replay; `set_out` accepts `"surrendered"`; `status` returns `"surrendered"` for foes; `wound_state` returns `"Surrendered"` |
| `web/routes/combat.py` | `_STATUS_TEXT["surrendered"] = ("{n} surrenders", "{n} surrenders")`; knights still reject everything but `None`/`unconscious`/`fled` |
| `web/combat_state.py` | `serialise(...)`: add `types` (GM: one entry per foe type, `{type, characteristics, attacks, armour_text, notes_text}` deduplicated from `_descriptions`), `gm_notes` (GM), `defeated: [cid]`, `pool: [cid]`. `engaged_by` stays |
| `web/static/js/tools/combat.js` | rewrite `running()` / `row()` into lanes (below); remove the Knights/Foe blocks and the "Descriptions & mechanics" panel |
| `web/static/css/tools/combat.css` | new classes `.cbt-lanes .cbt-lane .cbt-lane-head .cbt-types .cbt-type .cbt-foe .cbt-foe.open .cbt-target .cbt-pool .cbt-defeated .drop-ok` |

Class-level defaults on `Combatant`, added now so S2/S3 don't touch `from_dict`:
```python
mounted = False; attacks_horse = False; height_override = None; countercharge = False
captured_by = None; defeated_with = ""; posture = None; rounds = None; extra_rounds = 0; position = None
```

### Events
`combat.status` accepts `data.out ∈ {null, "unconscious", "dead", "fled", "surrendered"}` (foes only).
`combat.engage` is unchanged and is used for retargeting, with `with: ""` meaning the pool.

### UI (matches `#gm-fight` without the battle frame, which arrives in S8)
- **Header (sticky):** encounter name, `Round n`, **Next round**, **+ Add**, **End fight**, standing
  counts, round-note input. The existing behaviour is kept and **End** is renamed **End fight**.
- **GM notes ▸**: one collapsed `<details>` line, shown only if the encounter has notes.
- **Type headers**: one block per foe type present, shown above the lanes:
  - type name; `SIZ · DEX · STR · CON` (each clickable to roll); attacks `Dagger 15 (2D6+3)` (clickable);
    `Armour n`; the card's short rules; **ⓘ** popover with the deduplicated description and notes.
  - Clicking an attack or characteristic with exactly one active foe of that type rolls for that foe.
    With several, it opens a menu of the active foes, each with its effective value (Open point 11).
    An attack roll then runs the existing `attackDialog` against the foe's engaged knight.
- **Lanes**: one per knight (`side == "party"`) in party order.
  - **Lane header:** shield, knight name, player, `Down` / `Out` buttons (existing status posts). The
    slots for Mounted pill, MO chip (S2), Glory (S3) and posture/rounds/position (S8) render empty until
    those slices land.
  - **Lane body:** the foes whose `engaged_with == knight.display_name` and whose status is active.
- **Foe line** (one line):
  - marker + name (click toggles `.open`); HP bar with `cur / max` numbers; wound word; a chips slot (S2);
    **target chip** `→ Sir Erik ▾` (menu: each knight + "Not engaged" → `POST /api/combat/{cid}/engage`);
    **Hit** (existing `hitDialog`); **±HP** input (Enter → `/hp`; the separate Apply button is removed);
    **⋯** menu.
  - The ⋯ menu holds: Promote/Demote · Knock out/Revive · Slay · **Surrenders** (`out:"surrendered"`) ·
    Deactivate (fled) · Surrender check · Roll ransom · Remove.
  - The expanded line shows the full stat line (existing `statLine`), armour/looks (existing `flavour`),
    and the **Mod** input (existing `combat.modifier`).
- **Not engaged (pool)**: compact chips for active foes with no matching knight, with the hint "drag onto
  a knight, or click to assign". Clicking a chip opens the target menu.
- **Drag & drop**: foe lines and pool chips are `draggable`. Lanes and the pool are drop targets
  (`.drop-ok` highlight). A drop posts `engage` with the lane knight's `display_name` or `""`. Nothing is
  posted when the target doesn't change.
- **Defeated strip**: one line per foe with status in `DEFEATED`: icon (✝ slain, ⇢ fled, ⚐ surrendered,
  ☾ unconscious) · name · fate word · a slot for the Glory credit (S3) and captured (S2). Clicking it
  opens a menu with Revive / Reactivate (the existing status posts), plus S2/S3 items.
- **No knights** (Knights-join unchecked): there are no lanes, and every active foe is in the pool.
- **States:**
  - empty fight: "No foes — add some."
  - all foes defeated: lanes show "No foe engaged"
  - ended: the launcher shows "Last combat" (existing)

### Tests
| Test | File | Asserts |
|---|---|---|
| `test_surrendered_status_and_word` | `test_combat.py` | `set_out("surrendered")` → status `"surrendered"`, `down`, wound word `"Surrendered"` |
| `test_old_snapshot_without_new_fields_replays` | `test_combat.py` | `Combatant.from_dict` of a dict lacking `mounted` etc. gives the defaults and `to_dict` round-trips |
| `test_foe_can_surrender_knight_cannot` | `test_web_tracker.py` (new) | foe 200; knight `{"out":"surrendered"}` → 400; Table wound word "Surrendered" |
| `test_retarget_to_pool_and_lane` | | engage to knight, then `""` → gm view `pool` contains the cid |
| `test_types_deduplicated_in_gm_view_only` | | gm `types` has one entry per foe type; `/api/table` has no `types` / `gm_notes` |

Existing `test_web.py` combat tests keep passing unchanged.

### Acceptance
1. Launch "Knights of Gorre" for a party of 3.
2. Drag foes between lanes and the pool, mark one surrendered and one slain, and confirm both move to the Defeated strip.
3. Strike the slain event in the log and confirm the foe returns to its lane.
4. UX acceptance against `#gm-fight` (no battle frame yet).

---

## S2 — Mounted pill, automatic Height, attacking the horse, Height override, MO chip, captured, surrender −5 (size **M**)

**Goal.** Height ±5 is applied to foes' attack rolls automatically from the engaged pair's pills. Knights
see their own modifiers as reminder chips. Multiple Opponents is warned about, and captives are flagged.

### Files
| File | Change |
|---|---|
| `core/combat.py` | `Combatant.__init__`: `self.mounted = bool(template.get("mounted"))`, `self.attacks_horse = bool(template.get("attacks_horse"))`, `self.countercharge = bool(template.get("countercharge"))`; `from_party(member, mounted=True)` sets `mounted`; `surrender_check(c, roll=None, modifier=0)` (−5 applied to the value; the line says "(−5 on foot vs a mounted knight)") |
| `web/combat_state.py` | `COMBAT_STATE_TYPES` += `combat.mounted`, `combat.horse`, `combat.height`, `combat.captured`; refactor to `apply(state, ev)` + `reduce()` loop (design §3.3); `gm_view`/`table_view` add the fields below |
| `web/routes/combat.py` | `start` accepts `knights_mounted` (default `True`, Q28) → `Combatant.from_party(m, mounted=...)`; new routes; `roll` adds Height to `what == "attack"`; `surrender` passes the −5 |
| `web/routes/library.py` | none (`A.finalise` already keeps unknown keys) |
| `web/static/js/tools/adversaries.js` | "Battle flags" row in the stats panel: checkboxes **Mounted by default**, **Countercharges (lance)**, **Attacks the horse first** → `d.mounted`, `d.countercharge`, `d.attacks_horse` |
| `web/static/js/tools/combat.js` | launcher toggle **Knights mounted** (default on); lane-header Mounted pill + MO chip; foe-line chips; ⋯ items; Defeated strip "captured by" |
| `web/static/css/tools/combat.css` | `.pill-mounted .chip-height .chip-horse .chip-mo.warn .tag-captured` |

### Events
| Type | Vis. | `data` | Reducer |
|---|---|---|---|
| `combat.mounted` | public | `{cid, mounted: bool, table_text, touches?}` | `c.mounted = mounted` (any combatant) |
| `combat.horse` | public | `{cid, on: bool, table_text}` | `c.attacks_horse = on` |
| `combat.height` | public | `{cid, override: null\|"none", table_text}` | `c.height_override = override` |
| `combat.captured` | public | `{cid, by: party_id\|null, table_text, touches}` | `c.captured_by = by` |

`roll.check` from `/api/combat/{cid}/roll` with `what=attack` gains `data.height` (−5/0/+5) and folds it
into `modifier`. The `text` notes the change, e.g. "(Height −5)".

### Derived fields
Computed in `serialise`, never stored. The engaged knight is the party Combatant whose `display_name == foe.engaged_with`.
- foe `height = {"foe": f, "knight": k}` from `core.battle.height(foe.mounted, knight.mounted, foe.height_override, foe.attacks_horse)`.
  It is zero when the foe isn't engaged with a knight.
- knight `mo = {"n": n, "mod": multiple_opponents(n), "limit": mo_limit(any attacker mounted), "over": n > limit}`, where n counts active foes engaged with the knight.
- knight `height_chips = [{"foe": name, "mod": k}]` for each engaged foe with a non-zero `knight` mod.

### Routes (`web/routes/combat.py`)
| Method | Path | Body | Event | Errors |
|---|---|---|---|---|
| POST | `/api/combat/start` | + `knights_mounted: bool` (default true) | `combat.started` (knight snapshots carry `mounted`) | as today |
| POST | `/api/combat/{cid}/mounted` | `{mounted: bool}` | `combat.mounted` | 409 no combat; 404 cid; no-op returns `{event: null}` |
| POST | `/api/combat/{cid}/horse` | `{on: bool}` | `combat.horse` | 400 if the cid is a knight |
| POST | `/api/combat/{cid}/height` | `{override: null\|"none"}` | `combat.height` | 400 bad value or knight |
| POST | `/api/combat/{cid}/captured` | `{by?: party_id\|null}` (omitted = engaged knight) | `combat.captured` | 400 knight target; 400 foe not `unconscious`/`surrendered`; 400 no engaged knight and no `by` |
| POST | `/api/combat/{cid}/roll` | unchanged | `roll.check` + `data.height` | — |
| POST | `/api/combat/{cid}/surrender` | unchanged | `combat.check` (−5 when the foe is on foot and its engaged knight is mounted, Q24) | — |

### UI (matches `#gm-fight` lanes)
- **Launcher**: a checkbox "Knights mounted" under "Knights join the fight" (default on), posted as `knights_mounted`.
- **Lane header**:
  - **Mounted / On foot** pill (click → `/mounted`, toggles)
  - **MO chip** `⚠ 2 foes · −5 vs each` (hidden at n ≤ 1; `.warn` + title "More than 3 on foot / 2 mounted can't all attack one knight" when over)
  - knight reminder chips `+5 Height vs Gorre 1` (vert) or `−5 Height` (gules)
- **Foe-line chips**:
  - Height chip: `−5 Height (she is mounted)`, `+5 Height`, or `Height: none (both on foot)` /
    `Height: none` when cancelled. Click opens the override menu: Auto / "Negated (two-handed spear or halberd)".
  - Horse toggle `⇣ horse`, shown only when the engaged knight is mounted (on = filled) → `/horse`.
- **⋯ menu additions:** Mounted/On foot (foe pill) · Attacking the horse · Height override… · Captured by… (knight submenu; only for unconscious/surrendered).
- **Defeated strip:** `captured by Sir Bors` tag; menu item "Captured by…" / "Release" (`by: null`).
- **Table** (`table_view`): foes gain `mounted`, `height_chip` (e.g. `"+5 Height"`, `"Height: none"`; no
  other numbers) and `captured_by_name`. Knights gain `mounted` and `mo_mod`. S3 renders them.
- **Adversary editor:** the "Battle flags" row is shown for every category.

### Tests (`tests/test_web_tracker.py`)
| Test | Asserts |
|---|---|
| `test_knights_mounted_default_and_off` | default `mounted` True on knight snapshots; `knights_mounted:false` → False |
| `test_height_applied_to_foe_attack` | Gorre (mounted) engaged with an on-foot knight → `roll.check.data.height == 5`; a Bandit (foot) vs a mounted knight → −5; `combat.horse on` → 0; `combat.height "none"` → 0; unengaged → 0 |
| `test_height_not_applied_to_characteristic_rolls` | |
| `test_surrender_minus5_from_pills` | |
| `test_mo_chip_counts_and_limit` | 3 foot foes on one knight → mod −10, limit 3, not over; 4 → over; mounted attackers → limit 2 |
| `test_captured_defaults_to_engaged_knight` | and is rejected on an active foe |
| `test_table_shows_height_chip_not_numbers` | `height_chip` present; no `cur_hp` / `max_hp` / `attacks` |
| `test_adversary_editor_keeps_flags` | PUT a draft with the three flags, then GET → flags kept |

Existing tests: `test_enemy_attack_on_knight` is unaffected because `_start_with_knight` never engages the foe.

### Acceptance
1. Launch Pictish Knifemen against 3 mounted knights and engage the foes.
2. Check that Knifemen show `Height: none` with the horse toggle on. Flip one knight's pill and watch the chips change.
3. Roll a foe attack and check that the log line shows the Height modifier.
4. UX acceptance against `#gm-fight` (chips, pill, MO warning).

---

## S3 — Glory ledger + Table fight view with reusable knight cards (size **L**)

**Goal.**
- Glory for each defeated foe goes automatically to the knight it was engaged with when it fell.
- A "Who defeated them?" prompt covers foes that fell while unengaged.
- Credits can be reassigned, Glory can be awarded by hand, and every fight keeps a tally.
- The Table fight view mirrors the GM's lanes using the reusable knight-card components.

### Files
| File | Change |
|---|---|
| `web/combat_state.py` | In `apply`, track defeat transitions: when a foe's status goes from not defeated to `DEFEATED`, set `c.defeated_with = c.engaged_with`; when it leaves `DEFEATED`, clear it. Fold `glory.reassigned` (`state["credits"][cid] = knight`) and `glory.awarded` with `data.fight == state["started_event"]` (`state["manual"]`). `serialise`: `glory = {pid: n}` (derived + credits + manual), foe `credit = {"knight": pid, "name", "glory"} \| null`, `uncredited: [cid]` |
| `web/routes/combat.py` | After `/hp`, `/blow`, `/status` and `/attack` record a defeat: if the foe is credited, append " — +50 Glory, Sir Erik" to its `table_text` and add `touches`; if it is uncredited and knights exist, return `"prompt": {"kind": "who_defeated", "cid"}`. New routes below |
| `web/routes/glory.py` (new; registered in `web/app.py`) | `POST /api/glory` |
| `web/table.py` | `knight_cards(session, combat, battle=None)`; `_SAFE_DATA` += `glory.awarded: ("knight_name","amount","reason")`, `glory.reassigned: ("knight_name","foe","amount")`, `combat.mounted: ("mounted",)`, `combat.captured: ()`; `build(...)` adds `knights: [...]` |
| `web/static/js/board.js` + `web/static/css/board.css` (new) | reusable components (Conventions) |
| `web/static/js/table.js` | the fight view (rename `battle(p)` → `fight(p)`) renders lanes with `knightCard` |
| `web/static/js/tools/combat.js` | lane-header Glory; Defeated-strip credit; "Who defeated them?" modal; **Award Glory** button |
| `web/static/js/gm.js` | `KIND`: `glory.*` → `["combat","star"]` |

**Auto Glory is derived (Q10), not stored.** A foe's credit is resolved in this order:
1. the latest `glory.reassigned` for (fight, cid)
2. otherwise the knight whose `display_name == defeated_with`
3. otherwise uncredited

The amount is `core.battle.glory_for(c)`. Striking the defeating event therefore removes the award
exactly. A re-defeat never double-counts. Retargeting after the defeat doesn't move the credit (Q9).

### Events
| Type | Vis. | `data` | Reducer |
|---|---|---|---|
| `glory.reassigned` | public | `{fight: started_event_id, cid, knight: party_id\|null, knight_name, foe, amount, table_text: "+50 Glory · Sir Bors defeated Gorre 2", touches:[pid]}` | sets the credit (both the prompt answer and the reassign) |
| `glory.awarded` | public | `{knight: party_id, knight_name, amount: int (≠0), reason: str, fight: int\|null, battle: {id,day,turn,step}\|null, source: "manual", table_text: "+25 Glory · Sir Erik — seized the standard", touches:[pid]}` | adds to the fight tally if `fight` matches, and to the battle tally (S8) if `battle` is set. It is logged even with no fight or battle |

### Routes
| Method | Path | Body | Response / event | Errors |
|---|---|---|---|---|
| POST | `/api/combat/{cid}/credit` | `{knight: party_id\|null, fight?: int}` | `glory.reassigned` | 404 cid; 400 foe not defeated; 400 unknown knight |
| POST | `/api/glory` | `{knight: party_id, amount: int, reason: str}` | `glory.awarded`; attaches `fight` = the active combat's `started_event` (if any) and `battle` = the live battle link (S6+) | 400 amount 0 / missing reason / unknown knight |
| POST | `/api/combat/{cid}/hp` · `/status` · `/api/combat/blow` · `/attack` | unchanged bodies | response gains `prompt?` | — |

These route shapes differ from design §5's `POST /api/glory/{event_id}/reassign`, because auto awards
have no event id under Q10. See Open point 1.

### UI
- **GM tracker** (`#gm-fight`):
  - Lane header shows `✦ 10 this fight`; in battle fights from S8 it reads `✦ 10 this battle`.
  - Defeated-strip line shows `✦10 Sir Erik`, or a gules **Who defeated them?** button when uncredited.
  - Strip menu: **Reassign Glory…** (knight list + "Nobody") → `/credit`.
  - A route response with `prompt` opens the modal **"Who defeated Gorre 2?"** with one button per knight
    plus "Nobody (no Glory)". "Nobody" posts `knight: null`.
  - Header button **✦ Award Glory**: a modal with knight select, amount, reason (all required) → `/api/glory`.
- **Table fight view** (`#t-fight`):
  - **Header band:** encounter name and `Round n`. The battle/day/turn line and the Morale chip are
    added in S8.
  - **Banner slot:** shows "They go for the horses!" when any active foe has `attacks_horse` on and is
    engaged with a mounted knight. S8 adds countercharge/barrage banners.
  - **Lanes:** each starts with `knightCard(k)`:
    - shield, name
    - `GLORY n`: the fight tally in a plain fight, the battle total in a battle fight
    - effect chips: `On foot` (state), `+5 Height` (boon), `−5 Height` (harm), `−5 two foes` /
      `−10 three foes` (harm); posture chips are added in S8
    - LAST line
  - **Foe tiles:** shield + name + wound word, plus `captured` / Height-horse chips. No numbers.
  - **Footer:** `Defeated: Knifeman 3 slain (✦10 Sir Erik) · Knifeman 8 fled · Waiting: Knifeman 6, Knifeman 7`.
    The pool is shown as "Waiting".
  - The Glory counter ticks with a flourish when it rises: `+10 · Knifeman 3 slain`.
- **Knight-card dict** (built in `table.py: knight_cards()`):
  ```json
  {"pid": "ab12", "name": "Sir Erik", "player": "Ann", "mounted": true,
   "glory": {"value": 20, "scope": "fight"|"battle", "last": {"amount": 10, "text": "Knifeman 3 slain"}|null},
   "effects": [{"key": "height_up", "label": "+5 Height", "tone": "boon"}],
   "happened": ["+10 Glory · Knifeman 3 slain", "Engaged by Knifeman 1", "…"],
   "lane": {"foes": [{"id","name","wound_state","chips":[…]}]}}
  ```
  `happened` holds the `table_text` of up to 3 most recent non-struck public events whose `touches`
  include the pid. The card shows the newest one as **LAST** (Open point 21).
  This slice adds `touches` to `combat.engage` (knight engaged), `combat.blow` with `to_knight`,
  `combat.attack`, a knight's `combat.status`, `combat.mounted`, `combat.captured` and `glory.*`.

### Tests (`tests/test_web_glory.py`, new)
| Test | Asserts |
|---|---|
| `test_auto_glory_to_engaged_knight` | engage, slay → gm `glory[pid] == foe glory`; `/api/table` card text has "+N Glory" |
| `test_strike_removes_auto_glory` | |
| `test_retarget_after_defeat_keeps_credit` | |
| `test_unengaged_defeat_prompts_and_credit_route` | response `prompt.kind == "who_defeated"`; `/credit` → credited; `knight:null` → no Glory |
| `test_reassign_moves_credit` | |
| `test_redefeat_does_not_double_count` | slay → revive → slay |
| `test_manual_award_without_fight` | logged; Table card shows amount and reason; no `fight` |
| `test_manual_award_counts_in_active_fight` | |
| `test_glory_hidden_before_defeat` | foe `table_view` has no `glory` / `credit` until defeated |
| `test_knight_card_last_line_and_no_touches_leak` | `knights[0].happened[0]` is the latest touching event; the string `"touches"` is absent from `/api/table` |
| `test_old_session_without_glory_events_replays` | |

### Acceptance
1. Slay a foe engaged with Sir Erik and check that the tracker, log and Table all show +Glory.
2. Strike the slay event and check that the Glory disappears.
3. Defeat a pool foe, answer the prompt, then reassign from the strip.
4. UX acceptance against `#gm-fight` (lane Glory, strip) and `#t-fight` (lanes, chips, LAST line, Defeated/Waiting footer).

---

## S4 — Random fight with tag filter (size **S**)

**Goal.** The Combat launcher can draw a random encounter from the library, optionally filtered by tags
(P1 d5). This draw is separate from battle decks.

### Files
- `web/routes/combat.py`:
  - factor the body of `start()` into `_launch(state, cs, defn, name, body, lines_prefix)`
  - add `POST /api/combat/random`
- `web/static/js/tools/combat.js`: launcher tag chips + **Random fight** button.

### Route
| Method | Path | Body | Behaviour | Errors |
|---|---|---|---|---|
| POST | `/api/combat/random` | `{tags?: [str], players?, include_party?, knights_mounted?}` | Candidates are encounters that carry **all** selected tags (Open point 19), excluding `battle_role == "opportunity"` and any whose roster and leader are empty. `random.choice` picks one, then `_launch` runs as for `/start`. The log text is prefixed `Random fight: drew 'X' — …` and the table_text is as for `/start` | 400 "No encounter has all those tags" |

No new event type is needed (`combat.started`).

### UI
- Launcher panel: under the search box, a chip row of every tag in the library (multi-select, toggles).
- **Random fight** button (icon d6) beside **Launch encounter**.
- The toast reads "Drew Saxon raiders".

### Tests (`test_web_tracker.py`)
| Test | Asserts |
|---|---|
| `test_random_fight_filters_by_all_tags` | Save two tagged encounters; `tags:["x","y"]` only ever starts the one with both |
| `test_random_fight_excludes_opportunities_and_empty` | |
| `test_random_fight_no_match_400` | |

### Acceptance
Tag two encounters, filter, and click Random fight several times. UX acceptance: the launcher has no
mockup, so check it against the existing launcher layout.

---

## S5 — Encounter battle fields + deck lists (size **M**)

**Goal.** Encounters can be marked as battle Foes or Opportunities, with Morale Minimum, Morale Loss,
missile and rules text. Battle-approved decks become listable.

### Files
| File | Change |
|---|---|
| `core/encounter_def.py` | `blank_encounter()` adds `battle_role: None, morale_minimum: None, morale_loss: "", missile: False, rules: ""`. `to_editable` keeps them, and legacy entries keep their `morale_minimum` |
| `web/routes/library.py` | `_clean_encounter` validates and keeps the new fields. It currently **drops** `morale_minimum` and the other battle keys, which is a bug fixed here. `_enc_summary` adds `battle_role`. `preview` adds `battle_defaults`. New `GET /api/battle-decks` |
| `web/static/js/tools/encounters.js` + `css/tools/encounters.css` | **Battle** panel in the editor; role tag in the list |
| `web/static/js/components.js` (new) | `deckPicker()` (used by S6) |

**Field validation in `_clean_encounter`:**
- `battle_role ∈ {None,"foe","opportunity"}` (else 400)
- `morale_minimum` is an int ≥ 0, or None
- `morale_loss` is `""` or valid dice (`roll_notation` dry-run, else 400 "Morale Loss isn't dice")
- `missile` bool; `rules` str

### Routes
| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| POST | `/api/encounters/preview` | unchanged | + `battle_defaults: {morale_minimum, morale_loss, kv_per_knight: "⅜"}` from `core.battle.default_morale` | — |
| PUT | `/api/encounters` | + battle fields | as today | 400 as above |
| GET | `/api/battle-decks` | `?role=foe\|opportunity` (optional) | `{cards: [{key, role, description, morale_minimum, morale_loss, kv: [{adversary, kv:"⅛", per_knight: 3.0}], kv_per_knight:"⅜", missile, countercharge, mounted_charge, has_roster, rules}]}`. GM only and never projected | 400 bad role |

### UI (Encounters editor; no mockup, so it follows design §6 / P3)
- A new panel **Battle** under the roster:
  - Role chips **Not in battles / Foe / Opportunity ★**
  - **Minimum Morale** number (placeholder = default, "from the cards: 13")
  - **Morale Loss** text (placeholder = default dice)
  - **Missile barrage** checkbox (Foe only)
  - **Rules / rewards** textarea (Opportunity; hint "played at the table")
  - A GM-only line: "KV per knight ⅜ · Glory per foe …"
- With Opportunity chosen, the roster heading reads "Foes to fight (optional)".
- List items show a `Foe` tag (gules) or `★ Opportunity` tag (or) beside the name.
- `deckPicker` is built here and reused in S6:
  - Foes / Opportunities tabs, rows `☐ name · Min 13 · Loss 1D6+3 · KV 1`, search
  - selected count in each tab label
  - unknown keys (deleted encounters) shown as "missing" rows that can be removed

### Tests (`tests/test_web_library.py`)
| Test | Asserts |
|---|---|
| `test_encounter_battle_fields_round_trip` | |
| `test_saving_legacy_encounter_keeps_morale_minimum` | regression for the existing bug |
| `test_bad_morale_loss_rejected` | |
| `test_opportunity_with_empty_roster_saves` | |
| `test_battle_decks_lists_roles_with_min_loss_kv` | baseline after S0: 12 foes, 5 opportunities; Archers `missile`; Gorre `countercharge` + `mounted_charge` |
| `test_preview_battle_defaults_mixed_roster` | Q23 |
| `test_battle_decks_never_on_table` | after `GET /api/battle-decks`, `/api/table` contains no `morale_minimum` |

### Acceptance
Mark a home-made encounter as a Foe and check that the defaults pre-fill from its cards. Save, reload,
and confirm the fields are kept. Create an Opportunity with no roster. UX: no mockup, so match the
existing editor panels.

---

## S6 — Battle container: Battles editor, launch, Mustering, Morale strip, army rolls, day Intensity, settings, deck edit, pause/resume, Table title + Morale gauge (size **L**)

**Goal.** A battle can be prepared (saved definitions), launched (saved or quick), mustered (knights,
commander, Morale, army rolls, Intensity), edited live, paused at session end and resumed in a later
session. The Table shows the battle's title band and Morale gauge.

### Files
| File | Change |
|---|---|
| `core/battle_def.py` (new) | `blank_battle()`, `blank_day(size)`, `quick_battle(size, days, name, where, against, notes)`, `clean_battle(d, encounters) → (clean, warnings)` |
| `web/battle_state.py` (new) | `reduce(live_events) → battle\|None`, `gm_view(b, party)`, `table_view(b, party)`, `snapshot(b, cs)`, `paused_battles(store)` |
| `web/routes/battle.py` (new; in `web/app.py`) | live routes (S6 subset below); `record_outcome` skeleton |
| `web/routes/library.py` | `/api/battles` CRUD |
| `web/state.py` | `battle_state()`, `end_session()` (writes `battle.paused` first), `table_payload()` passes the battle |
| `web/routes/session.py` | `end_session`, `start_session` (when ending a previous one), `resume_session` (when switching) call `state.end_session()` instead of `sessions.end()`; `table_mode` accepts `"battle"` |
| `web/table.py` | `build(session, combat, battle, pinned_mode)`; auto mode; `_SAFE_DATA` for S6 events |
| `web/static/js/gm.js` | `TOOLS`: `{id:"battle", label:"Battle", icon:"banner"}` after Combat; `{id:"battles", label:"Battles", icon:"banner"}` after Encounters; table-mode chips (Open point 3); `KIND` `battle.*` → `["battle","banner"]` |
| `web/static/js/lib.js` | `banner` icon path in `P` |
| `web/static/js/components.js` | `outcomeChips`, `amountEntry`, `moraleStrip`, `knightChip`, `dayCard` |
| `web/static/js/tools/battle.js` + `css/tools/battle.css` (new) | launch panel, Mustering, running shell (header, Morale strip, knight chips; the stepper arrives in S7), settings drawer, quick-create modal |
| `web/static/js/tools/battles.js` + `css/tools/battles.css` (new) | saved-battle editor |
| `web/static/js/board.js`, `table.js`, `css/board.css` | `moraleGauge`, battle view (title band + gauge + title card + Fray) |

### Data: `combat.json` → `battles` (design §2.1) plus defaults
```json
"battles": {"<name>": {
  "source": "user", "name": "", "size": "clash", "where": "", "against": "", "notes": "",
  "outcome": null, "commander": null,
  "army_commanders": {"friendly": {"name": "", "battle": null}, "enemy": {"name": "", "battle": null}},
  "days": [{"intensity": {"mode": "roll"}, "turns": 5, "first_charge": true, "on_foot": false,
            "no_charge": false, "commanders": {"friendly": null, "enemy": null},
            "deck": {"foes": [], "opportunities": []}, "notes": "", "scripts": []}]}}
```
- `commander` (`"gm"|null`, pre-selects the commander chip) and `army_commanders` (names and Battle
  values shown in Mustering, `#gm-muster`) are **additions** that are needed to render the approved
  mockup and Carlion (Open point 8).
- `clean_battle` rules:
  - `size ∈ SIZES`; ≥ 1 day
  - fixed intensity is an int 1–40
  - `turns` int ≥ 1 (no maximum; the UI hints above Table 6.1)
  - outcome presets ∈ `OUTCOMES ∪ {null}`
  - scripts need `turn ≥ 1`, non-empty `text`, bool `if_intensity`, and `deck` null or `{foes, opportunities}`
  - unknown deck keys are kept and reported in `warnings`
  - `outcome` (preset) only for Small and up

### Live battle state
`web/battle_state.py` produces the design §2.5 shape plus these keys:
- `step.current` (step key or `null`), `step.items: [{key, state: done|current|skipped|todo|locked, summary, events: [ids], reason}]`, and `step.options` (what the current step allows; S7)
- `closed`: aggregates from finished fights (`defeated`, `glory`, `kv_by_turn`); the open fight is added
  live in S8. This is so `battle.resumed` never double-counts (Open point 17)
- `army: {day: {friendly, enemy}}`, `tokens: {force: available|spent|none, negate: …}`, both scoped to the current day (Q15)
- `last_title_event`, used for the Table title card

### Events (S6). Every one carries `data.battle` with `step: null`.
| Type | Vis. | `data` | Reducer |
|---|---|---|---|
| `battle.started` | public | `definition` (full copy), `source_key: str\|null`, `knights: [pid]` (active party), `table_text: "The Battle of Bedegraine begins — Huge Battle, 2 days"` | new state; `status = "mustering"`, `day = 1`, `turn = 0`; `id` = `secrets.token_hex(4)` (from the route) |
| `battle.settings` | gm | `day: int`, `patch: {intensity?, turns?, first_charge?, on_foot?, no_charge?, commanders?, notes?, scripts?}` or `add_day: {…day…}` | patch `definition.days[day-1]`. `on_foot: true` on the current day sets every pill to On foot. `add_day` appends (Open point 18) |
| `battle.deck` | public | `day`, `add: [key]`, `remove: [key]`, `cards: {key: card}`, `table_text: "New foes join the field: Saxon Warriors"` | edit that day's deck |
| `battle.army_roll` | public | `day`, `side`, `outcome`, `roll: null\|{value, value_rolled: bool, mods, roll}`, `table_text: "Arthur's Battle roll: Success — turn 1 opens with a mounted charge"` | the latest per (day, side) wins; effects come from `army_effects` (first-charge override, `minus5` reminder, tokens) |
| `battle.day_started` | public | `day`, `intensity: int`, `rolled: bool`, `dice: "3D6+1"\|null`, `table_text: "Day 1 — Intensity 14"` | the latest for the day wins → `intensity` |
| `battle.mustered` | public | `day`, `start: int ≥ 1`, `passion: str`, `commander: pid\|"gm"`, `knights: [pid]`, `table_text: "The conroi musters — Morale 21 (Loyalty (King)), led by Sir Erik"` | `morale = {start, current: start}`; commander; members; positions → `conroi`; passions reset (**scenario rule**); pills: day 1 → mounted, later days keep their pills, `on_foot` day → all On foot; `status = "turn"`, `turn = 1`, step `set` (① implicit, §14.2) |
| `battle.commander` | public | `commander`, `table_text` | change |
| `battle.morale_adjust` | public | `delta: int\|null`, `start: int\|null` (exactly one), `reason: str`, `table_text: "Morale +2 · rallying cry (16 of 21)"` | `delta` → `apply_morale` (capped, Q13); `start` → new start, with current capped to it |
| `battle.script` | public | `day`, `index`, `text`, `table_text = text` | adds to `revealed_scripts` (Q20) |
| `battle.paused` | gm | `summary: {name, day, turn, morale: [cur, start]}` | `status = "paused"` |
| `battle.resumed` | gm | `snapshot: {battle, combat\|null}`, `from_session` | **replace** state (`combat_state` restores `snapshot.combat` like a `combat.started`, with `started_event` = this event's id) |

### Routes (S6)
| Method | Path | Body | Response / events | Errors |
|---|---|---|---|---|
| GET | `/api/battles` | — | `{battles: [{key, size, days, source}]}` | — |
| GET | `/api/battles/blank` | `?size=` | `{battle}` | — |
| GET | `/api/battles/{key}` | — | `{key, battle}` | 404 |
| PUT | `/api/battles` | `{battle, original?, overwrite?}` | `{key, battle, warnings, path}`; `notify("library")` | 400 invalid; 409 name exists |
| DELETE | `/api/battles/{key}` | — | `{ok}` | 404 |
| GET | `/api/battle` | — | `{battle: gm_view\|null}` | — |
| GET | `/api/battle/paused` | — | `{paused: [{battle_id, session_id, session_title, name, day, turn, morale}]}` from scanning session files (design §3.5) | — |
| POST | `/api/battle/start` | `{key}` or `{quick: {size, days, name?, where?, against?, notes?}}` | `battle.started` | 404 key; 400 bad size/days; 409 "A battle is running — pause or finish it first" |
| POST | `/api/battle/resume` | `{battle_id, session_id}` | `battle.resumed` (the snapshot is rebuilt by reducing that session's live events) | 404; 409 battle running |
| POST | `/api/battle/pause` | — | `battle.paused` | 409 none running |
| POST | `/api/battle/settings` | `{day, patch}` or `{add_day: {...}}` | `battle.settings` | 409 "Past days are locked" (`day < current day`); 400 invalid |
| POST | `/api/battle/deck` | `{day, add, remove}` | `battle.deck` (cards snapshotted from the library) | 400 unknown key or non-battle encounter |
| POST | `/api/battle/quick-encounter` | `{definition}` (an encounter with `battle_role`) | saves via `_clean_encounter`, then `battle.deck` add for the current day | 409 name exists; 400 no role |
| POST | `/api/battle/template` | `{name, overwrite?}` | saves the live `definition` to `battles[name]` with `source: "user"` | 409 exists |
| POST | `/api/battle/muster` | `{start, passion?, commander, knights: [pid]}` | records preset army rolls the GM didn't answer, then `battle.mustered` | 400 no commander / start < 1 / no knights; 409 "Set today's Intensity" (Open point 9); 409 not mustering |
| POST | `/api/battle/commander` | `{commander}` | `battle.commander` | 400 not a member / not "gm" |
| POST | `/api/battle/army-roll` | `{side, outcome}` or `{side, roll_for_me: {battle?: int, mods: int}}` | `battle.army_roll`. Roll-for-me rolls `2D6+10` when `battle` is omitted, then `resolve_skill(value + mods)` | 400 below Clash; 409 not mustering |
| POST | `/api/battle/day` | `{intensity: int}` or `{roll_for_me: true}` | `battle.day_started`. Roll-for-me uses the Table 6.1 dice for the size | 409 not mustering |
| POST | `/api/battle/morale` | `{delta, reason}` or `{start, reason}` | `battle.morale_adjust` | 400 empty reason / delta 0 |
| POST | `/api/battle/script` | `{day, index}` | `battle.script` | 404; 409 already shown |
| POST | `/api/battle/knight/{pid}` | `{position?}` or `{mounted?}` | `battle.position` / `battle.mounted` (schemas in S7/S8; S6 records the pill only) | 404 not a member |

Session end (`AppState.end_session()`): if `battle_state()` is live (status not `ended`/`paused`), record
`battle.paused`, then call `sessions.end()`. This applies to `/api/session/end`, `/api/session/start`
when it ends an active session, and `/api/session/resume` when it switches sessions.

### UI: Battle tool (`tools/battle.js`)
**Idle: launch panel** (no mockup; design §6.2):
- **Paused battles**: rows `Bedegraine · Day 1 · Turn 3 · Morale 14 / 21 · Session 12` with **Resume**.
  Empty state: hidden.
- **Quick battle**:
  - Size chips; each chip shows `max 8 turns · 3D6`.
  - Days stepper (1–7).
  - Name (optional; default "Battle of <Size>"), plus a folded "where / against / notes".
  - **Launch**: two clicks from idle.
- **Saved battles**: list `name · Size · n days` with **Launch ▶**. Empty: "Prepare battles in the Battles tool."

**Mustering** (matches `#gm-muster`):
- **Header:** `Battle of Bedegraine` · `Mustering · Day 1 of 2 · Huge · 5 turns · first charge on`.
- **Left panel "The conroi":**
  - checklist of active party knights (✓ shield name + Mounted pill → `/api/battle/knight/{pid}` `{mounted}`)
  - **Commander** chips (each checked knight + **GM (NPC)**), pre-selected from `definition.commander`
    or yesterday's commander
  - **Starting Morale** number (pre-filled with yesterday's start on a new day)
  - **Passion (optional)** text
  - helper: "The players work Morale out at the table: the average of their Passion, +5 if they all chose the same one."
- **Right panel "Army commanders"** (Clash and up only; hidden for Fight/Skirmish):
  - two rows `Arthur (friendly)` / `King Lot (enemy)` (names from `army_commanders`, falling back to "Friendly" / "Enemy")
  - each row: outcome chips Crit/Success/Fail/Fumble (pre-highlighted from `days[d].commanders`; a click
    records `battle.army_roll`) + **roll for me** (popover: Battle value, blank = 2D6+10, and the
    Table 6.2 ticklist with modifiers summed)
  - a one-line consequence under each, e.g. "Success → turn 1 is a mounted charge." / "Success → you hold a Force Encounter token for this day."
  - folded **▸ Table 6.2 modifiers** reference
- **Day Intensity**:
  - fixed day: `14 fixed by the saved battle` (editable number → `/api/battle/day`)
  - roll day: **Roll for me (3D6)** + a number input
- **Begin Turn 1 ▸**:
  - disabled with a reason (`Set a commander` / `Enter the starting Morale` / `Set today's Intensity`)
  - when enabled: "Ready: commander and Morale are set."
  - Enter key = click
- On a later day the header reads `Re-muster · Day 2 of 2` and the button reads **Begin Day 2**.

**Running shell** (matches the `#gm-turn` header; the stepper body is S7):
- **Header:** `Battle of Bedegraine` · `Day 1 · Turn 3 of 5 · Intensity 14 · Huge`, with buttons
  **+ New encounter** (quick-create modal), **Battle settings** (drawer), **Pause** (confirm → `/api/battle/pause`).
- **Morale strip** (`moraleStrip`, pinned):
  - big `14 / 21` + band word
  - **±** (modal: delta + reason, or "Edit starting Morale" + reason → `/api/battle/morale`; a delta that
    would exceed the start shows "capped at 21")
  - token chips **⚑ Force Encounter** / **✋ Negate loss** when available (glow rules in S7)
  - **Commander: Sir Erik** chip (click → menu → `/api/battle/commander`)
- **Knight chips row**: shield, name, Mounted pill, position chip (S7/S8), posture tag (S7).
- The stepper area shows "Turn loop arrives in the next build" until S7.

**Settings drawer** (no mockup):
- a wide modal holding one `dayCard` per day; past days are read-only with "(past days are locked)"
- **Add day**; **Save** posts `/api/battle/settings` once per changed day
- day card **Edit deck** opens `deckPicker` → `/api/battle/deck`

**Quick-create modal** ("+ New encounter", P3 d5):
- Name, Role (Foe / Opportunity), Description, roster lines (adversary picker + count + "per knight"),
  Min Morale, Morale Loss, Missile (Foe), Rules (Opportunity)
- **Save & add to today's deck**

### UI: Battles tool (`tools/battles.js`; no mockup; design §6.3, Encounters pattern)
- **List:** search, **New**, **Duplicate**, **Delete**; items `name · Size · n days` with a ▶ Launch button.
- **Form header:**
  - Name, Size chips (with the hint), Where, Against, Notes
  - **Commander** "GM leads the conroi" checkbox
  - Army commander names + Battle values (Clash+)
  - **Preset outcome** select (Small+)
- **Day cards** (`dayCard`):
  - **Intensity**: Roll from size / Fixed [n]
  - **Turns** stepper (hint `over Table 6.1 max (8): scenario override`, never blocked)
  - switches **First charge** / **Conroi starts on foot** / **No charge this day**
  - commander outcome presets (Clash+)
  - `deckPicker`
  - Notes
  - **Turn scripts** list (turn #, text, "only if Intensity succeeds", **Restrict deck…** → deckPicker),
    add/remove script; remove day
- **Add day**.
- Footer: **Save** (PUT; 409 → overwrite confirm), **Revert**, dirty guard, **Launch**.

### Table (S6 part of `#t-battle`)
`table.build` mode logic:
- `auto` → `"combat"` if a combat is active
- otherwise → `"battle"` if a battle is live or paused in this session
- otherwise → `"chronicle"`

Payload gains `battle: table_view|null`. `table_view` (S6 subset):
```json
{"name", "where", "against", "size_label", "status", "day", "days", "turn", "turns_today",
 "intensity", "morale": {"current", "start", "band", "last": {"delta", "reason"}|null},
 "commander_name", "title_card": {"kind": "started"|"day", "id": event_id}|null}
```
- **Title band**: `The Battle of Bedegraine` · `against King Lot …` · `Day 1 · Turn 3 of 5` · `Intensity 14`.
- **Morale gauge** (`moraleGauge`):
  - number `14 of 21`
  - draining fill; the frame shifts from green-gold to deep red and the texture from clean to
    bloodied (CSS classes by band)
  - band word
  - last change `−3 · Pictish Knifemen`, animated once per new `last`
- **Title card** on the latest `battle.started` / `battle.day_started` until the next battle event.
- **Fray**: existing `mini` cards.

`_SAFE_DATA` (S6):
| Event | Safe keys |
|---|---|
| `battle.started` | `()` (the definition is never projected) |
| `battle.deck` | `("day","add","remove")` |
| `battle.army_roll` | `("side","outcome")` |
| `battle.day_started` | `("day","intensity")` |
| `battle.mustered` | `("day","start","passion")` |
| `battle.commander` | `()` |
| `battle.morale_adjust` | `("delta","start","reason")` |
| `battle.script` | `("text",)` |

### Tests (`tests/test_web_battle.py`, new)
| Test | Asserts |
|---|---|
| `test_battles_crud_writes_working_copy` | PUT/GET/DELETE; 409 on a duplicate name; `examplecombat.json` unchanged |
| `test_quick_battle_start_carries_full_definition` | `battle.started.data.definition.days` has length = days, turns = Table 6.1 max, roll mode |
| `test_live_settings_never_touch_template` | start from a saved battle, change settings, then GET `/api/battles/{key}` is unchanged |
| `test_past_day_settings_rejected` | |
| `test_muster_requires_commander_morale_intensity` | |
| `test_muster_sets_status_turn_and_morale` | |
| `test_army_rolls_only_clash_and_up_and_tokens` | friendly success → `first_charge` True; enemy success → force token available; fumble → negate; latest roll wins |
| `test_preset_army_roll_recorded_at_muster` | |
| `test_day_intensity_roll_for_me_in_range` | Large → 3–18 |
| `test_morale_adjust_capped_and_start_edit` | |
| `test_pause_on_session_end_and_resume_in_new_session` | start session A → battle → end → `battle.paused` in A; start B → `/api/battle/paused` lists it → resume → `battle.resumed` in B; B's state equals A's final state |
| `test_template_saves_live_definition` | |
| `test_quick_encounter_saves_and_adds_to_deck` | |
| `test_table_battle_mode_and_gauge` | `mode == "battle"`; `battle.morale.band` |
| `test_table_never_sees_army_die_or_definition` | `"value_rolled"`, `"mods"`, script text and `"morale_minimum"` absent from `/api/table` text |
| `test_settings_and_pause_events_gm_only` | |

Existing tests: `test_session_lifecycle_persists` must still pass (no battle → no extra events).

### Acceptance
1. Prepare a 2-day Clash in Battles, Launch, and muster with army rolls and Intensity.
2. Watch the Table switch to the battle view with the gauge.
3. Adjust Morale ±, end the session, start a new one and resume.
4. UX acceptance against `#gm-muster`, the `#gm-turn` header and strip, and the `#t-battle` title band and gauge.

---

## S7 — Turn stepper ②–⑧ and ⑩, rest/rear, cascade undo, inconsistency flags (size **L**)

**Goal.** A full turn can be run without the fight: set, charge, Intensity, picks, choice, Morale,
postures, end turn and end day, plus retiring and resting. Answering a step completes it. A reopened
step strikes it and everything after it in one undoable action.

### Files
| File | Change |
|---|---|
| `web/battle_state.py` | step machine (below); `undo_targets(b, events, step)` |
| `web/routes/battle.py` | `POST /api/battle/step`, `GET /api/battle/undo-preview`, `POST /api/battle/undo`, `POST /api/battle/undo/{strike_id}/restore` |
| `web/sessions.py` | `flags()` honours `data.targets: [ids]` on `meta.strike` / `meta.unstrike` as well as `data.target` (Q12) |
| `web/routes/session.py` | `_target` unchanged |
| `web/static/js/gm.js` | `applyIncoming` handles `data.targets` |
| `web/static/js/tools/battle.js` + `css/tools/battle.css` | stepper (matches `#gm-turn`) |
| `web/table.py` | `_SAFE_DATA` for the S7 events |

### Step machine (in `battle_state.reduce`)
| Step | Done by | Skipped when |
|---|---|---|
| ① `field` | implicit: `battle.set` = took the field (§14.2); `battle.field {choice:"retire"}` = retired | — |
| ② `set` | `battle.set` | — |
| ③ `charge` | `battle.charge` | turn 1 (Q29), the day's `no_charge`, `set.forced` |
| ④ `intensity` | `battle.intensity` | forced; enemy charge locked |
| ⑤ `picks` | `battle.pick` × n, closed by `battle.select` | Intensity not `failure` |
| ⑥ `select` | `battle.select` (`via: commander\|keep\|fumble\|enemy_charge`) | no picks and no fumble or enemy charge |
| ⑦ `morale` | `battle.morale` | — |
| ⑧ `postures` | `battle.posture` for every conroi knight | forced retire |
| ⑨ `fight` | S8; in S7, ⑨ shows "fights arrive in the next build" and ⑩ is allowed after ⑧ | forced retire; rest |
| ⑩ `end` | `battle.turn_ended` (+ `battle.day_ended` on the last turn) | — |

More rules:
- A route rejects an event that doesn't fit the current step with 409 `"Not now: …"`.
- On replay, a misfit event goes to `step.inconsistent: [{event, reason}]` and is ignored (P9 K2).
- **Retire path:** `battle.field retire` (or a ⑦ forced retire) → `battle.rest` (Q2) → ⑩. The next
  turn opens at the rear: `status = "rear"`, and the stepper is replaced by the rear choices (§14.2).
- **Rear turn:** `battle.field {rear_choice}`:
  - `rest` → `battle.rest` → ⑩
  - `return` → `status = "turn"` and ② opens this turn
  - `leave` → `status = "aftermath"`
- **Morale 0 (Q1):** if Morale is 0 at the start of a turn, only "Retire to the Rear" is offered. If ⑦'s
  Loss takes it to 0, a forced retire is required.

### Events (S7). All carry `data.battle` with the step.
| Type | `data` | Reducer / validation |
|---|---|---|
| `battle.field` | `choice: "retire"` \| `rear_choice: "rest"\|"return"\|"leave"`; table_text "The conroi retires to the rear" etc. | as above |
| `battle.rest` | `amount: 1–6`, `rolled: bool`; table_text `"Rest at the rear: Morale +4 (17 of 21)"` | `apply_morale(+amount)`; once per turn |
| `battle.set` | `encounter`, `card`, `flavour: str`, `drawn: bool`, `forced: bool`; table_text `"This turn: Pictish Javeliniers — painted men with bundles of javelins"` | must be a Foe in today's deck (or the turn script's restricted deck); `forced` needs the Force token and spends it |
| `battle.charge` | `outcome`, `engaged_last: bool`; table_text summarises the per-knight lines | per-knight `charge_line` from pills; `enemy_charge` with an eligible card in the deck → ⑥ requires `via: "enemy_charge"` and ④ ⑤ are skipped; no eligible card → treated as `no_charge` (Q17, P4 d4) |
| `battle.intensity` | `outcome`, `roll: null\|{roll, value}`; table_text `"Intensity roll: Failure — the knights may choose their fate"` | `doubled` on crit; fumble → ⑥ `via: "fumble"` (an Opportunity or keep); failure → ⑤ |
| `battle.pick` | `knight`, `encounter`, `card`, `crit: bool`; table_text `"Dame Cwylog (critical) picks Clash of Champions ★"`; touches | knight in the conroi; Opportunity only with `crit`, and not spent; the latest pick per knight wins; `encounter: null` removes the pick |
| `battle.select` | `encounter`, `card`, `via`; table_text `"The commander chooses Pictish Knifemen"` / `"No picks — the set Encounter stands"` | candidates per `via`; a chosen Opportunity → `spent_opportunities` (once per battle, across days, Q15) |
| `battle.morale` | `kind: "loss"\|"forced_retire"`, `amount: int\|null`, `rolled: bool`, `negated: bool`, `reason: "minimum"\|"zero"\|null`; table_text `"Morale −4 · Pictish Knifemen (10 of 21)"` / `"The enemy commander's blunder — no Morale lost"` / `"Not enough Morale — Retire to the Rear"` | `forced_retire` only if `forced_retire(current, minimum)`; `negated` spends the Negate token, amount stays 0, and it can't bypass the Minimum (Q14); Loss → `apply_morale(−amount)` |
| `battle.posture` | `knight`, `posture`, `amount: int\|null`, `rolled`, `above_half: bool\|null`; table_text `"Sir Erik rides Reckless (3 rounds) — Morale +2"`; touches | one per conroi knight per turn (409 on a duplicate; to change, reopen ⑧, Open point 14); first-charge turn → R/V only; delta via `posture_delta`; Cowardly → position `rear` |
| `battle.passion` | `knight`, `used: bool`, `name: str`; touches | the latest per knight per day; no Morale effect |
| `battle.position` | `knight`, `position: conroi\|rear\|alone\|left`; touches | only `conroi` knights count for postures and scaling |
| `battle.mounted` | `knight`, `mounted`; touches | the pill outside fights |
| `battle.turn_ended` | table_text `"End of Turn 3 — Morale +1 for foes defeated (15 of 21)"` | KV gain (S8; 0 in S7); `turn += 1`; step → `set`; `fought_days` (S8) |
| `battle.day_ended` | table_text | tokens expire (Q15); `day += 1` → `status = "mustering"`; after the last day → `aftermath` |

### Routes (S7)
`POST /api/battle/step` with body `{step, …}`. Each value of `step` maps to one handler, and each
writes one event unless noted:

| `step` | Body | Notes |
|---|---|---|
| `retire` | `{}` | → `battle.field {choice:"retire"}` |
| `rear` | `{choice}` | `rest` / `return` / `leave` |
| `rest` | `{amount}` \| `{roll_for_me: true}` | 1D6 |
| `set` | `{encounter, flavour?, forced?}` \| `{draw: true, flavour?}` | draw = `random.choice` of the (restricted) Foe deck, not Morale-filtered; flavour defaults to the card description |
| `charge` | `{outcome, engaged_last}` | `engaged_last` is pre-filled by the UI (fought last turn → true; rested or first turn of day → false) |
| `intensity` | `{outcome}` \| `{roll_for_me: true}` | roll = `resolve_skill(today's intensity)` |
| `pick` | `{knight, encounter\|null, crit}` | |
| `select` | `{encounter, via}` | `via: "keep"` → the set Encounter, only when there are no picks |
| `morale` | `{kind:"loss", amount}` \| `{kind:"loss", roll_for_me:true}` \| `{kind:"loss", negate:true}` \| `{kind:"forced_retire"}` | roll uses the selected card's `morale_loss`; "" → amount 0 |
| `posture` | `{knight, posture, amount?, roll_for_me?, above_half?}` | |
| `passion` | `{knight, used, name?}` | |
| `end_turn` | `{}` | |
| `end_day` | `{}` | writes `battle.turn_ended` (if not yet written) + `battle.day_ended` |

Errors for `/step`: 400 unknown step or bad value; 409 not now (with the reason); 409 no battle.

Response: `{events: [...], battle: gm_view}`. Responses never include secrets beyond the GM view.

| Method | Path | Body | Response / event | Errors |
|---|---|---|---|---|
| GET | `/api/battle/undo-preview` | `?step=charge` | `{targets: [{id, type, text}], locked: bool}`. The targets are every live event with `data.battle.id == id` for the same day and turn whose step index ≥ the step's index, plus `battle.turn_ended`/`day_ended` for the turn, the linked fight's events (S8: from its `combat.started` to its `combat.ended`, covering `combat.*`, `glory.*`, and `roll.*` carrying `cid`), and `battle.rest` | 404 step not done |
| POST | `/api/battle/undo` | `{step}` | one `meta.strike {targets: [ids], cascade: {battle, day, turn, step}}` (gm), text `"Undone ③–⑩ of Turn 2 (14 events)"` | 409 `locked`: targets before the latest `battle.resumed` (Q11) |
| POST | `/api/battle/undo/{strike_id}/restore` | — | `meta.unstrike {targets}` (same list) | 404 not a cascade strike |

### UI: stepper (matches `#gm-turn`; §14 choices 1–9)
- **Layout:** a vertical list ②…⑩ under the Morale strip. Done steps collapse to one line with the
  result plus **reopen**. The current step is expanded. Steps that don't apply are greyed with their
  reason (e.g. "③ No charge on turn 1"). There are **no Next buttons**: answering a step completes it.
- **Reopen**:
  - `GET undo-preview` → `confirmBox("Undo from ③?", list of event lines, "Undo", danger)` → `POST undo`.
  - Afterwards the line "Undone ③–⑩ of Turn 2 · **Restore**" stays until the next battle event.
  - A locked step shows 🔒 with the title "Before the resume — correct it with a Morale override, or undo everything since the resume".
- **Inconsistent**: a gules tag "Doesn't add up — an earlier step was struck" on the step, listing the
  ignored events, with a **Reopen** suggestion.
- **Beside ②: turn scripts** (GM only), as `Turn script (GM only): "…"`.
  - Each has **Show on Table** (Q20), except "only if Intensity succeeds" scripts, which are tagged
    "shown to players after a successful Intensity roll".
  - Scripts also show on a rear turn. This satisfies P5's "at step ①"; see Open point 15.
- **② Set Encounter:**
  - Flavour input, pre-filled with the hovered card's description.
  - Foe cards from today's (restricted) deck as compact cards with GM-only `min · loss · KV`. A click
    sets the Encounter (with the current flavour).
  - **Draw** (D key).
  - **⚑ Force this Encounter**: the token chip on the strip glows while ② is open. Clicking a card with
    Force armed sets `forced`.
  - **Edit deck** / **+ New encounter** links.
  - Secondary button **Retire to the Rear instead**.
  - Empty deck: "No foes in today's deck: Edit deck / + New encounter".
- **③④ shared row:** left half "Commander's charge roll" outcome chips + **Engaged last round** toggle;
  right half "Intensity roll" **Roll for me** (Enter) + outcome chips.
  - A skipped half greys out with its reason.
  - Turn 1 after a friendly army fumble shows the reminder `−5 Battle this turn` here (§14.8).
  - The result line, e.g. `Charge: may charge (mounted) · Intensity: failed — knights may choose`, lists
    per-knight charge lines.
  - On an enemy charge: "Enemy knights charge you!" + a picker of eligible cards (→ `select via enemy_charge`)
    + an on-foot prompt "On foot: enemy +5 Height; Set Spear possible with a spear".
  - On an Intensity fumble: the unspent Opportunities + **Keep the set Encounter** (→ `select via fumble`).
- **⑤ Picks (card-first):**
  - A card grid of today's deck: Foes, then Opportunities (`min · loss · KV` GM-only).
  - Tap a card, then tap a knight token to record the pick. The token on the card toggles **crit**.
  - Opportunities stay locked until that knight's token is crit. Spent ones show "played on turn 1" and are greyed.
  - A helper line, e.g. "Opportunities unlock only for a pick marked crit. Clash of Champions needs
    Morale 14 — the conroi has 14 ✓".
  - **Commander chooses ▸** (Enter) opens ⑥, or with one candidate posts the select directly (§14.5).
  - **No picks — keep the set Encounter** → `select via keep`.
- **⑥ Commander's choice:** candidate cards (the set card + distinct picks, with knight tokens), each
  with GM-only `within Morale ✓ / below Minimum ✗`. A click selects. A chosen Opportunity shows "Opportunity
  picked — it must be played (Clash of Champions)" and its rules text.
- **⑦ Morale:**
  - First a GM-only line `Morale 14 ≥ Minimum 5 ✓` (or ✗).
  - Below the Minimum: **Not enough Morale — Retire to the Rear** (Enter), then the Rest roll entry.
  - Otherwise: amount entry with the dice hint (GM-only, e.g. `1D6+3`) + roll for me (Enter).
  - **✋ Negate loss** glows on the strip while ⑦ is open and shows here as a button when available.
  - A card with no Loss shows **No Morale Loss** (amount 0).
  - If the Loss takes Morale to 0, a forced retire is required.
- **⑧ Postures:**
  - A header line, e.g. `last turn: Erik Reckless · Cwylog Valorous · Emrys Prudent`.
  - One row per conroi knight: chips **R V P K** with rounds (3/2/1/0).
  - From turn 2, each knight's previous posture is pre-highlighted (§14.7). The first-charge turn shows
    only R/V; with on-foot knights, the line "GM ruling: mounted knights must charge…" carries a GR tag.
  - Amount entry for R (1D3 gain), P (1D3 loss), and K ("above half HP?" toggle → 1D6 loss).
  - **Passion** toggle + name (posts at once; a second use in a day asks "Already used today — use again?").
  - Reminder line "Trait checks: Reckless / Valorous / Prudent · Cowardly: −1 Honor (on paper)".
  - **Confirm postures** (Enter) posts one `posture` per knight.
- **⑩ End turn:** a KV gain preview (S8), then **End turn** / **End day** on the last turn (Enter).
  The ⑩ line in the mockup reads "KV Morale gain, then Turn 4".
- **At the rear** (replaces the stepper): "The conroi is at the rear", with **Rest another turn** ·
  **Return to the field** · **Leave the field** (confirm).
  - The Rest roll entry (1D6, roll for me).
  - Reminders: "First Aid 14+1D6 per knight (on paper) · remount → flip the knight's pill".
- **Keyboard (§14.9):** C/S/F/X pick outcome chips in the open step (in the ③④ row, the first unanswered
  half); R/V/P/K set the posture of the selected knight row (↑/↓ moves the selection); D = Draw at ②;
  Enter = the open step's main action. Keys are ignored while an input has focus.

### Table (S7 part)
`_SAFE_DATA`:
| Event | Safe keys |
|---|---|
| `battle.field` | `("choice","rear_choice")` |
| `battle.rest` | `("amount",)` |
| `battle.set` | `("encounter","flavour","drawn","forced")` |
| `battle.charge` | `("outcome","engaged_last")` |
| `battle.intensity` | `("outcome",)` |
| `battle.pick` | `("encounter","crit")` |
| `battle.select` | `("encounter","via")` |
| `battle.morale` | `("kind","amount","negated")` |
| `battle.posture` | `("posture","amount")` |
| `battle.passion` | `("used","name")` |
| `battle.position` | `("position",)` |
| `battle.mounted` | `("mounted",)` |
| `battle.turn_ended` | `()` |
| `battle.day_ended` | `()` |

The full battle view is S9. In S7 the Fray and gauge already update.

### Tests (`tests/test_web_battle.py`)
| Test | Asserts |
|---|---|
| `test_turn_loop_without_fight` | set → charge → intensity success → morale loss → postures → end_turn → turn 2 |
| `test_turn1_skips_charge` | the Q29 path |
| `test_step_out_of_order_409` | |
| `test_draw_picks_a_deck_foe_not_opportunity` | |
| `test_forced_retire_below_minimum` | and fighting is then impossible |
| `test_morale_zero_only_retire` | |
| `test_rest_capped_at_start` | |
| `test_opportunity_pick_needs_crit_and_is_once_per_battle` | the spent card stays spent on day 2 |
| `test_force_token_skips_intensity_and_picks_and_expires_at_day_end` | |
| `test_negate_token_zeroes_loss_not_minimum` | |
| `test_posture_deltas_and_first_charge_limit` | |
| `test_duplicate_posture_409` | |
| `test_cowardly_moves_knight_to_rear` | |
| `test_cascade_undo_single_strike_event` | one `meta.strike` with `targets`; state back to before ③; restore brings it back |
| `test_undo_locked_before_resume` | |
| `test_single_strike_marks_inconsistent` | strike `battle.intensity` alone → later `battle.pick` listed in `step.inconsistent` |
| `test_every_public_battle_event_has_table_text` | runs a full turn; every public `battle.*` event has `data.table_text` |
| `test_table_never_sees_min_loss_or_intensity_die` | with roll-for-me Loss and Intensity, `/api/table` text lacks the dice expression, `"morale_minimum"`, `"Minimum"` and the d20 roll value key `"roll"` under `battle.intensity` |
| `test_flags_targets_list` | in `test_web.py`: unit test of `flags()` with `targets`; the existing single strike still works |

### Acceptance
1. Run Bedegraine-style turns: Draw, failed Intensity, two picks (one crit Opportunity), choose, Loss,
   postures, End turn.
2. Reopen ③ and confirm that the cascade list shows, the undo is one log line, and Restore brings it back.
3. Retire, rest, and Return.
4. UX acceptance against `#gm-turn`: count the clicks for the walkthrough scenario (target ≈ 13 outside the fight).

---

## S8 — Step ⑨: linked fight, scaling + doubling, postures/rounds in lanes, barrage, countercharge, positions, KV Morale, Alone (size **L**)

**Goal.** Battles play end to end. ⑨ launches an ordinary tracked fight that is linked to the battle
turn and scaled to the knights with the conroi. Posture rounds, barrage and countercharge show in the
tracker. Ending the fight returns to ⑩, which applies the KV Morale gain.

### Files
| File | Change |
|---|---|
| `web/routes/battle.py` | `POST /api/battle/fight`; `/step` gains `barrage`, `countercharge`, `extra_round` |
| `web/routes/combat.py` | `_launch` accepts `battle_link`, `knight_overrides`, `multiplier` |
| `core/combat.py` | `Encounter.generate_from_definition(defn, n_players, multiplier=1)` (×count per roster line; the leader is not doubled, Open point 12) |
| `web/combat_state.py` | keep `data.battle` on the state; fold `battle.extra_round` into the knight's `extra_rounds`; `serialise` adds `battle` (GM: link + battle frame view; Table: name/day/turn/encounter) and knight `posture`, `rounds`, `extra_rounds`, `position`, `withdraws` (= `round > rounds + extra_rounds`), and `reaches` |
| `web/battle_state.py` | fold linked fights via `combat_state.apply`; open-fight aggregates; `kv_by_turn`; `fought_days` (Q27); glory per fight, day and total; `snapshot()` covers the open fight |
| `web/static/js/tools/combat.js` | battle frame (`#gm-fight` top); lane-header posture/rounds/position, "+1 round", "withdraws after this round", Alone lane tag; banners |
| `web/static/js/tools/battle.js` | ⑨ and the ⑩ preview |
| `web/table.py` | fight-view battle header; knight-card posture chips |

### Events
| Type | `data` | Reducer |
|---|---|---|
| `battle.barrage` | `outcome`; table_text `"The archers loose — 2 rounds of arrows before contact"` | `barrage = barrage_rounds(outcome)` |
| `battle.countercharge` | `roll: int\|null`, `rolled: bool`; table_text `"They countercharge!"` / `"No countercharge — their lances are spent"` | `countercharge(first_turn_of_day, roll)` (**scenario-rule extension** for the first turn of a day) |
| `battle.extra_round` | `knight`; table_text `"Sir Erik fights on — one more round"`; touches | `extra_rounds += 1` (combat_state and battle) |
| `combat.started` (changed) | + `battle: {id, day, turn, step: "fight", encounter, doubled}`; knight snapshots carry `mounted`, `posture`, `rounds`, `extra_rounds: 0`, `position` | linked fight |

### Route
`POST /api/battle/fight` with body `{}`. Before launching:
- ⑧ is complete
- if the selected card has `missile`, a `battle.barrage` exists this turn
- if it has `countercharge` and this isn't the day's first turn, a `battle.countercharge` exists

Then:
1. On the day's first turn, if the card has countercharge foes, it records `battle.countercharge {roll: null}` automatically.
2. It builds the definition from the library by the selected key, with `n = number of knights with
   position conroi and posture ≠ cowardly` (Q6). It applies `multiplier = 2` if the turn's Intensity was
   critical (Q5).
3. Knights are those positions `conroi` (not Cowardly) **plus** `alone` knights (each its own lane tagged
   "Alone", Q16), carrying their pill, posture and `POSTURES` rounds.
4. It records `combat.started` with the link, ending any active unrelated combat first (as `/start` does).

Response: `{event}`. Errors: 409 not at ⑨ / prerequisites missing; 400 card has no roster ("Play this
Opportunity at the table, then End turn").

`/step` additions:

| `step` | Body | Errors |
|---|---|---|
| `barrage` | `{outcome}` | 409 card not missile |
| `countercharge` | `{roll}` \| `{roll_for_me: true}` | 409 first turn (automatic) or card has no lance foes |
| `extra_round` | `{knight}` | 409 no linked fight active |

**Reducer on `battle.turn_ended`:**
- Morale += `kv_morale_gain([[kv of foes in DEFEATED] for each fight linked to this turn])`, capped (Q3/Q4).
- `fought_days[pid]` adds the day for knights in any fight that day with position `conroi` at ⑨ and not
  Cowardly (Q27).
- A turn whose selected Opportunity has no roster allows ⑩ right after ⑧ and adds no fought day (Open point 16).

### UI
- **Battle tool ⑨** (`#gm-turn`):
  - A barrage row (missile cards): outcome chips + per-knight lines `Sir Emrys endures 1 round, turns back` /
    `Sir Erik reaches the archers` (from `reaches`).
  - A countercharge row: an auto banner "They countercharge! (first turn of the day — **scenario rule**)",
    or an amount entry 1D6 + roll for me.
  - **Begin the fight → combat tracker** (Enter) posts, then `ctx.navigate("combat")`.
  - After the fight: the line `Fought Pictish Knifemen ×6: 5 defeated · ✦ 45`.
  - Opportunity without a roster: its rules text + **✦ Award Glory** + "Play it at the table, then End turn".
- **⑩:** a preview line `Foes defeated: KV 1⅜ → Morale +1 (GM ruling: rounded half up)`, then **End turn** / **End day**.
- **Combat tracker battle frame** (`#gm-fight` top):
  - title `Pictish Knifemen` + `Bedegraine · Day 1 · Turn 3 · Round 2`
  - buttons Next round · + Add · End fight · **◂ Back to battle** (→ `ctx.navigate("battle")`)
  - Morale strip compact `11 / 21` + token chips
  - banners: "They countercharge!" / "Barrage: 2 rounds" / per-knight "turns back"
- **Lane header:**
  - `Reckless · round 2 of 3`; `withdraws after this round` when `round == rounds + extra`; `withdraws`
    when past it (never blocking)
  - **+1 round** (→ `extra_round`) shown when rounds are used up
  - position chip (`with the conroi` / `at the rear` / `Alone on the Field` / `left the field`; click → menu →
    `/api/battle/knight/{pid}` `{position}`)
  - Glory `✦ n this battle`
  - an Alone lane gets a gules "Alone" tag + the reminder "Alone: rolls Battle at −10, still drains conroi Morale (use ± with a reason)"
- **End fight** in a linked fight → confirm "End the fight and return to the battle?" → `/api/combat/end` → navigate to Battle (⑩ open).
- **Table fight view** (`#t-fight`):
  - header `Pictish Knifemen · Bedegraine · Day 1 · Turn 3 · Round 2`
  - compact `MORALE 11 Shaken`
  - banners for countercharge / barrage
  - knight-card chips gain `Reckless · round 2 of 3` / `Valorous · last round` (state) and `Charge +5` (boon) on charge turns

### Tests (`tests/test_web_battle.py`)
| Test | Asserts |
|---|---|
| `test_fight_scaled_to_conroi_knights` | 3 conroi knights + Lothian (1.5) → 5 foes; with one knight Cowardly, 2 knights count → 3 foes |
| `test_intensity_crit_doubles_resolved_count` | 5 → 10 |
| `test_knight_snapshots_carry_pill_posture_rounds` | |
| `test_countercharge_auto_first_turn_and_roll_later` | |
| `test_barrage_required_for_missile_card_and_reach_lines` | |
| `test_end_turn_applies_kv_gain_half_up` | defeat 4 Kerns-like ⅛ foes → +1, capped |
| `test_fought_days_and_cowardly_excluded` | |
| `test_cascade_undo_strikes_linked_fight_and_its_glory` | |
| `test_resume_mid_fight_restores_combat_and_glory_once` | pause mid-fight in session A, resume in B → the combat is active with the same HP; battle Glory isn't double-counted |
| `test_alone_knight_gets_lane_not_scaling` | |
| `test_table_fight_view_battle_header_has_no_numbers` | no `morale_minimum`, `cur_hp` or KV |

### Acceptance
1. Play one full Bedegraine turn into the tracker: barrage on the Javeliniers, defeats, +1 round, Back to battle.
2. End turn and check the KV gain.
3. Pause mid-fight and resume.
4. UX acceptance against `#gm-fight` (battle frame and lanes) and `#t-fight`.

---

## S9 — Table battle view: cards, deck spread, knights row, LAST lines, step results, Fray (size **M/L**)

**Goal.** Between fights, players see the turn's story (`#t-battle`):
- the result banner
- the GM's card beside the knights' picks
- today's battlefield
- each knight's Glory, effect chips and LAST line
- the Fray

### Files
- `web/battle_state.py`: complete `table_view`.
- `web/table.py`: `knight_cards()` gains the battle-sourced chips and `touches` from battle events.
- `web/static/js/table.js`: `battleView(p)`.
- `web/static/js/board.js` + `css/board.css`: `cardFrame`, deck spread, result banner.

### `battle_state.table_view` (complete; anything not listed is never sent)
```json
{"…S6 fields…",
 "banner": {"text": "Intensity fails · choose your fate", "tone": "harm"|"boon"|"state"}|null,
 "this_turn": {"set": {"name", "flavour", "opportunity": false}|null,
               "picks": [{"name", "flavour", "opportunity", "knight_name", "crit"}],
               "selected": "name"|null},
 "deck": {"foes": [{"name", "in_play": bool}],
          "opportunities": [{"name", "in_play": bool, "spent": bool}]},
 "results": [{"kind": "intensity"|"charge"|"enemy_charge"|"barrage"|"countercharge"|"forced_retire"|"script"|"minus5", "text"}],
 "knights": [<knight-card dict from S3, plus battle chips>]}
```
- The banner comes from the latest step result. Copy: Intensity crit "The foe comes on in strength —
  doubled!", success "The Encounter stands", fumble "Fortune smiles — an Opportunity?", failure
  "Intensity fails · choose your fate", forced "Not enough Morale — Retire to the Rear".
- **Battle chips** on the knight card:

| Chip | Tone |
|---|---|
| `Commander` | state |
| `May charge` / `Charge +5` | boon |
| `Enemy charge — on foot` | harm |
| `On foot` | state |
| `Reckless last turn` / current posture `Reckless 3 rounds` | state |
| `Passion: Love (Family)` | state |
| `At the rear` | state |
| `Alone on the Field` | harm |
| `−5 Battle (army fumble)` (turn 1 only) | harm |

- `results.script` covers `if_intensity` scripts after a successful ④ on that turn, plus scripts shown
  with `battle.script`. Turn 1's `minus5` reminder is also listed.
- **Never** sent: `morale_minimum`, `morale_loss`, KV, `card`, the definition, unrevealed scripts, the
  Intensity die, army dice and modifiers, tokens.

### UI (`#t-battle`)
- **Title band** (S6) + **Morale gauge**, the largest element on screen.
- **Result banner** over the centre.
- **This turn:** card frames for `THE GM SETS`, `PICKED` (with the knight's shield token), and
  `★ OPPORTUNITY` (gold border, `· critical`). The set card flips in from the deck on `battle.set`.
- **TODAY'S BATTLEFIELD:** one row of every card name. Cards in play are outlined and spent
  Opportunities struck through. Additions animate in.
- **Knights row:** `knightCard` per conroi knight (shield, name, `GLORY n` battle total, chips, `LAST …`).
- **THE FRAY:** `table_text` cards, newest first.
- **Opening title card** on `battle.started` / `battle.day_started`.

### Tests (`tests/test_web_battle.py`)
| Test | Asserts |
|---|---|
| `test_table_battle_view_cards_and_deck_names_only` | deck entries have only `name` / `in_play` / `spent`; no `morale_minimum` / `morale_loss` / `kv` keys anywhere |
| `test_spent_opportunity_flag_on_table` | |
| `test_picks_carry_knight_names_and_crit` | |
| `test_if_intensity_script_revealed_only_after_success` | absent before ④, present after a success, never on a failure |
| `test_unconditional_script_only_after_show` | |
| `test_knight_chips_from_battle_state` | Commander, posture, Passion, rear |
| `test_last_line_from_battle_events` | |
| `test_banner_follows_latest_step` | |

### Acceptance
Run the walkthrough turn with the Table open beside the console, and check that each step updates the
board. UX acceptance against `#t-battle`: the two-second check that every player finds their knight.

---

## S10 — Aftermath + finale (size **M**)

**Goal.** The battle closes with one aftermath (Outcome / Glory / Spoils, every number editable,
`#gm-after`), then **Post to Table** shows the finale (`#t-finale`).

### Files
- `web/battle_state.py`: `aftermath_view(b, party)`, computed on replay with `core.battle`.
- `web/routes/battle.py`: `/aftermath`, `/finale`, `/end`.
- `web/static/js/tools/battle.js`: aftermath panel.
- `web/static/js/table.js` + `board.js`: finale scene; chronicle `hero()` for `battle.finale` after the battle ends.

### Aftermath computation
| Figure | Default |
|---|---|
| **Enemy KV** | Σ `parse_kv` of foes in all linked fights that are `dead`, or `captured_by` set and `unconscious`/`surrendered` (RAW "killed or captured", Q4) |
| **Friendly KV** | `friendly_pk_losses` + Table 6.5 helper (`gm_knights`, `gm_losses_roll` → `conroi_losses`, or an override) |
| **Outcome** | `outcome(enemy, friendly, outnumber)`; Small+ → `outcome_choice` (pre-set from `definition.outcome`) with the computed value as a suggestion |
| **Glory per knight** | Encounter Glory (battle ledger: fights + manual) + `participation_glory(size, days_fought[pid], outcome, role[pid])` |
| **Plunder per knight** | `plunder(opponents, outcome, decisive_roll, outnumber, role, size)` (V/DV only) |

- Roles default to `conroi` for the knight who commanded most days (Q7), and None for the others.
- `days_fought[pid]` defaults to `len(fought_days)` (Q27).
- **Captives:** foes with `captured_by`, each listed with its captor and a **Roll ransom** action.
  The existing `/api/combat/{cid}/ransom` works only on the active combat, so `/api/battle/ransom {fight, cid}`
  records a `combat.check` with the same text. Ransom money is not stored (paper).

### Events
| Type | Vis. | `data` | Reducer |
|---|---|---|---|
| `battle.aftermath` | gm | `patch: {enemy_kv?: "6 3/8", friendly_pk_losses?: int, gm_knights?: int, gm_losses_roll?: outcome\|null, gm_losses_override?: {killed, captured}\|null, outnumber?: "none"\|"we"\|"they", outcome_choice?: label\|null, roles?: {pid: "conroi"\|"bataille"\|"army"\|null}, days_fought?: {pid: int}, opponents?: "feudal"\|…, decisive_roll?: int, decisive_rolled?: bool}` | merged, latest key wins |
| `battle.finale` | public | `summary: {outcome, outcome_label, line, knights: [{pid, name, encounter_glory, participation, role_label, total, plunder: "£2 ⅔", ransoms: [{captive, amount}]}]}`; table_text `"Victory — Sir Erik 145 Glory, Dame Cwylog 75, Sir Emrys 25"` | `finale` (the Table shows it) |
| `battle.ended` | public | table_text `"The battle is over"` | `status = "ended"` |
| `combat.check` (ransom) | public | as the existing ransom | — |

### Routes
| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| POST | `/api/battle/aftermath` | `{patch}` | `battle.aftermath`, plus the recomputed `aftermath` in the response | 409 not in aftermath; 400 bad values |
| POST | `/api/battle/aftermath/roll` | `{what: "decisive"}` | `battle.aftermath {decisive_roll: 2D3 rolled, decisive_rolled: true}` | 409 not DV |
| POST | `/api/battle/ransom` | `{fight, cid}` | `combat.check` | 404 |
| POST | `/api/battle/finale` | `{}` | `battle.finale` (summary from `aftermath_view`) | 409 not in aftermath |
| POST | `/api/battle/end` | `{}` | `battle.ended` | 409 not in aftermath |

### UI: aftermath panel (`#gm-after`)
- **Header:** `Clash at the Ford · Aftermath · Clash · 1 day` + **Post to Table ▸**.
- **Outcome column:**
  - `Enemy losses (dead + captured) [6 ⅜] KV`
  - `Friendly losses [2] KV` (+ "GM knights in the conroi [n]" with Table 6.5 outcome chips → killed/captured shown)
  - `Outnumbering [none | we 2:1 | they 2:1]`
  - `Ratio 3.2` → big **Victory**
  - "Computed from KV. Every number above is editable."
  - Small+: an outcome select with "suggested: Victory"
  - zero friendly losses → the ruling line with a GR tag
- **Glory column:** a table `Knight | role ▾ | Encounters | Participation | Total`.
  - Participation shows its working, e.g. `10 × 3½ = 35`, and multi-day `45 × 2 days × 1½ = 135` with an SR tag on "× days".
  - Editable days fought per knight.
  - Footnote "Participation: Table 6.6 base × (outcome + leader)…".
- **Spoils column:**
  - Opponent select (Table 6.9) showing `Feudal army · £2`
  - DV: `Decisive +£2D3 [n]` + roll for me
  - `Plunder per knight £2`, `Commander +⅓ £2 ⅔`, or Division/Army lines
  - **Captives** list `Knight of Gorre — Sir Erik [Roll ransom]`, with the result shown after rolling
  - non-victory: "No plunder (Indecisive)"
- Every input posts `/api/battle/aftermath` on change (debounced).
- **After finale:** **End battle** → `/api/battle/end` → the launch panel.
- **Table finale (`#t-finale`):**
  - battle name + "The battle is done" + outcome + flavour line (copy per outcome: DV "The enemy is
    destroyed", V "The enemy breaks and flies the field", I "Neither host gives way", D "The conroi is
    driven back", DD "A rout — the day is lost")
  - one card per knight: shield, name, big `145 GLORY`, breakdown (Foes defeated / Participation (commander) / Plunder / Ransom lines)

### Tests
| Test | File | Asserts |
|---|---|---|
| `test_aftermath_enemy_kv_dead_plus_captured_only` | `test_web_battle.py` | fled and uncaptured unconscious foes excluded |
| `test_aftermath_outcome_computed_and_small_plus_choice` | | |
| `test_zero_friendly_losses_ruling` | | |
| `test_participation_per_days_fought_and_roles` | | |
| `test_plunder_only_on_victory_and_decisive_roll` | | |
| `test_aftermath_is_gm_only` | | `/api/table` has no `enemy_kv` / KV |
| `test_finale_summary_on_table_then_ended` | | |
| `test_leave_the_field_goes_to_aftermath` | | |

### Acceptance
Finish a 1-day Clash, edit the numbers, Post to Table, then End battle. UX acceptance against `#gm-after` and `#t-finale`.

---

## S11 — Log grouping, Battle filter, example battles (size **S**)

**Goal.** The session log groups battle events under `Day N · Turn t` headers and gains a **Battle**
filter. Bedegraine and Carlion ship as ready-made examples.

### Files
- `web/static/js/gm.js`:
  - `FILTERS` += `["battle","Battle"]`
  - `matchesFilter`: `battle` matches events with `data.battle` or type `battle.*`, plus `glory.*`/`combat.*` inside a linked fight
  - `renderLog` inserts header rows (`.log-group`, e.g. `DAY 1 · TURN 3` / `DAY 1 · TURN 3 · FIGHT` / `AFTERMATH`) whenever the battle day, turn or fight changes; the live append path does the same
- `web/static/css/gm.css`: `.log-group`.
- `data/examplecombat.json`: `battles` key with **Bedegraine** and **Carlion** (P9 K4):
  - **Bedegraine:** `size: "huge"` (mockups; Open point 7), 2 days, Intensity fixed 14 / 18, 5 turns per
    day, per-day decks from the scenario, scripts as short paraphrases (e.g. day 1 turn 1 "Always
    choose the Pictish Knifemen this day."), day 2 `on_foot: true`, army commander names.
  - **Carlion:** `commander: "gm"`.
  - Deck and script content comes from the scenario text (book), paraphrased (Q18). Any corpus gap
    found → a rules-issues entry in ttrpg-parser (never write the corpus).
- `core/examples.py`: the merge already covers `battles` (S0).

### Tests
| Test | File | Asserts |
|---|---|---|
| `test_example_battles_valid` | `test_examples.py` | `clean_battle` gives no errors; Bedegraine day 2 `on_foot`; Carlion `commander == "gm"` |
| `test_launch_bedegraine_day2_on_foot` | `test_web_battle.py` | after `day_ended` and re-muster, every pill is On foot |
| `test_examples_merge_adds_battles` | | |

### Acceptance
1. Filter the log to Battle during a turn and check the headers.
2. Merge the examples into a copied `combat.json`, then launch Bedegraine.
3. UX acceptance against the `#gm-turn` log pane (group headers).

---

## Open points

Each item gives the problem, then the recommended resolution (marked **Rec.**). None is a new product
decision unless marked as one for the user to confirm.

1. **Q10 vs design §3.3/§5.** Design §3.3 still lists auto `glory.awarded` events with `source: defeat`
   and `/api/glory/{event_id}/reassign`, but the accepted Q10 derives auto awards on replay, so they have
   no event id. **Rec.:** as specified in S3:
   - auto credit is derived
   - `glory.reassigned {fight, cid, knight}` answers both "Who defeated them?" and reassign
   - the route is `POST /api/combat/{cid}/credit`
   - `glory.awarded` is manual only
2. **Q12 vs design §3.5** ("one `meta.strike` per event"). **Rec.:** one `meta.strike {targets}` per
   cascade, with `flags()` and `gm.js applyIncoming` taught `targets` and a dedicated Restore route (S7).
3. **Table mode name clash.** The existing pin chip labelled "Battle" means mode `combat` (the fight
   board). **Rec.:** relabel it **Fight** (the mode value `combat` is unchanged, so tests keep passing)
   and add a **Battle** chip for mode `battle`.
4. **Knights of Lothian repair is moot.** The user's `combat.json` entry is now identical to the
   baseline (checked 2026-10-17). The baseline fixes (Kerns armour, Archers text, card text) still won't
   reach existing user entries through "absent keys only". **Rec.:** drop the dedicated Lothian repair.
   Offer instead a per-entry, user-confirmed **Restore shipped card** for differing battle-card entries
   (S0), which keeps to the targeted-consent rule of Q19.
5. **Merge scope (Q19).** "Absent keys only" taken literally would never add `mounted` / `countercharge`
   to the user's existing cards. **Rec.:** also insert absent *fields* inside same-named baseline entries,
   skipping `roster` / `core` / `scaling` / `per_player` so a legacy encounter's own scaling isn't
   shadowed (S0).
6. **Example battles: §9 vs §10.** §9 puts Bedegraine and Carlion in S0, while §10 puts them in S11.
   **Rec.:** S11, because they need the S6 `battles` schema and validator.
7. **Bedegraine size.** Design §2.1 shows `"large"` (45 per day). Piece 7 says "Bedegraine: 60/day",
   which is the Huge base, and the approved mockups show "Huge". **Rec.:** `size: "huge"` (piece and
   mockup agree). Confirm against the scenario text when writing the example.
8. **Definition can't express the mockup or Carlion.** `#gm-muster` shows army commanders by name
   ("Arthur", "King Lot"), and Carlion needs "GM commander" pre-set. Design §2.1 has neither. **Rec.:**
   add optional `commander: "gm"|null` and `army_commanders: {friendly|enemy: {name, battle}}` at battle
   level. These are pre-fills only.
9. **Begin Turn 1 without an Intensity.** Design §6.4 gates only on commander and Morale, but ④ needs
   today's Intensity. **Rec.:** also require the Intensity at Mustering. A fixed day is pre-filled, and
   a roll day takes one click.
10. **Multiple Opponents limit.** The design passes `mo_limit` the *knight's* pill. RAW
    (core.combat.multiple-opponents) bases "3 unmounted / 2 mounted attackers" on the **attackers**.
    **Rec.:** use the attackers' pills (2 if any engaged attacker is mounted).
11. **Type-header attacks with several foes.** §14 and `#gm-fight` move attacks into one header per
    type. **Rec.:** with one active foe, a click rolls for it. Otherwise it opens a menu of that type's
    active foes, each with its effective value (Height and modifier).
12. **Crit doubling and the leader.** Q5 says "every roster line"; a leader isn't a roster line.
    **Rec.:** double the roster lines only and keep a single leader (none of the battle cards has one).
13. **Plunder size multiplier below Small.** Table 6.10 has none, yet the Q8 dropdown offers
    bataille/army roles for Clash (their Glory multiplier is valid there). **Rec.:** below Small, plunder
    applies only the conroi +⅓ for any commander role. RAW gives no multiplier, so no ruling is invented.
14. **Changing a posture after Confirm.** No source says how. **Rec.:** postures are local until
    **Confirm postures**. A later change means reopening ⑧ (cascade), and the route rejects a duplicate.
15. **Turn-script placement.** Piece 5 d5 says step ①, while design §6.5 and §14 say ②, with ① now
    implicit. **Rec.:** show scripts beside ② (§14), and also on a rear turn, which honours "at the start
    of the turn".
16. **Opportunity with no roster at ⑨.** There is nothing to fight. **Rec.:** ⑨ shows the rules text and
    Award Glory, and ⑩ is allowed right away. It doesn't add a "fought" day (Q27 says "in any fight"),
    and the aftermath can edit that.
17. **Resume double-counting.** A snapshot taken mid-fight holds both the battle aggregates and the open
    fight. **Rec.:** the battle state keeps closed-fight aggregates separate from the open fight, and the
    snapshot stores the closed part plus the combat (S8). *Implementation choice.*
18. **"Add day" live.** The drawer edits "current + future days", but a 1-day battle has none.
    **Rec.:** allow **Add day** in the settings drawer (`battle.settings {add_day}`).
19. **Random-fight tag semantics.** **Rec.:** an encounter must carry *all* selected tags, which
    narrows the pool as more chips are picked.
20. **Large-shield −2 reminder chip.** No data says which foe carries a large shield, and cards like
    Malahaut already include the penalty. **Rec.:** leave it out of v1 chips; it stays in the card ⓘ text.
21. **"Happened to you" depth.** Design §7.2 says the last 2–3 events, while the approved mockups show
    one **LAST** line. **Rec.:** the server sends up to 3 and the card shows the newest (matching the
    mockup). The full history stays in the Fray.
22. **`fled` now awards Glory.** The ⋯ item "Deactivate (fled / not tracked)" is also used to drop foes
    from tracking, and after S3 it awards Glory (Table A.1 "driven from the fight"). **Rec.:** relabel it
    "Driven off / fled (Glory)" and keep **Remove from encounter** for removals that aren't defeats.
23. **Positions reset at muster** (design §3.2) isn't in any piece. **Rec.:** keep it, because it follows
    P1 d2's per-day engagement reset (scenario rule).
24. **The SKILL.md process changed mid-run** (stage 3½ mockups, spec by an Opus agent, UX acceptance
    per slice). The spec includes the acceptance steps and cites the approved mockups. Screens with no
    mockup (Battles editor, launch panel, settings drawer, examples dialog, Encounters battle panel)
    follow design §6.

## Conflicts between pieces and design.md (pieces win)

- **P1 d7 vs Q10 / §3.3.** P1 d7 calls each award "an undoable/reassignable event", while §3.3 keeps auto
  `glory.awarded` events. The user accepted Q10 (derived awards), which still meets "undoable and
  reassignable". The spec follows Q10 (Open point 1).
- **P7 d1 vs §2.1.** P7 d1 says "Bedegraine: 60/day", but the §2.1 example size is `large` (45). The spec
  follows the piece and the mockup: Huge (Open point 7).
- **P5 d5 vs §6.5/§14.** P5 d5 puts turn scripts at step ①, while §6.5 and §14 put them at ② (Open point 15).
- **P6 d2 vs mockups.** P6 d2 says "no horse-loss reasons recorded", but `#gm-fight` and `#t-battle` show
  "horse killed turn 2" / "On foot · horse killed". **Rec.:** the piece wins. Show `On foot since turn 2`,
  taken from the pill event, with no reason field. The Fray keeps whatever the GM narrated.
- **P6 d5 vs Q16.** P6 d5's "separate small fight" for Alone is superseded by the accepted Q16, which
  makes it a lane in the same tracker. No action is needed.
- **P6 d15 vs §2.4/§4.** P6 d15 ("3 on foot / 2 mounted on one knight") is ambiguous, and design §2.4/§4
  reads it as the knight's pill. RAW uses the attackers (Open point 10).
- **P9 K2 vs §3.5.** P9 K2's cascade covers "every later step in the same turn". Design §3.5 extends it
  to the linked fight's `combat.*` events and Glory. This is consistent with the intent, and the spec
  follows the design.
