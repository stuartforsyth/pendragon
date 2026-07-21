#!/usr/bin/env python3
"""Encounter Creator for the Pendragon app.

A tab to create, edit, and manage **encounter definitions** — reusable recipes
(which adversaries, how many, how they scale) that the Encounter tab turns into
a live fight (see docs/encounter-creator-spec.md). Definitions live in the same
``encounters`` map as the built-in themes; this editor writes the richer roster
shape and a "Send to tracker" bridge runs one immediately.
"""

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from rules import save_combat
from encounter import resolve_roster


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def blank_encounter():
    return {
        "source": "user", "name": "", "description": "", "tags": [],
        "roster": [], "leader": None, "notes": "",
    }


def _fmt_count(v):
    """Display a count value: whole numbers without a trailing '.0'."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def to_editable(defn):
    """An editable copy in the self-scaling roster shape.

    New-shape definitions pass through. Legacy definitions are migrated: a global
    ``scaling`` block is folded into each roster line's own multiplier, and a
    legacy random pool (``core`` + ``per_player``) becomes explicit per-player
    roster lines.
    """
    if "roster" in defn:
        d = copy.deepcopy(blank_encounter())
        d.update(copy.deepcopy(defn))
        scaling = d.pop("scaling", None)
        factor = 1.0
        if isinstance(scaling, dict) and scaling.get("mode", "per_player") == "per_player":
            factor = scaling.get("per_player", 1.0)
        for line in d["roster"]:
            if "per_player" in line:
                continue  # already self-scaling
            if line.get("count") == "per_player":   # migrate legacy scaled line
                line["per_player"] = True
                line["count"] = factor
            else:                                   # migrate legacy fixed line
                line["per_player"] = False
        return d
    d = blank_encounter()
    d["name"] = defn.get("name", "")
    core = defn.get("core", [])
    # Legacy pool (per_player × players): split the factor across the pool's
    # members so the converted roster totals the same, not ×len(core).
    factor = defn.get("per_player", 1.0) / max(1, len(core))
    for adv in core:
        d["roster"].append({"adversary": adv, "count": factor,
                            "per_player": True, "promote": False})
    lead = defn.get("leader")
    if lead:
        d["leader"] = {"adversary": lead, "promote": True}
    return d


def preview_lines(defn, n_players):
    """Human-readable '4× Bandit' preview lines + total, for the editor."""
    counts = {}
    order = []
    for adv, n, promote in resolve_roster(defn, n_players):
        key = (adv, promote)
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + n
    lines = []
    for adv, promote in order:
        tag = " (promoted)" if promote else ""
        lines.append(f"{counts[(adv, promote)]}× {adv}{tag}")
    leader = defn.get("leader")
    total = sum(counts.values())
    if isinstance(leader, dict) and leader.get("adversary"):
        tag = " (promoted)" if leader.get("promote", True) else ""
        lines.append(f"1× {leader['adversary']} — leader{tag}")
        total += 1
    return lines, total


# ---------------------------------------------------------------------------
# GUI — the Encounter Creator tab
# ---------------------------------------------------------------------------

class EncounterCreatorTab(ttk.Frame):
    def __init__(self, parent, rules, set_status, send_to_tracker):
        super().__init__(parent)
        self.rules = rules
        self.combat = rules.combat
        self.set_status = set_status
        self.send_to_tracker = send_to_tracker
        self.draft = blank_encounter()
        self.draft_key = None
        self.roster_rows = []
        self._build_ui()
        self._refresh_library()
        self._show(self.draft, None)

    # -- data --------------------------------------------------------------

    def _encounters(self):
        return self.combat.get("encounters", {})

    def _adversary_names(self):
        return sorted(self.combat.get("adversaries", {}))

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        lib = ttk.LabelFrame(self, text="Encounter library")
        lib.pack(side="left", fill="y", padx=(10, 4), pady=10)
        srow = ttk.Frame(lib)
        srow.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(srow, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._refresh_library())
        ttk.Entry(srow, textvariable=self.search_var, width=22).pack(
            side="left", fill="x", expand=True, padx=(4, 0))
        self.lib_list = tk.Listbox(lib, width=32, height=22, activestyle="dotbox")
        self.lib_list.pack(fill="both", expand=True, padx=6, pady=2)
        self.lib_list.bind("<<ListboxSelect>>", self._on_select)
        btns = ttk.Frame(lib)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btns, text="New", width=10, command=self._new).grid(row=0, column=0, padx=1)
        ttk.Button(btns, text="Duplicate", width=10, command=self._duplicate).grid(row=0, column=1, padx=1)
        ttk.Button(btns, text="Delete", width=10, command=self._delete).grid(row=0, column=2, padx=1)

        outer = ttk.LabelFrame(self, text="Editor")
        outer.pack(side="left", fill="both", expand=True, padx=(4, 10), pady=10)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.ed = ttk.Frame(canvas)
        self.ed.bind("<Configure>",
                     lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.ed, anchor="nw")
        canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self._build_editor()

    def _section(self, title):
        f = ttk.LabelFrame(self.ed, text=title)
        f.pack(fill="x", padx=8, pady=(6, 0))
        return f

    def _build_editor(self):
        bar = ttk.Frame(self.ed)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        self.header = ttk.Label(bar, text="New encounter",
                                font=("TkDefaultFont", 10, "bold"))
        self.header.pack(side="left")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="right", padx=(0, 6))

        info = self._section("Details")
        self.name_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        ttk.Label(info, text="Name:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(info, textvariable=self.name_var, width=30).grid(
            row=0, column=1, columnspan=3, sticky="w")
        ttk.Label(info, text="Description:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(info, textvariable=self.desc_var, width=48).grid(
            row=1, column=1, columnspan=3, sticky="we")
        ttk.Label(info, text="Tags:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(info, textvariable=self.tags_var, width=30).grid(
            row=2, column=1, columnspan=3, sticky="w")

        # GM notes & campaign references — free text stored in the config file
        # with the encounter (distinct from the short one-line Description above).
        gm = self._section("GM notes & campaign references  (saved with the encounter)")
        self.notes_text = tk.Text(gm, height=6, width=48, wrap="word",
                                  font=("TkDefaultFont", 10))
        self.notes_text.pack(fill="both", expand=True, padx=6, pady=4)

        rf = self._section("Roster  (each line scales itself)")
        hint = ttk.Label(rf, foreground="#555", font=("TkDefaultFont", 9), justify="left",
                         text=("Set a count per adversary. Tick “× players” to scale with "
                               "party size (fractions allowed, e.g. 1.5× players of "
                               "Bodyguards); leave it unticked for a fixed number "
                               "(e.g. 1 King Lot)."))
        hint.pack(anchor="w", fill="x", padx=6, pady=(4, 2))
        hint.bind("<Configure>",
                  lambda e, l=hint: l.configure(wraplength=max(300, e.width - 8)))
        hdr = ttk.Frame(rf)
        hdr.pack(fill="x", padx=6)
        ttk.Label(hdr, text="Adversary", width=22, font=("TkDefaultFont", 9, "bold")).pack(side="left")
        ttk.Label(hdr, text="Count", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self.roster_frame = ttk.Frame(rf)
        self.roster_frame.pack(fill="x", padx=6, pady=2)
        addbar = ttk.Frame(rf)
        addbar.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(addbar, text="Add roster line",
                   command=lambda: self._add_roster_row()).pack(side="left")

        lf = self._section("Leader (optional, auto-promoted)")
        self.leader_var = tk.StringVar()
        ttk.Combobox(lf, textvariable=self.leader_var, width=22, state="readonly",
                     values=[""] + self._adversary_names()).pack(side="left", padx=6, pady=4)
        self.leader_promote = tk.BooleanVar(value=True)
        ttk.Checkbutton(lf, text="promote", variable=self.leader_promote,
                        command=self._update_preview).pack(side="left")
        self.leader_var.trace_add("write", lambda *a: self._update_preview())

        pf = self._section("Preview")
        prow = ttk.Frame(pf)
        prow.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(prow, text="Players:").pack(side="left")
        self.preview_players = tk.IntVar(value=4)
        ttk.Spinbox(prow, from_=1, to=20, width=4, textvariable=self.preview_players,
                    command=self._update_preview).pack(side="left", padx=(4, 10))
        ttk.Button(prow, text="Send to tracker",
                   command=self._send_to_tracker).pack(side="left")
        self.preview_lbl = ttk.Label(pf, text="", justify="left")
        self.preview_lbl.pack(anchor="w", padx=6, pady=(2, 6))

    # -- library -----------------------------------------------------------

    def _refresh_library(self):
        self.lib_list.delete(0, "end")
        q = self.search_var.get().strip().lower()
        self._lib_keys = []
        for key, d in sorted(self._encounters().items()):
            advs = " ".join(a.get("adversary", "") for a in d.get("roster", [])) \
                + " ".join(d.get("core", []))
            hay = f"{key} {d.get('description', '')} {' '.join(d.get('tags', []))} {advs}".lower()
            if q and q not in hay:
                continue
            n = len(d.get("roster", d.get("core", [])))
            self.lib_list.insert("end", f"{key}   ({n} line{'s' if n != 1 else ''})")
            self._lib_keys.append(key)

    def _on_select(self, _e):
        sel = self.lib_list.curselection()
        if not sel:
            return
        key = self._lib_keys[sel[0]]
        self.draft = to_editable(self._encounters()[key])
        self.draft_key = key
        self._show(self.draft, key)

    def _new(self):
        self.draft = blank_encounter()
        self.draft_key = None
        self._show(self.draft, None)
        self.set_status("New encounter — build a roster and Save.", "#1a5fb4")

    def _duplicate(self):
        if self.draft_key is None:
            return
        self.draft = to_editable(self._encounters()[self.draft_key])
        self.draft["name"] = f"{self.draft_key} (copy)"
        self.draft["source"] = "user"
        self.draft_key = None
        self._show(self.draft, None)

    def _delete(self):
        if self.draft_key is None or self.draft_key not in self._encounters():
            return
        if not messagebox.askyesno("Delete encounter",
                                   f"Delete '{self.draft_key}' from the working library?"):
            return
        del self._encounters()[self.draft_key]
        save_combat(self.combat, self.rules.data_dir)
        self.set_status(f"Deleted {self.draft_key}.", "#a33")
        self.draft_key = None
        self._refresh_library()
        self._new()

    # -- editor load / collect ---------------------------------------------

    def _show(self, defn, key):
        self.header.config(text=(f"Editing: {key}" if key else "New encounter"))
        self.name_var.set(defn.get("name", "") or key or "")
        self.desc_var.set(defn.get("description", ""))
        self.tags_var.set(", ".join(defn.get("tags", [])))
        for row in list(self.roster_rows):
            row["frame"].destroy()
        self.roster_rows = []
        for line in defn.get("roster", []):
            self._add_roster_row(line)
        leader = defn.get("leader") or {}
        self.leader_var.set(leader.get("adversary", "") if isinstance(leader, dict) else "")
        self.leader_promote.set(leader.get("promote", True) if isinstance(leader, dict) else True)
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", defn.get("notes", ""))
        self._update_preview()

    def _add_roster_row(self, line=None):
        line = line or {"adversary": "", "count": 1, "per_player": True, "promote": False}
        fr = ttk.Frame(self.roster_frame)
        fr.pack(fill="x", pady=1)
        av = tk.StringVar(value=line.get("adversary", ""))
        # Accept new (per_player flag) and legacy (count == "per_player") shapes.
        per_player = line.get("per_player", line.get("count") == "per_player")
        raw = line.get("count", 1)
        if raw == "per_player":
            raw = 1
        cv = tk.StringVar(value=_fmt_count(raw))
        pv = tk.BooleanVar(value=bool(per_player))
        prom = tk.BooleanVar(value=bool(line.get("promote")))
        ttk.Combobox(fr, textvariable=av, width=20, state="readonly",
                     values=self._adversary_names()).pack(side="left")
        ttk.Entry(fr, textvariable=cv, width=5).pack(side="left", padx=(6, 4))
        ttk.Checkbutton(fr, text="× players", variable=pv,
                        command=self._update_preview).pack(side="left")
        ttk.Checkbutton(fr, text="promote", variable=prom,
                        command=self._update_preview).pack(side="left", padx=(8, 0))
        ttk.Button(fr, text="✕", width=2,
                   command=lambda: self._remove_roster_row(row)).pack(side="left", padx=(6, 0))
        for var in (av, cv):
            var.trace_add("write", lambda *a: self._update_preview())
        pv.trace_add("write", lambda *a: self._update_preview())
        row = {"frame": fr, "adversary": av, "count": cv, "per_player": pv, "promote": prom}
        self.roster_rows.append(row)
        return row

    def _remove_roster_row(self, row):
        row["frame"].destroy()
        self.roster_rows.remove(row)
        self._update_preview()

    def _collect(self):
        d = blank_encounter()
        d["name"] = self.name_var.get().strip()
        d["description"] = self.desc_var.get().strip()
        d["tags"] = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        d["roster"] = []
        for row in self.roster_rows:
            adv = row["adversary"].get()
            if not adv:
                continue
            per_player = bool(row["per_player"].get())
            raw = row["count"].get().strip()
            if per_player:
                try:
                    count = float(raw)
                except (TypeError, ValueError):
                    count = 1.0
            else:
                try:
                    count = max(0, int(round(float(raw))))
                except (TypeError, ValueError):
                    count = 1
            d["roster"].append({"adversary": adv, "count": count,
                                "per_player": per_player,
                                "promote": bool(row["promote"].get())})
        leader = self.leader_var.get().strip()
        d["leader"] = ({"adversary": leader, "promote": bool(self.leader_promote.get())}
                       if leader else None)
        d["notes"] = self.notes_text.get("1.0", "end").rstrip("\n")
        return d

    # -- preview / send ----------------------------------------------------

    def _update_preview(self, *_):
        defn = self._collect()
        lines, total = preview_lines(defn, self.preview_players.get())
        body = "\n".join(f"  • {ln}" for ln in lines) if lines else "  (empty roster)"
        self.preview_lbl.config(
            text=f"For {self.preview_players.get()} players:\n{body}\n  = {total} combatants")

    def _send_to_tracker(self):
        defn = self._collect()
        if not defn["roster"] and not defn["leader"]:
            self.set_status("Add at least one roster line first.", "#a33")
            return
        self.send_to_tracker(defn, self.preview_players.get(), defn["name"] or "encounter")

    # -- save / revert -----------------------------------------------------

    def _revert(self):
        if self.draft_key and self.draft_key in self._encounters():
            self._show(to_editable(self._encounters()[self.draft_key]), self.draft_key)
        else:
            self._show(blank_encounter(), None)

    def _save(self):
        d = self._collect()
        key = d["name"]
        if not key:
            messagebox.showwarning("Name required", "Give the encounter a name before saving.")
            return
        enc = self._encounters()
        if key in enc and key != self.draft_key:
            if not messagebox.askyesno("Overwrite",
                                       f"An encounter named '{key}' exists. Overwrite it?"):
                return
        if self.draft_key and self.draft_key != key and self.draft_key in enc:
            del enc[self.draft_key]
        enc[key] = d
        path = save_combat(self.combat, self.rules.data_dir)
        self.draft_key = key
        self._refresh_library()
        self.set_status(f"Saved encounter '{key}' to {path}.", "#2a7d2a")
