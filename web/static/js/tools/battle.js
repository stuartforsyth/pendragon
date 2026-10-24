// Battle tool: launch a battle (quick or saved), resume a paused one, muster
// the conroi, then run it — Morale strip with tokens, knight chips, live
// settings, new encounters mid-battle. The turn stepper arrives in S7.
// Players roll and resolve at the table; the GM records outcomes here.

import { h, clear, api, post, icon, modal, confirmBox, toast, useCss, debounce, menu } from "../lib.js";
import { cardFace, statFace } from "../cardface.js";
import { dayCard, deckPicker, outcomeChips, amountEntry, moraleStrip, knightChip, examplesBanner, POS_LABEL, launchBattle } from "../components.js";

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

    let pending = false;           // an update arrived while the GM was typing
    function render() {
      if (el.querySelector(".bl input:focus, .bl textarea:focus")) { pending = true; return; }
      pending = false;
      const live = b && ["mustering", "turn", "rear"].includes(b.status);
      clear(body, h("div", { class: "bl" }, b?.status === "aftermath" ? aftermathPanel()
        : !live ? launchPanel() : b.status === "mustering" ? mustering() : running()));
    }

    // One banner per render; it checks the library itself and hides when up to date.
    let bannerEl = null;
    const banner = () => (bannerEl ||= examplesBanner({ onAdded: () => { bannerEl = null; toast("Battle cards added", "ok"); load(); } }));

    // A paused battle lives in a saved session: Duplicate copies that session (the battle gets a fresh id),
    // Delete bins it (sessions/.trash — a file you can move back, not oblivion).
    async function duplicateBattle(p) {
      const r = await post("/api/battle/duplicate", { battle_id: p.battle_id, session_id: p.session_id });
      toast(`Copied to “${r.session.title}”`, "ok");
      load();
    }
    async function binBattle(p) {
      if (!await confirmBox("Delete this battle?", `“${p.session_title}” — the whole session, battle and log — goes to the bin folder, sessions/.trash, and can no longer be resumed from here.`, "Delete it", true)) return;
      await api(`/api/sessions/${encodeURIComponent(p.session_id)}`, { method: "DELETE" });
      toast("Moved to the bin", "ok");
      load();
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
        banner(),
        rows.length ? h("div", { class: "panel" }, h("h3", {}, "Paused battles"),
          rows.map((p) => h("div", { class: "bl-row" },
            h("span", {}, h("b", {}, p.name), ` · Day ${p.day} · Turn ${p.turn}`, p.morale ? ` · Morale ${p.morale[0]} / ${p.morale[1]}` : "",
              h("span", { class: "faint small" }, ` · ${p.session_title}`)),
            h("span", { class: "row", style: { gap: "6px" } },
              h("button", { class: "btn primary sm", onclick: () => post("/api/battle/resume", { battle_id: p.battle_id, session_id: p.session_id }) }, icon("play"), "Resume"),
              p.session_id === session.id ? null : [
                h("button", { class: "btn ghost sm", title: "Copy this battle to a new session — to test on, the original stays as it is", onclick: () => duplicateBattle(p) }, icon("copy"), "Duplicate"),
                h("button", { class: "btn ghost sm danger", title: "Bin this session and the battle in it", onclick: () => binBattle(p) }, icon("x"), "Delete")])))) : null,
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
            h("button", { class: "btn primary", style: { marginTop: "12px" }, onclick: () => launchBattle({ quick: { ...quick } }) }, icon("banner"), "Launch battle")),
          h("div", { class: "panel" }, h("h3", {}, "Saved battles"),
            saved.length ? h("div", { class: "list" }, saved.map((s) => h("div", { class: "list-item bl-saved" },
              h("span", {}, h("b", {}, s.key), h("span", { class: "faint small" }, ` · ${SIZES[s.size]?.label || s.size} · ${s.days} day${s.days === 1 ? "" : "s"}`)),
              h("button", { class: "btn sm", onclick: () => launchBattle({ key: s.key }) }, icon("play"), "Launch"))))
              : h("p", { class: "faint" }, "Prepare battles in the Battles tool."))),
      ];
    }

    // ------------------------------------------------------------ mustering
    function mustering() {
      const S = SIZES[b.definition.size];
      const day = b.day, days = b.days, dd = b.day_def;
      const active = party.filter((m) => m.active !== false || b.conroi.includes(m.id));
      if (!muster.knights) muster.knights = b.conroi.length ? [...b.conroi] : active.filter((m) => !m.away).map((m) => m.id);
      if (muster.commander === null) muster.commander = b.commander || null;     // yesterday's, on a later day
      if (muster.start === "" && b.morale) muster.start = b.morale.start;
      const whyNot = () => !muster.commander ? "Set a commander" : !(Number(muster.start) >= 1) ? "Enter the starting Morale"
        : b.intensity_today == null && dd.intensity?.mode !== "fixed" ? "Set today's Intensity" : "";
      const reason = whyNot();
      // Typing the Morale updates the Begin button in place — a full redraw on
      // leaving the box would swallow the click that moved the cursor away.
      const beginBtn = h("button", { class: "btn primary", disabled: !!reason || null, onclick: () => begin() }, day > 1 ? `Begin Day ${day} ▸` : "Begin Turn 1 ▸");
      const beginWhy = h("span", { class: "faint small" }, reason || "Ready: commander and Morale are set.");
      const refreshBegin = () => { const r = whyNot(); beginBtn.disabled = !!r; beginWhy.textContent = r || "Ready: commander and Morale are set."; };
      const begin = async () => {
        const reason = whyNot();
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
        (() => {
          const ids = muster.knights.filter((p) => b.knights[p]);
          const allFoot = ids.length && ids.every((p) => !b.knights[p].mounted);
          return ids.length ? h("div", { class: "row", style: { marginTop: "6px" } },
            h("button", { class: "btn sm", onclick: () => post("/api/battle/mounted", { mounted: allFoot, pids: ids }) }, allFoot ? "All mounted" : "All on foot"),
            h("span", { class: "faint small" }, b.day > 1 ? "Horses carry over from yesterday — click a pill for a knight who lost or found one." : "Click a pill for any knight who starts on foot.")) : null;
        })(),
        h("div", { class: "label", style: { marginTop: "8px" } }, "Commander"),
        h("div", { class: "chips" },
          [...active.filter((m) => muster.knights.includes(m.id)).map((m) => [m.id, m.name]), ["gm", "GM (NPC)"]].map(([id, name]) =>
            h("button", { class: `chip ${muster.commander === id ? "on" : ""}`, onclick: () => { muster.commander = id; render(); } }, name))),
        h("div", { class: "row", style: { alignItems: "flex-end", marginTop: "8px" } },
          h("label", { class: "field" }, h("span", {}, "Starting Morale"),
            h("input", { class: "input big-num", type: "number", min: 1, value: muster.start, oninput: (e) => { muster.start = e.target.value; refreshBegin(); },
              onkeydown: (e) => e.key === "Enter" && begin() })),
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
            h("button", { class: "btn ghost sm", onclick: pause }, "Pause"),
            b.turn === 0 && b.day === 1 ? h("button", { class: "btn ghost sm", title: "Launched by mistake? Call it off — nothing has been played yet", onclick: async () => {
              if (await confirmBox("Call off the battle?", "It hasn't begun, so nothing is lost. The Battle tool goes back to Launch.", "Call it off", true)) await post("/api/battle/abandon");
            } }, "Call it off") : null)),
        dd.notes ? h("div", { class: "hint bl-daynotes" }, h("b", {}, `Day ${day} (GM only): `), dd.notes) : null,
        h("div", { class: "grid2" }, conroi, h("div", { class: "stack" }, army, intensity)),
        h("div", { class: "row" }, beginBtn, beginWhy),
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
        moraleStrip(b, { onAdjust: adjustMorale, onCommander: changeCommander, onToken: tokenHint }),
        h("div", { class: "kchips" }, b.knight_list.filter((k) => b.conroi.includes(k.pid)).map((k) =>
          knightChip(k, { onMounted: () => post(`/api/battle/knight/${k.pid}`, { mounted: !k.mounted }), onPosition: positionMenu }))),
        b.minus5 && b.turn === 1 ? h("div", { class: "bl-reminder" }, "−5 Battle this turn for the whole army (Army Commander fumbled).") : null,
        b.day_def.notes ? h("div", { class: "hint bl-daynotes" }, h("b", {}, `Day ${b.day} (GM only): `), b.day_def.notes) : null,
        b.status === "rear" ? rearPanel() : stepper(),
      ];
    }

    // ------------------------------------------------------------ aftermath (#gm-after)
    const OUTCOMES = [["decisive_victory", "Decisive Victory"], ["victory", "Victory"], ["indecisive", "Indecisive"], ["defeat", "Defeat"], ["decisive_defeat", "Decisive Defeat"]];
    const OPPONENTS = [["feudal", "Feudal army · £2"], ["inferior", "Inferior feudal army · £1½"], ["saxons", "Saxons · £1"], ["cymric", "Cymric hill tribes · £½"], ["picts_irish", "Picts or Irish · £¼"]];
    const patchSoon = debounce((patch) => post("/api/battle/aftermath", { patch }), 350);
    function aftermathPanel() {
      const a = b.aftermath;
      const num = (val, onset, attrs = {}) => h("input", { class: "input num", value: val, onchange: (e) => onset(e.target.value), ...attrs });
      const sel = (opts, val, onset) => h("select", { class: "input", onchange: (e) => onset(e.target.value || null) },
        opts.map(([v, l]) => h("option", { value: v ?? "", selected: (v ?? "") === (val ?? "") }, l)));
      const outcomeCol = h("div", { class: "panel" }, h("h3", {}, "Outcome"),
        h("div", { class: "kv" },
          h("span", {}, "Enemy losses (dead + captured)"), h("span", {}, num(a.enemy_kv, (v) => patchSoon({ enemy_kv: v }), { style: { width: "80px" } }), " KV"),
          h("span", {}, "Player knights killed or captured"), num(a.friendly_pk_losses, (v) => patchSoon({ friendly_pk_losses: Number(v) || 0 })),
          h("span", {}, "GM knights in the conroi"), num(a.gm_knights, (v) => patchSoon({ gm_knights: Number(v) || 0 })),
          a.gm_knights ? [h("span", {}, "Their losses (Table 6.5 roll)"), outcomeChips({ value: a.gm_losses_roll, onPick: (o) => patchSoon({ gm_losses_roll: o }) })] : null,
          h("span", {}, "Friendly losses"), h("b", {}, `${a.friendly_kv} KV`),
          h("span", {}, "Outnumbering"), sel([["none", "none"], ["we", "we outnumbered them 2:1"], ["they", "they outnumbered us 2:1"]], a.outnumber, (v) => patchSoon({ outnumber: v || "none" })),
          h("span", {}, "Ratio"), h("b", {}, a.ratio ?? "—")),
        h("div", { class: "result" }, a.outcome_label),
        a.zero_ruling ? h("div", { class: "hint" }, h("span", { class: "tag purpure rule-gr", title: "The book divides by friendly losses" }, "GM ruling"), " No friendly losses: any enemy loss is a Decisive Victory, none is Indecisive.") : null,
        a.small_plus ? h("label", { class: "field" }, h("span", {}, `Outcome — the book leaves Small battles and larger to the story (suggested: ${OUTCOMES.find((o) => o[0] === a.computed)[1]})`),
          sel([[null, "Use the suggestion"], ...OUTCOMES], b.aftermath_patch?.outcome_choice || b.definition.outcome, (v) => patchSoon({ outcome_choice: v }))) : null,
        h("div", { class: "hint" }, "Computed from KV. Every number above is editable."));
      const gloryCol = h("div", { class: "panel" }, h("h3", {}, "Glory"),
        h("table", { class: "gt" }, h("thead", {}, h("tr", {}, ["Knight", "Role", "Days", "Encounters", "Participation", "Total"].map((x) => h("th", {}, x)))),
          h("tbody", {}, a.knights.map((k) => h("tr", {},
            h("td", {}, k.name),
            h("td", {}, sel([[null, "—"], ["conroi", "conroi ×2"], ["bataille", "bataille ×3"], ["army", "army ×5"]], k.role, (v) => patchSoon({ roles: { ...(b.aftermath_patch?.roles || {}), [k.pid]: v } }))),
            h("td", {}, num(k.days, (v) => patchSoon({ days_fought: { ...(b.aftermath_patch?.days_fought || {}), [k.pid]: Number(v) || 0 } }), { style: { width: "54px" } })),
            h("td", { class: "n" }, k.encounter_glory), h("td", { class: "n" }, k.working), h("td", { class: "tot" }, k.total))))),
        h("div", { class: "hint" }, "Participation: Table 6.6 base × (outcome + leader). ", a.days > 1 ? [h("span", { class: "tag or rule-sr", title: "The Sword Campaign treats each day as its own engagement" }, "Scenario rule"), " × days fought."] : null));
      const spoilsCol = h("div", { class: "panel" }, h("h3", {}, "Spoils"),
        ["victory", "decisive_victory"].includes(a.outcome) ? [
          h("label", { class: "field" }, h("span", {}, "Opponents (Table 6.9)"), sel(OPPONENTS, a.opponents, (v) => patchSoon({ opponents: v || "feudal" }))),
          a.outcome === "decisive_victory" ? h("div", { class: "row" }, h("span", {}, "Decisive +£2D3"),
            num(a.decisive_roll ?? "", (v) => patchSoon({ decisive_roll: Number(v) || null })),
            h("button", { class: "btn ghost sm", onclick: () => post("/api/battle/aftermath/roll", { what: "decisive" }) }, icon("d6"), "roll for me")) : null,
          h("div", { class: "kv" }, a.knights.map((k) => [h("span", {}, k.name), h("b", {}, k.plunder || "—")])),
        ] : h("p", { class: "faint" }, `No plunder (${a.outcome_label}).`),
        h("div", { class: "label", style: { marginTop: "8px" } }, "Captives"),
        a.captives.length ? h("div", { class: "kv" }, a.captives.map((c) => [h("span", {}, `${c.name} — ${c.captor_name}`),
          c.ransom ? h("button", { class: "btn sm", onclick: () => post("/api/battle/ransom", { fight: c.fight, cid: c.cid }) }, "Roll ransom") : h("span", { class: "faint" }, "no ransom table")]))
          : h("p", { class: "faint small" }, "No captives taken."));
      return [
        h("div", { class: "bhead" }, h("span", { class: "bl-title" }, b.definition.name || "Battle"),
          h("span", { class: "faint" }, `Aftermath · ${a.size_label} · ${a.days} day${a.days === 1 ? "" : "s"}`),
          h("span", { class: "sp" },
            h("button", { class: "btn primary", onclick: () => post("/api/battle/finale") }, a.finale ? "Post again ▸" : "Post to Table ▸"),
            a.finale ? h("button", { class: "btn", onclick: async () => { if (await confirmBox("End the battle?", "It moves to the log; the Table returns to the Chronicle.", "End battle")) post("/api/battle/end"); } }, "End battle") : null)),
        h("div", { class: "cols3" }, outcomeCol, gloryCol, spoilsCol),
      ];
    }

    // ------------------------------------------------------------ the turn stepper
    // Answering a step completes it; done steps collapse to their result and
    // can be reopened (cascade undo). Matches the approved #gm-turn mockup.
    const NUM = { field: "①", set: "②", charge: "③", intensity: "④", picks: "⑤", select: "⑥", morale: "⑦", opportunity: "★", postures: "⑧", fight: "⑨", rest: "☾", end: "⑩" };
    const NAME = { field: "Field or rear", set: "Set Encounter", charge: "Charge", intensity: "Intensity", picks: "Picks", select: "Commander's choice",
      morale: "Morale", opportunity: "Play the Opportunity", postures: "Postures", fight: "Fight", rest: "Rest at the rear", end: "End turn" };
    const OUT_WORD = { critical: "critical", success: "success", failure: "failed", fumble: "fumble" };
    const ui = { pickCard: null, choosing: false, forceArmed: false, flavour: null, postures: {}, lastUndo: null, turnKey: "", opp: null, flipped: new Set() };
    const knightName = (pid) => b.knight_list.find((k) => k.pid === pid)?.name || "A knight";
    const cardOf = (key) => decks.find((c) => c.key === key) || b.cards?.[key] || { key };
    // Recording an outcome releases the cursor, so the stepper can redraw (it
    // holds off while someone is typing in one of its boxes).
    const step = (stepKey, extra = {}) => { document.activeElement?.blur?.(); return post("/api/battle/step", { step: stepKey, ...extra }); };

    function summary(key) {
      const t = b.t;
      switch (key) {
        case "set": return t.set ? [h("b", {}, t.set.encounter), t.set.flavour ? h("em", {}, ` · “${t.set.flavour}”`) : null, t.set.forced ? h("span", { class: "tag gules" }, "forced") : null] : "";
        case "opportunity": return t.opportunity ? [h("b", {}, b.chosen.encounter), " resolved", (t.awards || []).length ? ` · ${t.awards.reduce((n, a) => n + a.amount, 0)} Glory in ${t.awards.length} award${t.awards.length === 1 ? "" : "s"}` : ""] : "";
        case "charge": return !t.charge ? "" : t.charge.skipped ? "not rolled — no charge possible"
          : { may_charge_plus5: "Charge! (+5, mounted)", may_charge: "may charge (mounted)", no_charge: "no charge", enemy_charge: "Enemy knights charge!" }[t.charge.result];
        case "intensity": return t.intensity ? [`Intensity: `, h("b", { class: `o-${t.intensity.outcome}` }, OUT_WORD[t.intensity.outcome]),
          { doubled: " — foes doubled", stands: " — the Encounter stands", choose: " — knights may choose", opportunity: " — an Opportunity" }[t.intensity.result]] : "";
        case "picks": return Object.entries(t.picks).map(([pid, p]) => `${knightName(pid)}${p.crit ? " (crit)" : ""}: ${p.encounter}`).join(" · ") || "no picks";
        case "select": return t.select ? [h("b", {}, t.select.encounter), t.select.card?.role === "opportunity" ? " ★ must be played" : ""] : "";
        case "morale": return !t.morale ? "" : t.morale.kind === "forced_retire" ? "Not enough Morale — retired" : t.morale.negated ? "Loss negated (token)" : t.morale.amount ? `−${t.morale.amount} Morale` : "No Morale lost";
        case "postures": return Object.entries(t.postures).map(([pid, p]) => `${knightName(pid)} ${p.posture}`).join(" · ");
        case "rest": return t.rest != null ? `+${t.rest} Morale` : "";
        case "field": return t.retired ? "Retired to the Rear" : "";
        case "fight": return t.fight ? `${t.fight.encounter}: ${t.fight.defeated} of ${t.fight.foes} defeated` : "";
        default: return "";
      }
    }

    function stepper() {
      const tk = `${b.day}.${b.turn}`;
      // A new turn (or day) resets the stepper's scratch state, including the
      // "Undone … Restore" offer: restoring a past turn's steps would no longer fit.
      if (ui.turnKey !== tk) Object.assign(ui, { pickCard: null, choosing: false, forceArmed: false, flavour: null, postures: {}, lastUndo: null, turnKey: tk, opp: null });
      const items = b.step.items;
      const rows = [];
      for (const it of items) {
        if (it.key === "intensity" && rows.length && rows.at(-1).dataset?.key === "charge") continue;   // drawn in the shared row
        rows.push(stepRow(it, items));
      }
      return h("div", { class: "stepper" },
        ui.lastUndo ? h("div", { class: "bl-undone" }, ui.lastUndo.text, " · ", h("button", { class: "linkish", onclick: async () => {
          await post(`/api/battle/undo/${ui.lastUndo.id}/restore`); ui.lastUndo = null; } }, "Restore")) : null,
        b.inconsistent?.length ? h("div", { class: "bl-inconsistent" }, h("span", { class: "tag gules" }, "Doesn't add up"),
          ` An earlier step was struck, so ${b.inconsistent.length} later entr${b.inconsistent.length === 1 ? "y is" : "ies are"} ignored. Reopen the step to redo it.`) : null,
        rows,
        b.step.current === "set" ? h("div", { class: "row" }, h("button", { class: "btn danger sm", onclick: () => step("retire") }, "Retire to the Rear instead"),
          turnScriptsInline()) : null);
    }

    function stepRow(it, items) {
      const row = (state, num, name, res, extra) => h("div", { class: `step ${state}`, "data-key": it.key },
        h("div", { class: "row" }, h("span", { class: "n" }, num), h("span", { class: "nm" }, name), h("span", { class: "res" }, res), extra || h("span")));
      // ③ and ④ share one row (approved UX choice 3)
      if (it.key === "charge") {
        const inten = items.find((x) => x.key === "intensity");
        const st = [it.state, inten.state];
        const cur = st.includes("current");
        const allDone = st.every((x) => x === "done" || x === "skipped");
        const res = [it.state === "skipped" ? h("em", {}, it.reason) : summary("charge") ? ["Charge: ", summary("charge")] : h("em", {}, "commander's charge roll"), " · ",
          inten.state === "skipped" ? h("em", {}, inten.reason) : summary("intensity") || h("em", {}, "Intensity roll")];
        if (cur) return h("div", { class: "step cur", "data-key": "charge" },
          h("div", { class: "row" }, h("span", { class: "n" }, "③④"), h("span", { class: "nm" }, "Charge · Intensity"), h("span", { class: "res" }, ""), h("span")),
          h("div", { class: "body" }, chargeIntensityBody(it, inten)));
        return row(allDone ? "done" : "todo", "③④", "Charge · Intensity", res,
          allDone ? reopenBtn(it.state === "done" ? "charge" : "intensity") : null);
      }
      if (it.state === "done") return row("done", NUM[it.key], NAME[it.key], summary(it.key), reopenBtn(it.key));
      if (it.state === "skipped") return row("skip", NUM[it.key], NAME[it.key], h("em", {}, it.reason));
      if (it.state === "current" || (it.state === "optional" && b.step.current === it.key)) {
        return h("div", { class: "step cur", "data-key": it.key },
          h("div", { class: "row" }, h("span", { class: "n" }, NUM[it.key]), h("span", { class: "nm" }, NAME[it.key]), h("span", { class: "res" }, ""), h("span")),
          h("div", { class: "body" }, stepBody(it.key)));
      }
      const hint = { set: "", opportunity: "played at the table, then its Glory", picks: "picks from a failed Intensity roll", select: "the commander chooses", morale: "minimum check, then the Loss",
        postures: b.prev_postures && Object.keys(b.prev_postures).length ? `last turn: ${Object.entries(b.prev_postures).map(([p, v]) => `${knightName(p)} ${v}`).join(" · ")}` : "",
        fight: "Begin the fight → combat tracker", end: `KV Morale gain, then Turn ${b.turn + 1}` }[it.key] || "";
      return row(it.state === "optional" ? "todo" : "todo", NUM[it.key], NAME[it.key], h("em", {}, hint));
    }

    function reopenBtn(key) {
      return h("button", { class: "re linkish", title: "Undo this step and everything after it this turn", onclick: async () => {
        const p = await api(`/api/battle/undo-preview?step=${key}`);
        if (p.locked) return toast("Made before the battle was resumed — correct it with a Morale override instead", "err");
        if (!(await confirmBox(`Undo from ${NAME[key]}?`, p.targets.map((t) => `• ${t.text}`).join("\n"), "Undo", true))) return;
        const r = await post("/api/battle/undo", { step: key });
        ui.lastUndo = { id: r.event.id, text: r.event.text };
      } }, "reopen");
    }

    // Put a card over the Table so everyone reads it together (and take it off again).
    const showBtn = (name, cls = "ct-show") => h("button", { class: cls, "aria-label": "Show on the Table",
      title: ctx.spot === name ? "Take it off the Table" : "Show this card big on the Table",
      onclick: (e) => { e.stopPropagation(); return ctx.spot === name ? post("/api/spotlight/off") : post("/api/spotlight", { kind: "card", name }); } },
      icon("present"));

    // A whole printed card to choose from: the front (what the players are told), flipped
    // with the corner toggle to the back (the stat block) — no physical card needed.
    function cardTile(key, c, onPick, onHover) {
      const faces = c.faces || { front: [], back: [] };
      const flipped = ui.flipped.has(key);
      const tile = h("div", { class: `ct ${flipped ? "flipped" : ""}`, role: "button", tabindex: 0, title: `Set ${key} as this turn's Encounter`,
        onclick: onPick, onmouseenter: onHover, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } } },
        h("div", { class: "ct-inner" },
          h("div", { class: "ct-face" }, (faces.front.length ? faces.front : [{ title: key, flavour: c.description || "", blocks: [] }]).slice(0, 1).map((f) => cardFace(f))),
          h("div", { class: "ct-face ct-back" }, faces.back.length ? faces.back.map((f) => statFace(f)).slice(0, 1) : h("div", { class: "ct-noback" }, "No stat block for this card."))),
        faces.back.length > 1 ? h("span", { class: "ct-more" }, `+${faces.back.length - 1} more on the back`) : null,
        showBtn(key),
        h("button", { class: "ct-flip", title: flipped ? "Show the front" : "Flip to the stat block", "aria-label": "Flip the card",
          onclick: (e) => { e.stopPropagation(); ui.flipped.has(key) ? ui.flipped.delete(key) : ui.flipped.add(key); tile.classList.toggle("flipped");
            e.currentTarget.title = ui.flipped.has(key) ? "Show the front" : "Flip to the stat block"; } }, "⟳"));
      return h("div", { class: "ct-wrap" }, tile, h("div", { class: "ct-meta" }, gmMeta(c)));
    }

    function gmMeta(c) {
      return h("span", { class: "cm" }, c.role === "opportunity" ? `min ${c.morale_minimum ?? "—"} · loss ${c.morale_loss || "0"}`
        : `min ${c.morale_minimum ?? "—"} · loss ${c.morale_loss || "—"} · KV ${c.kv_per_knight ?? "?"}`);
    }

    // Today's deck from the server: script-restricted, and an empty day deck
    // means every battle Foe and Opportunity in the library.
    function deckKeys(role) {
      const deck = b.deck_now || { foes: [], opportunities: [] };
      return (role === "opportunity" ? deck.opportunities : deck.foes) || [];
    }

    function turnScriptsInline() {
      const sc = (b.day_def.scripts || []).map((x, i) => ({ ...x, i })).filter((x) => x.turn === b.turn);
      if (!sc.length) return null;
      const shown = (i) => b.revealed_scripts.some((r) => r.day === b.day && r.index === i);
      return h("div", { class: "bl-inline-scripts" }, sc.map((x) => h("span", { class: "hint" }, "Turn script (GM only): ", h("b", {}, `“${x.text}”`),
        x.if_intensity ? h("span", { class: "faint small" }, " — shown to players after a successful Intensity roll")
          : h("button", { class: "linkish", disabled: shown(x.i) || null, onclick: () => post("/api/battle/script", { day: b.day, index: x.i }) }, shown(x.i) ? " on the Table" : " Show on Table"))));
    }

    function stepBody(key) {
      switch (key) {
        case "set": return setBody();
        case "picks": return picksBody();
        case "select": return selectBody();
        case "morale": return moraleBody();
        case "opportunity": return opportunityBody();
        case "postures": return posturesBody();
        case "fight": return fightBody();
        case "rest": return restBody();
        case "end": return endButtons();
        default: return null;
      }
    }

    function setBody() {
      const keys = deckKeys("foe");
      if (b.morale.current <= 0) {
        return [h("div", { class: "bl-reminder" }, "Morale is 0 — the conroi must Retire to the Rear."),
          h("div", { class: "hint" }, "Rest there to recover Morale (1D6 a turn), or leave the field.")];
      }
      if (ui.flavour === null) ui.flavour = "";
      const missingBanner = banner();
      const fl = h("input", { class: "input", placeholder: "Flavour line for the Table (defaults to the card's description)", value: ui.flavour,
        oninput: (e) => { ui.flavour = e.target.value; } });
      const forceAvail = b.tokens.force === "available";
      return [
        missingBanner,
        keys.length ? h("div", { class: "ct-deck" }, keys.map((k) => cardTile(k, cardOf(k),
          () => step("set", { encounter: k, flavour: ui.flavour, forced: ui.forceArmed }),
          () => { if (!ui.flavour) fl.placeholder = cardOf(k).description || fl.placeholder; }))) : h("div", { class: "hint" }, "No battle Foes in your library yet — mark encounters as Foes in the Encounter Creator, add the battle cards with Encounters → Examples…, or ",
          h("button", { class: "linkish", onclick: quickEncounter }, "+ New encounter"), "."),
        b.deck_now?.all && keys.length ? h("div", { class: "faint small" }, "No deck set for today, so every battle Foe in your library is available. ",
          h("button", { class: "linkish", onclick: settingsDrawer }, "Choose today's deck")) : null,
        fl,
        h("div", { class: "row" },
          keys.length ? h("button", { class: "btn sm", title: "A random Foe from today's deck (not filtered by Morale)", onclick: () => step("set", { draw: true, flavour: ui.flavour, forced: ui.forceArmed }) }, icon("d6"), "Draw") : null,
          forceAvail ? h("label", { class: "check small" }, h("input", { type: "checkbox", checked: ui.forceArmed, onchange: (e) => { ui.forceArmed = e.target.checked; } }),
            "⚑ Force this Encounter (spends the token: no Intensity roll, no picks)") : null,
          h("button", { class: "linkish", onclick: settingsDrawer }, "Edit deck"), h("button", { class: "linkish", onclick: quickEncounter }, "+ New encounter")),
      ];
    }

    function chargeIntensityBody(ch, inten) {
      // Table 6.3: OUR commander rolls Battle — may the knights make a mounted
      // charge? Knights can charge foot troops; the foe's own charge only comes
      // in on a fumble. The GM can skip the roll when no charge is possible.
      const chargeLabel = h("div", { class: "label", title: "Table 6.3, Mounted Charge Opportunity: the conroi commander's Battle roll decides whether the knights may make a mounted charge this turn" },
        [h("span", { class: "tag or" }, "Conroi commander rolls"), " Commander's charge roll (Battle, mounted charge opportunity) — may the knights charge?"]);
      const allFoot = b.conroi_now.length && b.conroi_now.every((pid) => !b.knights[pid]?.mounted);
      const left = ch.state === "skipped" ? h("div", { class: "half skip" }, chargeLabel, h("em", {}, ch.reason))
        : ch.state === "done" ? h("div", { class: "half" }, chargeLabel, summary("charge"))
        : (() => {
          let engaged = b.fought_last;
          const tog = h("label", { class: "check small" }, h("input", { type: "checkbox", checked: engaged, onchange: (e) => { engaged = e.target.checked; } }), "Engaged last round");
          return h("div", { class: "half" }, chargeLabel,
            outcomeChips({ keys: true, onPick: (o) => step("charge", { outcome: o, engaged_last: engaged }) }), tog,
            h("div", { class: "row" },
              h("button", { class: "btn ghost sm", title: "No charge is possible this turn (ground, everyone on foot, the GM's call): record it without a roll", onclick: () => step("charge", { skip: true }) }, "Don't roll — no charge possible"),
              h("span", { class: "faint small" }, allFoot ? "Everyone is on foot: only a fumble (enemy knights charge) could matter — skip if the enemy has no knights."
                : "Mounted knights may charge foes on foot too; a fumble means enemy knights charge.")),
            b.minus5 && b.turn === 1 ? h("div", { class: "bl-reminder" }, "−5 Battle this turn") : null);
        })();
      const right = inten.state === "skipped" ? h("div", { class: "half skip" }, h("div", { class: "label" }, "GM's Intensity roll"), h("em", {}, inten.reason))
        : inten.state === "current" ? h("div", { class: "half" }, h("div", { class: "label" }, h("span", { class: "tag gules" }, "GM rolls"), ` Intensity roll against the battle's Intensity (${b.intensity_today}) — does the Encounter stand?`),
          h("div", { class: "row" }, h("button", { class: "btn primary sm", onclick: () => step("intensity", { roll_for_me: true }) }, icon("d20"), "Roll for me"),
            outcomeChips({ keys: ch.state !== "current", onPick: (o) => step("intensity", { outcome: o }) })))
        : h("div", { class: "half todo" }, h("div", { class: "label" }, "GM's Intensity roll (against the battle's Intensity)"), h("em", {}, "after the charge"));
      const lines = b.t.charge?.result ? b.conroi_now.map((pid) => `${knightName(pid)}: ${({ may_charge_plus5: "charges +5", may_charge: "may charge", no_charge: "no charge", enemy_charge: "enemy knights charge!" })[b.t.charge.result]}${b.knights[pid]?.mounted ? "" : " (on foot)"}`) : [];
      return [h("div", { class: "split2" }, left, right), lines.length ? h("div", { class: "hint" }, lines.join(" · ")) : null];
    }

    function picksBody() {
      const foes = deckKeys("foe"), opps = deckKeys("opportunity");
      const picks = b.t.picks;
      const tokensOn = (k) => Object.entries(picks).filter(([, p]) => p.encounter === k);
      const card = (k, opp) => {
        const c = cardOf(k);
        const spent = b.spent_opportunities.includes(k);
        const isSet = b.t.set?.encounter === k;
        return h("div", { class: `gcard ${opp ? "opp" : ""} ${spent ? "dis" : ""} ${isSet ? "set" : ""} ${ui.pickCard === k ? "picked" : ""}`,
          onclick: () => { if (!spent) { ui.pickCard = ui.pickCard === k ? null : k; render(); } } },
          h("span", { class: "cn" }, k), showBtn(k, "gc-show"), gmMeta(c), spent ? h("span", { class: "cm" }, "already played") : null,
          h("span", { class: "picks" }, tokensOn(k).map(([pid, p]) => h("button", { class: `ptok ${p.crit ? "crit" : ""}`, title: "Toggle critical, or remove",
            onclick: (e) => { e.stopPropagation(); menu(e.currentTarget, [
              [p.crit ? "Not a critical" : "Mark critical", () => step("pick", { knight: pid, encounter: k, crit: !p.crit })],
              ["Remove this pick", () => step("pick", { knight: pid, encounter: null })]]); } }, icon("shield"), knightName(pid).split(" ").slice(-1)[0], p.crit ? " · crit" : ""))));
      };
      const c = ui.pickCard ? cardOf(ui.pickCard) : null;
      const isOpp = c && opps.includes(ui.pickCard);
      return [
        h("div", { class: "hint" }, "Tap a card, then the knight who picked it. Only successful Battle rolls count."),
        h("div", { class: "cards" }, foes.map((k) => card(k, false)), opps.map((k) => card(k, true))),
        ui.pickCard ? h("div", { class: "row" }, h("span", { class: "hint" }, `${ui.pickCard} — picked by:`),
          b.conroi_now.map((pid) => [
            !isOpp ? h("button", { class: "btn sm", onclick: () => { step("pick", { knight: pid, encounter: ui.pickCard, crit: false }); ui.pickCard = null; } }, knightName(pid)) : null,
            h("button", { class: "btn sm crit", onclick: () => { step("pick", { knight: pid, encounter: ui.pickCard, crit: true }); ui.pickCard = null; } }, `${knightName(pid)} · crit`)])) : null,
        h("div", { class: "hint" }, h("b", {}, "Opportunities"), " unlock only for a pick marked crit.",
          c?.morale_minimum != null ? [" ", h("b", {}, ui.pickCard), ` needs Morale ${c.morale_minimum} — the conroi has ${b.morale.current} ${b.morale.current >= c.morale_minimum ? "✓" : "✗"}`] : null),
        h("div", { class: "row" },
          h("button", { class: "btn primary", onclick: commanderChooses }, "Commander chooses ▸"),
          !Object.keys(picks).length ? h("button", { class: "btn ghost sm", onclick: () => step("select", { via: "keep" }) }, "No picks — keep the set Encounter") : null),
        ui.choosing ? selectBody() : null,
      ];
    }

    function candidates() {
      const set = b.t.set?.encounter;
      const picked = [...new Set(Object.values(b.t.picks).map((p) => p.encounter))];
      const opps = picked.filter((k) => cardOf(k).role === "opportunity" || deckKeys("opportunity").includes(k));
      return opps.length ? opps : [...new Set([set, ...picked])];
    }

    function commanderChooses() {
      if (!Object.keys(b.t.picks).length) return step("select", { via: "keep" });
      const cs = candidates();
      if (cs.length === 1) return step("select", { encounter: cs[0], via: "commander" });       // §14.5
      ui.choosing = true; render();
    }

    function selectBody() {
      const io = b.t.intensity?.outcome;
      if (b.t.charge?.result === "enemy_charge") {
        const eligible = deckKeys("foe").filter((k) => cardOf(k).mounted_charge);
        return [h("div", { class: "bl-reminder" }, "Enemy knights charge you! No countercharge, no choosing."),
          h("div", { class: "hint" }, "On foot: enemy +5 Height; Set Spear possible with a spear."),
          h("div", { class: "cards" }, eligible.map((k) => h("button", { class: "gcard", onclick: () => step("select", { encounter: k, via: "enemy_charge" }) }, h("span", { class: "cn" }, k), gmMeta(cardOf(k)))))];
      }
      if (io === "fumble") {
        const opps = deckKeys("opportunity").filter((k) => !b.spent_opportunities.includes(k));
        return [h("div", { class: "hint" }, "Intensity fumble: an Opportunity of your choice — or keep the set Encounter."),
          h("div", { class: "cards" }, opps.map((k) => h("button", { class: "gcard opp", onclick: () => step("select", { encounter: k, via: "fumble" }) }, h("span", { class: "cn" }, k), gmMeta(cardOf(k))))),
          h("button", { class: "btn ghost sm", onclick: () => step("select", { via: "fumble" }) }, `Keep ${b.t.set.encounter}`)];
      }
      const cs = candidates();
      const mustOpp = cs.some((k) => deckKeys("opportunity").includes(k));
      return [mustOpp ? h("div", { class: "hint" }, "An Opportunity was picked — it must be played.") : null,
        h("div", { class: "cards" }, cs.map((k) => {
          const c = cardOf(k);
          const ok = b.morale.current >= (c.morale_minimum || 0);
          return h("button", { class: `gcard ${deckKeys("opportunity").includes(k) ? "opp" : ""}`, onclick: () => step("select", { encounter: k, via: "commander" }) },
            h("span", { class: "cn" }, k), showBtn(k, "gc-show"), gmMeta(c), h("span", { class: `cm ${ok ? "ok" : "bad"}` }, ok ? "within Morale ✓" : "below Minimum ✗"));
        }))];
    }

    function moraleBody() {
      const c = b.chosen?.card || {};
      const min = c.morale_minimum || 0;
      const ok = b.morale.current >= min && b.morale.current > 0;
      if (!ok) return [h("div", { class: "hint" }, `GM only: Morale ${b.morale.current} < Minimum ${min} ✗`),
        h("button", { class: "btn danger", onclick: () => step("morale", { kind: "forced_retire" }) }, "Not enough Morale — Retire to the Rear")];
      return [
        h("div", { class: "hint" }, `GM only: Morale ${b.morale.current} ≥ Minimum ${min} ✓ — ${b.chosen.encounter}`),
        c.morale_loss ? amountEntry({ dice: c.morale_loss, min: 0, max: 99, placeholder: `Loss (${c.morale_loss})`,
          onEnter: (v) => step("morale", { kind: "loss", amount: v }), rollForMe: () => step("morale", { kind: "loss", roll_for_me: true }) })
          : h("button", { class: "btn", onclick: () => step("morale", { kind: "loss", amount: 0 }) }, "No Morale Loss"),
        b.tokens.negate === "available" ? h("button", { class: "token glow", onclick: () => step("morale", { kind: "loss", negate: true }) }, "✋ Negate this loss (token)") : null,
      ];
    }

    const PST = [["reckless", "R", 3], ["valorous", "V", 2], ["prudent", "P", 1], ["cowardly", "K", 0]];
    function posturesBody() {
      const firstCharge = b.first_charge_turn;
      const ks = b.conroi_now.filter((pid) => !b.t.postures[pid]);
      for (const pid of ks) ui.postures[pid] ||= { posture: b.prev_postures?.[pid] || null, amount: "", above: false };
      const confirm = async () => {
        for (const pid of ks) {
          const p = ui.postures[pid];
          if (!p.posture) return toast(`Choose ${knightName(pid)}'s posture`, "err");
          if (firstCharge && !["reckless", "valorous"].includes(p.posture)) return toast("The first charge allows only Reckless or Valorous", "err");
          if ((p.posture === "reckless" || p.posture === "prudent") && !p.amount) return toast(`Enter ${knightName(pid)}'s 1D3`, "err");
          if (p.posture === "cowardly" && p.above && !p.amount) return toast(`Enter ${knightName(pid)}'s 1D6`, "err");
        }
        for (const pid of ks) {
          const p = ui.postures[pid];
          await step("posture", { knight: pid, posture: p.posture, amount: p.amount ? Number(p.amount) : null, above_half: p.posture === "cowardly" ? p.above : null });
        }
      };
      const onFoot = b.conroi_now.some((pid) => !b.knights[pid]?.mounted);
      return [
        firstCharge ? h("div", { class: "hint" }, "First charge: Reckless or Valorous only.", onFoot ? [" ", h("span", { class: "tag purpure rule-gr", title: "The book assumes everyone is mounted on the first charge" }, "GM ruling"), " mounted knights must charge; knights on foot fight normally."] : null) : null,
        ks.map((pid) => {
          const p = ui.postures[pid];
          const dice = { reckless: "1D3 gain", prudent: "1D3 loss", cowardly: "1D6 loss" }[p.posture];
          return h("div", { class: "posture-row" }, h("span", { class: "kn" }, knightName(pid)),
            h("div", { class: "chips" }, PST.map(([key, letter, rounds]) => h("button", {
              class: `chip ${p.posture === key ? "on" : ""} ${b.prev_postures?.[pid] === key ? "prev" : ""}`, disabled: (firstCharge && !["reckless", "valorous"].includes(key)) || null,
              title: `${key} — ${rounds} round${rounds === 1 ? "" : "s"}`, onclick: () => { p.posture = key; render(); } }, `${letter} · ${rounds}`))),
            p.posture === "cowardly" ? h("label", { class: "check small" }, h("input", { type: "checkbox", checked: p.above, onchange: (e) => { p.above = e.target.checked; render(); } }), "above half HP?") : null,
            dice && (p.posture !== "cowardly" || p.above) ? h("input", { class: "input num", type: "number", min: 1, max: p.posture === "cowardly" ? 6 : 3, placeholder: dice, value: p.amount,
              oninput: (e) => { p.amount = e.target.value; } }) : null,
            passionToggle(pid));
        }),
        h("div", { class: "faint small" }, "Trait checks: Reckless / Valorous / Prudent · Cowardly: −1 Honor (on paper)."),
        h("button", { class: "btn primary", onclick: confirm }, "Confirm postures"),
      ];
    }

    function passionToggle(pid) {
      const k = b.knights[pid] || {};
      return h("label", { class: "check small", title: "Once per battle day" }, h("input", { type: "checkbox", checked: !!k.passion_used, onchange: async (e) => {
        await step("passion", { knight: pid, used: e.target.checked, name: b.passion || "" });
      } }), "Passion used");
    }

    function fightBody() {
      const t = b.t, c = b.chosen?.card || {};
      const out = [];
      if (t.fight && t.fight.active) {
        return [h("div", { class: "hint" }, `Fighting ${t.fight.encounter}: ${t.fight.defeated} of ${t.fight.foes} defeated.`),
          h("button", { class: "btn primary", onclick: () => ctx.navigate("combat") }, icon("swords"), "Back to the fight")];
      }
      if (c.missile) {
        out.push(h("div", { class: "half" }, h("div", { class: "label" }, "Barrage — the commander's Battle roll"),
          t.barrage ? h("span", {}, t.barrage.rounds ? `${t.barrage.rounds} round${t.barrage.rounds === 1 ? "" : "s"} of arrows before contact` : "Straight into contact")
            : outcomeChips({ keys: true, onPick: (o) => step("barrage", { outcome: o }) })));
      }
      if (c.countercharge) {
        out.push(h("div", { class: "half" }, h("div", { class: "label" }, "Countercharge"),
          b.turn === 1 ? h("span", {}, "They countercharge! ", h("span", { class: "tag or rule-sr", title: "The book: on the first Battle Turn. Each day of a multi-day battle counts as a new first turn." }, "Scenario rule"))
            : t.countercharge ? h("span", {}, t.countercharge.yes ? "They countercharge!" : "No countercharge — lances spent")
            : amountEntry({ dice: "1D6", min: 1, max: 6, placeholder: "1D6: 1–2 yes", onEnter: (v) => step("countercharge", { roll: v }), rollForMe: () => step("countercharge", { roll_for_me: true }) })));
      }
      const ready = (!c.missile || t.barrage) && (!c.countercharge || b.turn === 1 || t.countercharge);
      if (t.fight && !t.fight.active) out.push(h("div", { class: "hint" }, `Fought ${t.fight.encounter}: ${t.fight.defeated} of ${t.fight.foes} defeated.`));
      out.push(h("div", { class: "row" },
        !t.fight ? h("button", { class: "btn primary", disabled: !ready || null, onclick: async () => { await post("/api/battle/fight"); ctx.navigate("combat"); } },
          icon("swords"), `Begin the fight${b.t.intensity?.outcome === "critical" ? " (foes doubled)" : ""} → combat tracker`) : null,
        endButtons()));
      return out;
    }

    // An Opportunity is played offline: the card's instructions are on the Table; here is
    // the whole card (stats too) and, once it's over, the Glory printed on it.
    function opportunityBody() {
      const o = b.opportunity;
      if (!o) return null;
      const sel = ui.opp ||= { all: false, knights: new Set(), amount: "", reason: "" };
      const redraw = render;
      const fillFrom = (r) => { sel.amount = String(r.amount); sel.reason = r.label; sel.all = r.scope === "all"; if (sel.all) sel.knights.clear(); };
      const award = async () => {
        const knights = sel.all ? "all" : [...sel.knights];
        if (!sel.all && !knights.length) return toast("Choose who receives the Glory", "err");
        const ok = await post("/api/battle/step", { step: "opportunity_glory", knights, amount: Number(sel.amount), reason: sel.reason }).catch(() => null);
        if (ok) Object.assign(sel, { amount: "", reason: "" });
      };
      const chip = (label, on, onclick, cls = "") => h("button", { class: `chip ${on ? "on" : ""} ${cls}`, onclick }, label);
      return [
        h("div", { class: "row" }, h("button", { class: `btn sm ${ctx.spot === o.name ? "primary" : ""}`,
          onclick: () => ctx.spot === o.name ? post("/api/spotlight/off") : post("/api/spotlight", { kind: "card", name: o.name }) },
          icon("present"), ctx.spot === o.name ? "Remove from Table" : "Show on Table")),
        h("div", { class: "hint" }, h("b", {}, o.name), " is played at the table — no postures, no combat tracker. The players read the card on the Table; the stats are yours."),
        h("div", { class: "cf-gm" }, o.front.map((f) => cardFace(f)), o.back.map((f) => statFace(f))),
        h("div", { class: "opp-glory" },
          h("div", { class: "label" }, "Resolve — award Glory"),
          o.rewards.length ? h("div", { class: "row wrap" }, o.rewards.map((r) =>
            h("button", { class: "btn ghost sm", title: r.scope === "all" ? "Every knight with the conroi" : "One knight at a time",
              onclick: () => { fillFrom(r); redraw(); } }, `+${r.amount} ${r.label}`))) : h("div", { class: "faint small" }, "No Glory is printed on this card — enter an amount."),
          h("div", { class: "row wrap" }, h("span", { class: "faint small" }, "To"),
            chip("All with the conroi", sel.all, () => { sel.all = !sel.all; sel.knights.clear(); redraw(); }),
            b.conroi_now.map((pid) => chip(knightName(pid), !sel.all && sel.knights.has(pid), () => {
              sel.all = false; sel.knights.has(pid) ? sel.knights.delete(pid) : sel.knights.add(pid); redraw(); }))),
          h("div", { class: "row" },
            h("input", { class: "input num", type: "number", placeholder: "Glory", value: sel.amount, oninput: (e) => { sel.amount = e.target.value; } }),
            h("input", { class: "input", placeholder: "What for", value: sel.reason, oninput: (e) => { sel.reason = e.target.value; }, style: { flex: 1 } }),
            h("button", { class: "btn", onclick: award }, icon("star"), "Award Glory")),
          o.awards.length ? h("ul", { class: "opp-awards" }, o.awards.map((a) =>
            h("li", {}, `${a.amount > 0 ? "+" : ""}${a.amount} Glory · ${knightName(a.knight)} — ${a.reason}`))) : null),
        h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => step("opportunity_done") }, "Done — back to the turn's end"))];
    }

    function restBody() {
      return [h("div", { class: "hint" }, "The commander rolls 1D6 at the table. Morale can't rise above its start."),
        amountEntry({ dice: "1D6", min: 1, max: 6, onEnter: (v) => step("rest", { amount: v }), rollForMe: () => step("rest", { roll_for_me: true }) }),
        h("div", { class: "faint small" }, "First Aid 14+1D6 per knight (on paper) · a new horse → flip the knight's pill.")];
    }

    function endButtons() {
      const last = b.turn >= b.turns_today;
      const gain = b.kv_gain || 0;
      return h("div", { class: "row" },
        gain ? h("span", { class: "hint" }, `Foes defeated → Morale +${gain} `, h("span", { class: "tag purpure rule-gr", title: "Fractions of Knight Value round half up per Encounter" }, "GM ruling")) : null,
        h("span", { class: "hint" }, last ? `Last turn of Day ${b.day}.` : `Then Turn ${b.turn + 1}.`),
        h("button", { class: "btn primary", onclick: () => step(last ? "end_day" : "end_turn") }, last ? (b.day >= b.days ? "End the last day" : "End day") : "End turn"));
    }

    function rearPanel() {
      const t = b.t;
      if (!t.rear_choice) return h("div", { class: "panel" }, h("h3", {}, "The conroi is at the rear"),
        turnScriptsInline(),
        h("div", { class: "row" },
          h("button", { class: "btn primary", onclick: () => step("rear", { choice: "rest" }) }, "Rest another turn"),
          h("button", { class: "btn", onclick: () => step("rear", { choice: "return" }) }, "Return to the field"),
          h("button", { class: "btn danger", onclick: async () => { if (await confirmBox("Leave the field?", "The conroi's part in the battle ends.", "Leave", true)) step("rear", { choice: "leave" }); } }, "Leave the field")),
        h("div", { class: "faint small" }, "First Aid 14+1D6 per knight (on paper) · a new horse → flip the knight's pill."));
      return stepper();
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

    // Where a knight is. Only knights with the conroi take postures and fight
    // the Encounter; a Cowardly knight goes to the rear and comes back from here.
    function positionMenu(k, anchor) {
      const POS_HINT = { conroi: "", rear: "escorting captives, resting, remounting", alone: "fights alone: Battle −10, still drains Morale", left: "out of the battle" };
      menu(anchor, Object.entries(POS_LABEL).map(([pos, label]) => [
        `${label}${pos === (k.position || "conroi") ? " ✓" : ""}${POS_HINT[pos] ? ` — ${POS_HINT[pos]}` : ""}`,
        () => pos !== (k.position || "conroi") && post(`/api/battle/knight/${k.pid}`, { position: pos })]));
    }

    function tokenHint(key) {
      toast(key === "force" ? "Spend it at ② Set Encounter: tick “Force this Encounter”." : "Spend it at ⑦ Morale: “Negate this loss”.", "ok");
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
    // Live settings: everything about the battle stays editable while it runs —
    // the battle itself, the conroi, today's Intensity and army rolls, and the
    // days (today and later; past days are locked).
    async function settingsDrawer() {
      const edits = {};
      const det = { name: b.definition.name || "", where: b.definition.where || "", against: b.definition.against || "", notes: b.definition.notes || "", size: b.definition.size };
      const running = ["turn", "rear"].includes(b.status);
      const con = { knights: [...b.conroi], passion: b.passion || "", start: b.morale?.start ?? "" };
      const dayIntensity = { value: b.intensity_today ?? "" };
      await modal("Battle settings", (close) => {
        const sizeChips = h("div", { class: "chips" });
        const drawSizes = () => clear(sizeChips, Object.entries(SIZES).map(([k, sz]) => h("button", { class: `chip ${det.size === k ? "on" : ""}`, onclick: () => { det.size = k; drawSizes(); } }, sz.label)));
        drawSizes();
        const field = (label, key, textarea = false) => h("label", { class: "field" }, h("span", {}, label),
          textarea ? h("textarea", { class: "input", rows: 2, oninput: (e) => { det[key] = e.target.value; } }, det[key])
            : h("input", { class: "input", value: det[key], oninput: (e) => { det[key] = e.target.value; } }));
        const party_ = party.filter((m) => m.active !== false || b.conroi.includes(m.id));
        const conroiSec = running ? h("div", { class: "panel" }, h("h3", {}, "The conroi"),
          party_.map((m) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: con.knights.includes(m.id),
            onchange: (e) => { con.knights = e.target.checked ? [...con.knights, m.id] : con.knights.filter((x) => x !== m.id); } }), m.name)),
          h("div", { class: "row" },
            h("label", { class: "field" }, h("span", {}, "Starting Morale"), h("input", { class: "input num", type: "number", min: 1, value: con.start, oninput: (e) => { con.start = e.target.value; } })),
            h("label", { class: "field", style: { flex: 1 } }, h("span", {}, "Passion"), h("input", { class: "input", value: con.passion, oninput: (e) => { con.passion = e.target.value; } }))),
          h("div", { class: "faint small" }, "Change the commander from the Morale strip.")) : null;
        const todaySec = running ? h("div", { class: "panel" }, h("h3", {}, `Today — Day ${b.day}`),
          h("div", { class: "row" }, h("label", { class: "field" }, h("span", {}, "Intensity"),
            h("input", { class: "input num", type: "number", min: 1, max: 40, value: dayIntensity.value, oninput: (e) => { dayIntensity.value = e.target.value; } })),
            h("button", { class: "btn sm", onclick: async () => { await post("/api/battle/day", { roll_for_me: true }); close(); settingsDrawer(); } }, icon("d6"), `Roll again (${SIZES[b.definition.size].dice})`)),
          SIZES[b.definition.size].army ? ["friendly", "enemy"].map((side) => {
            const ac = b.definition.army_commanders?.[side] || {};
            return h("div", { class: "army-row" }, h("div", { class: "label" }, `${ac.name || (side === "friendly" ? "Friendly" : "Enemy")} — Battle roll`),
              outcomeChips({ value: b.army[String(b.day)]?.[side] || null, onPick: async (o) => { await post("/api/battle/army-roll", { side, outcome: o }); close(); settingsDrawer(); } }));
          }) : null) : null;
        return [
          h("div", { class: "panel" }, h("h3", {}, "The battle"),
            h("div", { class: "grid2" }, field("Name", "name"), h("div", {}, h("div", { class: "label" }, "Size"), sizeChips)),
            h("div", { class: "grid2" }, field("Where", "where"), field("Against", "against")), field("Notes (GM only)", "notes", true)),
          conroiSec, todaySec,
          h("div", { class: "stack" }, b.definition.days.map((day, i) => {
            const n = i + 1, past = n < b.day;
            return h("div", {}, h("div", { class: "label" }, `Day ${n}`, past ? " (past days are locked)" : ""),
              dayCard(day, det.size, { readOnly: past, decks, label: `Day ${n}`, onChange: (d) => { edits[n] = d; } }));
          })),
          h("div", { class: "foot" },
            h("button", { class: "btn", onclick: async () => { await post("/api/battle/settings", { add_day: { turns: SIZES[det.size].turns } }); close(); settingsDrawer(); } }, icon("plus"), "Add day"),
            h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: async () => {
              const bp = {};
              for (const k of ["name", "where", "against", "notes", "size"]) if ((b.definition[k] || "") !== det[k]) bp[k] = det[k];
              if (Object.keys(bp).length) await post("/api/battle/settings", { battle_patch: bp });
              if (running) {
                const cp = {};
                if (JSON.stringify([...con.knights].sort()) !== JSON.stringify([...b.conroi].sort())) cp.knights = con.knights;
                if (con.passion !== (b.passion || "")) cp.passion = con.passion;
                if (String(con.start) !== String(b.morale?.start ?? "")) cp.start = Number(con.start);
                if (Object.keys(cp).length) await post("/api/battle/conroi", cp);
                if (String(dayIntensity.value) !== String(b.intensity_today ?? "") && dayIntensity.value !== "") await post("/api/battle/day", { intensity: Number(dayIntensity.value) });
              }
              for (const [n, d] of Object.entries(edits)) {
                const old = b.definition.days[n - 1];
                const patch = {};
                for (const k of ["intensity", "turns", "first_charge", "no_charge", "commanders", "notes", "scripts"])
                  if (JSON.stringify(old[k]) !== JSON.stringify(d[k])) patch[k] = d[k];
                if (Object.keys(patch).length) await post("/api/battle/settings", { day: Number(n), patch });
                const before = new Set([...old.deck.foes, ...old.deck.opportunities]), after = new Set([...d.deck.foes, ...d.deck.opportunities]);
                const add = [...after].filter((k) => !before.has(k)), remove = [...before].filter((k) => !after.has(k));
                if (add.length || remove.length) await post("/api/battle/deck", { day: Number(n), add, remove });
              }
              close();
            } }, "Save")),
        ];
      }, { wide: true });
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
      if (reset || evs.some((e) => e.type.startsWith("battle.") || e.type.startsWith("table.") || (e.type.startsWith("glory.") && e.data?.battle) || e.type.startsWith("meta.") || e.type.startsWith("session."))) loadSoon();
    });
    // Catch up after typing — but only if something changed meanwhile, and only
    // once the click that moved the cursor away has landed.
    el.addEventListener("focusout", () => { if (pending) setTimeout(() => pending && render(), 250); });
    await load();
    return { async show() { await load(); }, async onLibrary() { await load(); } };
  },
};
