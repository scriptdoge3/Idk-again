'use strict';
/* =====================================================================
   LOOK · surface realism for the cabinets
   Procedural grime, wear, fingerprints, scratches, plinth scuffs, the
   cable tray, ceiling-light pools and camera grain. Everything is drawn
   once after layout; nothing here runs per frame.
   ===================================================================== */
window.LOOK = (() => {
  function rng(seed) {
    let s = (seed * 2654435761) >>> 0 || 1;
    return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }
  function cv(w, h) { const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c; }

  /* low-frequency value noise: tiny random canvas scaled up with smoothing */
  function blotches(R, w, h, cell, rgb, aMax) {
    const nw = Math.max(2, Math.ceil(w / cell)), nh = Math.max(2, Math.ceil(h / cell));
    const n = cv(nw, nh), g = n.getContext('2d'), id = g.createImageData(nw, nh);
    for (let i = 0; i < id.data.length; i += 4) {
      const v = R();
      id.data[i] = rgb[0]; id.data[i + 1] = rgb[1]; id.data[i + 2] = rgb[2];
      id.data[i + 3] = Math.round(255 * aMax * v * v);
    }
    g.putImageData(id, 0, 0);
    return n;
  }
  function relPos(el, root) {
    let x = 0, y = 0, e = el;
    while (e && e !== root) { x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; }
    return { x, y, w: el.offsetWidth, h: el.offsetHeight };
  }
  function blob(g, x, y, r, rgba) {
    const gr = g.createRadialGradient(x, y, 0, x, y, r);
    gr.addColorStop(0, rgba); gr.addColorStop(1, rgba.replace(/[\d.]+\)$/, '0)'));
    g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
  }
  function fingerprint(g, R, x, y, s) {
    const rot = (R() - 0.5) * 1.6;
    g.save(); g.translate(x, y); g.rotate(rot);
    blob(g, 0, 0, 9 * s, 'rgba(70,58,40,0.07)');
    g.strokeStyle = 'rgba(60,48,32,0.075)'; g.lineWidth = 0.55;
    for (let i = 0; i < 11; i++) {
      const a0 = R() * 0.6, a1 = Math.PI * 2 - R() * 0.9;
      g.beginPath(); g.ellipse(R() * 0.6, R() * 0.6, (1.6 + i * 0.95) * s, (2.4 + i * 1.25) * s, 0, a0, a1); g.stroke();
    }
    g.restore();
  }
  function scratch(g, R, x, y, len, ang, a) {
    g.strokeStyle = `rgba(255,252,240,${a})`; g.lineWidth = 0.4 + R() * 0.5;
    g.beginPath(); g.moveTo(x, y);
    const cx = x + Math.cos(ang) * len * 0.5 + (R() - 0.5) * 6, cy = y + Math.sin(ang) * len * 0.5 + (R() - 0.5) * 6;
    g.quadraticCurveTo(cx, cy, x + Math.cos(ang) * len, y + Math.sin(ang) * len); g.stroke();
  }

  /* ---------- per-door wear maps ---------- */
  function doorSkin(door, seed, lineup) {
    const R = rng(seed + 11);
    const W = door.clientWidth, H = door.clientHeight;
    // multiply layer: dirt, grime, smudges, fingerprints
    const m = cv(W, H), g = m.getContext('2d');
    g.imageSmoothingEnabled = true;
    g.drawImage(blotches(R, W, H, 70, [120, 105, 80], 0.20), 0, 0, W, H);
    g.drawImage(blotches(R, W, H, 18, [110, 98, 76], 0.10), 0, 0, W, H);
    let gr = g.createLinearGradient(0, H * 0.70, 0, H);           // floor-level dirt
    gr.addColorStop(0, 'rgba(95,82,62,0)'); gr.addColorStop(1, 'rgba(95,82,62,0.26)');
    g.fillStyle = gr; g.fillRect(0, 0, W, H);
    gr = g.createLinearGradient(0, 0, 0, 40);                      // dust under the roof edge
    gr.addColorStop(0, 'rgba(90,80,62,0.22)'); gr.addColorStop(1, 'rgba(90,80,62,0)');
    g.fillStyle = gr; g.fillRect(0, 0, W, 40);
    for (let i = 0; i < 5; i++) {                                  // faint run-off streaks
      const x = R() * W, w = 6 + R() * 18, y0 = R() * H * 0.3, len = 80 + R() * 260;
      const sg = g.createLinearGradient(0, y0, 0, y0 + len);
      sg.addColorStop(0, 'rgba(100,88,66,0)'); sg.addColorStop(0.3, 'rgba(100,88,66,0.06)'); sg.addColorStop(1, 'rgba(100,88,66,0)');
      g.fillStyle = sg; g.fillRect(x, y0, w, len);
    }
    // door handle: decades of hands
    blob(g, W - 10, H * 0.47 + 46, 85, 'rgba(70,58,40,0.20)');
    blob(g, W - 16, H * 0.47 + 70, 40, 'rgba(60,48,32,0.18)');
    for (let i = 0; i < 4; i++) fingerprint(g, R, W - 30 - R() * 40, H * 0.47 + 20 + R() * 80, 0.9 + R() * 0.3);
    // controls: grime where fingers go
    door.querySelectorAll('.rot, .pb, .dsw, .estop, .lh, .rst, .card').forEach(el => {
      const p = relPos(el, door);
      const cx = p.x + p.w / 2, cy = p.y + p.h / 2, r = Math.max(p.w, p.h);
      const use = el.classList.contains('card') ? 0.5 : 0.35 + R() * 0.75;
      blob(g, cx + 3, cy + r * 0.25, r * 0.95, `rgba(72,60,42,${(0.10 * use).toFixed(3)})`);
      if (R() < 0.45) fingerprint(g, R, cx + (R() - 0.3) * r * 1.1, cy + r * (0.35 + R() * 0.4), 0.8 + R() * 0.35);
    });
    // a little rust bloom at the bottom corners
    for (const x of [6, W - 6]) for (let i = 0; i < 6; i++) blob(g, x + (R() - 0.5) * 16, H - 4 - R() * 18, 2 + R() * 6, 'rgba(140,72,30,0.20)');
    m.className = 'wear mul';

    // screen layer: scratches, worn edges, chips
    const s = cv(W, H), h = s.getContext('2d');
    const nS = 12 + Math.floor(R() * 12);
    for (let i = 0; i < nS; i++) {
      const nearHandle = R() < 0.35;
      const x = nearHandle ? W - 20 - R() * 90 : R() * W, y = nearHandle ? H * 0.40 + R() * H * 0.25 : H * (0.25 + R() * 0.75);
      scratch(h, R, x, y, 8 + R() * 70, (R() - 0.5) * 1.2 + (R() < 0.3 ? 1.4 : 0), 0.10 + R() * 0.22);
    }
    for (let i = 0; i < 80; i++) {                                 // paint worn on the door edges
      const side = Math.floor(R() * 4), t = R();
      const x = side === 0 ? t * W : side === 1 ? W - 1.5 : side === 2 ? t * W : 1.5;
      const y = side === 0 ? 1.5 : side === 1 ? t * H : side === 2 ? H - 1.5 : t * H;
      blob(h, x, y, 1 + R() * 3.5, `rgba(255,250,236,${(0.12 + R() * 0.25).toFixed(2)})`);
    }
    for (let i = 0; i < 7; i++) {                                  // chips down to primer
      const x = R() * W, y = H * (0.5 + R() * 0.5);
      h.fillStyle = 'rgba(255,240,215,0.30)';
      h.beginPath(); h.ellipse(x, y, 0.8 + R() * 2, 0.6 + R() * 1.4, R() * 3, 0, 7); h.fill();
    }
    // ---- compose: paint, orange peel, grime (multiply), wear (screen), room light ----
    const k = Math.min(2, window.devicePixelRatio || 1);
    const out = cv(W * k, H * k), o = out.getContext('2d');
    o.scale(k, k);
    o.fillStyle = '#bab5a2'; o.fillRect(0, 0, W, H);
    if (PEEL) { o.fillStyle = o.createPattern(PEEL, 'repeat'); o.fillRect(0, 0, W, H); }
    let lg = o.createLinearGradient(0, 0, 0, H);
    lg.addColorStop(0, 'rgba(255,255,255,.12)'); lg.addColorStop(0.3, 'rgba(255,255,255,0)'); lg.addColorStop(0.8, 'rgba(0,0,0,.05)'); lg.addColorStop(1, 'rgba(0,0,0,.10)');
    o.fillStyle = lg; o.fillRect(0, 0, W, H);
    o.globalCompositeOperation = 'multiply'; o.drawImage(m, 0, 0, W, H);
    o.globalCompositeOperation = 'screen'; o.drawImage(s, 0, 0, W, H);
    const dp = relPos(door, lineup), cab = door.closest('.cab');
    const cTop = cab.offsetTop, cH = cab.offsetHeight;
    o.globalCompositeOperation = 'soft-light';
    for (const px of POOLX) {
      o.save(); o.translate(px - dp.x, POOLY - dp.y); o.scale(1, POOLRY / POOLRX);
      const pg = o.createRadialGradient(0, 0, 0, 0, 0, POOLRX);
      pg.addColorStop(0, 'rgba(255,248,226,.30)'); pg.addColorStop(0.45, 'rgba(255,248,226,.10)'); pg.addColorStop(0.75, 'rgba(255,248,226,0)');
      o.fillStyle = pg; o.fillRect(-POOLRX, -POOLRX, POOLRX * 2, POOLRX * 2); o.restore();
    }
    o.globalCompositeOperation = 'multiply';
    const fy0 = cTop - dp.y, fg = o.createLinearGradient(0, fy0, 0, fy0 + cH);
    FALL.forEach(([t, c]) => fg.addColorStop(t, c));
    o.fillStyle = fg; o.fillRect(0, 0, W, H);
    o.globalCompositeOperation = 'source-over';
    // pressed-steel door edges, and the roof's shadow on the top of the door
    o.fillStyle = 'rgba(255,255,255,.45)'; o.fillRect(0, 0, W, 1); o.fillRect(0, 0, 1, H);
    o.fillStyle = 'rgba(0,0,0,.28)'; o.fillRect(0, H - 1, W, 1); o.fillRect(W - 1, 0, 1, H);
    const rs = o.createLinearGradient(0, 0, 0, 18); rs.addColorStop(0, 'rgba(0,0,0,.28)'); rs.addColorStop(1, 'rgba(0,0,0,0)');
    o.fillStyle = rs; o.fillRect(0, 0, W, 18);
    out.className = 'skin';
    out.style.width = W + 'px'; out.style.height = H + 'px';
    door.prepend(out);
  }

  /* light falling on any point of the lineup: used by the meters' glass */
  const POOLX = [], POOLY = -60, POOLRX = 520, POOLRY = 760, STEP = 780;
  const FALL = [[0, '#f3f1ec'], [0.35, '#ebe8e1'], [0.75, '#d6d1c6'], [1, '#aaa498']];
  const FALLV = [[0, 0.946], [0.35, 0.913], [0.75, 0.825], [1, 0.640]];
  function lightAt(x, y, cabTop, cabH) {
    let glow = 0;
    for (const px of POOLX) {
      const d = Math.hypot((x - px) / POOLRX, (y - POOLY) / POOLRY);
      glow += d < 0.45 ? 0.30 - 0.20 * d / 0.45 : d < 0.75 ? 0.10 * (1 - (d - 0.45) / 0.30) : 0;
    }
    const t = Math.max(0, Math.min(1, (y - cabTop) / cabH));
    let v = 1;
    for (let i = 1; i < FALLV.length; i++) if (t <= FALLV[i][0]) { const [t0, a] = FALLV[i - 1], [t1, b] = FALLV[i]; v = a + (b - a) * (t - t0) / (t1 - t0); break; }
    return { glow, shade: 1 - v };
  }

  function plinthScuffs(pl, seed) {
    const R = rng(seed + 77), W = pl.clientWidth, H = pl.clientHeight;
    const c = cv(W, H), g = c.getContext('2d');
    for (let i = 0; i < 14; i++) {
      const x = R() * W, y = H * (0.35 + R() * 0.6), len = 14 + R() * 60;
      g.strokeStyle = `rgba(200,195,180,${(0.06 + R() * 0.12).toFixed(2)})`; g.lineWidth = 1 + R() * 3; g.lineCap = 'round';
      g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x + len / 2, y - 3 - R() * 6, x + len, y + (R() - 0.5) * 4); g.stroke();
    }
    g.drawImage(blotches(R, W, H, 14, [190, 185, 170], 0.10), 0, 0, W, H);
    c.className = 'scuff';
    pl.appendChild(c);
  }

  /* ---------- cable ladder tray with drops into the cabinet roofs ---------- */
  function cableTray(lineup, seed) {
    const R = rng(seed);
    const W = lineup.scrollWidth, H = 100;
    const c = cv(W * 2, H * 2); c.style.width = W + 'px'; c.style.height = H + 'px';
    c.className = 'tray';
    const g = c.getContext('2d'); g.scale(2, 2);
    const cabs = [...lineup.querySelectorAll('.cab')];
    const yR1 = 14, yR2 = 40;
    // drops first (behind the tray rail)
    const drops = [];
    cabs.forEach(cb => {
      const n = 2 + Math.floor(R() * 3);
      for (let i = 0; i < n; i++) drops.push(cb.offsetLeft + 40 + R() * (cb.offsetWidth - 80));
    });
    for (const x of drops) {
      const thick = 4 + R() * 7, col = R() < 0.7 ? '#1d1d1c' : (R() < 0.5 ? '#3b3b39' : '#55554f');
      const bend = (R() - 0.5) * 30;
      g.strokeStyle = col; g.lineWidth = thick; g.lineCap = 'butt';
      g.beginPath(); g.moveTo(x + bend, yR1 + 10); g.bezierCurveTo(x + bend, 60, x, 62, x, H); g.stroke();
      g.strokeStyle = 'rgba(255,255,255,.10)'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(x + bend - thick * 0.25, yR1 + 10); g.bezierCurveTo(x + bend - thick * 0.25, 60, x - thick * 0.25, 62, x - thick * 0.25, H); g.stroke();
      // gland on the roof
      const gl = g.createLinearGradient(x - thick, 0, x + thick, 0);
      gl.addColorStop(0, '#5d5d58'); gl.addColorStop(0.45, '#c9c8c0'); gl.addColorStop(1, '#4c4c48');
      g.fillStyle = gl; g.fillRect(x - thick * 0.9, H - 9, thick * 1.8, 9);
      g.fillStyle = '#2a2a28'; g.fillRect(x - thick * 0.9, H - 9, thick * 1.8, 1.2);
    }
    // cables lying in the tray
    for (let k = 0; k < 9; k++) {
      const y = yR1 + 6 + R() * (yR2 - yR1 - 10), thick = 3 + R() * 6;
      g.strokeStyle = R() < 0.75 ? '#1b1b1a' : '#4a4a46'; g.lineWidth = thick;
      g.beginPath(); g.moveTo(0, y);
      for (let x = 0; x <= W; x += 120) g.lineTo(x, y + Math.sin(x / 170 + k) * 1.6);
      g.stroke();
    }
    // ladder: rungs + side rails (hot-dip galvanized)
    for (let x = 6; x < W; x += 34) {
      const rg = g.createLinearGradient(0, yR1, 0, yR2);
      rg.addColorStop(0, '#9a9b96'); rg.addColorStop(0.5, '#c8c9c3'); rg.addColorStop(1, '#7f807b');
      g.fillStyle = rg; g.fillRect(x, yR1, 5, yR2 - yR1);
    }
    for (const y of [yR1 - 6, yR2]) {
      const rg = g.createLinearGradient(0, y, 0, y + 8);
      rg.addColorStop(0, '#d8d9d3'); rg.addColorStop(0.35, '#a7a8a2'); rg.addColorStop(1, '#6f706b');
      g.fillStyle = rg; g.fillRect(0, y, W, 8);
      for (let i = 0; i < W / 3; i++) { g.fillStyle = `rgba(${R() < 0.5 ? '255,255,255' : '0,0,0'},${(R() * 0.07).toFixed(3)})`; g.fillRect(R() * W, y + R() * 8, 2 + R() * 6, 1 + R() * 2); }
    }
    // wall brackets
    for (let x = 140; x < W; x += 900) {
      g.fillStyle = '#6c6d68'; g.fillRect(x, 0, 10, yR2 + 10);
      g.fillStyle = 'rgba(0,0,0,.25)'; g.fillRect(x + 10, 0, 3, yR2 + 10);
    }
    // shadow cast on the wall below the tray
    const sh = g.createLinearGradient(0, yR2 + 8, 0, yR2 + 30);
    sh.addColorStop(0, 'rgba(0,0,0,.28)'); sh.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = sh; g.fillRect(0, yR2 + 8, W, 22);
    lineup.prepend(c);
  }

  /* ---------- ceiling light pools + falloff, baked to match the lineup ---------- */
  function lighting(lineup) {
    POOLX.length = 0;
    for (let x = 260; x < lineup.scrollWidth + STEP; x += STEP) POOLX.push(x);
  }

  /* ---------- small imperfections: crooked labels, uneven dymo letters ---------- */
  function imperfections(root, seed) {
    const R = rng(seed + 5);
    root.querySelectorAll('.tag, .np .name, .np .code, .plate-metal, .blank').forEach(t => {
      t.style.setProperty('--rot', ((R() - 0.5) * 0.9).toFixed(2) + 'deg');
      t.style.setProperty('--dx', ((R() - 0.5) * 1.2).toFixed(2) + 'px');
    });
    root.querySelectorAll('.dymo').forEach(d => {
      const txt = d.textContent; d.textContent = '';
      for (const ch of txt) {
        const sp = document.createElement('span'); sp.textContent = ch;
        sp.style.display = 'inline-block';
        sp.style.transform = `translateY(${((R() - 0.5) * 1.1).toFixed(2)}px) rotate(${((R() - 0.5) * 3).toFixed(1)}deg)`;
        if (ch === ' ') sp.style.width = '.45em';
        d.appendChild(sp);
      }
      d.style.setProperty('--rot', ((R() - 0.5) * 2.2).toFixed(2) + 'deg');
    });
    root.querySelectorAll('.scr').forEach(s => s.style.setProperty('--a', Math.round(R() * 180) + 'deg'));
  }

  /* ---------- camera grain tile ---------- */
  function grain() {
    const c = cv(180, 180), g = c.getContext('2d'), id = g.createImageData(180, 180);
    for (let i = 0; i < id.data.length; i += 4) {
      const v = Math.random() * 255;
      id.data[i] = id.data[i + 1] = id.data[i + 2] = v; id.data[i + 3] = 255;
    }
    g.putImageData(id, 0, 0);
    document.documentElement.style.setProperty('--grain', `url(${c.toDataURL()})`);
  }

  /* orange-peel powder-coat micro texture (tiles) */
  function peel() {
    const N = 192, c = cv(N, N), g = c.getContext('2d'), id = g.createImageData(N, N);
    const R = rng(9);
    const base = new Float32Array(N * N);
    for (let i = 0; i < base.length; i++) base[i] = R();
    // cheap blur for a soft, bumpy surface
    const out = new Float32Array(N * N);
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      let s = 0;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) s += base[((y + dy + N) % N) * N + ((x + dx + N) % N)];
      out[y * N + x] = s / 25;
    }
    for (let i = 0; i < out.length; i++) {
      const v = (out[i] - 0.5) * 6;
      const sh = out[i] - out[(i + N - 1) % (N * N)];   // directional: lit from the top-left
      const l = 128 + v * 60 + sh * 900;
      id.data[i * 4] = id.data[i * 4 + 1] = id.data[i * 4 + 2] = Math.max(0, Math.min(255, l));
      id.data[i * 4 + 3] = 28;
    }
    g.putImageData(id, 0, 0);
    PEEL = c;
    document.documentElement.style.setProperty('--noise', `url(${c.toDataURL()})`);
  }
  let PEEL = null;

  function apply(lineup) {
    let seed = 1;
    lighting(lineup);
    lineup.querySelectorAll('.door').forEach(d => { if (!d.querySelector('.skin')) doorSkin(d, seed++ * 31, lineup); });
    lineup.querySelectorAll('.plinth').forEach(p => { if (!p.querySelector('.scuff')) plinthScuffs(p, seed++ * 17); });
    if (!lineup.querySelector('.tray')) cableTray(lineup, 4);
    imperfections(lineup, 3);
  }
  peel(); grain();
  return { apply, rng, lightAt, relPos };
})();
