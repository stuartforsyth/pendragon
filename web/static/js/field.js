// The Field: knights and foes as tokens, an engagement as a glowing line.
// Shared by the GM's combat tracker and the players' board, so both show the
// same clusters. This module only lays out and draws; what a token says and
// what clicking or dragging it does belong to each caller.
//
// An item is {id, side: "party" | "foe", name, linked: [knight names], down}.

export const FOE_GLYPH = {
  human: '<path d="M50 22v40M42 58h16M50 62v14" stroke="currentColor" stroke-width="6" stroke-linecap="round"/><path d="M50 18l5 9h-10z" fill="currentColor"/>',
  beast: '<path d="M30 70c4-14 8-30 12-40M46 72c2-16 4-32 6-44M62 70c0-14-1-28-2-40" stroke="currentColor" stroke-width="6" stroke-linecap="round" fill="none"/>',
  monster: '<path d="M26 70c8-4 10-14 4-20s-4-16 6-20 22 2 24 12-6 14-2 20 14 6 18-2" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round"/><circle cx="40" cy="31" r="3.5" fill="currentColor"/>',
  fae: '<path d="M50 20l7 22h23l-18 13 7 22-19-14-19 14 7-22-18-13h23z" fill="currentColor"/>',
};

/** A foe's medallion: its kind as a glyph, ringed by how much fight is left
 * in it (a fraction 0–1 and a colour — HP for the GM, a wound word for the players). */
export function foeFace(category, pct, col) {
  const R = 46, C = 2 * Math.PI * R;
  pct = Math.max(0, Math.min(1, pct));
  const s = document.createElement("span");
  s.className = "ftok-face";
  s.innerHTML = `<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="40" class="medal"/>` +
    `<g class="glyph">${FOE_GLYPH[category] || FOE_GLYPH.human}</g>` +
    `<circle cx="50" cy="50" r="${R}" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="6"/>` +
    `<circle cx="50" cy="50" r="${R}" fill="none" stroke="${col}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${C * pct} ${C}" transform="rotate(-90 50 50)"/></svg>`;
  return s;
}

/** A horseshoe on the token: mounted at a glance (knights and foes alike).
 * Open end up, a broad band with flared heels and the nail holes cut through. */
export function horseBadge() {
  const s = document.createElement("span");
  s.className = "ftok-horse";
  s.title = "Mounted";
  s.innerHTML = '<svg viewBox="0 0 32 32" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="M4 2.5H10.5V5H10V16.5A6 6 0 0 0 22 16.5V5H21.5V2.5H28V5H26.5V16.5A10.5 10.5 0 0 1 5.5 16.5V5H4ZM6.449999999999999 8.5a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM6.75 13.5a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM8.15 18.3a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM23.25 8.5a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM22.950000000000003 13.5a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM21.55 18.3a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM12.049999999999999 23.3a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0ZM17.650000000000002 23.3a1.15 1.15 0 1 0 2.3 0a1.15 1.15 0 1 0 -2.3 0Z"/></svg>';
  return s;
}

/**
 * Lay the engagements out: each knight with its foes (knights fighting the
 * same foe share a cluster), flowed across a field W wide like words in a
 * paragraph. Returns {placed: [[item, x, y]], lines: [[knightId, foeId]], height}.
 */
export function layoutField(knights, foes, W, { scale = 1, tokW = 130, tokH = 96, gap = 8 } = {}) {
  const S = (n) => n * scale;
  // No two labels may overlap: a token's box is tokW × tokH around its anchor
  // (every token hangs from its anchor the same way, so anchors compare
  // directly). Foes give way; knights hold their place.
  const separate = (pos) => {
    for (let iter = 0; iter < 60; iter++) {
      let moved = false;
      for (let i = 0; i < pos.length; i++) {
        for (let j = i + 1; j < pos.length; j++) {
          const a = pos[i], b = pos[j];
          const dx = b[1] - a[1], dy = b[2] - a[2];
          const ox = tokW + gap - Math.abs(dx), oy = tokH + gap - Math.abs(dy);
          if (ox <= 0 || oy <= 0) continue;
          const wa = a[0].side === "party" ? 0 : 1, wb = b[0].side === "party" ? 0 : 1;
          if (!wa && !wb) continue;
          const share = (w) => w / (wa + wb);
          if (ox < oy) {                                    // push apart sideways
            const sgn = dx === 0 ? (i % 2 ? 1 : -1) : Math.sign(dx);
            a[1] -= sgn * ox * share(wa); b[1] += sgn * ox * share(wb);
          } else {                                          // push apart up/down
            const sgn = dy === 0 ? 1 : Math.sign(dy);
            a[2] -= sgn * oy * share(wa); b[2] += sgn * oy * share(wb);
          }
          moved = true;
        }
      }
      if (!moved) break;
    }
    return pos;
  };
  const live = foes.filter((f) => !f.down && (f.linked || []).length);
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
        live.filter((f) => f.linked.includes(x.name)).forEach((f) => todo.push(f));
      } else {
        g.fs.push(x);
        knights.filter((kk) => x.linked.includes(kk.name)).forEach((kk) => todo.push(kk));
      }
    }
    groups.push(g);
  }
  const ring = (list, r, start, sy = .85) => list.map((t, j) => {
    const a = start + (2 * Math.PI * j) / list.length;
    return [t, r * Math.cos(a), r * sy * Math.sin(a)];
  });
  const shape = (g) => {
    let pos;
    if (g.ks.length === 1) {
      const n = g.fs.length;
      pos = [[g.ks[0], 0, 0], ...ring(g.fs, S(92 + Math.max(0, n - 6) * 9), n === 2 ? Math.PI : Math.PI / 2)];
    } else {
      const shared = g.fs.filter((f) => f.linked.filter((n) => g.ks.some((k) => k.name === n)).length > 1);
      const R = shared.length ? S(135) : 0;
      pos = [...(shared.length === 1 ? [[shared[0], 0, 0]] : ring(shared, S(48), Math.PI / 2))];
      g.ks.forEach((k, i) => {
        const th = Math.PI + (2 * Math.PI * i) / g.ks.length, kx = R * Math.cos(th), ky = R * .8 * Math.sin(th);
        pos.push([k, kx, ky]);
        const own = g.fs.filter((f) => !shared.includes(f) && f.linked.includes(k.name));
        own.forEach((f, j) => {
          const a = th + (j - (own.length - 1) / 2) * 1.05;
          pos.push([f, kx + S(110) * Math.cos(a), ky + S(110) * .9 * Math.sin(a)]);
        });
      });
    }
    separate(pos);
    const xs = pos.map((p) => p[1]), ys = pos.map((p) => p[2]);
    const box = { x0: Math.min(...xs) - tokW / 2 - 4, x1: Math.max(...xs) + tokW / 2 + 4, y0: Math.min(...ys) - S(30), y1: Math.max(...ys) + tokH - S(26) };
    return { pos, w: box.x1 - box.x0, h: box.y1 - box.y0, box };
  };
  const shapes = groups.map(shape), rowsOf = [[]];
  let x = 0;
  for (const sh of shapes) {
    if (x + sh.w > W - 16 && rowsOf.at(-1).length) { rowsOf.push([]); x = 0; }
    rowsOf.at(-1).push(sh); x += sh.w + 12;
  }
  const placed = [];
  let y = 12;
  for (const row of rowsOf) {
    const rowW = row.reduce((t, sh) => t + sh.w, 0) + 12 * (row.length - 1), rowH = Math.max(...row.map((sh) => sh.h));
    let ox = (W - rowW) / 2;
    for (const sh of row) {
      const cx = ox - sh.box.x0, cy = y + (rowH - sh.h) / 2 - sh.box.y0;
      sh.pos.forEach(([t, dx, dy]) => placed.push([t, cx + dx, cy + dy]));
      ox += sh.w + 12;
    }
    y += rowH + 14;
  }
  const lines = [];
  groups.forEach((g) => g.fs.forEach((f) => g.ks.forEach((k) => { if (f.linked.includes(k.name)) lines.push([k.id, f.id]); })));
  return { placed, lines, height: Math.max(S(240), y + 6) };
}

/**
 * Draw the engagement lines between tokens on a stage, and keep them right
 * as the stage resizes. ``cls`` names the stage's token class (tokens carry
 * data-id and a .ftok-face), ``glowId`` keeps SVG filter ids unique per page.
 */
export function linkLines(stage, svg, lines, { glowId = "field-glow" } = {}) {
  const draw = () => {
    const box = stage.getBoundingClientRect();
    const centre = (id) => {
      const f = stage.querySelector(`[data-id="${CSS.escape(id)}"] .ftok-face`);
      if (!f) return null;
      const b = f.getBoundingClientRect();
      return [b.left - box.left + b.width / 2, b.top - box.top + b.height / 2];
    };
    svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
    svg.innerHTML = `<defs><filter id="${glowId}" filterUnits="userSpaceOnUse" x="0" y="0" width="${box.width}" height="${box.height}"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>` +
      lines.map(([a, b]) => { const p = centre(a), q = centre(b); return p && q ? `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" class="cbt-link" filter="url(#${glowId})"/>` : ""; }).join("");
  };
  requestAnimationFrame(draw);
  const ro = new ResizeObserver(() => { if (!stage.isConnected) return ro.disconnect(); draw(); });
  ro.observe(stage);
}
