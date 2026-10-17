// Shared GM-console components for the Battle and Battles tools (built once,
// reused): the deck picker, outcome chips, amount entry, Morale strip, knight
// chip and day card. GM-only — nothing here is ever on the Table.

import { h, clear, icon, modal } from "./lib.js";

/**
 * A checklist of battle encounters with Foes / Opportunities tabs and the
 * GM-only Minimum, Loss and KV columns. `cards` come from /api/battle-decks;
 * `selected` is an array of keys; `onChange(keys)` fires on every tick.
 * Keys no longer in the library show as "missing" rows that can be removed.
 */
export function deckPicker({ cards, selected = [], onChange, tab = "foe" }) {
  let chosen = new Set(selected);
  let q = "";
  const root = h("div", { class: "deck-picker" });
  const byKey = new Map(cards.map((c) => [c.key, c]));
  const draw = () => {
    const count = (role) => [...chosen].filter((k) => byKey.get(k)?.role === role).length;
    const rows = cards.filter((c) => c.role === tab && (!q || c.key.toLowerCase().includes(q)));
    const missing = [...chosen].filter((k) => !byKey.has(k));
    clear(root,
      h("div", { class: "dp-head" },
        h("div", { class: "dp-tabs", role: "tablist" },
          [["foe", "Foes"], ["opportunity", "Opportunities ★"]].map(([r, label]) =>
            h("button", { class: `chip ${tab === r ? "on" : ""}`, role: "tab", "aria-selected": String(tab === r),
              onclick: () => { tab = r; draw(); } }, `${label} (${count(r)})`))),
        h("input", { class: "input dp-search", type: "search", placeholder: "Search…", value: q,
          oninput: (e) => { q = e.target.value.toLowerCase(); draw(); } })),
      h("div", { class: "dp-list" },
        rows.length ? rows.map((c) => h("label", { class: `dp-row ${chosen.has(c.key) ? "on" : ""}` },
          h("input", { type: "checkbox", checked: chosen.has(c.key), onchange: (e) => {
            e.target.checked ? chosen.add(c.key) : chosen.delete(c.key);
            onChange?.([...chosen]); draw();
          } }),
          h("span", { class: "dp-name" }, c.role === "opportunity" ? "★ " : "", c.key),
          h("span", { class: "dp-meta" }, `Min ${c.morale_minimum ?? "—"}`),
          h("span", { class: "dp-meta" }, `Loss ${c.morale_loss || "—"}`),
          h("span", { class: "dp-meta" }, c.has_roster ? `KV ${c.kv_per_knight || "0"}` : "no foes"),
          c.missile ? h("span", { class: "tag" }, "missile") : null))
          : h("div", { class: "faint small" }, tab === "foe" ? "No battle Foes yet — mark encounters as Foes in the Encounter Creator." : "No Opportunities yet."),
        missing.map((k) => h("div", { class: "dp-row missing" }, h("span", { class: "dp-name" }, k), h("span", { class: "tag gules" }, "missing"),
          h("button", { class: "btn ghost sm", onclick: () => { chosen.delete(k); onChange?.([...chosen]); draw(); } }, "Remove")))));
  };
  draw();
  return root;
}

// ---------------------------------------------------------------- day card
// One day of a battle definition (design §2.1): Intensity, turns, the charge
// switches, commander presets, the day's deck, notes and turn scripts. Used by
// the Battles editor and the live Battle settings drawer (past days readOnly).

// Table 6.1 (mirrors core/battle.py SIZES): max turns, Intensity dice, army rolls.
const DC_SIZES = {
  fight: { label: "Fight", turns: 1, intensity: "1D6+2", army: false },
  skirmish: { label: "Skirmish", turns: 3, intensity: "2D6", army: false },
  clash: { label: "Clash", turns: 5, intensity: "2D6+1", army: true },
  small: { label: "Small Battle", turns: 6, intensity: "2D6+2", army: true },
  medium: { label: "Medium Battle", turns: 7, intensity: "2D6+3", army: true },
  large: { label: "Large Battle", turns: 8, intensity: "3D6", army: true },
  huge: { label: "Huge Battle", turns: 8, intensity: "3D6+1", army: true },
};
const DC_OUTCOMES = [["critical", "Critical"], ["success", "Success"], ["failure", "Failure"], ["fumble", "Fumble"]];
const dcClone = (o) => JSON.parse(JSON.stringify(o));

/** Split picked keys into {foes, opportunities} by card role; keys missing
 * from the library stay in the list they were in before (else Foes). */
function dcSplit(keys, cards, prev = { foes: [], opportunities: [] }) {
  const role = new Map(cards.map((c) => [c.key, c.role]));
  const out = { foes: [], opportunities: [] };
  for (const k of keys) {
    const r = role.get(k) || ((prev.opportunities || []).includes(k) ? "opportunity" : "foe");
    out[r === "opportunity" ? "opportunities" : "foes"].push(k);
  }
  return out;
}
const dcKeys = (deck) => [...(deck?.foes || []), ...(deck?.opportunities || [])];
const dcDeckSummary = (deck) => {
  const f = deck?.foes?.length || 0, o = deck?.opportunities?.length || 0;
  return `${f} Foe${f === 1 ? "" : "s"} · ${o} Opportunit${o === 1 ? "y" : "ies"}`;
};

/**
 * dayCard(day, size, {readOnly, onChange, decks, label, onRemove}) → element.
 * `day` is a day definition (it is cloned, never mutated); `size` a Table 6.1
 * key. `decks` is the /api/battle-decks `cards` list for the deck pickers.
 * `onChange(updatedDay)` fires with a fresh copy on every edit. `label`
 * (default "Day") titles the card; `onRemove` adds a "Remove day" button.
 * readOnly renders the same card with every control disabled.
 */
export function dayCard(day, size, { readOnly = false, onChange, decks = [], label = "Day", onRemove } = {}) {
  const d = dcClone(day || {});
  d.intensity ||= { mode: "roll" };
  d.commanders ||= { friendly: null, enemy: null };
  d.deck ||= { foes: [], opportunities: [] };
  d.scripts ||= [];
  d.notes ??= "";
  const S = DC_SIZES[size] || DC_SIZES.clash;
  const root = h("div", { class: `panel day-card ${readOnly ? "readonly" : ""}` });
  let deckOpen = false;
  const sumEl = h("span", { class: "faint small" });
  const drawSum = () => { sumEl.textContent = `${d.intensity.mode === "fixed" ? `Intensity ${d.intensity.value ?? "—"}` : `Intensity ${S.intensity}`} · ${d.turns ?? S.turns} turns`; };
  const emit = () => { drawSum(); if (!readOnly) onChange?.(dcClone(d)); };
  const dis = readOnly || null;

  const hintEl = h("span", { class: "dc-hint" });
  const drawHint = () => clear(hintEl, d.turns > S.turns
    ? [h("span", { class: "tag or rule-sr", title: `Table 6.1 gives a ${S.label} at most ${S.turns} turn${S.turns === 1 ? "" : "s"}; the book lets a scenario set its own length.` }, "Scenario rule"),
      ` over Table 6.1 max (${S.turns}): scenario override`]
    : h("span", { class: "faint" }, `Table 6.1 max: ${S.turns}`));

  const sw = (key, text, title) => h("label", { class: "check", title },
    h("input", { type: "checkbox", checked: !!d[key], disabled: dis, onchange: (e) => { d[key] = e.target.checked; emit(); } }), text);

  const draw = () => {
    // Intensity
    const fixed = d.intensity.mode === "fixed";
    const valIn = h("input", { class: "input num", type: "number", min: 1, max: 40, value: d.intensity.value ?? "", disabled: dis, placeholder: "—",
      oninput: (e) => { d.intensity = { mode: "fixed", value: e.target.value === "" ? null : Number(e.target.value) }; emit(); } });
    const inten = h("div", { class: "dc-field" }, h("span", { class: "label" }, "Intensity"),
      h("div", { class: "row tight" },
        h("button", { class: `chip ${fixed ? "" : "on"}`, disabled: dis, title: "Rolled when the day starts",
          onclick: () => { d.intensity = { mode: "roll" }; emit(); draw(); } }, `Roll from size (${S.intensity})`),
        h("button", { class: `chip ${fixed ? "on" : ""}`, disabled: dis,
          onclick: () => { if (!fixed) { d.intensity = { mode: "fixed", value: d.intensity.value ?? 10 }; emit(); draw(); } } }, "Fixed"),
        fixed ? valIn : null));

    // Turns stepper
    const turnsIn = h("input", { class: "input num", type: "number", min: 1, value: d.turns ?? S.turns, disabled: dis,
      oninput: (e) => { const n = Math.max(1, Math.round(Number(e.target.value) || 1)); d.turns = n; drawHint(); emit(); } });
    const step = (n) => { d.turns = Math.max(1, (Number(d.turns) || S.turns) + n); turnsIn.value = d.turns; drawHint(); emit(); };
    drawHint(); drawSum();
    const turns = h("div", { class: "dc-field" }, h("span", { class: "label" }, "Turns"),
      h("div", { class: "row tight" },
        h("button", { class: "btn sm icon", disabled: dis, title: "One fewer turn", onclick: () => step(-1) }, "−"),
        turnsIn,
        h("button", { class: "btn sm icon", disabled: dis, title: "One more turn", onclick: () => step(1) }, "+"),
        hintEl));

    // Commander presets (Clash and up)
    const cmdRow = (side, text) => h("div", { class: "dc-cmd" }, h("span", { class: "dc-cmd-name" }, text),
      h("div", { class: "chips" },
        h("button", { class: `chip ${d.commanders[side] ? "" : "on"}`, disabled: dis, title: "Rolled or entered at Mustering",
          onclick: () => { d.commanders[side] = null; emit(); draw(); } }, "Ask at Mustering"),
        DC_OUTCOMES.map(([o, t]) => h("button", { class: `chip ${d.commanders[side] === o ? "on" : ""}`, disabled: dis,
          onclick: () => { d.commanders[side] = o; emit(); draw(); } }, t))));
    const commanders = S.army ? h("div", { class: "dc-sec" },
      h("div", { class: "label" }, "Army commanders' Battle rolls (preset)"),
      cmdRow("friendly", "Friendly"), cmdRow("enemy", "Enemy")) : null;

    // Deck
    const deckSec = h("details", { class: "dc-sec dc-deck", open: deckOpen || null },
      h("summary", {}, h("span", { class: "label" }, "Battle deck"), h("span", { class: "faint small" }, ` ${dcDeckSummary(d.deck)}`)),
      readOnly
        ? h("div", { class: "dc-deck-list" }, dcKeys(d.deck).length
          ? dcKeys(d.deck).map((k) => h("span", { class: `tag ${d.deck.opportunities.includes(k) ? "or" : ""}` }, d.deck.opportunities.includes(k) ? `★ ${k}` : k))
          : h("span", { class: "faint small" }, "No cards."))
        : deckPicker({ cards: decks, selected: dcKeys(d.deck), onChange: (keys) => {
          d.deck = dcSplit(keys, decks, d.deck); emit();
          deckSec.querySelector("summary .faint").textContent = ` ${dcDeckSummary(d.deck)}`;
        } }));

    // Notes
    const notes = h("textarea", { class: "input", rows: 2, disabled: dis, placeholder: "What happens today — GM only" }, d.notes);
    notes.addEventListener("input", () => { d.notes = notes.value; emit(); });

    // Turn scripts
    const scripts = h("div", { class: "dc-sec" },
      h("div", { class: "label" }, "Turn scripts"),
      h("p", { class: "faint small dc-help" }, "Events you read out on a set turn. Any modifiers in them are yours to apply."),
      d.scripts.length ? d.scripts.map((sc, i) => {
        const tIn = h("input", { class: "input num", type: "number", min: 1, value: sc.turn ?? 1, disabled: dis, title: "Turn",
          oninput: (e) => { sc.turn = Math.max(1, Math.round(Number(e.target.value) || 1)); emit(); } });
        const txt = h("textarea", { class: "input", rows: 1, disabled: dis, placeholder: "What happens on this turn" }, sc.text || "");
        txt.addEventListener("input", () => { sc.text = txt.value; emit(); });
        const n = dcKeys(sc.deck).length;
        return h("div", { class: "dc-script" },
          h("label", { class: "dc-script-turn" }, h("span", { class: "label" }, "Turn"), tIn),
          txt,
          h("div", { class: "dc-script-opts" },
            h("label", { class: "check small", title: "Show this script only when the turn's Intensity roll succeeds" },
              h("input", { type: "checkbox", checked: !!sc.if_intensity, disabled: dis, onchange: (e) => { sc.if_intensity = e.target.checked; emit(); } }),
              "only if Intensity succeeds"),
            readOnly
              ? h("span", { class: "faint small" }, sc.deck ? `Deck limited to ${n} card${n === 1 ? "" : "s"}` : "Uses the day's deck")
              : h("button", { class: `btn sm ${sc.deck ? "on" : ""}`, title: sc.deck ? dcKeys(sc.deck).join(", ") : "Limit this turn to some cards",
                onclick: () => restrict(sc) }, sc.deck ? `Deck limited (${n})…` : "Restrict deck…"),
            readOnly ? null : h("button", { class: "btn ghost sm icon", title: "Remove script", onclick: () => { d.scripts.splice(i, 1); emit(); draw(); } }, icon("x"))));
      }) : h("div", { class: "faint small" }, "No scripts."),
      readOnly ? null : h("button", { class: "btn sm", onclick: () => {
        const last = d.scripts[d.scripts.length - 1];
        d.scripts.push({ turn: Math.min((last?.turn || 0) + 1, Math.max(1, d.turns || 1)), text: "", if_intensity: false, deck: null });
        emit(); draw(); root.querySelector(".dc-script:last-of-type textarea")?.focus();
      } }, icon("plus"), "Add script"));

    clear(root,
      h("div", { class: "dc-head" }, h("h3", {}, label), sumEl,
        readOnly || !onRemove ? null : h("button", { class: "btn ghost sm danger dc-remove", onclick: () => onRemove() }, icon("x"), "Remove day")),
      h("div", { class: "dc-top" }, inten, turns),
      h("div", { class: "dc-switches" },
        sw("first_charge", "First charge", "Turn 1 opens with a mounted charge (an army commander's roll can change this)"),
        sw("on_foot", "Conroi starts on foot", "Every knight's Mounted pill starts On foot today"),
        sw("no_charge", "No charge this day", "Skip the charge step on every turn today")),
      commanders,
      deckSec,
      h("label", { class: "field dc-sec" }, h("span", {}, "Notes"), notes),
      scripts);
    deckSec.addEventListener("toggle", () => { deckOpen = deckSec.open; });
  };

  function restrict(sc) {
    let keys = dcKeys(sc.deck);
    // A restriction narrows the day's deck; with no day deck yet, offer every card.
    const dayKeys = new Set([...dcKeys(d.deck), ...keys]);
    const pool = dcKeys(d.deck).length ? decks.filter((c) => dayKeys.has(c.key)) : decks;
    modal(`Restrict the deck — turn ${sc.turn}`, (close) => [
      h("p", { class: "muted small" }, "On this turn only the ticked cards from the day's deck can be set or picked. Tick nothing to use the whole deck."),
      deckPicker({ cards: pool, selected: keys, onChange: (k) => { keys = k; } }),
      h("div", { class: "foot" },
        h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
        h("button", { class: "btn", onclick: () => { sc.deck = null; emit(); draw(); close(); } }, "Use the day's deck"),
        h("button", { class: "btn primary", onclick: () => { sc.deck = keys.length ? dcSplit(keys, decks, sc.deck || undefined) : null; emit(); draw(); close(); } }, "Done")),
    ], { wide: true });
  }

  draw();
  return root;
}

// ---------------------------------------------------------------- outcome chips
const OUTCOME_CHIPS = [["critical", "Crit", "c", "C"], ["success", "Success", "s", "S"], ["failure", "Fail", "f", "F"], ["fumble", "Fumble", "x", "X"]];

/**
 * Crit / Success / Fail / Fumble — how the GM records a roll the players (or
 * the GM) made at the table. `value` highlights a recorded or preset outcome;
 * `onPick(outcome)` records it. With `keys`, C/S/F/X pick while it is on screen.
 */
export function outcomeChips({ value = null, onPick, keys = false, disabled = false } = {}) {
  const root = h("div", { class: "outcome-chips", role: "group", "aria-label": "Outcome" },
    OUTCOME_CHIPS.map(([o, label, cls, key]) => h("button", { class: `oc ${cls} ${value === o ? "on" : ""}`, disabled: disabled || null,
      title: keys ? `${label} (${key})` : label, onclick: () => onPick?.(o) }, label, keys ? h("span", { class: "kbd" }, key) : null)));
  if (keys && !disabled) {
    const onKey = (e) => {
      if (!root.isConnected) return document.removeEventListener("keydown", onKey);
      if (e.target.closest?.("input, textarea, select")) return;
      const hit = OUTCOME_CHIPS.find(([, , , k]) => k.toLowerCase() === e.key.toLowerCase());
      if (hit) { e.preventDefault(); onPick?.(hit[0]); }
    };
    document.addEventListener("keydown", onKey);
  }
  return root;
}

// ---------------------------------------------------------------- amount entry
/** A number the players rolled (Enter submits) and an optional "roll for me". */
export function amountEntry({ dice, min = 1, max = 99, onEnter, rollForMe, placeholder } = {}) {
  const inp = h("input", { class: "input num", type: "number", min, max, placeholder: placeholder || dice || "" });
  const submit = () => {
    const v = Number(inp.value);
    if (inp.value === "" || v < min || v > max) { inp.focus(); inp.select?.(); return; }
    inp.blur();
    onEnter?.(v);
  };
  inp.addEventListener("keydown", (e) => e.key === "Enter" && submit());
  return h("div", { class: "amount-entry row tight" }, inp, h("button", { class: "btn sm", onclick: submit }, "Enter"),
    rollForMe ? h("button", { class: "btn ghost sm", title: "The GM rolls it here", onclick: rollForMe }, icon("d6"), `roll for me${dice ? ` (${dice})` : ""}`) : null);
}

// ---------------------------------------------------------------- Morale strip
/** The pinned strip: Morale current / start with its band, the GM's ± override,
 * the Force / Negate tokens, and the commander. `b` is the GM battle view. */
export function moraleStrip(b, { onAdjust, onCommander, onToken, glow = {} } = {}) {
  const m = b.morale;
  const pct = m ? Math.max(0, Math.min(100, (m.current / Math.max(1, m.start)) * 100)) : 0;
  const token = (key, label) => {
    const st = b.tokens?.[key];
    if (!st || st === "none") return null;
    return h("button", { class: `token ${st === "spent" ? "spent" : ""} ${glow[key] && st === "available" ? "glow" : ""}`, disabled: st === "spent" || null,
      title: key === "force" ? "Enemy commander's success: force one Encounter today" : "Enemy commander's fumble: shrug off one Encounter's Morale loss today",
      onclick: () => onToken?.(key) }, label);
  };
  return h("div", { class: "mstrip" },
    h("div", { class: "mval" }, m ? m.current : "—", h("small", {}, ` / ${m ? m.start : "—"}`)),
    h("div", { class: "mbar-wrap" }, h("div", { class: `mbar band-${(b.band || "").toLowerCase()}` }, h("i", { style: { width: `${pct}%` } })),
      h("span", { class: "mband" }, b.band || "")),
    h("button", { class: "btn ghost sm", title: "Adjust Morale (logged, with a reason)", onclick: () => onAdjust?.() }, "±"),
    h("div", { class: "row tight" }, token("force", "⚑ Force Encounter"), token("negate", "✋ Negate loss")),
    h("button", { class: "who", title: "Change the commander", onclick: (e) => onCommander?.(e.currentTarget) }, icon("shield"), `Commander: ${b.commander_name || "—"}`));
}

// ---------------------------------------------------------------- knight chip
const POS_LABEL = { conroi: "with the conroi", rear: "at the rear", alone: "alone on the field", left: "left the field" };
/** A knight in the battle: shield, name, Mounted pill, position, posture. */
export function knightChip(k, { onMounted, onPosition } = {}) {
  return h("div", { class: `kchip ${k.position && k.position !== "conroi" ? "away" : ""}` },
    icon("shield"), h("b", {}, k.name),
    h("button", { class: `pill-mounted ${k.mounted ? "on" : ""}`, title: "Toggle mounted / on foot", onclick: () => onMounted?.(k) }, k.mounted ? "Mounted" : "On foot"),
    k.position && k.position !== "conroi" ? h("button", { class: "kpos", onclick: (e) => onPosition?.(k, e.currentTarget) }, POS_LABEL[k.position]) : null,
    k.posture ? h("span", { class: "kposture" }, k.posture) : null,
    k.passion_used ? h("span", { class: "faint small" }, "Passion used") : null);
}
