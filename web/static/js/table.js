// The Table screen: a live, player-safe view of the session. The server sends
// only what players may see (see web/table.py); this file just makes it sing.

import { h, clear, icon, debounce } from "./lib.js";

const $ = (id) => document.getElementById(id);
let last = { heroId: null, states: {} };

const OUT = { critical: "Critical", success: "Success", failure: "Failure", fumble: "Fumble" };

// ---------------------------------------------------------------- ornaments
const svg = (markup, attrs = "") => {
  const s = document.createElement("span");
  s.innerHTML = `<svg ${attrs}>${markup}</svg>`;
  return s.firstChild;
};

const flourish = () => svg(
  '<path d="M0 11h120M180 11h120" stroke="currentColor" stroke-width="1.2"/>' +
  '<path d="M150 2l7 9-7 9-7-9z" fill="currentColor"/><circle cx="130" cy="11" r="2.5" fill="currentColor"/><circle cx="170" cy="11" r="2.5" fill="currentColor"/>',
  'class="flourish" viewBox="0 0 300 22" fill="none"');

function medalBg(tone = "#b08a36") {
  let dots = "";
  for (let i = 0; i < 20; i++) {
    const a = (i / 20) * Math.PI * 2;
    dots += `<circle cx="${125 + Math.cos(a) * 112}" cy="${125 + Math.sin(a) * 112}" r="${i % 5 === 0 ? 4 : 2.2}" fill="${tone}"/>`;
  }
  return svg(`<circle cx="125" cy="125" r="122" fill="#f6ecd2" stroke="${tone}" stroke-width="3"/>` +
    `<circle cx="125" cy="125" r="100" fill="none" stroke="#8e2219" stroke-width="1.6"/>` +
    `<circle cx="125" cy="125" r="94" fill="none" stroke="${tone}" stroke-width=".8"/>${dots}`,
    'class="bg" viewBox="0 0 250 250"');
}

const waxSeal = () => svg(
  '<defs><radialGradient id="wx" cx="40%" cy="35%"><stop offset="0" stop-color="#c2463a"/><stop offset=".7" stop-color="#8e2219"/><stop offset="1" stop-color="#5e140e"/></radialGradient></defs>' +
  '<path d="M100 8c14 0 18 10 30 12s24-2 30 8 0 20 6 30 18 16 14 28-16 14-18 26 6 24-4 32-22 2-32 8-14 20-28 20-18-14-28-20-24 0-32-8-2-20-4-32-14-14-18-26 8-18 14-28 0-22 6-30 18-6 30-8 16-12 30-12z" fill="url(#wx)"/>' +
  '<circle cx="100" cy="100" r="54" fill="none" stroke="#5e140e" stroke-width="3" opacity=".6"/>' +
  '<path d="M80 92c6-12 14-16 24-12l7-7 3 10c3 3 3 9 0 13l-10 3-6 13-3-10-10 3z" fill="#5e140e" opacity=".75"/>',
  'viewBox="0 0 200 200"');

const TINCTURE = {
  party: ["#24507f", "#d2a645"], foe: ["#8e2219", "#d2a645"], named: ["#5b2f7a", "#d2a645"],
  beast: ["#2f6b3e", "#efe3c6"], monster: ["#1b1612", "#b3342a"], fae: ["#3a8fb0", "#efe3c6"],
};
function shield(f) {
  const key = f.side === "party" ? "party" : f.named ? "named" : (TINCTURE[f.category] ? f.category : "foe");
  const [field, charge] = TINCTURE[key];
  const rim = f.elite ? "#d2a645" : "#4e3a28";
  const slain = f.status === "dead" ? '<path d="M10 12 34 44M34 12 10 44" stroke="#2a1d14" stroke-width="3.5"/>' : "";
  const chargeShape = f.side === "party"
    ? `<path d="M6 32 22 18l16 14" fill="none" stroke="${charge}" stroke-width="4"/>`
    : `<path d="M6 10 38 40" stroke="${charge}" stroke-width="7" clip-path="url(#sh)"/>`;
  const outline = "M22 2 3 7v14c0 13 8 21 19 27 11-6 19-14 19-27V7Z";
  return svg(`<clipPath id="sh"><path d="${outline}"/></clipPath><path d="${outline}" fill="${field}"/>${chargeShape}<path d="${outline}" fill="none" stroke="${rim}" stroke-width="${f.elite ? 3 : 2}"/>${slain}`,
    'class="shield" viewBox="0 0 44 50"');
}

// ---------------------------------------------------------------- number tumble
function tumble(el, final, ms = 650) {
  const start = performance.now();
  const max = Math.max(20, Math.abs(final) * 1.5);
  const step = (t) => {
    if (t - start >= ms) { el.textContent = final; return; }
    el.textContent = Math.ceil(Math.random() * max);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- hero (spotlight)
function hero(c, fresh) {
  const d = c.data || {};
  const t = c.type;
  if (t === "narrate") {
    if (d.style === "scene") return h("div", { class: "hero scene" }, flourish(), h("div", { class: "h-title" }, d.text), flourish());
    if (d.style === "image") return h("div", { class: "hero framed" }, h("img", { src: d.image_url, alt: "" }), d.text ? h("div", { class: "cap" }, d.text) : null);
    return h("div", { class: "hero" }, h("p", { class: "illum" }, d.text));
  }
  if (t.startsWith("npc.") && d.npc) {
    return h("div", { class: "hero" },
      h("div", { class: "kicker" }, t === "npc.presented" ? "Before you stands" : "A new face"),
      h("div", { class: "h-title" }, d.npc.full), h("div", { class: "h-sub" }, d.npc.subtitle),
      flourish(), h("p", { class: "illum", style: { fontSize: "27px" } }, d.npc.description));
  }
  if (t === "sealed") {
    return h("div", { class: "hero sealed-hero" }, waxSeal(),
      c.title ? h("div", { class: "kicker", style: { marginTop: "12px" } }, c.title) : null,
      h("div", { class: "msg" }, "The GM rolls in secret…"));
  }
  if (t === "roll.check" || t === "roll.dice" || t === "roll.damage") {
    const n = t === "roll.check" ? d.roll : d.total;
    const num = h("div", { class: "n" }, n);
    if (fresh) tumble(num, n);
    let ribbon = null;
    if (t === "roll.check") ribbon = h("div", { class: `ribbon ${d.outcome}` }, OUT[d.outcome] || d.outcome);
    else if (t === "roll.damage") ribbon = h("div", { class: `ribbon ${d.critical ? "critical" : "failure"}` }, d.critical ? "Critical damage" : "Damage");
    const who = c.title || d.label || "";
    const faces = t === "roll.dice" && d.terms ? h("div", { class: "dicefaces" }, d.terms.flatMap((term, i) =>
      term.constant !== undefined
        ? [h("div", { class: `face const ${term.sign < 0 ? "neg" : ""}` }, `${term.sign < 0 ? "−" : "+"}${term.constant}`)]
        : term.rolls.map((r, j) => h("div", { class: `face ${term.sign < 0 ? "neg" : ""}`, style: { animationDelay: `${(i * 4 + j) * 60}ms` } }, r)))) : null;
    const cls = d.outcome === "critical" || d.critical ? "critical-glow" : d.outcome === "fumble" && fresh ? "fumble-shake" : "";
    return h("div", { class: `hero rollhero ${cls}` },
      who ? h("div", { class: "who" }, who) : null,
      h("div", { class: "medal" }, medalBg(d.outcome === "critical" ? "#d2a645" : "#b08a36"), num),
      ribbon, faces, c.revealed ? h("div", { class: "vs" }, "— revealed —") : null);
  }
  if (t === "roll.opposed" && d.a) {
    const side = (s) => h("div", { class: `side ${s.result === "win" ? "win" : s.result === "loss" ? "lose" : ""}` },
      h("div", { class: "nm" }, s.label), h("div", { class: "rl" }, s.roll),
      h("div", { class: "res" }, `${OUT[s.outcome] || ""} · ${s.result}`));
    const verdict = d.winner ? `${d[d.winner].label} wins` : d.a.result === "tie" ? "A tie!" : "Both fail";
    return h("div", { class: "hero" }, h("div", { class: "kicker" }, "Opposed"),
      h("div", { class: "opposed" }, side(d.a), h("div", { class: "mid" }, "⚔"), side(d.b)),
      h("div", { class: "verdict" }, h("span", { class: `ribbon ${d.winner ? "critical" : "failure"}` }, verdict)));
  }
  if (t === "rule.shown") {
    return h("div", { class: "hero card rulehero" },
      h("div", { class: "kicker" }, `${d.book === "gm" ? "GM Handbook" : "Core Rulebook"} · p.${(d.pages || []).join(", ")}`),
      h("div", { html: d.html }));
  }
  if (t === "session.started" || t === "session.resumed") {
    return h("div", { class: "hero scene" }, h("div", { class: "kicker" }, t === "session.started" ? "Here begins" : "Here resumes"),
      h("div", { class: "h-title" }, c.title), flourish());
  }
  return h("div", { class: "hero" }, c.title ? h("div", { class: "kicker" }, c.title) : null, h("p", { class: "linehero" }, c.text));
}

// ---------------------------------------------------------------- mini cards
const MINI_ICON = (t) => t.startsWith("roll.") || t === "combat.check" ? "d20" : t === "sealed" ? "lock"
  : t.startsWith("combat.") ? "swords" : t.startsWith("npc.") ? "helm" : t === "narrate" ? "feather"
  : t === "rule.shown" ? "book" : t === "party.hp" ? "heart" : "scroll";

function mini(c) {
  const d = c.data || {};
  let res = null;
  if (c.type === "roll.check" && d.outcome) res = h("span", { class: "res", style: { color: { critical: "#b08a36", success: "#2f6b3e", failure: "#8e2219", fumble: "#1b1612" }[d.outcome] } }, `${d.roll} ${OUT[d.outcome]}`);
  if (c.type === "roll.dice" || c.type === "roll.damage") res = h("span", { class: "res" }, d.total);
  let text = c.text;
  if (c.type.startsWith("npc.") && d.npc) text = d.npc.subtitle;
  if (c.type === "narrate") text = d.style === "scene" ? "" : d.text || "An image";
  if (c.type === "roll.check") text = d.kind && d.kind !== "skill" ? d.kind : "";
  if (c.type === "roll.dice" || c.type === "roll.damage") text = text.replace(/^.*?(damage)?: /, "");
  const title = c.title || (c.type === "narrate" ? (d.style === "scene" ? "Scene" : "Narration") : c.type === "sealed" ? "A secret roll" : "");
  if (c.type === "session.started" || c.type === "session.resumed") text = c.type === "session.started" ? "The session begins" : "The session resumes";
  return h("div", { class: `card mini ${c.type === "sealed" ? "sealed" : ""}` },
    h("div", { class: "ic" }, icon(MINI_ICON(c.type))),
    h("div", { class: "t" }, title || text),
    title ? h("div", { class: "x" }, res, text) : h("div", { class: "x" }, res));
}

// ---------------------------------------------------------------- views
function chronicle(p) {
  const [top, ...rest] = p.feed;
  if (!top) {
    return h("div", { class: "spot idle" }, h("div", {},
      h("div", { class: "h-title", style: { fontFamily: "var(--f-display)", color: "var(--gules)" } }, "Pendragon"),
      flourish(), h("p", {}, "The tale is about to begin…")));
  }
  const fresh = top.id !== last.heroId;
  last.heroId = top.id;
  return h("div", { class: "chronicle" },
    h("div", { class: "spot" }, hero(top, fresh)),
    h("div", { class: "feed" }, h("h2", {}, "Earlier"), rest.slice(0, 10).map(mini)));
}

function fighter(f) {
  const prev = last.states[f.id];
  const hit = prev && prev !== `${f.wound_state}/${f.cur_hp ?? ""}`;
  last.states[f.id] = `${f.wound_state}/${f.cur_hp ?? ""}`;
  const stCls = `s-${f.wound_state.toLowerCase().replace(/\s+/g, "-")}`;
  const hp = f.side === "party" && f.max_hp ? [
    h("div", { class: "hp" }, h("i", { style: { width: `${Math.max(0, Math.min(100, (f.cur_hp / f.max_hp) * 100))}%` } })),
  ] : null;
  return h("div", { class: `card fighter ${stCls} ${f.elite ? "elite" : ""} ${f.named ? "named" : ""} ${hit ? "hit" : ""}` },
    shield(f),
    h("div", { class: "nm" }, f.name, f.elite ? h("span", { class: "crown" }, "♛") : null),
    h("div", { class: "st" }, f.side === "party" ? h("span", { class: "hp-num" }, `${f.cur_hp} / ${f.max_hp} HP · `) : null, f.wound_state),
    f.engaged_with ? h("div", { class: "eng" }, `⚔ ${f.engaged_with}`) : hp ? h("div", {}, hp) : null);
}

function battle(p) {
  const cs = p.combat;
  if (!cs) return chronicle(p);
  const knights = cs.combatants.filter((c) => c.side === "party");
  const foes = cs.combatants.filter((c) => c.side !== "party");
  const latestRoll = p.feed.find((c) => c.type.startsWith("roll.") || c.type === "sealed" || c.type === "combat.check");
  const others = p.feed.filter((c) => c !== latestRoll).slice(0, 7);
  let latest = null;
  if (latestRoll) {
    const d = latestRoll.data || {};
    const n = latestRoll.type === "roll.check" ? d.roll : d.total ?? (latestRoll.type === "sealed" ? "?" : d.roll ?? "");
    const num = h("div", { class: "bign" }, n);
    if (latestRoll.id !== last.heroId && typeof n === "number") tumble(num, n);
    last.heroId = latestRoll.id;
    latest = h("div", { class: "card latest" },
      h("div", { class: "rollline" }, num, h("div", { style: { minWidth: 0 } },
        h("div", { class: "lt" }, latestRoll.title || (latestRoll.type === "sealed" ? "A secret roll" : "Roll")),
        d.outcome ? h("span", { class: `ribbon ${d.outcome}` }, OUT[d.outcome]) : h("div", { class: "lx" }, latestRoll.text))));
  }
  return h("div", { class: "battle" },
    h("div", { class: `sides ${knights.length && foes.length ? "" : "solo"}` },
      knights.length ? h("section", { class: "host knights" }, h("h2", {}, "The Knights"), h("div", { class: "grid" }, knights.map(fighter))) : null,
      foes.length ? h("section", { class: "host foes" }, h("h2", {}, "The Foe"), h("div", { class: "grid" }, foes.map(fighter))) : null),
    h("div", { class: "fray" }, h("div", { class: "side-head" }, "The Fray"), latest, others.map(mini)));
}

function render(p) {
  $("title").textContent = p.session.scratch ? "Pendragon" : p.session.title;
  document.title = `${p.session.scratch ? "Pendragon" : p.session.title} — The Table`;
  const combat = p.mode === "combat" && p.combat;
  clear($("mode"), combat
    ? [h("span", {}, p.combat.active ? p.combat.name : `${p.combat.name} — ended`), h("span", { class: "round" }, "Round ", h("span", { class: "rn" }, p.combat.round))]
    : h("span", {}, "The Chronicle"));
  clear($("view"), combat ? battle(p) : chronicle(p));
}

// ---------------------------------------------------------------- live
async function refresh() {
  try {
    const r = await fetch("/api/table");
    if (r.ok) render(await r.json());
  } catch { /* the stream reconnects and refreshes */ }
}

function connect() {
  const es = new EventSource("/api/stream");
  const go = debounce(refresh, 60);
  es.onopen = () => { $("offline").classList.remove("on"); go(); };
  es.onerror = () => $("offline").classList.add("on");
  es.onmessage = () => go();
}

$("view").style.cssText = "min-height:0;display:grid";
refresh();
connect();
