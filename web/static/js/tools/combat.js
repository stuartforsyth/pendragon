// Combat tracker: launch an encounter (the Party joins automatically), then
// run it — HP, wounds, engagements, situational modifiers, click-to-roll,
// promotion, surrender and ransom. Every change is an event; strike one in the
// log to undo it.

import { h, clear, api, post, icon, menu, modal, toast, useCss, confirmBox, skillDisplay,
  CHAR_FULL, CHAR_ORDER, debounce } from "../lib.js";
import { moraleStrip } from "../components.js";
import { knightShield } from "../board.js";
import { foeFace as sharedFoeFace, layoutField, linkLines, horseBadge, proneBadge, stanceBadge } from "../field.js";

export default {
  async mount(el, ctx) {
    useCss("combat");
    let cs = null;             // GM view of the combat
    let encounters = [], advs = [], party = [], npcs = [];
    let pending = false;       // a re-render waiting for an input to lose focus
    let launchQuery = "", selected = "", players = null, includeParty = true, knightsMounted = true;
    const randomTags = new Set();    // tags a Random fight must carry (all of them)

    const body = h("div");
    clear(el, body);

    async function loadLibrary() {
      [encounters, advs, party, npcs] = await Promise.all([
        api("/api/encounters").then((r) => r.encounters),
        api("/api/adversaries").then((r) => r.adversaries),
        api("/api/party").then((r) => r.party),
        api("/api/cast/fightable").then((r) => r.npcs),
      ]);
    }

    let bt = null;              // the battle a linked fight belongs to (GM view)
    async function refresh() {
      cs = (await api("/api/combat")).combat;
      bt = cs?.battle ? (await api("/api/battle")).battle : null;
      render();
    }

    function render() {
      if (el.querySelector(".cbt-foe input:focus, .cbt-head input:focus, .cbt-drawer input:focus")) { pending = true; return; }
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
              h("label", { class: "check" }, h("input", { type: "checkbox", checked: knightsMounted, onchange: (e) => { knightsMounted = e.target.checked; } }),
                "Knights mounted"),
              h("div", { class: "row" },
                h("button", { class: "btn primary", onclick: () => launch() }, icon("swords"), "Launch encounter"),
                h("button", { class: "btn", onclick: randomFight, title: "Draw a random encounter — only those with every tag picked below" }, icon("d6"), "Random fight")),
              tagChips(),
              h("button", { class: "btn", onclick: pickSingle }, icon("dragon"), "Fight a single adversary or NPC…"),
              h("div", { class: "faint small" }, "Build new encounters in the Encounter Creator."))),
          h("div", { class: "panel" }, h("h3", {}, "Encounters"), search, h("div", { style: { height: "8px" } }), list)),
        cs && !cs.active ? h("div", { class: "panel", style: { marginTop: "14px" } },
          h("h3", {}, "Last combat"), h("p", { class: "muted", style: { margin: 0 } },
            `${cs.name} ended after ${cs.round} round${cs.round === 1 ? "" : "s"} — `,
            `${cs.combatants.filter((c) => c.side !== "party" && c.down).length} of ${cs.combatants.filter((c) => c.side !== "party").length} foes down.`)) : null,
      ];
    }

    // Tags across the library; picked ones narrow a Random fight.
    function tagChips() {
      const tags = [...new Set(encounters.flatMap((e) => e.tags || []))].sort((a, b) => a.localeCompare(b));
      if (!tags.length) return null;
      const box = h("div", { class: "tag-pick" }, h("span", { class: "faint small" }, "Random fight from:"),
        tags.map((t) => h("button", { class: `chip ${randomTags.has(t) ? "on" : ""}`, onclick: (e) => {
          randomTags.has(t) ? randomTags.delete(t) : randomTags.add(t);
          e.currentTarget.classList.toggle("on");
        } }, t)));
      return box;
    }

    async function randomFight() {
      const activeParty = party.filter((m) => m.active !== false);
      const r = await post("/api/combat/random", { tags: [...randomTags], players: players ?? (activeParty.length || 4),
        include_party: includeParty, knights_mounted: knightsMounted });
      if (r?.event) toast(`Drew ${r.event.title}`, "ok");
    }

    // Pick an adversary — or a Cast NPC with saved stats (helm icon, murrey).
    async function pickFoe(title, onPick) {
      await modal(title, (close) => {
        const list = h("div", { class: "list", style: { maxHeight: "50vh", overflow: "auto" } });
        const all = [...npcs.map((n) => ({ ...n, isNpc: true })), ...advs];
        const draw = (q = "") => clear(list, all.filter((a) => `${a.key} ${a.category} ${a.tier} ${a.isNpc ? "npc cast" : ""}`.toLowerCase().includes(q.toLowerCase()))
          .map((a) => h("div", { class: `list-item ${a.isNpc ? "npc-item" : ""}`, onclick: async () => { await onPick(a); close(); } },
            a.isNpc ? icon("helm", "npc-ico") : null,
            h("span", {}, a.key),
            a.isNpc ? h("span", { class: "tag murrey" }, "NPC") : null,
            h("span", { class: "meta" }, a.isNpc ? `${a.tier} · HP ${a.hp ?? "?"}` : `${a.category}${a.tier ? " · " + a.tier : ""} · HP ${a.hp ?? "?"}`))));
        const search = h("input", { class: "input", placeholder: "Search adversaries and NPCs…", oninput: (e) => draw(e.target.value) });
        draw();
        return [search, h("div", { style: { height: "8px" } }), list];
      });
    }

    const pickSingle = () => pickFoe("Fight a single adversary or NPC", (a) =>
      post("/api/combat/start", { ...(a.isNpc ? { cast: a.cast_id } : { adversary: a.key }), include_party: includeParty, knights_mounted: knightsMounted }));

    async function launch(key = selected) {
      if (!key) return toast("Search, then pick an encounter to launch", "err");
      const activeParty = party.filter((m) => m.active !== false);
      await post("/api/combat/start", { encounter: key, players: players ?? (activeParty.length || 4), include_party: includeParty, knights_mounted: knightsMounted });
    }

    // ------------------------------------------------------------ running
    // Lanes by knight: each knight's foes sit under them; one stat header per
    // foe type; one line per foe; defeated foes collapse into a strip.
    const openFoes = new Set();      // foe lines expanded to show their full stats
    let view = (() => { try { return localStorage.getItem("cbt-view") || "field"; } catch { return "field"; } })();
    let picked = null;               // the token whose controls are open (Field view)
    const adjust = new Map();        // foe id → a one-roll ± for its next attack

    // Post a change; if it defeated a foe nobody was fighting, ask who gets the Glory.
    async function act(path, body) {
      const r = await post(path, body);
      if (r?.prompt?.kind === "who_defeated") whoDefeated(r.prompt.cid, r.prompt.name);
      return r;
    }

    async function whoDefeated(cid, name) {
      const knights = cs.combatants.filter((o) => o.side === "party");
      await modal(`Who defeated ${name}?`, (close) => [
        h("p", { class: "muted" }, "They weren't fighting anyone. Their Glory goes to:"),
        h("div", { class: "row", style: { flexWrap: "wrap" } },
          knights.map((k) => h("button", { class: "btn", onclick: async () => { await post(`/api/combat/${cid}/credit`, { knight: k.party_id }); close(); } }, k.display_name)),
          h("button", { class: "btn ghost", onclick: async () => { await post(`/api/combat/${cid}/credit`, { knight: null }); close(); } }, "Nobody (no Glory)")),
      ]);
    }

    async function awardGlory() {
      const knights = cs?.combatants.filter((o) => o.side === "party") || [];
      const list = knights.length ? knights.map((k) => ({ id: k.party_id, name: k.display_name }))
        : party.filter((m) => m.active !== false).map((m) => ({ id: m.id, name: m.name }));
      if (!list.length) return toast("No knights to award", "err");
      await modal("Award Glory", (close) => {
        const who = h("select", { class: "input" }, list.map((k) => h("option", { value: k.id }, k.name)));
        const amt = h("input", { class: "input", type: "number", placeholder: "Glory, e.g. 50" });
        const why = h("input", { class: "input", placeholder: "What for — e.g. seized the standard" });
        const go = async () => {
          if (!amt.value || !why.value.trim()) return toast("Enter the Glory and what it's for", "err");
          await post("/api/glory", { knight: who.value, amount: amt.value, reason: why.value });
          close();
        };
        why.addEventListener("keydown", (e) => e.key === "Enter" && go());
        return [h("label", { class: "field" }, h("span", {}, "Knight"), who),
          h("label", { class: "field" }, h("span", {}, "Glory"), amt),
          h("label", { class: "field" }, h("span", {}, "For"), why),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: go }, icon("star"), "Award"))];
      });
    }

    function running() {
      const knights = cs.combatants.filter((c) => c.side === "party");
      const foes = cs.combatants.filter((c) => c.side !== "party");
      const up = foes.filter((c) => !c.down).length;
      const note = h("input", { class: "input", placeholder: "Round note — e.g. the bridge collapses · Shift+Enter for a divider", style: { flex: 1 },
        title: "Enter: a note in the log and the Fray. Shift+Enter: a thin divider — the start of something new",
        onkeydown: async (e) => { if (e.key === "Enter" && e.target.value.trim()) { await post(e.shiftKey ? "/api/combat/divider" : "/api/combat/note", { text: e.target.value }); e.target.value = ""; } } });
      const availableKnights = party.filter((m) => !cs.combatants.some((c) => c.party_id === m.id));
      const pool = foes.filter((c) => cs.pool.includes(c.id));
      return [
        h("div", { class: "cbt-head sticky-bar" },
          h("div", { class: "row", style: { alignItems: "flex-end" } },
            h("div", { style: { minWidth: 0, flex: 1 } },
              h("div", { class: "label" }, bt ? `${bt.definition.name || "Battle"} · Day ${cs.battle.day} · Turn ${cs.battle.turn}${cs.battle.doubled ? " · foes doubled" : ""}` : "In combat"),
              h("h1", { class: "cbt-title" }, cs.name)),
            h("div", { class: "round-box" }, h("span", { class: "label" }, "Round"), h("span", { class: "round-n" }, cs.round)),
            h("button", { class: "btn primary", onclick: () => post("/api/combat/round") }, icon("hourglass"), "Next round"),
            h("button", { class: "btn", onclick: (e) => addMenu(e.currentTarget, availableKnights) }, icon("plus"), "Add"),
            knights.length && foes.some((c) => !c.down) ? h("button", { class: "btn", onclick: () => post("/api/combat/distribute"),
              title: "Spread the foes still fighting evenly over the knights still in the fight. Defeated foes stay with the knight they fell to." }, icon("swords"), "Distribute foes equally") : null,
            h("button", { class: "btn", onclick: awardGlory, title: "Award Glory by hand (an Opportunity's reward, a deed)" }, icon("star"), "Award Glory"),
            h("button", { class: "btn danger", onclick: endCombat }, icon("flag"), "End fight"),
            bt ? h("button", { class: "btn ghost", onclick: () => ctx.navigate("battle") }, "◂ Back to battle") : null),
          barrageBar(foes),
          h("div", { class: "row", style: { marginTop: "10px" } },
            h("span", { class: "tag gules" }, `${up} of ${foes.length} foes standing`),
            up ? h("span", { class: `tag ${cs.to_act.length ? "or" : "vert"}`, title: "A foe's roll marks it as having acted; click the circle on a foe to tick it by hand. Next round clears the ticks." },
              cs.to_act.length ? `${cs.to_act.length} of ${up} still to act this round` : "Every foe has acted this round") : null,
            knights.length ? h("span", { class: "tag azure" }, `${knights.filter((k) => !k.down).length} of ${knights.length} knights in the fight`) : null,
            note,
            knights.length ? h("span", { class: "seg", role: "group", "aria-label": "View" },
              ["field", "list"].map((v) => h("button", { class: `chip ${view === v ? "on" : ""}`, onclick: () => {
                view = v; try { localStorage.setItem("cbt-view", v); } catch {} render(); } }, v === "field" ? "Field" : "List"))) : null)),
        bt ? moraleStrip(bt, { onAdjust: () => ctx.navigate("battle"), onCommander: () => ctx.navigate("battle") }) : null,
        bt ? battleBanners() : null,
        cs.gm_notes ? h("details", { class: "cbt-notes" }, h("summary", {}, "GM notes"), h("p", { class: "muted" }, cs.gm_notes)) : null,
        cs.types?.length ? h("div", { class: "cbt-types" }, cs.types.map(typeHeader)) : null,
        !foes.length ? h("div", { class: "empty" }, "No foes — add some.") : null,
        view === "field" && knights.length ? field(knights, foes, pool) : [
        knights.length ? h("div", { class: "cbt-lanes" }, knights.map((k) => lane(k, foes))) : null,
        knights.length
          ? (pool.length ? dropZone(h("div", { class: "cbt-pool" }, h("span", { class: "label" }, "Not engaged"),
              pool.map(poolChip), h("span", { class: "faint small" }, "drag onto a knight, or click to assign")), "") : null)
          : (pool.length ? h("div", { class: "cbt-lane" }, h("div", { class: "cbt-lane-body" }, pool.map(foeLine))) : null)],
        defeatedStrip(foes),
        h("div", { class: "cbt-help faint small" },
          "Each foe shows the weapon in its hand: click it to switch weapons or mark it Disarmed (it fights on with Brawling). Attack rolls that weapon against the knight it's fighting — you click the knight's result, and if the foe wins its damage is rolled. ",
          "In a foe type's header, “All wield” switches every foe of that type at once (lances down, swords out). ",
          "When a knight hits a foe, press Hit and enter the damage the player rolled — armour comes off automatically. ±HP is for plain changes (healing, a fall). ",
          "Drag a foe to another knight, or use its target chip, to change who it fights. Strike any log entry to undo it."),
      ];
    }

    // One shared stat block per foe type. Clicking a value acts for that
    // type's only active foe, or asks which one when there are several.
    function typeHeader(t) {
      const active = cs.combatants.filter((c) => c.side !== "party" && c.type === t.type && !c.down);
      const forFoe = (anchor, label, value, fn) => {
        if (!active.length) return toast(`No ${t.type} still fighting`, "err");
        if (active.length === 1) return fn(active[0]);
        menu(anchor, active.map((c) => [`${c.display_name} — ${value(c)}`, () => fn(c)]));
      };
      const rollFor = (c, body) => post(`/api/combat/${c.id}/roll`, body).then((r) => ctx.showLastRoll(r.event));
      return h("div", { class: "cbt-type" },
        h("b", { class: "cbt-type-name" }, t.type),
        h("span", { class: "grp" }, Object.entries(t.characteristics).map(([k, v]) => h("span", { class: "pair" }, h("span", { class: "nm" }, k), " ",
          h("span", { class: "rollable", title: `Roll ${CHAR_FULL[k]}`, onclick: (e) => forFoe(e.currentTarget, k, (c) => c.characteristics[k] + (c.modifier || 0), (c) => rollFor(c, { what: "char", key: k })) }, v)))),
        t.attacks.length > 1 ? h("span", { class: "grp" }, h("span", { class: "faint small" }, "All wield"),
          t.attacks.map((a, i) => {
            const all = active.length && active.every((c) => wieldedOf(c)[0] === i);
            return h("button", { class: `cbt-wpick ${all ? "on" : ""}`, title: `Every ${t.type} still fighting takes up ${a.weapon}`,
              onclick: () => post("/api/combat/wield", { type: t.type, wield: i }) },
              a.weapon, " ", h("b", {}, skillDisplay(a.value)), h("span", { class: "faint" }, ` · ${a.damage}`));
          }))
          : h("span", { class: "grp" }, t.attacks.map((a) => h("span", { class: "pair" }, h("span", { class: "nm" }, a.weapon), " ", h("b", {}, skillDisplay(a.value)), h("span", { class: "faint" }, ` · ${a.damage}`)))),
        active.some((c) => c.missile != null) ? h("button", { class: "cbt-wpick loose-all", title: `Every ${t.type} facing a knight looses — one volley per knight, so the players see one card each`,
          onclick: () => looseAll(t.type) }, "🏹 All loose") : null,
        h("span", { class: "grp" }, h("span", { class: "faint small" }, "All"),
          Object.entries(STANCE).map(([k, st]) => {
            const all = active.length && active.every((c) => (c.stance || "attack") === k);
            return h("button", { class: `cbt-wpick ${all ? "on" : ""}`, title: `Every ${t.type} still fighting: ${st.hint}`,
              onclick: () => post("/api/combat/stance", { type: t.type, stance: k }) }, st.label);
          })),
        h("span", { class: "faint" }, t.armour_text),
        t.description || t.notes ? h("button", { class: "btn ghost sm icon", title: "Card text and rules",
          onclick: () => modal(t.type, (close) => [
            t.description ? h("p", {}, t.description) : null,
            t.notes && t.notes !== t.description ? h("p", { class: "muted" }, t.notes) : null,
            h("div", { class: "foot" }, h("button", { class: "btn primary", onclick: () => close() }, "Close"))]) }, icon("scroll")) : null);
    }

    // ------------------------------------------------------------ the Field
    // Knights and foes as tokens; an engagement is a glowing red line. Drag a
    // foe onto a knight (or a knight onto a foe) to engage them, a foe onto a
    // foe to join its knight, a foe onto Waiting to free it. Click a token to
    // open its controls. One foe fights one knight (for now).
    function foeFace(c) {
      const pct = c.cur_hp / Math.max(1, c.max_hp);
      return sharedFoeFace(c.category, pct, pct > .5 ? "#79b585" : pct > .25 ? "#d4a84b" : "#d0574b", { struck: c.down, lost: c.down ? "rgba(0,0,0,.35)" : "#7a2a22" });
    }
    let dragging = null;             // { id, side } while a token is dragged
    function ftok(c, x, y) {
      const knight = c.side === "party";
      const stance = !knight && !c.down ? (c.stance || "attack") : "attack";
      const node = h("div", { class: `ftok ${knight ? "is-knight" : "is-foe"} ${!knight && c.engaged_with ? "engaged" : ""} ${c.down ? "down" : ""} ${c.elite ? "elite" : ""} ${picked === c.id ? "picked" : ""} ${!knight && c.acted && !c.down ? "acted" : ""} ${stance !== "attack" ? "st-" + stance + (stance === "trample" ? "" : " defensive") : ""}`,
        "data-id": c.id, style: { left: `${x}px`, top: `${y}px` }, title: knight ? "Click for controls · drag onto a foe to engage" : "Click for controls · drag onto a knight to engage",
        onclick: () => { picked = picked === c.id ? null : c.id; render(); } },
        knight ? h("span", { class: "ftok-face" }, knightShield(c.down)) : foeFace(c),
        c.mounted && !c.down ? horseBadge() : null,
        c.prone && !c.down ? proneBadge() : null,
        stanceBadge(stance),
        !knight && c.acted && !c.down ? h("span", { class: "ftok-acted", title: "Has acted this round" }, "✓") : null,
        h("span", { class: "ftok-name" }, c.display_name),
        h("span", { class: "ftok-sub" }, knight ? (c.down ? (c.status === "fled" ? "Out of the fight" : "Down") : c.prone ? "Prone" : c.mounted ? "Mounted" : "On foot")
          : c.down ? `${c.wound_state}${c.credit ? " · ✦" + c.credit.glory : ""}`
          : `${c.cur_hp}/${c.max_hp}${c.wound_state && c.wound_state !== "Unhurt" ? " · " + c.wound_state : ""}${c.prone ? " · Prone" : ""}${c.wielding === "brawl" ? " · Disarmed" : ""}`));
      if (c.down) return node;
      node.draggable = true;
      node.addEventListener("dragstart", (e) => {
        dragging = { id: c.id, side: knight ? "knight" : "foe" };
        e.dataTransfer.setData("text/cid", c.id); e.dataTransfer.effectAllowed = "move";
        el.classList.add(`drag-${dragging.side}`);
      });
      node.addEventListener("dragend", () => { dragging = null; el.classList.remove("drag-knight", "drag-foe"); });
      node.addEventListener("dragover", (e) => { if (dragging && canDrop(dragging, c)) { e.preventDefault(); node.classList.add("over"); } });
      node.addEventListener("dragleave", () => node.classList.remove("over"));
      node.addEventListener("drop", (e) => {
        node.classList.remove("over");
        if (!dragging || !canDrop(dragging, c)) return;          // let Waiting take it
        e.preventDefault(); e.stopPropagation(); dropOn(e.dataTransfer.getData("text/cid"), c);
      });
      return node;
    }
    const byId = (id) => cs.combatants.find((o) => o.id === id);
    function canDrop(d, target) {
      if (target.down || d.id === target.id) return false;
      const tKnight = target.side === "party";
      if (d.side === "foe") return tKnight || !!target.engaged_with;
      return !tKnight && !(target.linked || []).includes(byId(d.id)?.display_name);
    }
    function dropOn(srcId, target) {
      const src = byId(srcId);
      if (!src || !canDrop({ id: src.id, side: src.side === "party" ? "knight" : "foe" }, target)) return;
      if (src.side === "party") return post("/api/combat/link", { cid: target.id, knight: src.display_name });   // a knight joins
      const knightName = target.side === "party" ? target.display_name : target.engaged_with;                  // a foe moves
      if ((src.linked || []).join() !== knightName) post(`/api/combat/${src.id}/engage`, { with: knightName });
    }

    function field(knights, foes, pool) {
      const measured = el.querySelector(".cbt-field")?.clientWidth || el.clientWidth || 960;
      const W = Math.max(picked ? 360 : 640, measured);
      const item = (c) => ({ id: c.id, side: c.side === "party" ? "party" : "foe", name: c.display_name, linked: c.linked || [], down: c.down,
        credit: c.down ? c.credit?.name : null, ref: c });
      const { placed, lines, height } = layoutField(knights.map(item), foes.map(item), W, { tokW: 130, tokH: 94 });
      const tokens = placed.map(([t, x, y]) => ftok(t.ref, x, y));

      const waiting = pool.filter((f) => !f.down);
      const wait = h("div", { class: "cbt-wait" }, h("span", { class: "label" }, "Waiting"),
        waiting.length ? waiting.map((f) => { const t = ftok(f, 0, 0); t.classList.add("inline"); return t; })
          : h("span", { class: "faint small" }, "Drag a foe here to take it out of an engagement"));
      wait.addEventListener("dragover", (e) => { if (dragging?.side === "foe") { e.preventDefault(); wait.classList.add("over"); } });
      wait.addEventListener("dragleave", () => wait.classList.remove("over"));
      wait.addEventListener("drop", (e) => {
        e.preventDefault(); wait.classList.remove("over");
        const f = byId(e.dataTransfer.getData("text/cid"));
        if (f && f.side !== "party" && f.engaged_with) post(`/api/combat/${f.id}/engage`, { with: "" });
      });
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "cbt-links");
      const stage = h("div", { class: "cbt-field", style: { height: `${height}px` } }, svg, tokens);
      // the Field shares its row with the drawer: when its width changes, lay the clusters out again
      const widthWatch = new ResizeObserver(() => {
        if (!stage.isConnected) return widthWatch.disconnect();
        // A tool the GM has left is hidden and measures 0 wide — and so is the Field the redraw makes, which
        // would redraw again, for ever (Firefox reports a hidden target at once): only a shown Field is laid out.
        if (stage.clientWidth && Math.abs(stage.clientWidth - measured) > 40) { widthWatch.disconnect(); render(); }
      });
      widthWatch.observe(stage);
      stage.addEventListener("dragover", (e) => { if (dragging?.side === "knight") e.preventDefault(); });
      stage.addEventListener("drop", (e) => {                     // a knight dropped on open ground breaks off
        if (dragging?.side !== "knight" || e.target.closest(".ftok")) return;     // a knight on a knight does nothing
        e.preventDefault();
        const k = byId(dragging.id);
        if (k) post("/api/combat/unlink", { knight: k.display_name });
      });
      linkLines(stage, svg, lines, { glowId: "cbt-glow" });
      const pick = picked && byId(picked);
      return [h("div", { class: `cbt-field-wrap ${pick ? "has-drawer" : ""}` }, stage, pick ? drawer(pick, foes) : null), wait];
    }

    // The picked token's controls: a foe's row (weapon, Attack, Hit, ±HP…) and
    // stats, or a knight's lane (mounted, Down/Out, their foes).
    function drawer(c, foes) {
      if (c.side !== "party" && !openFoes.has(c.id)) openFoes.add(c.id);
      return h("div", { class: "cbt-drawer" },
        h("button", { class: "btn ghost sm icon cbt-drawer-x", title: "Close", onclick: () => { picked = null; render(); } }, icon("x")),
        c.side === "party" ? lane(c, foes) : h("div", { class: "cbt-lane" }, h("div", { class: "cbt-lane-body" }, foeLine(c))));
    }

    // Lanes and the pool accept dropped foes: the drop retargets the foe.
    function dropZone(node, knightName) {
      node.addEventListener("dragover", (e) => { e.preventDefault(); node.classList.add("drop-ok"); });
      node.addEventListener("dragleave", () => node.classList.remove("drop-ok"));
      node.addEventListener("drop", (e) => {
        e.preventDefault(); node.classList.remove("drop-ok");
        const c = cs.combatants.find((o) => o.id === e.dataTransfer.getData("text/cid"));
        if (c && (c.engaged_with || "") !== knightName) post(`/api/combat/${c.id}/engage`, { with: knightName });
      });
      return node;
    }
    const draggable = (node, c) => {
      node.draggable = true;
      node.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/cid", c.id); e.dataTransfer.effectAllowed = "move"; });
      return node;
    };

    function targetMenu(anchor, c) {
      const knights = cs.combatants.filter((o) => o.side === "party").map((o) => o.display_name);
      menu(anchor, [...knights.map((n) => [n === c.engaged_with ? `${n} ✓` : n, () => n !== c.engaged_with && post(`/api/combat/${c.id}/engage`, { with: n }), { icon: "swords" }]),
        null, ["Not engaged", () => c.engaged_with && post(`/api/combat/${c.id}/engage`, { with: "" })]]);
    }

    function lane(k, foes) {
      const mine = foes.filter((c) => (c.linked || []).includes(k.display_name) && !c.down);
      const mark = (out) => post(`/api/combat/${k.id}/status`, { out });
      const tag = { unconscious: ["Down", "gules"], fled: ["Out of the fight", ""] }[k.status];
      return dropZone(h("div", { class: `cbt-lane ${k.down ? "is-down" : ""}` },
        h("div", { class: "cbt-lane-head" },
          icon("shield", "cbt-shield"),
          h("span", { class: "cbt-knight" }, k.display_name),
          k.player ? h("span", { class: "faint small" }, k.player) : null,
          tag ? h("span", { class: `tag ${tag[1]}` }, tag[0]) : null,
          mountedPill(k),
          k.mounted && !k.down ? h("button", { class: `pill-lance ${k.lance ? "on" : ""}`, title: k.lance ? "Charging with a couched lance this round: a partial success or tie breaks it, a fumble breaks it and calls for Table 7.2. Click to lower it." : "Couch a lance for a charge this round",
            onclick: () => post(`/api/combat/${k.id}/lance`, { on: !k.lance }) }, k.lance ? "⚔ Lance couched" : "Lance") : null,
          foes.some((c) => c.missile != null) ? shieldChip(k) : null,
          (() => { const n = foes.filter((c) => c.missile != null && !c.down && c.engaged_with === k.display_name).length;
            return n && !k.down ? h("button", { class: "btn sm atk-btn loose", title: `The ${n} archer${n === 1 ? "" : "s"} facing ${k.display_name} loose together — the players get one card for the volley`,
              onclick: () => volley(k, n) }, `🏹 Volley · ${n}`) : null; })(),
          h("button", { class: `pill-prone ${k.prone ? "on" : ""}`, "aria-label": k.prone ? "Prone — back on their feet" : "Mark prone",
            title: k.prone ? "Prone — click when back on their feet (standing takes the action)" : "Mark knocked prone (a failed Knockdown roll, a fall)",
            onclick: () => post(`/api/combat/${k.id}/prone`, { on: !k.prone }) }, k.prone ? "Prone" : "⤓"),
          k.prone_foes?.length ? h("span", { class: "tag gules", title: `${k.prone_foes.join(", ")} prone: from the saddle only a spear or lance reaches — or Trample (Horsemanship vs their action −5, the horse's damage)` }, "Prone foe: spear or Trample") : null,
          h("span", { class: "cbt-lane-slots" },
            k.mo?.n > 1 ? h("span", { class: `chip-mo ${k.mo.over ? "warn" : ""}`,
              title: k.mo.over ? `More than ${k.mo.limit} ${k.mo.limit === 2 ? "mounted foes" : "foes on foot"} can't all attack one knight` : "Multiple Opponents: the knight applies this to each opponent" },
              k.mo.over ? `⚠ ${k.mo.n} foes (counts ${k.mo.faced}) · −${-k.mo.mod} vs each` : `⚠ ${k.mo.n} foes · −${-k.mo.mod} vs each`) : null,
            heightReminders(k.height_chips || [])),
          k.posture ? h("span", { class: "meta" }, `${k.posture[0].toUpperCase() + k.posture.slice(1)} · round ${Math.min(cs.round, k.rounds + k.extra_rounds)} of ${k.rounds + k.extra_rounds}`,
            k.last_round ? h("b", { class: "withdraw" }, " · withdraws after this round") : k.withdraws ? h("b", { class: "withdraw" }, " · withdraws") : null) : null,
          k.position === "alone" ? h("span", { class: "tag gules", title: "Alone: rolls Battle at −10, still drains conroi Morale (use ± with a reason)" }, "Alone") : null,
          bt && (k.last_round || k.withdraws) ? h("button", { class: "btn ghost sm", title: "Energetic + Valorous succeeded: one more round",
            onclick: () => post("/api/battle/step", { step: "extra_round", knight: k.party_id }) }, "+1 round") : null,
          h("span", { class: "cbt-glory", title: bt ? "Glory won this battle" : "Glory won this fight" },
            bt ? `✦ ${bt.glory_battle?.[k.party_id] ?? 0} this battle` : `✦ ${cs.glory?.[k.party_id] ?? 0} this fight`),
          k.down ? h("button", { class: "btn ghost sm", onclick: () => mark(null) }, "Back in the fight")
            : [h("button", { class: "btn ghost sm", onclick: () => mark("unconscious") }, "Down"),
               h("button", { class: "btn ghost sm", onclick: () => mark("fled") }, "Out")]),
        h("div", { class: "cbt-lane-body" }, mine.length ? mine.map(foeLine) : h("div", { class: "faint small cbt-none" }, "No foe engaged"))),
      k.display_name);
    }

    function foeLine(c) {
      const creature = ["beast", "monster", "fae"].includes(c.category);
      const marker = (c.elite ? "★" : "") + (c.named ? "◆" : "") + (creature && !c.named ? "✦" : "");
      const tone = c.npc ? "npc" : c.elite ? "elite" : c.named ? "named" : c.category;
      const pct = Math.max(0, Math.min(100, (c.cur_hp / c.max_hp) * 100));
      const hpTone = pct > 50 ? "" : pct > 25 ? "w" : "b";
      const open = openFoes.has(c.id);
      const hpIn = h("input", { class: "input num hp-in", placeholder: "±HP", title: "Damage as negative, healing as positive — Enter",
        onkeydown: (e) => { if (e.key === "Enter") applyHp(c, e.target); } });
      const line = h("div", { class: `cbt-foe t-${tone} ${open ? "open" : ""} ${c.acted && !c.down ? "acted" : ""}`, "data-id": c.id },
        h("div", { class: "cbt-foe-line" },
          h("span", { class: "cbt-foe-id" },
            c.down ? null : h("button", { class: `acted-tog ${c.acted ? "on" : ""}`,
              title: c.acted ? "Has acted this round — click to untick" : "Yet to act this round — its roll ticks it, or click to tick by hand",
              onclick: () => post(`/api/combat/${c.id}/acted`, { on: !c.acted }) }, c.acted ? "✓" : ""),
            h("button", { class: "cbt-foe-name", title: "Everything about this foe: stats, armour, Glory, flavour and how it fights",
              onclick: () => foeSheet(c) },
              c.npc ? icon("helm", "npc-ico") : marker ? h("span", { class: "marker" }, marker) : null, c.display_name)),
          h("div", { class: "cbt-hp" },
            h("div", { class: "hp-bar big" }, h("i", { class: hpTone, style: { width: `${pct}%` } })),
            h("span", { class: "hp-text" }, h("b", {}, c.cur_hp), h("span", { class: "faint" }, ` / ${c.max_hp}`),
              c.wound_state ? h("span", { class: "ws faint" }, ` · ${c.wound_state}`) : null)),
          h("span", { class: "cbt-chips" }, foeChips(c)),
          h("button", { class: `cbt-target ${c.engaged_with ? "set" : ""}`, title: "Who is this foe fighting?",
            onclick: (e) => targetMenu(e.currentTarget, c) }, `→ ${c.engaged_with || "nobody"} ▾`),
          weaponCell(c),
          h("button", { class: "btn sm hit-btn", disabled: cs.barrage?.active || null, title: cs.barrage?.active ? "The knights can't reach the archers until the barrage ends" : `A knight hit ${c.display_name}: enter the damage rolled`, onclick: () => hitDialog(c) }, icon("shield"), "Hit"),
          hpIn,
          h("button", { class: "btn sm icon", title: "Actions", onclick: (e) => actions(e.currentTarget, c) }, icon("dots"))),
        open ? h("div", { class: "cbt-foe-more" }, statLine(c, false),
          h("div", { class: "row" }, h("div", { class: "cbt-mod" }, h("span", { class: "faint small" }, "Mod"), modInput(c)), flavour(c))) : null);
      return draggable(line, c);
    }

    // The weapon in hand (click to switch, or mark Disarmed) and Attack, which
    // rolls it against the knight this foe is fighting.
    function wieldedOf(c) {
      if (c.wielding === "brawl" || !c.attacks?.length) return ["brawl", c.brawl];
      const i = Number(c.wielding) || 0;
      return [i, c.attacks[i] || c.attacks[0]];
    }
    // What the foe does when the knight comes at it: attack, or one of the
    // defensive actions (core.combat.defensive-actions).
    const STANCE = {
      attack: { label: "Attack", verb: "attacks", icon: "swords", hint: "Weapon skill vs the knight's action" },
      defend: { label: "Defend", verb: "defends", icon: "shield", hint: "Weapon skill +10; a win or tie means no damage either way" },
      evade: { label: "Evade", verb: "evades", icon: "flag", hint: "Movement Rate vs the knight's action; a win breaks the engagement" },
      dodge: { label: "Dodge", verb: "dodges", icon: "drop", hint: "Movement Rate, one roll against every attacker; a win avoids damage but ends on the ground" },
      trample: { label: "Trample", verb: "tramples", icon: "hourglass", hint: "A rider over a prone knight: Horsemanship vs the knight's action −5, no Height for the rider; a win is the horse's 3D6" },
    };
    function stanceMenu(anchor, c) {
      const cur = c.stance || "attack";
      menu(anchor, Object.entries(STANCE).filter(([k]) => k !== "trample" || c.mounted).map(([k, st]) => [
        `${k === cur ? "• " : ""}${st.label}${k === "defend" ? " +10" : k === "evade" ? ` (Movement ${c.mounted ? c.horse_move + ", horse" : c.movement_rate})` : k === "dodge" ? (c.mounted ? " — on foot only" : ` (Movement ${c.movement_rate})`) : k === "trample" ? ` (Horsemanship ${c.skills?.Horsemanship ?? "10"})${c.knight_prone ? "" : " — needs a prone knight"}` : ""}`,
        () => { if (k === "dodge" && c.mounted) return toast("Dodge is for foes on their feet — a rider evades instead", "err"); if (k !== cur) post("/api/combat/stance", { cid: c.id, stance: k }); },
        { icon: st.icon }]));
    }

    function weaponCell(c) {
      const [key, a] = wieldedOf(c);
      const disarmed = key === "brawl";
      const noSkill = a?.value == null;
      const knightsIn = cs.combatants.some((o) => o.side === "party");
      const st = STANCE[c.stance || "attack"];
      const defensive = (c.stance || "attack") !== "attack";
      return h("span", { class: "cbt-wield" },
        h("button", { class: `stance-btn ${defensive ? "on" : ""}`, "aria-label": "Stance", title: `Stance — ${defensive ? st.label + ": " + st.hint : "attacking as usual"}. Click to change what this foe does this round`,
          onclick: (e) => stanceMenu(e.currentTarget, c) }, icon(st.icon), defensive ? st.label : null),
        h("button", { class: `cbt-weapon ${disarmed ? "disarmed" : ""}`, title: disarmed ? "Disarmed — click to pick a weapon back up" : "The weapon in hand — click to switch, or mark Disarmed",
          onclick: (e) => weaponMenu(e.currentTarget, c, key) },
          disarmed ? "✋ " : "⚔ ", h("span", { class: "wn" }, a?.weapon || "Brawling"), " ",
          h("b", {}, noSkill ? "—" : skillDisplay(a.value)), h("span", { class: "faint" }, ` · ${a?.damage || "—"}`),
          disarmed ? h("span", { class: "tag gules" }, "Disarmed") : null, " ▾"),
        c.outnumbered ? h("span", { class: "tag gules out-tag", title: `${c.linked.length} knights on it: −5 per knight after the first, on its attack rolls` },
          `${c.outnumbered}`.replace("-", "−") + " outnumbered") : null,
        h("input", { class: "input num adj-in", placeholder: "±", value: adjust.get(c.id) ?? "", title: "Any other modifier for this foe's next attack roll only",
          oninput: (e) => { const v = e.target.value.trim(); /^[+-]?\d+$/.test(v) ? adjust.set(c.id, Number(v)) : adjust.delete(c.id); } }),
        c.missile != null && !c.down ? h("button", { class: `btn sm atk-btn loose ${cs.barrage?.active ? "primary-ish" : ""}`, title: `${c.display_name} looses ${c.attacks[c.missile].weapon} at ${c.engaged_with || "a knight"} — unopposed, less the knight's shield penalty and the ± box`,
          onclick: () => { render(); looseOne(c); } }, "🏹 Loose") : null,
        h("button", { class: `btn sm atk-btn ${defensive ? "defensive" : ""} ${c.charging && !defensive ? "charge" : ""}`, disabled: c.down || (noSkill && !defensive) || c.cant_strike_prone || (cs.barrage?.active && !defensive) || null,
          "data-barrage": cs.barrage?.active ? "1" : null,
          title: cs.barrage?.active && !defensive ? "Under the barrage the lines haven't met: the archers Loose instead" : c.cant_strike_prone ? `${c.engaged_with} is prone: from the saddle only a spear or lance reaches — set the stance to Trample, or dismount`
            : noSkill && !defensive ? "No Brawling skill — set one in the Adversaries editor"
            : defensive ? `${c.display_name} ${st.verb} against ${c.engaged_with || "a knight"}: ${st.hint}`
            : `${c.display_name} attacks ${c.engaged_with || "a knight"} with ${a.weapon}`,
          onclick: () => {
            const adj = adjust.get(c.id) || 0;                   // one roll, then the box clears
            adjust.delete(c.id); render();
            return knightsIn ? attackDialog(c, key, adj)
              : post(`/api/combat/${c.id}/roll`, { what: "attack", key, adjust: adj }).then((r) => { ctx.showLastRoll(r.event); render(); });
          } },
          icon("swords"), c.charging && !defensive ? "Charge" : st.label));
    }
    function weaponMenu(anchor, c, current) {
      const wield = (w) => w !== current && post("/api/combat/wield", { cid: c.id, wield: w });
      const b = c.brawl || {};
      const broken = new Set(c.broken || []);
      menu(anchor, [
        ...c.attacks.map((a, i) => [`${i === current ? "• " : ""}${a.weapon} ${skillDisplay(a.value)} · ${a.damage}${a.skill === "Charge" ? " — charge" : ""}${broken.has(i) ? " — broken" : ""}`,
          () => broken.has(i) ? toast(`${a.weapon} is broken`, "err") : wield(i)]),
        c.attacks.length ? null : undefined,
        [`${current === "brawl" ? "• " : ""}Disarmed — Brawling ${b.value ?? "—"} · ${b.damage || "—"}`, () => wield("brawl"), { icon: "x" }],
      ].filter((x) => x !== undefined));
    }

    // The knight's own Height reminders, grouped: "+5 Height vs 3 foes".
    function heightReminders(chips) {
      const by = new Map();
      for (const ch of chips) by.set(ch.mod, [...(by.get(ch.mod) || []), ch.foe]);
      return [...by].map(([mod, names]) => h("span", { class: `chip-height ${mod > 0 ? "up" : "down"}`,
        title: `Reminder for the player — Height Advantage against ${names.join(", ")}` },
        `${mod > 0 ? "+" : "−"}${Math.abs(mod)} Height vs ${names.length === 1 ? names[0] : `${names.length} foes`}`));
    }

    function mountedPill(c) {
      return h("button", { class: `pill-mounted ${c.mounted ? "on" : ""}`, title: "Click to toggle mounted / on foot",
        onclick: () => post(`/api/combat/${c.id}/mounted`, { mounted: !c.mounted }) }, c.mounted ? "Mounted" : "On foot");
    }

    // Height chip (click: automatic or negated) and the attacking-the-horse
    // toggle, shown only when this foe's knight is mounted.
    function foeChips(c) {
      const hgt = c.height || { foe: 0, knight: 0 };
      const word = c.height_chip || "";
      const chips = [];
      if (c.engaged_with && word) chips.push(h("button", { class: `chip-height ${hgt.foe > 0 ? "up" : hgt.foe < 0 ? "down" : ""}`,
        title: "Height Advantage on this foe's rolls — click to override",
        onclick: (e) => menu(e.currentTarget, [
          ["Automatic (from who is mounted)", () => post(`/api/combat/${c.id}/height`, { override: null })],
          ["Negated (two-handed spear or halberd)", () => post(`/api/combat/${c.id}/height`, { override: "none" })]]) }, word));
      if (c.prone) chips.push(h("button", { class: "chip-prone", title: "Prone: standing foes get +5 against them, they −5; click when back on their feet",
        onclick: () => post(`/api/combat/${c.id}/prone`, { on: false }) }, "⤓ prone"));
      if (c.knight_mounted && !c.mounted) chips.push(h("button", { class: `chip-horse ${c.attacks_horse ? "on" : ""}`,
        title: c.attacks_horse ? "Attacking the horse: no −5 for this foe; the rider keeps +5" : "Click if this foe goes for the horse",
        onclick: () => post(`/api/combat/${c.id}/horse`, { on: !c.attacks_horse }) }, "⇣ horse"));
      return chips;
    }

    function captiveMenu(c) {
      const knights = cs.combatants.filter((o) => o.side === "party");
      return knights.map((k) => [`Captured by ${k.display_name}`, () => post(`/api/combat/${c.id}/captured`, { by: k.party_id })]);
    }

    // A plain HP change (healing, a fall): damage as negative, healing positive.
    async function applyHp(c, input) {
      const v = input.value.trim();
      if (!v) return;
      input.value = "";
      input.blur();
      await act(`/api/combat/${c.id}/hp`, { delta: v });
    }

    function modInput(c) {
      return h("input", { class: `input num mod-in ${c.modifier < 0 ? "neg" : c.modifier > 0 ? "pos" : ""}`, value: c.modifier ? (c.modifier > 0 ? `+${c.modifier}` : c.modifier) : "0",
        title: "Situational modifier on every roll — Enter",
        onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); },
        onchange: (e) => post(`/api/combat/${c.id}/modifier`, { value: e.target.value.trim() || 0 }) });
    }

    function poolChip(c) {
      return draggable(h("button", { class: "cbt-chip-foe", title: "Click to choose a knight, or drag onto one",
        onclick: (e) => targetMenu(e.currentTarget, c) }, c.display_name, h("span", { class: "faint small" }, ` · ${c.wound_state}`)), c);
    }

    const FATE = { dead: ["✝", "slain"], fled: ["⇢", "fled"], surrendered: ["⚐", "surrendered"], unconscious: ["☾", "unconscious"] };
    function defeatedStrip(foes) {
      const down = foes.filter((c) => cs.defeated.includes(c.id));
      if (!down.length) return null;
      return h("div", { class: "cbt-defeated" }, h("span", { class: "label" }, "Defeated"),
        down.map((c) => h("button", { class: "cbt-chip-foe down", title: "Revive or reactivate",
          onclick: (e) => menu(e.currentTarget, [
            [c.status === "fled" ? "Reactivate (back in the fight)" : "Revive", () => post(`/api/combat/${c.id}/status`, { out: null }), { icon: "heart" }],
            c.status !== "dead" ? ["Slay", () => act(`/api/combat/${c.id}/status`, { out: "dead" }), { icon: "x" }] : false,
            c.ransom ? ["Roll ransom", () => post(`/api/combat/${c.id}/ransom`), { icon: "d6" }] : false,
            ...(["unconscious", "surrendered"].includes(c.status) ? [null, ...captiveMenu(c)] : []),
            c.captured_by ? ["Release the captive", () => post(`/api/combat/${c.id}/captured`, { by: null })] : false,
            null, ["Reassign Glory…", () => whoDefeated(c.id, c.display_name), { icon: "star" }],
          ].filter((x) => x !== undefined && x !== false && x !== "")) },
          `${FATE[c.status][0]} ${c.display_name}`, h("span", { class: "faint small" }, ` · ${FATE[c.status][1]}`),
          c.credit ? h("span", { class: "dcredit" }, ` ✦${c.credit.glory} ${c.credit.name}`)
            : cs.uncredited?.includes(c.id) ? h("span", { class: "dwho" }, " Who defeated them?") : null,
          c.captured_by_name ? h("span", { class: "tag-captured" }, `captured by ${c.captured_by_name}`) : null)));
    }

    function addMenu(anchor, knights) {
      const items = knights.map((m) => [`${m.name} (knight)`, () => post("/api/combat/add-party", { member_id: m.id }), { icon: "party" }]);
      if (items.length) items.push(null);
      items.push(["An adversary or NPC…", pickAdversary, { icon: "dragon" }]);
      menu(anchor, items);
    }

    const pickAdversary = () => pickFoe("Add a combatant", (a) =>
      post("/api/combat/add", a.isNpc ? { cast: a.cast_id } : { adversary: a.key }));

    async function endCombat() {
      if (bt) {
        if (await confirmBox("End the fight?", "End the fight and return to the battle — End turn applies the Morale gain for foes defeated.", "End fight")) {
          await post("/api/combat/end");
          ctx.navigate("battle");
        }
        return;
      }
      if (await confirmBox("End combat?", "The Table returns to the Chronicle. Knights' Hit Points are saved back to the Party.", "End combat")) {
        await post("/api/combat/end");
      }
    }

    // The barrage: rounds of missile fire before the lines meet. In a battle the
    // turn's barrage roll sets it; in free play the GM sets it here. While it
    // lasts the archers Loose and the knights can't reach them.
    const SHIELD_SIZES = [["none", "No shield", 0], ["small", "Small shield", 0], ["medium", "Medium shield", -5], ["large", "Large shield (kite)", -10]];
    function barrageBar(foes) {
      const archers = foes.some((c) => c.missile != null && !c.down);
      const b = cs.barrage;
      if (!archers && !b) return null;
      const setRounds = (e) => menu(e.currentTarget, [0, 1, 2, 3].map((n) => [n ? `${n} round${n === 1 ? "" : "s"} of fire before contact` : "No barrage — straight to contact",
        () => post("/api/combat/barrage", { rounds: n })]));
      if (!b) return h("div", { class: "row", style: { marginTop: "8px" } },
        h("button", { class: "btn ghost sm", title: "Missile foes: how many rounds do they shoot before the knights reach them?", onclick: setRounds }, icon("d6"), "Set a barrage…"));
      return h("div", { class: `banner cc ${b.active ? "barrage-on" : ""}` },
        b.active ? h("span", {}, `🏹 Barrage — round ${cs.round} of ${b.rounds} before contact. The knights can't reach the archers yet; each archer looses at the knight it faces, and a hit on a rider lands on the horse on 1–4.`)
          : h("span", {}, `Contact — the barrage (${b.rounds} round${b.rounds === 1 ? "" : "s"}) is over.`),
        bt ? null : h("button", { class: "linkish", onclick: setRounds }, "change"));
    }
    function shieldChip(k) {
      const cur = SHIELD_SIZES.find((x) => x[0] === (k.shield_size || "large")) || SHIELD_SIZES[3];
      return h("button", { class: "chip-shield", title: "The shield this knight raises against missiles: its size sets the archers' penalty (Table 9.4). Click to change.",
        onclick: (e) => menu(e.currentTarget, SHIELD_SIZES.map(([size, label, pen]) => [`${size === cur[0] ? "• " : ""}${label}${pen ? ` · archers ${pen}`.replace("-", "−") : ""}`,
          () => size !== cur[0] && post(`/api/combat/${k.id}/shield`, { size })])) },
        icon("shield"), cur[2] ? `${cur[2]}`.replace("-", "−") + " to archers" : cur[1]);
    }
    async function looseOne(c) {
      const adj = adjust.get(c.id) || 0;
      adjust.delete(c.id);
      const r = await post(`/api/combat/${c.id}/loose`, { adjust: adj });
      ctx.showLastRoll(r.blow || r.event);
      toast(r.hit ? `${c.display_name} hits${r.where === "mount" ? " the horse" : ""}` : `${c.display_name} misses`, r.hit ? "err" : "ok");
    }
    async function volley(k, n) {
      const r = await post(`/api/combat/${k.id}/volley`, {});
      ctx.showLastRoll(r.event);
      toast(`${k.display_name}: ${r.shots} shot${r.shots === 1 ? "" : "s"}, ${r.hits} hit${r.hits === 1 ? "" : "s"}${r.mounts ? ` (${r.mounts} on the horse)` : ""}${r.rider_damage ? ` · ${r.rider_damage} damage` : ""}`, r.hits ? "err" : "ok");
    }
    async function looseAll(type) {
      const r = await post("/api/combat/loose-all", { type });
      toast(`${type}: ${r.shots} shot${r.shots === 1 ? "" : "s"}, ${r.hits} hit${r.hits === 1 ? "" : "s"}${r.mounts ? ` (${r.mounts} on horses)` : ""}`, r.hits ? "err" : "ok");
    }

    // Banners for a battle fight: barrage, countercharge.
    function battleBanners() {
      const t = bt.t || {};
      const bits = [];
      if (t.countercharge) bits.push(t.countercharge.yes ? "↯ They countercharge!" : "No countercharge — lances spent");
      if (t.barrage) bits.push(t.barrage.rounds ? `Barrage: ${t.barrage.rounds} round${t.barrage.rounds === 1 ? "" : "s"} before contact` : "No barrage — straight into contact");
      return bits.length ? h("div", { class: "banner cc" }, bits.map((x) => h("span", {}, x))) : null;
    }

    const byName = (n) => cs.combatants.find((o) => o.display_name === n);

    // ------------------------------------------------------------ an enemy attacks a knight
    // Core p.133 Table 7.1: roll the enemy's attack, then the GM clicks the
    // knight's result; the app decides whether the enemy's blow lands.
    const OUT = { critical: "Critical", success: "Success", failure: "Failure", fumble: "Fumble" };

    // One pane for the whole exchange: weapon → knight → roll → the knight's
    // result → verdict (and the Hit dialog if the knight won). The knight is
    // chosen BEFORE the roll, so Height and the Fray name the right one.
    async function attackDialog(c, i, adj = 0) {
      const knights = cs.combatants.filter((o) => o.side === "party" && !o.down);
      if (!knights.length) return toast("No knights in the fight", "err");
      const stance = c.stance || "attack", st = STANCE[stance];
      const defensive = stance !== "attack" && stance !== "trample";
      const broken = new Set(c.broken || []);
      const S = { weapon: i ?? wieldedOf(c)[0], target: (byName(c.engaged_with)?.side === "party" ? byName(c.engaged_with) : knights[0]).id,
        adjust: adj, roll: null, result: null, done: new Set() };
      const dodging = stance === "dodge" && (c.linked || []).length > 1;
      await modal(`${c.display_name} ${st.verb}`, (close) => {
        const box = h("div", { class: "atk-pane" });
        const draw = () => {
          const rolled = !!S.roll, resolved = !!S.result;
          const weaponChips = h("div", { class: "chips" },
            c.attacks.map((a, k) => h("button", { class: `chip ${S.weapon === k ? "on" : ""} ${broken.has(k) ? "dis" : ""}`, disabled: rolled || broken.has(k) || null,
              title: broken.has(k) ? `${a.weapon} is broken` : a.skill === "Charge" ? "The charge weapon: breaks on a partial success or tie, Table 7.2 on a fumble" : "",
              onclick: () => { S.weapon = k; draw(); } }, `${a.weapon} ${skillDisplay(a.value)}`, h("span", { class: "faint" }, ` · ${a.damage}`), a.skill === "Charge" ? " ⚡" : "", broken.has(k) ? " ✗" : "")),
            h("button", { class: `chip ${S.weapon === "brawl" ? "on" : ""}`, disabled: rolled || null, onclick: () => { S.weapon = "brawl"; draw(); } }, `Brawling ${c.brawl?.value ?? "—"}`, h("span", { class: "faint" }, ` · ${c.brawl?.damage || "—"}`)));
          const knightChips = h("div", { class: "chips" }, knights.map((k) => h("button", { class: `chip ${k.id === S.target ? "on" : ""} ${S.done.has(k.id) ? "done" : ""}`, disabled: (rolled && !dodging) || S.done.has(k.id) || null,
            onclick: () => { S.target = k.id; draw(); } }, k.display_name, c.engaged_with === k.display_name ? h("span", { class: "faint" }, " · engaged") : null, S.done.has(k.id) ? " ✓" : "")));
          const adjIn = h("input", { class: "input num adj-in", placeholder: "±", value: S.adjust || "", disabled: rolled || null, title: "Any other modifier for this roll only",
            oninput: (e) => { const v = e.target.value.trim(); S.adjust = /^[+-]?\d+$/.test(v) ? Number(v) : 0; } });
          const d = S.roll?.data;
          const rollLine = d ? h("div", { class: "attack-roll" }, `${d.label} ${d.shown}: rolled `, h("b", {}, d.roll), " — ", h("b", { class: `o-${d.outcome}` }, OUT[d.outcome])) : null;
          const ok = d && (d.outcome === "critical" || d.outcome === "success");
          const go = async (knight) => {
            const r = await post("/api/combat/attack", { event: S.roll.id, target: S.target, knight });
            if (r.blow) ctx.showLastRoll(r.blow);
            if (r.prompt?.kind === "table72") toast(`${r.prompt.name} fumbled the lance: roll Horsemanship on Table 7.2 — critical: no harm · success: 1D6 splinters · failure: thrown, 2D6 · fumble: horse down too, 3D6 (armour does not protect)`, "err");
            S.result = { verdict: r.event.data.verdict, knightHits: r.result === "knight" || (r.result === "tie" && stance === "attack"), shield: r.knight_shield, target: S.target };
            S.done.add(S.target);
            if (dodging) {
              const left = knights.filter((k) => !S.done.has(k.id) && (c.linked || []).includes(k.display_name));
              if (left.length) S.target = left[0].id;
            }
            draw();
          };
          const results = d && !resolved ? h("div", {},
            h("div", { class: "label" }, `${byId(S.target)?.display_name || "The knight"}'s result`),
            h("div", { class: "knight-results" },
              h("button", { class: "btn", onclick: () => go("critical") }, "Critical"),
              ...(d.outcome === "success"
                ? [h("button", { class: "btn", onclick: () => go("higher") }, `Success — beat ${d.roll}`),
                   h("button", { class: "btn", onclick: () => go("equal") }, `Success — equal ${d.roll}`),
                   h("button", { class: "btn", onclick: () => go("lower") }, `Success — under ${d.roll}`)]
                : [h("button", { class: "btn", onclick: () => go("higher") }, "Success")]),
              h("button", { class: "btn", onclick: () => go("failure") }, "Fail"),
              h("button", { class: "btn danger", onclick: () => go("fumble") }, "Fumble")),
            !ok ? h("div", { class: "faint small", style: { marginTop: "8px" } }, `${c.display_name} missed — the knight can still win the exchange.`) : null) : null;
          const verdict = resolved ? h("div", { class: "verdict-box" },
            h("div", { class: "label" }, "Verdict"), h("div", { class: "verdict-text" }, S.result.verdict),
            S.result.knightHits ? h("div", { class: "faint small" }, `${byId(S.result.target)?.display_name} struck ${c.display_name}: enter the damage.`) : null) : null;
          const more = resolved && dodging && knights.some((k) => !S.done.has(k.id) && (c.linked || []).includes(k.display_name));
          clear(box,
            defensive ? h("div", { class: "hint" }, st.hint, dodging ? " — the same roll is set against each knight in turn." : "") : null,
            h("div", { class: "label" }, "Weapon"), weaponChips,
            h("div", { class: "label", style: { marginTop: "8px" } }, "Against"), knightChips,
            !rolled ? h("div", { class: "row", style: { marginTop: "10px" } },
              h("button", { class: "btn primary", onclick: async () => {
                adjust.delete(c.id);
                S.roll = (await post(`/api/combat/${c.id}/roll`, { what: "attack", key: S.weapon, adjust: S.adjust, target: S.target })).event;
                ctx.showLastRoll(S.roll); draw();
              } }, icon("d20"), defensive ? st.label : c.attacks[S.weapon]?.skill === "Charge" ? "Charge!" : "Roll the attack"),
              h("span", { class: "faint small" }, "modifier"), adjIn,
              h("span", { class: "faint small" }, "Height, outnumbered and the stance are worked out at the roll.")) : null,
            rollLine, results, verdict,
            more ? h("div", { class: "hint" }, `Now ${byId(S.target)?.display_name}'s result against the same roll.`) : null,
            more && S.roll ? (() => { S.result = null; return null; })() : null,
            h("div", { class: "foot" },
              resolved && S.result.knightHits ? h("button", { class: "btn primary", onclick: () => { close(); hitDialog(c, S.result.shield); } }, icon("shield"), "Enter the knight's hit") : null,
              h("button", { class: resolved ? "btn" : "btn ghost", onclick: () => close() }, resolved ? "Done" : "Cancel")));
        };
        draw();
        return box;
      }, { wide: true });
    }

    // ------------------------------------------------------------ a knight hits an enemy
    async function hitDialog(c, shieldDefault = false) {
      await modal(`Hit ${c.display_name}`, (close) => {
        const dmg = h("input", { class: "input", type: "number", min: 0, placeholder: "damage the player rolled" });
        const shield = h("input", { type: "checkbox", checked: shieldDefault });
        const apply = async () => {
          if (dmg.value === "") return dmg.focus();
          const r = await act("/api/combat/blow", { target: c.id, damage: dmg.value, shield: shield.checked });
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

    // The foe's sheet: everything the card says, including the flavour and the
    // way it fights ("they flee once a third are down") — shown, not enforced.
    function foeSheet(c) {
      const kv = (label, value) => value === undefined || value === null || value === "" ? null
        : h("div", { class: "fs-kv" }, h("span", { class: "fs-k" }, label), h("span", { class: "fs-v" }, value));
      const eng = (c.linked || []).length ? c.linked.join(", ") : "nobody";
      const ransom = Array.isArray(c.ransom) && c.ransom.length ? c.ransom.map((r) => `${r.type || ""} ${r.amount || ""}`.trim()).join(" · ") : null;
      modal(c.display_name, (close) => [
        h("div", { class: "fs-sub" }, [c.type !== c.display_name ? c.type : null, c.category !== "human" ? c.category : null,
          c.elite ? `champion (${c.promotion_title || "elite"})` : null, c.wound_state, `fighting ${eng}`].filter(Boolean).join(" · ")),
        c.description ? h("p", { class: "fs-flavour" }, c.description) : null,
        c.notes && c.notes !== c.description ? h("div", { class: "fs-notes" }, h("span", { class: "label" }, "How they fight"), h("p", {}, c.notes)) : null,
        h("div", { class: "fs-stats" }, statLine(c, false)),
        h("div", { class: "fs-grid" },
          kv("Hit Points", `${c.cur_hp} / ${c.max_hp}`), kv("Knockdown", c.knockdown), kv("Major Wound", c.major_wound), kv("Unconscious", c.unconscious),
          kv("Armour", c.armour_text), kv("Movement", c.movement || null), kv("Glory", c.glory),
          kv("Knight Value", c.knight_value || null), kv("Minimum Morale", c.morale_minimum), kv("Morale Loss", c.morale_loss || null),
          kv("Valorous", c.valorous), kv("Ransom", ransom), kv("Culture", c.culture || null), kv("Religion", c.religion || null),
          kv("Looks", c.looks || null)),
        h("div", { class: "row", style: { marginTop: "10px", alignItems: "center" } },
          h("span", { class: "faint small" }, "Situational modifier on every roll"), modInput(c),
          h("span", { class: "sp" }), h("button", { class: "btn ghost", onclick: () => close() }, "Close")),
      ], { wide: true });
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
        () => act(`/api/combat/${c.id}/status`, { out: c.status === "unconscious" || c.status === "dead" ? null : "unconscious" }), { icon: "heart" }]);
      if (c.status !== "dead") items.push(["Slay", () => act(`/api/combat/${c.id}/status`, { out: "dead" }), { icon: "x" }]);
      if (!isKnight && c.status !== "surrendered") items.push(["Surrenders", () => act(`/api/combat/${c.id}/status`, { out: "surrendered" }), { icon: "flag" }]);
      if (!isKnight) {
        items.push(null);
        items.push([c.mounted ? "Dismount (on foot)" : "Mount (mounted)", () => post(`/api/combat/${c.id}/mounted`, { mounted: !c.mounted }), { icon: "shield" }]);
        items.push([c.prone ? "Back on their feet" : "Knocked prone", () => post(`/api/combat/${c.id}/prone`, { on: !c.prone })]);
        items.push([c.attacks_horse ? "Stop attacking the horse" : "Attacking the horse", () => post(`/api/combat/${c.id}/horse`, { on: !c.attacks_horse })]);
        items.push([c.height_override ? "Height: automatic" : "Height: negated (spear/halberd)", () => post(`/api/combat/${c.id}/height`, { override: c.height_override ? null : "none" })]);
        if (["unconscious", "surrendered"].includes(c.status)) items.push(...captiveMenu(c));
      }
      items.push([c.status === "fled" ? "Reactivate (resume tracking)" : "Driven off / fled (Glory)",
        () => act(`/api/combat/${c.id}/status`, { out: c.status === "fled" ? null : "fled" }), { icon: "flag" }]);
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
      if (reset || evs.some((e) => e.type.startsWith("combat.") || e.type.startsWith("glory.") || e.type.startsWith("battle.") || e.type.startsWith("meta."))) refreshSoon();
    });

    await loadLibrary();
    await refresh();
    return {
      async show() { await loadLibrary(); await refresh(); },
      async onLibrary() { await loadLibrary(); if (!cs?.active) render(); },
    };
  },
};
