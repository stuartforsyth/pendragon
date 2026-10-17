// Encounter Creator: reusable encounter recipes (who, how many, how they scale
// with the party) with a live preview and one-click launch into combat.

import { h, clear, api, post, put, del, enc, icon, confirmBox, modal, toast, useCss, debounce } from "../lib.js";

const CATS = ["all", "human", "beast", "monster", "fae"];
const clone = (o) => JSON.parse(JSON.stringify(o));
const fmtCount = (v) => (Number.isInteger(Number(v)) ? String(Number(v)) : String(v));

export default {
  async mount(el, ctx) {
    useCss("encounters");
    let library = [];
    let adversaries = [];       // [{key, category, kind, hp, glory}]
    let q = "";
    let key = null, draft = null, baseline = "";
    let battleHint = null;
    let players = 4;

    const search = h("input", { class: "input", type: "search", placeholder: "Search name, tags, adversaries…" });
    const listEl = h("div", { class: "list list-scroll enc-list" });
    const countEl = h("span", { class: "faint small" });
    const editor = h("div", { class: "enc-editor" });
    search.addEventListener("input", () => { q = search.value.toLowerCase(); renderList(); });
    search.addEventListener("keydown", (e) => { if (e.key === "Enter") { const f = filtered()[0]; if (f) load(f.key); } });

    clear(el,
      h("div", { class: "tool-head" }, h("div", {}, h("h1", {}, "Encounter Creator"),
        h("p", { class: "lede" }, "Recipes for a fight — which foes, how many, and how they scale with the party. Launch one straight into combat.")),
        h("div", { class: "actions" }, h("button", { class: "btn", onclick: examplesDialog, title: "New cards and fixes shipped with the app" }, icon("download"), "Examples…"))),
      h("div", { class: "split enc-split" },
        h("aside", { class: "panel enc-lib" }, search, h("div", { class: "row", style: { justifyContent: "flex-end" } }, countEl), listEl,
          h("div", { class: "enc-lib-btns" },
            h("button", { class: "btn sm", onclick: newDraft }, icon("plus"), "New"),
            h("button", { class: "btn sm", onclick: duplicate }, icon("copy"), "Duplicate"),
            h("button", { class: "btn sm danger", onclick: remove }, icon("x"), "Delete"))),
        editor));

    // ---------------------------------------------------------------- examples
    // New shipped content (battle cards, Opportunities, fixes) into the user's
    // library: missing entries and fields are added; nothing is overwritten
    // except a card the GM explicitly restores.
    // One line per name, adversary and encounter fields side by side.
    function fieldRows(fields) {
      const by = new Map();
      for (const f of fields) {
        const row = by.get(f.key) || {};
        row[f.kind] = f.fields.map((x) => x.replace(/^other\./, "").replace(/_/g, " "));
        by.set(f.key, row);
      }
      return [...by].map(([k, row]) => h("li", {}, h("b", {}, k), ": ",
        [row.adversaries && `card — ${row.adversaries.join(", ")}`, row.encounters && `encounter — ${row.encounters.join(", ")}`,
         row.battles && `battle — ${row.battles.join(", ")}`].filter(Boolean).join(" · ")));
    }

    async function examplesDialog() {
      const r = await api("/api/library/examples");
      const names = Object.entries(r.missing).flatMap(([kind, keys]) => keys.map((k) => ({ kind, k })));
      const nothing = !names.length && !r.fields.length && !r.differs.length;
      await modal("Examples", (close) => {
        if (nothing) return [h("p", { class: "muted" }, "Your library has everything."),
          h("div", { class: "foot" }, h("button", { class: "btn primary", onclick: () => close() }, "Close"))];
        const addable = names.length || r.fields.length;
        return [
          names.length ? h("div", { class: "ex-sec" }, h("div", { class: "section-label" }, `New in the app's examples (${names.length})`),
            h("p", { class: "small" }, names.map((n) => n.k).join(" · "))) : null,
          r.fields.length ? h("div", { class: "ex-sec" }, h("div", { class: "section-label" }, "New fields for your cards"),
            h("ul", { class: "ex-list small" }, fieldRows(r.fields))) : null,
          addable ? h("div", { class: "row" }, h("button", { class: "btn primary", onclick: async () => {
            const a = (await post("/api/library/examples/merge")).added;
            toast(`Added ${a.adversaries} adversaries, ${a.encounters} encounters, ${a.fields} fields`);
            close(); await refreshLibrary();
          } }, icon("plus"), "Add missing")) : null,
          r.differs.length ? h("div", { class: "ex-sec" }, h("div", { class: "section-label" }, "Cards that differ from the shipped card"),
            h("p", { class: "faint small" }, "Your edits are kept unless you restore a card."),
            h("ul", { class: "ex-list" }, r.differs.map((d) => h("li", { class: "ex-row" },
              h("span", {}, h("b", {}, d.key), h("span", { class: "faint small" }, ` — ${d.fields.join(", ")}`)),
              h("button", { class: "btn sm", onclick: async (e) => {
                if (!(await confirmBox("Restore shipped card?", `Replace your ${d.key} with the shipped card? Your edits to it are lost.`, "Restore", true))) return;
                await post("/api/library/examples/restore", { kind: d.kind, key: d.key });
                toast(`${d.key} restored`);
                e.target.closest("li").remove();
                await refreshLibrary();
              } }, "Restore shipped card"))))) : null,
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Close")),
        ];
      }, { wide: true });
    }

    // ---------------------------------------------------------------- data
    async function refreshLibrary() {
      const [e, a] = await Promise.all([api("/api/encounters"), api("/api/adversaries")]);
      library = e.encounters;
      adversaries = a.adversaries;
      renderList();
    }

    async function defaultPlayers() {
      try {
        const p = (await api("/api/party")).party.filter((m) => m.active !== false);
        players = p.length || 4;
      } catch { players = 4; }
    }

    function filtered() {
      return library.filter((e) => !q || `${e.key} ${e.description} ${e.tags.join(" ")} ${e.adversaries.join(" ")}`.toLowerCase().includes(q));
    }

    function renderList() {
      const rows = filtered();
      countEl.textContent = `${rows.length} of ${library.length}`;
      clear(listEl, rows.length ? rows.map((e) => h("div", { class: `list-item enc-item ${e.key === key ? "on" : ""}`, onclick: () => load(e.key), title: e.description || e.key },
        h("div", { class: "enc-item-main" },
          h("div", { class: "enc-item-name" }, e.key,
            e.battle_role === "foe" ? h("span", { class: "tag gules role-tag" }, "Foe")
              : e.battle_role === "opportunity" ? h("span", { class: "tag or role-tag" }, "★ Opportunity") : null),
          h("div", { class: "faint small enc-item-sub" }, e.tags.length ? e.tags.join(" · ") : `${e.lines} line${e.lines === 1 ? "" : "s"}`)),
        h("button", { class: "btn ghost sm icon enc-launch", title: `Launch “${e.key}” for ${players} players`,
          onclick: (ev) => { ev.stopPropagation(); launch({ encounter: e.key, name: e.key }); } }, icon("play"))))
        : h("div", { class: "faint small", style: { padding: "10px" } }, "No encounters match."));
    }

    // ---------------------------------------------------------------- drafts
    const dirty = () => draft && JSON.stringify(draft) !== baseline;
    async function guardDirty() {
      if (!dirty()) return true;
      return confirmBox("Discard changes?", `“${draft.name || "This encounter"}” has unsaved changes.`, "Discard", true);
    }

    function normalise(d) {
      d.roster ||= []; d.tags ||= []; d.notes ??= ""; d.description ??= ""; d.name ??= "";
      d.battle_role ??= null; d.morale_minimum ??= null; d.morale_loss ??= ""; d.missile ??= false; d.rules ??= "";
      if (!d.leader || typeof d.leader !== "object") d.leader = null;
      return d;
    }

    function setDraft(d, k, fresh = true) {
      draft = normalise(clone(d));
      key = k;
      baseline = fresh ? JSON.stringify(draft) : "";
      renderList();
      renderEditor();
      updatePreview();
    }

    async function load(k) {
      if (k === key && draft) return;
      if (!(await guardDirty())) return;
      const r = await api(`/api/encounters/${enc(k)}`);
      setDraft(r.encounter, r.key);
    }

    async function newDraft() {
      if (!(await guardDirty())) return;
      const r = await api("/api/encounters/blank");
      setDraft(r.encounter, null);
    }

    async function duplicate() {
      if (!key) return toast("Pick an encounter to duplicate", "err");
      if (!(await guardDirty())) return;
      const d = clone(draft);
      d.name = `${key} (copy)`; d.source = "user";
      setDraft(d, null, false);
    }

    async function remove() {
      if (!key) return toast("Pick a saved encounter to delete", "err");
      if (!(await confirmBox("Delete encounter", `Delete “${key}” from the working library?`, "Delete", true))) return;
      await del(`/api/encounters/${enc(key)}`);
      toast(`Deleted ${key}`, "ok");
      key = null; baseline = JSON.stringify(draft);
      await refreshLibrary();
      setDraft((await api("/api/encounters/blank")).encounter, null);
    }

    async function save(overwrite = false) {
      if (!draft.name.trim()) return toast("Give the encounter a name first", "err");
      let r;
      try {
        r = await put("/api/encounters", { encounter: draft, original: key, overwrite }, { quiet: [409] });
      } catch (e) {
        if (e.status === 409 && !overwrite
            && await confirmBox("Overwrite?", `An encounter named “${draft.name}” already exists. Replace it?`, "Overwrite", true)) return save(true);
        return;
      }
      setDraft(r.encounter, r.key);
      toast(`Saved “${r.key}”`, "ok");
      await refreshLibrary();
    }

    async function revert() {
      if (key) setDraft((await api(`/api/encounters/${enc(key)}`)).encounter, key);
      else setDraft((await api("/api/encounters/blank")).encounter, null);
    }

    // ---------------------------------------------------------------- launch
    async function launch(body) {
      const cs = (await api("/api/combat")).combat;
      if (cs?.active && !(await confirmBox("Start a new combat?", `“${cs.name}” is still in progress — launching ends it (the knights' Hit Points carry back to the Party).`, "Launch", true))) return;
      await post("/api/combat/start", { players, ...body });
      toast(`Launched “${body.name}”`, "ok");
      ctx.navigate("combat");
    }

    async function launchDraft() {
      if (!draft.roster.some((l) => l.adversary) && !draft.leader?.adversary) return toast("Add at least one roster line first", "err");
      await launch({ definition: draft, name: draft.name || "Encounter" });
    }

    // ---------------------------------------------------------------- editor
    let headEl, previewEl, playersIn;
    const touched = () => headEl?.classList.toggle("dirty", dirty());

    const advOptions = (cat, current) => {
      const names = adversaries.filter((a) => cat === "all" || a.category === cat).map((a) => a.key);
      if (current && !names.includes(current)) names.unshift(current);
      return [h("option", { value: "" }, "Choose…"), ...names.map((n) => h("option", { value: n, selected: n === current }, n))];
    };
    const catOf = (name) => adversaries.find((a) => a.key === name)?.category || "all";

    function advPicker(current, onPick) {
      const cat = h("select", { class: "input cat-sel", title: "Filter by category" }, CATS.map((c) => h("option", { value: c }, c)));
      const adv = h("select", { class: "input" }, advOptions("all", current));
      cat.onchange = () => clear(adv, advOptions(cat.value, adv.value));
      adv.onchange = () => onPick(adv.value);
      return [cat, adv];
    }

    function renderEditor() {
      if (!draft) { clear(editor, h("div", { class: "empty" }, icon("flag"), "Pick an encounter, or start a new one.")); return; }
      const d = draft;
      const txt = (f, attrs = {}) => {
        const i = h("input", { class: "input", value: d[f] ?? "", ...attrs });
        i.addEventListener("input", () => { d[f] = i.value; touched(); if (f === "name") title.textContent = i.value || "New encounter"; });
        return i;
      };
      const fld = (label, input, cls = "") => h("label", { class: `field ${cls}` }, h("span", {}, label), input);
      const title = h("span", { class: "enc-title" }, d.name || "New encounter");

      headEl = h("div", { class: "panel enc-head sticky-bar" },
        h("div", { style: { flex: 1, minWidth: 0 } }, title,
          h("div", { class: "faint small" }, key ? `Editing ${key}` : "Not yet saved", h("span", { class: "dirty-mark" }, " · unsaved changes"))),
        h("div", { class: "toolbar" },
          h("button", { class: "btn", onclick: revert }, icon("undo"), "Revert"),
          h("button", { class: "btn primary", onclick: () => save() }, icon("check"), "Save")));

      const tags = h("input", { class: "input", value: d.tags.join(", "), placeholder: "forest, saxon, night…" });
      tags.addEventListener("input", () => { d.tags = tags.value.split(",").map((t) => t.trim()).filter(Boolean); touched(); });
      const notes = h("textarea", { class: "input", rows: 4, placeholder: "Who they are, why they're here, campaign references — shown only in your console." }, d.notes);
      notes.addEventListener("input", () => { d.notes = notes.value; touched(); });

      const details = h("div", { class: "panel" }, h("h3", {}, "Details"),
        h("div", { class: "enc-grid" },
          fld("Name", txt("name", { placeholder: "e.g. Saxon raiding party" })),
          fld("Tags", tags),
          fld("Description (read on the Table at launch)", txt("description", { placeholder: "A one-line set-up" }), "span-2"),
          fld("GM notes & campaign references", notes, "span-2")));

      // roster
      const rosterEl = h("div", { class: "roster" });
      const drawRoster = () => clear(rosterEl, d.roster.length ? [
        h("div", { class: "roster-row roster-headrow" }, ...["Filter", "Adversary", "Count", "", "", ""].map((t) => h("span", { class: "label" }, t))),
        ...d.roster.map((ln, i) => {
          const [cat, adv] = advPicker(ln.adversary, (v) => { ln.adversary = v; touched(); updatePreview(); });
          if (ln.adversary) cat.value = "all";
          const count = h("input", { class: "input num", value: fmtCount(ln.count ?? 1), inputmode: "decimal",
            title: ln.per_player ? "Multiplier of the party size (fractions allowed)" : "A fixed number" });
          count.addEventListener("input", () => { ln.count = ln.per_player ? Number(count.value) || 0 : Math.max(0, Math.round(Number(count.value) || 0)); touched(); updatePreview(); });
          const per = h("input", { type: "checkbox", checked: !!ln.per_player });
          per.onchange = () => { ln.per_player = per.checked; touched(); updatePreview(); };
          const prom = h("input", { type: "checkbox", checked: !!ln.promote });
          prom.onchange = () => { ln.promote = prom.checked; touched(); updatePreview(); };
          return h("div", { class: "roster-row" }, cat, adv, count,
            h("label", { class: "check small", title: "Scale with party size" }, per, "× players"),
            h("label", { class: "check small", title: "Promote to champion" }, prom, "promote"),
            h("button", { class: "btn ghost sm icon", title: "Remove line", onclick: () => { d.roster.splice(i, 1); touched(); drawRoster(); updatePreview(); } }, icon("x")));
        })] : h("div", { class: "faint small" }, "No roster lines yet — add one below."));
      drawRoster();

      const roster = h("div", { class: "panel" }, h("h3", {}, d.battle_role === "opportunity" ? "Foes to fight (optional) — each line scales itself" : "Roster — each line scales itself"),
        h("p", { class: "faint small", style: { margin: "-4px 0 10px" } },
          "Tick “× players” to scale with the party (fractions allowed — 1.5 × players of Bodyguards); untick for a fixed number (1 King Lot)."),
        rosterEl,
        h("button", { class: "btn sm", style: { marginTop: "10px" }, onclick: () => {
          d.roster.push({ adversary: "", count: 1, per_player: true, promote: false });
          touched(); drawRoster(); rosterEl.querySelector(".roster-row:last-child select:nth-child(2)")?.focus();
        } }, icon("plus"), "Add roster line"));

      // battle: Foe or Opportunity, with the deck's Morale Minimum and Loss
      battleHint = h("div", { class: "faint small" });
      const role = (r, label) => h("button", { class: `chip ${d.battle_role === r ? "on" : ""}`,
        onclick: () => { d.battle_role = r; if (r !== "foe") d.missile = false; touched(); renderEditor(); updatePreview(); } }, label);
      const mmIn = h("input", { class: "input num", type: "number", min: 0, value: d.morale_minimum ?? "", placeholder: "—" });
      mmIn.addEventListener("input", () => { d.morale_minimum = mmIn.value === "" ? null : Number(mmIn.value); touched(); });
      const lossIn = h("input", { class: "input", value: d.morale_loss || "", placeholder: "e.g. 1D6+3", style: { width: "120px" } });
      lossIn.addEventListener("input", () => { d.morale_loss = lossIn.value.trim(); touched(); });
      const battle = h("div", { class: "panel" }, h("h3", {}, "Battle"),
        h("div", { class: "row", style: { flexWrap: "wrap" } }, role(null, "Not in battles"), role("foe", "Foe"), role("opportunity", "Opportunity ★")),
        d.battle_role ? h("div", { class: "row battle-fields", style: { flexWrap: "wrap", marginTop: "10px" } },
          h("label", { class: "field" }, h("span", {}, "Minimum Morale"), mmIn),
          h("label", { class: "field" }, h("span", {}, "Morale Loss"), lossIn),
          d.battle_role === "foe" ? h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!d.missile,
            onchange: (e) => { d.missile = e.target.checked; touched(); } }), "Missile barrage before contact") : null) : null,
        d.battle_role === "opportunity" ? h("label", { class: "field", style: { marginTop: "10px" } }, h("span", {}, "Rules / rewards — played at the table"),
          (() => { const t = h("textarea", { class: "input", rows: 4, placeholder: "e.g. Win within four rounds: each knight +100 Glory" }, d.rules || "");
            t.addEventListener("input", () => { d.rules = t.value; touched(); }); return t; })()) : null,
        d.battle_role ? battleHint : null);

      // leader
      const lead = d.leader || { adversary: "", promote: true };
      const [lcat, ladv] = advPicker(lead.adversary, (v) => {
        d.leader = v ? { adversary: v, promote: lprom.checked } : null; touched(); updatePreview();
      });
      const lprom = h("input", { type: "checkbox", checked: lead.promote !== false });
      lprom.onchange = () => { if (d.leader) d.leader.promote = lprom.checked; touched(); updatePreview(); };
      const leader = h("div", { class: "panel" }, h("h3", {}, "Leader — optional, auto-promoted"),
        h("div", { class: "row leader-row" }, lcat, ladv, h("label", { class: "check small" }, lprom, "promote"),
          h("span", { class: "faint small" }, "e.g. a war-leader, or a lone monster")));

      // preview
      playersIn = h("input", { class: "input num", type: "number", min: 1, max: 20, value: players });
      playersIn.addEventListener("input", () => { players = Math.max(1, Number(playersIn.value) || 1); updatePreview(); renderList(); });
      previewEl = h("div", { class: "preview-body" });
      const preview = h("div", { class: "panel preview-panel" },
        h("div", { class: "preview-side" },
          h("h3", {}, "Preview"),
          h("label", { class: "field" }, h("span", {}, "For players"), playersIn),
          h("button", { class: "btn primary", onclick: launchDraft, title: "Start this fight in the combat tracker" }, icon("swords"), "Launch combat")),
        previewEl);

      clear(editor, headEl, preview, roster, leader, battle, details);
      touched();
    }

    const updatePreview = debounce(async () => {
      if (!draft || !previewEl) return;
      const r = await post("/api/encounters/preview", { encounter: draft, players });
      if (battleHint && draft.battle_role) {
        const bd = r.battle_defaults;
        const mm = battleHint.closest(".panel")?.querySelector('input[type="number"]');
        const loss = battleHint.closest(".panel")?.querySelector('.battle-fields input:not([type])');
        if (mm) mm.placeholder = bd.morale_minimum != null ? `from the cards: ${bd.morale_minimum}` : "—";
        if (loss && bd.morale_loss) loss.placeholder = bd.morale_loss;
        clear(battleHint, `GM only · KV per knight ${bd.kv_per_knight || "0"} · ≈ Glory ${r.glory.toLocaleString()} for this party`);
      }
      clear(previewEl,
        r.lines.length ? h("ul", { class: "preview-lines" }, r.lines.map((l) => {
          const m = l.match(/^(\d+)× (.*)$/);
          return h("li", {}, m ? [h("span", { class: "pc" }, `${m[1]}×`), " ", m[2]] : l);
        })) : h("div", { class: "faint small" }, "Empty roster."),
        h("div", { class: "threat" },
          h("div", { class: "stat" }, h("div", { class: "label" }, "Combatants"), h("div", { class: "stat-v" }, r.total)),
          h("div", { class: "stat" }, h("div", { class: "label" }, "Total HP"), h("div", { class: "stat-v" }, r.hp)),
          h("div", { class: "stat" }, h("div", { class: "label" }, "≈ Glory"), h("div", { class: "stat-v or" }, r.glory.toLocaleString()))));
    }, 180);

    // ---------------------------------------------------------------- boot
    await Promise.all([refreshLibrary(), defaultPlayers()]);
    if (library.length) await load(library[0].key);
    else setDraft((await api("/api/encounters/blank")).encounter, null);

    return {
      show() { renderList(); },
      async onLibrary() {
        await refreshLibrary();
        if (draft && !dirty()) { renderEditor(); updatePreview(); }
      },
    };
  },
};
