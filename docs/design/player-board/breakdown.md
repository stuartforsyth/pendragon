# Player board improvements — breakdown (stage 1)

Status: **draft, awaiting user agreement on the piece list.**
Goal (user): make the Table easier for players to follow what has happened, and whether it affected their knight. Battle/fight board is designed in docs/design/battles (piece 8) — this covers the rest of play and shared parts.

## User direction (2026-10-17)
- The board is the **centrepiece**: players watch it to see what is happening to their knights and to pick up valuable information. The current implementation is poor — UI quality is the priority; get the UI right before anything else. Resume after the battles design questions are handled.

## Current Chronicle board (screenshot 2026-10-17)
- Latest event spotlit large (illuminated initial); "Earlier" feed of ~4 cards to the right; older events drop off.
- Knights are absent outside combat; events are linked to knights only by free-text labels ("Sir Erik — Awareness").
- Nothing persists about what changed for a knight (damage, Glory, checks) — players must catch it as it scrolls past.
- No scene structure; feed is flat chronological.

## Pieces (proposed)
| # | Piece | Covers |
|---|-------|--------|
| 1 | Knights on the board | an always-visible party strip in Chronicle mode; GM attribution of events to knights (who did it / who it affects) |
| 2 | "For your sheet" | per-knight list of things to write down this session (damage, Glory, experience checks, Passion/Trait changes, £/items), end-of-session summary card |
| 3 | Feed structure | scenes (GM-marked), longer readable history, event-type styling, knight shields on events that touch them |
| 4 | Session recap | "Previously…" card at session start from the last session |
| 5 | Shared with battles | effect chips, Glory counters, Morale gauge — reuse battles piece 8 components |
- Mockup v1 (2026-10-17): docs/design/player-board/mockup-v1.html — published privately at https://claude.ai/artifact/Vnb7TvxdRqWpAvPCzjDbLK
