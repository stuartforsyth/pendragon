// Combat tracker: launch an encounter (the Party joins automatically), then
// run it — HP, wounds, engagements, situational modifiers, click-to-roll,
// promotion, surrender and ransom. Every change is an event; strike one in the
// log to undo it.

import { h, clear, api, post, icon, menu, modal, toast, useCss, confirmBox, skillDisplay,
  CHAR_FULL, CHAR_ORDER, debounce } from "../lib.js";
import { moraleStrip } from "../components.js";
import { knightShield } from "../board.js";

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
      const note = h("input", { class: "input", placeholder: "Round note — e.g. the bridge collapses", style: { flex: 1 },
        onkeydown: async (e) => { if (e.key === "Enter" && e.target.value.trim()) { await post("/api/combat/note", { text: e.target.value }); e.target.value = ""; } } });
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
          h("div", { class: "row", style: { marginTop: "10px" } },
            h("span", { class: "tag gules" }, `${up} of ${foes.length} foes standing`),
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
    const FOE_GLYPH = {
      human: '<path d="M50 22v40M42 58h16M50 62v14" stroke="currentColor" stroke-width="6" stroke-linecap="round"/><path d="M50 18l5 9h-10z" fill="currentColor"/>',
      beast: '<path d="M30 70c4-14 8-30 12-40M46 72c2-16 4-32 6-44M62 70c0-14-1-28-2-40" stroke="currentColor" stroke-width="6" stroke-linecap="round" fill="none"/>',
      monster: '<path d="M26 70c8-4 10-14 4-20s-4-16 6-20 22 2 24 12-6 14-2 20 14 6 18-2" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round"/><circle cx="40" cy="31" r="3.5" fill="currentColor"/>',
      fae: '<path d="M50 20l7 22h23l-18 13 7 22-19-14-19 14 7-22-18-13h23z" fill="currentColor"/>',
    };
    function foeFace(c) {
      const pct = Math.max(0, Math.min(1, c.cur_hp / Math.max(1, c.max_hp)));
      const R = 46, C = 2 * Math.PI * R, col = pct > .5 ? "#79b585" : pct > .25 ? "#d4a84b" : "#d0574b";
      const s = document.createElement("span");
      s.className = "ftok-face";
      s.innerHTML = `<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="40" class="medal"/>` +
        `<g class="glyph">${FOE_GLYPH[c.category] || FOE_GLYPH.human}</g>` +
        `<circle cx="50" cy="50" r="${R}" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="6"/>` +
        `<circle cx="50" cy="50" r="${R}" fill="none" stroke="${col}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${C * pct} ${C}" transform="rotate(-90 50 50)"/></svg>`;
      return s;
    }
    let dragging = null;             // { id, side } while a token is dragged
    function ftok(c, x, y) {
      const knight = c.side === "party";
      const node = h("div", { class: `ftok ${knight ? "is-knight" : "is-foe"} ${!knight && c.engaged_with ? "engaged" : ""} ${c.down ? "down" : ""} ${c.elite ? "elite" : ""} ${picked === c.id ? "picked" : ""}`,
        "data-id": c.id, style: { left: `${x}px`, top: `${y}px` }, title: knight ? "Click for controls · drag onto a foe to engage" : "Click for controls · drag onto a knight to engage",
        onclick: () => { picked = picked === c.id ? null : c.id; render(); } },
        knight ? h("span", { class: "ftok-face" }, knightShield(c.down)) : foeFace(c),
        h("span", { class: "ftok-name" }, c.display_name),
        h("span", { class: "ftok-sub" }, knight ? (c.down ? (c.status === "fled" ? "Out of the fight" : "Down") : c.mounted ? "Mounted" : "On foot")
          : `${c.cur_hp}/${c.max_hp}${c.wound_state && c.wound_state !== "Unhurt" ? " · " + c.wound_state : ""}${c.wielding === "brawl" ? " · Disarmed" : ""}`));
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
      const W = Math.max(640, (el.querySelector(".cbt-field")?.clientWidth) || el.clientWidth || 960);
      const live = foes.filter((f) => !f.down && (f.linked || []).length);
      // engagements = knights joined through the foes they share
      const seen = new Set(), groups = [];
      for (const k of knights) {
        if (seen.has(k.id)) continue;
        const g = { ks: [], fs: [] }, todo = [k];
        while (todo.length) {
          const x = todo.pop();
          if (seen.has(x.id)) continue;
          seen.add(x.id);
          if (x.side === "party") {
            g.ks.push(x);
            live.filter((f) => f.linked.includes(x.display_name)).forEach((f) => todo.push(f));
          } else {
            g.fs.push(x);
            knights.filter((kk) => x.linked.includes(kk.display_name)).forEach((kk) => todo.push(kk));
          }
        }
        groups.push(g);
      }
      // Lay out each engagement around (0,0), then flow them across the field
      // like words in a paragraph, each taking only the room it needs.
      const ring = (list, r, start, sy = .85) => list.map((t, j) => {
        const a = start + (2 * Math.PI * j) / list.length;
        return [t, r * Math.cos(a), r * sy * Math.sin(a)];
      });
      const shape = (g) => {
        let pos;
        if (g.ks.length === 1) {
          const n = g.fs.length;
          pos = [[g.ks[0], 0, 0], ...ring(g.fs, 92 + Math.max(0, n - 6) * 9, n === 2 ? Math.PI : Math.PI / 2)];
        } else {
          const shared = g.fs.filter((f) => f.linked.filter((n) => g.ks.some((k) => k.display_name === n)).length > 1);
          const R = shared.length ? 135 : 0;
          pos = [...(shared.length === 1 ? [[shared[0], 0, 0]] : ring(shared, 48, Math.PI / 2))];
          g.ks.forEach((k, i) => {
            const th = Math.PI + (2 * Math.PI * i) / g.ks.length, kx = R * Math.cos(th), ky = R * .8 * Math.sin(th);
            pos.push([k, kx, ky]);
            const own = g.fs.filter((f) => !shared.includes(f) && f.linked.includes(k.display_name));
            own.forEach((f, j) => {
              const a = th + (j - (own.length - 1) / 2) * 1.05;
              pos.push([f, kx + 110 * Math.cos(a), ky + 110 * .9 * Math.sin(a)]);
            });
          });
        }
        const xs = pos.map((p) => p[1]), ys = pos.map((p) => p[2]);
        const box = { x0: Math.min(...xs) - 68, x1: Math.max(...xs) + 68, y0: Math.min(...ys) - 34, y1: Math.max(...ys) + 50 };
        return { pos, w: box.x1 - box.x0, h: box.y1 - box.y0, box };
      };
      const shapes = groups.map(shape), rowsOf = [[]];
      let x = 0;
      for (const sh of shapes) {
        if (x + sh.w > W - 16 && rowsOf.at(-1).length) { rowsOf.push([]); x = 0; }
        rowsOf.at(-1).push(sh); x += sh.w + 12;
      }
      const tokens = [], lines = [];
      let y = 12;
      for (const row of rowsOf) {
        const rowW = row.reduce((t, sh) => t + sh.w, 0) + 12 * (row.length - 1), rowH = Math.max(...row.map((sh) => sh.h));
        let ox = (W - rowW) / 2;
        for (const sh of row) {
          const cx = ox - sh.box.x0, cy = y + (rowH - sh.h) / 2 - sh.box.y0;
          sh.pos.forEach(([t, dx, dy]) => tokens.push(ftok(t, cx + dx, cy + dy)));
          ox += sh.w + 12;
        }
        y += rowH + 14;
      }
      groups.forEach((g) => g.fs.forEach((f) => g.ks.forEach((k) => { if (f.linked.includes(k.display_name)) lines.push([k.id, f.id]); })));
      const height = Math.max(240, y + 6);

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
      stage.addEventListener("dragover", (e) => { if (dragging?.side === "knight") e.preventDefault(); });
      stage.addEventListener("drop", (e) => {                     // a knight dropped on open ground breaks off
        if (dragging?.side !== "knight" || e.target.closest(".ftok")) return;     // a knight on a knight does nothing
        e.preventDefault();
        const k = byId(dragging.id);
        if (k) post("/api/combat/unlink", { knight: k.display_name });
      });
      const drawLinks = () => {
        const box = stage.getBoundingClientRect();
        const centre = (id) => { const f = stage.querySelector(`.ftok[data-id="${id}"] .ftok-face`); if (!f) return null;
          const b = f.getBoundingClientRect(); return [b.left - box.left + b.width / 2, b.top - box.top + b.height / 2]; };
        svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
        svg.innerHTML = '<defs><filter id="cbt-glow" filterUnits="userSpaceOnUse" x="0" y="0" width="${box.width}" height="${box.height}"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>' +
          lines.map(([a, b]) => { const p = centre(a), q = centre(b); return p && q ? `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" class="cbt-link" filter="url(#cbt-glow)"/>` : ""; }).join("");
      };
      requestAnimationFrame(drawLinks);
      const ro = new ResizeObserver(() => { if (!stage.isConnected) return ro.disconnect(); drawLinks(); });
      ro.observe(stage);
      const pick = picked && byId(picked);
      return [h("div", { class: "cbt-field-wrap" }, stage, pick ? drawer(pick, foes) : null), wait];
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
          h("span", { class: "cbt-lane-slots" },
            k.mo?.n > 1 ? h("span", { class: `chip-mo ${k.mo.over ? "warn" : ""}`,
              title: k.mo.over ? `More than ${k.mo.limit} ${k.mo.limit === 2 ? "mounted foes" : "foes on foot"} can't all attack one knight` : "Multiple Opponents: the knight applies this to each opponent" },
              `⚠ ${k.mo.n} foes · −${-k.mo.mod} vs each`) : null,
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
      const line = h("div", { class: `cbt-foe t-${tone} ${open ? "open" : ""}`, "data-id": c.id },
        h("div", { class: "cbt-foe-line" },
          h("button", { class: "cbt-foe-name", title: open ? "Hide details" : "Show stats, armour and modifier",
            onclick: () => { open ? openFoes.delete(c.id) : openFoes.add(c.id); render(); } },
            c.npc ? icon("helm", "npc-ico") : marker ? h("span", { class: "marker" }, marker) : null, c.display_name),
          h("div", { class: "cbt-hp" },
            h("div", { class: "hp-bar big" }, h("i", { class: hpTone, style: { width: `${pct}%` } })),
            h("span", { class: "hp-text" }, h("b", {}, c.cur_hp), h("span", { class: "faint" }, ` / ${c.max_hp}`),
              c.wound_state ? h("span", { class: "ws faint" }, ` · ${c.wound_state}`) : null)),
          h("span", { class: "cbt-chips" }, foeChips(c)),
          h("button", { class: `cbt-target ${c.engaged_with ? "set" : ""}`, title: "Who is this foe fighting?",
            onclick: (e) => targetMenu(e.currentTarget, c) }, `→ ${c.engaged_with || "nobody"} ▾`),
          weaponCell(c),
          h("button", { class: "btn sm hit-btn", title: `A knight hit ${c.display_name}: enter the damage rolled`, onclick: () => hitDialog(c) }, icon("shield"), "Hit"),
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
    function weaponCell(c) {
      const [key, a] = wieldedOf(c);
      const disarmed = key === "brawl";
      const noSkill = a?.value == null;
      const knightsIn = cs.combatants.some((o) => o.side === "party");
      return h("span", { class: "cbt-wield" },
        h("button", { class: `cbt-weapon ${disarmed ? "disarmed" : ""}`, title: disarmed ? "Disarmed — click to pick a weapon back up" : "The weapon in hand — click to switch, or mark Disarmed",
          onclick: (e) => weaponMenu(e.currentTarget, c, key) },
          disarmed ? "✋ " : "⚔ ", h("span", { class: "wn" }, a?.weapon || "Brawling"), " ",
          h("b", {}, noSkill ? "—" : skillDisplay(a.value)), h("span", { class: "faint" }, ` · ${a?.damage || "—"}`),
          disarmed ? h("span", { class: "tag gules" }, "Disarmed") : null, " ▾"),
        c.outnumbered ? h("span", { class: "tag gules out-tag", title: `${c.linked.length} knights on it: −5 per knight after the first, on its attack rolls` },
          `${c.outnumbered}`.replace("-", "−") + " outnumbered") : null,
        h("input", { class: "input num adj-in", placeholder: "±", value: adjust.get(c.id) ?? "", title: "Any other modifier for this foe's next attack roll only",
          oninput: (e) => { const v = e.target.value.trim(); /^[+-]?\d+$/.test(v) ? adjust.set(c.id, Number(v)) : adjust.delete(c.id); } }),
        h("button", { class: "btn sm atk-btn", disabled: c.down || noSkill || null,
          title: noSkill ? "No Brawling skill — set one in the Adversaries editor" : `${c.display_name} attacks ${c.engaged_with || "a knight"} with ${a.weapon}`,
          onclick: () => {
            const adj = adjust.get(c.id) || 0;                   // one roll, then the box clears
            adjust.delete(c.id); render();
            return knightsIn ? attackDialog(c, key, adj)
              : post(`/api/combat/${c.id}/roll`, { what: "attack", key, adjust: adj }).then((r) => { ctx.showLastRoll(r.event); render(); });
          } },
          icon("swords"), "Attack"));
    }
    function weaponMenu(anchor, c, current) {
      const wield = (w) => w !== current && post("/api/combat/wield", { cid: c.id, wield: w });
      const b = c.brawl || {};
      menu(anchor, [
        ...c.attacks.map((a, i) => [`${i === current ? "• " : ""}${a.weapon} ${skillDisplay(a.value)} · ${a.damage}`, () => wield(i)]),
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

    async function attackDialog(c, i, adj = 0) {
      const knights = cs.combatants.filter((o) => o.side === "party" && !o.down);
      if (!knights.length) return toast("No knights in the fight", "err");
      let target = (byName(c.engaged_with)?.side === "party" ? byName(c.engaged_with) : knights[0]).id;
      const roll = (await post(`/api/combat/${c.id}/roll`, { what: "attack", key: i, adjust: adj })).event;
      ctx.showLastRoll(roll);
      const d = roll.data, ok = d.outcome === "critical" || d.outcome === "success";
      const go = async (knight, close) => {
        const r = await post("/api/combat/attack", { event: roll.id, target, knight });
        if (r.blow) ctx.showLastRoll(r.blow);
        toast(r.event.data.verdict, "ok");
        close();
        if (r.result === "knight" || r.result === "tie") hitDialog(c, r.knight_shield);
      };
      const chips = h("div", { class: "chips" });
      const againstChips = () => clear(chips, knights.map((k) => h("button", { class: `chip ${k.id === target ? "on" : ""}`,
        onclick: () => { target = k.id; againstChips(); } }, k.display_name)));
      await modal(`${c.display_name} attacks`, (close) => [
        h("div", { class: "attack-roll" }, `${d.label} ${d.shown}: rolled `, h("b", {}, d.roll), " — ",
          h("b", { class: `o-${d.outcome}` }, OUT[d.outcome])),
        h("div", { class: "field", style: { margin: "12px 0" } }, h("span", {}, "Against"), againstChips()),
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
