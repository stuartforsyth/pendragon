// Reusable pieces of the players' board (the Table): knight cards, Glory
// counters, effect chips, the "last thing that happened to you" line.
// Combat and battles use them now; feasts and hunts will reuse them. The
// server builds every dict (web/table.py: knight_cards) — this only renders.

import { h } from "./lib.js";

const prevGlory = {};   // pid -> last value shown, for the tick animation

const svg = (markup, attrs) => {
  const s = document.createElement("span");
  s.innerHTML = `<svg ${attrs}>${markup}</svg>`;
  return s.firstChild;
};

const SHIELD = "M22 2 3 7v14c0 13 8 21 19 27 11-6 19-14 19-27V7Z";
export function knightShield(down = false) {
  return svg(`<path d="${SHIELD}" fill="#24507f"/><path d="M6 32 22 18l16 14" fill="none" stroke="#d2a645" stroke-width="4"/>` +
    `<path d="${SHIELD}" fill="none" stroke="#4e3a28" stroke-width="2"/>` +
    (down ? '<path d="M10 12 34 44M34 12 10 44" stroke="#2a1d14" stroke-width="3.5"/>' : ""),
  'class="kshield" viewBox="0 0 44 50" aria-hidden="true"');
}

/** The big Glory number; it ticks up with "+n · reason" when it rises. */
export function gloryCounter(pid, g, label = "Glory") {
  const before = prevGlory[pid];
  const rose = before !== undefined && g.value > before;
  prevGlory[pid] = g.value;
  return h("div", { class: `glory-counter ${rose ? "rose" : ""}` },
    h("span", { class: "gl-label" }, label),
    h("b", { class: "gl-value" }, g.value),
    rose && g.last ? h("span", { class: "gl-plus" }, `+${g.last.amount}`) : null);
}

/** Reminder chips in three tones: harm (gules), boon (vert), state (grey). */
export function effectChips(list) {
  if (!list?.length) return null;
  return h("div", { class: "fx-chips" }, list.map((e) => h("span", { class: `fx ${e.tone}` }, e.label)));
}

/** The newest thing that touched this knight. */
export function happenedLine(items) {
  if (!items?.length) return null;
  return h("div", { class: "happened" }, h("i", {}, "Last"), items[0]);
}

/** One knight: shield, name, player, Glory, chips and the LAST line. */
export function knightCard(k, { compact = false } = {}) {
  const down = k.status && k.status !== "active";
  return h("div", { class: `kcard ${compact ? "compact" : ""} ${down ? "down" : ""}` },
    h("div", { class: "kc-top" },
      knightShield(down),
      h("div", { class: "kc-id" }, h("div", { class: "kc-name" }, k.name),
        k.player ? h("div", { class: "kc-player" }, `played by ${k.player}`) : null),
      gloryCounter(k.pid, k.glory)),
    effectChips(k.effects),
    happenedLine(k.happened));
}
