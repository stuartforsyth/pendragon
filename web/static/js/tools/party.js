// The Party: lightweight tracking records for the player knights.
// They join combats automatically and the active count scales encounters.

import { h, clear, api, post, patch, del, icon, modal, confirmBox, toast, useCss, skillDisplay } from "../lib.js";

const FIELDS = [
  ["name", "Name", "text", "Sir Bors de Ganis"],
  ["player", "Player", "text", "who plays them"],
  ["max_hp", "Hit Points (max)", "number"],
  ["cur_hp", "Hit Points (now)", "number"],
  ["major_wound", "Major Wound (= CON)", "number"],
  ["unconscious", "Unconscious", "number"],
  ["knockdown", "Knockdown", "number"],
  ["move", "Move", "number"],
  ["armour", "Armour points", "number"],
  ["shield", "Shield points", "number"],
];

export default {
  async mount(el, ctx) {
    useCss("party");
    let party = [];
    const grid = h("div", { class: "party-grid" });
    const summary = h("div", { class: "party-summary" });

    clear(el,
      h("div", { class: "tool-head" },
        h("div", {}, h("h1", {}, "Party"),
          h("p", { class: "lede" }, "The player knights. Active knights join every combat automatically, and their number scales encounters.")),
        h("div", { class: "actions" }, h("button", { class: "btn primary", onclick: () => edit() }, icon("plus"), "Add knight"))),
      summary, grid);

    async function load() {
      party = (await api("/api/party")).party;
      render();
    }

    const hpOf = (m) => (m.cur_hp ?? m.max_hp ?? 0);

    function render() {
      const active = party.filter((m) => m.active !== false);
      clear(summary, party.length ? [
        h("span", { class: "tag or" }, icon("party"), `${active.length} active`),
        party.length > active.length ? h("span", { class: "tag" }, `${party.length - active.length} resting`) : null,
        h("span", { class: "faint small" }, `Encounters will scale for ${active.length || "?"} player${active.length === 1 ? "" : "s"}.`),
      ] : null);
      clear(grid, party.length ? party.map(card) : h("div", { class: "empty", style: { gridColumn: "1 / -1" } }, icon("party"),
        "No knights yet. Add each player's knight so they appear on the battle board and scale encounters."));
    }

    function card(m) {
      const max = m.max_hp || 0, cur = hpOf(m);
      const pct = max ? Math.max(0, Math.min(1, cur / max)) : 0;
      const down = max && (cur <= 0 || (m.unconscious && cur < m.unconscious));
      const hue = Math.round(pct * 42);          // 42° gold → 0° red
      const values = Object.entries(m.values || {});
      return h("div", { class: `knight ${m.active === false ? "resting" : ""} ${down ? "down" : ""}` },
        h("div", { class: "knight-head" },
          h("div", { class: "knight-shield" }, icon("shield"), h("span", {}, (m.name || "?").replace(/^Sir\s+/i, "")[0])),
          h("div", { style: { minWidth: 0, flex: 1 } },
            h("div", { class: "knight-name" }, m.name),
            h("div", { class: "faint small" }, m.player ? `played by ${m.player}` : "no player set")),
          h("label", { class: "check small", title: "Inactive knights don't join combats or count for scaling" },
            h("input", { type: "checkbox", checked: m.active !== false,
              onchange: async (e) => { await patch(`/api/party/${m.id}`, { active: e.target.checked }); load(); } }), "Active")),
        h("div", { class: "hp" },
          h("div", { class: "hp-row" }, h("span", { class: "label" }, "Hit Points"),
            h("span", { class: "hp-num" }, h("b", {}, cur), ` / ${max || "?"}`),
            down ? h("span", { class: "tag gules" }, cur <= 0 ? "Near death" : "Unconscious") : null),
          h("div", { class: "hp-bar" }, h("div", { class: "hp-fill", style: { width: `${pct * 100}%`, background: `linear-gradient(90deg, hsl(${hue} 65% 38%), hsl(${hue} 72% 52%))` } }))),
        h("div", { class: "knight-stats" },
          stat("Armour", `${m.armour ?? 0}${m.shield ? `+${m.shield}` : ""}`, m.shield ? `${m.armour ?? 0} armour + ${m.shield} shield` : "Armour points"),
          stat("Major", m.major_wound ?? "—", "Major Wound (a single blow ≥ this)"),
          stat("Uncon.", m.unconscious ?? "—", "Unconscious threshold"),
          stat("Knock.", m.knockdown ?? "—", "Knockdown"),
          stat("Move", m.move ?? "—", "Move")),
        m.armour_desc ? h("div", { class: "faint small knight-arm" }, m.armour_desc) : null,
        values.length ? h("div", { class: "flow knight-values" }, values.map(([nm, v]) =>
          h("span", { class: "pair" }, h("span", { class: "nm" }, nm), " ",
            h("span", { class: `rollable ${v >= 16 ? "famous" : ""}`, title: `Roll ${nm}`,
              onclick: () => ctx.rollCheck({ label: nm, value: v, actor: m.name }) }, skillDisplay(v))))) : null,
        m.notes ? h("div", { class: "knight-notes" }, m.notes) : null,
        h("div", { class: "knight-actions" },
          h("button", { class: "btn sm", onclick: () => hpChange(m) }, icon("heart"), "HP change"),
          h("button", { class: "btn sm", onclick: () => edit(m) }, "Edit"),
          h("button", { class: "btn sm ghost icon", title: "Remove knight", onclick: () => remove(m) }, icon("x"))));
    }

    const stat = (k, v, title) => h("div", { class: "kstat", title }, h("div", { class: "label" }, k), h("div", { class: "kv" }, v));

    async function hpChange(m) {
      const res = await modal(`Hit Points — ${m.name}`, (close) => {
        const delta = h("input", { class: "input", type: "number", placeholder: "-8 for a wound, +3 for healing" });
        const reason = h("input", { class: "input", placeholder: "Reason (optional) — e.g. a week's healing, a fall" });
        const go = () => delta.value && Number(delta.value) ? close({ delta: Number(delta.value), reason: reason.value }) : delta.focus();
        [delta, reason].forEach((i) => i.addEventListener("keydown", (e) => e.key === "Enter" && go()));
        return [
          h("p", { class: "muted" }, `Now ${hpOf(m)} / ${m.max_hp ?? "?"}. Out-of-combat changes are logged to the session.`),
          h("div", { class: "row" },
            [-1, -5, +1, +3].map((n) => h("button", { class: "chip", onclick: () => { delta.value = n; } }, n > 0 ? `+${n}` : n)),
            m.max_hp ? h("button", { class: "chip", onclick: () => { delta.value = m.max_hp - hpOf(m); reason.value ||= "fully healed"; } }, "Full") : null),
          h("div", { class: "stack", style: { marginTop: "10px" } },
            h("label", { class: "field" }, h("span", {}, "Change"), delta),
            h("label", { class: "field" }, h("span", {}, "Reason"), reason)),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: go }, "Apply")),
        ];
      });
      if (!res) return;
      await post(`/api/party/${m.id}/hp`, res);
      load();
    }

    async function edit(m = null) {
      const data = await modal(m ? `Edit ${m.name}` : "Add a knight", (close) => {
        const inputs = {};
        const grid = h("div", { class: "party-form" }, FIELDS.map(([k, label, type, ph]) => {
          inputs[k] = h("input", { class: "input", type, placeholder: ph || "", value: m?.[k] ?? "" });
          return h("label", { class: `field ${k === "name" || k === "player" ? "wide" : ""}` }, h("span", {}, label), inputs[k]);
        }));
        const armDesc = h("input", { class: "input", placeholder: "e.g. Haubergeon, open helm + kite shield", value: m?.armour_desc || "" });
        const notes = h("textarea", { class: "input", rows: 3, placeholder: "Anything you want at hand mid-fight" }, m?.notes || "");
        const vals = h("textarea", { class: "input", rows: 4, placeholder: "One per line, e.g.\nSword 16\nValorous 15\nAwareness 10" },
          Object.entries(m?.values || {}).map(([k, v]) => `${k} ${v}`).join("\n"));
        const save = () => {
          const out = { armour_desc: armDesc.value, notes: notes.value, values: {} };
          for (const [k, , type] of FIELDS) out[k] = type === "number" ? (inputs[k].value === "" ? null : Number(inputs[k].value)) : inputs[k].value;
          if (!out.name.trim()) return inputs.name.focus();
          for (const line of vals.value.split("\n")) {
            const mm = line.trim().match(/^(.*?)[\s:]+(-?\d+)$/);
            if (mm) out.values[mm[1].trim()] = Number(mm[2]);
          }
          close(out);
        };
        return [
          grid,
          h("div", { class: "stack", style: { marginTop: "10px" } },
            h("label", { class: "field" }, h("span", {}, "Armour worn"), armDesc),
            h("label", { class: "field" }, h("span", {}, "Key values (click-to-roll)"), vals),
            h("label", { class: "field" }, h("span", {}, "Notes"), notes)),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: save }, m ? "Save" : "Add knight")),
        ];
      }, { wide: true });
      if (!data) return;
      if (m) await patch(`/api/party/${m.id}`, data);
      else await post("/api/party", data);
      toast(m ? "Saved" : `${data.name} joins the party`, "ok");
      load();
    }

    async function remove(m) {
      if (!await confirmBox("Remove knight?", `${m.name} will be removed from the party.`, "Remove", true)) return;
      await del(`/api/party/${m.id}`);
      load();
    }

    ctx.onEvent((evs) => { if (evs.some((e) => e.type === "combat.ended" || e.type === "party.hp")) load(); });
    await load();
    return { show: () => load() };
  },
};
