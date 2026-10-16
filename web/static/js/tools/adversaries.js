// Adversary & Creature Creator: the reusable stat blocks encounters are built
// from. Library on the left, a live editor on the right.

import { h, clear, api, post, put, del, enc, icon, confirmBox, toast, useCss,
  debounce, CHAR_FULL, CHAR_ORDER } from "../lib.js";

const CATS = ["human", "beast", "monster", "fae"];
const CAT_TAG = { beast: "vert", monster: "gules", fae: "azure", human: "" };
const CREATURE_FIELDS = [
  ["health", "hit_points", "Hit Points"], ["health", "major_wound", "Major Wound"],
  ["health", "knockdown", "Knockdown"], ["health", "unconscious", "Unconscious"],
  ["other", "healing_rate", "Healing Rate"], ["other", "movement", "Move"],
  ["other", "armor_points", "Natural Armor"], ["other", "shield", "Shield"],
  ["other", "glory", "Glory Won"], ["other", "valorous_modifier", "Valorous mod"],
];

const clone = (o) => JSON.parse(JSON.stringify(o));
const badge = (a) => (a.category !== "human" ? "✦" : a.kind === "named" ? "★" : "▸");

export default {
  async mount(el, ctx, handoff) {
    useCss("adversaries");
    const meta = await api("/api/adversaries/meta");
    let library = [];
    const filt = { q: "", kind: "all", category: "all" };
    let key = null;          // library key being edited (null = new)
    let draft = null;        // working copy
    let baseline = "";       // JSON at last load/save, for the dirty marker
    let hint = "";

    // ---------------------------------------------------------------- layout
    const search = h("input", { class: "input", placeholder: "Search name, tier, description…", type: "search" });
    const kindSel = selectEl(["all", "generic", "named", "npc"], "all", ["all", "generic", "named", "NPCs (Cast)"]);
    const catSel = selectEl(["all", ...CATS], "all");
    const listEl = h("div", { class: "list list-scroll adv-list" });
    const countEl = h("span", { class: "faint small" });
    const editor = h("div", { class: "adv-editor" });

    search.addEventListener("input", () => { filt.q = search.value.toLowerCase(); renderList(); });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { const first = filtered()[0]; if (first) load(first.key); }
    });
    kindSel.onchange = () => { filt.kind = kindSel.value; renderList(); };
    catSel.onchange = () => { filt.category = catSel.value; renderList(); };

    clear(el,
      h("div", { class: "tool-head" },
        h("div", {}, h("h1", {}, "Adversaries & Creatures"),
          h("p", { class: "lede" }, "The reusable stat blocks every encounter is built from — generic types and named foes alike."))),
      h("div", { class: "split adv-split" },
        h("aside", { class: "panel adv-lib" },
          h("div", { class: "stack" }, search,
            h("div", { class: "row" }, h("span", { class: "label" }, "Kind"), kindSel, h("span", { class: "label" }, "Category"), catSel)),
          h("div", { class: "row adv-lib-head" }, countEl),
          listEl,
          h("div", { class: "adv-lib-btns" },
            h("button", { class: "btn sm", onclick: () => newDraft("generic") }, icon("plus"), "New generic"),
            h("button", { class: "btn sm", onclick: () => newDraft("named") }, icon("plus"), "New named"),
            h("button", { class: "btn sm", onclick: duplicate }, icon("copy"), "Duplicate"),
            h("button", { class: "btn sm danger", onclick: remove }, icon("x"), "Delete"))),
        editor));

    function selectEl(values, value, labels) {
      return h("select", { class: "input sel-sm" }, values.map((v, i) =>
        h("option", { value: v, selected: v === value }, labels ? labels[i] : v)));
    }

    // ---------------------------------------------------------------- library
    async function refreshLibrary() {
      const [a, c] = await Promise.all([api("/api/adversaries"), api("/api/cast/fightable")]);
      // Cast NPCs with saved stats are listed too (helm icon, murrey).
      library = [...c.npcs.map((n) => ({ ...n, isNpc: true })), ...a.adversaries];
      renderList();
    }

    function filtered() {
      return library.filter((a) => (filt.kind === "all" || a.kind === filt.kind)
        && (filt.category === "all" || a.category === filt.category)
        && (!filt.q || `${a.key} ${a.description} ${a.tier} ${a.category}`.toLowerCase().includes(filt.q)));
    }

    function renderList() {
      const rows = filtered();
      countEl.textContent = `${rows.length} of ${library.length}`;
      clear(listEl, rows.length ? rows.map((a) => a.isNpc ? h("div", {
        class: "list-item adv-item npc-item", title: "A Cast NPC — opens their stats as a new named adversary",
        onclick: () => loadNpc(a),
      },
        icon("helm", "npc-ico"),
        h("div", { class: "adv-item-main" },
          h("div", { class: "adv-item-name" }, a.key),
          h("div", { class: "faint small adv-item-sub" }, `NPC · ${a.tier}`)),
        h("span", { class: "meta" }, a.hp != null ? `HP ${a.hp}` : "")) : h("div", {
        class: `list-item adv-item ${a.key === key ? "on" : ""}`, title: a.description || a.key,
        onclick: () => load(a.key),
      },
        h("span", { class: `adv-badge ${a.category !== "human" ? "cat-" + a.category : a.kind}` }, badge(a)),
        h("div", { class: "adv-item-main" },
          h("div", { class: "adv-item-name" }, a.key),
          h("div", { class: "faint small adv-item-sub" }, a.category !== "human" ? a.category : (a.tier || a.kind))),
        h("span", { class: "meta" }, a.hp != null ? `HP ${a.hp}` : ""))) :
        h("div", { class: "faint small", style: { padding: "10px" } }, "No adversaries match."));
    }

    // ---------------------------------------------------------------- loading drafts
    const dirty = () => draft && JSON.stringify(draft) !== baseline;

    async function guardDirty() {
      if (!dirty()) return true;
      return confirmBox("Discard changes?", `“${draft.name || "This adversary"}” has unsaved changes.`, "Discard", true);
    }

    async function load(k) {
      if (k === key && draft) return;
      if (!(await guardDirty())) return;
      const r = await api(`/api/adversaries/${enc(k)}`);
      setDraft(r.adversary, r.key, "");
    }

    function setDraft(d, k, msg, fresh = true) {
      draft = normalise(clone(d));
      key = k;
      baseline = fresh ? JSON.stringify(draft) : "";
      hint = msg;
      renderList();
      renderEditor();
      recompute();
    }

    function normalise(d) {
      d.kind ||= "generic"; d.category ||= "human";
      d.characteristics ||= {}; d.attacks ||= []; d.skills ||= {}; d.traits ||= {}; d.passions ||= {};
      d.armour ||= { pieces: [], helmet: "", shield: "" };
      d.armour.pieces ||= [];
      d.health ||= {}; d.other ||= {};
      for (const f of ["name", "tier", "culture", "religion", "description", "promotion_title", "notes"]) d[f] ??= "";
      return d;
    }

    async function loadNpc(n) {
      if (!(await guardDirty())) return;
      const r = await api(`/api/cast/${enc(n.cast_id)}/adversary`);
      setDraft(r.adversary, null, `Stats from the Cast NPC ${n.key} — add armour if they wear any, then Save to keep them as an adversary.`, false);
    }

    async function newDraft(kind) {
      if (!(await guardDirty())) return;
      const r = await api(`/api/adversaries/blank?kind=${kind}`);
      setDraft(r.adversary, null, `New ${kind} adversary — fill in and Save.`);
    }

    async function duplicate() {
      if (!draft || !key) return toast("Pick an adversary to duplicate", "err");
      if (!(await guardDirty())) return;
      const d = clone(draft);
      d.name = `${key} (copy)`;
      d.source = "user";
      setDraft(d, null, "Duplicated — rename it and Save.", false);
    }

    async function remove() {
      if (!key) return toast("Pick a saved adversary to delete", "err");
      if (!(await confirmBox("Delete adversary", `Delete “${key}” from the working library? Encounters that use it will skip it.`, "Delete", true))) return;
      await del(`/api/adversaries/${enc(key)}`);
      toast(`Deleted ${key}`, "ok");
      baseline = JSON.stringify(draft);
      key = null;
      await refreshLibrary();
      const r = await api("/api/adversaries/blank");
      setDraft(r.adversary, null, "");
    }

    // ---------------------------------------------------------------- save / revert
    async function save(overwrite = false) {
      readName();
      if (!draft.name.trim()) return toast("Enter a name (named) or type name (generic) first", "err");
      let r;
      try {
        r = await put("/api/adversaries", { adversary: draft, original: key, overwrite }, { quiet: [409] });
      } catch (e) {
        if (e.status === 409 && !overwrite
            && await confirmBox("Overwrite?", `An adversary named “${draft.name}” already exists. Replace it?`, "Overwrite", true)) {
          return save(true);
        }
        return;
      }
      setDraft(r.adversary, r.key, "");
      toast(`Saved “${r.key}”`, "ok");
      await refreshLibrary();
    }

    async function revert() {
      if (key) {
        const r = await api(`/api/adversaries/${enc(key)}`);
        setDraft(r.adversary, r.key, "Reverted.");
      } else {
        const r = await api(`/api/adversaries/blank?kind=${draft.kind}`);
        setDraft(r.adversary, null, "Cleared.");
      }
    }

    let nameInput;
    function readName() { if (nameInput) draft.name = nameInput.value.trim(); }

    // ---------------------------------------------------------------- live feedback
    let derivedEl, armourEl, headEl;
    const recompute = debounce(async () => {
      if (!draft) return;
      const r = await post("/api/adversaries/compute", { characteristics: draft.characteristics, armour: draft.armour });
      if (derivedEl) {
        const d = r.derived;
        clear(derivedEl, [["Hit Points", d["Hit Points"]], ["Move", d.Move], ["Damage", d.Damage], ["Healing", d["Healing Rate"]],
          ["Major Wound", d["Major Wound"]], ["Knockdown", d.Knockdown], ["Unconscious", d.Unconscious]]
          .map(([k, v]) => h("div", { class: "stat" }, h("div", { class: "label" }, k), h("div", { class: "stat-v" }, v))));
      }
      if (armourEl) {
        clear(armourEl, h("span", {}, r.armour_desc || "(no armour)"), h("span", { class: "faint" }, "  →  "),
          h("b", {}, r.armor_points), h("span", { class: "faint" }, " armour + "), h("b", {}, r.shield),
          h("span", { class: "faint" }, " shield = "), h("b", { class: "or" }, r.armor_points + r.shield), h("span", { class: "faint" }, " total"));
      }
    }, 150);

    const touched = () => { if (headEl) headEl.classList.toggle("dirty", dirty()); };

    // ---------------------------------------------------------------- editor
    function renderEditor() {
      if (!draft) {
        clear(editor, h("div", { class: "empty" }, icon("dragon"), "Pick an adversary on the left, or start a new one."));
        return;
      }
      const d = draft;
      const human = d.category === "human";
      derivedEl = armourEl = null;

      const txt = (obj, f, attrs = {}) => {
        const inp = h("input", { class: "input", value: obj[f] ?? "", ...attrs });
        inp.addEventListener("input", () => { obj[f] = inp.value; touched(); });
        return inp;
      };
      const sel = (obj, f, values, onchange) => {
        const s = selectEl(values, obj[f]);
        s.onchange = () => { obj[f] = s.value; touched(); onchange?.(); };
        return s;
      };
      const fld = (label, input, cls = "") => h("label", { class: `field ${cls}` }, h("span", {}, label), input);

      nameInput = txt(d, "name", { placeholder: d.kind === "named" ? "e.g. Sir Breuse sans Pitié" : "e.g. Bandit" });
      nameInput.addEventListener("input", () => { headTitle.textContent = nameInput.value || "New adversary"; });

      // header / save bar
      const headTitle = h("span", { class: "adv-title" }, d.name || "New adversary");
      headEl = h("div", { class: "panel adv-head sticky-bar" },
        h("div", { class: "row", style: { flex: 1, minWidth: 0 } },
          h("span", { class: `adv-badge big ${d.category !== "human" ? "cat-" + d.category : d.kind}` }, badge(d)),
          h("div", { style: { minWidth: 0 } },
            headTitle,
            h("div", { class: "faint small" }, key ? `Editing ${key}` : "Not yet saved", h("span", { class: "dirty-mark" }, " · unsaved changes"),
              hint ? h("span", { class: "adv-hint" }, " · " + hint) : null))),
        h("div", { class: "toolbar" },
          combatBtn,
          h("button", { class: "btn", onclick: revert, title: "Discard edits" }, icon("undo"), "Revert"),
          h("button", { class: "btn primary", onclick: () => save() }, icon("check"), "Save")));

      // identity
      const kindS = sel(d, "kind", ["generic", "named"], () => { renderEditor(); });
      const catS = sel(d, "category", CATS, () => { renderEditor(); recompute(); });
      const tierS = sel(d, "tier", meta.tiers.includes(d.tier) || !d.tier ? meta.tiers : [d.tier, ...meta.tiers]);
      const cultureIn = txt(d, "culture", { list: "adv-cultures", placeholder: "—" });
      const religionIn = txt(d, "religion", { list: "adv-religions", placeholder: "—" });
      const identity = h("div", { class: "panel" }, h("h3", {}, "Identity"),
        h("datalist", { id: "adv-cultures" }, meta.cultures.map((c) => h("option", { value: c }))),
        h("datalist", { id: "adv-religions" }, meta.religions.map((c) => h("option", { value: c }))),
        h("div", { class: "adv-grid id-grid" },
          fld(d.kind === "named" ? "Name" : "Type name", nameInput, "span-2"),
          fld("Kind", kindS), fld("Category", catS),
          fld("Tier", tierS), fld("Promotion title", txt(d, "promotion_title", { placeholder: "Champion" })),
          fld("Culture", cultureIn), fld("Religion", religionIn),
          fld("Description", txt(d, "description", { placeholder: "One line the GM can read out" }), "span-4")));

      // characteristics
      const charInputs = CHAR_ORDER.map((k) => {
        const inp = h("input", { class: "input num char-in", value: d.characteristics[k] ?? "", title: CHAR_FULL[k] });
        inp.addEventListener("input", () => {
          const v = inp.value.trim();
          d.characteristics[k] = /^-?\d+$/.test(v) ? Number(v) : v;
          touched(); recompute();
        });
        return fld(CHAR_FULL[k], inp);
      });
      derivedEl = h("div", { class: "derived-grid" });
      const chars = h("div", { class: "panel" },
        h("div", { class: "row panel-title-row" }, h("h3", {}, "Characteristics"), h("span", { style: { flex: 1 } }),
          h("button", { class: "btn sm", onclick: rollChars, title: "Roll for the culture (or the first culture)" }, icon("d20"), "Roll characteristics")),
        h("div", { class: "adv-grid char-grid" }, charInputs),
        human ? [h("div", { class: "section-label" }, "Derived — computed from characteristics"), derivedEl] : null);

      // creature stats
      const creature = human ? null : h("div", { class: "panel" },
        h("h3", {}, "Creature combat stats"), h("p", { class: "faint small", style: { margin: "-4px 0 10px" } }, "Printed, not derived — a creature's Hit Points, Move and armour come straight from its stat block."),
        h("div", { class: "adv-grid creature-grid" }, CREATURE_FIELDS.map(([grp, f, label]) => {
          const inp = h("input", { class: "input num", type: "number", value: d[grp][f] ?? "" });
          inp.addEventListener("input", () => { d[grp][f] = inp.value === "" ? (f === "valorous_modifier" ? "" : 0) : Number(inp.value); touched(); });
          return fld(label, inp);
        })));

      // attacks
      const atkList = h("div", { class: "atk-list" });
      const drawAttacks = () => clear(atkList, d.attacks.length ? [
        h("div", { class: "atk-row atk-headrow" }, h("span", { class: "label" }, "Weapon / attack"), h("span", { class: "label" }, "Skill"), h("span", { class: "label" }, "Damage"), h("span")),
        ...d.attacks.map((a, i) => {
          const w = h("input", { class: "input", value: a.weapon, list: "adv-weapons", placeholder: "Claws, Bite…" });
          w.addEventListener("input", () => { a.weapon = w.value; touched(); });
          const v = h("input", { class: "input num", type: "number", value: a.value });
          v.addEventListener("input", () => { a.value = Number(v.value || 0); touched(); });
          const dm = h("input", { class: "input", value: a.damage, placeholder: "4D6" });
          dm.addEventListener("input", () => { a.damage = dm.value; touched(); });
          return h("div", { class: "atk-row" }, w, v, dm,
            h("button", { class: "btn ghost sm icon", title: "Remove", onclick: () => { d.attacks.splice(i, 1); touched(); drawAttacks(); } }, icon("x")));
        })] : h("div", { class: "faint small" }, "No attacks yet."));
      drawAttacks();
      const weaponPick = h("select", { class: "input" }, h("option", { value: "" }, "Choose a weapon…"),
        Object.entries(meta.weapons).map(([w, info]) => h("option", { value: w }, `${w} (${info.skill})`)));
      const attacks = h("div", { class: "panel" }, h("h3", {}, "Attacks & weapons"),
        h("datalist", { id: "adv-weapons" }, Object.keys(meta.weapons).map((w) => h("option", { value: w }))),
        atkList,
        h("div", { class: "row", style: { marginTop: "10px" } }, weaponPick,
          h("button", { class: "btn sm", onclick: async () => {
            if (!weaponPick.value) return weaponPick.focus();
            const r = await post("/api/adversaries/weapon", { weapon: weaponPick.value, characteristics: d.characteristics });
            d.attacks.push(r.attack); touched(); drawAttacks();
          } }, icon("plus"), "Add weapon"),
          h("button", { class: "btn sm ghost", onclick: () => { d.attacks.push({ weapon: "", skill: "", value: 10, damage: "1D6" }); touched(); drawAttacks(); atkList.querySelector(".atk-row:last-child input")?.focus(); } },
            icon("plus"), "Add natural attack")));

      // armour (humans)
      let armour = null;
      if (human) {
        armourEl = h("div", { class: "armour-total" });
        const pieces = h("div", { class: "piece-grid" }, Object.entries(meta.armour_pieces).map(([p, prot]) => {
          const cb = h("input", { type: "checkbox", checked: d.armour.pieces.includes(p) });
          cb.onchange = () => {
            d.armour.pieces = Object.keys(meta.armour_pieces).filter((n) => n === p ? cb.checked : d.armour.pieces.includes(n));
            touched(); recompute();
          };
          return h("label", { class: "check piece" }, cb, p, h("span", { class: "faint" }, ` ${prot}`));
        }));
        const opt = (map, cur) => [h("option", { value: "" }, "None"), ...Object.entries(map).map(([n, p]) => h("option", { value: n, selected: n === cur }, `${n} (${p})`))];
        const helm = h("select", { class: "input" }, opt(meta.helmets, d.armour.helmet));
        helm.onchange = () => { d.armour.helmet = helm.value; touched(); recompute(); };
        const shield = h("select", { class: "input" }, opt(meta.shields, d.armour.shield));
        shield.onchange = () => { d.armour.shield = shield.value; touched(); recompute(); };
        armour = h("div", { class: "panel" }, h("h3", {}, "Armour worn"), pieces,
          h("div", { class: "adv-grid two" }, fld("Helmet", helm), fld("Shield", shield)), armourEl);
      }

      // skills / traits / passions
      const statLists = h("div", { class: "grid grid-3 stat-lists" },
        statBlock("Skills", "skill", "skills", meta.skills),
        statBlock("Traits", "trait", "traits", meta.traits, "Pairs balance to 20"),
        statBlock("Passions", "passion", "passions", meta.passions));

      // notes
      const notes = h("textarea", { class: "input", rows: 4, placeholder: "Special mechanics: regeneration, immunities, special attacks, tactics…" }, d.notes);
      notes.addEventListener("input", () => { d.notes = notes.value; touched(); });

      // auto-generate
      const gGender = selectEl(["Male", "Female"], "Male");
      const gClass = selectEl(["Random", ...meta.classes], "Random");
      const auto = h("div", { class: "panel auto-panel" },
        h("h3", {}, "Auto-generate from an NPC template"),
        h("p", { class: "faint small", style: { margin: "-4px 0 10px" } }, "Rolls a full NPC of the culture above and takes its characteristics, weapons, skills, traits and passions. Identity fields are only filled if empty."),
        h("div", { class: "row" }, fld("Gender", gGender), fld("Class", gClass),
          h("button", { class: "btn", style: { alignSelf: "flex-end" }, onclick: () => autoGen(gGender.value, gClass.value) }, icon("refresh"), "Auto-generate all")));

      clear(editor, headEl, identity, chars, creature, attacks, armour, statLists,
        h("div", { class: "panel" }, h("h3", {}, "Mechanics & notes"), notes), auto);
      touched();
    }

    function statBlock(title, kind, field, vocab, note) {
      const rows = h("div", { class: "stat-rows" });
      let before = { ...draft[field] };
      const draw = () => {
        const entries = Object.entries(draft[field]);
        clear(rows, entries.length ? entries.map(([n, v]) => {
          const nm = h("input", { class: "input", value: n });
          const val = h("input", { class: "input num", type: "number", value: v });
          nm.addEventListener("change", () => {
            const name = nm.value.trim();
            const next = {};
            for (const [k2, v2] of Object.entries(draft[field])) {
              if (k2 === n) { if (name) next[name] = v2; } else next[k2] = v2;
            }
            draft[field] = next; touched(); draw();
          });
          val.addEventListener("input", () => { draft[field][n] = Number(val.value || 0); touched(); });
          if (kind === "trait") val.addEventListener("change", balance);
          return h("div", { class: "stat-row" }, nm, val,
            h("button", { class: "btn ghost sm icon", title: "Remove", onclick: () => { delete draft[field][n]; touched(); before = { ...draft[field] }; draw(); } }, icon("x")));
        }) : h("div", { class: "faint small" }, "None."));
      };
      const balance = async () => {
        const r = await post("/api/adversaries/balance-traits", { traits: draft.traits, before });
        const changed = JSON.stringify(r.traits) !== JSON.stringify(draft.traits);
        draft.traits = r.traits; before = { ...r.traits };
        touched(); draw();
        if (changed) toast("Balanced trait pairs (each sums to 20)", "ok");
      };
      const pick = h("select", { class: "input" }, h("option", { value: "" }, `Add ${kind}…`), vocab.map((v) => h("option", { value: v }, v)));
      pick.onchange = async () => {
        if (!pick.value) return;
        const name = pick.value;
        pick.value = "";
        const r = await post("/api/adversaries/stat-value", { kind, name, current: draft[field] });
        draft[field][r.name] = r.value;
        before = { ...draft[field] };
        touched(); draw();
        toast(`Added ${r.name} ${r.value} (${r.note})`, "ok");
      };
      draw();
      return h("div", { class: "panel" }, h("div", { class: "row panel-title-row" }, h("h3", {}, title), note ? h("span", { class: "faint small" }, note) : null),
        pick, rows);
    }

    async function rollChars() {
      const r = await post("/api/adversaries/roll-characteristics", { culture: meta.cultures.includes(draft.culture) ? draft.culture : "" });
      Object.assign(draft.characteristics, r.characteristics);
      renderEditor(); recompute();
    }

    async function autoGen(gender, cls) {
      readName();
      const culture = meta.cultures.includes(draft.culture) ? draft.culture : meta.cultures[0];
      const r = await post("/api/adversaries/auto", { culture, gender, social_class: cls });
      const src = r.draft;
      Object.assign(draft, { characteristics: src.characteristics, attacks: src.attacks, skills: src.skills,
        traits: src.traits, passions: src.passions });
      if (!draft.culture) draft.culture = culture;
      if (!draft.religion) draft.religion = r.religion;
      if (!draft.description) draft.description = r.looks;
      hint = `Auto-generated from a ${culture} ${r.social_class}.`;
      renderEditor(); recompute();
    }

    // ---------------------------------------------------------------- send to combat
    const combatBtn = h("button", { class: "btn", hidden: true, title: "Add one of these to the combat in progress", onclick: async () => {
      if (!key) return toast("Save the adversary first", "err");
      if (dirty()) return toast("Save your changes first", "err");
      await post("/api/combat/add", { adversary: key });
      toast(`${key} joins the combat`, "ok");
    } }, icon("swords"), "Add to combat");

    async function refreshCombat() {
      try {
        const r = await api("/api/combat");
        combatBtn.hidden = !(r.combat && r.combat.active);
      } catch { combatBtn.hidden = true; }
    }
    ctx.onEvent((evs) => { if (evs.some((e) => e.type === "combat.started" || e.type === "combat.ended" || e.type.startsWith("meta.") || e.type.startsWith("session."))) refreshCombat(); });

    // ---------------------------------------------------------------- boot
    await refreshLibrary();
    await refreshCombat();
    renderEditor();

    const inst = {
      async show(p) {
        refreshCombat();
        if (p?.draft) {
          if (!(await guardDirty())) return;
          const d = clone(p.draft);
          d.kind = "named";
          setDraft(d, null, "Drafted from the NPC — review, pick armour, then Save.", false);
        }
      },
      onLibrary() { refreshLibrary(); },
    };
    if (handoff?.draft) await inst.show(handoff);
    else {
      const first = library.find((a) => !a.isNpc);     // open a real adversary, not a Cast NPC
      if (first) await load(first.key);
    }
    return inst;
  },
};
