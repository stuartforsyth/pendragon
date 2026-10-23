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

/**
 * The Glory race: the cards sorted by Glory, highest first (ties keep the table's
 * order), once anyone has any. The knight(s) on top — with at least two in the
 * race and some Glory on the board — are the leaders: ``leader`` is true on them.
 */
export function rankByGlory(knights) {
  const list = (knights || []).filter(Boolean);
  const val = (k) => k.glory?.value || 0;
  const top = Math.max(0, ...list.map(val));
  if (!top) return { list, leaders: new Set() };
  const sorted = list.map((k, i) => [k, i]).sort((a, b) => val(b[0]) - val(a[0]) || a[1] - b[1]).map((x) => x[0]);
  return { list: sorted, leaders: list.length > 1 ? new Set(sorted.filter((k) => val(k) === top)) : new Set() };
}

/** A laurel wreath for the leader's number: two branches of leaves round it. */
function laurel() {
  let leaves = "";
  for (let i = 0; i < 7; i++) {
    const a = (115 + i * 17) * Math.PI / 180, x = 60 + 29 * Math.cos(a), y = 31 - 25 * Math.sin(a), rot = 115 + i * 17 + 90;
    for (const side of [1, -1]) {
      leaves += `<ellipse cx="${side > 0 ? 120 - x : x}" cy="${y}" rx="${6.2 - i * 0.25}" ry="2.6" transform="rotate(${side > 0 ? 180 - rot : rot} ${side > 0 ? 120 - x : x} ${y})"/>`;
    }
  }
  return svg(`<g fill="#b8892b" opacity=".92">${leaves}</g>`, 'class="gl-laurel" viewBox="0 0 120 62" aria-hidden="true"');
}

const CROWN = '<path d="M2 17 5 5l6 6 5-9 5 9 6-6 3 12Z" fill="#d2a645" stroke="#8a6a1c" stroke-width="1.2" stroke-linejoin="round"/><circle cx="5" cy="4.5" r="1.7" fill="#8e2219"/><circle cx="16" cy="2.5" r="1.7" fill="#8e2219"/><circle cx="27" cy="4.5" r="1.7" fill="#8e2219"/>';

/** The big Glory number; it ticks up with "+n · reason" when it rises. The leader's
 * wears a laurel wreath and a crown. */
export function gloryCounter(pid, g, label = "Glory", { leader = false } = {}) {
  const before = prevGlory[pid];
  const rose = before !== undefined && g.value > before;
  prevGlory[pid] = g.value;
  return h("div", { class: `glory-counter ${rose ? "rose" : ""} ${leader ? "leader" : ""}` },
    h("span", { class: "gl-label" }, label),
    h("span", { class: "gl-wrap" },
      leader ? [laurel(), svg(CROWN, 'class="gl-crown" viewBox="0 0 30 18" aria-hidden="true"')] : null,
      h("b", { class: "gl-value" }, g.value)),
    rose && g.last ? h("span", { class: "gl-plus" }, `+${g.last.amount}`) : null);
}

/** Reminder chips in three tones: harm (gules), boon (vert), state (grey). */
export function effectChips(list) {
  if (!list?.length) return null;
  return h("div", { class: "fx-chips" }, list.map((e) => h("span", { class: `fx ${e.tone}` }, e.label)));
}

/** One knight: shield, name, player, Glory, chips and the LAST line. */
export function knightCard(k, { compact = false, leader = false } = {}) {
  const down = k.status && k.status !== "active";
  const slain = k.tally?.length || 0;            // foes defeated: the ledger lives in the finale, the count lives here
  return h("div", { class: `kcard ${compact ? "compact" : ""} ${down ? "down" : ""} ${leader ? "leader" : ""}` },
    h("div", { class: "kc-top" },
      knightShield(down),
      h("div", { class: "kc-id" }, h("div", { class: "kc-name" }, k.name, slain ? h("span", { class: "kc-def", title: "Foes defeated" }, `⚔ ${slain}`) : null),
        k.player ? h("div", { class: "kc-player", title: "The player" }, k.player) : null),
      gloryCounter(k.pid, k.glory, "Glory", { leader })),
    effectChips(k.effects));
}

/**
 * Morale across the top of the Table: one wide, plain line — the number, the bar, the band word and the
 * last change — so it can be read from a compressed stream and costs the board no column.
 */
export function moraleBar(m) {
  if (!m) return null;
  const pct = Math.max(0, Math.min(100, (m.current / Math.max(1, m.start)) * 100));
  const key = `${m.current}/${m.start}/${m.last?.delta}/${m.last?.reason}`;
  const changed = lastMorale.key !== null && lastMorale.key !== key;
  lastMorale.key = key;
  const band = (m.band || "").toLowerCase();
  return h("div", { class: `mbar band-${band} ${changed ? "changed" : ""}`, role: "img", "aria-label": `Morale ${m.current} of ${m.start}, ${m.band}` },
    h("span", { class: "mb-label" }, "Morale"),
    h("b", { class: "mb-num" }, m.current), h("span", { class: "mb-of" }, `/ ${m.start}`),
    h("span", { class: "mb-track" }, h("i", { style: { width: `${pct}%` } })),
    h("span", { class: "mb-word" }, m.band),
    m.last ? h("span", { class: "mb-why" }, `${m.last.delta > 0 ? "+" : m.last.delta < 0 ? "−" : ""}${Math.abs(m.last.delta)} · ${m.last.reason}`) : null);
}

const lastMorale = { key: null };

/**
 * A battle card as the players see it: the printed card with only its green title box
 * readable — the name and the flavour — and its Morale Minimum. The rest of the card (its
 * rules, the stat block) is the GM's. A card the conroi lacks the Morale for is greyed and
 * says so; a spent Opportunity is struck through.
 */
export function cardFrame(c, { kind, small = false, token = null, crit = false, disabled = false } = {}) {
  const need = c.minimum;
  const band = h("div", { class: "cf-band" }, h("div", { class: "cf-title" }, c.name), c.flavour ? h("div", { class: "cf-flav" }, c.flavour) : null);
  const face = h("div", { class: "pc-face cf front first" }, band, h("div", { class: "cf-body" }),
    need != null ? h("div", { class: "cf-foot" }, h("span", { class: "cf-fl" }, "Morale Minimum"), h("span", { class: "cf-fv" }, need)) : null);
  return h("div", { class: `pcard ${c.opportunity ? "opp" : ""} ${small ? "small" : ""} ${disabled ? "cant" : ""} ${c.spent ? "spent" : ""}`,
      title: c.spent ? `${c.name} — already played this battle` : disabled ? `${c.name} needs Morale ${need}` : c.name },
    kind ? h("span", { class: "kind" }, kind) : null,
    face,
    disabled && !c.spent ? h("div", { class: "cant-rib" }, "Not enough Morale") : null,
    c.spent ? h("div", { class: "cant-rib spent-rib" }, "Already played") : null,
    token ? h("div", { class: "toks" }, h("span", { class: `ttok ${crit ? "crit" : ""}` }, knightShield(), token, crit ? " · critical" : "")) : null);
}

/** The battlefield as the players may choose from it: the playable cards,
 * each with its Minimum Morale; the ones out of reach greyed. */
export function deckSpread(options, { label = "The battlefield" } = {}) {
  return h("div", { class: "deck" }, h("span", { class: "dl" }, label),
    h("div", { class: `drow ${options.some((c) => c.in_play) ? "has-play" : ""}` }, options.map((c) => {
      const by = c.picked_by?.[0];                       // the GM's set card and the knights' picks are marked on the cards themselves
      const el = cardFrame(c, { small: true, disabled: !c.playable, kind: c.set ? "The GM sets" : by ? "Picked" : null,
        token: by ? by.knight.split(" ").slice(-1)[0] + (c.picked_by.length > 1 ? ` +${c.picked_by.length - 1}` : "") : null, crit: !!by?.crit });
      if (c.in_play) el.classList.add("on");
      return el;
    })));
}
