# Pendragon web app — design

The web app replaces the Tkinter desktop app. This records the decisions made
when designing it, and the architecture that follows from them.

## Decisions

| Decision | Choice |
|---|---|
| Stack | FastAPI + uvicorn + Jinja templates + vanilla JS modules (no build step), JSON files (no database). Launched like jobfinder: `launch.sh` (venv, detached server, pidfile, `/healthz`, open browser) / `stop.sh`. Port **8020**, bound to 127.0.0.1. |
| How players see it | The GM opens the **Table screen** (`/table`) in its own window and shares it with Discord *Go Live*. Designed for streaming: large type, high contrast, legible at 720p. Discord webhook posting may come later. |
| Backbone | Every action is a typed **event**. The **session log** is the ordered event list; the Table screen and the saved session file are views of it. |
| Visibility | Every event carries `visibility` (`public`/`gm`) and `masked`. Almost everything is public. The only GM controls exposed: the dice tray's **Secret** toggle (a sealed card on the Table, revealable later) and private **Notes**. Bookkeeping events (modifier changes, removing a combatant, strike/unstrike) are GM-only. |
| Sessions | Explicit **Start / End session**; one active session; autosaved after every event to `sessions/<date>-<slug>.json`; reopen to append. With no session, events go to an unsaved scratch log (the Table still works). Library edits (adversaries, encounters, party, cast) are prep and aren't logged. |
| Corrections | Append-only. **Strike** an event (it disappears from the Table, stays struck-through in the log, and stops counting); combat state is rebuilt by replaying un-struck events, so undo is always exact. |
| Migration | Game logic extracted into UI-free `core/` (with tests); the Tk app runs on `core/` during the transition and is deleted once the web app has replaced it in play. |
| Look | GM console: dark "great hall at night", candle-gold, heraldic tinctures for meaning. Table: parchment, illuminated initials, heraldic battle board. |
| GM console layout | Three panes: tool rail · active tool · live log with the dice tray docked beneath. |
| Table modes | **Chronicle** (newest event spotlit, earlier events as a feed) and **Battle** (knights vs foes board + "the Fray"), switching automatically when combat starts/ends; the GM can pin either. |
| Foe health on the Table | Described wound states only — Unhurt / Wounded / Badly wounded / Unconscious / Near death / Slain / Fled. Knights show exact HP. |
| Dice tray | Free notation, quick dice, Pendragon check (critical / fumble / critical bonus), opposed roll, label, Secret toggle. Every click-to-roll in the app uses the same engine (`core.dice`). |
| Narration | A Narrate box (read-aloud, scene title, image link) and "Present" on NPCs to spotlight their read-aloud description. |
| Party | Lightweight records for the player knights (`data/party.json`): join combats automatically, set encounter scaling, HP carried back after combat. |
| Cast | NPCs kept across sessions with private notes (`data/cast.json`); replaces the per-session roster; old roster JSON files import. |
| Exports | All desktop exports kept (statblock, Markdown, image prompt, Cymric sheet PDF); the combat-log save is replaced by the session file + **Chronicle** (Markdown / web page). |
| Rules lookup | Search the rules corpus index from the console; show a rule on the Table. |

## Architecture

```
core/                      pure game logic (no UI) — shared by both apps
  dice.py                  the one roll engine: checks, opposed, damage, notation
  npc.py names.py          NPC generation + statblock/description formatting
  combat.py                Combatant (serialisable, shared HP/wound logic), Encounter
  adversary.py encounter_def.py  creator helpers
  battle.py                every Battle rule (GM ch. 6) as pure tables/functions
  examples.py              bring new shipped examples into the user's combat.json (adds only)
  battle_def.py            saved battle definitions: battle → days → turn scripts
  rules.py pdf_export.py   rules data loading, combat.json persistence, PDF sheet
web/
  app.py                   create_app(): routes, static, templates
  state.py                 AppState: rules, generator, sessions, hub, party/cast stores
  sessions.py              Session / SessionStore — the append-only event log
  combat_state.py          reduce(events) -> live combat; gm_view / table_view
  battle_state.py          reduce(events) -> live battle (Morale, day/turn, army rolls, tokens); pause/resume
  table.py                 the player-safe projection (filters secrets server-side)
  hub.py                   server-sent events: "something changed" pings
  rules_index.py           rules corpus search (reads the rules_corpus symlink) + markdown rendering
  routes/                  session, rolls, npc, cast, party, combat, library, rules
  templates/ gm.html table.html
  static/js/ gm.js (shell, log, tray) table.js lib.js tools/<tool>.js
  static/css/ gm.css table.css tools.css tools/<tool>.css
```

### Events

```json
{"id": 17, "ts": "2026-10-16T19:02:11", "type": "roll.check",
 "visibility": "public", "masked": false,
 "title": "Sir Bors — Valorous", "text": "Sir Bors rolls Valorous (15): 12 — SUCCESS",
 "data": {"label": "Valorous", "value": 15, "roll": 12, "outcome": "success"}}
```

- `text` is the GM log line; `data.table_text` (optional) is the player-safe
  line the Table shows instead (e.g. a foe's HP change becomes "is hit — Wounded").
- Combat events hold **deterministic** changes: `combat.started` / `combat.added`
  carry full combatant snapshots (HP jitter, looks already rolled); `combat.hp`
  carries a delta; promotions carry the config. Never re-roll in the reducer.
- Types: `session.*`, `roll.dice|check|opposed|damage`, `combat.*`,
  `npc.generated|updated|presented`, `narrate`, `note` (GM), `rule.shown`,
  `party.hp`, `meta.strike|unstrike|reveal`.

### Live updates

The server publishes a tiny SSE message on every change. GM consoles fetch
`/api/session/events?after=<last id>` (the log is append-only, so this never
misses anything) and the combat view; the Table refetches `/api/table`.

## Combat (kept deliberately simple)

The tracker shows **one lane per knight** holding the foes engaged with them, a
shared stat header per foe type (attacks clickable to roll), one line per foe
(HP bar, wound word, target chip, Hit, ±HP, ⋯), a **Not engaged** pool and a
**Defeated** strip (unconscious, slain, fled, surrendered). Drag a foe to a lane
or use its target chip to retarget (`combat.engage`; `with: ""` = the pool).
Each combatant has a **Mounted / On foot** pill (`combat.mounted`; knights start
mounted unless the launcher says otherwise). Height ±5 is worked out from the
engaged pair's pills and added to foe attack rolls automatically; a foe going for
the horse (`combat.horse`) loses its −5, and the GM can negate Height for a
two-handed spear (`combat.height`). Knight lanes show their own Height and
Multiple Opponents reminders; captives are flagged with `combat.captured`.
**Distribute foes equally** (`combat.distribute`, one event, one strike to undo)
spreads the foes still fighting evenly over the knights still in the fight; foes
already on a knight stay while he's under his share, and defeated foes never move,
so their Glory stays with the knight they fell to.

**Glory ledger.** A defeated foe's Glory (Table A.1: unconscious, slain, fled or
surrendered) goes to the knight it was fighting when it fell. This is derived on
replay, so striking the defeating event removes it. A foe that fell unengaged
prompts "Who defeated them?" (`glory.reassigned`, also used to reassign);
**Award Glory** (`glory.awarded`) covers rewards and deeds. The Table's fight
view shows one lane per knight built from reusable board components
(`static/js/board.js`): knight card with Glory counter, reminder chips and the
last thing that happened to them (from events' server-only `touches`).

**Random fight** (Combat launcher) draws an encounter carrying every picked tag,
never an Opportunity. Encounters can be marked **Foe** or **Opportunity** for
battle decks, with Minimum Morale, Morale Loss, a missile flag and rules text;
`GET /api/battle-decks` lists them with their GM-only mechanics.

Player knights are run on paper: the app never tracks their Hit Points,
armour, wounds or death. It only tracks the enemies.

- **Knights** are names in the fight. The GM can mark one **Down** or **Out of
  the fight** (and back). The Party tool is just the roster: name, player,
  notes, active.
- **An enemy attacks a knight**: click the enemy's weapon skill. The app rolls
  it; the GM clicks the knight's result — critical, success (beat / equal /
  under the enemy's roll, only asked when both succeed), fail, fumble — and
  Table 7.1 (Core p.133, `core.combat.resolve_attack`, every cell tested)
  decides. If the enemy hits, the app rolls its damage (+4D6 on its critical)
  and **reports** it with the protection that applies (armour only, or armour
  + shield/parry on a partial success or tie). Nothing is applied to the
  knight.
- **A knight hits an enemy**: *Hit* on the enemy (it opens automatically when
  the knight wins or ties the attack above, with the shield box set). Enter
  the total damage the player rolled; the enemy's armour (and shield, if
  ticked) comes off and the enemy's wound, Major/Mortal Wound and knockdown
  are worked out and applied.
- **Who's fighting whom**: each enemy has a dropdown of the knights; knights
  show "fought by …". The Table shows the same.
- All combat rolls are public; the dice tray's Secret toggle is the only way
  to hide a roll.

## Battles

A **battle** is a container of fights with its own state (docs/design/battles/).
Prepare saved battles in the **Battles** tool (`combat.json` → `battles`: size,
days, per-day Intensity/turns/switches/deck/turn scripts) or launch a quick one
from the **Battle** tool with just a Size. Launching copies the definition into
`battle.started`; the GM musters the conroi (knights, commander, starting Morale
the players worked out, Army Commander rolls for Clash+, today's Intensity), and
the Morale strip, tokens and live settings run from there. Ending a session
with a battle running writes `battle.paused`; **Resume** in a later session
writes `battle.resumed` with a full snapshot. The Table's battle view shows the
title band, the Morale gauge (number, draining bloodied fill, band word) and the
Fray. Player rolls are resolved at the table; the GM records outcomes.

Each turn runs as a **stepper** (Set Encounter → Charge · Intensity → Picks →
Commander's choice → Morale → Postures → Fight → End turn), every outcome posted
to `POST /api/battle/step` (the single entry point a future dice source can
use). The reducer checks each event against the step machine; an event that no
longer fits after a strike is listed as inconsistent, not applied. Reopening a
step strikes it and everything after it this turn in **one** `meta.strike`
with `targets` (Restore unstrikes them). Retiring, resting at the rear, forced
retires, Opportunities once per battle and the Force/Negate tokens are handled
here.

Step ⑨ **Begin the fight** launches an ordinary tracked fight linked to the turn
(`combat.started.data.battle`), scaled to the knights with the conroi (Cowardly
knights don't count; Alone knights get a lane), doubled on an Intensity
critical, with each knight's pill, posture and rounds. The battle reducer folds
linked fights into plain summaries (defeats, KV, Glory, who fought); End turn
adds the KV Morale gain (half up per Encounter, a GM ruling). Barrage and
countercharge are recorded before the fight. The tracker shows a battle frame
(Morale strip, banners, posture rounds, +1 round, Back to battle) and the
Table's fight view a battle header with compact Morale.

Between fights the Table's **battle view** tells the turn's story: a result
banner, the GM's card beside the knights' picks (card frames with name and
flavour only, Opportunities gold), today's battlefield as names (in play
outlined, spent struck through), revealed turn scripts, the Morale gauge, the
Fray, and a knights row (battle Glory, chips such as Commander / May charge /
posture / Passion / At the rear, and the LAST line). `battle_state.table_view`
sends only these fields — never Minimum, Loss, KV, card mechanics, dice or tokens.

After the last turn of the last day (or Leave the field) the battle enters its
**aftermath**: Outcome (enemy KV from dead + captured foes, friendly losses with
the Table 6.5 helper, outnumbering, ratio → result; Small+ battles let the GM
choose), Glory (encounter Glory + participation by days fought and role) and
Spoils (Table 6.9/6.10 plunder, captives with Roll ransom) — all editable
(`battle.aftermath`, GM-only). **Post to Table** (`battle.finale`) shows the
finale; **End battle** (`battle.ended`) closes it.

The GM log groups battle events under `Day N · Turn t` (and `· Fight`,
`Aftermath`) headers, with a **Battle** filter. Bedegraine and Carlion ship as
example battles in `examplecombat.json`; Encounters → Examples… adds them to the
user's library.
