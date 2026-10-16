// The Party: the player knights by name. Players keep their own sheets on
// paper — no Hit Points here. Active knights join every combat (as the
// opponents enemies can be set to fight) and their number scales encounters.

import { h, clear, api, post, patch, del, icon, modal, confirmBox, useCss } from "../lib.js";

export default {
  async mount(el) {
    useCss("party");
    let party = [];
    const list = h("div", { class: "party-list" });
    const summary = h("div", { class: "faint small", style: { margin: "-6px 0 14px" } });

    clear(el,
      h("div", { class: "tool-head" },
        h("div", {}, h("h1", {}, "Party"),
          h("p", { class: "lede" }, "The player knights. Active knights join every combat and set how encounters scale.")),
        h("div", { class: "actions" }, h("button", { class: "btn primary", onclick: () => edit() }, icon("plus"), "Add knight"))),
      summary, list);

    async function load() {
      party = (await api("/api/party")).party;
      const n = party.filter((m) => m.active !== false).length;
      summary.textContent = `${n} active knight${n === 1 ? "" : "s"} — encounters scale for ${n || 4} players.`;
      clear(list, party.length ? party.map(card) : h("div", { class: "empty" }, icon("party"), "No knights yet — add your players' knights."));
    }

    function card(m) {
      const active = m.active !== false;
      return h("div", { class: `panel party-row ${active ? "" : "inactive"}` },
        h("div", { class: "party-shield" }, icon("shield")),
        h("div", { class: "party-main" },
          h("div", { class: "party-name" }, m.name),
          h("div", { class: "faint small" }, m.player ? `played by ${m.player}` : ""),
          m.notes ? h("div", { class: "muted small party-notes" }, m.notes) : null),
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: active,
          onchange: async (e) => { await patch(`/api/party/${m.id}`, { active: e.target.checked }); load(); } }), "Active"),
        h("button", { class: "btn sm", onclick: () => edit(m) }, "Edit"),
        h("button", { class: "btn sm ghost icon", title: "Remove", onclick: async () => {
          if (await confirmBox("Remove knight?", `Remove ${m.name} from the Party?`, "Remove", true)) { await del(`/api/party/${m.id}`); load(); }
        } }, icon("x")));
    }

    async function edit(m = null) {
      const name = h("input", { class: "input", value: m?.name || "", placeholder: "Sir Bors de Ganis" });
      const player = h("input", { class: "input", value: m?.player || "", placeholder: "who plays them" });
      const notes = h("textarea", { class: "input", rows: 3, placeholder: "Anything worth remembering" }, m?.notes || "");
      const saved = await modal(m ? `Edit ${m.name}` : "Add a knight", (close) => [
        h("div", { class: "stack" },
          h("label", { class: "field" }, h("span", {}, "Name"), name),
          h("label", { class: "field" }, h("span", {}, "Player"), player),
          h("label", { class: "field" }, h("span", {}, "Notes"), notes)),
        h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
          h("button", { class: "btn primary", onclick: () => close(true) }, m ? "Save" : "Add")),
      ]);
      if (!saved) return;
      const body = { name: name.value, player: player.value, notes: notes.value };
      if (m) await patch(`/api/party/${m.id}`, body); else await post("/api/party", body);
      load();
    }

    await load();
    return { show: load };
  },
};
