// Feedback: a tab on the right edge of the GM console slides out a panel to
// report a bug, a change or an idea. Where it came from is captured
// automatically (the tool, its heading, an open dialog, the token open on the
// Field, selected text; the server adds the session, its newest event, the
// fight and the battle), so a report can be reproduced exactly. The /feedback
// skill works through the queue; replies show under "Your recent reports".

import { h, clear, api, post } from "./lib.js";

const KINDS = [["bug", "Bug"], ["change", "Change"], ["idea", "Idea"], ["question", "Question"]];
const STATUS = { new: "received", planned: "planned", done: "done", wontfix: "closed" };

const tab = h("button", { id: "fb-tab", type: "button", "aria-haspopup": "dialog", "aria-expanded": "false",
  title: "Report a bug, ask for a change or suggest an idea" }, "Feedback");
const msg = h("textarea", { id: "fb-message", rows: 7, maxlength: 4000, placeholder: "What were you doing, and what happened instead? Or what should change?" });
const captured = h("p", { class: "fb-captured" });
const status = h("span", { class: "fb-status", role: "status", "aria-live": "polite" });
const list = h("ul", { class: "fb-list" });
let kind = "bug", selected = "";
const kinds = h("div", { class: "fb-kinds", role: "radiogroup", "aria-label": "What is this?" });
const drawKinds = () => clear(kinds, KINDS.map(([k, label]) => h("button", { type: "button", class: `chip ${kind === k ? "on" : ""}`,
  role: "radio", "aria-checked": String(kind === k), onclick: () => { kind = k; drawKinds(); } }, label)));
drawKinds();
const send = h("button", { type: "submit", class: "btn primary" }, "Send");
const panel = h("aside", { id: "fb-panel", role: "dialog", "aria-label": "Send feedback", "aria-hidden": "true" },
  h("div", { class: "fb-head" }, h("strong", {}, "Feedback"), h("button", { type: "button", class: "fb-close", "aria-label": "Close", onclick: () => close() }, "×")),
  h("form", { onsubmit: (e) => { e.preventDefault(); submit(); } },
    kinds, msg, captured, h("div", { class: "fb-actions" }, send, status)),
  h("div", { class: "fb-mine" }, h("div", { class: "label" }, "Your recent reports"), list));
document.body.append(tab, panel);

function pageInfo() {
  const route = location.hash || "#/";
  const tool = document.querySelector(".rail a.active")?.textContent.trim() || "";
  const heading = document.querySelector("#main h1")?.textContent.trim().slice(0, 200) || "";
  const open = document.querySelector(".modal h2")?.textContent.trim() || document.querySelector(".cbt-drawer .cbt-foe-name, .cbt-drawer .cbt-knight")?.textContent.trim() || "";
  const picked = document.querySelector(".ftok.picked .ftok-name")?.textContent.trim() || "";
  return { route, tool, heading, open, picked, selected, viewport: `${innerWidth}x${innerHeight}` };
}

function showCaptured() {
  const p = pageInfo();
  captured.textContent = `Sent with this report: ${p.tool || p.route}${p.heading ? " · " + p.heading : ""}` +
    `${p.open ? " · " + p.open : ""}${p.selected ? " · your selected text" : ""}, plus the session and its latest log entry.`;
}

async function loadMine() {
  try {
    const r = await api("/api/feedback");
    clear(list, r.items.length ? r.items.map((i) => h("li", {},
      h("span", { class: `fb-chip fb-${i.status}` }, STATUS[i.status] || i.status), " ",
      h("span", { class: "fb-kind" }, `#${i.id} ${i.kind}`), " ", i.message.slice(0, 140),
      i.note ? h("div", { class: "fb-note" }, i.note) : null)) : h("li", { class: "faint" }, "Nothing yet."));
  } catch { clear(list, h("li", { class: "faint" }, "Could not load.")); }
}

function open() {
  panel.classList.add("open"); panel.setAttribute("aria-hidden", "false"); tab.setAttribute("aria-expanded", "true");
  showCaptured(); loadMine();
  setTimeout(() => msg.focus(), 50);
}
function close() {
  panel.classList.remove("open"); panel.setAttribute("aria-hidden", "true"); tab.setAttribute("aria-expanded", "false");
  selected = "";
}

// Grab any selected text before the click on the tab clears it.
tab.addEventListener("mousedown", () => { selected = (getSelection?.().toString().trim() || "").slice(0, 300); });
tab.addEventListener("click", () => (panel.classList.contains("open") ? close() : open()));
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && panel.classList.contains("open")) close(); });

async function submit() {
  const text = msg.value.trim();
  if (!text) { status.textContent = "Write something first."; return; }
  send.disabled = true; status.textContent = "Sending…";
  try {
    const r = await post("/api/feedback", { kind, message: text, page: pageInfo() });
    msg.value = ""; status.textContent = `Thanks — queued as #${r.item.id}.`;
    loadMine();
  } catch (e) {
    status.textContent = e?.message || "Could not send. Try again.";
  } finally { send.disabled = false; }
}
