// Small shared helpers for the GM console and the Table screen.
// No framework: h() builds elements, api() talks JSON to the server.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

// ---------------------------------------------------------------- api
export class ApiError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}

/** fetch JSON. Errors toast unless their HTTP status is listed in ``quiet``
 * (for callers that handle it themselves, e.g. a 409 overwrite prompt). */
export async function api(path, { method = "GET", body, raw = false, quiet = [] } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    toast("Can't reach the server — is it running?", "err");
    throw new ApiError("network");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    if (!quiet.includes(res.status)) toast(msg, "err");
    throw new ApiError(msg, res.status);
  }
  return raw ? res : res.json();
}
export const post = (path, body = {}, opts = {}) => api(path, { method: "POST", body, ...opts });
export const put = (path, body = {}, opts = {}) => api(path, { method: "PUT", body, ...opts });
export const patch = (path, body = {}) => api(path, { method: "PATCH", body });
export const del = (path) => api(path, { method: "DELETE" });
export const enc = encodeURIComponent;

// ---------------------------------------------------------------- feedback
let toastHost;
export function toast(text, kind = "") {
  toastHost ??= document.body.appendChild(h("div", { class: "toasts" }));
  const t = h("div", { class: `toast ${kind}` }, text);
  toastHost.append(t);
  setTimeout(() => t.remove(), kind === "err" ? 5000 : 2600);
}

export async function copyText(text, what = "Copied") {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = h("textarea", { style: { position: "fixed", opacity: 0 } }, text);
    document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  toast(`${what} to the clipboard`, "ok");
}

export function download(url) {
  const a = h("a", { href: url, download: "" });
  document.body.append(a); a.click(); a.remove();
}

/** A modal dialog. build(close) returns the body nodes; resolves with close(value). */
export function modal(title, build, { wide = false } = {}) {
  return new Promise((resolve) => {
    const close = (v) => { back.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") close(undefined); };
    const box = h("div", { class: "modal", style: wide ? { width: "min(820px, calc(100vw - 32px))" } : null },
      h("h2", {}, title), build(close));
    const back = h("div", { class: "modal-back", onmousedown: (e) => { if (e.target === back) close(undefined); } }, box);
    document.body.append(back);
    document.addEventListener("keydown", onKey);
    box.querySelector("input,textarea,select,button.primary")?.focus();
  });
}

export function confirmBox(title, text, okLabel = "OK", danger = false) {
  return modal(title, (close) => [
    h("p", { class: "muted" }, text),
    h("div", { class: "foot" },
      h("button", { class: "btn ghost", onclick: () => close(false) }, "Cancel"),
      h("button", { class: `btn ${danger ? "danger" : "primary"}`, onclick: () => close(true) }, okLabel)),
  ]).then(Boolean);
}

/** A popover menu of [label, fn, {danger, icon}] items (null = divider). */
export function menu(anchor, items) {
  document.querySelector(".menu")?.remove();
  const m = h("div", { class: "menu" }, items.map((it) => it === null ? h("hr") :
    h("button", { class: it[2]?.danger ? "danger" : "", onclick: () => { m.remove(); it[1](); } },
      it[2]?.icon ? icon(it[2].icon) : null, it[0])));
  document.body.append(m);
  const r = anchor.getBoundingClientRect();
  const left = Math.min(r.left, window.innerWidth - m.offsetWidth - 8);
  const top = r.bottom + 4 + m.offsetHeight > window.innerHeight ? r.top - m.offsetHeight - 4 : r.bottom + 4;
  Object.assign(m.style, { left: `${left}px`, top: `${top}px` });
  setTimeout(() => document.addEventListener("mousedown", function off(e) {
    if (!m.contains(e.target)) { m.remove(); document.removeEventListener("mousedown", off); }
  }), 0);
}

// ---------------------------------------------------------------- formatting
export const time = (ts) => (ts || "").slice(11, 16);
export const OUTCOME_LABEL = { critical: "Critical", success: "Success", failure: "Failure", fumble: "Fumble" };
export const skillDisplay = (v) => (v > 20 ? `20 (+${v - 20})` : String(v));
export const CHAR_FULL = { SIZ: "Size", DEX: "Dexterity", STR: "Strength", CON: "Constitution", APP: "Appeal" };
export const CHAR_ORDER = ["SIZ", "DEX", "STR", "CON", "APP"];

export function debounce(fn, ms = 250) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// ---------------------------------------------------------------- icons
// Simple 24×24 stroke icons drawn for this app.
const P = {
  d20: '<path d="M12 2.5 20.5 7.3v9.4L12 21.5 3.5 16.7V7.3Z"/><path d="M12 2.5 7 15h10Z"/><path d="M3.5 7.3 7 15l-3.5 1.7M20.5 7.3 17 15l3.5 1.7M7 15l5 6.5 5-6.5"/>',
  d6: '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1.2" fill="currentColor"/><circle cx="15" cy="15" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>',
  helm: '<path d="M5 20v-7a7 7 0 0 1 14 0v7"/><path d="M5 20h14M12 6v14M8.5 13h7"/>',
  crowd: '<circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><circle cx="17" cy="9" r="2.4"/><path d="M15.5 14.2A4.5 4.5 0 0 1 21 19"/>',
  swords: '<path d="m4 4 9.5 9.5M4 4h3.5L17 13.5M4 4v3.5L13.5 17"/><path d="m20 4-6 6M20 4h-3.5M20 4v3.5"/><path d="m12 15 3 3m-6-3 3 3M15 12l3 3m0-3-3 3M7.5 16.5 5 19m11.5-2.5L19 19"/>',
  shield: '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.6 7.5 9 4.3-1.4 7.5-4.5 7.5-9V6Z"/>',
  party: '<path d="M12 3 5 6v5.5c0 4 2.8 6.8 7 8.5 4.2-1.7 7-4.5 7-8.5V6Z"/><path d="M12 3v17M5 10h14"/>',
  dragon: '<path d="M4 18c3-1 4-4 4-7 0-3 2-6 6-6 2 0 3 1 3 1l3-1-1 3s1 1 1 3c0 4-4 5-6 4"/><path d="M8 11c2 0 4 1 4 4s-2 4-5 4H4"/><circle cx="15.5" cy="7.5" r=".8" fill="currentColor"/>',
  scroll: '<path d="M7 4h11a2 2 0 0 1 2 2v1h-4"/><path d="M7 4a2 2 0 0 0-2 2v12a2 2 0 0 1-2 2h11a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2"/><path d="M8 9h5M8 13h5"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2Z"/><path d="M4 20a2 2 0 0 0 2 1h13v-3M9 7h6"/>',
  feather: '<path d="M20 4c-6 0-11 4-12 11l-3 5"/><path d="M8 15c5 0 9-3 10-7M10 11h6"/>',
  note: '<path d="M5 4h10l4 4v12H5Z"/><path d="M15 4v4h4M8 12h8M8 16h5"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M3 3l18 18M10.6 5.6A9.6 9.6 0 0 1 12 5.5C18 5.5 21.5 12 21.5 12a17 17 0 0 1-3 3.7M6.6 6.7A16.7 16.7 0 0 0 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.5-1.2"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  strike: '<path d="M4 12h16"/><path d="M16 6.5C15 5 13.6 4.5 12 4.5c-2.5 0-4 1.3-4 3.2M8 17.5c1 1.5 2.4 2 4 2 2.5 0 4-1.4 4-3.3"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  download: '<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>',
  upload: '<path d="M12 20V9m-5 5 5-5 5 5M5 4h14"/>',
  present: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="m10 8 4 2-4 2Z" fill="currentColor"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5L20 16m0 4v-4h-4"/>',
  star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  dots: '<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  hourglass: '<path d="M6 3h12M6 21h12M7 3c0 5 10 5 10 9s-10 4-10 9M17 3c0 5-10 5-10 9"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  heart: '<path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 3c0 5.4-7.5 10-7.5 10Z"/>',
  play: '<path d="m8 5 11 7-11 7Z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  pin: '<path d="M9 4h6l-1 5 3 3H7l3-3ZM12 12v8"/>',
  image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m21 16-5-5-9 8"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10h14V9M10 13h4"/>',
};

export function icon(name, cls = "") {
  const span = document.createElement("span");
  span.className = `i ${cls}`;
  span.style.display = "inline-flex";
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${P[name] || P.dots}</svg>`;
  return span;
}

/** Load a tool's own stylesheet once (static/css/tools/<name>.css). */
export function useCss(name) {
  const href = `/static/css/tools/${name}.css`;
  if (!document.querySelector(`link[href="${href}"]`)) {
    document.head.append(h("link", { rel: "stylesheet", href }));
  }
}
