// The Table screen: a live, player-safe view of the session. The server sends
// only what players may see (see web/table.py); this file just makes it sing.

import { h, clear, icon, debounce } from "./lib.js";
import { knightCard, moraleGauge, cardFrame, deckSpread, knightShield as knightShieldEl } from "./board.js";

const $ = (id) => document.getElementById(id);
let last = { heroId: null, states: {}, titleCard: null };

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
  npc: ["#7a2f55", "#efe3c6"],
  beast: ["#2f6b3e", "#efe3c6"], monster: ["#1b1612", "#b3342a"], fae: ["#3a8fb0", "#efe3c6"],
};
function shield(f) {
  const key = f.side === "party" ? "party" : f.npc ? "npc" : f.named ? "named" : (TINCTURE[f.category] ? f.category : "foe");
  const [field, charge] = TINCTURE[key];
  const rim = f.elite ? "#d2a645" : "#4e3a28";
  const slain = f.status === "dead" ? '<path d="M10 12 34 44M34 12 10 44" stroke="#2a1d14" stroke-width="3.5"/>' : "";
  const chargeShape = f.side === "party"
    ? `<path d="M6 32 22 18l16 14" fill="none" stroke="${charge}" stroke-width="4"/>`
    : f.npc ? `<path d="M14 36V24a8 8 0 0 1 16 0v12M22 16v20M17 26h10" fill="none" stroke="${charge}" stroke-width="3"/>`
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
      ribbon, faces,
      t === "roll.check" && d.shown ? h("div", { class: "vs" }, `against ${d.shown}`) : null,
      c.revealed ? h("div", { class: "vs" }, "— revealed —") : null);
  }
  if (t === "combat.blow" && d.blow) {
    const b = d.blow;
    const shown = d.to_knight ? b.damage : b.wound;
    const num = h("div", { class: "n" }, shown);
    if (fresh) tumble(num, shown);
    const faces = h("div", { class: "dicefaces" }, b.terms.flatMap((term, i) => term.rolls.length
      ? term.rolls.map((r, j) => h("div", { class: `face ${term.label !== "damage" ? "bonus" : ""}`, title: term.label, style: { animationDelay: `${(i * 6 + j) * 50}ms` } }, r))
      : [h("div", { class: "face const" }, term.total)]));
    const steps = [`${b.full} rolled`];
    if (b.rebated) steps.push(`rebated ½ → ${b.damage}`);
    if (d.to_knight) steps.push(d.knight_shield ? "armour + shield/parry apply" : "armour only");
    if (b.armour) steps.push(`− ${b.armour} armour`);
    if (b.shield_roll != null) steps.push(`− ${b.shield_blocked} shield (1D6)`);
    else if (b.shield_blocked) steps.push(`− ${b.shield_blocked} shield`);
    const outcome = d.to_knight ? "" : d.mortal ? "Slain!" : d.major ? "Major Wound!" : b.wound ? "" : "Turned aside";
    const extras = d.to_knight ? [] : [b.knockdown === "automatic" ? "Knocked down!" : b.knockdown === "check" ? "Knockdown — DEX roll!" : "",
      b.shield_broken ? "Shield broken!" : ""].filter(Boolean);
    return h("div", { class: `hero rollhero ${b.critical ? "critical-glow" : ""}` },
      h("div", { class: "who" }, d.attacker ? `${d.attacker} — ${d.weapon}` : d.weapon),
      d.target ? h("div", { class: "vs", style: { marginTop: "0" } }, `strikes ${d.target}`) : null,
      h("div", { class: "medal" }, medalBg(b.critical ? "#d2a645" : "#8e2219"), num),
      h("div", { class: `ribbon ${b.critical ? "critical" : "failure"}` }, b.critical ? "Critical hit" : b.reckless ? "Reckless blow" : "Damage"),
      faces,
      h("div", { class: "blowsteps" }, steps.join("  ·  ")),
      outcome || extras.length ? h("div", { class: "blowfx" }, [outcome, ...extras].filter(Boolean).join("  ·  ")) : null);
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
const MINI_ICON = (t) => t === "combat.blow" || t === "roll.damage" ? "drop" : t === "combat.attack" ? "swords" : t.startsWith("roll.") || t === "combat.check" ? "d20" : t === "sealed" ? "lock"
  : t.startsWith("combat.") ? "swords" : t.startsWith("npc.") ? "helm" : t === "narrate" ? "feather"
  : t === "rule.shown" ? "book" : "scroll";

function mini(c) {
  const d = c.data || {};
  let res = null;
  if (c.type === "roll.check" && d.outcome) res = h("span", { class: "res", style: { color: { critical: "#b08a36", success: "#2f6b3e", failure: "#8e2219", fumble: "#1b1612" }[d.outcome] } }, `${d.roll} ${OUT[d.outcome]}`);
  if (c.type === "roll.dice") res = h("span", { class: "res" }, d.total);
  if (c.type === "roll.damage") res = h("span", { class: "res dmg" }, `${d.total} damage`);
  if (c.type === "combat.blow" && d.blow) res = h("span", { class: "res dmg" }, d.to_knight ? `${d.blow.damage} damage` : `${d.blow.wound} wound`);
  let text = c.text;
  if (c.type.startsWith("npc.") && d.npc) text = d.npc.subtitle;
  if (c.type === "narrate") text = d.style === "scene" ? "" : d.text || "An image";
  if (c.type === "roll.check") text = d.shown ? `vs ${d.shown}` : "";
  if (c.type === "roll.dice" || c.type === "roll.damage") text = text.replace(/^.*?(damage)?: /, "");
  if (c.type === "combat.blow" && d.blow) text = d.narrative || text;
  const title = c.title || (c.type === "narrate" ? (d.style === "scene" ? "Scene" : "Narration") : c.type === "sealed" ? "A secret roll" : "");
  if (c.type === "session.started" || c.type === "session.resumed") text = c.type === "session.started" ? "The session begins" : "The session resumes";
  return h("div", { class: `card mini ${c.type === "sealed" ? "sealed" : ""} ${isDamage(c) ? "k-dmg" : c.type.startsWith("roll.") ? "k-roll" : ""} ${isCrit(c) ? "crit" : ""}` },
    h("div", { class: "ic" }, icon(MINI_ICON(c.type))),
    h("div", { class: "t" }, title || text),
    title ? h("div", { class: "x" }, isCrit(c) ? h("span", { class: "critmark" }, "★ Critical") : null, res, text) : h("div", { class: "x" }, res));
}

// ---------------------------------------------------------------- views
function chronicle(p) {
  const [top, ...rest] = p.feed;
  if (top && top.type === "battle.finale" && top.data?.summary) return h("div", { class: "chronicle" },
    h("div", { class: "spot" }, finaleScene(top.data.summary)), h("div", { class: "feed" }, h("h2", {}, "Earlier"), rest.slice(0, 10).map(mini)));
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

// Rolls and damage look different at a glance: a roll is a number on a die
// (gold, with its outcome); damage is a number on a red seal, with the sum
// that produced it. Players must never mistake "rolled 9" for "took 9".
const isDamage = (c) => c.type === "combat.blow" || c.type === "roll.damage";
const DIE = '<path d="M50 4 92 28v44L50 96 8 72V28Z" fill="none" stroke="currentColor" stroke-width="4"/><path d="M50 4 8 72h84ZM8 28l42 24 42-24M50 52v44" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".45"/>';
const SEAL = '<path d="M50 3c8 9 16 2 22 10s-1 16 8 22 4 16 9 24-6 14-5 22-12 9-17 15-14 0-17 0-11 6-17 0-17-7-17-15-9-14-4-22 1-16 9-24-1-15 8-22 14 0 22-10Z" fill="currentColor"/>';
const BURST = Array.from({ length: 16 }, (_, i) => { const a = (i * Math.PI) / 8, b = a + Math.PI / 16;
  return `<path d="M50 50 L${50 + 50 * Math.cos(a)} ${50 + 50 * Math.sin(a)} L${50 + 50 * Math.cos(b)} ${50 + 50 * Math.sin(b)}Z" fill="currentColor"/>`; }).join("");
const isCrit = (c) => { const d = c.data || {}; return d.outcome === "critical" || !!d.critical || !!d.blow?.critical; };
const badgeSvg = (markup) => { const x = document.createElement("span"); x.innerHTML = `<svg viewBox="0 0 100 100" aria-hidden="true">${markup}</svg>`; return x.firstChild; };

function blowLines(d) {
  const b = d.blow;
  if (d.to_knight) {
    return [`${b.full} rolled${b.rebated ? ` · rebated ½ → ${b.damage}` : ""}`,
      d.knight_shield ? "Subtract your armour and shield" : "Subtract your armour (no shield)"];
  }
  const sum = [`${b.full} rolled`];
  if (b.rebated) sum.push(`½ → ${b.damage}`);
  if (b.armour) sum.push(`− ${b.armour} armour`);
  if (b.shield_blocked) sum.push(`− ${b.shield_blocked} shield`);
  return [`${sum.join(" ")} = ${b.wound}`];
}

// Headline chips: the sentence tells the story, these shout the big outcomes.
function blowFx(d) {
  return [d.mortal ? "Slain!" : d.major ? "Major Wound!" : ""].filter(Boolean);
}

// The latest roll, big, for the Fray column.
function latestRollCard(p) {
  const latestRoll = p.feed.find((c) => c.type.startsWith("roll.") || c.type === "sealed" || c.type === "combat.check" || c.type === "combat.blow");
  if (!latestRoll) return [null, p.feed.slice(0, 7)];
  const d = latestRoll.data || {};
  const dmg = isDamage(latestRoll);
  const n = latestRoll.type === "roll.check" ? d.roll : latestRoll.type === "combat.blow" ? (d.to_knight ? d.blow?.damage : d.blow?.wound)
    : d.total ?? (latestRoll.type === "sealed" ? "?" : d.roll ?? "");
  const num = h("div", { class: "bign" }, n);
  if (latestRoll.id !== last.heroId && typeof n === "number") tumble(num, n);
  last.heroId = latestRoll.id;
  const kindWord = !dmg ? "Roll" : latestRoll.type === "combat.blow" && !d.to_knight ? "Wound" : "Damage";
  const crit = isCrit(latestRoll);
  const badge = h("div", { class: `badge ${dmg ? "seal" : "die"} ${d.outcome || ""}` },
    crit ? h("span", { class: "burst" }, badgeSvg(BURST)) : null,
    badgeSvg(dmg ? SEAL : DIE), num, h("span", { class: "kw" }, kindWord));
  let body;
  if (latestRoll.type === "combat.blow" && d.blow) {
    const fx = blowFx(d);
    body = [h("div", { class: "story" }, d.narrative || latestRoll.text),
      blowLines(d).map((x) => h("div", { class: "lx sum" }, x)),
      fx.length ? h("div", { class: "fxrow" }, fx.map((x) => h("span", { class: "fxx" }, x))) : null];
  } else if (latestRoll.type === "roll.damage") {
    body = [h("div", { class: "lt" }, latestRoll.title || d.label || "Damage"),
      h("div", { class: "lx sum" }, `${d.expr || ""}${d.critical ? " · critical" : ""}${d.rebated ? " · rebated ½" : ""}`)];
  } else {
    body = [h("div", { class: "lt" }, latestRoll.title || (latestRoll.type === "sealed" ? "A secret roll" : "Roll")),
      d.outcome ? [h("span", { class: `ribbon ${d.outcome}` }, OUT[d.outcome]), d.shown ? h("div", { class: "lx" }, `against ${d.shown}`) : null]
        : h("div", { class: "lx" }, latestRoll.text)];
  }
  const card = h("div", { class: `card latest ${dmg ? "k-dmg" : "k-roll"} ${crit ? "crit" : ""} ${crit && latestRoll.id !== last.critId ? "crit-new" : ""}` },
    crit ? h("div", { class: "critbanner" }, "★ ", dmg ? (latestRoll.type === "combat.blow" ? "Critical hit!" : "Critical damage!") : "Critical!", " ★") : null,
    h("div", { class: "rollline" }, badge, h("div", { style: { minWidth: 0 } }, body)));
  if (crit) last.critId = latestRoll.id;
  return [card, p.feed.filter((c) => c !== latestRoll).slice(0, 6)];
}

const FATE_WORD = { dead: "slain", fled: "fled", surrendered: "surrendered", unconscious: "unconscious" };

// A foe on the players' board: shield, name, wound word, Disarmed.
function foeTile(f, p) {
  const c = p.combat.combatants.find((x) => x.id === f.id) || f;
  const prev = last.states[f.id];
  const hit = prev && prev !== f.wound_state;
  last.states[f.id] = f.wound_state;
  const ws = (f.wound_state || "").toLowerCase().replace(/\s+/g, "-");
  return h("div", { class: `tfoe s-${ws} ${c.elite ? "elite" : ""} ${hit ? "hit" : ""}` },
    shield(c), h("b", {}, f.name), h("span", { class: "wd" }, f.wound_state),
    (f.chips || []).map((x) => h("span", { class: "tchip" }, x)));
}

// The fight view: one lane per knight (their card, then the foes on them),
// a Defeated / Waiting footer, and the Fray with the latest roll.
function fight(p) {
  const cs = p.combat;
  if (!cs) return chronicle(p);
  const knights = p.knights || [];
  const foes = cs.combatants.filter((c) => c.side !== "party");
  const [latest, others] = latestRollCard(p);
  const defeated = foes.filter((f) => FATE_WORD[f.status]);
  const engagedNames = new Set(knights.map((k) => k.name));
  const waiting = foes.filter((f) => f.status === "active" && !engagedNames.has(f.engaged_with));
  const lanes = knights.length
    ? knights.map((k) => h("div", { class: "tlane" }, knightCard(k),
        h("div", { class: "tlane-foes" }, k.lane.foes.length ? k.lane.foes.map((f) => foeTile(f, p))
          : h("span", { class: "tlane-none" }, k.status === "active" ? "No foe engaged" : ""))))
    : [h("div", { class: "tlane solo" }, h("div", { class: "tlane-foes" }, foes.filter((f) => f.status === "active").map((f) => foeTile({ ...f, chips: [] }, p))))];
  const bt = cs.battle && p.battle && p.battle.id === cs.battle.id ? p.battle : null;
  // Which foes go for the horses is the GM's secret: the players find out when a horse is struck.
  const banners = [bt?.countercharge ? "They countercharge!" : null,
    bt?.barrage ? `${bt.barrage} round${bt.barrage === 1 ? "" : "s"} of arrows before contact` : null].filter(Boolean);
  return h("div", { class: "fightview" },
    h("div", { class: "lanes" },
      bt ? h("div", { class: "fv-head" }, h("span", { class: "fv-battle" }, `${bt.name} · Day ${bt.day} · Turn ${bt.turn}`),
        bt.morale ? h("span", { class: `fv-morale band-${(bt.morale.band || "").toLowerCase()}` }, h("span", { class: "lbl" }, "Morale"),
          h("span", { class: "mb" }, h("i", { style: { width: `${Math.round(100 * bt.morale.current / Math.max(1, bt.morale.start))}%` } })),
          h("b", {}, bt.morale.current), h("span", { class: "mw" }, bt.morale.band)) : null) : null,
      banners.length ? h("div", { class: "row", style: { gap: "10px", flexWrap: "wrap" } }, banners.map((x) => h("div", { class: "fv-banner" }, x))) : null,
      lanes,
      defeated.length || waiting.length ? h("div", { class: "fv-foot" },
        defeated.length ? [h("span", { class: "lbl" }, "Defeated"), defeated.map((f) => h("span", { class: "dft" },
          h("s", {}, f.name), ` ${FATE_WORD[f.status]}`, f.credit ? h("span", { class: "dcr" }, ` ✦${f.credit.glory} ${f.credit.name}`) : null,
          f.captured_by_name ? h("span", { class: "dcr" }, ` · captive of ${f.captured_by_name}`) : null))] : null,
        waiting.length ? [h("span", { class: "lbl" }, "Waiting"), h("span", {}, waiting.map((f) => f.name).join(", "))] : null) : null),
    h("div", { class: "fray" }, h("div", { class: "side-head" }, "The Fray"), latest, others.map(mini)));
}

// The battle view (between fights): title band, the Morale gauge, the
// centre stage (title card, revealed turn scripts; cards arrive with the turn
// loop), and the Fray.
const STATUS_LINE = { mustering: "The conroi musters", paused: "The battle is paused", rear: "At the rear" };
// The finale: outcome, then one card per knight with their Glory breakdown.
function finaleScene(f) {
  return h("div", { class: "finale" },
    h("div", { class: "fin-kicker" }, f.name),
    h("div", { class: "fin-outcome" }, f.outcome_label),
    h("div", { class: "fin-line" }, f.line),
    h("div", { class: "fin-cards" }, f.knights.map((k) => h("div", { class: "fin-card" },
      h("div", { class: "fin-top" }, knightShieldEl(), h("span", { class: "fin-name" }, k.name)),
      h("div", { class: "fin-total" }, k.total, h("small", {}, " Glory")),
      h("ul", {}, h("li", {}, h("span", {}, "Foes defeated"), h("span", {}, k.encounter_glory)),
        h("li", {}, h("span", {}, `Participation${k.role_label ? ` (${k.role_label})` : ""}`), h("span", {}, k.participation)),
        k.plunder ? h("li", {}, h("span", {}, "Plunder"), h("span", {}, k.plunder)) : null,
        (k.ransoms || []).map((r) => h("li", {}, h("span", {}, `Ransom · ${r.captive}`), h("span", {}, r.amount || "—"))))))));
}

function battleView(p) {
  const b = p.battle;
  if (!b) return chronicle(p);
  if (b.finale && b.status === "aftermath") return finaleScene(b.finale);
  const titleFresh = b.title_card && b.title_card.id !== last.titleCard;
  last.titleCard = b.title_card?.id;
  const tt = b.this_turn || {};
  const centre = [];
  if (b.banner) centre.push(h("div", { class: `resbanner ${b.banner.tone}` }, b.banner.text));
  else if (STATUS_LINE[b.status]) centre.push(h("div", { class: "bv-status" }, STATUS_LINE[b.status]));
  const cards = [];
  if (tt.set) cards.push(cardFrame(tt.set, { kind: tt.picks?.length ? "The GM sets" : "This turn", small: tt.picks?.length > 0 }));
  for (const pk of tt.picks || []) {
    if (pk.name === tt.set?.name) continue;
    cards.push(cardFrame(pk, { kind: pk.opportunity ? "★ Opportunity" : "Picked", token: pk.knight_name.split(" ").slice(-1)[0], crit: pk.crit }));
  }
  if (cards.length) centre.push(h("div", { class: `slots ${tt.selected ? "chosen" : ""}` }, cards));
  else if (b.status === "mustering" || titleFresh || !tt.set) {
    centre.push(h("div", { class: `bv-title ${titleFresh ? "fresh" : ""}` },
      h("div", { class: "bv-kicker" }, b.size_label, b.days > 1 ? ` · ${b.days} days` : ""),
      h("div", { class: "bv-name" }, b.name),
      b.where ? h("div", { class: "bv-where" }, b.where) : null,
      b.against ? h("div", { class: "bv-against" }, `against ${b.against}`) : null,
      flourish(),
      h("div", { class: "bv-day" }, `Day ${b.day}`, b.intensity ? ` · Intensity ${b.intensity}` : "")));
  }
  for (const r of b.results || []) centre.push(h("div", { class: `bv-script ${r.kind}` }, r.text));
  if (b.deck && (b.deck.foes.length || b.deck.opportunities.length)) centre.push(deckSpread(b.deck));
  return h("div", { class: "battleview" },
    moraleGauge(b.morale),
    h("div", { class: "bv-centre" }, centre),
    h("div", { class: "fray" }, h("div", { class: "side-head" }, "The Fray"), p.feed.slice(0, 6).map(mini)),
    (p.battle_knights || []).length ? h("div", { class: "bv-knights" }, p.battle_knights.map((k) => knightCard(k, { compact: true }))) : null);
}

function render(p) {
  $("title").textContent = p.session.scratch ? "Pendragon" : p.session.title;
  document.title = `${p.session.scratch ? "Pendragon" : p.session.title} — The Table`;
  const combat = p.mode === "combat" && p.combat;
  const battle = p.mode === "battle" && p.battle;
  clear($("mode"), combat
    ? [h("span", {}, p.combat.active ? p.combat.name : `${p.combat.name} — ended`), h("span", { class: "round" }, "Round ", h("span", { class: "rn" }, p.combat.round))]
    : battle ? (battle.status === "aftermath" ? h("span", {}, "The battle is done")
      : [h("span", {}, battle.turn ? `Day ${battle.day} · Turn ${battle.turn} of ${battle.turns_today}` : `Day ${battle.day}`),
        battle.intensity ? h("span", { class: "round" }, "Intensity ", h("span", { class: "rn" }, battle.intensity)) : null])
    : h("span", {}, "The Chronicle"));
  if (battle) $("title").textContent = battle.name;
  clear($("view"), combat ? fight(p) : battle ? battleView(p) : chronicle(p));
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
