// GM console shell: tool rail + router, the live session log, the dice tray,
// session controls, and the ctx object every tool receives.

import { liveStream } from "./stream.js";
import { h, clear, api, post, toast, modal, menu, icon, time, debounce, download,
  OUTCOME_LABEL, skillDisplay, copyText } from "./lib.js";

const TOOLS = [
  { id: "npc", label: "NPCs", icon: "helm" },
  { id: "cast", label: "Cast", icon: "crowd" },
  { id: "combat", label: "Combat", icon: "swords" },
  { id: "battle", label: "Battle", icon: "banner" },
  { id: "party", label: "Party", icon: "party" },
  null,
  { id: "adversaries", label: "Adversaries", icon: "dragon" },
  { id: "encounters", label: "Encounters", icon: "flag" },
  { id: "battles", label: "Battles", icon: "banner" },
  { id: "rules", label: "Rules", icon: "book" },
  { id: "sessions", label: "Sessions", icon: "archive" },
];

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ state
const S = {
  session: null,
  events: [],          // projected events (with struck/revealed)
  lastId: 0,
  filter: "all",
  tools: {},           // id -> {el, inst}
  current: null,
  listeners: new Set(),
  handoff: {},         // cross-tool payloads, e.g. npc -> adversary draft
  combatActive: false,
};

// ------------------------------------------------------------------ ctx
const ctx = {
  navigate(id, payload) {
    if (payload !== undefined) S.handoff[id] = payload;
    location.hash = `#/${id}`;
    if (S.current === id) S.tools[id]?.inst?.show?.(takeHandoff(id));
  },
  onEvent(fn) { S.listeners.add(fn); return () => S.listeners.delete(fn); },
  get session() { return S.session; },
  get spot() { return S.spot; },
  get events() { return S.events; },

  async rollCheck({ label, value, kind = "skill", actor = "", modifier = 0, masked }) {
    // Click-to-roll from a statblock is always public; Secret is the dice tray's own toggle.
    const r = await post("/api/roll/check", { label, value, kind, actor, modifier,
      masked: masked ?? false, show_label: tray.showLabel });
    showLastRoll(r.event);
    return r.event;
  },

  /** Ask normal/critical (+4D6) and rebated, then roll. path/extra let combat use its own endpoint. */
  async rollDamage({ label, expr, actor = "", path = "/api/roll/damage", extra = {} }) {
    const choice = await damageChooser(`${actor ? actor + " — " : ""}${label} (${expr})`);
    if (!choice) return null;
    const r = await post(path, { label, expr, actor, ...extra, ...choice });
    showLastRoll(r.event);
    return r.event;
  },
  showLastRoll: (ev) => showLastRoll(ev),
  get masked() { return tray.masked; },
};

function takeHandoff(id) {
  const p = S.handoff[id];
  delete S.handoff[id];
  return p;
}

function damageChooser(prompt) {
  return modal("Damage roll", (close) => {
    const reb = h("input", { type: "checkbox" });
    return [
      h("p", { class: "muted" }, prompt),
      h("label", { class: "check", style: { marginBottom: "14px" } }, reb, "Rebated — ½ damage (blunted / tournament weapon)"),
      h("div", { class: "stack" },
        h("button", { class: "btn primary", onclick: () => close({ critical: false, rebated: reb.checked }) }, "Normal damage"),
        h("button", { class: "btn", onclick: () => close({ critical: true, rebated: reb.checked }) }, "Critical — +4D6"),
        h("button", { class: "btn ghost", onclick: () => close(null) }, "Cancel (don't roll or log)")),
    ];
  });
}

// ------------------------------------------------------------------ rail & router
function buildRail() {
  const rail = $("rail");
  for (const t of TOOLS) {
    if (!t) { rail.append(h("hr")); continue; }
    rail.append(h("a", { href: `#/${t.id}`, id: `rail-${t.id}`, title: t.label }, icon(t.icon), t.label));
  }
}

async function route() {
  const id = (location.hash.match(/^#\/([a-z]+)/) || [])[1] || "npc";
  const def = TOOLS.find((t) => t && t.id === id) || TOOLS[0];
  document.querySelectorAll(".rail a").forEach((a) => a.classList.toggle("active", a.id === `rail-${def.id}`));
  S.current = def.id;
  for (const [tid, t] of Object.entries(S.tools)) t.el.hidden = tid !== def.id;
  let t = S.tools[def.id];
  if (!t) {
    const el = h("section", { class: "tool" });
    $("main").append(el);
    t = S.tools[def.id] = { el, inst: null };
    try {
      const mod = await import(`./tools/${def.id}.js`);
      t.inst = (await mod.default.mount(el, ctx, takeHandoff(def.id))) || {};
    } catch (e) {
      console.error(e);
      clear(el, h("div", { class: "empty" }, `Couldn't load ${def.label}: ${e.message}`));
    }
  } else {
    t.inst?.show?.(takeHandoff(def.id));
  }
  document.title = `${def.label} — Pendragon GM`;
}

// ------------------------------------------------------------------ session & log
const KIND = (t) => t.startsWith("roll.") ? ["roll", "d20"]
  : t === "combat.check" ? ["roll", "d20"]
  : t === "combat.blow" || t === "combat.attack" ? ["combat", "swords"]
  : t.startsWith("combat.") ? ["combat", "swords"]
  : t.startsWith("glory.") ? ["combat", "star"]
  : t.startsWith("battle.") ? ["combat", "banner"]
  : t.startsWith("npc.") ? ["npc", "helm"]
  : t === "narrate" ? ["narrate", "feather"]
  : t === "note" ? ["note", "note"]
  : t === "rule.shown" || t === "rule.hidden" ? ["rule", "book"]
  : t === "divider" ? ["combat", "scroll"]
  : t.startsWith("session.") ? ["session", "flag"]
  : t === "table.cleared" ? ["meta", "present"]
  : t.startsWith("meta.") ? ["meta", "undo"] : ["other", "scroll"];

const FILTERS = [["all", "All"], ["roll", "Rolls"], ["combat", "Combat"], ["battle", "Battle"], ["npc", "NPCs"], ["narrate", "Story"]];

// Battle grouping: each event's "DAY 1 · TURN 3" (or "· FIGHT", "AFTERMATH")
// label, worked out in order so a linked fight's combat events join its turn.
function battleGroups(events) {
  const out = new Map();
  let fight = null;
  for (const ev of events) {
    const link = ev.data?.battle;
    if (ev.type === "combat.started") fight = link || null;
    let label = null;
    if (fight && (ev.type.startsWith("combat.") || ev.type.startsWith("glory.") || (ev.type.startsWith("roll.") && ev.data?.cid))) {
      label = `Day ${fight.day} · Turn ${fight.turn} · Fight`;
    } else if (link) {
      label = link.step === "aftermath" ? "Aftermath" : link.turn ? `Day ${link.day} · Turn ${link.turn}` : `Day ${link.day} · Muster`;
    }
    if (ev.type === "combat.ended") fight = null;
    if (label) out.set(ev.id, label);
  }
  return out;
}

function buildLog() {
  const list = h("div", { class: "log-list", id: "logList" });
  const filters = h("div", { class: "chips", style: { padding: "8px 12px 0" } },
    FILTERS.map(([k, label]) => h("button", { class: `chip ${k === S.filter ? "on" : ""}`, "data-f": k,
      onclick: () => { S.filter = k; S.logLimit = LOG_SHOW; filters.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c.dataset.f === k)); renderLog(); } }, label)));
  clear($("log"),
    h("div", { class: "log-head" }, h("h2", {}, "Session Log"), h("span", { class: "spacer" }),
      h("button", { class: "btn ghost sm", title: "Export the chronicle", onclick: (e) => exportMenu(e.currentTarget) }, icon("download"), "Export")),
    filters, list, buildTray());
}

function exportMenu(anchor) {
  const id = S.session?.scratch ? "" : S.session?.id;
  menu(anchor, [
    ["Chronicle (Markdown)", () => download(`/api/session/chronicle.md?id=${id || ""}`), { icon: "scroll" }],
    ["Chronicle (web page)", () => window.open(`/api/session/chronicle.html?id=${id || ""}`, "_blank"), { icon: "book" }],
    ["Raw session file (JSON)", () => download(`/api/session/download?id=${id || ""}`), { icon: "download" }],
  ]);
}

function matchesFilter(ev) {
  if (ev.type.startsWith("meta.")) return false;
  if (S.filter === "all") return true;
  if (S.filter === "battle") return ev.type.startsWith("battle.") || !!ev.data?.battle || (S.groups?.has(ev.id) ?? false);
  const [k] = KIND(ev.type);
  if (S.filter === "narrate") return k === "narrate" || k === "note" || k === "rule" || k === "session";
  return k === S.filter;
}

function resultBits(ev) {
  const d = ev.data || {};
  if (ev.type === "roll.check" || ev.type === "combat.check") {
    return d.outcome ? h("span", { class: `result-pill o-${d.outcome}` }, `${d.roll} ${OUTCOME_LABEL[d.outcome] || ""}`) : null;
  }
  if (ev.type === "roll.dice" || ev.type === "roll.damage") return h("span", { class: "result-pill o-critical" }, d.total);
  if (ev.type === "roll.opposed") return h("span", { class: "result-pill o-critical" }, d.verdict);
  if (ev.type === "combat.blow") { const n = d.to_knight ? d.blow?.damage : d.blow?.wound;
    return h("span", { class: `result-pill ${n ? "o-fumble" : "o-success"}` }, `${n ?? 0} dmg`); }
  return null;
}

function entryEl(ev) {
  // a divider — or a new round — is a thin rule, not a card
  if (ev.type === "divider" || ev.type === "combat.round") {
    return h("div", { class: `log-divider ${ev.struck ? "struck" : ""} ${ev.type === "combat.round" ? "round" : ""}`, "data-id": ev.id },
      h("span", { class: "ld-line" }), h("span", { class: "ld-text" }, ev.type === "combat.round" ? `Round ${ev.data?.round ?? ""}` : ev.text),
      h("span", { class: "ld-line" }), h("span", { class: "time" }, time(ev.ts)),
      h("button", { class: "btn ghost sm icon ld-x", title: ev.struck ? "Restore" : "Strike (undo)",
        onclick: () => post(`/api/events/${ev.id}/${ev.struck ? "unstrike" : "strike"}`) }, icon(ev.struck ? "undo" : "strike")));
  }
  const [kind, ic] = KIND(ev.type);
  const cls = ["entry", `k-${kind}`, ev.struck && "struck", ev.visibility === "gm" && "gm",
    ev.masked && "masked", ev.revealed && "revealed"].filter(Boolean).join(" ");
  const flags = h("span", { class: "flags" },
    ev.visibility === "gm" ? h("span", { class: "tag purpure", title: "GM only — never shown on the Table" }, icon("eyeoff"), "GM") : null,
    ev.masked && !ev.revealed ? h("span", { class: "tag purpure", title: "Secret roll — sealed on the Table" }, icon("lock"), "secret") : null,
    ev.masked && ev.revealed ? h("span", { class: "tag", title: "Revealed to the table" }, icon("eye"), "revealed") : null);
  const actions = h("div", { class: "actions" },
    ev.masked && !ev.revealed && !ev.struck ? h("button", { class: "btn ghost sm icon", title: "Reveal to the table", onclick: () => post(`/api/events/${ev.id}/reveal`) }, icon("eye")) : null,
    kind !== "session" ? h("button", { class: "btn ghost sm icon", title: ev.struck ? "Restore" : "Strike (undo)",
      onclick: () => post(`/api/events/${ev.id}/${ev.struck ? "unstrike" : "strike"}`) }, icon(ev.struck ? "undo" : "strike")) : null,
    h("button", { class: "btn ghost sm icon", title: "Copy", onclick: () => copyText(ev.text, "Copied") }, icon("copy")));
  const title = ev.title || (kind === "narrate" ? (ev.data?.style === "scene" ? "Scene" : "Narration") : kind === "note" ? "GM note" : "");
  return h("div", { class: cls, "data-id": ev.id },
    h("div", { class: "ico" }, icon(ic)),
    h("div", { class: "head" }, title ? h("span", { class: "title" }, title) : null, flags, h("span", { class: "time" }, time(ev.ts))),
    h("div", { class: "text" }, resultBits(ev), ev.text),
    actions);
}

// The page keeps only the newest LOG_SHOW entries in the DOM (a long battle is
// thousands, and Firefox balloons); "Show earlier" reveals LOG_STEP more. The
// full log stays in S.events, and in the file.
const LOG_SHOW = 300, LOG_STEP = 300;

function renderLog() {
  const list = $("logList");
  S.groups = battleGroups(S.events);
  const all = S.events.filter(matchesFilter);
  S.logLimit = S.logLimit || LOG_SHOW;
  const shown = all.slice(-S.logLimit);
  S.rendered = shown.length;
  const rows = [];
  if (all.length > shown.length) {
    rows.push(h("button", { class: "btn ghost sm log-earlier", onclick: () => { S.logLimit += LOG_STEP; renderLog(); list.scrollTop = 0; } },
      `Show ${Math.min(LOG_STEP, all.length - shown.length)} earlier (${all.length - shown.length} hidden)`));
  }
  let last = null;
  for (const ev of shown) {
    const g = S.groups.get(ev.id) || null;
    if (g && g !== last) rows.push(h("div", { class: "log-group" }, g));
    last = g;
    rows.push(entryEl(ev));
  }
  S.lastGroup = last;
  clear(list, rows.length ? rows :
    h("div", { class: "empty", style: { margin: "12px" } }, icon("scroll"),
      S.session?.scratch ? "No session started — rolls still reach the Table but aren't saved." : "Nothing yet. Roll some dice!"));
  list.scrollTop = list.scrollHeight;
}

function applyIncoming(events) {
  for (const ev of events) {
    if (ev.type.startsWith("meta.")) {
      for (const id of ev.data.targets || [ev.data.target]) {      // a cascade undo strikes many
        const target = S.events.find((e) => e.id === id);
        if (!target) continue;
        if (ev.type === "meta.strike") target.struck = true;
        if (ev.type === "meta.unstrike") target.struck = false;
        if (ev.type === "meta.reveal") target.revealed = true;
      }
    }
    S.events.push(ev);
    S.lastId = Math.max(S.lastId, ev.id);
  }
}

async function loadSession() {
  const r = await api("/api/session");
  S.session = r.session;
  S.suggested = r.suggested_title;
  S.events = r.events;
  S.logLimit = LOG_SHOW;
  S.lastId = r.events.length ? r.events[r.events.length - 1].id : 0;
  renderSessionBar();
  renderLog();
}

async function fetchNew() {
  const r = await api(`/api/session/events?after=${S.lastId}`);
  if (r.session.id !== S.session?.id) return loadSession().then(() => notify(S.events, true));
  S.session = r.session;
  if (!r.events.length) return;
  const list = $("logList");
  const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
  applyIncoming(r.events);
  // Only a strike/reveal changes entries already on the page; everything else
  // (battle groups included — a group depends only on the events before it)
  // is appended, so a long battle log isn't rebuilt from scratch on every event.
  if (r.events.some((e) => e.type.startsWith("meta.")) || S.events.length < 3) renderLog();
  else {
    list.querySelector(".empty")?.remove();
    S.groups = battleGroups(S.events);
    for (const ev of r.events.filter(matchesFilter)) {
      const g = S.groups.get(ev.id) || null;
      if (g && g !== S.lastGroup) list.append(h("div", { class: "log-group" }, g));
      S.lastGroup = g;
      list.append(entryEl(ev));
      S.rendered++;
    }
    if (S.rendered > S.logLimit + 100) { renderLog(); list.scrollTop = list.scrollHeight; }
    if (atBottom) list.scrollTop = list.scrollHeight;
  }
  renderSessionBar();
  notify(r.events);
}

// The card on the Table right now (the spotlight): a chip in the bar takes it off from any tool.
async function refreshSpot() {
  try { S.spot = (await api("/api/spotlight")).spotlight?.name || null; } catch { return; }
  const chip = $("spotChip");
  chip.hidden = !S.spot;
  if (S.spot) { clear(chip, icon("present"), `On the Table: ${S.spot}  ✕`); chip.onclick = () => post("/api/spotlight/off"); }
}

function notify(events, reset = false) {
  if (reset || events.some((e) => e.type.startsWith("table.") || e.type.startsWith("battle.") || e.type.startsWith("session."))) refreshSpot();
  for (const fn of S.listeners) { try { fn(events, { reset }); } catch (e) { console.error(e); } }
}

function renderSessionBar() {
  const s = S.session;
  const t = $("sessionTitle");
  t.textContent = s.title;
  t.classList.toggle("scratch", s.scratch);
  $("recDot").classList.toggle("off", s.scratch);
  $("recDot").title = s.scratch ? "Not recording — start a session" : "Recording to the session file";
  $("sessionSub").textContent = s.scratch ? "" : `${s.count} event${s.count === 1 ? "" : "s"} · autosaved`;
  clear($("sessionControls"), s.scratch
    ? h("button", { class: "btn primary", onclick: startSession }, icon("play"), "Start session")
    : h("button", { class: "btn", onclick: endSession }, icon("stop"), "End session"));
}

async function startSession() {
  const title = await modal("Start a session", (close) => {
    const inp = h("input", { class: "input", value: S.suggested || "", onkeydown: (e) => e.key === "Enter" && close(inp.value) });
    return [
      h("p", { class: "muted" }, "Everything from now on — rolls, NPCs, combat, narration — is recorded to one session file and autosaved after every event."),
      h("label", { class: "field" }, h("span", {}, "Session name"), inp),
      h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
        h("button", { class: "btn primary", onclick: () => close(inp.value) }, "Begin")),
    ];
  });
  if (title === undefined) return;
  await post("/api/session/start", { title });
  await loadSession();
  toast("Session started — recording", "ok");
}

async function endSession() {
  const ok = await modal("End the session?", (close) => [
    h("p", { class: "muted" }, `“${S.session.title}” is saved. You can reopen it from Sessions to carry on later.`),
    h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close(false) }, "Keep playing"),
      h("button", { class: "btn primary", onclick: () => close(true) }, "End session")),
  ]);
  if (!ok) return;
  await post("/api/session/end");
  await loadSession();
}

// ------------------------------------------------------------------ table mode
let tableMode = "auto";
let tableScale = 1;
const TABLE_SCALES = [0.9, 1, 1.15, 1.3];
function renderTableMode() {
  const step = async (dir) => {
    const i = Math.max(0, Math.min(TABLE_SCALES.length - 1, TABLE_SCALES.indexOf(tableScale) + dir));
    await post("/api/table/scale", { scale: TABLE_SCALES[i] }); tableScale = TABLE_SCALES[i]; renderTableMode();
  };
  clear($("tableMode"), [["auto", "Auto"], ["chronicle", "Story"], ["combat", "Fight"], ["battle", "Battle"]].map(([m, label]) =>
    h("button", { class: `chip ${m === tableMode ? "on" : ""}`, title: m === "auto" ? "Table shows the fight during combat, the battle while one runs, otherwise the story" : `Pin the Table to ${label}`,
      onclick: async () => { await post("/api/table/mode", { mode: m }); tableMode = m; renderTableMode(); } }, label)),
    h("button", { class: "chip", id: "scaleDown", title: `Table text size ${Math.round(tableScale * 100)}% — smaller`, "aria-label": "Smaller Table text",
      disabled: tableScale <= TABLE_SCALES[0] || null, onclick: () => step(-1) }, "A−"),
    h("button", { class: "chip", id: "scaleUp", title: `Table text size ${Math.round(tableScale * 100)}% — bigger, for a stream that is hard to read`, "aria-label": "Bigger Table text",
      disabled: tableScale >= TABLE_SCALES.at(-1) || null, onclick: () => step(1) }, "A+"));
}

// ------------------------------------------------------------------ dice tray
const tray = { tab: "dice", masked: false, showLabel: false };

function maskControls() {
  const box = h("div", { class: "row" });
  const draw = () => clear(box,
    h("button", { class: `btn sm mask-toggle ${tray.masked ? "on" : ""}`, title: "Secret roll: the Table shows a sealed card; you can reveal it later",
      onclick: () => { tray.masked = !tray.masked; draw(); syncMask(); } }, icon(tray.masked ? "lock" : "eye"), tray.masked ? "Secret" : "Open"),
    tray.masked ? h("label", { class: "check small" }, h("input", { type: "checkbox", checked: tray.showLabel,
      onchange: (e) => { tray.showLabel = e.target.checked; } }), "show label on Table") : null);
  draw();
  box.redraw = draw;
  return box;
}
const maskBoxes = [];
const syncMask = () => maskBoxes.forEach((b) => b.redraw());

let lastRollEl;
function showLastRoll(ev) {
  if (!lastRollEl || !ev) return;
  const d = ev.data || {};
  let big = "", detail = ev.text;
  if (ev.type === "roll.dice" || ev.type === "roll.damage") big = d.total;
  else if (ev.type === "combat.blow") big = (d.to_knight ? d.blow?.damage : d.blow?.wound) ?? "";
  else if (ev.type === "roll.check") big = d.roll;
  else if (ev.type === "roll.opposed") big = d.winner ? "⚔" : "=";
  const cls = d.outcome ? `o-${d.outcome}` : "";
  clear(lastRollEl,
    h("div", { class: `big ${cls}` }, big),
    h("div", { class: "detail" }, ev.masked ? h("span", { class: "tag purpure" }, icon("lock"), "secret") : null, " ",
      d.outcome ? h("b", { class: cls }, (OUTCOME_LABEL[d.outcome] || "") + " · ") : null, detail));
}

function buildTray() {
  const body = h("div");
  const tabs = h("div", { class: "tray-tabs" });
  lastRollEl = h("div", { class: "last-roll" }, h("div", { class: "detail faint" }, "Roll results land here and in the log."));
  const TABS = [["dice", "Dice"], ["check", "Check"], ["opposed", "Opposed"], ["narrate", "Narrate"], ["note", "Note"]];
  const drawTabs = () => clear(tabs, TABS.map(([k, label]) => h("button", { class: k === tray.tab ? "on" : "", onclick: () => { tray.tab = k; drawTabs(); drawBody(); } }, label)));
  const drawBody = () => {
    maskBoxes.length = 0;
    clear(body, ({ dice: dicePane, check: checkPane, opposed: opposedPane, narrate: narratePane, note: notePane })[tray.tab]());
    body.querySelector("input,textarea")?.focus();
  };
  drawTabs(); drawBody();
  return h("div", { class: "tray" }, tabs, body, lastRollEl);
}

function withMask() { const m = maskControls(); maskBoxes.push(m); return m; }

function dicePane() {
  const expr = h("input", { class: "input", placeholder: "e.g. 3d6+2", style: { flex: 2 } });
  const label = h("input", { class: "input", placeholder: "Label (optional)", style: { flex: 3 } });
  const roll = async (e) => {
    const v = e || expr.value.trim();
    if (!v) return expr.focus();
    const r = await post("/api/roll/dice", { expr: v, label: label.value, masked: tray.masked, show_label: tray.showLabel });
    showLastRoll(r.event);
  };
  expr.addEventListener("keydown", (e) => e.key === "Enter" && roll());
  label.addEventListener("keydown", (e) => e.key === "Enter" && roll());
  return [
    h("div", { class: "dice-quick" }, ["d20", "d6", "2d6", "3d6", "4d6", "6d6"].map((d) =>
      h("button", { class: "die-btn", title: `Roll ${d}`, onclick: () => roll(d) }, icon(d === "d20" ? "d20" : "d6"), d))),
    h("div", { class: "row" }, expr, label),
    h("div", { class: "row" }, withMask(), h("span", { class: "spacer", style: { flex: 1 } }),
      h("button", { class: "btn primary sm", onclick: () => roll() }, icon("d20"), "Roll")),
  ];
}

function checkPane() {
  const label = h("input", { class: "input", placeholder: "What? e.g. Awareness", style: { flex: 3 } });
  const value = h("input", { class: "input num", type: "number", placeholder: "15" });
  const mod = h("input", { class: "input num", type: "number", placeholder: "±0", title: "Modifier" });
  const kind = h("select", { class: "input", style: { flex: 2 } },
    ["skill", "trait", "passion", "characteristic"].map((k) => h("option", { value: k }, k[0].toUpperCase() + k.slice(1))));
  const go = async () => {
    if (value.value === "") return value.focus();
    await ctx.rollCheck({ label: label.value || "Check", value: Number(value.value), kind: kind.value, modifier: Number(mod.value || 0) });
  };
  for (const el of [label, value, mod]) el.addEventListener("keydown", (e) => e.key === "Enter" && go());
  return [
    h("div", { class: "row" }, label, value, mod),
    h("div", { class: "row" }, kind, withMask(), h("button", { class: "btn primary sm", onclick: go }, icon("d20"), "Roll d20")),
    h("div", { class: "faint small", style: { marginTop: "6px" } }, "Critical on the exact value, fumble on 20; over 20 adds a critical bonus. Characteristics are pass/fail."),
  ];
}

function opposedPane() {
  const side = (ph) => [h("input", { class: "input", placeholder: ph, style: { flex: 3 } }), h("input", { class: "input num", type: "number", placeholder: "15" })];
  const [al, av] = side("Side A — e.g. Sir Bors, Sword");
  const [bl, bv] = side("Side B — e.g. Bandit, Spear");
  const go = async () => {
    if (av.value === "" || bv.value === "") return (av.value === "" ? av : bv).focus();
    const r = await post("/api/roll/opposed", { a: { label: al.value, value: Number(av.value) }, b: { label: bl.value, value: Number(bv.value) },
      masked: tray.masked, show_label: tray.showLabel });
    showLastRoll(r.event);
  };
  return [h("div", { class: "row" }, al, av), h("div", { class: "row" }, bl, bv),
    h("div", { class: "row" }, withMask(), h("span", { style: { flex: 1 } }), h("button", { class: "btn primary sm", onclick: go }, icon("swords"), "Resolve"))];
}

function narratePane() {
  let style = "read-aloud";
  const text = h("textarea", { class: "input", rows: 3, placeholder: "Read-aloud text, a scene title, or a caption…" });
  const url = h("input", { class: "input", placeholder: "Image link (https://…)", hidden: true });
  const chips = h("div", { class: "chips" });
  const draw = () => clear(chips, [["read-aloud", "Read-aloud"], ["scene", "Scene title"], ["image", "Image"]].map(([k, l]) =>
    h("button", { class: `chip ${k === style ? "on" : ""}`, onclick: () => { style = k; url.hidden = k !== "image"; draw(); } }, l)));
  draw();
  const go = async () => {
    await post("/api/narrate", { text: text.value, style, image_url: url.value });
    text.value = ""; url.value = "";
    toast("Shown on the Table", "ok");
  };
  text.addEventListener("keydown", (e) => (e.key === "Enter" && (e.ctrlKey || e.metaKey)) && go());
  return [chips, h("div", { style: { height: "6px" } }), text, url,
    h("div", { class: "row", style: { marginTop: "6px", justifyContent: "flex-end" } },
      h("span", { class: "faint small", style: { marginRight: "auto" } }, "Ctrl+Enter"),
      h("button", { class: "btn primary sm", onclick: go }, icon("present"), "Show on Table"))];
}

function notePane() {
  const text = h("textarea", { class: "input", rows: 3, placeholder: "A private note — kept in your log and session file, never shown on the Table." });
  const go = async () => {
    if (!text.value.trim()) return;
    await post("/api/note", { text: text.value });
    text.value = "";
  };
  text.addEventListener("keydown", (e) => (e.key === "Enter" && (e.ctrlKey || e.metaKey)) && go());
  return [text, h("div", { class: "row", style: { marginTop: "6px", justifyContent: "flex-end" } },
    h("span", { class: "faint small", style: { marginRight: "auto" } }, icon("lock"), " GM only"),
    h("button", { class: "btn sm", onclick: go }, icon("note"), "Add note"))];
}

// ------------------------------------------------------------------ live updates
// After a server restart (new code, or state the page fetched while it was
// down) reload the page; a brief network blip just reconnects.
let bootId = null;
async function checkBoot() {
  try {
    const b = (await (await fetch("/healthz", { cache: "no-store" })).json()).boot;
    if (bootId && b && b !== bootId) return location.reload();
    bootId = b;
  } catch { /* still down: the stream retries */ }
}
function connect() {
  const refresh = debounce(fetchNew, 40);
  liveStream({
    open: () => { checkBoot(); $("conn").classList.remove("down"); $("conn").textContent = "live"; refresh(); },
    error: () => { $("conn").classList.add("down"); $("conn").textContent = "reconnecting"; },
    message: (data) => {
      const msg = JSON.parse(data);
      if (msg.reason === "event") refresh();
      else if (msg.reason === "session") loadSession().then(() => notify(S.events, true));
      else if (msg.reason === "library") for (const t of Object.values(S.tools)) t.inst?.onLibrary?.();
    },
  });
}

// ------------------------------------------------------------------ boot
async function boot() {
  buildRail();
  buildLog();
  $("openTable").replaceChildren(icon("present"), "Open Table");
  $("clearTable").onclick = async () => { await post("/api/table/clear"); toast("Table cleared", "ok"); };
  // Pinned rules, reachable mid-fight: show one on the Table, or take the shown one off.
  $("pinnedRules").onclick = async (e) => {
    const anchor = e.currentTarget;                        // gone from the event after the await
    const [{ pins }, { shown }] = await Promise.all([api("/api/rules/pins"), api("/api/rules/shown")]);
    const items = [];
    if (shown) items.push([`Remove “${shown.title}” from the Table`, () => post("/api/rules/hide"), { icon: "present" }], null);
    for (const p of pins) items.push([p.id === shown?.rule_id ? `${p.title} ✓ on Table` : p.title,
      () => post(`/api/rules/${encodeURIComponent(p.id)}/show`), { icon: "book" }]);
    if (!pins.length) items.push(["No pinned rules — pin them in the Rules tool", () => { location.hash = "#/rules"; }, { icon: "pin" }]);
    items.push(null, ["Open the Rules tool", () => { location.hash = "#/rules"; }, { icon: "search" }]);
    menu(anchor, items);
  };
  $("openTable").onclick = () => window.open("/table", "pendragon-table", "width=1280,height=760");
  $("toggleLog").replaceChildren(icon("panel"));
  $("toggleLog").onclick = () => $("shell").classList.toggle("log-collapsed");
  try { const t = await api("/api/table"); tableMode = t.pinned; tableScale = t.scale ?? 1; } catch {}
  renderTableMode();
  await loadSession();
  refreshSpot();
  window.addEventListener("hashchange", route);
  await route();
  connect();
}

boot();
