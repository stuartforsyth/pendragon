// Shared GM-console components for the Battle and Battles tools (built once,
// reused): the deck picker, outcome chips, amount entry, Morale strip, knight
// chip and day card. GM-only — nothing here is ever on the Table.

import { h, clear } from "./lib.js";

/**
 * A checklist of battle encounters with Foes / Opportunities tabs and the
 * GM-only Minimum, Loss and KV columns. `cards` come from /api/battle-decks;
 * `selected` is an array of keys; `onChange(keys)` fires on every tick.
 * Keys no longer in the library show as "missing" rows that can be removed.
 */
export function deckPicker({ cards, selected = [], onChange, tab = "foe" }) {
  let chosen = new Set(selected);
  let q = "";
  const root = h("div", { class: "deck-picker" });
  const byKey = new Map(cards.map((c) => [c.key, c]));
  const draw = () => {
    const count = (role) => [...chosen].filter((k) => byKey.get(k)?.role === role).length;
    const rows = cards.filter((c) => c.role === tab && (!q || c.key.toLowerCase().includes(q)));
    const missing = [...chosen].filter((k) => !byKey.has(k));
    clear(root,
      h("div", { class: "dp-head" },
        h("div", { class: "dp-tabs", role: "tablist" },
          [["foe", "Foes"], ["opportunity", "Opportunities ★"]].map(([r, label]) =>
            h("button", { class: `chip ${tab === r ? "on" : ""}`, role: "tab", "aria-selected": String(tab === r),
              onclick: () => { tab = r; draw(); } }, `${label} (${count(r)})`))),
        h("input", { class: "input dp-search", type: "search", placeholder: "Search…", value: q,
          oninput: (e) => { q = e.target.value.toLowerCase(); draw(); } })),
      h("div", { class: "dp-list" },
        rows.length ? rows.map((c) => h("label", { class: `dp-row ${chosen.has(c.key) ? "on" : ""}` },
          h("input", { type: "checkbox", checked: chosen.has(c.key), onchange: (e) => {
            e.target.checked ? chosen.add(c.key) : chosen.delete(c.key);
            onChange?.([...chosen]); draw();
          } }),
          h("span", { class: "dp-name" }, c.role === "opportunity" ? "★ " : "", c.key),
          h("span", { class: "dp-meta" }, `Min ${c.morale_minimum ?? "—"}`),
          h("span", { class: "dp-meta" }, `Loss ${c.morale_loss || "—"}`),
          h("span", { class: "dp-meta" }, c.has_roster ? `KV ${c.kv_per_knight || "0"}` : "no foes"),
          c.missile ? h("span", { class: "tag" }, "missile") : null))
          : h("div", { class: "faint small" }, tab === "foe" ? "No battle Foes yet — mark encounters as Foes in the Encounter Creator." : "No Opportunities yet."),
        missing.map((k) => h("div", { class: "dp-row missing" }, h("span", { class: "dp-name" }, k), h("span", { class: "tag gules" }, "missing"),
          h("button", { class: "btn ghost sm", onclick: () => { chosen.delete(k); onChange?.([...chosen]); draw(); } }, "Remove")))));
  };
  draw();
  return root;
}
