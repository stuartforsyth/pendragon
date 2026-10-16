---
name: design-mechanic
description: Iterative design process for adding a whole game mechanic (battles, feasts, tournaments…) to the Pendragon web app — break the mechanic's full sequence into pieces, grill the user on each piece, have Opus compile the answers into one design, get approval, write the spec, then build. Use when the user wants to add or rework a multi-step game mechanic, says "design battles/feasts/…", or invokes /design-mechanic.
argument-hint: "{mechanic} e.g. battles, feasts"
---

# Design a game mechanic, piece by piece

For **$ARGUMENTS**. Every mechanic gets the same pipeline, with a gate between stages. State
lives in files under `docs/design/{mechanic}/` so the process survives context loss — always
re-read them before continuing. Never skip a gate; never start building before the spec is
approved.

```
docs/design/{mechanic}/
├── breakdown.md        # stage 1: the sequence and its pieces, with scope decisions
├── pieces/NN-slug.md   # stage 2: one decision record per piece
├── design.md           # stage 3: Opus's compiled design  (approval gate)
└── spec.md             # stage 4: build spec              (approval gate)
```

## 1 — Break down the sequence

1. Read the mechanic's rules from the **rules corpus** (`rules_corpus/`, see CLAUDE.md —
   corpus first, PDFs only for gaps; file an issue in the rules-issues queue for corpus
   errors). Read the existing code that already touches it (`core/`, `web/`, events in
   `web/combat_state.py`, the Table projection in `web/table.py`) and `docs/web-app.md`.
2. Write `breakdown.md`: the **whole sequence from beginning to end** as ordered steps, then
   group them into **pieces** — a piece is a unit you can design and build on its own (a
   phase, a roll, a tracker, a screen, a player-facing view). For each piece give: what the
   rules say (cite corpus ids/pages), what already exists in the app, and a first-guess
   scope tag: **app** (automate/track it), **assist** (prompt or reference only), or
   **paper/VTT** (the GM handles it elsewhere — not implemented).
3. Also list the cross-cutting concerns: events needed, what the Table (players' screen) may
   show and what stays secret, GM-only controls, undo.
4. **Gate:** show the user the piece list and order; adjust until they agree. Then number
   the pieces.

## 2 — Grill each piece

For each piece, in order, one at a time, invoke the **`mattpocock-skills:grilling`** skill:
relentless, one-question-at-a-time interview with a recommended answer for each question,
until the design for *that piece* is settled. Ground questions in the rules text and the
current app — don't ask what the corpus already answers. Explicitly settle: scope tag (the
user will drop things they run in their own VTT), GM workflow, what is rolled vs chosen,
state/events, player-visible output, edge cases and rules ambiguities.

**Then hold a UI conversation for the same piece — never skip it, and never leave UI to be
decided at build time.** Settle, one question at a time with a recommendation: where it lives
(which GM tool/tab/panel, or the Table); the elements it needs (every input, readout, button,
list, roll control, status chip, warning); what each shows and when (empty, in-progress,
done, error states); the primary GM flow in clicks (what is one click, what needs
confirmation, what is automatic); what the players' Table shows for it and what is hidden;
how it looks (reuse existing patterns/components in `web/static/js/tools/` and the CSS
tokens; ask before inventing a new visual idea); and mobile/desktop and keyboard needs. Offer
a quick ASCII sketch for layout choices (AskUserQuestion previews work well) and settle on
one. Pieces tagged **paper/VTT** skip the UI conversation.

**Review every decision the user makes — you are a design partner, not a scribe.** After each
answer (rules, workflow or UI), before recording it, run a quick critical review and say the
result out loud:

1. **Rules check.** Does the decision break a rule of the game or add something the rules do
   not contain? Check the corpus (cite id/pages; PDFs for gaps). Classify it as **RAW**
   (as written), **house rule** (deliberate departure or addition), or **conflict** (breaks
   the rules by accident). Never let a house rule slip in unlabelled: name it, say what the
   book does instead, and ask whether it is intended. Record house rules in the piece file
   under **House rules** with the book rule they replace, so the design, spec and UI can
   label them.
2. **Better-way check.** Is there a simpler, safer or more useful way to get the same
   outcome? Consider: fewer clicks or fewer states; what the GM does mid-session under
   pressure; consistency with existing tools and the event-sourced model (undo, replay,
   deterministic deltas); whether it makes the Table leak secrets or clutter; edge cases it
   mishandles; cost versus value (the user may be better served by *assist* than *app*).
3. **Challenge, with a recommendation.** If a decision is weak, say so plainly and propose the
   alternative with the trade-off; don't just ask "are you sure". Don't defer to the user
   because they decided it — and equally don't relitigate a decision after they have heard
   the challenge and chosen to keep it: record it, with the concern noted, and move on.
   Agreement is allowed to be the whole review when the decision is sound — say why in a line.

After each piece write `pieces/NN-slug.md`: **Decisions** (final, numbered), **UI** (location,
element list, states, GM flow, Table view, sketch), **House rules** (departures from the book, each with the rule it replaces), **Rejected / out of scope** with the reason, **Rules cited**, **Open questions** (should be empty before
moving on), and **Interfaces** to neighbouring pieces. Read the user back a 5-line summary
and get a yes before the next piece. Later pieces may reopen earlier ones — edit that file
and note why.

## 3 — Compile the design with Opus

When every piece file is closed, launch one **Agent** with `model: "opus"` (a fresh agent,
not a fork). Its brief must name the files to read — `breakdown.md`, all `pieces/*.md`,
`CLAUDE.md`, `docs/web-app.md` — and say: reconcile the pieces into **one coherent design**
(data model, event types and replay, `core/` vs `web/` split, API routes, GM UI (consistent
across pieces: shared components, navigation between pieces), Table projection and secret filtering, rules coverage, build order); flag contradictions or gaps
between pieces rather than papering over them; independently review the whole for rules
violations, unlabelled house rules and better alternatives, and report them; invent no decisions the user did not make —
list them as questions. Output `design.md`.

**Gate:** relay the design's summary and its open questions to the user. Resolve questions
(back to stage 2 for the affected piece if needed). The user must explicitly approve
`design.md`.

## 4 — Spec

Write `spec.md` from the approved design: ordered build slices each shippable on its own,
with files to touch, event schemas, route signatures, UI elements and behaviour per slice, and **tests per slice**
(real behaviours, run against copies of the data per CLAUDE.md). **Gate:** user approves.

## 5 — Build

Implement slice by slice following the spec and project rules (logic in `core/`, every action
an event, deterministic deltas, Table data filtered server-side). Run the test suite after
each slice, run the app to see it working, commit per slice when the user asks. Update
`docs/web-app.md` and tick the spec off. Deviations from the spec are surfaced to the user,
not silently made.

## Notes

- **Players roll and resolve at the table; the app is not a VTT.** The GM screenshares the
  Table; players roll physical dice, work out their own results (success, crit, sums,
  averages such as starting Morale) and tell the GM. That table-side work is part of the fun —
  never design the app to take it over, and never require player-knight profiles (skills,
  Passions) in the app. The GM records only the **outcomes and amounts that change tracked
  state** (e.g. "Battle roll succeeded, chose Pictish Knifemen", "rest roll 4"), and the app
  enforces the rules on them (caps, minimums, what an outcome permits). Don't ask for a roll
  that changes nothing the app tracks. GM-side rolls (Intensity, NPCs) may offer "roll for
  me". A later design phase may add VTT-style player dice; keep outcome capture behind one
  entry point so it can plug in, and note it in each design.

- One mechanic at a time; feasts and others reuse this process unchanged.
- Keep the user's VTT boundary explicit: anything tagged **paper/VTT** stays out of the build.
- If the user adds a request mid-process, record it in the relevant piece file, don't drop it.
