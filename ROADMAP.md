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

- [x] **Session roster + export** — keep a list of NPCs generated this session
  (add/remove/clear); click an entry to reload/edit it; copy the whole roster
  to the clipboard as Markdown.
- [x] **GM notes + save/load** — per-NPC free-text notes for capturing play;
  save/load the roster (incl. notes) as JSON; prompt before losing unsaved
  notes. Roster JSON is the cross-session persistence for notes.
- [ ] **Batch generate** — spin up a whole village, court, or warband at once
  (e.g. "generate 8") with a summary table.
- [x] **Social class / rank** — Commoner / Squire / Knight / Lady / Noble /
  Clergy, each with a **skills block**, a **Glory** value, and class-appropriate
  attire (used in the image prompt). Selectable in the UI or rolled at random.

## Flavour & depth

- [x] **Rulebook-accurate traits + trait-driven manner** — generate all 13 pairs
  by the Random Method (±3 for religion virtues), highlight Famous traits, and
  derive the manner from the profile (surface demeanour + moral "at heart").


- [ ] **Campaign year + age** — set the GPC year (485–566); age the NPC and
  adjust stats, and derive era-appropriate cultural Passions (e.g. Salisbury →
  `Hate (Saxons)`).
- [ ] **Plot hook / secret one-liner** and **relationship to the party or a
  faction** for instant adventure relevance.
- [ ] **Glory value** to signal renown.
- [ ] **Homeland / region** that can drive culture and cultural Passions.

## Full character creation (Cymric knight, Core Ch.3)

- [x] **Phase 1 — the sheet.** Full skills (Table 3.5 beginning values + Cymric
  cultural + family characteristic + 7 years' Training), rules-based inherited
  **Glory** via Quick Family History (+ heroic-event family lore), complete
  starting **Passions**, plus age/homeland. Cymri knights only (other cultures
  are supplement material — kept to today's lighter generation).
- [ ] **Phase 2 — kit.** Starting equipment (hauberk+aketon+nasal helm+kite
  shield, sword/spears/lance/dagger), horses (Charger/Rouncy/Sumpter — stats
  already seeded in the bestiary), and a **Beginner's Luck heirloom** (Table 3.9).
- [ ] **Phase 3 — flourish.** Coat of arms (text blazon; Tables B.1–B.3),
  Ideals (Chivalry/Religious/Romantic), a squire supporting-NPC, and — if the
  supplement is available — Saxon/Pict cultural creation.

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
