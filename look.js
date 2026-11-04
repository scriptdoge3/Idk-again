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

  /* ---------- 2.5D room, drawn by hand on one canvas behind the cabinets ----------
     The cabinet fronts are the z = 0 plane. Wall, ladder tray, cable drops and
     floor sit at real depth and are projected for the current camera position,
     so panning gives parallax and a floor that recedes. One redraw per pan frame. */
  const DEPTH = 300;                         // cabinet depth ≈ 600 mm, lineup px
  const TRAY_Y = -17, TRAY_W = 130, TRAY_GAP = 6, CAM_P = 1800;
  const ROOM = { drops: [], W: 0, H: 0, cabTop: 110, ready: false };
  function initRoom(lineup, seed) {
    const R = rng(seed);
    const cabs = [...lineup.querySelectorAll('.cab')];
    ROOM.W = lineup.offsetWidth; ROOM.H = lineup.offsetHeight;
    ROOM.cabTop = cabs.length ? cabs[0].offsetTop : 110;
    ROOM.drops = [];
    cabs.forEach(cb => {
      const n = 3 + Math.floor(R() * 3);
      for (let i = 0; i < n; i++) ROOM.drops.push({
        x: cb.offsetLeft + 40 + R() * (cb.offsetWidth - 80), t: 4 + R() * 7, bend: (R() - 0.5) * 34,
        col: R() < 0.7 ? '#1d1d1c' : (R() < 0.5 ? '#3b3b39' : '#55554f'),
      });
    });
    ROOM.cables = Array.from({ length: 7 }, () => ({ f: 0.12 + R() * 0.76, t: 6 + R() * 9, c: R() < 0.75 ? '#151514' : '#3a3a37' }));
    ROOM.ready = true;
  }
  function drawRoom(c, cam) {
    if (!ROOM.ready) return;
    const { Z, sl, cw, ch, vx, vy, dpr } = cam;
    const W = ROOM.W, H = ROOM.H, D = DEPTH;
    if (c.width !== Math.round(cw * dpr) || c.height !== Math.round(ch * dpr)) { c.width = Math.round(cw * dpr); c.height = Math.round(ch * dpr); }
    const g = c.getContext('2d');
    const sc = z => CAM_P / (CAM_P - z);
    const P3 = (x, y, z) => { const s = sc(z); return [(vx + (x - vx) * s) * Z - sl, (vy + (y - vy) * s) * Z]; };
    const plane = z => { const s = sc(z); g.setTransform(dpr * Z * s, 0, 0, dpr * Z * s, dpr * ((vx * (1 - s)) * Z - sl), dpr * (vy * (1 - s)) * Z); };
    const xl = (sl / Z) - 3000, xr = (sl + cw) / Z + 3000;

    // --- back wall (z = -D), painted in its own coordinates
    plane(-D);
    let gr = g.createLinearGradient(0, -900, 0, H);
    gr.addColorStop(0, '#5c6555'); gr.addColorStop(0.45, '#6c7563'); gr.addColorStop(0.75, '#5a6252'); gr.addColorStop(1, '#4a5143');
    g.fillStyle = gr; g.fillRect(xl, -2500, xr - xl, H + 2500);
    if (PEEL) { g.fillStyle = g.createPattern(PEEL, 'repeat'); g.fillRect(xl, -2500, xr - xl, H + 2500); }
    for (const px of POOLX) {
      g.save(); g.translate(px, -40); g.scale(1, 1.25);
      const pg = g.createRadialGradient(0, 0, 0, 0, 0, 420);
      pg.addColorStop(0, 'rgba(255,248,226,.16)'); pg.addColorStop(1, 'rgba(255,248,226,0)');
      g.fillStyle = pg; g.fillRect(-420, -420, 840, 840); g.restore();
    }
    gr = g.createLinearGradient(0, H - 36, 0, H);            // skirting
    gr.addColorStop(0, '#3d3630'); gr.addColorStop(0.85, '#2c2723'); gr.addColorStop(1, '#151311');
    g.fillStyle = gr; g.fillRect(xl, H - 36, xr - xl, 36);
    for (let x = 140; x < W + 1600; x += 900) {               // tray bracket wall plates
      gr = g.createLinearGradient(x - 8, 0, x + 8, 0);
      gr.addColorStop(0, '#8b8c86'); gr.addColorStop(0.45, '#c5c6c0'); gr.addColorStop(1, '#6e6f6a');
      g.fillStyle = 'rgba(0,0,0,.30)'; g.fillRect(x - 6, TRAY_Y - 21, 18, 36);
      g.fillStyle = gr; g.fillRect(x - 8, TRAY_Y - 24, 16, 34);
    }
    const shTop = TRAY_Y + 2, shg = g.createLinearGradient(0, shTop, 0, shTop + 70);   // tray shadow on the wall
    shg.addColorStop(0, 'rgba(0,0,0,.35)'); shg.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = shg; g.fillRect(xl, shTop, xr - xl, 70);

    // --- cable drops (vertical plane in the middle of the tray)
    const zd = -D + TRAY_GAP + TRAY_W * 0.5, dh = ROOM.cabTop - TRAY_Y + 90;
    plane(zd);
    for (const d of ROOM.drops) {
      const y0 = TRAY_Y + 2;
      g.strokeStyle = d.col; g.lineWidth = d.t;
      g.beginPath(); g.moveTo(d.x + d.bend, y0); g.bezierCurveTo(d.x + d.bend, y0 + dh * 0.45, d.x, y0 + dh * 0.4, d.x, y0 + dh); g.stroke();
      g.strokeStyle = 'rgba(255,255,255,.12)'; g.lineWidth = 1;
      const o = d.t * 0.25;
      g.beginPath(); g.moveTo(d.x + d.bend - o, y0); g.bezierCurveTo(d.x + d.bend - o, y0 + dh * 0.45, d.x - o, y0 + dh * 0.4, d.x - o, y0 + dh); g.stroke();
    }

    // --- ladder tray seen from below (horizontal plane y = TRAY_Y between zb and zf)
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const zb = -D + TRAY_GAP, zf = zb + TRAY_W;
    const quad = (a, b, c2, d2) => { g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.lineTo(...c2); g.lineTo(...d2); g.closePath(); };
    quad(P3(xl, TRAY_Y, zb), P3(xr, TRAY_Y, zb), P3(xr, TRAY_Y, zf), P3(xl, TRAY_Y, zf));
    g.fillStyle = '#121211'; g.fill();
    for (const cb of ROOM.cables) {                           // cables lying in the tray, seen between rungs
      const z = zb + cb.f * TRAY_W, s = sc(z);
      const a = P3(xl, TRAY_Y, z), b = P3(xr, TRAY_Y, z);
      g.strokeStyle = cb.c; g.lineWidth = Math.max(1, cb.t * Z * s * 0.35);
      g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
    }
    const firstRung = Math.floor(xl / 38) * 38;
    for (let x = firstRung; x < xr; x += 38) {                // rungs converge on the vanishing point
      const a = P3(x, TRAY_Y, zb), b = P3(x, TRAY_Y, zf);
      if (Math.max(a[0], b[0]) < -20 || Math.min(a[0], b[0]) > cw + 20) continue;
      const bracket = ((x - 140) % 900 + 900) % 900 < 38;
      g.strokeStyle = bracket ? '#4f504b' : '#7c7d78'; g.lineWidth = (bracket ? 12 : 5) * Z * sc((zb + zf) / 2);
      g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
      g.strokeStyle = 'rgba(255,255,255,.18)'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(a[0] + 1, a[1]); g.lineTo(b[0] + 1, b[1]); g.stroke();
    }
    for (const [z, col] of [[zb + 3, '#62635e'], [zf - 3, '#8a8b86']]) {   // bottom flanges of the side rails
      const a = P3(xl, TRAY_Y, z), b = P3(xr, TRAY_Y, z);
      g.strokeStyle = col; g.lineWidth = 7 * Z * sc(z); g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
    }
    // front side rail (vertical face toward the camera)
    const r1 = P3(xl, TRAY_Y - 14, zf + 1), r2 = P3(xr, TRAY_Y, zf + 1);
    gr = g.createLinearGradient(0, r1[1], 0, r2[1]);
    gr.addColorStop(0, '#e2e3dd'); gr.addColorStop(0.3, '#b4b5af'); gr.addColorStop(0.7, '#8e8f8a'); gr.addColorStop(1, '#63645f');
    g.fillStyle = gr; g.fillRect(r1[0], r1[1], r2[0] - r1[0], r2[1] - r1[1]);

    // --- floor (y = H) from the wall to the camera
    const yw = P3(0, H, -D)[1], yb = ch;
    if (yw < yb) {
      gr = g.createLinearGradient(0, yw, 0, yb);
      gr.addColorStop(0, '#27231e'); gr.addColorStop(0.35, '#3a332b'); gr.addColorStop(1, '#2c2721');
      g.fillStyle = gr; g.fillRect(0, yw, cw, yb - yw);
      if (PEEL) { g.globalAlpha = 0.8; g.fillStyle = g.createPattern(PEEL, 'repeat'); g.fillRect(0, yw, cw, yb - yw); g.globalAlpha = 1; }
      const sB = (yb / Z - vy) / (H - vy), zEnd = sB > 1 ? Math.min(CAM_P * 0.97, CAM_P - CAM_P / sB) : 0;
      g.strokeStyle = 'rgba(0,0,0,.30)'; g.lineWidth = 1.2;
      for (let x = Math.floor(xl / 300) * 300; x < xr; x += 300) {          // tile joints running toward you
        const a = P3(x, H, -D), b = P3(x, H, zEnd);
        if (Math.max(a[0], b[0]) < -50 || Math.min(a[0], b[0]) > cw + 50) continue;
        g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
      }
      for (let z = -D; z < zEnd; z += 300) {                                 // tile joints across
        const y = P3(0, H, z)[1];
        g.lineWidth = Math.max(1, 1.2 * sc(z)); g.beginPath(); g.moveTo(0, y); g.lineTo(cw, y); g.stroke();
      }
      for (const px of POOLX) {                                              // tube reflections in the lino
        const z = 380, [x, y] = P3(px, H, z), s = sc(z);
        if (x < -300 || x > cw + 300) continue;
        g.save(); g.translate(x, y); g.scale(1, 0.18);
        const rg = g.createRadialGradient(0, 0, 0, 0, 0, 260 * Z * s);
        rg.addColorStop(0, 'rgba(255,248,226,.10)'); rg.addColorStop(1, 'rgba(255,248,226,0)');
        g.fillStyle = rg; g.fillRect(-300 * Z * s, -300 * Z * s, 600 * Z * s, 600 * Z * s); g.restore();
      }
      const y0 = P3(0, H, 0)[1], y1 = P3(0, H, 60)[1];                       // contact shadow under the cabinets
      gr = g.createLinearGradient(0, y0 - 2, 0, y1);
      gr.addColorStop(0, 'rgba(0,0,0,.75)'); gr.addColorStop(0.25, 'rgba(0,0,0,.4)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
      const cx0 = P3(0, H, 0)[0], cx1 = P3(W, H, 0)[0];
      g.fillStyle = gr; g.fillRect(cx0 + 40 * Z, y0 - 2, cx1 - cx0 - 80 * Z, y1 - y0 + 2);
    }
  }

  /* ---------- depth for the hardware on the doors ----------
     Each part gets a depth and a side colour; CSS draws its sides toward the
     camera from the part's position and the live vanishing point. */
  const DEPTHS = [
    ['.mwrap', 8, '#0d0d0c'], ['.clockbox', 12, '#121211'], ['.ctr', 4, '#0b0b0b'], ['.lamp', 6, '#3b3b38'],
    ['.pb', 9, '#3e3d39'], ['.rot', 15, '#0b0b0b'], ['.estop', 3, '#7d6005'], ['.estop .mush', 18, '#5a0902'],
    ['.dsw', 10, '#0c0c0c'], ['.relay', 12, '#141412'], ['.lockout', 5, '#1a1a17'], ['.lockout .lh', 11, '#3c3b36'],
    ['.rec', 10, '#141412'], ['.printer', 16, '#7a725f'], ['.ann', 8, '#121211'], ['.door .handle', 16, '#060606'],
    ['.blank', 2, '#7a7565'], ['.plate-metal', 2, '#6f6f68'], ['.clip', 4, '#3f2a14'], ['.np .name', 2, '#050505'], ['.np .code', 2, '#050505'],
  ];
  function depths(lineup) {
    for (const [sel, d, sc] of DEPTHS) {
      lineup.querySelectorAll(sel).forEach(e => {
        e.classList.add('x3');
        e.style.setProperty('--d', d + 'px');
        e.style.setProperty('--sc', sc);
        const p = relPos(e, lineup);
        e.style.setProperty('--x', (p.x + p.w / 2).toFixed(0));
        e.style.setProperty('--y', (p.y + p.h / 2).toFixed(0));
      });
    }
  }

  /* ---------- ceiling light pools + falloff, baked to match the lineup ---------- */
  function lighting(lineup) {
    POOLX.length = 0;
    for (let x = 260; x < lineup.offsetWidth + STEP; x += STEP) POOLX.push(x);
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
    imperfections(lineup, 3);
    initRoom(lineup, 4);
    depths(lineup);
  }
  peel(); grain();
  return { apply, rng, lightAt, relPos, drawRoom, CAM_P };
})();
