# Battles UX pass — GM walkthrough of one Battle Turn (stage 3½)

Scenario: Bedegraine, Day 1, Turn 3. Three knights (Erik commander, Cwylog, Emrys). The GM sets
Pictish Javeliniers; Intensity fails; Erik succeeds at Battle and picks Knifemen, Cwylog crits and
picks Clash of Champions; commander chooses Knifemen; Loss 1D3; postures R/V/P; fight; end turn.

## Clicks as designed (design.md §6.5)
| Step | Clicks | Notes |
|---|---|---|
| ① Take the field | 1 | |
| ② Set Encounter | 2 (open picker, choose) or 1 (Draw) | turn script text shown here |
| ③ Charge | 1 outcome chip | engaged toggle pre-filled |
| ④ Intensity | 1 (roll for me) | |
| ⑤ Picks | 2 per knight (card, crit) + 1 "done" = 5 | |
| ⑥ Commander's choice | 1 | |
| ⑦ Morale Loss | 1 (roll for me) | |
| ⑧ Postures | 3 chips + 1 amount (Reckless 1D3) + 1 Passion = 5 | |
| ⑨ Begin the fight | 1 | |
| ⑩ End turn | 1 | |
| **Total outside the fight** | **≈ 19** | |

## Improvements adopted in the mockups (UX choices)
1. **No "Next" buttons — answering a step completes it.** Each step collapses to its one-line result and the next opens. (−4 clicks vs a confirm-per-step flow.)
2. **① is implicit.** The turn opens on ② with "Retire to the Rear" as a secondary button; setting an Encounter means taking the field. (−1)
3. **③ and ④ share one row** ("Commander's charge roll" and "Intensity roll" outcome chips side by side) — both are quick GM records made in the same breath. Skipped halves grey out.
4. **⑤ picks are card-first:** the deck shows as cards; tap a card, then tap the knight shield(s) who picked it; a crit toggle sits on the shield token. Opportunities are disabled until a crit is set. "Done" disappears: ⑥ opens as soon as the GM taps "Commander chooses". (−1)
5. **⑥ auto-completes** when there is only one candidate (no picks, or all picks the same card).
6. **⑦ shows the minimum check result before the Loss** (GM-only: "Morale 14 ≥ Minimum 5 ✓"), so the GM sees why a forced retire happens.
7. **⑧ postures default to the previous turn's choice per knight** (pre-highlighted, one tap to change, one tap "Confirm postures") — players usually keep their posture. Typical case: 1 click instead of 3. The first-charge turn forces R/V.
8. **Everything the GM must remember is on screen at the step that needs it:** this turn's script text at ②; tokens on the Morale strip glow at the step where they can be used (Force at ②, Negate at ⑦); posture rounds carried into the tracker lane headers; countercharge/barrage results as banners in the fight; "−5 Battle this turn" reminder at ③ when it applies.
9. **Keyboard:** C/S/F/X for outcome chips, R/V/P/K for postures, Enter = primary action of the open step.

Revised total for the scenario: **≈ 13 clicks** outside the fight (≈ 9 on a turn where Intensity succeeds).

## Player-glance check (Table)
- A player finds their knight in the **knights row**: shield + name + Glory, effect chips in tinctures (red harm, green boon, grey state), "happened to you" line. In the fight view the same knight heads a lane.
- Valuable information stands out: the **This turn** card is centre stage; Morale gauge is the largest element; step results appear as a banner over the card ("Intensity fails — choose your fate!").
- Routine noise (round ticks, engagements) stays in the Fray feed only.

## Rejected alternatives
- Wizard (one step per screen): hides the turn's history; rejected in piece 5.
- Auto-rolling the GM's Loss when ⑦ opens: removes the GM's moment of choice and the option to roll physically; kept as one click.
- Postures defaulting to Valorous for everyone: silently picks for the players; "previous turn" default only applies from turn 2 and is visibly highlighted.

Mockups: docs/design/battles/mockups/battles-ux-mockups.html (published privately at https://claude.ai/artifact/5h22dkrAiak61UpDS3pW3C) — **APPROVED by the user 2026-10-17**, including UX choices 1–9.
