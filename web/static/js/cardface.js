// The printed faces of an Opportunity card (data/battle_cards.json), shared by
// the Table (instruction faces only) and the GM console (instructions + stat
// faces). The server builds every face dict (core/battle_cards.py) — this only
// renders it, building DOM nodes (no innerHTML) and fitting the text to the box.

import { h } from "./lib.js";

/** "plain **bold** and *italic*" → DOM nodes. */
export function markup(text) {
  const out = [];
  for (const part of String(text ?? "").split(/(\*\*[^*]+\*\*|\*[^*]+\*)/)) {
    if (!part) continue;
    if (part.startsWith("**")) out.push(h("b", {}, part.slice(2, -2)));
    else if (part.startsWith("*")) out.push(h("i", {}, part.slice(1, -1)));
    else out.push(part);
  }
  return out;
}

const table = (head, rows, cls = "") =>
  h("table", { class: `cf-table ${cls}` },
    head ? h("thead", {}, h("tr", {}, head.map((x) => h("th", {}, x)))) : null,
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((x, i) => h(i === 0 && !head ? "th" : "td", {}, x))))));

/** Grow the text to the largest size that still fits the face (it never scrolls). */
function fit(el, body, max, min = 9, box = body) {
  let seen = false;
  const run = () => {
    if (!el.isConnected) { if (seen) ro.disconnect(); return; }      // redrawn away: stop watching
    seen = true;
    if (!el.clientHeight) return;
    let lo = min, hi = max;
    for (let i = 0; i < 8 && hi - lo > 0.25; i++) {
      const mid = (lo + hi) / 2;
      body.style.fontSize = `${mid}px`;
      if (body.scrollHeight > box.clientHeight + 0.5) hi = mid; else lo = mid;
    }
    body.style.fontSize = `${lo}px`;
  };
  const ro = new ResizeObserver(run);
  ro.observe(el);
  requestAnimationFrame(run);
  document.fonts?.ready.then(run);          // the web fonts change the line breaks
}

/** An instruction face: title band + flavour, body blocks, Morale footer. */
export function cardFace(face, { maxFont = 24 } = {}) {
  const body = h("div", { class: "cf-body" }, (face.blocks || []).map((b) => {
    if (b.h) return h("h4", {}, markup(b.h));
    if (b.rows) return h("div", { class: "cf-rows" }, h("div", { class: "cf-rt" }, b.rows.title),
      b.rows.rows.map(([k, v]) => h("p", {}, h("b", {}, `${k}: `), markup(v))));
    return h("p", {}, markup(b.p));
  }));
  const el = h("div", { class: `cf front ${face.title ? "first" : ""}` },
    face.title ? h("div", { class: "cf-band" }, h("div", { class: "cf-title" }, face.title),
      face.flavour ? h("div", { class: "cf-flav" }, face.flavour) : null) : null,
    body,
    face.footer ? h("div", { class: "cf-foot" }, h("span", { class: "cf-fl" }, face.footer.label), h("span", { class: "cf-fv" }, face.footer.value)) : null);
  fit(el, body, maxFont);
  return el;
}

/** A stat face — the GM's side of the card. */
export function statFace(face, { maxFont = 18 } = {}) {
  const body = h("div", { class: "cf-body" },
    h("div", { class: "cf-chars" }, (face.chars || []).map(([k, v]) => h("span", {}, h("small", {}, k), v))),
    face.attacks?.length ? [h("div", { class: "cf-sec" }, "Attacks"),
      table(["Weapon", "Skill", "Value", "DMG"], face.attacks),
      (face.attack_notes || []).map((n) => h("p", { class: "cf-note" }, n))] : null,
    h("div", { class: "cf-two" },
      h("div", {}, h("div", { class: "cf-sec" }, "Health"), table(["Statistic", "Value"], face.health || [], "kv")),
      h("div", {}, h("div", { class: "cf-sec" }, "Other"), table(["Statistic", "Value"], face.other || [], "kv"))),
    (face.lines || []).map(([k, v]) => h("p", {}, h("b", {}, `${k}: `), v)),
    face.rolls ? [h("p", { class: "cf-rollt" }, h("b", {}, face.rolls.title)), table(null, face.rolls.rows, "rolls")] : null,
    face.ransom_table ? h("div", { class: "cf-ransom-t" }, h("div", { class: "cf-sec mid" }, "Ransom"), table(face.ransom_table.head, face.ransom_table.rows, "rt"))
    : face.ransom ? h("div", { class: "cf-ransom" }, h("span", { class: "cf-fl" }, "Ransom"), h("span", { class: "cf-fv" }, face.ransom)) : null);
  const el = h("div", { class: "cf back" },
    h("div", { class: "cf-bar" }, face.title),
    face.subtitle ? h("div", { class: "cf-sub" }, face.subtitle) : null,
    body);
  fit(el, body, maxFont);
  return el;
}

/** What the players see of an Opportunity: only the green title box of the card, large. */
export function bandFace(card, { maxFont = 64 } = {}) {
  const inner = h("div", { class: "cf-bandbody" }, h("div", { class: "cf-title" }, card.title),
    card.flavour ? h("div", { class: "cf-flav" }, card.flavour) : null);
  const el = h("div", { class: "cf-bandcard" }, inner);
  fit(el, inner, maxFont, 14, el);
  return el;
}
