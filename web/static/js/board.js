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

const lastMorale = { key: null };

/**
 * The Morale gauge: the number "of N", a draining fill that bloodies as it
 * drops, and a band word (Steady · Shaken · Bloodied · Breaking) so the state
 * never rests on colour alone. The last change and its reason sit beneath.
 */
export function moraleGauge(m, { compact = false } = {}) {
  if (!m) return h("div", { class: "mgauge empty" }, h("span", { class: "mg-label" }, "Morale"), h("span", { class: "mg-wait" }, "The conroi is mustering…"));
  const pct = Math.max(0, Math.min(100, (m.current / Math.max(1, m.start)) * 100));
  const key = `${m.current}/${m.start}/${m.last?.delta}/${m.last?.reason}`;
  const changed = lastMorale.key !== null && lastMorale.key !== key;
  lastMorale.key = key;
  const band = (m.band || "").toLowerCase();
  const fill = h("div", { class: "mg-fill", style: { height: `${pct}%` } });
  return h("div", { class: `mgauge band-${band} ${compact ? "compact" : ""} ${changed ? "changed" : ""}`, role: "img",
    "aria-label": `Morale ${m.current} of ${m.start}, ${m.band}` },
    h("span", { class: "mg-label" }, "Morale"), fill,
    h("div", { class: "mg-cap" },
      h("span", { class: "mg-num" }, m.current), h("span", { class: "mg-of" }, `of ${m.start}`),
      h("span", { class: "mg-word" }, m.band),
      m.last ? h("span", { class: "mg-why" }, `${m.last.delta > 0 ? "+" : m.last.delta < 0 ? "−" : ""}${Math.abs(m.last.delta)} · ${m.last.reason}`) : null));
}

/** A battle card as players see it: kind, a device, the name and the GM's
 * flavour line — never the card's mechanics. Opportunities get a gold frame. */
export function cardFrame(c, { kind, small = false, token = null, crit = false } = {}) {
  const device = c.opportunity
    ? '<circle cx="30" cy="30" r="26" fill="none" stroke="#b08a36" stroke-width="2"/><path d="M14 40 17 20l8 9 5-12 5 12 8-9 3 20Z" fill="#b08a36"/>'
    : '<circle cx="30" cy="30" r="26" fill="none" stroke="#4e3a28" stroke-width="2"/><path d="M18 42 42 18M42 42 18 18" stroke="#8e2219" stroke-width="3"/><path d="M16 44l4-1-3-3zM44 44l-4-1 3-3z" fill="#8e2219"/>';
  return h("div", { class: `pcard ${c.opportunity ? "opp" : ""} ${small ? "small" : ""}` },
    h("span", { class: "kind" }, kind || (c.opportunity ? "★ Opportunity" : "")),
    h("span", { class: "dev" }, svg(device, `viewBox="0 0 60 60" width="${small ? 56 : 76}" height="${small ? 56 : 76}" aria-hidden="true"`)),
    h("div", {}, h("div", { class: "cname" }, c.name), c.flavour ? h("div", { class: "flav" }, c.flavour) : null),
    token ? h("div", { class: "toks" }, h("span", { class: `ttok ${crit ? "crit" : ""}` }, knightShield(), token, crit ? " · critical" : "")) : null);
}

/** Today's battlefield: every card name; in play outlined, spent struck. */
export function deckSpread(deck) {
  return h("div", { class: "deck" }, h("span", { class: "dl" }, "Today's battlefield"),
    h("div", { class: "drow" },
      (deck.foes || []).map((c) => h("span", { class: `dcard ${c.in_play ? "on" : ""}` }, c.name)),
      (deck.opportunities || []).map((c) => h("span", { class: `dcard opp ${c.in_play ? "on" : ""} ${c.spent ? "spent" : ""}` }, c.name))));
}
