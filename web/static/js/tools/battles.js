// Battles: the saved-battle library editor (prep). A battle is a Size plus one
// card per day (Intensity, turns, deck, turn scripts); Launch starts it in the
// Battle tool at Mustering. Library edits are not logged, as for encounters.

import { h, clear, api, post, put, del, enc, icon, confirmBox, toast, useCss } from "../lib.js";
import { dayCard, examplesBanner } from "../components.js";

// Table 6.1 (mirrors core/battle.py SIZES).
const SIZES = [
  ["fight", "Fight", 1, "1D6+2"], ["skirmish", "Skirmish", 3, "2D6"], ["clash", "Clash", 5, "2D6+1"],
  ["small", "Small Battle", 6, "2D6+2"], ["medium", "Medium Battle", 7, "2D6+3"],
  ["large", "Large Battle", 8, "3D6"], ["huge", "Huge Battle", 8, "3D6+1"],
].map(([key, label, turns, dice]) => ({ key, label, turns, dice }));
const SIZE = Object.fromEntries(SIZES.map((s) => [s.key, s]));
const ARMY = new Set(["clash", "small", "medium", "large", "huge"]);   // army commander rolls (Clash and up)
const PRESET = new Set(["small", "medium", "large", "huge"]);          // preset outcome (Small and up)
// Table 6.7 (core/battle.py OUTCOME_LABEL)
const BATTLE_OUTCOMES = [["decisive_victory", "Decisive Victory"], ["victory", "Victory"], ["indecisive", "Indecisive"],
  ["defeat", "Defeat"], ["decisive_defeat", "Decisive Defeat"]];
const SR_DAYS = "The core rules fight a battle as one engagement of up to the Table 6.1 turns. Several days, "
  + "each with its own Intensity, and Morale and Passions reset each morning, come from the Sword Campaign scenario.";

const clone = (o) => JSON.parse(JSON.stringify(o));
const dayCount = (b) => (Array.isArray(b.days) ? b.days.length : Number(b.days) || 1);
const sizeLabel = (k) => SIZE[k]?.label || k;

export default {
  async mount(el, ctx) {
    useCss("battles");
    let library = [];      // [{key, size, days, source}]
    let decks = [];        // /api/battle-decks cards
    let q = "";
    let key = null, draft = null, baseline = "";

    const search = h("input", { class: "input", type: "search", placeholder: "Search battles…" });
    const listEl = h("div", { class: "list list-scroll bt-list" });
    const countEl = h("span", { class: "faint small" });
    const editor = h("div", { class: "bt-editor" });
    search.addEventListener("input", () => { q = search.value.toLowerCase(); renderList(); });
    search.addEventListener("keydown", (e) => { if (e.key === "Enter") { const f = filtered()[0]; if (f) load(f.key); } });

    clear(el,
      h("div", { class: "tool-head" }, h("div", {}, h("h1", {}, "Battles"),
        h("p", { class: "lede" }, "Prepare battles ahead of the session: size, days, each day's deck and turn scripts. Launch one into the Battle tool."))),
      examplesBanner({ onAdded: async () => { toast("Battle cards added", "ok"); await refreshLibrary(); if (draft && !dirty()) renderEditor(); } }),
      h("div", { class: "split bt-split" },
        h("aside", { class: "panel bt-lib" }, search, h("div", { class: "row", style: { justifyContent: "flex-end" } }, countEl), listEl,
          h("div", { class: "bt-lib-btns" },
            h("button", { class: "btn sm", onclick: newDraft }, icon("plus"), "New"),
            h("button", { class: "btn sm", onclick: duplicate }, icon("copy"), "Duplicate"),
            h("button", { class: "btn sm danger", onclick: remove }, icon("x"), "Delete"))),
        editor));

    // ---------------------------------------------------------------- data
    async function refreshLibrary() {
      const [b, d] = await Promise.all([api("/api/battles"), api("/api/battle-decks")]);
      library = b.battles;
      decks = d.cards;
      renderList();
    }

    function filtered() {
      return library.filter((b) => !q || `${b.key} ${sizeLabel(b.size)}`.toLowerCase().includes(q));
    }

    function renderList() {
      const rows = filtered();
      countEl.textContent = `${rows.length} of ${library.length}`;
      clear(listEl, rows.length ? rows.map((b) => {
        const n = dayCount(b);
        return h("div", { class: `list-item bt-item ${b.key === key ? "on" : ""}`, onclick: () => load(b.key), title: b.key },
          h("div", { class: "bt-item-main" },
            h("div", { class: "bt-item-name" }, b.key, b.source === "example" ? h("span", { class: "tag bt-src" }, "example") : null),
            h("div", { class: "faint small" }, `${sizeLabel(b.size)} · ${n} day${n === 1 ? "" : "s"}`)),
          h("button", { class: "btn ghost sm icon bt-launch", title: `Launch “${b.key}”`,
            onclick: (ev) => { ev.stopPropagation(); launch(b.key); } }, icon("play")));
      }) : h("div", { class: "faint small", style: { padding: "10px" } }, library.length ? "No battles match." : "No saved battles yet — start a new one."));
    }

    // ---------------------------------------------------------------- drafts
    const dirty = () => draft && JSON.stringify(draft) !== baseline;
    async function guardDirty() {
      if (!dirty()) return true;
      return confirmBox("Discard changes?", `“${draft.name || "This battle"}” has unsaved changes.`, "Discard", true);
    }

    function normalise(d) {
      d.name ??= ""; d.where ??= ""; d.against ??= ""; d.notes ??= "";
      d.size = SIZE[d.size] ? d.size : "clash";
      d.outcome ??= null; d.commander ??= null;
      d.army_commanders ||= {};
      for (const side of ["friendly", "enemy"]) d.army_commanders[side] = { name: "", battle: null, ...(d.army_commanders[side] || {}) };
      d.days ||= [];
      return d;
    }

    function setDraft(d, k, fresh = true) {
      draft = normalise(clone(d));
      key = k;
      baseline = fresh ? JSON.stringify(draft) : "";
      renderList();
      renderEditor();
    }

    async function load(k) {
      if (k === key && draft) return;
      if (!(await guardDirty())) return;
      const r = await api(`/api/battles/${enc(k)}`);
      setDraft(r.battle, r.key);
    }

    const blank = async (size = "clash") => (await api(`/api/battles/blank?size=${enc(size)}`)).battle;

    async function newDraft() {
      if (!(await guardDirty())) return;
      setDraft(await blank(), null);
    }

    async function duplicate() {
      if (!key) return toast("Pick a battle to duplicate", "err");
      if (!(await guardDirty())) return;
      const d = clone(draft);
      d.name = `${key} (copy)`; d.source = "user";
      setDraft(d, null, false);
    }

    async function remove() {
      if (!key) return toast("Pick a saved battle to delete", "err");
      if (!(await confirmBox("Delete battle", `Delete “${key}” from the working library?`, "Delete", true))) return;
      await del(`/api/battles/${enc(key)}`);
      toast(`Deleted ${key}`, "ok");
      key = null; baseline = JSON.stringify(draft);
      await refreshLibrary();
      setDraft(await blank(), null);
    }

    /** PUT the draft; returns the saved key, or null when not saved. */
    async function save(overwrite = false) {
      if (!draft.name.trim()) { toast("Give the battle a name first", "err"); return null; }
      let r;
      try {
        r = await put("/api/battles", { battle: draft, original: key, overwrite }, { quiet: [409] });
      } catch (e) {
        if (e.status === 409 && !overwrite
            && await confirmBox("Overwrite?", `A battle named “${draft.name}” already exists. Replace it?`, "Overwrite", true)) return save(true);
        return null;
      }
      setDraft(r.battle, r.key);
      toast(`Saved “${r.key}”`, "ok");
      for (const w of r.warnings || []) toast(w);
      await refreshLibrary();
      return r.key;
    }

    async function revert() {
      if (key) setDraft((await api(`/api/battles/${enc(key)}`)).battle, key);
      else setDraft(await blank(draft?.size), null);
    }

    // ---------------------------------------------------------------- launch
    async function launch(k) {
      if (!k || (k === key && dirty())) {
        const what = k ? `“${k}” has unsaved changes.` : "This battle isn't saved yet.";
        if (!(await confirmBox("Save and launch?", `${what} Save it and launch?`, "Save & launch"))) return;
        k = await save();
        if (!k) return;
      }
      await post("/api/battle/start", { key: k });
      toast(`Launched “${k}”`, "ok");
      ctx.navigate("battle");
    }

    // ---------------------------------------------------------------- editor
    let headEl, footEl;
    const touched = () => { const on = dirty(); headEl?.classList.toggle("dirty", on); footEl?.classList.toggle("dirty", on); };

    function setSize(s) {
      const old = SIZE[draft.size];
      if (s === draft.size) return;
      for (const day of draft.days) {
        if (day.turns === old?.turns) day.turns = SIZE[s].turns;   // keep the book length unless overridden
        if (!ARMY.has(s)) day.commanders = { friendly: null, enemy: null };
      }
      if (!PRESET.has(s)) draft.outcome = null;
      draft.size = s;
      touched(); renderEditor();
    }

    function renderEditor() {
      if (!draft) { clear(editor, h("div", { class: "empty" }, icon("flag"), "Pick a battle, or start a new one.")); return; }
      const d = draft;
      const fld = (label, input, cls = "") => h("label", { class: `field ${cls}` }, h("span", {}, label), input);
      const txt = (f, attrs = {}) => {
        const i = h("input", { class: "input", value: d[f] ?? "", ...attrs });
        i.addEventListener("input", () => { d[f] = i.value; touched(); if (f === "name") title.textContent = i.value || "New battle"; });
        return i;
      };
      const title = h("span", { class: "bt-title" }, d.name || "New battle");

      headEl = h("div", { class: "panel bt-head" },
        h("div", { style: { flex: 1, minWidth: 0 } }, title,
          h("div", { class: "faint small" }, key ? `Editing ${key}` : "Not yet saved", h("span", { class: "dirty-mark" }, " · unsaved changes"))),
        h("span", { class: "tag or" }, `${sizeLabel(d.size)} · ${d.days.length} day${d.days.length === 1 ? "" : "s"}`));

      // Size chips with the Table 6.1 hint
      const sizes = h("div", { class: "bt-sizes" }, SIZES.map((s) => h("button", {
        class: `chip bt-size ${d.size === s.key ? "on" : ""}`, title: `Table 6.1: at most ${s.turns} turn${s.turns === 1 ? "" : "s"}, random Intensity ${s.dice}`,
        onclick: () => setSize(s.key) }, h("span", { class: "bt-size-name" }, s.label),
        h("span", { class: "bt-size-hint" }, `max ${s.turns} turn${s.turns === 1 ? "" : "s"} · ${s.dice}`))));

      const notes = h("textarea", { class: "input", rows: 3, placeholder: "Background, sources, what's at stake — GM only." }, d.notes);
      notes.addEventListener("input", () => { d.notes = notes.value; touched(); });

      const gm = h("label", { class: "check", title: "Pre-selects GM (NPC) as the conroi's commander at Mustering" },
        h("input", { type: "checkbox", checked: d.commander === "gm", onchange: (e) => { d.commander = e.target.checked ? "gm" : null; touched(); } }),
        "GM leads the conroi");

      const armyRow = (side, text) => {
        const a = d.army_commanders[side];
        const name = h("input", { class: "input", value: a.name, placeholder: side === "friendly" ? "e.g. King Arthur" : "e.g. King Lot" });
        name.addEventListener("input", () => { a.name = name.value; touched(); });
        const val = h("input", { class: "input num", type: "number", min: 1, max: 40, value: a.battle ?? "", placeholder: "2D6+10" });
        val.addEventListener("input", () => { a.battle = val.value === "" ? null : Number(val.value); touched(); });
        return h("div", { class: "bt-army-row" }, h("span", { class: "bt-army-side" }, text), name,
          h("label", { class: "bt-army-val" }, h("span", { class: "label" }, "Battle"), val));
      };
      const army = ARMY.has(d.size) ? h("div", { class: "bt-army span-2" },
        h("div", { class: "label" }, "Army commanders"),
        h("p", { class: "faint small bt-help" }, "Shown at Mustering. Leave Battle blank to roll 2D6+10."),
        armyRow("friendly", "Friendly"), armyRow("enemy", "Enemy")) : null;

      const outcome = PRESET.has(d.size) ? fld("Preset outcome",
        h("select", { class: "input", onchange: (e) => { d.outcome = e.target.value || null; touched(); } },
          h("option", { value: "" }, "None: decide in the Aftermath"),
          BATTLE_OUTCOMES.map(([v, t]) => h("option", { value: v, selected: d.outcome === v }, t)))) : null;

      const details = h("div", { class: "panel" }, h("h3", {}, "The battle"),
        h("div", { class: "bt-grid" },
          fld("Name", txt("name", { placeholder: "e.g. Bedegraine" })),
          h("div", { class: "field span-2" }, h("span", {}, "Size"), sizes),
          fld("Where", txt("where", { placeholder: "e.g. Bedegraine forest" })),
          fld("Against", txt("against", { placeholder: "e.g. the eleven rebel kings" })),
          fld("Notes", notes, "span-2"),
          h("div", { class: "field" }, h("span", {}, "Commander"), gm),
          outcome || h("div"),
          army));

      // Days
      const days = h("div", { class: "bt-days" },
        h("div", { class: "bt-days-head" }, h("h3", {}, "Days"),
          d.days.length > 1 ? h("span", { class: "tag or rule-sr", title: SR_DAYS }, "Scenario rule") : null,
          h("span", { class: "faint small" }, d.days.length > 1 ? "Each day starts with a new muster: Morale back to its start, Passions usable again." : "")),
        d.days.map((day, i) => dayCard(day, d.size, {
          decks, label: `Day ${i + 1}`,
          onChange: (nd) => { d.days[i] = nd; touched(); },
          onRemove: d.days.length > 1 ? async () => {
            if (!(await confirmBox("Remove day", `Remove Day ${i + 1} and its scripts?`, "Remove", true))) return;
            d.days.splice(i, 1); touched(); renderEditor();
          } : null,
        })),
        h("button", { class: "btn bt-add-day", onclick: async () => {
          d.days.push((await blank(d.size)).days[0]);
          touched(); renderEditor();
          editor.querySelector(".day-card:last-of-type")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } }, icon("plus"), "Add day"));

      const foot = footEl = h("div", { class: "panel bt-foot" },
        h("span", { class: "faint small" }, key ? `Editing ${key}` : "Not yet saved", h("span", { class: "dirty-mark" }, " · unsaved changes")),
        h("div", { class: "toolbar" },
          h("button", { class: "btn", onclick: revert }, icon("undo"), "Revert"),
          h("button", { class: "btn bt-save", onclick: () => save() }, icon("check"), "Save"),
          h("button", { class: "btn primary", onclick: () => launch(key), title: "Start this battle in the Battle tool, at Mustering" }, icon("play"), "Launch")));

      clear(editor, headEl, details, days, foot);
      touched();
    }

    // ---------------------------------------------------------------- boot
    await refreshLibrary();
    if (library.length) await load(library[0].key);
    else setDraft(await blank(), null);

    return {
      show() { renderList(); },
      async onLibrary() {
        await refreshLibrary();
        if (draft && !dirty()) renderEditor();
      },
    };
  },
};
