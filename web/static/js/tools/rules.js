// Rules lookup over the rules corpus (data/rules_index.jsonl): search or
// browse by chapter, read the rule, show it on the Table.

import { h, clear, api, post, icon, toast, useCss, debounce, copyText, enc } from "../lib.js";

const BOOK = { core: "Core Rulebook", gm: "GM Handbook" };

// Snippets come from raw Markdown — flatten emphasis, headings and table pipes.
const plain = (t) => (t || "").replace(/\|?\s*:?-{3,}:?\s*/g, " ").replace(/[*_#>`]+/g, "")
  .replace(/\s*\|\s*/g, " · ").replace(/(\s·)+/g, " ·").replace(/\s+/g, " ").trim();
const chapterNum = (c) => { const n = parseFloat(c); return Number.isNaN(n) ? 999 : n; };

export default {
  async mount(el, ctx) {
    useCss("rules");
    let results = [];
    let sel = -1;
    let current = null;
    let pins = [];

    const q = h("input", { class: "input rules-q", placeholder: "Search the rules — e.g. major wound, knockdown, ransom…  (press / )",
      oninput: debounce(() => search(), 180),
      onkeydown: (e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
        else if (e.key === "Enter") { e.preventDefault(); if (e.shiftKey || e.ctrlKey) showOnTable(); else if (results[sel]) open(results[sel].id); }
        else if (e.key === "Escape") { q.value = ""; search(); }
      } });
    const list = h("div", { class: "rules-list list-scroll" });
    const reader = h("div", { class: "rules-reader" });
    const count = h("div", { class: "faint small", style: { margin: "8px 2px 6px" } });
    const pinBox = h("div", { class: "rule-pins" });

    clear(el,
      h("div", { class: "tool-head" },
        h("div", {}, h("h1", {}, "Rules"),
          h("p", { class: "lede" }, "The rules corpus — Core Rulebook and GM Handbook — at your fingertips. ",
            h("span", { class: "faint" }, "↑↓ to move, Enter to read, Ctrl+Enter to show on the Table.")))),
      h("div", { class: "split rules-split" },
        h("div", { class: "panel rules-side" }, pinBox, h("div", { class: "rules-search" }, icon("search"), q), count, list),
        reader));

    document.addEventListener("keydown", (e) => {
      if (e.key !== "/" || el.hidden || el.closest("[hidden]")) return;
      const t = e.target;
      if (t.matches("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      q.focus(); q.select();
    });

    async function search() {
      const term = q.value.trim();
      results = (await api(`/api/rules?q=${enc(term)}&limit=${term ? 40 : 500}`)).results;
      sel = results.length ? 0 : -1;
      count.textContent = term ? `${results.length} match${results.length === 1 ? "" : "es"}` : `${results.length} rules · browse by chapter`;
      renderList(!term);
    }

    function itemEl(r, i) {
      return h("div", { class: `list-item rule-item ${i === sel ? "on" : ""} ${current?.id === r.id ? "reading" : ""}`, "data-i": i,
        onclick: () => { sel = i; open(r.id); } },
        h("div", { style: { minWidth: 0 } },
          h("div", { class: "rule-title" }, r.title),
          h("div", { class: "faint small" }, `${BOOK[r.book] || r.book} · ${r.chapter} · p.${(r.pages || []).join(", ")}`),
          r.snippet ? h("div", { class: "rule-snip" }, "…" + plain(r.snippet) + "…") : null));
    }

    function renderList(browse) {
      if (!results.length) {
        clear(list, h("div", { class: "faint small", style: { padding: "10px" } }, "No rule matches. Try fewer words."));
        return;
      }
      if (!browse) { clear(list, results.map(itemEl)); return; }
      const order = results.map((r, i) => [r, i]).sort(([a], [b]) =>
        a.book.localeCompare(b.book) || chapterNum(a.chapter) - chapterNum(b.chapter) || a.title.localeCompare(b.title));
      const groups = new Map();
      order.forEach(([r, i]) => {
        const key = `${BOOK[r.book] || r.book} — ${r.chapter}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(itemEl(r, i));
      });
      clear(list, [...groups].map(([k, items]) => h("details", { class: "rule-group", open: false },
        h("summary", {}, k, h("span", { class: "faint small" }, ` ${items.length}`)), items)));
    }

    function move(d) {
      if (!results.length) return;
      sel = Math.max(0, Math.min(results.length - 1, sel + d));
      list.querySelectorAll(".rule-item").forEach((x) => {
        const on = Number(x.dataset.i) === sel;
        x.classList.toggle("on", on);
        if (on) { x.closest("details")?.setAttribute("open", ""); x.scrollIntoView({ block: "nearest" }); }
      });
    }

    async function open(id) {
      current = (await api(`/api/rules/${enc(id)}`)).rule;
      list.querySelectorAll(".rule-item").forEach((x) => x.classList.toggle("reading", results[Number(x.dataset.i)]?.id === id));
      pinBox.querySelectorAll(".pin-item").forEach((x, i) => x.classList.toggle("reading", pins[i]?.id === id));
      renderReader();
    }

    // Pinned rules: the ones you expect to need this game, one click away.
    async function loadPins() {
      pins = (await api("/api/rules/pins")).pins;
      clear(pinBox, pins.length ? [
        h("div", { class: "label" }, icon("pin"), " Pinned"),
        pins.map((p) => h("div", { class: `list-item pin-item ${current?.id === p.id ? "reading" : ""}`, onclick: () => open(p.id) },
          h("span", { class: "rule-title", style: { minWidth: 0, flex: 1 } }, p.title),
          h("button", { class: "btn ghost sm icon", title: "Show on Table",
            onclick: (e) => { e.stopPropagation(); showOnTable(p.id); } }, icon("present")))),
      ] : null);
    }

    async function togglePin() {
      const pinned = !pins.some((p) => p.id === current.id);
      await post(`/api/rules/${enc(current.id)}/pin`, { pinned });
      await loadPins();
      renderReader();
    }

    async function showOnTable(pinnedId) {
      const id = (typeof pinnedId === "string" && pinnedId) || current?.id || results[sel]?.id;
      if (!id) return;
      await post(`/api/rules/${enc(id)}/show`);
      toast("Shown on the Table", "ok");
    }

    function renderReader() {
      if (!current) {
        clear(reader, h("div", { class: "empty" }, icon("book"), "Pick a rule to read it here."));
        return;
      }
      const r = current;
      const cite = `${r.id} — ${BOOK[r.book] || r.book} p.${(r.pages || []).join(", ")}`;
      const body = h("div", { class: "rule-body" });
      body.innerHTML = r.html;
      clear(reader, h("div", { class: "panel rule-card" },
        h("div", { class: "rule-head" },
          h("div", { style: { minWidth: 0 } },
            h("div", { class: "rule-crumb" }, `${BOOK[r.book] || r.book} · ${r.chapter}`),
            h("h2", { class: "rule-h" }, r.title),
            h("div", { class: "row tight" },
              h("span", { class: "tag or" }, `p.${(r.pages || []).join(", ")}`),
              (r.tags || []).slice(0, 8).map((t) => h("button", { class: "tag rule-tag", title: `Search “${t}”`,
                onclick: () => { q.value = t.replace(/-/g, " "); search(); } }, t)))),
          h("div", { class: "toolbar" },
            h("button", { class: "btn primary", onclick: () => showOnTable() }, icon("present"), "Show on Table"),
            h("button", { class: `btn ${pins.some((p) => p.id === r.id) ? "on" : ""}`, title: "Pin for quick access",
              onclick: togglePin }, icon("pin"), pins.some((p) => p.id === r.id) ? "Pinned" : "Pin"),
            h("button", { class: "btn icon", title: "Copy citation", onclick: () => copyText(cite, "Citation copied") }, icon("copy")))),
        body));
      el.closest(".main")?.scrollTo({ top: 0, behavior: "smooth" });
    }

    renderReader();
    await loadPins();
    await search();
    return { show: () => q.focus() };
  },
};
