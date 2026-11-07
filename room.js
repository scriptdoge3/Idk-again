'use strict';
/* =====================================================================
   ROOM · the control room in WebGL (three.js)
   Builds the three cabinets from PANELS layouts: atlas-mapped nameplates
   and dials, 3D meters with damped needles, lamps with incandescent lag,
   knobs, pistol-grip switches, lockouts, the annunciator, displays, the
   PLC behind its window. Then the room itself and the camera.
   ===================================================================== */
window.ROOM = (() => {
  let THREE, renderer, scene, camera, raycaster, ndc, canvasEl;
  const P = window.PLANT, S = P.S, sw = P.sw, PN = window.PANELS;
  const CAB = { w: 1.2, d: 0.62, h: 2.1, doorW: 1.14, doorH: 1.90, doorTop: 2.05 };
  const cabX = [-1.8, -0.6, 0.6];
  const EYE = 1.62;
  const PX = 3;                                    // atlas px per mm
  const parts = [], hits = [], dyn = [];
  const batch = new Map();
  let MAT = {}, glowTex = null, active = false, frameNo = 0;
  const ctl = { x: 0.35, z: 2.6, yaw: -0.06, pitch: -0.13, keys: {}, tx: null, tz: null, tyaw: null, tpitch: null };
  const ROOM = { X0: -3.4, X1: 3.4, ZB: -CAB.d, ZF: 4.6, HC: 3.0 };
  let hover = null, held = null, tipCb = null, soundCb = null;

  const wx = (ci, mm) => cabX[ci] + 0.03 + mm / 1000;
  const wy = mm => CAB.doorTop - mm / 1000;

  /* ------------------------------------------------------- utilities */
  function texFrom(canvas, srgb = true) {
    const t = new THREE.CanvasTexture(canvas);
    if (srgb) t.encoding = THREE.sRGBEncoding;
    t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    return t;
  }
  function stat(geom, mat) { if (!batch.has(mat)) batch.set(mat, []); batch.get(mat).push(geom); }
  function merge(list) {
    let n = 0;
    const gs = list.map(g => { const x = g.index ? g.toNonIndexed() : g; if (!x.attributes.normal) x.computeVertexNormals(); n += x.attributes.position.count; return x; });
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), uv = new Float32Array(n * 2);
    let o = 0;
    for (const g of gs) {
      const c = g.attributes.position.count;
      pos.set(g.attributes.position.array, o * 3); nor.set(g.attributes.normal.array, o * 3);
      if (g.attributes.uv) uv.set(g.attributes.uv.array, o * 2);
      o += c;
    }
    const out = new THREE.BufferGeometry();
    out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    out.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    out.computeBoundingSphere();
    return out;
  }
  function flushBatches() {
    for (const [mat, list] of batch) {
      const m = new THREE.Mesh(merge(list), mat);
      m.castShadow = !!mat.userData.cast; m.receiveShadow = true;
      scene.add(m);
    }
    batch.clear();
  }
  const cylZ = (rt, rb, h, seg = 28) => { const g = new THREE.CylinderGeometry(rt, rb, h, seg); g.rotateX(Math.PI / 2); return g; };
  const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  function at(g, x, y, z) { g.translate(x, y, z); return g; }
  function frame(ci, cx, cy, w, h, t, depth, mat) {        // four bezel strips around a window (mm in, metres out)
    const X = wx(ci, cx), Y = wy(cy), W = w / 1000, H = h / 1000, T = t / 1000, D = depth;
    stat(at(box(W, T, D), X, Y + H / 2 - T / 2, D / 2), mat);
    stat(at(box(W, T, D), X, Y - H / 2 + T / 2, D / 2), mat);
    stat(at(box(T, H - 2 * T, D), X - W / 2 + T / 2, Y, D / 2), mat);
    stat(at(box(T, H - 2 * T, D), X + W / 2 - T / 2, Y, D / 2), mat);
  }
  function hitBox(ci, it, cx, cy, w, h, d, extra = {}) {
    const m = new THREE.Mesh(box(w / 1000, h / 1000, d), MAT.hit);
    m.position.set(wx(ci, cx), wy(cy), d / 2 + 0.002);
    m.userData = { it, ci, cx, cy, ...extra };
    scene.add(m); hits.push(m);
    return m;
  }

  /* ---------------------------------------------------------- atlas */
  const atlasMats = [];
  function atlasMat(ci, page) {
    const key = ci * 10 + page;
    if (!atlasMats[key]) {
      const t = texFrom(ATL[ci].pages[page].c);
      t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter;
      atlasMats[key] = new THREE.MeshStandardMaterial({ map: t, roughness: 0.42, metalness: 0.0, envMapIntensity: 0.5 });
    }
    return atlasMats[key];
  }
  const ATL = [];
  function atlasPlane(ci, r, wM, hM) {
    const g = new THREE.PlaneGeometry(wM, hM), uv = g.attributes.uv, sz = ATL[ci].size;
    for (let i = 0; i < uv.count; i++) {
      const u = uv.getX(i), v = uv.getY(i);
      uv.setXY(i, (r.x + u * r.w) / sz, 1 - (r.y + (1 - v) * r.h) / sz);
    }
    return g;
  }
  function plate(ci, cxmm, cymm, wmm, hmm, text, opt = {}) {
    const r = ATL[ci].alloc(wmm * PX, hmm * PX);
    PN.drawPlate(r.g, r.x, r.y, r.w, r.h, text, { ...opt, size: opt.size ? opt.size * PX : undefined });
    stat(at(atlasPlane(ci, r, wmm / 1000, hmm / 1000), wx(ci, cxmm), wy(cymm), opt.z ?? 0.0016), atlasMat(ci, r.page));
    if (!opt.noEdge) stat(at(box(wmm / 1000 + 0.001, hmm / 1000 + 0.001, 0.0014), wx(ci, cxmm), wy(cymm), 0.0007), MAT.plateEdge);
  }
  function atlasArt(ci, cxmm, cymm, wmm, hmm, draw, z, rot = 0) {
    const r = ATL[ci].alloc(wmm * PX, hmm * PX);
    draw(r.g, r.x, r.y, r.w, r.h);
    const g = atlasPlane(ci, r, wmm / 1000, hmm / 1000);
    if (rot) g.rotateZ(rot);
    stat(at(g, wx(ci, cxmm), wy(cymm), z), atlasMat(ci, r.page));
  }

  /* -------------------------------------------------------- materials */
  function materials() {
    const std = (o) => new THREE.MeshStandardMaterial(o);
    MAT = {
      steel: std({ color: 0x9da29f, roughness: 0.55, metalness: 0.25 }),
      steelDark: std({ color: 0x4b4f4e, roughness: 0.7, metalness: 0.3 }),
      plinth: std({ color: 0x2a2c2b, roughness: 0.8, metalness: 0.2 }),
      black: std({ color: 0x151515, roughness: 0.38, metalness: 0.05 }),
      blackMatte: std({ color: 0x1b1b1b, roughness: 0.7, metalness: 0.05 }),
      chrome: std({ color: 0xd8dadc, roughness: 0.18, metalness: 1.0 }),
      bakelite: std({ color: 0x121212, roughness: 0.30, metalness: 0.0 }),
      needle: std({ color: 0x0c0c0c, roughness: 0.5 }),
      redNeedle: std({ color: 0xc8261a, roughness: 0.45 }),
      glass: new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.04, metalness: 0, transparent: true, opacity: 0.12, envMapIntensity: 1.6, depthWrite: false }),
      plateEdge: std({ color: 0x0e0e0e, roughness: 0.5 }),
      yellow: std({ color: 0xe8b51a, roughness: 0.45 }),
      red: std({ color: 0xb8140f, roughness: 0.32 }),
      gray: std({ color: 0x6d7173, roughness: 0.5, metalness: 0.2 }),
      brass: std({ color: 0xc9a24a, roughness: 0.3, metalness: 1.0 }),
      hit: new THREE.MeshBasicMaterial({ visible: false }),
    };
    MAT.steel.userData.cast = true; MAT.black.userData.cast = true; MAT.bakelite.userData.cast = true;
    const c = PN.cv(64, 64), g = c.getContext('2d'); const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.25, 'rgba(255,255,255,0.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64); glowTex = texFrom(c);
  }
  const LAMP = { red: [0x4a0d08, 0xff1a06], green: [0x0a3216, 0x19e84c], amber: [0x4f3004, 0xff9208], white: [0x5f5d56, 0xfff0cc], blue: [0x14245a, 0x3f7bff] };
  const CAP = { red: 0xb8140f, green: 0x16793a, black: 0x161616, amber: 0xd2860e, yellow: 0xe0b01a };

  /* =========================================================== CABINETS */
  function buildCabinet(ci) {
    const cab = PN.CABS[ci];
    ATL[ci] = PN.Atlas(2048);
    const X0 = cabX[ci], XC = X0 + CAB.w / 2;
    // door texture
    const door = PN.drawDoor(cab, 720, 17 + ci * 31);
    const dt = texFrom(door);
    const doorM = new THREE.MeshStandardMaterial({ map: dt, roughness: 0.55, metalness: 0.12, envMapIntensity: 0.45 });
    const hasWin = cab.items.find(i => i.t === 'plc');
    // cabinet body: front face left open where a window is cut in the door
    const frontM = hasWin ? new THREE.MeshBasicMaterial({ visible: false }) : MAT.steelDark;
    const body = new THREE.Mesh(box(CAB.w, CAB.h - 0.1, CAB.d), [MAT.steel, MAT.steel, MAT.steel, MAT.steelDark, frontM, MAT.steelDark]);
    body.position.set(XC, 0.1 + (CAB.h - 0.1) / 2, -CAB.d / 2 - 0.003); body.castShadow = true; body.receiveShadow = true; scene.add(body);
    const pl = new THREE.Mesh(box(CAB.w - 0.02, 0.1, CAB.d - 0.03), MAT.plinth); pl.position.set(XC, 0.05, -CAB.d / 2 - 0.015); pl.receiveShadow = true; scene.add(pl);
    // door frame margin strips (cabinet face around the door)
    stat(at(box(CAB.w, 0.05, 0.004), XC, CAB.doorTop + 0.025, -0.001), MAT.steel);
    stat(at(box(CAB.w, 0.05, 0.004), XC, 0.125, -0.001), MAT.steel);
    if (ci === 0) stat(at(box(0.004, CAB.h - 0.1, CAB.d), X0 + 0.002, 0.1 + (CAB.h - 0.1) / 2, -CAB.d / 2), MAT.steel);
    // the door itself
    let dg;
    const DW = CAB.doorW, DH = CAB.doorH, DCX = X0 + CAB.w / 2, DCY = CAB.doorTop - DH / 2;
    if (hasWin) {
      const sh = new THREE.Shape();
      sh.moveTo(-DW / 2, -DH / 2); sh.lineTo(DW / 2, -DH / 2); sh.lineTo(DW / 2, DH / 2); sh.lineTo(-DW / 2, DH / 2); sh.lineTo(-DW / 2, -DH / 2);
      const hx = (hasWin.x - DOORC.x) / 1000, hy = -(hasWin.y - DOORC.y) / 1000, hw = (hasWin.w - 30) / 2000, hh = (hasWin.h - 30) / 2000;
      const hole = new THREE.Path(); hole.moveTo(hx - hw, hy - hh); hole.lineTo(hx - hw, hy + hh); hole.lineTo(hx + hw, hy + hh); hole.lineTo(hx + hw, hy - hh); hole.lineTo(hx - hw, hy - hh);
      sh.holes.push(hole);
      dg = new THREE.ShapeGeometry(sh);
      const uv = dg.attributes.uv, pos = dg.attributes.position;
      for (let i = 0; i < uv.count; i++) uv.setXY(i, (pos.getX(i) + DW / 2) / DW, (pos.getY(i) + DH / 2) / DH);
    } else dg = new THREE.PlaneGeometry(DW, DH);
    const dm = new THREE.Mesh(dg, doorM); dm.position.set(DCX, DCY, 0); dm.receiveShadow = true; scene.add(dm);
    // door edge thickness + hinges + handle
    stat(at(box(DW, 0.004, 0.022), DCX, CAB.doorTop - 0.002, -0.011), MAT.steelDark);
    stat(at(box(DW, 0.004, 0.022), DCX, CAB.doorTop - DH + 0.002, -0.011), MAT.steelDark);
    for (const hy of [0.45, 1.75]) stat(at(cylZ(0.008, 0.008, 0.012, 12).rotateX(Math.PI / 2), X0 + 0.028, hy, 0.004), MAT.chrome);
    const hX = X0 + CAB.w - 0.075, hY = 1.08;
    stat(at(box(0.032, 0.17, 0.008), hX, hY, 0.004), MAT.chrome);
    stat(at(box(0.024, 0.13, 0.026), hX, hY - 0.005, 0.018), MAT.black);
    stat(at(cylZ(0.006, 0.006, 0.004, 14), hX, hY + 0.065, 0.010), MAT.brass);
    // roof, lifting eyes
    stat(at(box(CAB.w + 0.012, 0.014, CAB.d + 0.012), XC, CAB.h + 0.007, -CAB.d / 2), MAT.steel);
    for (const fx of [0.08, CAB.w - 0.08]) stat(at(new THREE.TorusGeometry(0.024, 0.0065, 8, 16, Math.PI), X0 + fx, CAB.h + 0.012, -0.10), MAT.steelDark);
    // title and cabinet number
    plate(ci, 520, 38, 760, 34, cab.title, { style: 'wb', weight: 700, size: 17 });
    plate(ci, 1040, 38, 110, 34, cab.no, { style: 'bw', weight: 700, size: 17 });
    if (hasWin) buildInterior(ci, hasWin);
    for (const it of cab.items) buildItem(ci, it);
  }
  const DOORC = { x: 570, y: 950 };

  function buildInterior(ci, win) {
    // dark cabinet interior seen through the PLC window, back panel with the rack
    const X = wx(ci, win.x), Y = wy(win.y);
    const inner = new THREE.Mesh(box(CAB.w - 0.04, CAB.h - 0.2, CAB.d - 0.03), new THREE.MeshStandardMaterial({ color: 0x3d413f, roughness: 0.85, side: THREE.BackSide }));
    inner.position.set(cabX[ci] + CAB.w / 2, 0.1 + (CAB.h - 0.2) / 2 + 0.03, -CAB.d / 2); scene.add(inner);
    const c = PN.cv(1024, 512), t = texFrom(c);
    const m = new THREE.MeshStandardMaterial({ map: t, roughness: 0.7, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0.22, envMapIntensity: 0.1 });
    const rack = new THREE.Mesh(new THREE.PlaneGeometry(win.w / 1000 * 1.05, win.h / 1000 * 1.0), m);
    rack.position.set(X, Y, -0.16); scene.add(rack);
    // DIN rail/terminal strips around, visible at angles
    const back = new THREE.Mesh(new THREE.PlaneGeometry(CAB.w - 0.06, 1.6), new THREE.MeshStandardMaterial({ color: 0x9c9a92, roughness: 0.85 }));
    back.position.set(cabX[ci] + CAB.w / 2, 1.1, -0.165); scene.add(back);
    for (let k = 0; k < 2; k++) { const d = new THREE.Mesh(box(CAB.w - 0.1, 0.06, 0.05), MAT.gray); d.position.set(cabX[ci] + CAB.w / 2, Y + (k ? 0.19 : -0.19), -0.14); scene.add(d); }
    // interior light so the rack reads through the glass
    const pl = new THREE.PointLight(0xfff4e0, 0.16, 0.8, 2); pl.position.set(X, Y + 0.22, -0.06); scene.add(pl);
    let acc = 0;
    dyn.push(dt => { acc += dt; if (acc < 0.12) return; acc = 0; PN.drawPLC(c.getContext('2d'), c.width, c.height); t.needsUpdate = true; });
    PN.drawPLC(c.getContext('2d'), c.width, c.height);
    // window gasket + glass
    frame(ci, win.x, win.y, win.w, win.h, 18, 0.012, MAT.blackMatte);
    const gl = new THREE.Mesh(new THREE.PlaneGeometry((win.w - 20) / 1000, (win.h - 20) / 1000), MAT.glass); gl.position.set(X, Y, 0.006); scene.add(gl);
    plate(ci, win.x, win.y - win.h / 2 - 18, 200, 18, 'PLC  ·  DO NOT FORCE I/O', { size: 9 });
  }

  /* ------------------------------------------------------- items */
  function buildItem(ci, it) {
    const T = it.t;
    if (T === 'section') {
      const w = Math.min(it.w - 20, 22 + it.label.length * 9.6);
      plate(ci, it.x - it.w / 2 + 10 + w / 2, it.y, w, 20, it.label, { size: 11, weight: 700 });
    } else if (T === 'plate') plate(ci, it.x, it.y, it.w, it.h, it.text, { size: it.size });
    else if (T === 'meter') buildMeter(ci, it);
    else if (T === 'edge') buildEdge(ci, it);
    else if (T === 'lamp') buildLamp(ci, it);
    else if (T === 'pb') buildPB(ci, it);
    else if (T === 'sel' || T === 'rl') buildSel(ci, it);
    else if (T === 'cs') buildCS(ci, it);
    else if (T === 'estop') buildEstop(ci, it);
    else if (T === 'lockout') buildLockout(ci, it);
    else if (T === 'ann') buildAnn(ci, it);
    else if (T === 'disp') buildDisp(ci, it);
    else if (T === 'leds') buildLeds(ci, it);
    else if (T === 'counter') buildCounter(ci, it);
    else if (T === 'synchro') buildSynchro(ci, it);
    else if (T === 'relay') buildRelay(ci, it);
    else if (T === 'oit') buildOIT(ci, it);
    else if (T === 'tape') atlasArt(ci, it.x, it.y, it.w, it.h, (g, x, y, w, h) => PN.drawTape(g, x, y, w, h, it.text, it.x + it.y), 0.0009, it.rot || 0);
    else if (T === 'warn') atlasArt(ci, it.x, it.y, it.w, it.h, (g, x, y, w, h) => PN.drawWarn(g, x, y, w, h), 0.0008);
  }

  // a needle that behaves like a moving-coil movement: second order, slightly underdamped
  function needle(group, target, k = 55, z = 0.72) {
    let a = target(), v = 0;
    parts.push(dt => {
      const t = target(); const c = 2 * z * Math.sqrt(k);
      const steps = Math.ceil(dt / 0.008), h = dt / steps;
      for (let i = 0; i < steps; i++) { v += (k * (t - a) - c * v) * h; a += v * h; }
      group.rotation.z = -a;
    });
  }
  function needleMesh(len, red, w = 0.0016) {
    const grp = new THREE.Group();
    const m = red ? MAT.redNeedle : MAT.needle;
    const n = new THREE.Mesh(new THREE.BufferGeometry(), m);
    // tapered blade
    const shp = new THREE.Shape(); shp.moveTo(-w, -len * 0.18); shp.lineTo(w, -len * 0.18); shp.lineTo(w * 0.35, len); shp.lineTo(-w * 0.35, len); shp.closePath();
    n.geometry = new THREE.ExtrudeGeometry(shp, { depth: 0.0006, bevelEnabled: false });
    n.castShadow = true;
    grp.add(n);
    const hub = new THREE.Mesh(cylZ(0.0035, 0.0035, 0.0015, 16), m); hub.position.z = 0.0008; grp.add(hub);
    const cw = new THREE.Mesh(box(w * 4, len * 0.10, 0.0012), m); cw.position.y = -len * 0.16; grp.add(cw);
    return grp;
  }
  function buildMeter(ci, it) {
    const s = it.s, X = wx(ci, it.x), Y = wy(it.y);
    // case + bezel
    frame(ci, it.x, it.y, s, s, 8, 0.020, MAT.black);
    stat(at(box(s / 1000 - 0.004, s / 1000 - 0.004, 0.004), X, Y, 0.002), MAT.black);
    // dial in the atlas
    const r = ATL[ci].alloc((s - 14) * PX, (s - 14) * PX);
    const d = PN.drawDial(r.g, r.x, r.y, r.w, it);
    const dw = (s - 14) / 1000;
    stat(at(atlasPlane(ci, r, dw, dw), X, Y, 0.0045), atlasMat(ci, r.page));
    const pvx = X + (d.cx - 0.5) * dw, pvy = Y - (d.cy - 0.5) * dw;
    const nd = needleMesh(d.R * dw * 0.98, false); nd.position.set(pvx, pvy, 0.0065); scene.add(nd);
    needle(nd, () => PN.meterAngle(it, it.get()));
    if (it.pointer2) { const n2 = needleMesh(d.R * dw * 0.9, true, 0.0013); n2.position.set(pvx, pvy, 0.0058); scene.add(n2); needle(n2, () => PN.meterAngle(it, it.pointer2()), 30, 0.9); }
    // glass
    stat(at(new THREE.PlaneGeometry(dw + 0.002, dw + 0.002), X, Y, 0.0175), MAT.glass);
    // nameplate below
    plate(ci, it.x, it.y + s / 2 + 15, s, 22, it.label, { size: it.label.includes('\n') ? 8 : 9.5 });
    hitBox(ci, it, it.x, it.y, s, s, 0.02);
  }
  function buildEdge(ci, it) {
    const w = it.w, h = it.h, X = wx(ci, it.x), Y = wy(it.y);
    frame(ci, it.x, it.y, w + 12, h + 12, 7, 0.022, MAT.black);
    stat(at(box((w + 10) / 1000, (h + 10) / 1000, 0.004), X, Y, 0.002), MAT.black);
    const r = ATL[ci].alloc(w * PX, h * PX);
    PN.drawEdge(r.g, r.x, r.y, r.w, r.h, it);
    stat(at(atlasPlane(ci, r, w / 1000, h / 1000), X, Y, 0.0045), atlasMat(ci, r.page));
    const top = Y + h / 2000 - h * 0.06 / 1000, bot = Y - h / 2000 + h * 0.06 / 1000;
    const mk = (red, get, k) => {
      const ptr = new THREE.Mesh(box(w * 0.55 / 1000, 0.0022, 0.0015), red ? MAT.redNeedle : MAT.needle);
      ptr.position.set(X - w * 0.18 / 1000, Y, red ? 0.0068 : 0.0062); scene.add(ptr);
      let a = PN.edgeFrac(it, get()), v = 0;
      parts.push(dt => { const t = PN.edgeFrac(it, get()); const c = 2 * 0.75 * Math.sqrt(k); v += (k * (t - a) - c * v) * dt; a += v * dt; ptr.position.y = bot + (top - bot) * a; });
    };
    mk(true, it.get, 40);
    if (it.pointer2) mk(false, it.pointer2, 25);
    stat(at(new THREE.PlaneGeometry((w + 2) / 1000, (h + 2) / 1000), X, Y, 0.0195), MAT.glass);
    plate(ci, it.x, it.y + h / 2 + 22, Math.max(70, w + 30), 24, it.label, { size: 8 });
    hitBox(ci, it, it.x, it.y, w + 12, h + 12, 0.022);
  }
  function buildLamp(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y);
    stat(at(cylZ(0.0165, 0.0175, 0.010, 28), X, Y, 0.005), MAT.black);
    stat(at(cylZ(0.0135, 0.0135, 0.003, 28), X, Y, 0.0115), MAT.chrome);
    const [base, glow] = LAMP[it.color];
    const lm = new THREE.MeshStandardMaterial({ color: base, emissive: glow, emissiveIntensity: 0, roughness: 0.28, metalness: 0, envMapIntensity: 0.35 });
    const lens = new THREE.Mesh(new THREE.SphereGeometry(0.0115, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), lm);
    lens.rotation.x = Math.PI / 2; lens.scale.set(1, 0.55, 1); lens.position.set(X, Y, 0.012); scene.add(lens);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: glow, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0 }));
    halo.position.set(X, Y, 0.022); halo.scale.set(0.042, 0.042, 1); scene.add(halo);
    let b = 0;
    parts.push(dt => {
      let v = it.on();
      if (v === 'flash') v = PN.blink(1.4) ? 1 : 0;
      v = v === true ? 1 : v ? +v : 0;
      if (S.dcV < 60) v = 0;
      b += (v - b) * (1 - Math.exp(-dt / (v > b ? 0.06 : 0.14)));
      lm.emissiveIntensity = b * (it.color === 'white' ? 0.9 : 1.5);
      halo.material.opacity = b * (it.color === 'white' ? 0.16 : it.dim ? 0.2 : 0.32);
    });
    plate(ci, it.x, it.y + 32, 62, it.label.includes('\n') ? 22 : 15, it.label, { size: 7.5 });
    hitBox(ci, it, it.x, it.y, 36, 36, 0.02);
  }
  function buildPB(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y), r = it.small ? 0.011 : it.big ? 0.017 : 0.014;
    stat(at(cylZ(r + 0.005, r + 0.006, 0.010, 28), X, Y, 0.005), MAT.chrome);
    const capM = new THREE.MeshStandardMaterial({ color: CAP[it.color] || CAP.black, roughness: 0.35 });
    const cap = new THREE.Mesh(cylZ(r, r, 0.012, 28), capM); cap.position.set(X, Y, 0.012); cap.castShadow = true; scene.add(cap);
    let p = 0;
    parts.push(dt => { const t = held && held.userData.it === it ? 1 : 0; p += (t - p) * (1 - Math.exp(-dt / 0.03)); cap.position.z = 0.013 - p * 0.005; });
    if (it.label && it.label.length > 2) plate(ci, it.x, it.y - (it.big ? 37 : it.small ? 28 : 32), 66, 16, it.label, { size: 8 });
    else if (it.label) plate(ci, it.x, it.y - 26, 24, 14, it.label, { size: 8 });
    hitBox(ci, it, it.x, it.y, r * 2400, r * 2400, 0.024, { action: 'pb' });
  }
  function knobMesh(kind) {
    const g = new THREE.Group();
    if (kind === 'cs') {          // pistol grip
      const shp = new THREE.Shape();
      shp.moveTo(-0.010, -0.016); shp.lineTo(0.010, -0.016); shp.lineTo(0.007, 0.040); shp.quadraticCurveTo(0, 0.048, -0.007, 0.040); shp.closePath();
      const gg = new THREE.ExtrudeGeometry(shp, { depth: 0.018, bevelEnabled: true, bevelThickness: 0.003, bevelSize: 0.003, bevelSegments: 3 });
      const m = new THREE.Mesh(gg, MAT.bakelite); m.castShadow = true; g.add(m);
      const hub = new THREE.Mesh(cylZ(0.016, 0.018, 0.012, 28), MAT.bakelite); hub.position.z = 0.006; g.add(hub);
    } else if (kind === 'key') {
      const cyl = new THREE.Mesh(cylZ(0.010, 0.011, 0.012, 24), MAT.chrome); cyl.position.z = 0.006; g.add(cyl);
      const key = new THREE.Mesh(box(0.004, 0.026, 0.003), MAT.brass); key.position.set(0, 0.006, 0.016); g.add(key);
      const bow = new THREE.Mesh(cylZ(0.008, 0.008, 0.003, 18), MAT.brass); bow.position.set(0, 0.022, 0.016); g.add(bow);
    } else {                      // oval lever handle
      const base = new THREE.Mesh(cylZ(0.013, 0.015, 0.010, 28), MAT.bakelite); base.position.z = 0.005; g.add(base);
      const lev = new THREE.Mesh(new THREE.CapsuleGeometry(0.0062, 0.030, 6, 14), MAT.bakelite); lev.position.z = 0.016; lev.scale.set(1, 1, 1.25); lev.castShadow = true; g.add(lev);
      const mark = new THREE.Mesh(box(0.0016, 0.012, 0.001), new THREE.MeshStandardMaterial({ color: 0xeeeeee, roughness: 0.6 })); mark.position.set(0, 0.012, 0.0245); g.add(mark);
    }
    return g;
  }
  function buildSel(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y);
    const pos = it.t === 'rl' ? [it.left, it.right] : it.pos;
    const ang = it.t === 'rl' ? [-Math.PI / 4, Math.PI / 4] : PN.selAngles(pos.length);
    const es = it.small ? 58 : 70;
    atlasArt(ci, it.x, it.y, es, es, (g, x, y, w) => PN.drawEscutcheon(g, x, y, w, pos, ang), 0.0012);
    stat(at(cylZ(0.0175, 0.019, 0.004, 28), X, Y, 0.002), MAT.chrome);
    const k = knobMesh(it.key ? 'key' : 'sel'); k.position.set(X, Y, 0.004); scene.add(k);
    let a = 0;
    parts.push(dt => {
      let t;
      if (it.t === 'rl') t = held && held.userData.it === it ? held.userData.side * Math.PI / 4 : 0;
      else t = ang[Math.max(0, it.get())] || 0;
      a += (t - a) * (1 - Math.exp(-dt / 0.045));
      k.rotation.z = -a;
    });
    if (!it.noPlate) plate(ci, it.x, it.y - es / 2 - 14, it.small ? 74 : 92, 17, it.label, { size: 8.5 });
    hitBox(ci, it, it.x, it.y, es, es, 0.03, { action: it.t });
  }
  function buildCS(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y), es = 92;
    atlasArt(ci, it.x, it.y, es, es, (g, x, y, w) => PN.drawEscutcheon(g, x, y, w, [it.left, it.right], [-Math.PI / 4, Math.PI / 4], { cs: true }), 0.0012);
    stat(at(cylZ(0.024, 0.026, 0.005, 32), X, Y, 0.0025), MAT.chrome);
    const k = knobMesh('cs'); k.position.set(X, Y, 0.004); scene.add(k);
    // semaphore target that shows the last operation
    const fm = new THREE.MeshStandardMaterial({ color: 0x1e9a3c, roughness: 0.5 });
    const flag = new THREE.Mesh(new THREE.PlaneGeometry(0.014, 0.010), fm); flag.position.set(X, Y - 0.032, 0.0055); scene.add(flag);
    stat(at(box(0.020, 0.015, 0.003), X, Y - 0.032, 0.003), MAT.black);
    let a = 0;
    parts.push(dt => {
      const t = held && held.userData.it === it ? held.userData.side * Math.PI / 4 : 0;
      a += (t - a) * (1 - Math.exp(-dt / 0.05)); k.rotation.z = -a;
      fm.color.setHex(it.flag() === 'red' ? 0xc8261a : 0x1e9a3c);
    });
    plate(ci, it.x, it.y - es / 2 - 16, 150, 18, it.label, { size: 8.5 });
    hitBox(ci, it, it.x, it.y, es, es, 0.04, { action: 'cs' });
  }
  function buildEstop(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y);
    atlasArt(ci, it.x, it.y, 100, 100, (g, x, y, w) => {
      g.save(); g.translate(x + w / 2, y + w / 2);
      g.fillStyle = '#e8b51a'; g.beginPath(); g.arc(0, 0, w * 0.49, 0, 7); g.fill();
      g.fillStyle = '#141414'; g.font = `800 ${w * 0.085}px ${PN.FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle';
      const t = 'EMERGENCY  STOP  ·  ', R = w * 0.40;
      for (let i = 0; i < t.length; i++) { const a = -Math.PI * 0.95 + i / t.length * Math.PI * 1.9; g.save(); g.rotate(a); g.fillText(t[i], 0, -R); g.restore(); }
      g.restore();
    }, 0.0012);
    stat(at(cylZ(0.022, 0.024, 0.016, 32), X, Y, 0.008), MAT.black);
    const head = new THREE.Group();
    const cap = new THREE.Mesh(new THREE.SphereGeometry(0.031, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2.6), MAT.red); cap.rotation.x = Math.PI / 2; cap.scale.set(1, 0.42, 1); head.add(cap);
    const rim = new THREE.Mesh(cylZ(0.031, 0.031, 0.008, 32), MAT.red); rim.position.z = -0.004; head.add(rim);
    head.position.set(X, Y, 0.030); head.traverse(o => { o.castShadow = true; }); scene.add(head);
    let p = 0;
    parts.push(dt => { p += ((S.estop ? 1 : 0) - p) * (1 - Math.exp(-dt / 0.04)); head.position.z = 0.030 - p * 0.008; head.rotation.z = p * 0.25; });
    hitBox(ci, it, it.x, it.y, 70, 70, 0.045, { action: 'estop' });
  }
  function buildLockout(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y);
    stat(at(box(0.082, 0.120, 0.012), X, Y, 0.006), MAT.blackMatte);
    atlasArt(ci, it.x, it.y + 38, 70, 30, (g, x, y, w, h) => PN.drawPlate(g, x, y, w, h, it.label, { style: 'bw', size: h * 0.36 }), 0.0125);
    stat(at(cylZ(0.016, 0.016, 0.006, 24), X, Y - 0.008, 0.015), MAT.chrome);
    const hd = new THREE.Group();
    const bar = new THREE.Mesh(box(0.016, 0.060, 0.014), MAT.bakelite); bar.position.y = 0.018; bar.castShadow = true; hd.add(bar);
    const hub = new THREE.Mesh(cylZ(0.013, 0.013, 0.012, 22), MAT.bakelite); hd.add(hub);
    hd.position.set(X, Y - 0.008, 0.024); scene.add(hd);
    const flagM = new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0x000000, roughness: 0.5 });
    const flag = new THREE.Mesh(new THREE.PlaneGeometry(0.018, 0.010), flagM); flag.position.set(X + 0.026, Y + 0.030, 0.0125); scene.add(flag);
    let a = 0;
    parts.push(dt => { const t = it.get() ? Math.PI / 4 : 0; a += (t - a) * (1 - Math.exp(-dt / 0.03)); hd.rotation.z = -a; flagM.color.setHex(it.get() ? 0xff7a10 : 0x1b1b1b); });
    plate(ci, it.x, it.y - 76, 92, 17, 'LOCKOUT RELAY', { size: 8 });
    hitBox(ci, it, it.x, it.y, 82, 120, 0.04, { action: 'lockout' });
  }
  function buildAnn(ci, it) {
    const w = it.cols * it.cw, h = it.rows * it.ch, X = wx(ci, it.x), Y = wy(it.y);
    stat(at(box((w + 40) / 1000, (h + 40) / 1000, 0.07), X, Y, 0.035), MAT.blackMatte);
    const c = PN.cv(it.cols * 180, it.rows * 100), t = texFrom(c);
    const m = new THREE.MeshStandardMaterial({ map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0.85, roughness: 0.85, envMapIntensity: 0.15 });
    const face = new THREE.Mesh(new THREE.PlaneGeometry(w / 1000, h / 1000), m); face.position.set(X, Y, 0.0705); scene.add(face);
    // window grid ribs
    for (let i = 0; i <= it.cols; i++) stat(at(box(0.004, h / 1000, 0.006), X - w / 2000 + i * it.cw / 1000, Y, 0.073), MAT.blackMatte);
    for (let j = 0; j <= it.rows; j++) stat(at(box(w / 1000, 0.004, 0.006), X, Y - h / 2000 + j * it.ch / 1000, 0.073), MAT.blackMatte);
    let last = '', acc = 0;
    dyn.push(dt => {
      acc += dt; if (acc < 0.05) return; acc = 0;
      const test = held && held.userData.it && held.userData.it.test;
      const key = (test ? 'T' : '') + P.ANN.map(a => a.st).join(',') + (P.ANN.some(a => a.st === 'alarm' || a.st === 'alarmRTN') ? (performance.now() / 156 | 0) : '') + (P.ANN.some(a => a.st === 'ring') ? (performance.now() / 555 | 0) : '');
      if (key === last) return; last = key;
      PN.drawAnn(c.getContext('2d'), c.width, c.height, it, test); t.needsUpdate = true;
    });
    plate(ci, it.x, it.y - h / 2 - 34, 220, 18, 'ANNUNCIATOR  ·  ISA SEQ R', { size: 9 });
    hitBox(ci, it, it.x, it.y, w, h, 0.075);
    // horn on the cabinet roof
    const hx = cabX[ci] + CAB.w - 0.22, hy = CAB.h + 0.06;
    const hornM = new THREE.MeshStandardMaterial({ color: 0x7a7f7d, roughness: 0.5, metalness: 0.4 });
    const hb = new THREE.Mesh(box(0.10, 0.09, 0.10), hornM); hb.position.set(hx, hy, -0.12); hb.castShadow = true; scene.add(hb);
    const hc = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.02, 0.09, 24, 1, true), hornM); hc.rotation.x = Math.PI / 2; hc.position.set(hx, hy, -0.03); scene.add(hc);
  }
  function buildDisp(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y);
    frame(ci, it.x, it.y, it.w + 14, it.h + 14, 8, 0.014, MAT.black);
    const res = it.kind === 'led7' ? 4 : 4;
    const c = PN.cv(it.w * res, it.h * res), t = texFrom(c);
    const emissive = it.kind !== 'lcdtag';
    const m = emissive ? new THREE.MeshBasicMaterial({ map: t, toneMapped: false }) : new THREE.MeshStandardMaterial({ map: t, roughness: 0.5 });
    if (emissive) m.color.setScalar(it.kind === 'vfd' ? 1.15 : 1.25);
    const face = new THREE.Mesh(new THREE.PlaneGeometry(it.w / 1000, it.h / 1000), m); face.position.set(X, Y, 0.004); scene.add(face);
    stat(at(new THREE.PlaneGeometry(it.w / 1000, it.h / 1000), X, Y, 0.012), MAT.glass);
    let last = null, acc = 1;
    const draw = () => {
      const g = c.getContext('2d');
      if (it.kind === 'led7') { const v = it.text(); if (v === last) return; last = v; PN.draw7(g, c.width, c.height, v, it.digits); }
      else if (it.kind === 'lcdtag') { const v = it.text(); if (v === last) return; last = v; g.fillStyle = '#d9d6cb'; g.fillRect(0, 0, c.width, c.height); g.fillStyle = '#141414'; g.font = `700 ${c.height * 0.6}px ${PN.FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(v, c.width / 2, c.height / 2); }
      else { const lines = (S.dcV < 60 || (it.kind === 'vfd' && false)) ? [] : it.text(); const v = lines.join('|'); if (v === last) return; last = v; PN.drawMatrix(g, c.width, c.height, lines, it.cols, it.rows, it.kind); }
      t.needsUpdate = true;
    };
    dyn.push(dt => { acc += dt; if (acc < 0.25) return; acc = 0; draw(); });
    draw();
    if (it.label) plate(ci, it.x, it.y - it.h / 2 - 20, Math.min(it.w + 10, 240), 16, it.label, { size: 8.5 });
    hitBox(ci, it, it.x, it.y, it.w + 14, it.h + 14, 0.016);
  }
  function buildLeds(ci, it) {
    const n = it.items.length, sp = 50, x0 = it.x - (n - 1) * sp / 2;
    it.items.forEach(([lab, get, col], i) => {
      const x = x0 + i * sp, X = wx(ci, x), Y = wy(it.y);
      stat(at(cylZ(0.004, 0.0045, 0.004, 14), X, Y, 0.002), MAT.black);
      const [base, glow] = LAMP[col === 'amber' ? 'amber' : col];
      const m = new THREE.MeshStandardMaterial({ color: base, emissive: glow, emissiveIntensity: 0, roughness: 0.2 });
      const l = new THREE.Mesh(new THREE.SphereGeometry(0.0028, 12, 8), m); l.position.set(X, Y, 0.0045); scene.add(l);
      parts.push(() => { m.emissiveIntensity = get() ? 3 : 0; });
      plate(ci, x, it.y + 14, 44, 12, lab, { size: 7 });
    });
  }
  function buildCounter(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y), w = it.w, h = 34;
    stat(at(box(w / 1000, h / 1000, 0.012), X, Y, 0.006), MAT.blackMatte);
    const c = PN.cv(w * 4, (h - 12) * 4), t = texFrom(c);
    const m = new THREE.MeshStandardMaterial({ map: t, roughness: 0.4 });
    const face = new THREE.Mesh(new THREE.PlaneGeometry((w - 12) / 1000, (h - 12) / 1000), m); face.position.set(X, Y, 0.0125); scene.add(face);
    let last = '';
    const draw = () => {
      const v = it.get(); const s = it.dec ? (v).toFixed(it.dec).replace('.', '') : String(Math.floor(v));
      const txt = s.padStart(it.digits, '0').slice(-it.digits);
      const frac = it.dec ? 0 : v - Math.floor(v);
      const key = txt + (frac * 10 | 0);
      if (key === last) return; last = key;
      const g = c.getContext('2d'), W = c.width, H = c.height, dw = W / it.digits;
      for (let i = 0; i < it.digits; i++) {
        const last1 = i === it.digits - 1;
        g.fillStyle = (it.dec && last1) ? '#b8140f' : '#161616'; g.fillRect(i * dw, 0, dw - 2, H);
        const gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, 'rgba(0,0,0,0.65)'); gr.addColorStop(0.3, 'rgba(0,0,0,0)'); gr.addColorStop(0.7, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(0,0,0,0.65)');
        g.fillStyle = '#f2efe4'; g.font = `600 ${H * 0.72}px ${PN.FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle';
        const roll = last1 && !it.dec ? frac * H : 0;
        g.fillText(txt[i], i * dw + dw / 2, H / 2 - roll);
        if (roll) g.fillText(String((+txt[i] + 1) % 10), i * dw + dw / 2, H / 2 - roll + H);
        g.fillStyle = gr; g.fillRect(i * dw, 0, dw - 2, H);
      }
      t.needsUpdate = true;
    };
    let acc = 0; dyn.push(dt => { acc += dt; if (acc < 0.2) return; acc = 0; draw(); }); draw();
    plate(ci, it.x, it.y + h / 2 + 10, w, 14, it.label, { size: 8 });
    hitBox(ci, it, it.x, it.y, w, h, 0.014);
  }
  function buildSynchro(ci, it) {
    const s = it.s, X = wx(ci, it.x), Y = wy(it.y);
    frame(ci, it.x, it.y, s, s, 9, 0.022, MAT.black);
    stat(at(box(s / 1000 - 0.004, s / 1000 - 0.004, 0.004), X, Y, 0.002), MAT.black);
    const fw = (s - 16);
    atlasArt(ci, it.x, it.y, fw, fw, (g, x, y, w) => PN.drawSyncFace(g, x, y, w), 0.0045);
    const nd = needleMesh(fw * 0.40 / 1000, true, 0.0024); nd.position.set(X, Y, 0.0065); scene.add(nd);
    let a = 0;
    parts.push(dt => {
      const live = !S.cb && S.Vt > 0.2 && S.vbus > 0.2 && sw.syncMode !== 'OFF';
      if (live) { let t = S.syncAng; let d = t - a; d = Math.atan2(Math.sin(d), Math.cos(d)); a += d * (1 - Math.exp(-dt / 0.08)); }
      else if (S.cb) { a += (0 - Math.atan2(Math.sin(a), Math.cos(a))) * (1 - Math.exp(-dt / 0.2)); }
      nd.rotation.z = -a;
    });
    stat(at(new THREE.PlaneGeometry(fw / 1000, fw / 1000), X, Y, 0.0195), MAT.glass);
    plate(ci, it.x, it.y + s / 2 + 12, 120, 16, 'SYNCHROSCOPE', { size: 8.5 });
    hitBox(ci, it, it.x, it.y, s, s, 0.022);
  }
  function buildRelay(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y), w = it.w, h = it.h;
    stat(at(box(w / 1000, h / 1000, 0.045), X, Y, 0.0225), MAT.blackMatte);
    const c = PN.cv(w * 3.4, h * 3.4), t = texFrom(c);
    const m = new THREE.MeshStandardMaterial({ map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0.25, roughness: 0.45 });
    const face = new THREE.Mesh(new THREE.PlaneGeometry((w - 8) / 1000, (h - 8) / 1000), m); face.position.set(X, Y, 0.0455); scene.add(face);
    let acc = 1;
    dyn.push(dt => { acc += dt; if (acc < 0.3) return; acc = 0; PN.drawGPR(c.getContext('2d'), c.width, c.height, PN.gprText()); t.needsUpdate = true; });
    // target reset button on the relay face
    const bx = it.x + w / 2 - 38, by = it.y + h / 2 - 28;
    const rb = new THREE.Mesh(cylZ(0.009, 0.009, 0.008, 20), new THREE.MeshStandardMaterial({ color: 0x2a5bd8, roughness: 0.4 })); rb.position.set(wx(ci, bx), wy(by), 0.05); scene.add(rb);
    plate(ci, bx - 52, by, 70, 14, 'TARGET RESET', { size: 7.5, z: 0.0465, noEdge: true });
    hitBox(ci, { t: 'pb', label: 'TARGET RESET', press: () => P.cmd('gprReset'), tip: 'Reset the relay trip targets' }, bx, by, 26, 26, 0.055, { action: 'pb' });
    hitBox(ci, it, it.x, it.y - 20, w, h - 50, 0.046);
    plate(ci, it.x, it.y - h / 2 - 14, 200, 16, 'GENERATOR PROTECTION RELAY', { size: 8.5 });
  }
  function buildOIT(ci, it) {
    const X = wx(ci, it.x), Y = wy(it.y), w = it.w, h = it.h;
    stat(at(box(w / 1000, h / 1000, 0.03), X, Y, 0.015), MAT.gray);
    const dw = 270, dh = 92, dy = it.y - h / 2 + 22 + dh / 2;
    const c = PN.cv(dw * 4, dh * 4), t = texFrom(c);
    const face = new THREE.Mesh(new THREE.PlaneGeometry(dw / 1000, dh / 1000), new THREE.MeshBasicMaterial({ map: t, toneMapped: false }));
    face.material.color.setScalar(1.15); face.position.set(X, wy(dy), 0.0305); scene.add(face);
    frame(ci, it.x, dy, dw + 12, dh + 12, 6, 0.034, MAT.blackMatte);
    let last = '', acc = 1;
    dyn.push(dt => { acc += dt; if (acc < 0.25) return; acc = 0; const L4 = S.dcV < 60 ? ['', '', '', ''] : PN.oitText(); const k = L4.join('|'); if (k === last) return; last = k; PN.drawMatrix(c.getContext('2d'), c.width, c.height, L4, 20, 4, 'vfd'); t.needsUpdate = true; });
    plate(ci, it.x, it.y - h / 2 + 10, 150, 12, 'OPERATOR INTERFACE', { size: 7, z: 0.0305, noEdge: true });
    // keypad
    const keys = [['F1', 'STATUS'], ['F2', 'LEVEL'], ['F3', 'EVENTS'], ['F4', 'PERMIT']];
    keys.forEach(([k, l], i) => oitKey(ci, it.x - 105 + i * 70, it.y + 30, k, l, 0x2b3a4f));
    const nav = [['LEFT', '◄', -105], ['UP', '▲', -35], ['DOWN', '▼', 35], ['RIGHT', '►', 105]];
    nav.forEach(([k, l, dx]) => oitKey(ci, it.x + dx, it.y + 85, k, l, 0x3a3d40));
    oitKey(ci, it.x, it.y + 125, 'ENT', 'ENTER', 0x3a3d40, true);
  }
  function oitKey(ci, x, y, k, label, color, wide) {
    const X = wx(ci, x), Y = wy(y), w = wide ? 0.09 : 0.05, h = 0.026;
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.55 });
    const key = new THREE.Mesh(box(w, h, 0.008), m); key.position.set(X, Y, 0.034); scene.add(key);
    plate(ci, x, y, w * 1000 - 10, 15, label, { size: 8, z: 0.0382, noEdge: true });
    const it = { t: 'pb', label, press: () => PN.oitKey(k), tip: `Operator interface key ${label}` };
    let p = 0;
    parts.push(dt => { const tg = held && held.userData.it === it ? 1 : 0; p += (tg - p) * (1 - Math.exp(-dt / 0.03)); key.position.z = 0.034 - p * 0.003; });
    hitBox(ci, it, x, y, w * 1000, h * 1000, 0.045, { action: 'pb' });
  }

  /* ============================================================ THE ROOM */
  function canvasTex(w, h, draw, rep) {
    const c = PN.cv(w, h); draw(c.getContext('2d'), w, h); const t = texFrom(c);
    if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); }
    return t;
  }
  function buildRoom() {
    const { X0, X1, ZB, ZF, HC } = ROOM, W = X1 - X0, D = ZF - ZB;
    const R = PN.rng(7);
    // vinyl composition tile, 12 in squares, two tones laid in a checker
    const floorT = canvasTex(512, 512, (g, w) => {
      const n = 4, s = w / n;
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        g.fillStyle = (i + j) % 2 ? '#9c927c' : '#6c6555'; g.fillRect(i * s, j * s, s, s);
        for (let k = 0; k < 260; k++) { g.fillStyle = `rgba(${R() < 0.5 ? '255,250,240' : '40,32,22'},${(R() * 0.18).toFixed(3)})`; g.fillRect(i * s + R() * s, j * s + R() * s, 1 + R() * 3, 1 + R() * 2); }
      }
      g.strokeStyle = 'rgba(40,34,26,0.5)'; g.lineWidth = 1.2;
      for (let i = 0; i <= n; i++) { g.beginPath(); g.moveTo(i * s, 0); g.lineTo(i * s, w); g.stroke(); g.beginPath(); g.moveTo(0, i * s); g.lineTo(w, i * s); g.stroke(); }
    }, [W / (4 * 0.3048), D / (4 * 0.3048)]);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshStandardMaterial({ map: floorT, roughness: 0.32, metalness: 0, envMapIntensity: 0.55 }));
    floor.rotation.x = -Math.PI / 2; floor.position.set((X0 + X1) / 2, 0, (ZB + ZF) / 2); floor.receiveShadow = true; scene.add(floor);
    // painted concrete block walls, 8 x 16 in running bond
    const wallT = canvasTex(512, 512, (g, w, h) => {
      g.fillStyle = '#aab4a0'; g.fillRect(0, 0, w, h);
      const bw = w / 2, bh = h / 4;
      for (let r = 0; r < 4; r++) for (let c = -1; c < 3; c++) {
        const x = c * bw + (r % 2 ? bw / 2 : 0), y = r * bh;
        g.fillStyle = `rgba(${R() < 0.5 ? '255,255,250' : '60,60,50'},${(R() * 0.05).toFixed(3)})`; g.fillRect(x + 3, y + 3, bw - 6, bh - 6);
        for (let k = 0; k < 220; k++) { g.fillStyle = `rgba(70,70,60,${(R() * 0.10).toFixed(3)})`; g.fillRect(x + R() * bw, y + R() * bh, 1.5, 1.5); }
        g.strokeStyle = 'rgba(80,80,70,0.45)'; g.lineWidth = 3; g.strokeRect(x + 1.5, y + 1.5, bw - 3, bh - 3);
        g.strokeStyle = 'rgba(255,255,250,0.25)'; g.lineWidth = 1; g.strokeRect(x + 4, y + 4, bw - 8, bh - 8);
      }
    }, [W / 0.8128, HC / 0.8128]);
    const wallM = new THREE.MeshStandardMaterial({ map: wallT, roughness: 0.92, envMapIntensity: 0.25 });
    const mkWall = (w, h, x, y, z, ry, rep) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), rep ? wallM.clone() : wallM);
      if (rep) { m.material.map = wallT.clone(); m.material.map.needsUpdate = true; m.material.map.repeat.set(w / 0.8128, h / 0.8128); }
      m.position.set(x, y, z); m.rotation.y = ry; m.receiveShadow = true; scene.add(m); return m;
    };
    mkWall(W, HC, (X0 + X1) / 2, HC / 2, ZB, 0);
    mkWall(D, HC, X0, HC / 2, (ZB + ZF) / 2, Math.PI / 2, true);
    mkWall(D, HC, X1, HC / 2, (ZB + ZF) / 2, -Math.PI / 2, true);
    mkWall(W, HC, (X0 + X1) / 2, HC / 2, ZF, Math.PI);
    // vinyl cove base
    const baseM = new THREE.MeshStandardMaterial({ color: 0x2c2a27, roughness: 0.6 });
    [[W, (X0 + X1) / 2, ZB + 0.004, 0], [W, (X0 + X1) / 2, ZF - 0.004, Math.PI], [D, X0 + 0.004, (ZB + ZF) / 2, Math.PI / 2], [D, X1 - 0.004, (ZB + ZF) / 2, -Math.PI / 2]].forEach(([w, x, z, ry]) => {
      const b = new THREE.Mesh(box(w, 0.10, 0.008), baseM); b.position.set(x, 0.05, z); b.rotation.y = ry; scene.add(b);
    });
    // 2x4 ft acoustic tile ceiling
    const ceilT = canvasTex(256, 512, (g, w, h) => {
      g.fillStyle = '#e4e2da'; g.fillRect(0, 0, w, h);
      for (let k = 0; k < 2600; k++) { g.fillStyle = `rgba(90,85,75,${(R() * 0.25).toFixed(3)})`; g.fillRect(R() * w, R() * h, 1.6, 1.6); }
      g.strokeStyle = '#f5f4ef'; g.lineWidth = 7; g.strokeRect(0, 0, w, h);
      g.strokeStyle = 'rgba(0,0,0,0.12)'; g.lineWidth = 1; g.strokeRect(4, 4, w - 8, h - 8);
    }, [W / 0.6096, D / 1.2192]);
    const ceil = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshStandardMaterial({ map: ceilT, roughness: 0.95 }));
    ceil.rotation.x = Math.PI / 2; ceil.position.set((X0 + X1) / 2, HC, (ZB + ZF) / 2); scene.add(ceil);
    // fluorescent troffers with prismatic lenses
    const lensT = canvasTex(128, 256, (g, w, h) => { g.fillStyle = '#fff'; g.fillRect(0, 0, w, h); g.fillStyle = 'rgba(200,200,190,0.35)'; for (let y = 0; y < h; y += 6) for (let x = (y / 6) % 2 * 3; x < w; x += 6) g.fillRect(x, y, 3, 3); });
    const lensM = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff6e6, emissiveMap: lensT, emissiveIntensity: 1.25, map: lensT, roughness: 0.6 });
    const trimM = new THREE.MeshStandardMaterial({ color: 0xf1f0ea, roughness: 0.5, metalness: 0.3 });
    for (const x of [-2.2, 0, 2.2]) for (const z of [0.95, 3.15]) {
      const tr = new THREE.Mesh(box(0.62, 0.02, 1.23), trimM); tr.position.set(x, HC - 0.01, z); scene.add(tr);
      const l = new THREE.Mesh(new THREE.PlaneGeometry(0.58, 1.19), lensM); l.rotation.x = Math.PI / 2; l.position.set(x, HC - 0.021, z); scene.add(l);
    }
    // lighting
    scene.add(new THREE.HemisphereLight(0xfff1dc, 0x2b2620, 0.26));
    for (const x of [-2.2, 0, 2.2]) { const pl = new THREE.PointLight(0xfff2de, 0.34, 7.5, 1.6); pl.position.set(x, HC - 0.25, 1.2); scene.add(pl); }
    const pl2 = new THREE.PointLight(0xfff2de, 0.26, 7, 1.6); pl2.position.set(0, HC - 0.25, 3.3); scene.add(pl2);
    const key = new THREE.SpotLight(0xfff3df, 1.15, 12, 1.0, 0.75, 1.1);
    key.position.set(0.2, HC - 0.05, 1.9); key.target.position.set(0, 1.15, -0.2);
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0003; key.shadow.normalBias = 0.012;
    key.shadow.camera.near = 0.6; key.shadow.camera.far = 6; scene.add(key, key.target);

    // cable ladder tray above the cabinets, drops into the roofs
    const trayM = new THREE.MeshStandardMaterial({ color: 0x7d8380, roughness: 0.6, metalness: 0.5, envMapIntensity: 0.4 });
    const ty = 2.62, tz = -0.32;
    for (const dz of [-0.16, 0.16]) { const r = new THREE.Mesh(box(4.6, 0.075, 0.004), trayM); r.position.set(0, ty, tz + dz); scene.add(r); const lip = new THREE.Mesh(box(4.6, 0.004, 0.02), trayM); lip.position.set(0, ty + 0.036, tz + dz * 0.94); scene.add(lip); }
    for (let x = -2.25; x <= 2.25; x += 0.23) { const r = new THREE.Mesh(box(0.025, 0.012, 0.32), trayM); r.position.set(x, ty - 0.03, tz); scene.add(r); }
    const cableM = new THREE.MeshStandardMaterial({ color: 0x222423, roughness: 0.6 });
    for (let i = 0; i < 9; i++) { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.012 + (i % 3) * 0.004, 0.012 + (i % 3) * 0.004, 4.5, 10), cableM); c.rotation.z = Math.PI / 2; c.position.set(0, ty - 0.012, tz - 0.12 + i * 0.03); scene.add(c); }
    for (let ci = 0; ci < 3; ci++) for (let k = 0; k < 4; k++) {
      const x = cabX[ci] + 0.35 + k * 0.12, c = new THREE.Mesh(new THREE.CylinderGeometry(0.013, 0.013, ty - CAB.h - 0.02, 10), cableM);
      c.position.set(x, (ty + CAB.h) / 2, tz - 0.08 + (k % 2) * 0.1); scene.add(c);
    }
    for (const x of [-2.1, 2.1]) { const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, HC - ty, 8), trayM); rod.position.set(x, (HC + ty) / 2, tz); scene.add(rod); }

    // personnel door on the left wall
    const doorM = new THREE.MeshStandardMaterial({ color: 0x6f7c84, roughness: 0.45, metalness: 0.3 });
    const dr = new THREE.Mesh(box(0.05, 2.13, 0.93), doorM); dr.position.set(X0 + 0.02, 1.065, 3.35); dr.castShadow = true; scene.add(dr);
    const fr = new THREE.Mesh(box(0.06, 2.2, 1.03), new THREE.MeshStandardMaterial({ color: 0x4c555a, roughness: 0.5, metalness: 0.4 })); fr.position.set(X0 + 0.01, 1.1, 3.35); scene.add(fr);
    const lever = new THREE.Mesh(box(0.05, 0.02, 0.13), MAT.chrome); lever.position.set(X0 + 0.07, 1.0, 3.0); scene.add(lever);
    const vision = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.5), new THREE.MeshStandardMaterial({ color: 0x1d2224, roughness: 0.1, metalness: 0.2, envMapIntensity: 1.4 })); vision.rotation.y = Math.PI / 2; vision.position.set(X0 + 0.047, 1.55, 3.48); scene.add(vision);
    const exitT = canvasTex(256, 96, (g, w, h) => { g.fillStyle = '#1a1a1a'; g.fillRect(0, 0, w, h); g.fillStyle = '#ff2a1a'; g.font = `800 ${h * 0.6}px ${PN.FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('EXIT', w / 2, h / 2 + 2); });
    const exitS = new THREE.Mesh(new THREE.PlaneGeometry(0.30, 0.11), new THREE.MeshBasicMaterial({ map: exitT, toneMapped: false })); exitS.rotation.y = Math.PI / 2; exitS.position.set(X0 + 0.03, 2.40, 3.35); scene.add(exitS);
    // fire extinguisher
    const ext = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.5, 20), MAT.red); ext.position.set(X0 + 0.12, 0.55, 2.55); ext.castShadow = true; scene.add(ext);
    const extTop = new THREE.Mesh(new THREE.SphereGeometry(0.075, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), MAT.red); extTop.position.set(X0 + 0.12, 0.80, 2.55); scene.add(extTop);
    const valve = new THREE.Mesh(box(0.05, 0.08, 0.04), MAT.chrome); valve.position.set(X0 + 0.12, 0.88, 2.55); scene.add(valve);
    const extSign = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.2), new THREE.MeshStandardMaterial({ map: canvasTex(128, 128, (g, w) => { g.fillStyle = '#c8102e'; g.fillRect(0, 0, w, w); g.fillStyle = '#fff'; g.font = `800 ${w * 0.17}px ${PN.FONT}`; g.textAlign = 'center'; g.fillText('FIRE', w / 2, w * 0.4); g.fillText('EXTINGUISHER', w / 2, w * 0.62); g.font = `700 ${w * 0.13}px ${PN.FONT}`; g.fillText('CLASS ABC', w / 2, w * 0.82); }) }));
    extSign.rotation.y = Math.PI / 2; extSign.position.set(X0 + 0.005, 1.45, 2.55); scene.add(extSign);

    // wall clock (follows plant time)
    const clockG = new THREE.Group();
    const face = new THREE.Mesh(new THREE.CircleGeometry(0.16, 48), new THREE.MeshStandardMaterial({ map: canvasTex(512, 512, (g, w) => {
      g.fillStyle = '#f4f2ea'; g.beginPath(); g.arc(w / 2, w / 2, w / 2, 0, 7); g.fill();
      g.fillStyle = '#141414'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = `600 ${w * 0.1}px ${PN.FONT}`;
      for (let i = 1; i <= 12; i++) { const a = i / 12 * Math.PI * 2 - Math.PI / 2; g.fillText(String(i), w / 2 + Math.cos(a) * w * 0.37, w / 2 + Math.sin(a) * w * 0.37); }
      for (let i = 0; i < 60; i++) { const a = i / 60 * Math.PI * 2; g.lineWidth = i % 5 ? 2 : 6; g.strokeStyle = '#141414'; g.beginPath(); g.moveTo(w / 2 + Math.cos(a) * w * 0.47, w / 2 + Math.sin(a) * w * 0.47); g.lineTo(w / 2 + Math.cos(a) * w * (i % 5 ? 0.45 : 0.43), w / 2 + Math.sin(a) * w * (i % 5 ? 0.45 : 0.43)); g.stroke(); }
    }), roughness: 0.5 }));
    clockG.add(face);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.165, 0.012, 10, 48), MAT.black); clockG.add(rim);
    const glassC = new THREE.Mesh(new THREE.CircleGeometry(0.16, 48), MAT.glass); glassC.position.z = 0.012; clockG.add(glassC);
    const hand = (len, w, m) => { const g = new THREE.Group(); const hm = new THREE.Mesh(box(w, len, 0.002), m); hm.position.y = len * 0.4; g.add(hm); return g; };
    const hH = hand(0.09, 0.008, MAT.black), mH = hand(0.13, 0.005, MAT.black), sH = hand(0.14, 0.0018, MAT.redNeedle);
    hH.position.z = 0.003; mH.position.z = 0.005; sH.position.z = 0.007; clockG.add(hH, mH, sH);
    clockG.rotation.y = Math.PI / 2; clockG.position.set(X0 + 0.02, 2.35, 0.95); scene.add(clockG);
    parts.push(() => { const t = S.tod; sH.rotation.z = -(t % 60) / 60 * Math.PI * 2; mH.rotation.z = -(t % 3600) / 3600 * Math.PI * 2; hH.rotation.z = -(t % 43200) / 43200 * Math.PI * 2; });

    // single-line diagram poster on the right wall
    const sld = canvasTex(1100, 800, (g, w, h) => drawSLD(g, w, h));
    const poster = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 0.8), new THREE.MeshStandardMaterial({ map: sld, roughness: 0.7 }));
    poster.rotation.y = -Math.PI / 2; poster.position.set(X1 - 0.012, 1.65, 1.3); scene.add(poster);
    const pf = new THREE.Mesh(box(0.012, 0.84, 1.14), MAT.black); pf.position.set(X1 - 0.006, 1.65, 1.3); scene.add(pf);
    poster.position.x = X1 - 0.0135;

    // operator desk with log book, phone, binder, mug
    const deskM = new THREE.MeshStandardMaterial({ color: 0x8a8d86, roughness: 0.5, metalness: 0.4 });
    const topM = new THREE.MeshStandardMaterial({ color: 0x6d5b45, roughness: 0.55 });
    const dx = 2.35, dz = 3.0;
    const top = new THREE.Mesh(box(1.5, 0.035, 0.76), topM); top.position.set(dx, 0.74, dz); top.castShadow = true; top.receiveShadow = true; scene.add(top);
    const ped = new THREE.Mesh(box(0.42, 0.72, 0.7), deskM); ped.position.set(dx + 0.5, 0.36, dz); ped.castShadow = true; scene.add(ped);
    for (let k = 0; k < 3; k++) { const h = new THREE.Mesh(box(0.14, 0.015, 0.02), MAT.chrome); h.position.set(dx + 0.5, 0.62 - k * 0.22, dz - 0.36); scene.add(h); }
    const leg = new THREE.Mesh(box(0.04, 0.72, 0.7), deskM); leg.position.set(dx - 0.72, 0.36, dz); scene.add(leg);
    const modesty = new THREE.Mesh(box(1.4, 0.4, 0.02), deskM); modesty.position.set(dx, 0.5, dz + 0.33); scene.add(modesty);
    const logT = canvasTex(1024, 700, (g, w, h) => drawLog(g, w, h));
    const log = new THREE.Mesh(new THREE.PlaneGeometry(0.46, 0.315), new THREE.MeshStandardMaterial({ map: logT, roughness: 0.8 }));
    log.rotation.x = -Math.PI / 2; log.rotation.z = 0.08; log.position.set(dx - 0.25, 0.761, dz - 0.05); scene.add(log);
    const cover = new THREE.Mesh(box(0.47, 0.012, 0.325), new THREE.MeshStandardMaterial({ color: 0x1f2a44, roughness: 0.7 })); cover.rotation.y = -0.08; cover.position.set(dx - 0.25, 0.7535, dz - 0.05); scene.add(cover);
    const phoneM = new THREE.MeshStandardMaterial({ color: 0xcfc6ad, roughness: 0.45 });
    const ph = new THREE.Mesh(box(0.2, 0.06, 0.22), phoneM); ph.position.set(dx + 0.35, 0.79, dz - 0.12); ph.rotation.y = -0.3; ph.castShadow = true; scene.add(ph);
    const hs = new THREE.Mesh(new THREE.CapsuleGeometry(0.025, 0.16, 6, 12), phoneM); hs.rotation.z = Math.PI / 2; hs.rotation.y = -0.3; hs.position.set(dx + 0.35, 0.835, dz - 0.12); scene.add(hs);
    const binder = new THREE.Mesh(box(0.08, 0.30, 0.25), new THREE.MeshStandardMaterial({ color: 0xa31d1d, roughness: 0.6 })); binder.position.set(dx + 0.62, 0.91, dz + 0.22); binder.castShadow = true; scene.add(binder);
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.036, 0.1, 20), new THREE.MeshStandardMaterial({ color: 0xf0eee6, roughness: 0.3 })); mug.position.set(dx + 0.05, 0.807, dz - 0.25); mug.castShadow = true; scene.add(mug);
    const coffee = new THREE.Mesh(new THREE.CircleGeometry(0.035, 20), new THREE.MeshStandardMaterial({ color: 0x2a1a0e, roughness: 0.15 })); coffee.rotation.x = -Math.PI / 2; coffee.position.set(dx + 0.05, 0.85, dz - 0.25); scene.add(coffee);
    // chair
    const chairM = new THREE.MeshStandardMaterial({ color: 0x2d3035, roughness: 0.7 });
    const seat = new THREE.Mesh(box(0.48, 0.07, 0.46), chairM); seat.position.set(dx - 0.15, 0.48, dz + 0.62); seat.castShadow = true; scene.add(seat);
    const backr = new THREE.Mesh(box(0.46, 0.5, 0.06), chairM); backr.position.set(dx - 0.15, 0.82, dz + 0.86); backr.castShadow = true; scene.add(backr);
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.4, 10), MAT.chrome); post.position.set(dx - 0.15, 0.25, dz + 0.62); scene.add(post);
    for (let k = 0; k < 5; k++) { const a = k / 5 * Math.PI * 2; const l = new THREE.Mesh(box(0.3, 0.025, 0.04), MAT.black); l.position.set(dx - 0.15 + Math.cos(a) * 0.15, 0.05, dz + 0.62 + Math.sin(a) * 0.15); l.rotation.y = -a; scene.add(l); }
    DESK = { x0: dx - 0.8, x1: dx + 0.8, z0: dz - 0.42, z1: dz + 0.95 };
  }
  let DESK = null;
  function drawSLD(g, w, h) {
    g.fillStyle = '#f3f1ea'; g.fillRect(0, 0, w, h);
    g.strokeStyle = '#141414'; g.fillStyle = '#141414'; g.lineWidth = 3;
    g.font = `700 34px ${PN.FONT}`; g.textAlign = 'left'; g.fillText('SABLE CREEK HYDRO  ·  SINGLE-LINE DIAGRAM', 40, 56);
    g.font = `500 20px ${PN.FONT}`; g.fillText('DWG E-001 REV 4   ·   FOR OPERATIONS REFERENCE ONLY', 40, 86);
    const cx = 300;
    const brk = (x, y, lab) => { g.strokeRect(x - 22, y - 22, 44, 44); g.font = `600 20px ${PN.FONT}`; g.textAlign = 'left'; g.fillText(lab, x + 32, y + 7); };
    g.beginPath(); g.arc(cx, 640, 52, 0, 7); g.stroke(); g.font = `700 36px ${PN.FONT}`; g.textAlign = 'center'; g.fillText('G', cx, 652);
    g.font = `500 19px ${PN.FONT}`; g.textAlign = 'left'; g.fillText('300 kVA  480 V  0.85 PF', cx + 70, 630); g.fillText('72 POLE  100 RPM  60 Hz', cx + 70, 655); g.fillText('BRUSHLESS EXC  ·  PMG', cx + 70, 680);
    g.beginPath(); g.moveTo(cx, 588); g.lineTo(cx, 470); g.stroke();
    brk(cx, 450, '52G  800 A'); g.beginPath(); g.moveTo(cx, 428); g.lineTo(cx, 360); g.stroke();
    g.lineWidth = 8; g.beginPath(); g.moveTo(120, 360); g.lineTo(820, 360); g.stroke(); g.lineWidth = 3;
    g.font = `600 20px ${PN.FONT}`; g.fillText('480 V MAIN BUS', 130, 345);
    // station service
    g.beginPath(); g.moveTo(640, 360); g.lineTo(640, 430); g.stroke(); brk(640, 452, 'SS BKR'); g.beginPath(); g.moveTo(640, 474); g.lineTo(640, 540); g.stroke();
    g.strokeRect(590, 540, 100, 50); g.font = `600 18px ${PN.FONT}`; g.textAlign = 'center'; g.fillText('MCC-1', 640, 572); g.textAlign = 'left';
    // transformer
    g.beginPath(); g.moveTo(cx, 360); g.lineTo(cx, 300); g.stroke();
    g.beginPath(); g.arc(cx, 270, 30, 0, 7); g.stroke(); g.beginPath(); g.arc(cx, 220, 30, 0, 7); g.stroke();
    g.font = `500 19px ${PN.FONT}`; g.fillText('T1  500 kVA  480Δ – 12470Y/7200 V  Z 5.75%', cx + 48, 250);
    g.beginPath(); g.moveTo(cx, 190); g.lineTo(cx, 140); g.stroke();
    g.fillText('12.47 kV FEEDER 7  ·  TO UTILITY RECLOSER R-22', cx + 20, 132);
    g.beginPath(); g.moveTo(cx, 140); g.lineTo(cx + 520, 140); g.stroke();
    g.font = `600 16px ${PN.FONT}`; g.fillText('PROTECTION: 24 27 32 40 50/51V 59 64G 78 81O/U 87G  ·  12 38 39 49 63 71 (PLC)', 40, 760);
  }
  function drawLog(g, w, h) {
    g.fillStyle = '#f2efe3'; g.fillRect(0, 0, w, h);
    g.strokeStyle = 'rgba(80,110,170,0.35)'; g.lineWidth = 1.5;
    for (let y = 70; y < h; y += 30) { g.beginPath(); g.moveTo(10, y); g.lineTo(w - 10, y); g.stroke(); }
    g.strokeStyle = 'rgba(190,60,60,0.5)'; g.beginPath(); g.moveTo(90, 0); g.lineTo(90, h); g.stroke(); g.beginPath(); g.moveTo(w / 2 + 90, 0); g.lineTo(w / 2 + 90, h); g.stroke();
    g.fillStyle = 'rgba(0,0,0,0.25)'; g.fillRect(w / 2 - 3, 0, 6, h);
    g.fillStyle = '#1b2a58'; g.font = `400 21px ${'"Permanent Marker", cursive'}`;
    const L = ['0600 RELIEVED NIGHT SHIFT', 'U1 ON LINE 232 KW LVL CTL', 'HW 513.0  TW 472.6', 'OPU AIR ADDED, LVL 52%', '0745 STRAINER BACKWASHED', '0910 UTILITY CALLED: R-22', '  OK, NO SWITCHING TODAY', 'DT AIR VALVE IN AUTO', 'ROUGH ZONE NOTED <110 KW', '1130 BRG TEMPS NORMAL'];
    L.forEach((l, i) => { const col = i < 6 ? 0 : 1; g.fillText(l, col ? w / 2 + 100 : 100, 64 + (i % 6) * 30 + (col ? 0 : 0)); });
  }

  function environment() {
    const pm = new THREE.PMREMGenerator(renderer);
    const env = new THREE.Scene();
    const roomG = new THREE.BoxGeometry(7, 3.2, 5.4); roomG.translate(0, 1.4, 1.8);
    env.add(new THREE.Mesh(roomG, new THREE.MeshBasicMaterial({ color: 0x9a9c90, side: THREE.BackSide })));
    for (const x of [-2.2, 0, 2.2]) for (const z of [0.95, 3.15]) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 1.2), new THREE.MeshBasicMaterial({ color: 0xffffff })); p.material.color.setScalar(5); p.rotation.x = Math.PI / 2; p.position.set(x, 2.95, z); env.add(p);
    }
    const fl = new THREE.Mesh(new THREE.PlaneGeometry(7, 5.4), new THREE.MeshBasicMaterial({ color: 0x7a7060 })); fl.rotation.x = -Math.PI / 2; fl.position.set(0, -0.19, 1.8); env.add(fl);
    const cabs = new THREE.Mesh(new THREE.BoxGeometry(3.6, 2, 0.1), new THREE.MeshBasicMaterial({ color: 0x8a8f8c })); cabs.position.set(0, 1, -0.7); env.add(cabs);
    scene.environment = pm.fromScene(env, 0.04).texture;
    pm.dispose();
  }

  /* ======================================================= CAMERA & INPUT */
  function clampCam() {
    ctl.x = Math.max(ROOM.X0 + 0.35, Math.min(ROOM.X1 - 0.35, ctl.x));
    ctl.z = Math.max(0.36, Math.min(ROOM.ZF - 0.35, ctl.z));
    if (DESK && ctl.x > DESK.x0 && ctl.x < DESK.x1 && ctl.z > DESK.z0 && ctl.z < DESK.z1) {
      const dx = Math.min(ctl.x - DESK.x0, DESK.x1 - ctl.x), dz = Math.min(ctl.z - DESK.z0, DESK.z1 - ctl.z);
      if (dx < dz) ctl.x = ctl.x - DESK.x0 < DESK.x1 - ctl.x ? DESK.x0 : DESK.x1; else ctl.z = ctl.z - DESK.z0 < DESK.z1 - ctl.z ? DESK.z0 : DESK.z1;
    }
    ctl.pitch = Math.max(-1.0, Math.min(0.7, ctl.pitch));
  }
  function applyCam() {
    camera.position.set(ctl.x, ctl.eye ?? EYE, ctl.z);
    const d = new THREE.Vector3(Math.sin(ctl.yaw) * Math.cos(ctl.pitch), Math.sin(ctl.pitch), -Math.cos(ctl.yaw) * Math.cos(ctl.pitch));
    camera.lookAt(camera.position.clone().add(d));
  }
  function walkTo(x, z, yaw = 0, pitch = -0.12) { ctl.tx = x; ctl.tz = z; ctl.tyaw = yaw; ctl.tpitch = pitch; }
  function pick(e) {
    const r = canvasEl.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const h = raycaster.intersectObjects(hits, false);
    return h.length ? h[0] : null;
  }
  function pickWorld(e) {
    const r = canvasEl.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const h = raycaster.intersectObjects(scene.children, false).filter(x => x.object.visible !== false && x.object.material && x.object.material.visible !== false);
    return h.length ? h[0] : null;
  }
  function press(h) {
    const ud = h.object.userData, it = ud.it;
    const local = h.object.worldToLocal(h.point.clone());
    const side = local.x < 0 ? -1 : 1;
    ud.side = side;
    let sound = 'click';
    if (ud.action === 'pb') { it.press && it.press(); sound = 'pb'; }
    else if (ud.action === 'sel') { const n = it.pos.length, i = it.get(); const j = Math.max(0, Math.min(n - 1, i + side)); if (j !== i) it.set(j); else sound = 'stop'; }
    else if (ud.action === 'rl') { it.hold(side); }
    else if (ud.action === 'cs') { it.act(side); sound = 'cs'; }
    else if (ud.action === 'estop') { P.cmd('estop'); sound = 'estop'; }
    else if (ud.action === 'lockout') { P.cmd('reset86', it.which); sound = 'cs'; }
    else return false;
    held = h.object;
    if (soundCb) soundCb(sound);
    return true;
  }
  function release() {
    if (!held) return;
    const ud = held.userData, it = ud.it;
    if (ud.action === 'rl') it.hold(0);
    if (ud.action === 'pb' || ud.action === 'cs') soundCb && soundCb('release');
    held = null;
  }
  function bindInput() {
    const ptrs = new Map();
    let drag = null, lastTap = 0, pinch = null;
    canvasEl.addEventListener('contextmenu', e => e.preventDefault());
    canvasEl.addEventListener('pointerdown', e => {
      canvasEl.setPointerCapture(e.pointerId);
      ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (ptrs.size === 2) {
        release(); drag = null;
        const [a, b] = [...ptrs.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2, x: ctl.x, z: ctl.z };
        return;
      }
      ctl.tx = ctl.tz = ctl.tyaw = ctl.tpitch = null;
      const h = e.button === 0 ? pick(e) : null;
      if (h && h.object.userData.action && press(h)) return;
      drag = { x: e.clientX, y: e.clientY, yaw: ctl.yaw, pitch: ctl.pitch, cx: ctl.x, cz: ctl.z, move: e.button === 2 || e.shiftKey, moved: 0, touch: e.pointerType === 'touch' };
    });
    canvasEl.addEventListener('pointermove', e => {
      if (ptrs.has(e.pointerId)) ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && ptrs.size === 2) {
        const [a, b] = [...ptrs.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2;
        const fwd = (d - pinch.d) * 0.006, side = -(mx - pinch.mx) * 0.004;
        ctl.x = pinch.x + Math.sin(ctl.yaw) * fwd + Math.cos(ctl.yaw) * side;
        ctl.z = pinch.z - Math.cos(ctl.yaw) * fwd + Math.sin(ctl.yaw) * side;
        clampCam(); return;
      }
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        drag.moved = Math.max(drag.moved, Math.abs(dx) + Math.abs(dy));
        if (drag.move) {
          ctl.x = drag.cx - Math.cos(ctl.yaw) * dx * 0.004; ctl.z = drag.cz - Math.sin(ctl.yaw) * dx * 0.004;
        } else {
          const k = drag.touch ? 0.0055 : 0.0042;
          ctl.yaw = drag.yaw - dx * k; ctl.pitch = drag.pitch + dy * k * 0.85;
        }
        clampCam(); return;
      }
      if (e.pointerType !== 'touch') {
        const h = pick(e);
        hover = h ? h.object : null;
        canvasEl.style.cursor = h && h.object.userData.action ? 'pointer' : 'grab';
        if (tipCb) tipCb(h ? h.object.userData : null, e.clientX, e.clientY, h ? h.point : null);
      }
    });
    const up = e => {
      ptrs.delete(e.pointerId);
      if (ptrs.size < 2) pinch = null;
      if (held) { release(); return; }
      if (drag && drag.moved < 6 && e.type === 'pointerup') {
        const now = performance.now();
        if (now - lastTap < 330) {
          const h = pickWorld(e);
          if (h && h.point.z < 0.12 && h.point.y > 0.3) walkTo(h.point.x, 0.78, 0, Math.atan2(h.point.y - EYE, 0.78) * 0.85);
          else if (h && h.point.y < 0.05) walkTo(h.point.x, Math.max(0.5, h.point.z), ctl.yaw, ctl.pitch);
        } else if (drag.touch) {
          const h = pick(e);
          if (tipCb) tipCb(h ? h.object.userData : null, e.clientX, e.clientY, h ? h.point : null, true);
        }
        lastTap = now;
      }
      drag = null;
    };
    canvasEl.addEventListener('pointerup', up); canvasEl.addEventListener('pointercancel', up);
    canvasEl.addEventListener('pointerleave', () => { if (tipCb) tipCb(null); });
    canvasEl.addEventListener('wheel', e => {
      e.preventDefault();
      const k = (e.deltaMode === 1 ? 0.05 : 0.0014) * e.deltaY;
      ctl.x -= Math.sin(ctl.yaw) * k; ctl.z += Math.cos(ctl.yaw) * k; ctl.tx = ctl.tz = null; clampCam();
    }, { passive: false });
    window.addEventListener('keydown', e => {
      if (!active || (e.target.closest && e.target.closest('input,textarea,select,button,[role=dialog]'))) return;
      const k = e.key.toLowerCase();
      ctl.keys[k] = true;
      if (k === '1' || k === '2' || k === '3') walkToCab(+k - 1);
      if (k === '0') home();
    });
    window.addEventListener('keyup', e => { ctl.keys[e.key.toLowerCase()] = false; });
    window.addEventListener('blur', () => { ctl.keys = {}; release(); });
    window.addEventListener('resize', resize);
  }
  function controls(dt) {
    const k = ctl.keys, sp = (k.shift ? 2.4 : 1.2) * dt;
    let fx = 0, fz = 0;
    if (k.w || k.arrowup) fz += 1; if (k.s || k.arrowdown) fz -= 1;
    if (k.d || k.arrowright) fx += 1; if (k.a || k.arrowleft) fx -= 1;
    if (k.q) ctl.yaw -= dt * 1.4; if (k.e) ctl.yaw += dt * 1.4;
    if (fx || fz) {
      ctl.tx = ctl.tz = null;
      ctl.x += (Math.sin(ctl.yaw) * fz + Math.cos(ctl.yaw) * fx) * sp;
      ctl.z += (-Math.cos(ctl.yaw) * fz + Math.sin(ctl.yaw) * fx) * sp;
    }
    const e = 1 - Math.exp(-dt * 4.2);
    if (ctl.tx !== null) { ctl.x += (ctl.tx - ctl.x) * e; ctl.z += (ctl.tz - ctl.z) * e; if (Math.abs(ctl.tx - ctl.x) + Math.abs(ctl.tz - ctl.z) < 0.002) ctl.tx = ctl.tz = null; }
    if (ctl.tyaw !== null) { let d = ctl.tyaw - ctl.yaw; d = Math.atan2(Math.sin(d), Math.cos(d)); ctl.yaw += d * e; ctl.pitch += (ctl.tpitch - ctl.pitch) * e; if (Math.abs(d) + Math.abs(ctl.tpitch - ctl.pitch) < 0.001) ctl.tyaw = ctl.tpitch = null; }
    clampCam(); applyCam();
  }
  function resize() {
    if (!renderer) return;
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false); canvasEl.style.width = w + 'px'; canvasEl.style.height = h + 'px';
    camera.aspect = w / h;
    camera.fov = w / h < 0.8 ? 68 : 55;
    camera.updateProjectionMatrix();
  }
  function walkToCab(i) { walkTo(cabX[i] + CAB.w / 2, 1.25, 0, -0.16); }
  function home() { walkTo(0.35, 2.6, -0.06, -0.13); }

  /* ============================================================ LIFECYCLE */
  let quality = 2, fpsN = 0, fpsT = 0;
  function frame(dt) {
    if (!active) return;
    frameNo++;
    dt = Math.min(dt, 0.1);
    controls(dt);
    for (const p of parts) p(dt);
    for (const d of dyn) d(dt);
    renderer.render(scene, camera);
    fpsN++; fpsT += dt;
    if (fpsT > 3) {
      const fps = fpsN / fpsT; fpsN = 0; fpsT = 0;
      if (fps < 28 && quality > 0) {
        quality--;
        if (quality === 1) renderer.setPixelRatio(1);
        if (quality === 0) { renderer.shadowMap.enabled = false; scene.traverse(o => { if (o.material) [].concat(o.material).forEach(m => { m.needsUpdate = true; }); }); renderer.setPixelRatio(0.75); }
        resize();
      }
    }
  }
  function available() {
    if (!window.THREE) return false;
    try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
  }
  function start(opts = {}) {
    THREE = window.THREE;
    tipCb = opts.onTip || null; soundCb = opts.onSound || null;
    canvasEl = document.createElement('canvas'); canvasEl.id = 'gl'; document.body.prepend(canvasEl);
    renderer = new THREE.WebGLRenderer({ canvas: canvasEl, antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(1.75, window.devicePixelRatio || 1));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.92;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    scene = new THREE.Scene(); scene.background = new THREE.Color(0x202220);
    camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.03, 30);
    raycaster = new THREE.Raycaster(); ndc = new THREE.Vector2();
    const t0 = performance.now();
    materials();
    environment();
    for (let i = 0; i < PN.CABS.length; i++) buildCabinet(i);
    buildRoom();
    flushBatches();
    renderer.compile(scene, camera);
    console.info(`ROOM built in ${Math.round(performance.now() - t0)} ms, ${hits.length} hit targets, ${parts.length} animated parts`);
    if (opts.view) Object.assign(ctl, opts.view);
    applyCam(); resize(); bindInput();
    active = true;
    return true;
  }
  return {
    available, start, frame, walkToCab, home,
    get active() { return active; },
    get held() { return held; },
    get camera() { return camera; },
    get ctl() { return ctl; },
    hitList: () => hits,
    toDoor(ci, p) { if (!p) return null; return { x: (p.x - (cabX[ci] + 0.03)) * 1000, y: (CAB.doorTop - p.y) * 1000 }; },
    screenOf(match) {               // test helper: screen position of a control by label
      const h = hits.find(m => m.userData.it && (m.userData.it.label === match || m.userData.it.which === match));
      if (!h) return null;
      const v = h.position.clone().project(camera);
      return { x: (v.x + 1) / 2 * window.innerWidth, y: (1 - v.y) / 2 * window.innerHeight };
    },
  };
})();
