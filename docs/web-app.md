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
  rules.py pdf_export.py   rules data loading, combat.json persistence, PDF sheet
web/
  app.py                   create_app(): routes, static, templates
  state.py                 AppState: rules, generator, sessions, hub, party/cast stores
  sessions.py              Session / SessionStore — the append-only event log
  combat_state.py          reduce(events) -> live combat; gm_view / table_view
  table.py                 the player-safe projection (filters secrets server-side)
  hub.py                   server-sent events: "something changed" pings
  rules_index.py           rules corpus search + markdown rendering
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

## Combat rolls and blows (follow-up)

- **All combat rolls are public** — characteristic, weapon-skill and skill
  rolls show their target value on the Table, and click-to-roll never uses
  the Secret toggle (that belongs to the dice tray only).
- **Who's fighting whom**: each combatant's *fighting* dropdown lists the
  other side (foes pick knights, knights pick foes, plus "Other…"). The Table
  shows "fighting X" on a combatant and "fought by X, Y" on its opponent.
- **Blows** (`POST /api/combat/blow`, `core.combat.resolve_blow`): clicking a
  weapon's damage (or *Hit* on the target) resolves one blow per Table 7.1 —
  the attacker's result (success / critical: +4D6, +2D6 unarmed), the
  defender's (failed → armour only; partial/tie → armour + shield/parry),
  rebated (crit dice first, then halve; knockdown on the full roll), reckless
  (+2D6 / +6D6, no shield/parry), axes through shields (1D6, a 1 breaks it),
  maces vs mail, extra dice. A knight's blow takes the damage the player
  rolled. The wound is applied (Major/Mortal Wounds follow), knockdown is
  flagged (> Knockdown: DEX roll; > twice: automatic), and the whole
  breakdown is shown to the players. Strike the log entry to undo it.

## Exchanges (Table 7.1)

**Fight** on a combatant runs one combat round (`POST /api/combat/exchange`,
`core.combat.resolve_exchange`, checked cell by cell against Core p.133 in
`tests/test_exchange.py`). The app rolls for anyone with attacks; for a player
knight the GM enters the skill (pre-filled from the Party sheet's values) and
the player's d20. The four results on each side become: winner strikes the
loser (+4D6 on a critical; the loser gets shield/parry only on a partial
success, i.e. a lower success), a tie (equal successes, or critical vs
critical — both strike, both get shield/parry, no +4D6), or both lose (nobody
hurt). Fumblers drop a sword or break other weapons; swords break
non-sword, non-dagger weapons on a tie, and any weapon when the loser fumbles
and the sword-wielder criticals. Strikes by app-rolled weapons are applied
at once; a knight's strike asks for the player's damage dice.
