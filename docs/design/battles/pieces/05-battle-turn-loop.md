# Piece 5 — The Battle Turn loop — CLOSED 2026-10-17

## Decisions
1. Each turn opens with the commander's choice: "Take the field" or "Retire to the Rear" (voluntary). Forced retire happens at step ⑥ when nothing selectable is within Morale. At the rear the choice is "Rest another turn" / "Return to the field" / "Leave the field".
2. Rest turns: commander's 1D6 rolled at the table, GM enters it, app adds capped at starting Morale; turn counter advances. After resting stops: return next turn or Leave the Field (ends the conroi's part for the day → aftermath). Rear reminders (First Aid 14+1D6 per knight; remount by Squire/Horsemanship) are table play; a remount flips the knight's pill to Mounted.
3. Postures per knight (R/V/P/C, rounds 3/2/1/0 shown); first-charge turns offer only R/V. Reckless: 1D3 entered as Morale gain; Prudent: 1D3 entered as Morale loss; Cowardly: knight individually retired, and if the player reports above half HP, 1D6 entered as Morale loss. Trait checks and −1 Honor are paper, with a board reminder.
4. Passions: per-knight "Passion used" toggle (optional Passion name), reset each day; second use in a day is an overridable warning; effects played at the table.
5. Turn end: Squire rolls are table play (remount flips pill); "End turn" applies the KV Morale gain (capped; piece 6), advances; last turn → "End day" → next day's re-muster or, on the last day, the aftermath. Turn scripts: text shown to the GM at step ①; "only if Intensity succeeds" scripts revealed on the board after a successful Intensity roll; their restricted deck applies to the set Encounter and picks.

## UI
- Live Battle tool = vertical stepper for the turn: header "Day N · Turn t of T" + Morale strip with tokens; steps ① field/retire, ② set, ③ charge, ④ Intensity, ⑤ picks, ⑥ commander, ⑦ Morale, ⑧ postures (R/V/P/C chips per knight + Passion toggles), ⑨ fight → combat tracker, ⑩ End turn/End day. Done steps collapse to a one-line result (reopenable for undo); current step expanded; non-applicable steps greyed.
- At the rear the stepper shows the rest choice + "Rest roll" entry + reminders.

## House rules
- None (Passion reset per day and per-day re-muster follow the scenario rule from piece 1).

## Rejected / out of scope
- Tracking trait checks, Honor, First Aid results.

## Open questions
- None.

## Interfaces
- Piece 6: per-knight positions (Cowardly retire, escort, Alone on the Field), rounds per posture in the fight, KV Morale. Piece 7: Leave the Field / last day → aftermath. Piece 8: board shows postures, Passion use, rest state.
