# Roadmap / Ideas

Future functionality for the Pendragon NPC Generator, grouped by theme. Tick
items off as they land. This file is the running backlog — add ideas here
rather than scattering TODOs through the code.

## Quick wins (small, high payoff)

- [x] **Wire up Directed Traits** — a one-line grudge/fear/loyalty aimed at a
  named target (e.g. `*Vengeful (a rival house) +5`, or an Obsession such as
  `Avarice (a famous sword)`). Data already lives in
  `rules/directed-traits.md`.
- [x] **Copy Image Prompt** — build a period-accurate image-generation prompt
  from the NPC's description (culture, appearance, distinctive features, eyes)
  for pasting into any image generator. No dependencies.
- [x] **Reroll individual fields** — reroll one part of the NPC (name, looks,
  traits, passions, grudge, manner) without regenerating the whole thing.
- [x] **Copy as Markdown** — a second export flavour so statblocks drop cleanly
  into `.md` game notes with headers and bold labels.

## Table workflow (bigger, most useful in play)

- [ ] **Session roster + export** — keep a running list of NPCs generated this
  session; save/append them to a Markdown file.
- [ ] **Batch generate** — spin up a whole village, court, or warband at once
  (e.g. "generate 8") with a summary table.
- [ ] **Social class / rank** — Commoner / Knight / Noble weighting that also
  unlocks a proper **skills block** (a combat weapon skill + a couple of
  courtly skills), turning a statblock into something runnable in a fight.

## Flavour & depth

- [ ] **Campaign year + age** — set the GPC year (485–566); age the NPC and
  adjust stats, and derive era-appropriate cultural Passions (e.g. Salisbury →
  `Hate (Saxons)`).
- [ ] **Plot hook / secret one-liner** and **relationship to the party or a
  faction** for instant adventure relevance.
- [ ] **Glory value** to signal renown.
- [ ] **Homeland / region** that can drive culture and cultural Passions.

## Presentation

- [ ] **Generate Portrait** — call a local image generator (ComfyUI / A1111
  API) and show the portrait in the window (needs one running locally).
- [ ] **NPC card** — a formatted, printable/exportable card layout.

## Under the hood

- [x] **Structured data layer** — generation data moved to `data/rules.json`
  (single source of truth, validated at startup) instead of parsing Markdown.
  Adding new sourcebook material is now "add a key". `rules/*.md` are docs only.
- [ ] **Unit tests** for the data loader and name parsing so edits to
  `data/rules.json` can't silently break generation.
- [ ] **Config file** — weightings and toggles for which sections to include.
