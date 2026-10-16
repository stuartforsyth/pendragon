# Piece 2 — Conroi & Morale — CLOSED 2026-10-17

## Decisions so far
1. Commander: the GM promotes one player knight to conroi commander, or takes the role (NPC commander) for scripted battles like Carlion. Changeable mid-battle (logged). Only player knights matter mechanically; no GM-knight tracking (Table 6.5's GM-knight question → piece 7).
2. Starting Morale: a plain number the GM enters (players compute it at the table from their Passions), plus optional Passion name. The app only enforces the cap (current ≤ starting) and tracks changes.
3. Rolls: players roll and resolve at the table; the GM records only outcomes/amounts that change tracked state (e.g. rest roll amount; "Battle roll succeeded → chosen Encounter"). No per-roll capture, no sheet data.
4. Leaving Mustering: Turn 1 is blocked until a commander and a starting Morale are set; Passion name optional.
5. New day: re-muster asks for the new starting Morale (pre-filled with yesterday's start; players recompute at the table); commander carries over, changeable.

## UI
- Mustering panel (Battle tool before Turn 1): commander chips (each party knight + "GM"), Starting Morale number, optional Passion text, party knights listed, "Begin Turn 1" disabled until commander + Morale.
- Morale strip pinned at the top of the running Battle tool: current / starting (e.g. 14 / 21), ± adjust (logged GM override), current commander (click to change, logged).
- Players' Morale visual → piece 8.

## House rules
- None. (RAW averages members' Passions; players do that at the table and the GM enters the result.)

## Rejected / out of scope
- App-computed Morale from per-knight Passion values; player-knight profiles; per-roll capture of player skill rolls.
- Tracking GM knights in the conroi (Table 6.5 question asked in piece 7).

## Open questions
- None.

## Interfaces
- Piece 5: Morale changes (Encounter loss, posture, rest, forced retire at 0/below minimum). Piece 6: KV gains, Alone on the Field drain. Piece 4: enemy-commander fumble negates one Encounter's Morale effect. Piece 8: Morale visual.
