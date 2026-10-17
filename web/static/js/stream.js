// The live update stream, shared by every Pendragon tab in the browser.
// Browsers allow only 6 connections to one site across all tabs; with one
// stream per tab, six open tabs would hold them all and every other request
// (tool data, the board) would queue forever. So one tab — whichever holds the
// "pendragon-stream" lock — keeps the single EventSource open and relays each
// message to the other tabs over a BroadcastChannel. When it closes, another
// tab takes the lock and reconnects.
//
// handlers: { open(), error(), message(data) } — called in every tab.

export function liveStream(handlers) {
  const call = (k, v) => { try { handlers[k]?.(v); } catch (e) { console.error(e); } };
  if (!("locks" in navigator) || typeof BroadcastChannel === "undefined") {   // old browser: one stream per tab
    const es = new EventSource("/api/stream");
    es.onopen = () => call("open");
    es.onerror = () => call("error");
    es.onmessage = (m) => call("message", m.data);
    return;
  }
  const bc = new BroadcastChannel("pendragon-stream");
  bc.onmessage = (e) => {
    const d = e.data || {};
    if (d.kind === "open") call("open");
    else if (d.kind === "error") call("error");
    else if (d.kind === "message") call("message", d.data);
  };
  navigator.locks.request("pendragon-stream", () => new Promise(() => {   // held for this tab's lifetime
    const es = new EventSource("/api/stream");
    es.onopen = () => { bc.postMessage({ kind: "open" }); call("open"); };
    es.onerror = () => { bc.postMessage({ kind: "error" }); call("error"); };
    es.onmessage = (m) => { bc.postMessage({ kind: "message", data: m.data }); call("message", m.data); };
  }));
  // A tab that isn't holding the stream is live as soon as the holder is.
  call("open");
}
