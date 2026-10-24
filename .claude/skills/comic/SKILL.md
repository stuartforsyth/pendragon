---
name: comic
description: Turn a session log into copy-paste Nano Banana (Google) prompts for a period-accurate three-panel comic strip. Reuses the shared style and character sheet in comics/, writes panel scripts from the session facts, and saves them as sessions/<id>.comic.md for Stuart to edit. Use for /comic, or when Stuart asks for a comic, comic strip or pictures of a session.
argument-hint: "<session id | path | latest | file.md> [strips]"
---

# Session comic prompts

Writes `sessions/<session-id>.comic.md`: ready-to-paste Nano Banana prompts, three panels per strip.
Optional second argument: the number of strips (`/comic latest 2`). Default 4 (12 panels). A short session gets
fewer strips; pick the strips-worth of moments that matter most and keep story order. If Stuart gives no number
and the session is short (about one fight), use 1-2 strips rather than padding to 4.
Decisions settled with Stuart (grilled 2026-10-23, tested on Session 4).

**Markdown source:** the first argument can be a `.md` file (a recap in `recaps/`, or Stuart's own notes) instead of
a session. Then skip the facts step and give Opus the Markdown as the only source of events: panels may show only
what it says. Write to `sessions/<md-file-stem>.comic.md`. Everything else (style, characters, strips, checks)
is the same. Say so in the report: a Markdown source carries no log tags, so criticals and wounds appear only
where the text mentions them.

## Shared files (reuse every session; Stuart edits them)

- `comics/style.md`: the art style and the period/gear rules, pasted at the top of every prompt.
- `comics/characters.md`: the three knights' fixed looks. Add a line `- Name: look` for anyone new; the
  assembler pastes only the lines for knights who appear in a panel.
If Stuart says "use the same prompt", change neither file. If he edits them, use his edits.

## Steps

1. **Facts (Sonnet):** (Markdown source: skip this; use the file itself.) `.venv/bin/python -m core.recap_facts <session> > $SCRATCH/facts.md`. Also read
   `recaps/<session-id>.md` if it exists, for the story order.
2. **Panel scripts (Opus):** spawn `opus-specialist`, effort `high`. Give it the facts file, `comics/style.md`
   and `comics/characters.md`; it returns JSON only (shape in `core/comic_prompt.py`). Rules for it:
   - 1-2 panels per battle turn, 3 x N panels, where N is the strip count (default 4, so at most 12; every strip exactly 3 panels). Rest turns get a panel only if
     the scripted story gives one. Pick the moment that matters: an establishing view of the foe, then the key
     deed (criticals, foes slain or felled, a knight going down).
   - `scene` is purely visual: framing, who is where, action, setting, weather. No text, speech or sound words.
     Use names or "the knight", never he/she. Show only what the facts say; no invented kills, wounds or
     outcomes. Blood implied, never graphic.
   - `who` lists the named knights in the panel, spelled exactly as in the character sheet.
   - Gear from the style file: mail hauberk, nasal helm, kite shield, saddles with stirrups; no plate, no
     visors, no turreted castles. Foes as the style file describes.
   - `caption`: exactly one line saying what is going on in that panel.
3. **Check (Sonnet):** every panel traces to the facts; knights' gear and looks match the sheet.
4. **Assemble:** write the JSON to the scratchpad, then
   `.venv/bin/python -m core.comic_prompt $SCRATCH/panes.json sessions/<id>.comic.md`.
   Tell Stuart the path. Nothing is added to the event log (it is append-only); the file is the thing he edits.
