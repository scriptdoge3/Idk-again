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
     The camera stands to the left of the row and looks along it (yaw), at eye
     height. The cabinet fronts are the z = 0 plane and are turned by CSS with
     exactly the same projection; the wall, the floor and the exposed end of the
     first cabinet are projected here. */
  const DEPTH = 300, CAM_P = 1600;           // cabinet depth ≈ 600 mm; camera distance, lineup px
  const ROOM = { W: 0, H: 0, cabTop: 70, cabL: 60, cabR: 0, ready: false };
  function initRoom(lineup) {
    const cabs = [...lineup.querySelectorAll('.cab')];
    ROOM.W = lineup.offsetWidth; ROOM.H = lineup.offsetHeight;
    ROOM.cabTop = cabs.length ? cabs[0].offsetTop : 70;
    ROOM.cabL = cabs.length ? cabs[0].offsetLeft : 60;
    ROOM.cabR = cabs.length ? cabs[cabs.length - 1].offsetLeft + cabs[cabs.length - 1].offsetWidth : ROOM.W;
    ROOM.ready = true;
  }
  function projector(cam) {
    const { Z, sl, Ox, Oy, yaw, pitch } = cam, Ps = CAM_P * Z;
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    return (x, y, z) => {
      const X = x * Z - Ox, Y = y * Z - Oy, Zz = z * Z;
      const X1 = X * cy + Zz * sy, Z1 = -X * sy + Zz * cy;
      const Y1 = Y * cp - Z1 * sp, Z2 = Y * sp + Z1 * cp;
      const s = Ps / Math.max(Ps * 0.08, Ps - Z2);
      return [Ox + X1 * s - sl, Oy + Y1 * s, s];
    };
  }
  function drawRoom(c, cam) {
    if (!ROOM.ready) return;
    const { Z, cw, ch, dpr, Ox, sl } = cam;
    const W = ROOM.W, H = ROOM.H, D = DEPTH;
    if (c.width !== Math.round(cw * dpr) || c.height !== Math.round(ch * dpr)) { c.width = Math.round(cw * dpr); c.height = Math.round(ch * dpr); }
    const g = c.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const P3 = projector(cam);
    const vxL = Ox / Z;
    const xa = vxL - 2600, xb = vxL + 7000;
    const poly = pts => { g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.closePath(); };

    // back wall (z = -D)
    g.fillStyle = '#40463b'; g.fillRect(0, 0, cw, ch);
    const wTop = P3(vxL, -1500, -D), wBot = P3(vxL, H, -D);
    let gr = g.createLinearGradient(0, wTop[1], 0, wBot[1]);
    gr.addColorStop(0, '#59624f'); gr.addColorStop(0.55, '#6a7361'); gr.addColorStop(0.85, '#5b6352'); gr.addColorStop(1, '#4a5143');
    poly([P3(xa, -1500, -D), P3(xb, -1500, -D), P3(xb, H, -D), P3(xa, H, -D)]); g.fillStyle = gr; g.fill();
    if (PEEL) { g.save(); g.clip(); g.fillStyle = g.createPattern(PEEL, 'repeat'); g.fillRect(0, 0, cw, ch); g.restore(); }
    for (const px of POOLX) {                                   // ceiling-light pools on the wall
      const [x, y, s] = P3(px, 10, -D);
      if (x < -600 || x > cw + 600) continue;
      g.save(); g.translate(x, y); g.scale(1, 1.3);
      const pg = g.createRadialGradient(0, 0, 0, 0, 0, 380 * Z * s);
      pg.addColorStop(0, 'rgba(255,248,226,.16)'); pg.addColorStop(1, 'rgba(255,248,226,0)');
      g.fillStyle = pg; g.fillRect(-400 * Z * s, -400 * Z * s, 800 * Z * s, 800 * Z * s); g.restore();
    }
    poly([P3(xa, H - 36, -D), P3(xb, H - 36, -D), P3(xb, H, -D), P3(xa, H, -D)]);   // skirting
    g.fillStyle = '#2f2924'; g.fill();
    poly([P3(xa, H - 36, -D), P3(xb, H - 36, -D), P3(xb, H - 33, -D), P3(xa, H - 33, -D)]);
    g.fillStyle = '#4a423a'; g.fill();

    // floor (y = H) from the wall toward the camera
    const zn = 700;
    const fl = [P3(xa, H, -D), P3(xb, H, -D), P3(xb, H, zn), P3(xa, H, zn)];
    gr = g.createLinearGradient(0, fl[0][1], 0, Math.max(fl[2][1], fl[0][1] + 1));
    gr.addColorStop(0, '#26221d'); gr.addColorStop(0.3, '#39322a'); gr.addColorStop(1, '#2e2822');
    poly(fl); g.fillStyle = gr; g.fill();
    if (PEEL) { g.save(); g.clip(); g.globalAlpha = 0.8; g.fillStyle = g.createPattern(PEEL, 'repeat'); g.fillRect(0, 0, cw, ch); g.restore(); }
    g.strokeStyle = 'rgba(0,0,0,.32)'; g.lineWidth = 1.2;
    for (let x = Math.floor(xa / 300) * 300; x < xb; x += 300) {          // tile joints
      const p1 = P3(x, H, -D), p2 = P3(x, H, zn);
      if (Math.max(p1[0], p2[0]) < -50 || Math.min(p1[0], p2[0]) > cw + 50) continue;
      g.beginPath(); g.moveTo(p1[0], p1[1]); g.lineTo(p2[0], p2[1]); g.stroke();
    }
    for (let z = -D; z <= zn; z += 300) {
      const p1 = P3(xa, H, z), p2 = P3(xb, H, z);
      g.beginPath(); g.moveTo(p1[0], p1[1]); g.lineTo(p2[0], p2[1]); g.stroke();
    }
    for (const px of POOLX) {                                   // tube reflections in the lino
      const [x, y, s] = P3(px, H, 330);
      if (x < -400 || x > cw + 400) continue;
      g.save(); g.translate(x, y); g.scale(1, 0.2);
      const rg = g.createRadialGradient(0, 0, 0, 0, 0, 240 * Z * s);
      rg.addColorStop(0, 'rgba(255,248,226,.10)'); rg.addColorStop(1, 'rgba(255,248,226,0)');
      g.fillStyle = rg; g.fillRect(-260 * Z * s, -260 * Z * s, 520 * Z * s, 520 * Z * s); g.restore();
    }
    // contact shadow along the foot of the cabinet row
    for (let i = 0; i < 6; i++) {
      const z0 = i * 9, z1 = (i + 1) * 9;
      poly([P3(ROOM.cabL + 6, H, z0), P3(ROOM.cabR - 6, H, z0), P3(ROOM.cabR - 6, H, z1), P3(ROOM.cabL + 6, H, z1)]);
      g.fillStyle = `rgba(0,0,0,${(0.55 * (1 - i / 6)).toFixed(3)})`; g.fill();
    }

    // exposed end panels of the row (the one facing the camera is visible)
    const endPanel = (x, sideSign) => {
      const f0 = P3(x, ROOM.cabTop, 0), b0 = P3(x, ROOM.cabTop, -D), b1 = P3(x, H, -D), f1 = P3(x, H, 0);
      if ((b0[0] - f0[0]) * sideSign <= 0.5) return;           // facing away from the camera
      // steel side sheet
      const sg = g.createLinearGradient(f0[0], 0, b0[0], 0);
      sg.addColorStop(0, '#a29d8a'); sg.addColorStop(1, '#7f7a69');
      poly([f0, b0, b1, f1]); g.fillStyle = sg; g.fill();
      if (PEEL) { g.save(); g.clip(); g.fillStyle = g.createPattern(PEEL, 'repeat'); g.fillRect(0, 0, cw, ch); g.restore(); }
      const band = (y0, y1, col) => { poly([P3(x, y0, 0), P3(x, y0, -D), P3(x, y1, -D), P3(x, y1, 0)]); g.fillStyle = col; g.fill(); };
      band(ROOM.cabTop, ROOM.cabTop + 30, 'rgba(255,255,255,.10)');              // roof edge
      band(H - 64, H, '#181817');                                                 // plinth
      band(H - 64, H - 62, '#0b0b0b');
      for (const zz of [-D * 0.5]) {                                              // panel seam
        const s0 = P3(x, ROOM.cabTop + 30, zz), s1 = P3(x, H - 64, zz);
        g.strokeStyle = 'rgba(0,0,0,.25)'; g.lineWidth = 1; g.beginPath(); g.moveTo(s0[0], s0[1]); g.lineTo(s1[0], s1[1]); g.stroke();
      }
      // shade toward the back, lit edge at the front
      const shg = g.createLinearGradient(f0[0], 0, b0[0], 0);
      shg.addColorStop(0, 'rgba(0,0,0,0)'); shg.addColorStop(1, 'rgba(0,0,0,.35)');
      poly([f0, b0, b1, f1]); g.fillStyle = shg; g.fill();
      g.strokeStyle = 'rgba(255,255,255,.35)'; g.lineWidth = 1.2; g.beginPath(); g.moveTo(f0[0], f0[1]); g.lineTo(f1[0], f1[1]); g.stroke();
    };
    endPanel(ROOM.cabL, -1);
    endPanel(ROOM.cabR, 1);
  }

  /* ---------- depth for the hardware on the doors ----------
     Each part gets a depth and a side colour; CSS draws its sides toward the
     camera from the part's position and the live vanishing point. */
  const DEPTHS = [
    ['.mwrap', 18, '#3a3a36'], ['.clockbox', 22, '#3e3e3a'], ['.ctr', 8, '#2c2c2a'], ['.lamp', 13, '#8c8b85'],
    ['.pb', 18, '#8f8d85'], ['.rot', 30, '#3a3a37'], ['.estop', 6, '#b48b0a'], ['.estop .mush', 42, '#8e1407'],
    ['.dsw', 22, '#383835'], ['.relay', 26, '#3c3c38'], ['.lockout', 10, '#3a3a35'], ['.lockout .lh', 22, '#6d6c66'],
    ['.rec', 20, '#3c3c38'], ['.printer', 30, '#9c937c'], ['.ann', 16, '#2e2e2b'], ['.door .handle', 30, '#3a3a38'],
    ['.blank', 4, '#8f8a78'], ['.plate-metal', 3, '#7f7f78'], ['.clip', 6, '#5a3c1d'], ['.np .name', 4, '#34342f'], ['.np .code', 4, '#34342f'],
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
    initRoom(lineup);
    depths(lineup);
  }
  peel(); grain();
  return { apply, rng, lightAt, relPos, drawRoom, projector, CAM_P };
})();
