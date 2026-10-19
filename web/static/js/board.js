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

/**
 * The running tally beneath the Field: one column per knight, the foes they
 * are credited with grouped by Day · Turn (newest first), "Knifemen 7 slain".
 * The knight cards stay for glanceable state; this is the ledger.
 */
export function tallyStrip(knights) {
  const list = (knights || []).filter((k) => k && k.name);
  if (!list.length || !list.some((k) => k.tally?.length)) return null;
  const col = (k) => {
    const groups = [];
    for (const e of k.tally || []) {
      const key = e.day != null && e.turn != null ? `Day ${e.day} · Turn ${e.turn}` : "";
      if (!groups.length || groups.at(-1).key !== key) groups.push({ key, items: [] });
      groups.at(-1).items.push(e);
    }
    return h("div", { class: "tally-col" },
      h("div", { class: "tally-head" }, knightShield(), h("span", { class: "tally-name" }, k.name), h("b", {}, (k.tally || []).length)),
      h("div", { class: "tally-body" }, (k.tally || []).length ? groups.map((g) => h("div", { class: "tally-group" },
        g.key ? h("span", { class: "tally-when" }, g.key) : null,
        g.items.map((e) => h("span", { class: `tally-item f-${e.fate}` }, h("span", { class: "tally-who" }, e.name), " ", h("span", { class: "tally-fate" }, e.fate)))))
        : h("span", { class: "tally-none" }, "none yet")));
  };
  return h("div", { class: "tally-strip" }, h("div", { class: "tally-label" }, "Defeated"), list.map(col));
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

/**
 * A battle card as players see it, after the printed cards: a coloured title
 * band (green for a Foe, gold for an Opportunity) carrying the name and the
 * flavour in italic, a braided rule, then the foot with the twin dragons and
 * the Morale Minimum in its roundel. A card the conroi lacks the Morale for is
 * greyed and says so; a spent Opportunity is struck through.
 */
const DRAGONS = '<path d="M4 26c6-10 14-14 22-12 4 1 6 4 6 8M118 26c-6-10-14-14-22-12-4 1-6 4-6 8" fill="none" stroke="#2f6b3e" stroke-width="2.4" stroke-linecap="round"/>' +
  '<path d="M8 24c5-6 11-9 17-8M114 24c-5-6-11-9-17-8" fill="none" stroke="#2f6b3e" stroke-width="1.4" stroke-linecap="round" opacity=".7"/>' +
  '<path d="M26 14l5-6 1 7M96 14l-5-6-1 7" fill="#2f6b3e"/>';
export function cardFrame(c, { kind, small = false, token = null, crit = false, disabled = false } = {}) {
  const need = c.minimum;
  return h("div", { class: `pcard ${c.opportunity ? "opp" : ""} ${small ? "small" : ""} ${disabled ? "cant" : ""} ${c.spent ? "spent" : ""}`,
      title: c.spent ? `${c.name} — already played this battle` : disabled ? `${c.name} needs Morale ${need}` : c.name },
    kind ? h("span", { class: "kind" }, kind) : null,
    h("div", { class: "band" }, h("div", { class: "cname" }, c.name), c.flavour ? h("div", { class: "flav" }, c.flavour) : null),
    h("div", { class: "braid" }),
    h("div", { class: "body" }),
    h("div", { class: "foot" },
      svg(DRAGONS, 'viewBox="0 0 122 30" class="dragons" aria-hidden="true"'),
      need != null ? h("div", { class: "mm" }, h("span", { class: "mm-l" }, "Morale", h("br"), "Minimum"), h("span", { class: "mm-n" }, need)) : null),
    disabled && !c.spent ? h("div", { class: "cant-rib" }, "Not enough Morale") : null,
    c.spent ? h("div", { class: "cant-rib spent-rib" }, "Already played") : null,
    token ? h("div", { class: "toks" }, h("span", { class: `ttok ${crit ? "crit" : ""}` }, knightShield(), token, crit ? " · critical" : "")) : null);
}

/** The battlefield as the players may choose from it: the playable cards,
 * each with its Minimum Morale; the ones out of reach greyed. */
export function deckSpread(options, { label = "The battlefield" } = {}) {
  return h("div", { class: "deck" }, h("span", { class: "dl" }, label),
    h("div", { class: "drow" }, options.map((c) => {
      const el = cardFrame(c, { small: true, disabled: !c.playable });
      if (c.in_play) el.classList.add("on");
      return el;
    })));
}
