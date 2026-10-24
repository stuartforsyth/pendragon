---
name: recap
description: Turn a session log into a player-facing session recap. Reads a session file, condenses it into per-turn facts, has Opus narrate each day and turn (who was met, criticals, foes taken down, grievous wounds to the knights), then checks every name and number against the log. Use for /recap, or when Stuart asks for a recap, chronicle or "previously on" of a session.
argument-hint: "<session id | path | latest>"
---

# Session recap

Writes `recaps/<session-id>.md`: a chronicle the **players** read before the next session.
Decisions below were settled with Stuart (grilled 2026-10-23, tested on Session 4).

## Steps

1. **Facts (Sonnet, deterministic):**
   `.venv/bin/python -m core.recap_facts <sessions/ID.json | latest> > $SCRATCH/facts.md`
   It honours strikes, keeps only public events, and groups by battle turn. Read the file.
   A "previously" opener: if another session in `sessions/` is the same battle's earlier log, read its last
   few public events and give the narrator one line of context. If there is none, no opener.
2. **Narrate (Opus):** spawn `opus-specialist` with effort `high`. Give it the facts file path, the voice
   rules below and the output layout. It returns the recap text; it does not write files.
3. **Check (Sonnet):** compare the draft with `facts.md`. Every name, number, kill, wound and critical must
   appear in the facts. Remove anything invented. Confirm no GM-only content or foe stats leaked.
   Fix small slips yourself; send back to Opus only for a structural miss (one retry).
4. **Write** `recaps/<session-id>.md` (create `recaps/`). Show Stuart the path and the opening paragraph.

## Voice and rules for the narrator

- **Chronicle prose**: a Pendragon-era scribe, past tense, plain but formal. Knight-focused, third person.
- **Layout:** title and one-line battle frame; then for each **Day**, for each **Turn**: a heading
  (`Day 2, Turn 1: The Cambrian Archers`), a short paragraph, then a **Deeds of note** box of one-line
  bullets. Fold turns with nothing notable (rests) into a single line.
- **Markers in the box:** ⚔ critical, ☠ foe slain, ⚠ grievous wound to a knight or a knight going down,
  🐎 a mount struck, `+N Glory` after a foe is defeated.
- **Who was met:** open each turn with the encounter's flavour text, in the narrator's voice. Name an
  individual foe only for a kill, a critical, or a described one (Pikeman 4's scar, Kern 8's slave-mark).
  The rest are a group ("the pikemen").
- **Knights:**
  - **Grievous** means a tag in the facts (`GRIEVOUS`, `KNIGHT DOWN`): a critical, or a single hit of 25+.
    Never state a Major Wound for a knight; the log doesn't record one.
  - **Mounts:** blows on horses are `MOUNT HIT`, never a wound to the knight.
  - **Sir Erik the Cruel:** his fights are not in the log. Say he held the flank, unrecorded; never invent
    deeds. He is absent on Day 2 unless the facts say otherwise.
- **Fidelity:** colour is allowed (weather, the look of a blow); facts are not invented. Every name, number,
  kill, wound and outcome comes from the facts file. Few or no quoted speeches.
- **Scripted story:** where the facts carry a "Scripted story" line (the battle module's own events, e.g. Day 2:
  Lot's charge up the hill), weave it in as flavour. Don't say the knights did more than the beats record; for
  turns they spent resting at the rear, report scripted events as word reaching the rear.
- **No invented outcomes:** the log says only what the facts say. Do not write that foes fled, broke, gave way
  or were routed, that a mount was lost or killed, that a fight ended in any particular way, or that one blow
  caused a later event, unless a fact says so. (A first Opus draft did all four; the check step caught them.)
- **Players only:** leave out rule cards shown, aftermath edits, foe hit points and damage dice. Damage on a
  knight appears only as "a critical stroke for 29".
- **Glory:** per fight, in the box, only what the facts list as logged. Close with one table headed
  *Glory from foes defeated* (battle Glory is not calculated yet; never print the finale totals).
- **Day boundaries:** "Day 1 ends" and the muster appear at the top of the next day's first turn in the
  facts; narrate them as the day break.

## Known limits

- Knight wounds are inferred from damage size; the log has no Major Wound state for knights.
- Fights are not logged for a knight whose player hasn't been played out (Sir Erik tonight).
- Turn numbers come from `battle.turn_ended`; a fight's own "Day N, Turn M" label can differ.
