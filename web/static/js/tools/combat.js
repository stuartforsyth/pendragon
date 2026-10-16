// Combat tracker: launch an encounter (the Party joins automatically), then
// run it — HP, wounds, engagements, situational modifiers, click-to-roll,
// promotion, surrender and ransom. Every change is an event; strike one in the
// log to undo it.

import { h, clear, api, post, icon, menu, modal, toast, useCss, confirmBox, skillDisplay,
  CHAR_FULL, CHAR_ORDER, debounce } from "../lib.js";

export default {
  async mount(el, ctx) {
    useCss("combat");
    let cs = null;             // GM view of the combat
    let encounters = [], advs = [], party = [];
    let pending = false;       // a re-render waiting for an input to lose focus
    let launchQuery = "", selected = "", players = null, includeParty = true;
    const descOpen = { v: true };

    const body = h("div");
    clear(el, body);

    async function loadLibrary() {
      [encounters, advs, party] = await Promise.all([
        api("/api/encounters").then((r) => r.encounters),
        api("/api/adversaries").then((r) => r.adversaries),
        api("/api/party").then((r) => r.party),
      ]);
    }

    async function refresh() {
      cs = (await api("/api/combat")).combat;
      render();
    }

    function render() {
      if (el.querySelector(".cbt-row input:focus, .cbt-head input:focus")) { pending = true; return; }
      pending = false;
      clear(body, cs && cs.active ? running() : launcher());
    }
    el.addEventListener("focusout", () => setTimeout(() => pending && render(), 0));

    // ------------------------------------------------------------ launcher
    function launcher() {
      const activeParty = party.filter((m) => m.active !== false);
      const n = players ?? (activeParty.length || 4);
      const list = h("div", { class: "list list-scroll" });
      const drawList = () => {
        const q = launchQuery.toLowerCase();
        const hits = encounters.filter((e) => !q || `${e.key} ${e.description} ${e.tags.join(" ")} ${e.adversaries.join(" ")}`.toLowerCase().includes(q));
        if (hits.length === 1) selected = hits[0].key;
        clear(list, hits.length ? hits.map((e) => h("div", { class: `list-item ${e.key === selected ? "on" : ""}`,
          onclick: () => { selected = e.key; drawList(); }, ondblclick: () => launch(e.key) },
          h("div", { style: { minWidth: 0 } }, h("div", { class: "enc-name" }, e.key),
            e.description ? h("div", { class: "faint small enc-desc" }, e.description) : null),
          h("span", { class: "meta" }, `${e.lines} line${e.lines === 1 ? "" : "s"}`)))
          : h("div", { class: "faint", style: { padding: "10px" } }, "No encounters match."));
      };
      drawList();
      const search = h("input", { class: "input", placeholder: "Search encounters, foes, tags…", value: launchQuery,
        oninput: (e) => { launchQuery = e.target.value; selected = ""; drawList(); },
        onkeydown: (e) => e.key === "Enter" && launch() });
      const nIn = h("input", { class: "input num", type: "number", min: 1, max: 20, value: n,
        oninput: (e) => { players = Number(e.target.value) || null; } });
      setTimeout(() => search.focus(), 0);
      return [
        h("div", { class: "tool-head" }, h("div", {}, h("h1", {}, "Combat"),
          h("p", { class: "lede" }, "Launch an encounter — the battle board appears on the Table automatically."))),
        h("div", { class: "split" },
          h("div", { class: "panel" },
            h("h3", {}, "Launch"),
            h("div", { class: "stack" },
              h("label", { class: "field" }, h("span", {}, "Players"), h("div", { class: "row" }, nIn,
                h("span", { class: "faint small" }, activeParty.length ? `${activeParty.length} active knight${activeParty.length === 1 ? "" : "s"} in the Party` : "No Party yet — add knights under Party"))),
              h("label", { class: "check" }, h("input", { type: "checkbox", checked: includeParty, onchange: (e) => { includeParty = e.target.checked; } }),
                "Knights join the fight"),
              h("button", { class: "btn primary", onclick: () => launch() }, icon("swords"), "Launch encounter"),
              h("div", { class: "faint small" }, "Build new encounters in the Encounter Creator."))),
          h("div", { class: "panel" }, h("h3", {}, "Encounters"), search, h("div", { style: { height: "8px" } }), list)),
        cs && !cs.active ? h("div", { class: "panel", style: { marginTop: "14px" } },
          h("h3", {}, "Last combat"), h("p", { class: "muted", style: { margin: 0 } },
            `${cs.name} ended after ${cs.round} round${cs.round === 1 ? "" : "s"} — `,
            `${cs.combatants.filter((c) => c.side !== "party" && c.down).length} of ${cs.combatants.filter((c) => c.side !== "party").length} foes down.`)) : null,
      ];
    }

    async function launch(key = selected) {
      if (!key) return toast("Search, then pick an encounter to launch", "err");
      const activeParty = party.filter((m) => m.active !== false);
      await post("/api/combat/start", { encounter: key, players: players ?? (activeParty.length || 4), include_party: includeParty });
    }

    // ------------------------------------------------------------ running
    function running() {
      const knights = cs.combatants.filter((c) => c.side === "party");
      const foes = cs.combatants.filter((c) => c.side !== "party");
      const up = foes.filter((c) => !c.down).length;
      const note = h("input", { class: "input", placeholder: "Round note — e.g. the bridge collapses", style: { flex: 1 },
        onkeydown: async (e) => { if (e.key === "Enter" && e.target.value.trim()) { await post("/api/combat/note", { text: e.target.value }); e.target.value = ""; } } });
      const availableKnights = party.filter((m) => !cs.combatants.some((c) => c.party_id === m.id));
      return [
        h("div", { class: "cbt-head sticky-bar" },
          h("div", { class: "row", style: { alignItems: "flex-end" } },
            h("div", { style: { minWidth: 0, flex: 1 } },
              h("div", { class: "label" }, "In combat"),
              h("h1", { class: "cbt-title" }, cs.name)),
            h("div", { class: "round-box" }, h("span", { class: "label" }, "Round"), h("span", { class: "round-n" }, cs.round)),
            h("button", { class: "btn primary", onclick: () => post("/api/combat/round") }, icon("hourglass"), "Next round"),
            h("button", { class: "btn", onclick: (e) => addMenu(e.currentTarget, availableKnights) }, icon("plus"), "Add"),
            h("button", { class: "btn danger", onclick: endCombat }, icon("flag"), "End")),
          h("div", { class: "row", style: { marginTop: "10px" } },
            h("span", { class: "tag gules" }, `${up} of ${foes.length} foes standing`),
            knights.length ? h("span", { class: "tag azure" }, `${knights.filter((k) => !k.down).length} of ${knights.length} knights standing`) : null,
            note)),
        descriptions(),
        knights.length ? [h("div", { class: "section-label" }, "The Knights"), h("div", { class: "cbt-list" }, knights.map(row))] : null,
        h("div", { class: "section-label" }, "The Foe"),
        h("div", { class: "cbt-list" }, foes.length ? foes.map(row) : h("div", { class: "empty" }, "No foes — add some.")),
        h("div", { class: "cbt-help faint small" },
          "Click an enemy's weapon skill to attack a knight: the app rolls it, you click the knight's result, and if the enemy hits its damage is rolled and applied (Table 7.1). ",
          "When a knight hits an enemy, press Hit and enter the damage the player rolled — armour comes off automatically. Click any other value to roll it. ",
          "Apply is for plain HP changes (healing, a fall). Mod: a situational modifier on every characteristic and skill roll (not damage). Strike any log entry to undo it."),
      ];
    }

    function descriptions() {
      const d = cs.descriptions || [];
      if (!d.length) return null;
      return h("details", { class: "panel cbt-desc", open: descOpen.v, ontoggle: (e) => { descOpen.v = e.target.open; } },
        h("summary", {}, "Descriptions & mechanics"),
        h("div", { class: "stack", style: { marginTop: "8px" } }, d.map((x) =>
          h("div", {}, h("b", { class: x.type === "GM notes" ? "gm-notes" : "" }, x.type), " — ", h("span", { class: "muted" }, x.text)))));
    }

    function addMenu(anchor, knights) {
      const items = knights.map((m) => [`${m.name} (knight)`, () => post("/api/combat/add-party", { member_id: m.id }), { icon: "party" }]);
      if (items.length) items.push(null);
      items.push(["An adversary…", pickAdversary, { icon: "dragon" }]);
      menu(anchor, items);
    }

    async function pickAdversary() {
      const { modal } = await import("../lib.js");
      await modal("Add a combatant", (close) => {
        const list = h("div", { class: "list", style: { maxHeight: "50vh", overflow: "auto" } });
        const draw = (q = "") => clear(list, advs.filter((a) => `${a.key} ${a.category} ${a.tier}`.toLowerCase().includes(q.toLowerCase())).slice(0, 80)
          .map((a) => h("div", { class: "list-item", onclick: async () => { await post("/api/combat/add", { adversary: a.key }); close(); } },
            h("span", {}, a.key), h("span", { class: "meta" }, `${a.category}${a.tier ? " · " + a.tier : ""} · HP ${a.hp ?? "?"}`))));
        const search = h("input", { class: "input", placeholder: "Search adversaries…", oninput: (e) => draw(e.target.value) });
        draw();
        return [search, h("div", { style: { height: "8px" } }), list];
      });
    }

    async function endCombat() {
      if (await confirmBox("End combat?", "The Table returns to the Chronicle. Knights' Hit Points are saved back to the Party.", "End combat")) {
        await post("/api/combat/end");
      }
    }

    // ------------------------------------------------------------ a combatant row
    const STATUS_TAG = { active: null, unconscious: ["Unconscious", "purpure"], dead: ["Slain", "gules"], fled: ["Fled — not tracked", ""] };

    function row(c) {
      const isKnight = c.side === "party";
      const creature = ["beast", "monster", "fae"].includes(c.category);
      const marker = (c.elite ? "★" : "") + (c.named && !isKnight ? "◆" : "") + (creature && !c.named ? "✦" : "");
      const tone = c.down ? "down" : c.elite ? "elite" : isKnight ? "knight" : c.named ? "named" : c.category;
      const st = STATUS_TAG[c.status];
      const pct = Math.max(0, Math.min(100, (c.cur_hp / c.max_hp) * 100));

      const hpIn = h("input", { class: "input num hp-in", placeholder: "±HP", title: "Damage as negative, healing as positive — Enter",
        onkeydown: (e) => { if (e.key === "Enter") applyHp(c, e.target); } });
      const modIn = h("input", { class: `input num mod-in ${c.modifier < 0 ? "neg" : c.modifier > 0 ? "pos" : ""}`, value: c.modifier ? (c.modifier > 0 ? `+${c.modifier}` : c.modifier) : "0",
        title: "Situational modifier — Enter",
        onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); },
        onchange: (e) => post(`/api/combat/${c.id}/modifier`, { value: e.target.value.trim() || 0 }) });
      const engIn = engageSelect(c);

      return h("div", { class: `cbt-row t-${tone} ${c.down ? "is-down" : ""}`, "data-id": c.id },
        h("div", { class: "cbt-line" },
          h("div", { class: "cbt-name" }, marker ? h("span", { class: "marker" }, marker + " ") : null, c.display_name,
            st ? h("span", { class: `tag ${st[1]}`, style: { marginLeft: "8px" } }, st[0]) : null),
          h("div", { class: "cbt-eng" }, h("span", { class: "faint small" }, "fighting"), engIn),
          h("div", { class: "cbt-hp" },
            h("div", { class: "hp-text" }, h("b", {}, c.cur_hp), h("span", { class: "faint" }, ` / ${c.max_hp}`), h("span", { class: "faint small" }, " HP"),
              !isKnight ? h("span", { class: "faint small ws" }, ` · ${c.wound_state}`) : null),
            h("div", { class: "hp-bar" }, h("i", { style: { width: `${pct}%` } }))),
          !isKnight ? h("button", { class: "btn sm hit-btn", title: `A knight hit ${c.display_name}: enter the damage rolled`,
            onclick: () => hitDialog(c) }, icon("swords"), "Hit") : null,
          hpIn,
          h("button", { class: "btn sm", title: "Apply a plain HP change (healing, a fall…)", onclick: () => applyHp(c, hpIn) }, "Apply"),
          h("div", { class: "cbt-mod" }, h("span", { class: "faint small" }, "Mod"), modIn),
          h("button", { class: "btn sm icon", title: "Actions", onclick: (e) => actions(e.currentTarget, c) }, icon("dots"))),
        statLine(c, isKnight),
        c.engaged_by?.length ? h("div", { class: "cbt-engby" }, icon("swords"), " Fought by ", c.engaged_by.join(", ")) : null,
        flavour(c));
    }

    // Who a combatant can be set to fight: foes pick from the knights, knights
    // from the foes (anyone else stays reachable through "Other…").
    function engageSelect(c) {
      const others = cs.combatants.filter((o) => o.id !== c.id && o.side !== c.side && o.status !== "dead");
      const names = others.map((o) => o.display_name);
      const cur = c.engaged_with || "";
      const sel = h("select", { class: `input eng-in ${cur ? "set" : ""}`, title: "Who is this combatant fighting?",
        onchange: async (e) => {
          let v = e.target.value;
          if (v === "__other") {
            v = await modal("Fighting whom?", (close) => {
              const inp = h("input", { class: "input", value: cur, onkeydown: (ev) => ev.key === "Enter" && close(inp.value) });
              return [inp, h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
                h("button", { class: "btn primary", onclick: () => close(inp.value) }, "Set"))];
            });
            if (v === undefined) { e.target.value = cur; return; }
          }
          await post(`/api/combat/${c.id}/engage`, { with: v });
        } },
        h("option", { value: "" }, "— nobody —"),
        names.map((n) => h("option", { value: n, selected: n === cur }, n)),
        cur && !names.includes(cur) ? h("option", { value: cur, selected: true }, cur) : null,
        h("option", { value: "__other" }, "Other…"));
      return sel;
    }

    const byName = (n) => cs.combatants.find((o) => o.display_name === n);

    // ------------------------------------------------------------ an enemy attacks a knight
    // Core p.133 Table 7.1: roll the enemy's attack, then the GM clicks the
    // knight's result; the app decides whether the enemy's blow lands.
    const OUT = { critical: "Critical", success: "Success", failure: "Failure", fumble: "Fumble" };

    async function attackDialog(c, i) {
      const knights = cs.combatants.filter((o) => o.side === "party" && !o.down);
      if (!knights.length) return toast("No knights in the fight", "err");
      let target = (byName(c.engaged_with)?.side === "party" ? byName(c.engaged_with) : knights[0]).id;
      const roll = (await post(`/api/combat/${c.id}/roll`, { what: "attack", key: i })).event;
      ctx.showLastRoll(roll);
      const d = roll.data, ok = d.outcome === "critical" || d.outcome === "success";
      const go = async (knight, close) => {
        const r = await post("/api/combat/attack", { event: roll.id, target, knight });
        if (r.blow) ctx.showLastRoll(r.blow);
        toast(r.event.data.verdict, "ok");
        close();
      };
      await modal(`${c.display_name} attacks`, (close) => [
        h("div", { class: "attack-roll" }, `${d.label} ${d.shown}: rolled `, h("b", {}, d.roll), " — ",
          h("b", { class: `o-${d.outcome}` }, OUT[d.outcome])),
        h("label", { class: "field", style: { margin: "12px 0" } }, h("span", {}, "Against"),
          h("select", { class: "input", onchange: (e) => { target = e.target.value; } },
            knights.map((k) => h("option", { value: k.id, selected: k.id === target }, k.display_name)))),
        h("div", { class: "label" }, "The knight's result"),
        h("div", { class: "knight-results" },
          h("button", { class: "btn", onclick: () => go("critical", close) }, "Critical"),
          ...(d.outcome === "success"
            ? [h("button", { class: "btn", onclick: () => go("higher", close) }, `Success — beat ${d.roll}`),
               h("button", { class: "btn", onclick: () => go("equal", close) }, `Success — equal ${d.roll}`),
               h("button", { class: "btn", onclick: () => go("lower", close) }, `Success — under ${d.roll}`)]
            : [h("button", { class: "btn", onclick: () => go("higher", close) }, "Success")]),
          h("button", { class: "btn", onclick: () => go("failure", close) }, "Fail"),
          h("button", { class: "btn danger", onclick: () => go("fumble", close) }, "Fumble")),
        !ok ? h("div", { class: "faint small", style: { marginTop: "8px" } }, "The enemy missed — the knight can still win the exchange.") : null,
        h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel")),
      ]);
    }

    // ------------------------------------------------------------ a knight hits an enemy
    async function hitDialog(c) {
      await modal(`Hit ${c.display_name}`, (close) => {
        const dmg = h("input", { class: "input", type: "number", min: 0, placeholder: "damage the player rolled" });
        const shield = h("input", { type: "checkbox" });
        const apply = async () => {
          if (dmg.value === "") return dmg.focus();
          const r = await post("/api/combat/blow", { target: c.id, damage: dmg.value, shield: shield.checked });
          ctx.showLastRoll(r.event);
          close();
        };
        dmg.addEventListener("keydown", (e) => e.key === "Enter" && apply());
        return [
          dmg,
          h("div", { class: "faint small", style: { margin: "8px 0" } },
            `Armour ${c.armor_points} is taken off automatically; knockdown (${c.knockdown}) and wounds are checked.`),
          c.shield ? h("label", { class: "check" }, shield, `Also subtract shield ${c.shield} (they got a partial success or tie)`) : null,
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: apply }, "Apply")),
        ];
      });
    }

    function statLine(c, isKnight) {
      const roll = (body) => post(`/api/combat/${c.id}/roll`, body).then((r) => ctx.showLastRoll(r.event));
      const hasChars = CHAR_ORDER.some((k) => c.characteristics?.[k]);
      const parts = [];
      if (hasChars) {
        parts.push(h("span", { class: "grp" }, CHAR_ORDER.map((k) => h("span", { class: "pair" }, h("span", { class: "nm" }, CHAR_FULL[k]), " ",
          h("span", { class: `rollable ${c.down ? "down" : ""}`, title: `Roll ${CHAR_FULL[k]}${c.modifier ? ` (${c.modifier > 0 ? "+" : ""}${c.modifier})` : ""}`,
            onclick: () => roll({ what: "char", key: k }) }, c.characteristics[k])))));
      }
      if (c.attacks?.length) {
        parts.push(h("span", { class: "grp" }, c.attacks.map((a, i) => h("span", { class: "pair" }, h("span", { class: "nm" }, a.weapon), " ",
          h("span", { class: `rollable ${a.value >= 16 ? "famous" : ""} ${c.down ? "down" : ""}`, title: `${a.weapon}: attack a knight`, onclick: () => (isKnight || !cs.combatants.some((o) => o.side === "party") ? roll({ what: "attack", key: i }) : attackDialog(c, i)) }, skillDisplay(a.value)),
          h("span", { class: `rollable dmg ${c.down ? "down" : ""}`, title: `Roll ${a.weapon} damage`,
            onclick: () => ctx.rollDamage({ label: a.weapon, expr: a.damage, actor: c.log_name, path: `/api/combat/${c.id}/roll`, extra: { what: "damage", key: i } }) }, a.damage)))));
      }
      const skills = Object.entries(c.skills || {});
      if (skills.length) {
        parts.push(h("span", { class: "grp" }, h("span", { class: "faint" }, "Skills "), skills.map(([nm, v]) => h("span", { class: "pair" }, h("span", { class: "nm" }, nm), " ",
          h("span", { class: `rollable ${c.down ? "down" : ""}`, onclick: () => roll({ what: "skill", key: nm }) }, skillDisplay(v))))));
      }
      parts.push(h("span", { class: "grp thresholds faint" },
        `Major Wound ${c.major_wound} · Knockdown ${c.knockdown} · Unconscious ${c.unconscious}`,
        c.morale_minimum ? ` · Min Morale to engage ${c.morale_minimum}` : ""));
      if (!isKnight && !hasChars && !c.attacks?.length) return null;
      return h("div", { class: "cbt-stats" }, parts);
    }

    function flavour(c) {
      const bits = [`Armour: ${c.armour_text}`];
      if (c.looks) bits.push(`Looks: ${c.looks}`);
      if (c.side === "party" && c.player) bits.unshift(`Player: ${c.player}`);
      return h("div", { class: "cbt-flavour" }, bits.join("   ·   "));
    }

    function actions(anchor, c) {
      const isKnight = c.side === "party";
      const items = [];
      if (!isKnight) items.push([c.elite ? "Demote" : `Promote to ${c.promotion_title || "champion"}`, () => post(`/api/combat/${c.id}/promote`), { icon: "star" }]);
      items.push([c.status === "unconscious" || c.status === "dead" ? "Revive" : "Knock out",
        () => post(`/api/combat/${c.id}/status`, { out: c.status === "unconscious" || c.status === "dead" ? null : "unconscious" }), { icon: "heart" }]);
      if (c.status !== "dead") items.push(["Slay", () => post(`/api/combat/${c.id}/status`, { out: "dead" }), { icon: "x" }]);
      items.push([c.status === "fled" ? "Reactivate (resume tracking)" : "Deactivate (fled / not tracked)",
        () => post(`/api/combat/${c.id}/status`, { out: c.status === "fled" ? null : "fled" }), { icon: "flag" }]);
      if (!isKnight) {
        items.push(null);
        items.push([`Surrender check (Valorous ${c.valorous})`, () => post(`/api/combat/${c.id}/surrender`), { icon: "d20" }]);
        if (c.ransom) items.push(["Roll ransom", () => post(`/api/combat/${c.id}/ransom`), { icon: "d6" }]);
      }
      items.push(null);
      items.push(["Remove from encounter", () => post(`/api/combat/${c.id}/remove`), { icon: "x", danger: true }]);
      menu(anchor, items);
    }

    // ------------------------------------------------------------ wiring
    const refreshSoon = debounce(refresh, 50);
    ctx.onEvent((evs, { reset }) => {
      if (reset || evs.some((e) => e.type.startsWith("combat.") || e.type.startsWith("meta."))) refreshSoon();
    });

    await loadLibrary();
    await refresh();
    return {
      async show() { await loadLibrary(); await refresh(); },
      async onLibrary() { await loadLibrary(); if (!cs?.active) render(); },
    };
  },
};
