// The Cast: NPCs kept across sessions, each with autosaving private GM notes.
// Replaces the desktop app's per-session roster (old roster files import here).

import { h, clear, api, post, patch, del, icon, confirmBox, toast, useCss, debounce,
  download, CHAR_FULL, CHAR_ORDER } from "../lib.js";

export default {
  async mount(el, ctx) {
    useCss("cast");
    let cast = [];
    let selected = null;
    const filter = { q: "", culture: "All", cls: "All" };

    const search = h("input", { class: "input", placeholder: "Search names, descriptions, notes…",
      oninput: (e) => { filter.q = e.target.value.trim().toLowerCase(); renderList(); } });
    const facets = h("div", { class: "cast-facets" });
    const listEl = h("div", { class: "cast-list list-scroll" });
    const detail = h("div", { class: "cast-detail" });
    const countEl = h("span", { class: "faint small" });
    const fileInput = h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: importFile });

    clear(el,
      h("div", { class: "tool-head" },
        h("div", {}, h("h1", {}, "Cast"),
          h("p", { class: "lede" }, "NPCs you've kept, across every session — with your private notes.")),
        h("div", { class: "actions" },
          h("button", { class: "btn", title: "Import a roster saved by the desktop app", onclick: () => fileInput.click() }, icon("upload"), "Import roster"),
          h("button", { class: "btn", onclick: () => download("/api/cast/export.md") }, icon("download"), "Export Markdown"),
          h("button", { class: "btn primary", onclick: () => ctx.navigate("npc") }, icon("helm"), "Generate NPC"),
          fileInput)),
      h("div", { class: "split cast-split" },
        h("div", { class: "panel cast-side" },
          search, facets, h("div", { class: "row", style: { margin: "8px 0 6px" } }, countEl), listEl),
        detail));

    async function load() {
      cast = (await api("/api/cast")).cast;
      if (selected && !cast.find((c) => c.id === selected)) selected = null;
      renderFacets();
      renderList();
      renderDetail();
    }

    const cultureOf = (c) => c.npc.culture || "—";
    const classOf = (c) => c.npc.social_class || "—";

    function renderFacets() {
      const uniq = (fn) => ["All", ...[...new Set(cast.map(fn))].sort()];
      const row = (label, key, values) => values.length > 2 ? h("div", { class: "facet" },
        h("div", { class: "label" }, label),
        h("div", { class: "chips" }, values.map((v) => h("button", { class: `chip ${filter[key] === v ? "on" : ""}`,
          onclick: () => { filter[key] = v; renderFacets(); renderList(); } }, v)))) : null;
      clear(facets, row("Culture", "culture", uniq(cultureOf)), row("Class", "cls", uniq(classOf)));
    }

    function matches(c) {
      if (filter.culture !== "All" && cultureOf(c) !== filter.culture) return false;
      if (filter.cls !== "All" && classOf(c) !== filter.cls) return false;
      if (!filter.q) return true;
      const hay = `${c.npc.full} ${c.npc.subtitle} ${c.npc.description} ${c.notes}`.toLowerCase();
      return hay.includes(filter.q);
    }

    function renderList() {
      const shown = cast.filter(matches).sort((a, b) => a.npc.full.localeCompare(b.npc.full));
      countEl.textContent = cast.length ? `${shown.length} of ${cast.length} kept` : "";
      if (!cast.length) {
        clear(listEl, h("div", { class: "empty" }, icon("crowd"),
          "No one kept yet. Generate an NPC and press ", h("b", {}, "Keep"), ", or import an old roster."));
        return;
      }
      clear(listEl, shown.length ? shown.map((c) => {
        const first = (c.npc.description || "").split(/(?<=\.)\s/)[0];
        return h("div", { class: `list-item cast-item ${c.id === selected ? "on" : ""}`, onclick: () => { selected = c.id; renderList(); renderDetail(); } },
          h("div", { class: "cast-seal" }, (c.npc.full || "?")[0]),
          h("div", { style: { minWidth: 0, flex: 1 } },
            h("div", { class: "cast-name" }, c.npc.full,
              c.notes?.trim() ? h("span", { class: "cast-noted", title: "Has GM notes" }, icon("note")) : null),
            h("div", { class: "faint small cast-sub" }, c.npc.subtitle),
            h("div", { class: "cast-first" }, first)));
      }) : h("div", { class: "faint small", style: { padding: "10px" } }, "Nothing matches."));
    }

    function renderDetail() {
      const c = cast.find((x) => x.id === selected);
      if (!c) {
        clear(detail, h("div", { class: "empty" }, icon("crowd"),
          cast.length ? "Choose someone from the Cast." : "Your recurring characters will live here."));
        return;
      }
      const n = c.npc, a = n.appearance || {}, d = n.derived || {};
      const fact = (k, v) => v ? [h("div", { class: "k" }, k), h("div", { class: "v" }, v)] : [];
      const traits = (n.traits || []).flatMap(([l, lv, r, rv]) => [[l, lv], [r, rv]])
        .filter(([, v]) => v >= 16).map(([nm, v]) => `${nm} ${v}`);
      const passions = (n.passions || []).map(([nm, v]) => `${nm} ${v}`).join(", ");
      const stats = n.stats ? CHAR_ORDER.map((k) => `${CHAR_FULL[k]} ${n.stats[k]}`).join(" · ") : "";
      const skills = n.skills ? Object.entries(n.skills).sort((x, y) => y[1] - x[1]).slice(0, 8)
        .map(([k, v]) => `${k} ${v}`).join(", ") : "";

      const status = h("span", { class: "faint small cast-saved" }, "Saved");
      const notes = h("textarea", { class: "input cast-notes", rows: 8,
        placeholder: "Private notes — secrets, relationships, what happened when the party met them… (never shown on the Table)" }, c.notes || "");
      const save = debounce(async () => {
        await patch(`/api/cast/${c.id}`, { notes: notes.value });
        c.notes = notes.value;
        status.textContent = "Saved";
        status.classList.remove("dirty");
        renderList();
      }, 600);
      notes.addEventListener("input", () => { status.textContent = "Saving…"; status.classList.add("dirty"); save(); });

      clear(detail, h("div", { class: "panel cast-card" },
        h("div", { class: "npc-top cast-top" },
          h("div", { style: { minWidth: 0 } },
            h("div", { class: "namebig" }, n.full),
            h("div", { class: "subtitle" }, n.subtitle,
              n.glory != null ? h("span", { class: "tag or", style: { marginLeft: "10px" } }, `Glory ${n.glory}`) : null,
              h("span", { class: "faint small", style: { marginLeft: "10px" } }, `kept ${(c.kept || "").slice(0, 10)}`))),
          h("div", { class: "toolbar" },
            h("button", { class: "btn", title: "Spotlight this character on the Table",
              onclick: async () => { await post(`/api/cast/${c.id}/present`); toast(`${n.full} presented on the Table`, "ok"); } }, icon("present"), "Present"),
            h("button", { class: "btn", title: "Open in the NPC Generator (click-to-roll, rerolls, exports)",
              onclick: () => ctx.navigate("npc", { npc: structuredClone(n) }) }, icon("helm"), "Open"),
            h("button", { class: "btn danger icon", title: "Remove from the Cast", onclick: () => remove(c) }, icon("x")))),
        h("div", { class: "readaloud" }, n.description),
        h("div", { class: "section-label" }, "At a glance"),
        h("div", { class: "sheet" },
          fact("Look", n.appearance ? `${a.descriptor}${n.height ? `, ~${n.height} tall` : ""}; ${a.eyes} eyes` : ""),
          fact("Features", (a.features || []).join("; ")),
          fact("Manner", n.manner),
          fact(n.directed?.kind || "", n.directed?.text),
          fact("Famous traits", traits.join(", ")),
          fact("Passions", passions),
          fact("Characteristics", stats),
          fact("Hit Points", d["Hit Points"] ? `${d["Hit Points"]} · Damage ${d.Damage} · Major Wound ${d["Major Wound"]}` : ""),
          fact("Top skills", skills),
          fact("Squire", n.squire ? `${n.squire.full}, age ${n.squire.age ?? "?"}` : "")),
        h("div", { class: "section-label" }, icon("lock"), "GM notes", status),
        notes));
    }

    async function remove(c) {
      if (!await confirmBox("Remove from the Cast?", `${c.npc.full} and your notes on them will be removed. Session logs that mention them are untouched.`, "Remove", true)) return;
      await del(`/api/cast/${c.id}`);
      selected = null;
      toast(`${c.npc.full} removed`);
      load();
    }

    async function importFile(e) {
      const file = e.target.files[0];
      e.target.value = "";
      if (!file) return;
      let data;
      try { data = JSON.parse(await file.text()); } catch { return toast("That file isn't JSON", "err"); }
      if (!Array.isArray(data)) return toast("That isn't a saved roster (expected a list of NPCs)", "err");
      if (!await confirmBox("Import roster", `Add ${data.length} NPC${data.length === 1 ? "" : "s"} from ${file.name} to the Cast? Their GM notes come with them.`, "Import")) return;
      const r = await post("/api/cast/import", data);
      toast(`Imported ${r.added} into the Cast`, "ok");
      load();
    }

    await load();
    return { show: () => load() };
  },
};
