// Sessions archive: every saved session file — resume one, read its chronicle,
// or download it.

import { h, clear, api, post, icon, modal, confirmBox, toast, useCss, download, enc } from "../lib.js";

const fmtDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" })
    + " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
};

export default {
  async mount(el, ctx) {
    useCss("sessions");
    const hero = h("div", { class: "sess-hero" });
    const list = h("div", { class: "sess-list" });

    clear(el,
      h("div", { class: "tool-head" },
        h("div", {}, h("h1", {}, "Sessions"),
          h("p", { class: "lede" }, "Every session is one file, autosaved after each event. Resume one to carry on where you left off."))),
      hero,
      h("div", { class: "section-label" }, "The chronicle"),
      list);

    async function load() {
      const r = await api("/api/sessions");
      renderHero(r.active);
      renderList(r.sessions, r.active);
    }

    function exportsFor(id) {
      return [
        h("button", { class: "btn sm", title: "Read the chronicle as a web page",
          onclick: () => window.open(`/api/session/chronicle.html?id=${enc(id)}`, "_blank") }, icon("book"), "Chronicle"),
        h("button", { class: "btn sm ghost", title: "Chronicle as Markdown",
          onclick: () => download(`/api/session/chronicle.md?id=${enc(id)}`) }, icon("scroll"), ".md"),
        h("button", { class: "btn sm ghost", title: "The raw session file",
          onclick: () => download(`/api/session/download?id=${enc(id)}`) }, icon("download"), ".json"),
      ];
    }

    function renderHero() {
      const s = ctx.session;
      if (!s || s.scratch) {
        clear(hero, h("div", { class: "panel sess-now idle" },
          h("div", { class: "sess-now-ico" }, icon("hourglass")),
          h("div", { style: { flex: 1, minWidth: 0 } },
            h("div", { class: "label" }, "No session in progress"),
            h("div", { class: "sess-now-title" }, "The hall is quiet"),
            h("p", { class: "muted", style: { margin: "4px 0 0" } },
              "Rolls and narration still reach the Table, but nothing is saved until you start a session.")),
          h("button", { class: "btn primary", onclick: start }, icon("play"), "Start session")));
        return;
      }
      clear(hero, h("div", { class: "panel sess-now live" },
        h("div", { class: "sess-now-ico" }, h("span", { class: "rec-dot" })),
        h("div", { style: { flex: 1, minWidth: 0 } },
          h("div", { class: "label" }, "Recording now"),
          h("div", { class: "sess-now-title" }, s.title),
          h("div", { class: "faint small" }, `Begun ${fmtDate(s.created)} · ${s.count} events`)),
        h("div", { class: "row" }, exportsFor(s.id),
          h("button", { class: "btn", onclick: end }, icon("stop"), "End session"))));
    }

    function renderList(sessions, active) {
      const past = sessions.filter((s) => s.id !== active);
      if (!past.length) {
        clear(list, h("div", { class: "empty" }, icon("archive"),
          sessions.length ? "Only the current session so far." : "No sessions yet — your first will appear here once you start one."));
        return;
      }
      clear(list, past.map((s, i) => h("div", { class: "sess-row" },
        h("div", { class: "sess-num" }, past.length - i),
        h("div", { style: { minWidth: 0, flex: 1 } },
          h("div", { class: "sess-title" }, s.title),
          h("div", { class: "faint small" }, fmtDate(s.created), " · ", `${s.count} events`,
            s.ended ? null : h("span", { class: "tag gules", style: { marginLeft: "8px" } }, "not ended"))),
        h("div", { class: "row" }, exportsFor(s.id),
          h("button", { class: "btn sm primary", onclick: () => resume(s) }, icon("play"), "Resume")))));
    }

    async function start() {
      const r = await api("/api/session");
      const title = await modal("Start a session", (close) => {
        const inp = h("input", { class: "input", value: r.suggested_title || "", onkeydown: (e) => e.key === "Enter" && close(inp.value) });
        return [h("label", { class: "field" }, h("span", {}, "Session name"), inp),
          h("div", { class: "foot" }, h("button", { class: "btn ghost", onclick: () => close() }, "Cancel"),
            h("button", { class: "btn primary", onclick: () => close(inp.value) }, "Begin"))];
      });
      if (title === undefined) return;
      await post("/api/session/start", { title });
      toast("Session started — recording", "ok");
    }

    async function end() {
      if (!await confirmBox("End the session?", `“${ctx.session.title}” is saved and can be resumed later.`, "End session")) return;
      await post("/api/session/end");
    }

    async function resume(s) {
      const cur = ctx.session;
      if (cur && !cur.scratch && cur.id !== s.id &&
          !await confirmBox("Resume an earlier session?", `“${cur.title}” will be ended and saved, and “${s.title}” reopened.`, "Resume")) return;
      await post("/api/session/resume", { id: s.id });
      toast(`Resumed “${s.title}”`, "ok");
    }

    ctx.onEvent((evs, { reset } = {}) => {
      if (reset || evs.some((e) => e.type.startsWith("session."))) load();
      else renderHero();
    });
    await load();
    return { show: () => load() };
  },
};
