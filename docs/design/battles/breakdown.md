# Battles — breakdown (stage 1)

Status: **draft, awaiting user agreement on the piece list.**
Sources: GM Handbook ch. 6 pp. 121–148 (corpus `gm.battle.*`), Battle Cards PDF (12 foe
conrois — already imported as adversaries/encounters, see `docs/encounter-generator-spec.md`
§5.2). Gaps in the corpus: **Opportunities (pp. 143–148)** and the Battle Cards deck as prose
— reported to the rules-issues queue; design must not depend on them being extracted yet.

User goals (from the request): run battles as a GM; track conroi **Morale**; present
encounters to players as **nice battle-card representations**; **randomise** an encounter from
a list of **battle-approved** encounters; **roll Intensity** and follow the **main battle
sequence**; the GM's own VTT handles some parts (scope tags below decide which).

## The whole sequence, start to finish

**A. Before the battle**
1. Set the stage: sides, forces, Army Commanders and their Battle Skill (2D6+10 if unknown),
   Battle Size (Table 6.1: max turns, random Intensity) and Intensity.
2. Build the two Encounter decks: **Foes** (recur) and **Opportunities** (once, critical
   Battle roll only).
3. Players form the conroi: makeup, leader, shared Passion → starting **Morale** (average,
   +5 if all the same; it can never exceed its start).
4. Army Commander rolls (Clash and up, Table 6.2 modifiers): friendly success → turn 1 is a
   mounted charge, fumble → army −5 Battle; enemy success → GM forces one Encounter,
   fumble → conroi commander may negate one Encounter's Morale effect.

**B. Each Battle Turn (up to the size's max turns)**
5. Set Encounter (GM default) + any turn-keyed Battle Events; Mounted Charge Opportunity roll
   (Table 6.3; turn 1 is always a charge unless the commander failed).
6. Intensity roll (GM, unopposed): stands / crit doubles foes / fumble gives an Opportunity /
   failure lets PKs reroll.
7. Battle roll (each PK who wants to change): success = choose an Encounter, critical =
   choose an Opportunity.
8. Select Encounter (conroi commander); below its Minimum Morale → Retire to the Rear.
9. Reduce Morale by the Encounter's Morale Loss.
10. Select Posture (Reckless / Valorous / Prudent / Cowardly: rounds fought and Morale
    effect), invoke Passions (once per battle).
11. Fight the Encounter (normal combat; chance of countercharge; missile barrage rounds;
    Multiple Opponents). Gain Glory per foe; raise Morale by defeated foes' KV.
12. Squire Skill roll (optional): replacement lance, horse, escort prisoner, bear a wounded PK.
13. Between/within turns: Retire to the Rear (restore Morale, treat wounds), Alone on the
    Field, Surrender/flee checks for foes, Capture and Ransom, disobeying orders.

**C. After the battle**
14. Tally losses in Knight Value (Table 6.4; Conroi Losses Table 6.5 for GM knights) →
    outcome ratio (decisive victory … decisive defeat).
15. Glory: participation (6.6) × outcome (6.7) × leader (6.8), on top of per-foe Glory.
16. Ransom and plunder (6.9, 6.10); post-battle record in the session log.

## Pieces (proposed order, with first-guess scope)

| # | Piece | Covers | First-guess scope |
|---|-------|--------|-------------------|
| 1 | Battle setup | steps 1–2: size, intensity, commanders, sides | app |
| 2 | Conroi & Morale | step 3, Morale tracking all through | app |
| 3 | Encounter decks | step 2: battle-approved encounters, Foes vs Opportunities, random draw, tagging in the library | app |
| 4 | Commander rolls & first charge | step 4, 5 (Table 6.2/6.3) | app (assist) |
| 5 | The Battle Turn loop | steps 5–10: intensity roll, battle rolls, selection, morale loss, posture | app |
| 6 | Fighting an Encounter | step 11–13: links the turn to the existing combat tracker (rounds per posture, barrage, countercharge, surrender, retire, alone) | app on top of existing combat |
| 7 | Aftermath | steps 14–16: KV tally, outcome, Glory, ransom, plunder | app / assist |
| 8 | Players' view (Table) | battle-card presentation, what players see and what stays secret (Intensity, Opportunities, enemy deck) | app |
| 9 | Events, undo & log | event types, replay, session log, integration with `combat_state` | app (cross-cutting) |

Cross-cutting: every action an event (deterministic deltas); the Table projection filters
secrets server-side (`web/table.py`); GM can correct any value (strike/reveal events).

## Gate

Do these pieces, this order, and these first-guess scopes look right? Then grill piece by
piece.
