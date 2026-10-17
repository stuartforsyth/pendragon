// Battle tool: launch a battle (quick or saved), resume a paused one, muster
// the conroi, then run it — Morale strip with tokens, knight chips, live
// settings, new encounters mid-battle. The turn stepper arrives in S7.
// Players roll and resolve at the table; the GM records outcomes here.

import { h, clear, api, post, icon, modal, confirmBox, toast, useCss, debounce, menu } from "../lib.js";
import { dayCard, deckPicker, outcomeChips, moraleStrip, knightChip } from "../components.js";

const SIZES = {
  fight: { label: "Fight", turns: 1, dice: "1D6+2", army: false },
  skirmish: { label: "Skirmish", turns: 3, dice: "2D6", army: false },
  clash: { label: "Clash", turns: 5, dice: "2D6+1", army: true },
  small: { label: "Small Battle", turns: 6, dice: "2D6+2", army: true },
  medium: { label: "Medium Battle", turns: 7, dice: "2D6+3", army: true },
  large: { label: "Large Battle", turns: 8, dice: "3D6", army: true },
  huge: { label: "Huge Battle", turns: 8, dice: "3D6+1", army: true },
};

const ARMY_HINT = {
  friendly: { critical: "turn 1 is a mounted charge.", success: "turn 1 is a mounted charge.", failure: "no opening charge.", fumble: "no opening charge, and the army is −5 Battle on turn 1." },
  enemy: { critical: "you hold a Force Encounter token for this day.", success: "you hold a Force Encounter token for this day.", failure: "no advantage to the enemy.", fumble: "the conroi may shrug off one Encounter's Morale loss today." },
};

const TABLE_6_2 = [
  ["Outnumber the enemy 1½:1", 2], ["Outnumber the enemy 2:1", 5], ["Outnumber the enemy 3:1", 7], ["Outnumber the enemy 5:1", 10],
  ["Outnumbered 1½:1", -2], ["Outnumbered 2:1", -5], ["Outnumbered 3:1", -7], ["Outnumbered 5:1", -10],
  ["Fighting in own Homeland", 5], ["Last Stand (not with Homeland)", 5], ["Scouts, ⅕ of KV (not with Homeland)", 5],
  ["Fatigued (forced march, hot weather)", -5], ["Disease or hunger", -5], ["Multiple fractious commanders", -5],
];

export default {
  async mount(el, ctx) {
    useCss("battle");
    let b = null, party = [], paused = [], saved = [], decks = [], session = null;
    const quick = { size: "clash", days: 1, name: "", where: "", against: "", notes: "", more: false };
    const muster = { knights: null, commander: null, start: "", passion: "" };
    const body = h("div");
    clear(el, body);

    async function load() {
      const [bb, pp, ps, sv, dk, ss] = await Promise.all([
        api("/api/battle"), api("/api/party"), api("/api/battle/paused"), api("/api/battles"),
        api("/api/battle-decks"), api("/api/session")]);
      b = bb.battle; party = pp.party; paused = ps.paused; saved = sv.battles; decks = dk.cards; session = ss.session;
      render();
    }

    function render() {
      if (el.querySelector(".bl input:focus, .bl textarea:focus")) return;
      const live = b && ["mustering", "turn", "rear"].includes(b.status);
      clear(body, h("div", { class: "bl" }, !live ? launchPanel() : b.status === "mustering" ? mustering() : running()));
    }

    // ------------------------------------------------------------ idle: launch
    function launchPanel() {
      const here = b && b.status === "paused" ? [{ battle_id: b.id, session_id: session.id, session_title: "this session",
        name: b.definition.name, day: b.day, turn: b.turn, morale: b.morale ? [b.morale.current, b.morale.start] : null }] : [];
      const rows = [...here, ...paused];
      const S = SIZES[quick.size];
      return [
        h("div", { class: "tool-head" }, h("div", {}, h("h1", {}, "Battle"),
          h("p", { class: "lede" }, "Launch a battle — Size is all it needs — or resume one paused at the end of a session."))),
        rows.length ? h("div", { class: "panel" }, h("h3", {}, "Paused battles"),
          rows.map((p) => h("div", { class: "bl-row" },
            h("span", {}, h("b", {}, p.name), ` · Day ${p.day} · Turn ${p.turn}`, p.morale ? ` · Morale ${p.morale[0]} / ${p.morale[1]}` : "",
              h("span", { class: "faint small" }, ` · ${p.session_title}`)),
            h("button", { class: "btn primary sm", onclick: () => post("/api/battle/resume", { battle_id: p.battle_id, session_id: p.session_id }) }, icon("play"), "Resume")))) : null,
        h("div", { class: "split bl-split" },
          h("div", { class: "panel" }, h("h3", {}, "Quick battle"),
            h("div", { class: "chips bl-sizes" }, Object.entries(SIZES).map(([k, s]) => h("button", { class: `chip ${quick.size === k ? "on" : ""}`,
              onclick: () => { quick.size = k; render(); } }, s.label))),
            h("div", { class: "faint small" }, `${S.label} · up to ${S.turns} turn${S.turns === 1 ? "" : "s"} · Intensity ${S.dice}`),
            h("div", { class: "row", style: { marginTop: "10px", flexWrap: "wrap" } },
              h("label", { class: "field" }, h("span", {}, "Days"),
                h("input", { class: "input num", type: "number", min: 1, max: 7, value: quick.days, oninput: (e) => { quick.days = Math.max(1, Math.min(7, Number(e.target.value) || 1)); } })),
              h("label", { class: "field", style: { flex: 1 } }, h("span", {}, "Name (optional)"),
                h("input", { class: "input", value: quick.name, placeholder: `A ${S.label}`, oninput: (e) => { quick.name = e.target.value; } }))),
            h("details", { open: quick.more || null, ontoggle: (e) => { quick.more = e.target.open; } }, h("summary", { class: "faint small" }, "Add flavour — where, against, notes"),
              h("div", { class: "stack", style: { marginTop: "8px" } },
                h("input", { class: "input", placeholder: "Where — e.g. the ford at Bedegraine", value: quick.where, oninput: (e) => { quick.where = e.target.value; } }),
                h("input", { class: "input", placeholder: "Against — e.g. King Lot and the northern kings", value: quick.against, oninput: (e) => { quick.against = e.target.value; } }),
                h("textarea", { class: "input", rows: 2, placeholder: "Notes to read out", oninput: (e) => { quick.notes = e.target.value; } }, quick.notes))),
            h("button", { class: "btn primary", style: { marginTop: "12px" }, onclick: () => post("/api/battle/start", { quick: { ...quick } }) }, icon("banner"), "Launch battle")),
          h("div", { class: "panel" }, h("h3", {}, "Saved battles"),
            saved.length ? h("div", { class: "list" }, saved.map((s) => h("div", { class: "list-item bl-saved" },
              h("span", {}, h("b", {}, s.key), h("span", { class: "faint small" }, ` · ${SIZES[s.size]?.label || s.size} · ${s.days} day${s.days === 1 ? "" : "s"}`)),
              h("button", { class: "btn sm", onclick: () => post("/api/battle/start", { key: s.key }) }, icon("play"), "Launch"))))
              : h("p", { class: "faint" }, "Prepare battles in the Battles tool."))),
      ];
    }

    // ------------------------------------------------------------ mustering
    function mustering() {
      const S = SIZES[b.definition.size];
      const day = b.day, days = b.days, dd = b.day_def;
      const active = party.filter((m) => m.active !== false || b.conroi.includes(m.id));
      if (!muster.knights) muster.knights = b.conroi.length ? [...b.conroi] : active.map((m) => m.id);
      if (muster.commander === null) muster.commander = b.commander || b.definition.commander || null;
      if (muster.start === "" && b.morale) muster.start = b.morale.start;
      const reason = !muster.commander ? "Set a commander" : !(Number(muster.start) >= 1) ? "Enter the starting Morale"
        : b.intensity_today == null && dd.intensity?.mode !== "fixed" ? "Set today's Intensity" : "";
      const begin = async () => {
        if (reason) return toast(reason, "err");
        await post("/api/battle/muster", { start: Number(muster.start), passion: muster.passion, commander: muster.commander, knights: muster.knights });
        Object.assign(muster, { knights: null, commander: null, start: "", passion: "" });
      };
      const conroi = h("div", { class: "panel" }, h("h3", {}, "The conroi"),
        active.map((m) => {
          const k = b.knights[m.id] || { mounted: true };
          const on = muster.knights.includes(m.id);
          return h("div", { class: "kchk" },
            h("label", { class: "check" }, h("input", { type: "checkbox", checked: on, onchange: (e) => {
              muster.knights = e.target.checked ? [...muster.knights, m.id] : muster.knights.filter((x) => x !== m.id);
              if (!e.target.checked && muster.commander === m.id) muster.commander = null;
              render(); } }), icon("shield"), m.name),
            b.knights[m.id] ? h("button", { class: `pill-mounted ${k.mounted ? "on" : ""}`, onclick: () => post(`/api/battle/knight/${m.id}`, { mounted: !k.mounted }) }, k.mounted ? "Mounted" : "On foot") : null);
        }),
        h("div", { class: "label", style: { marginTop: "8px" } }, "Commander"),
        h("div", { class: "chips" },
          [...active.filter((m) => muster.knights.includes(m.id)).map((m) => [m.id, m.name]), ["gm", "GM (NPC)"]].map(([id, name]) =>
            h("button", { class: `chip ${muster.commander === id ? "on" : ""}`, onclick: () => { muster.commander = id; render(); } }, name))),
        h("div", { class: "row", style: { alignItems: "flex-end", marginTop: "8px" } },
          h("label", { class: "field" }, h("span", {}, "Starting Morale"),
            h("input", { class: "input big-num", type: "number", min: 1, value: muster.start, oninput: (e) => { muster.start = e.target.value; },
              onchange: () => render(), onkeydown: (e) => e.key === "Enter" && begin() })),
          h("label", { class: "field", style: { flex: 1 } }, h("span", {}, "Passion (optional)"),
            h("input", { class: "input", value: muster.passion, placeholder: "e.g. Loyalty (King)", oninput: (e) => { muster.passion = e.target.value; } }))),
        h("p", { class: "faint small" }, "The players work Morale out at the table: the average of their Passion, +5 if they all chose the same one."));

      const army = S.army ? h("div", { class: "panel" }, h("h3", {}, "Army commanders ", h("span", { class: "faint small" }, "Clash and larger")),
        ["friendly", "enemy"].map((side) => {
          const ac = b.definition.army_commanders?.[side] || {};
          const got = b.army[String(day)]?.[side] || null;
          return h("div", { class: "army-row" },
            h("div", { class: "label" }, `${ac.name || (side === "friendly" ? "Friendly" : "Enemy")} (${side})`),
            h("div", { class: "row" }, outcomeChips({ value: got || dd.commanders?.[side] || null,
              onPick: (o) => post("/api/battle/army-roll", { side, outcome: o }) }),
              h("button", { class: "btn ghost sm", onclick: () => rollForMe(side, ac) }, "roll for me")),
            h("div", { class: "faint small" }, got ? `${got[0].toUpperCase() + got.slice(1)} → ${ARMY_HINT[side][got]}`
              : dd.commanders?.[side] ? `Preset: ${dd.commanders[side]} (recorded when you begin)` : "Not rolled yet"));
        }),
        h("details", {}, h("summary", { class: "faint small" }, "Table 6.2 modifiers"),
          h("ul", { class: "t62" }, TABLE_6_2.map(([l, m]) => h("li", {}, `${l}: ${m > 0 ? "+" : ""}${m}`))))) : null;

      const fixed = dd.intensity?.mode === "fixed";
      const intensity = h("div", { class: "panel" }, h("h3", {}, `Day ${day} Intensity`),
        h("div", { class: "row" },
          h("input", { class: "input num", type: "number", min: 1, max: 40, value: b.intensity_today ?? (fixed ? dd.intensity.value : ""),
            onchange: (e) => e.target.value && post("/api/battle/day", { intensity: Number(e.target.value) }) }),
          fixed && b.intensity_today == null ? h("span", { class: "faint small" }, "fixed by the saved battle")
            : h("button", { class: "btn sm", onclick: () => post("/api/battle/day", { roll_for_me: true }) }, icon("d6"), `Roll for me (${S.dice})`)));

      return [
        h("div", { class: "bhead" }, h("span", { class: "bl-title" }, b.definition.name || "Battle"),
          h("span", { class: "faint" }, `${day > 1 ? "Re-muster" : "Mustering"} · Day ${day} of ${days} · ${S.label} · ${b.turns_today} turns · first charge ${b.first_charge ? "on" : "off"}`),
          h("span", { class: "sp" }, h("button", { class: "btn ghost sm", onclick: settingsDrawer }, "Battle settings"),
            h("button", { class: "btn ghost sm", onclick: pause }, "Pause"))),
        h("div", { class: "grid2" }, conroi, h("div", { class: "stack" }, army, intensity)),
        h("div", { class: "row" }, h("button", { class: "btn primary", disabled: !!reason || null, onclick: begin }, day > 1 ? `Begin Day ${day} ▸` : "Begin Turn 1 ▸"),
          h("span", { class: "faint small" }, reason || "Ready: commander and Morale are set.")),
      ];
    }

    async function rollForMe(side, ac) {
      await modal(`Roll for ${ac.name || side}`, (close) => {
        const val = h("input", { class: "input num", type: "number", value: ac.battle ?? "", placeholder: "2D6+10" });
        let mods = 0;
        const sum = h("b", {}, "+0");
        const ticks = TABLE_6_2.map(([l, m]) => h("label", { class: "check small" }, h("input", { type: "checkbox", onchange: (e) => {
          mods += e.target.checked ? m : -m; sum.textContent = `${mods >= 0 ? "+" : ""}${mods}`; } }), `${l} (${m > 0 ? "+" : ""}${m})`));
        return [h("label", { class: "field" }, h("span", {}, "Battle skill (blank = roll 2D6+10)"), val),
          h("div", { class: "t62 stack" }, ticks), h("div", {}, "Modifiers: ", sum),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: async () => {
              await post("/api/battle/army-roll", { side, roll_for_me: { battle: val.value === "" ? null : Number(val.value), mods } }); close(); } }, icon("d20"), "Roll"))];
      });
    }

    // ------------------------------------------------------------ running
    function running() {
      const S = SIZES[b.definition.size];
      return [
        h("div", { class: "bhead" }, h("span", { class: "bl-title" }, b.definition.name || "Battle"),
          h("span", { class: "faint" }, `Day ${b.day} · Turn ${b.turn} of ${b.turns_today} · Intensity ${b.intensity_today ?? "—"} · ${S.label}`),
          h("span", { class: "sp" },
            h("button", { class: "btn ghost sm", onclick: quickEncounter }, icon("plus"), "New encounter"),
            h("button", { class: "btn ghost sm", onclick: settingsDrawer }, "Battle settings"),
            h("button", { class: "btn ghost sm", onclick: saveTemplate }, "Save as template"),
            h("button", { class: "btn ghost sm", onclick: pause }, "Pause"))),
        moraleStrip(b, { onAdjust: adjustMorale, onCommander: changeCommander }),
        h("div", { class: "kchips" }, b.knight_list.filter((k) => b.conroi.includes(k.pid)).map((k) =>
          knightChip(k, { onMounted: () => post(`/api/battle/knight/${k.pid}`, { mounted: !k.mounted }) }))),
        b.minus5 && b.turn === 1 ? h("div", { class: "bl-reminder" }, "−5 Battle this turn for the whole army (Army Commander fumbled).") : null,
        scriptsPanel(),
        h("div", { class: "panel bl-stepper-soon" }, h("p", { class: "faint" }, "The turn stepper arrives in the next build. Use the Combat tool for this turn's fight.")),
      ];
    }

    function scriptsPanel() {
      const sc = (b.day_def.scripts || []).map((s, i) => ({ ...s, i })).filter((s) => s.turn === b.turn);
      if (!sc.length) return null;
      const shown = (i) => b.revealed_scripts.some((r) => r.day === b.day && r.index === i);
      return h("div", { class: "panel bl-scripts" }, h("h3", {}, `Turn ${b.turn} script (GM only)`),
        sc.map((s) => h("div", { class: "bl-script" }, h("span", {}, s.text, s.if_intensity ? h("span", { class: "faint small" }, " — only if Intensity succeeds") : null),
          !s.if_intensity ? h("button", { class: "btn ghost sm", disabled: shown(s.i) || null,
            onclick: () => post("/api/battle/script", { day: b.day, index: s.i }) }, shown(s.i) ? "On the Table" : "Show on Table") : null)));
    }

    async function adjustMorale() {
      await modal("Adjust Morale", (close) => {
        const d = h("input", { class: "input num", type: "number", placeholder: "+2 / −3" });
        const st = h("input", { class: "input num", type: "number", placeholder: String(b.morale.start) });
        const why = h("input", { class: "input", placeholder: "Why — e.g. rallying cry" });
        const note = h("div", { class: "faint small" });
        d.addEventListener("input", () => {
          const v = Number(d.value) || 0, after = Math.max(0, Math.min(b.morale.start, b.morale.current + v));
          note.textContent = v ? `${b.morale.current} → ${after}${after !== b.morale.current + v ? ` (capped at ${b.morale.start})` : ""}` : "";
        });
        const go = async () => {
          if (!why.value.trim()) return toast("Say why Morale changes", "err");
          if (st.value) await post("/api/battle/morale", { start: Number(st.value), reason: why.value });
          else if (d.value) await post("/api/battle/morale", { delta: Number(d.value), reason: why.value });
          close();
        };
        why.addEventListener("keydown", (e) => e.key === "Enter" && go());
        return [h("div", { class: "row" }, h("label", { class: "field" }, h("span", {}, "Change"), d),
          h("label", { class: "field" }, h("span", {}, "or new starting Morale"), st)), note,
          h("label", { class: "field" }, h("span", {}, "Reason (logged)"), why),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"), h("button", { class: "btn primary", onclick: go }, "Apply"))];
      });
    }

    function changeCommander(anchor) {
      const ks = b.knight_list.filter((k) => b.conroi.includes(k.pid));
      menu(anchor, [...ks.map((k) => [k.name, () => post("/api/battle/commander", { commander: k.pid })]), ["GM (NPC)", () => post("/api/battle/commander", { commander: "gm" })]]);
    }

    async function pause() {
      if (await confirmBox("Pause the battle?", "Resume it later — in this session or the next — from the Battle tool.", "Pause")) await post("/api/battle/pause");
    }

    async function saveTemplate() {
      await modal("Save as template", (close) => {
        const n = h("input", { class: "input", value: b.definition.name || "" });
        const go = async (overwrite = false) => {
          try { await post("/api/battle/template", { name: n.value, overwrite }, { quiet: [409] }); toast("Saved to Battles", "ok"); close(); }
          catch (e) { if (e.status === 409 && await confirmBox("Overwrite?", `A battle named “${n.value}” exists. Replace it?`, "Overwrite", true)) go(true); }
        };
        return [h("label", { class: "field" }, h("span", {}, "Name"), n), h("p", { class: "faint small" }, "Saves the days, decks, scripts and flavour — not where this battle has got to."),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"), h("button", { class: "btn primary", onclick: () => go() }, "Save"))];
      });
    }

    // Live settings: today and later days are editable; past days are locked.
    async function settingsDrawer() {
      const edits = {};
      await modal("Battle settings", (close) => [
        h("div", { class: "stack" }, b.definition.days.map((day, i) => {
          const n = i + 1, past = n < b.day;
          return h("div", {}, h("div", { class: "label" }, `Day ${n}`, past ? " (past days are locked)" : ""),
            dayCard(day, b.definition.size, { readOnly: past, decks, label: `Day ${n}`, onChange: (d) => { edits[n] = d; } }));
        })),
        h("div", { class: "foot" },
          h("button", { class: "btn", onclick: async () => { await post("/api/battle/settings", { add_day: { turns: SIZES[b.definition.size].turns } }); close(); settingsDrawer(); } }, icon("plus"), "Add day"),
          h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
          h("button", { class: "btn primary", onclick: async () => {
            for (const [n, d] of Object.entries(edits)) {
              const old = b.definition.days[n - 1];
              const deckChanged = JSON.stringify(old.deck) !== JSON.stringify(d.deck);
              const patch = {};
              for (const k of ["intensity", "turns", "first_charge", "on_foot", "no_charge", "commanders", "notes", "scripts"])
                if (JSON.stringify(old[k]) !== JSON.stringify(d[k])) patch[k] = d[k];
              if (Object.keys(patch).length) await post("/api/battle/settings", { day: Number(n), patch });
              if (deckChanged) {
                const before = new Set([...old.deck.foes, ...old.deck.opportunities]), after = new Set([...d.deck.foes, ...d.deck.opportunities]);
                const add = [...after].filter((k) => !before.has(k)), remove = [...before].filter((k) => !after.has(k));
                if (add.length || remove.length) await post("/api/battle/deck", { day: Number(n), add, remove });
              }
            }
            close();
          } }, "Save")),
      ], { wide: true });
    }

    // + New encounter: saved to the library and added to today's deck.
    async function quickEncounter() {
      const advs = (await api("/api/adversaries")).adversaries;
      await modal("New encounter", (close) => {
        const d = { name: "", battle_role: "foe", description: "", roster: [{ adversary: "", count: 1, per_player: true }], morale_minimum: "", morale_loss: "", missile: false, rules: "" };
        const rosterEl = h("div", { class: "stack" });
        const drawRoster = () => clear(rosterEl, d.roster.map((ln, i) => h("div", { class: "row" },
          h("select", { class: "input", onchange: (e) => { ln.adversary = e.target.value; } }, h("option", { value: "" }, "Choose a foe…"),
            advs.map((a) => h("option", { value: a.key, selected: a.key === ln.adversary }, a.key))),
          h("input", { class: "input num", type: "number", step: "0.5", value: ln.count, oninput: (e) => { ln.count = Number(e.target.value) || 1; } }),
          h("label", { class: "check small" }, h("input", { type: "checkbox", checked: ln.per_player, onchange: (e) => { ln.per_player = e.target.checked; } }), "per knight"),
          h("button", { class: "btn ghost sm icon", onclick: () => { d.roster.splice(i, 1); drawRoster(); } }, icon("x")))));
        drawRoster();
        const role = h("div", { class: "chips" });
        const drawRole = () => clear(role, [["foe", "Foe"], ["opportunity", "Opportunity ★"]].map(([r, l]) =>
          h("button", { class: `chip ${d.battle_role === r ? "on" : ""}`, onclick: () => { d.battle_role = r; drawRole(); } }, l)));
        drawRole();
        const save = async () => {
          if (!d.name.trim()) return toast("Name the encounter", "err");
          const def = { ...d, roster: d.roster.filter((x) => x.adversary), morale_minimum: d.morale_minimum === "" ? null : Number(d.morale_minimum) };
          await post("/api/battle/quick-encounter", { definition: def });
          close();
        };
        return [
          h("label", { class: "field" }, h("span", {}, "Name"), h("input", { class: "input", oninput: (e) => { d.name = e.target.value; } })),
          role,
          h("label", { class: "field" }, h("span", {}, "Description (read on the Table)"), h("input", { class: "input", oninput: (e) => { d.description = e.target.value; } })),
          h("div", { class: "label" }, "Foes"), rosterEl,
          h("button", { class: "btn sm", onclick: () => { d.roster.push({ adversary: "", count: 1, per_player: true }); drawRoster(); } }, icon("plus"), "Add a line"),
          h("div", { class: "row" },
            h("label", { class: "field" }, h("span", {}, "Minimum Morale"), h("input", { class: "input num", type: "number", oninput: (e) => { d.morale_minimum = e.target.value; } })),
            h("label", { class: "field" }, h("span", {}, "Morale Loss"), h("input", { class: "input", placeholder: "1D6", oninput: (e) => { d.morale_loss = e.target.value; } }))),
          h("label", { class: "field" }, h("span", {}, "Rules / rewards (Opportunity)"), h("textarea", { class: "input", rows: 2, oninput: (e) => { d.rules = e.target.value; } })),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: save }, "Save & add to today's deck")),
        ];
      }, { wide: true });
    }

    // ------------------------------------------------------------ wiring
    const loadSoon = debounce(load, 60);
    ctx.onEvent((evs, { reset }) => {
      if (reset || evs.some((e) => e.type.startsWith("battle.") || e.type.startsWith("meta.") || e.type.startsWith("session."))) loadSoon();
    });
    el.addEventListener("focusout", () => setTimeout(render, 0));
    await load();
    return { async show() { await load(); }, async onLibrary() { await load(); } };
  },
};
