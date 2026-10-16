// NPC Generator: options → a rolled-up NPC with click-to-roll values,
// reroll-a-field, present to the Table, keep in the Cast, exports.

import { h, clear, api, post, icon, menu, copyText, toast, useCss, skillDisplay,
  CHAR_FULL, CHAR_ORDER } from "../lib.js";

const FAMOUS = 16, EXALTED = 20;

export default {
  async mount(el, ctx, handoff) {
    useCss("npc");
    const opts = await api("/api/npc/options");
    const choice = { gender: "Male", social_class: "Random", culture: opts.cultures.includes("Cymri") ? "Cymri" : opts.cultures[0],
      religion: "Random", include_negative: true };
    let npc = null, fmt = null;

    // ---------- options
    const group = (title, key, values) => {
      const chips = h("div", { class: "chips" });
      const draw = () => clear(chips, values.map((v) => h("button", { class: `chip ${choice[key] === v ? "on" : ""}`,
        onclick: () => { choice[key] = v; draw(); } }, v)));
      draw();
      return h("div", { class: "opt-group" }, h("div", { class: "label" }, title), chips);
    };
    const neg = h("input", { type: "checkbox", checked: true, onchange: (e) => { choice.include_negative = e.target.checked; } });
    const optionsPanel = h("div", { class: "panel npc-options" },
      h("div", { class: "opt-grid" },
        group("Gender", "gender", ["Male", "Female", "Random"]),
        group("Class", "social_class", ["Random", ...opts.classes]),
        group("Culture", "culture", [...opts.cultures, "Random"]),
        group("Religion", "religion", ["Random", ...opts.religions])),
      h("div", { class: "row", style: { marginTop: "14px" } },
        h("button", { class: "btn primary", onclick: () => generate() }, icon("helm"), "Generate"),
        h("button", { class: "btn", onclick: () => generate(true), title: "Random gender, class and culture" }, icon("d20"), "Randomise"),
        h("label", { class: "check", style: { marginLeft: "10px" } }, neg, "Negative physical traits (scars, unflattering features)")));

    const result = h("div", { class: "npc-result" });
    const recent = h("div", { class: "list" });

    clear(el,
      h("div", { class: "tool-head" }, h("div", {}, h("h1", {}, "NPC Generator"),
        h("p", { class: "lede" }, "Rules-accurate NPCs from the Core Rulebook tables — every generated NPC is logged and shown on the Table."))),
      optionsPanel,
      h("div", { class: "npc-layout" }, result,
        h("aside", { class: "panel npc-recent" }, h("h3", {}, "This session"), recent)));

    // ---------- actions
    async function generate(randomise = false) {
      const body = { ...choice };
      if (randomise) Object.assign(body, { gender: "Random", culture: "Random", religion: "Random", social_class: "Random", randomise_class: true });
      const r = await post("/api/npc/generate", body);
      show(r.npc, r.formats);
    }

    async function reroll(field) {
      const r = await post("/api/npc/reroll", { npc, field });
      show(r.npc, r.formats);
      toast(`Rerolled ${field}`, "ok");
    }

    function show(n, f) {
      npc = n; fmt = f;
      render();
    }

    async function ensureFormats() {
      if (!fmt) fmt = await post("/api/npc/formats", { npc });
      return fmt;
    }

    // ---------- rendering
    const roll = (label, value, kind = "skill") => ctx.rollCheck({ label, value, kind, actor: npc.full });

    function rollable(label, value, kind) {
      return h("span", { class: `rollable ${value >= FAMOUS && kind !== "characteristic" ? "famous" : ""}`,
        title: `Roll ${label} (${skillDisplay(value)})`, onclick: () => roll(label, value, kind) }, kind === "characteristic" ? value : skillDisplay(value));
    }

    function named(name, value, kind) {
      const cls = value >= EXALTED ? "nm exalted" : value >= FAMOUS ? "nm famous" : "nm";
      return h("span", { class: "pair" }, h("span", { class: cls }, name), " ", rollable(name, value, kind));
    }

    function row(k, ...v) { return [h("div", { class: "k" }, k), h("div", { class: "v" }, ...v)]; }

    function render() {
      if (!npc) {
        clear(result, h("div", { class: "empty" }, icon("helm"), "Choose some options and press Generate."));
        return;
      }
      const n = npc, a = n.appearance || {}, d = n.derived || {};
      const sheet = h("div", { class: "sheet" });
      const add = (...rows) => sheet.append(...rows.flat());

      if (n.appearance) {
        const height = n.height ? `, ~${n.height} tall` : "";
        add(row("Appearance", `${a.build ? a.build + "; " : ""}${a.descriptor}${height}; ${a.eyes} eyes`));
        if (a.features?.length) add(row("Features", a.features.join("; ")));
      }
      if (n.manner) add(row("Manner", n.manner));
      if (n.directed) add(row(n.directed.kind, n.directed.text));

      const traits = n.traits ? h("div", { class: "traits-grid" }, n.traits.map(([l, lv, r, rv]) =>
        h("div", { class: "trait-pair" }, named(l, lv, "trait"), h("span", { class: "faint" }, " / "), named(r, rv, "trait")))) : null;
      const passions = n.passions ? h("div", { class: "flow" }, n.passions.map(([nm, v]) => named(nm, v, "passion"))) : null;
      const chars = n.stats ? h("div", { class: "flow" }, CHAR_ORDER.map((k) =>
        h("span", { class: "pair" }, h("span", { class: "nm" }, CHAR_FULL[k]), " ", rollable(CHAR_FULL[k], n.stats[k], "characteristic")))) : null;
      const derived = n.derived ? h("div", { class: "flow derived" },
        h("span", {}, "Hit Points ", h("b", {}, d["Hit Points"])),
        h("span", {}, "Move ", h("b", {}, d.Move)),
        h("span", {}, "Damage ", h("span", { class: "rollable dmg", title: "Roll damage",
          onclick: () => ctx.rollDamage({ label: "Damage", expr: d.Damage, actor: n.full }) }, d.Damage)),
        h("span", {}, "Healing ", h("b", {}, d["Healing Rate"])),
        h("span", {}, "Major Wound ", h("b", {}, d["Major Wound"])),
        h("span", {}, "Knockdown ", h("b", {}, d.Knockdown)),
        h("span", {}, "Unconscious ", h("b", {}, d.Unconscious))) : null;
      const skills = n.skills ? h("div", { class: "flow" }, Object.entries(n.skills)
        .sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0])).map(([nm, v]) => named(nm, v, "skill"))) : null;

      const knight = n.full_knight ? h("div", { class: "sheet" },
        n.homeland ? row("Age / Home", `${n.age ?? 21} · ${n.homeland}${n.residence ? ` (${n.residence})` : ""}`) : [],
        n.family_talent?.length ? row("Family talent", "+3 " + n.family_talent.join(", ")) : [],
        n.parent_glory ? row("Inherited", `Glory from a parent of ${n.parent_glory.toLocaleString()} Glory`) : [],
        n.family_lore?.length ? row("Family lore", h("ul", { class: "lore" }, n.family_lore.map((l) => h("li", {}, `An ancestor ${l}`)))) : [],
        n.ideals ? row("Ideals", h("div", { class: "ideals" }, n.ideals.map((i) => h("div", { class: `ideal ${i.met ? "met" : ""}` },
          h("span", { class: "mark" }, i.met ? "✓" : "✗"), h("b", {}, i.name),
          i.met ? null : h("span", { class: "faint" }, " — needs " + i.requirements.filter((x) => !x.ok)
            .map((x) => `${x.label.split("(")[0].trim()} ${x.current}/${x.needed}`).join("; ")))))) : [],
        n.squire ? row("Squire", h("span", { class: "linkish", title: "Open the squire as an NPC", onclick: () => show(n.squire, null) },
          `${n.squire.full} (${n.squire.culture} squire, age ${n.squire.age ?? "?"})`)) : []) : null;

      const naming = (n.naming_note || n.pronunciation?.length) ? h("div", { class: "sheet faint-sheet" },
        n.naming_note ? row("Naming", n.naming_note) : [],
        n.pronunciation?.length ? row("Say it", n.pronunciation.join("; ")) : []) : null;

      clear(result,
        h("div", { class: "panel npc-card" },
          h("div", { class: "npc-top" },
            h("div", { style: { minWidth: 0 } },
              h("div", { class: "namebig", title: "Click to copy the name", onclick: () => copyText(n.full, `“${n.full}” copied`) }, n.full),
              h("div", { class: "subtitle" }, n.subtitle, n.glory != null ? h("span", { class: "tag or", style: { marginLeft: "10px" } }, `Glory ${n.glory}`) : null,
                n.full_knight ? h("span", { class: "tag azure", style: { marginLeft: "6px" } }, "Full Cymric knight") : null)),
            h("div", { class: "toolbar" },
              h("button", { class: "btn", title: "Spotlight this NPC's description on the Table", onclick: () => post("/api/npc/present", { npc }).then(() => toast("Presented on the Table", "ok")) }, icon("present"), "Present"),
              h("button", { class: "btn", title: "Keep this NPC in the Cast (with GM notes) across sessions",
                onclick: () => post("/api/cast", { npc }).then(() => toast(`${npc.full} kept in the Cast`, "ok")) }, icon("star"), "Keep"),
              h("button", { class: "btn", onclick: (e) => menu(e.currentTarget, opts.reroll_fields.map((f) => [f, () => reroll(f)])) }, icon("refresh"), "Reroll ▾"),
              h("button", { class: "btn icon", title: "More", onclick: (e) => moreMenu(e.currentTarget) }, icon("dots")))),
          h("div", { class: "readaloud" }, n.description),
          h("div", { class: "section-label" }, "Look & manner"), sheet,
          traits ? [h("div", { class: "section-label" }, "Personality traits"), traits] : null,
          passions ? [h("div", { class: "section-label" }, "Passions"), passions] : null,
          chars ? [h("div", { class: "section-label" }, "Characteristics"), chars, derived] : null,
          skills ? [h("div", { class: "section-label" }, "Skills"), skills] : null,
          knight ? [h("div", { class: "section-label" }, "Knightly heritage"), knight] : null,
          naming ? [h("div", { class: "section-label" }, "Name"), naming] : null));
    }

    function moreMenu(anchor) {
      menu(anchor, [
        ["Copy statblock", async () => copyText((await ensureFormats()).statblock, "Statblock copied"), { icon: "copy" }],
        ["Copy Markdown", async () => copyText((await ensureFormats()).markdown, "Markdown copied"), { icon: "copy" }],
        ["Copy image prompt", async () => copyText((await ensureFormats()).image_prompt, "Image prompt copied"), { icon: "image" }],
        null,
        ["Make an adversary from this NPC", async () => {
          const r = await post("/api/npc/adversary-draft", { npc });
          ctx.navigate("adversaries", { draft: r.draft });
        }, { icon: "dragon" }],
        ...(npc.full_knight && opts.pdf_available ? [["Export character sheet PDF", exportPdf, { icon: "download" }]] : []),
      ]);
    }

    async function exportPdf() {
      const res = await api("/api/npc/pdf", { method: "POST", body: { npc }, raw: true });
      const blob = await res.blob();
      const a = h("a", { href: URL.createObjectURL(blob), download: `${npc.full}.pdf` });
      document.body.append(a); a.click(); a.remove();
    }

    // ---------- this-session list (replaces the desktop roster)
    function renderRecent() {
      const seen = new Map();
      for (const ev of ctx.events) {
        if ((ev.type === "npc.generated" || ev.type === "npc.updated") && !ev.struck && ev.data?.npc) seen.set(ev.data.npc.uid || ev.data.npc.full, ev.data.npc);
      }
      const list = [...seen.values()].reverse().slice(0, 30);
      clear(recent, list.length ? list.map((n) => h("div", { class: `list-item ${npc && n.uid === npc.uid ? "on" : ""}`, onclick: () => show(structuredClone(n), null) },
        h("div", { style: { minWidth: 0 } }, h("div", { class: "nm-line" }, n.full), h("div", { class: "faint small" }, n.subtitle))))
        : h("div", { class: "faint small" }, "NPCs you generate this session appear here."));
    }

    ctx.onEvent((evs) => { if (evs.some((e) => e.type.startsWith("npc.") || e.type.startsWith("meta."))) renderRecent(); });
    render();
    renderRecent();
    const inst = {
      show(p) { if (p?.npc) show(p.npc, null); },
    };
    inst.show(handoff);
    return inst;
  },
};
