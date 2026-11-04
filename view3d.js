'use strict';
/* =====================================================================
   VIEW3D · the control room in real 3D (three.js / WebGL)
   The DOM cabinets stay the source of truth: they are laid out (hidden),
   the simulator keeps driving them, and this module mirrors them as 3D
   geometry. Flat artwork (labels, plates, mimic, grime) is painted from
   the DOM into one texture per cabinet front; everything that sticks out
   or moves (meters, lamps, knobs, buttons, relays, E-stop...) is a mesh.
   Clicks are ray-cast back onto the DOM controls.
   ===================================================================== */
window.VIEW3D = (() => {
  const S = 2.2 / 1079;                 // metres per CSS px (cabinet = 2.2 m tall)
  const T = 1.75;                        // texture px per CSS px for painted fronts
  const DEPTH = 0.6, EYE = 1.62;
  let THREE, renderer, scene, camera, U, lineup, cabs = [], rowLen = 0;
  const parts = [];                      // { update(dt) }
  const meterTex = [];                   // { m, tex, mesh, last }
  const pick = [];                       // meshes for ray casting
  const hits = [];                       // per cab: [{el, x, y, w, h}]
  let active = false, frameNo = 0, quality = 2;
  const ctl = { x: 0, z: 2.4, yaw: 0, pitch: -0.12, tx: null, tz: null, tyaw: null, tpitch: null, keys: {} };

  /* ---------------------------------------------------------------- utils */
  const cv = (w, h) => { const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c; };
  function rel(el, origin) {
    const r = el.getBoundingClientRect();
    return { x: r.left - origin.left, y: r.top - origin.top, w: r.width, h: r.height };
  }
  function texFrom(canvas, srgb = true) {
    const t = new THREE.CanvasTexture(canvas);
    if (srgb) t.encoding = THREE.sRGBEncoding;
    t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    return t;
  }
  function rrect(g, x, y, w, h, r) {
    g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
  }
  const has = (el, sel) => el.matches && el.matches(sel);

  /* ------------------------------------------------------------ painter
     Paints a DOM subtree (backgrounds by component type + every text node)
     onto a canvas, at T texture px per CSS px. */
  const MESHY = '.mwrap, .lamp, .pb, .knobw, .estop, .dsw, .relay, .ann, .printer, .ctr, .clockbox, .rec, .lh, .lflag, .hit, .handle, .lock, .skin, .scuff, svg, canvas';
  function paintSubtree(g, root, origin, opts = {}) {
    const skip = opts.skip || MESHY;
    const walk = (el, isRoot) => {
      if (!isRoot && has(el, skip)) return;
      drawBox(g, el, origin);
      for (const ch of el.childNodes) {
        if (ch.nodeType === 3) { if (ch.nodeValue.trim()) drawText(g, ch, el, origin); }
        else if (ch.nodeType === 1) walk(ch, false);
      }
    };
    walk(root, true);
  }
  function drawText(g, node, parent, origin) {
    const cs = getComputedStyle(parent);
    let txt = node.nodeValue.replace(/\s+/g, ' ');
    if (cs.textTransform === 'uppercase') txt = txt.toUpperCase();
    const range = document.createRange(); range.selectNodeContents(node);
    const rects = [...range.getClientRects()].filter(r => r.width > 0.5);
    if (!rects.length) return;
    g.font = `${cs.fontStyle} ${cs.fontWeight} ${parseFloat(cs.fontSize) * T}px ${cs.fontFamily}`;
    try { g.letterSpacing = (parseFloat(cs.letterSpacing) || 0) * T + 'px'; } catch (e) { /* older canvas */ }
    g.fillStyle = cs.color; g.textBaseline = 'middle'; g.textAlign = 'left';
    const pieces = rects.length > 1 ? splitToRects(g, node.nodeValue.trim(), rects, cs) : [txt.trim()];
    rects.forEach((r, i) => {
      const s = pieces[i]; if (!s) return;
      g.fillText(s, (r.left - origin.left) * T, (r.top - origin.top + r.height / 2) * T);
    });
    try { g.letterSpacing = '0px'; } catch (e) { /* noop */ }
  }
  function splitToRects(g, text, rects, cs) {
    const up = cs.textTransform === 'uppercase';
    let lines = text.split('\n').map(s => s.trim()).filter(Boolean);
    if (lines.length !== rects.length) {          // soft-wrapped: fill each rect greedily by width
      const words = text.replace(/\s+/g, ' ').split(' '); lines = [];
      let wi = 0;
      for (const r of rects) {
        let line = '';
        while (wi < words.length) {
          const t = line ? line + ' ' + words[wi] : words[wi];
          if (line && g.measureText(up ? t.toUpperCase() : t).width > r.width * T * 1.04) break;
          line = t; wi++;
        }
        lines.push(line);
      }
    }
    return lines.map(s => up ? s.toUpperCase() : s);
  }
  function screwAt(g, cx, cy, r, ang) {
    const gr = g.createRadialGradient(cx - r * 0.3, cy - r * 0.3, 0, cx, cy, r);
    gr.addColorStop(0, '#f2f0ea'); gr.addColorStop(0.55, '#a4a198'); gr.addColorStop(1, '#5d5b55');
    g.fillStyle = gr; g.beginPath(); g.arc(cx, cy, r, 0, 7); g.fill();
    g.save(); g.translate(cx, cy); g.rotate(ang); g.fillStyle = 'rgba(35,33,30,.9)'; g.fillRect(-r * 0.8, -r * 0.16, r * 1.6, r * 0.32); g.restore();
  }
  function drawBox(g, el, origin) {
    if (!el.classList || !el.classList.length) return;
    const r = rel(el, origin), x = r.x * T, y = r.y * T, w = r.w * T, h = r.h * T;
    if (w < 1 || h < 1) return;
    const cl = el.classList;
    let gr;
    if (cl.contains('sec')) {
      g.fillStyle = 'rgba(0,0,0,.04)'; rrect(g, x, y, w, h, 2 * T); g.fill();
      g.strokeStyle = 'rgba(0,0,0,.14)'; g.lineWidth = T; g.stroke();
      g.strokeStyle = 'rgba(255,255,255,.22)'; g.beginPath(); g.moveTo(x + 2, y + h - 1); g.lineTo(x + 2, y + 2); g.lineTo(x + w - 2, y + 2); g.stroke();
    } else if (cl.contains('tag') || ((cl.contains('code') || cl.contains('name')) && el.parentNode.classList.contains('np'))) {
      const white = cl.contains('w');
      gr = g.createLinearGradient(0, y, 0, y + h);
      if (white) { gr.addColorStop(0, '#f6f4ec'); gr.addColorStop(1, '#e1ded3'); } else { gr.addColorStop(0, '#272725'); gr.addColorStop(1, '#121211'); }
      g.fillStyle = 'rgba(0,0,0,.45)'; rrect(g, x + T * 0.5, y + T * 1.2, w, h, 2 * T); g.fill();
      g.fillStyle = gr; rrect(g, x, y, w, h, 1.6 * T); g.fill();
      g.strokeStyle = white ? 'rgba(0,0,0,.25)' : 'rgba(255,255,255,.12)'; g.lineWidth = 1; g.beginPath(); g.moveTo(x + 2, y + 1); g.lineTo(x + w - 2, y + 1); g.stroke();
    } else if (cl.contains('dymo')) {
      const col = cl.contains('red') ? '#9b1d1a' : cl.contains('blk') ? '#1b1b1b' : '#1f3f86';
      g.fillStyle = 'rgba(0,0,0,.4)'; rrect(g, x + T, y + 1.5 * T, w, h, 2 * T); g.fill();
      g.fillStyle = col; rrect(g, x, y, w, h, 2 * T); g.fill();
      gr = g.createLinearGradient(0, y, 0, y + h); gr.addColorStop(0, 'rgba(255,255,255,.22)'); gr.addColorStop(0.45, 'rgba(255,255,255,0)'); gr.addColorStop(1, 'rgba(0,0,0,.15)');
      g.fillStyle = gr; rrect(g, x, y, w, h, 2 * T); g.fill();
    } else if (cl.contains('plate-metal') || cl.contains('plate')) {
      g.fillStyle = 'rgba(0,0,0,.35)'; rrect(g, x + T, y + 2 * T, w, h, 3 * T); g.fill();
      gr = g.createLinearGradient(x, y, x + w, y + h);
      gr.addColorStop(0, '#eeede8'); gr.addColorStop(0.4, '#c3c2bc'); gr.addColorStop(0.62, '#a9a8a2'); gr.addColorStop(1, '#dcdbd5');
      g.fillStyle = gr; rrect(g, x, y, w, h, 3 * T); g.fill();
      g.globalAlpha = 0.07; g.fillStyle = '#fff';
      for (let i = 0; i < w; i += 2) g.fillRect(x + i, y, 1, h);
      g.globalAlpha = 1;
      g.strokeStyle = 'rgba(0,0,0,.35)'; g.lineWidth = 1; rrect(g, x + 0.5, y + 0.5, w - 1, h - 1, 3 * T); g.stroke();
    } else if (cl.contains('rv')) {
      screwAt(g, x + w / 2, y + h / 2, w / 2, 0);
    } else if (cl.contains('scr')) {
      const a = parseFloat(getComputedStyle(el).getPropertyValue('--a')) || 30;
      screwAt(g, x + w / 2, y + h / 2, w / 2, a * Math.PI / 180);
    } else if (cl.contains('blank')) {
      g.fillStyle = 'rgba(0,0,0,.3)'; g.fillRect(x + T, y + 2 * T, w, h);
      g.fillStyle = '#b3ae9b'; g.fillRect(x, y, w, h);
      g.strokeStyle = 'rgba(0,0,0,.3)'; g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      for (const [sx, sy] of [[x + 11 * T, y + 11 * T], [x + w - 11 * T, y + 11 * T]]) screwAt(g, sx, sy, 3.5 * T, 0.6);
    } else if (cl.contains('card')) {
      g.fillStyle = 'rgba(0,0,0,.3)'; g.fillRect(x + 1.5 * T, y + 3 * T, w, h);
      g.fillStyle = '#efe6c6'; g.fillRect(x, y, w, h);
      g.fillStyle = 'rgba(240,236,210,.75)'; g.fillRect(x + 10 * T, y - 6 * T, 36 * T, 13 * T); g.fillRect(x + w - 46 * T, y - 6 * T, 36 * T, 13 * T);
    } else if (cl.contains('clip')) {
      g.fillStyle = 'rgba(0,0,0,.4)'; rrect(g, x + 3 * T, y + 8 * T, w, h, 6 * T); g.fill();
      gr = g.createLinearGradient(x, y, x + w, y + h); gr.addColorStop(0, '#8a6236'); gr.addColorStop(0.6, '#6d4a25'); gr.addColorStop(1, '#7c5630');
      g.fillStyle = gr; rrect(g, x, y, w, h, 6 * T); g.fill();
    } else if (cl.contains('clamp')) {
      gr = g.createLinearGradient(0, y, 0, y + h); gr.addColorStop(0, '#e3e3dd'); gr.addColorStop(0.6, '#9c9c95'); gr.addColorStop(1, '#cfcfc8');
      g.fillStyle = gr; rrect(g, x, y, w, h, 5 * T); g.fill();
    } else if (cl.contains('logsheet')) {
      g.fillStyle = '#fbf9ef'; g.fillRect(x, y, w, h);
      g.strokeStyle = 'rgba(70,110,170,.28)'; g.lineWidth = T;
      for (let yy = y + 24 * T; yy < y + h; yy += 19 * T) { g.beginPath(); g.moveTo(x, yy); g.lineTo(x + w, yy); g.stroke(); }
      g.strokeStyle = 'rgba(200,60,60,.45)'; g.beginPath(); g.moveTo(x + 26 * T, y); g.lineTo(x + 26 * T, y + h); g.stroke();
    } else if (cl.contains('mimic')) {
      g.fillStyle = 'rgba(0,0,0,.05)'; g.fillRect(x, y, w, h);
      g.strokeStyle = 'rgba(0,0,0,.14)'; g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    } else if (cl.contains('lockout')) {
      g.fillStyle = 'rgba(0,0,0,.45)'; rrect(g, x + 2 * T, y + 4 * T, w, h, 4 * T); g.fill();
      gr = g.createLinearGradient(0, y, 0, y + h); gr.addColorStop(0, '#4b4c45'); gr.addColorStop(1, '#262722');
      g.fillStyle = gr; rrect(g, x, y, w, h, 4 * T); g.fill();
    } else if (cl.contains('hinge')) {
      gr = g.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, '#77756c'); gr.addColorStop(0.5, '#c8c5b9'); gr.addColorStop(1, '#6a685f');
      g.fillStyle = gr; rrect(g, x, y, w, h, 2 * T); g.fill();
    } else if (cl.contains('relays') || cl.contains('lockouts')) {
      /* containers */
    }
  }

  /* --------------------------------------------- cabinet front textures */
  function paintCabFront(cab, door, plinth) {
    const o = cab.getBoundingClientRect();
    const pl = plinth.getBoundingClientRect();
    const W = o.width, H = pl.top - o.top;
    const c = cv(W * T, H * T), g = c.getContext('2d');
    // frame and roof band
    g.fillStyle = '#a29d8a'; g.fillRect(0, 0, c.width, c.height);
    const top = cab.querySelector('.cab-top'), tr = rel(top, o);
    let gr = g.createLinearGradient(0, tr.y * T, 0, (tr.y + tr.h) * T);
    gr.addColorStop(0, '#d8d2bd'); gr.addColorStop(0.1, '#c9c4b1'); gr.addColorStop(0.5, '#bab5a2'); gr.addColorStop(1, '#a29d8a');
    g.fillStyle = gr; g.fillRect(0, tr.y * T, c.width, tr.h * T);
    cab.querySelectorAll('.cab-top .louv').forEach(l => {
      const r = rel(l, o);
      g.fillStyle = '#2b2a26'; g.fillRect(r.x * T, r.y * T, r.w * T, r.h * T);
      for (let yy = 0; yy < r.h; yy += 4.5) {
        g.fillStyle = '#d6d0bc'; g.fillRect(r.x * T, (r.y + yy + 2) * T, r.w * T, 0.6 * T);
        g.fillStyle = '#bab5a2'; g.fillRect(r.x * T, (r.y + yy + 2.6) * T, r.w * T, 1.6 * T);
      }
    });
    // door skin (paint, grime, light) baked by look.js
    const dr = rel(door, o), skin = door.querySelector('.skin');
    g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect((dr.x - 2) * T, (dr.y - 2) * T, (dr.w + 4) * T, (dr.h + 4) * T);
    if (skin) g.drawImage(skin, dr.x * T, dr.y * T, dr.w * T, dr.h * T);
    else { g.fillStyle = '#bab5a2'; g.fillRect(dr.x * T, dr.y * T, dr.w * T, dr.h * T); }
    paintSubtree(g, door, o);
    const tex = texFrom(c);
    // the single-line diagram is SVG: rasterise it asynchronously into the same texture
    const svg = door.querySelector('.mimic svg');
    if (svg) {
      const r = rel(svg, o);
      const clone = svg.cloneNode(true);
      clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      clone.setAttribute('width', r.w); clone.setAttribute('height', r.h);
      let src = new XMLSerializer().serializeToString(clone)
        .replace(/var\(--mimic-hv\)/g, '#b0251c').replace(/var\(--mimic-lv\)/g, '#2c6a3a').replace(/var\(--mimic-dc\)/g, '#23468f');
      const img = new Image();
      img.onload = () => {
        g.drawImage(img, r.x * T, r.y * T, r.w * T, r.h * T);
        door.querySelectorAll('.mimic .tag').forEach(t => paintSubtree(g, t, o, { skip: MESHY }));
        tex.needsUpdate = true;
      };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(src);
    }
    return { tex, H };
  }
  function paintPlinth(plinth) {
    const o = plinth.getBoundingClientRect();
    const c = cv(o.width * T, o.height * T), g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 0, c.height); gr.addColorStop(0, '#262624'); gr.addColorStop(1, '#141413');
    g.fillStyle = gr; g.fillRect(0, 0, c.width, c.height);
    g.fillStyle = '#0b0b0b'; g.fillRect(0, 0, c.width, 2 * T);
    const vx = c.width * 0.2, vw = c.width * 0.6;
    for (let x = vx; x < vx + vw; x += 9 * T) { g.fillStyle = '#050505'; g.fillRect(x, 18 * T, 6 * T, 26 * T); g.fillStyle = '#2a2a28'; g.fillRect(x + 6 * T, 18 * T, 3 * T, 26 * T); }
    const sc = plinth.querySelector('.scuff');
    if (sc) g.drawImage(sc, 0, 0, c.width, c.height);
    return texFrom(c);
  }

  /* ----------------------------------------------------- materials */
  let MAT;
  function materials() {
    const steelC = cv(256, 256), sg = steelC.getContext('2d');
    sg.fillStyle = '#bab5a2'; sg.fillRect(0, 0, 256, 256);
    const peel = getComputedStyle(document.documentElement).getPropertyValue('--noise');
    void peel;
    for (let i = 0; i < 2600; i++) { sg.fillStyle = `rgba(${Math.random() < 0.5 ? '255,255,255' : '60,55,45'},${(Math.random() * 0.05).toFixed(3)})`; sg.fillRect(Math.random() * 256, Math.random() * 256, 2, 2); }
    const steelT = texFrom(steelC); steelT.wrapS = steelT.wrapT = THREE.RepeatWrapping; steelT.repeat.set(3, 3);
    const std = (o) => new THREE.MeshStandardMaterial(o);
    MAT = {
      steel: std({ color: 0xffffff, map: steelT, roughness: 0.62, metalness: 0.12, envMapIntensity: 0.5 }),
      steelDark: std({ color: 0x8f8a78, map: steelT, roughness: 0.65, metalness: 0.1, envMapIntensity: 0.4 }),
      plinth: std({ color: 0x1b1b1a, roughness: 0.8, metalness: 0.1 }),
      bezel: std({ color: 0x141413, roughness: 0.38, metalness: 0.05, envMapIntensity: 0.8 }),
      chrome: std({ color: 0xd6d6d0, roughness: 0.22, metalness: 1.0, envMapIntensity: 1.2 }),
      chromeKnurl: std({ color: 0xb8b7b0, roughness: 0.38, metalness: 1.0, envMapIntensity: 1.0 }),
      bakelite: std({ color: 0x121212, roughness: 0.32, metalness: 0.0, envMapIntensity: 0.9 }),
      bakeliteRed: std({ color: 0xa3200f, roughness: 0.3, metalness: 0.0, envMapIntensity: 0.8 }),
      white: std({ color: 0xf0eee6, roughness: 0.5 }),
      brass: std({ color: 0xc9a54a, roughness: 0.3, metalness: 1.0, envMapIntensity: 1.0 }),
      yellow: std({ color: 0xe8b512, roughness: 0.45 }),
      grey: std({ color: 0xc8c6bc, roughness: 0.5, metalness: 0.2 }),
      relayCase: std({ color: 0x292a25, roughness: 0.5, metalness: 0.2 }),
      beige: std({ color: 0xcfc6ad, roughness: 0.6 }),
      glass: new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.04, metalness: 0, transmission: 0, transparent: true, opacity: 0.12, envMapIntensity: 1.4, clearcoat: 1, depthWrite: false }),
    };
  }
  const glowTex = (() => { let t = null; return () => {
    if (t) return t;
    const c = cv(64, 64), g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.25, 'rgba(255,255,255,.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64); t = new THREE.CanvasTexture(c); return t;
  }; })();
  const LAMPC = { red: [0xff4a2a, 0x3a0b06], green: [0x48ff6a, 0x0c2410], amber: [0xffa526, 0x3a2405], white: [0xfff3d6, 0x34322b], blue: [0x5a8cff, 0x0b1430] };
  const CAPC = { green: 0x167a2c, red: 0xb01a0b, black: 0x161615, white: 0xcfccbf, yellow: 0xc89a10, blue: 0x173c99 };

  /* ------------------------------------------------- mesh builders */
  function place(mesh, cabInfo, r, z) {
    mesh.position.set(cabInfo.x0 + (r.x + r.w / 2) * S, cabInfo.h - (r.y + r.h / 2) * S, z);
    return mesh;
  }
  function addPick(mesh, ci) { mesh.userData.cab = ci; pick.push(mesh); }
  function mountZ(el) {
    if (el.closest('.printer')) return 0.035;
    if (el.closest('.relay')) return 0.05;
    return 0;
  }
  function cyl(rt, rb, h, seg = 32) { const g = new THREE.CylinderGeometry(rt, rb, h, seg); g.rotateX(Math.PI / 2); return g; }

  function buildLamp(el, ci, info) {
    const r = rel(el, info.o), rad = r.w / 2 * S, z0 = mountZ(el);
    const color = ['red', 'green', 'amber', 'white', 'blue'].find(c => el.classList.contains(c)) || 'white';
    const grp = new THREE.Group();
    const bez = new THREE.Mesh(cyl(rad, rad * 1.04, 0.012, 28), MAT.chromeKnurl); bez.position.z = 0.006; grp.add(bez);
    const lensG = new THREE.SphereGeometry(rad * 0.74, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2); lensG.rotateX(Math.PI / 2); lensG.scale(1, 1, 0.55);
    const [on, off] = LAMPC[color];
    const lensM = new THREE.MeshStandardMaterial({ color: off, emissive: on, emissiveIntensity: 0, roughness: 0.3, metalness: 0, envMapIntensity: 0.45 });
    const lens = new THREE.Mesh(lensG, lensM); lens.position.z = 0.012; grp.add(lens);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: on, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, opacity: 0.85 }));
    glow.scale.set(rad * 6, rad * 6, 1); glow.position.z = 0.02; glow.visible = false; grp.add(glow);
    place(grp, info, r, z0); scene.add(grp);
    bez.castShadow = true;
    let last = null;
    parts.push({ update() {
      const isOn = el.classList.contains('on');
      const op = isOn ? parseFloat(el.firstChild && el.firstChild.style.opacity || '1') : 0;
      const k = isOn ? (isNaN(op) ? 1 : op) : 0;
      if (k === last) return; last = k;
      lensM.emissiveIntensity = k * 2.4; lensM.color.setHex(k ? on : off);
      glow.visible = k > 0.05; glow.material.opacity = 0.75 * k;
    } });
  }
  function buildButton(el, ci, info) {
    const r = rel(el, info.o), rad = r.w / 2 * S, z0 = mountZ(el);
    const color = Object.keys(CAPC).find(c => el.classList.contains(c)) || 'black';
    const sq = el.classList.contains('sq');
    const grp = new THREE.Group();
    const ring = new THREE.Mesh(sq ? new THREE.BoxGeometry(r.w * S, r.h * S, 0.01) : cyl(rad, rad * 1.03, 0.01, 32), MAT.chromeKnurl);
    ring.position.z = 0.005; grp.add(ring);
    const capM = new THREE.MeshStandardMaterial({ color: CAPC[color], roughness: 0.3, metalness: 0, envMapIntensity: 0.6, emissive: CAPC[color], emissiveIntensity: 0 });
    const cap = new THREE.Mesh(sq ? new THREE.BoxGeometry(r.w * S * 0.8, r.h * S * 0.8, 0.018) : cyl(rad * 0.76, rad * 0.8, 0.018, 32), capM);
    cap.position.z = 0.019; grp.add(cap);
    place(grp, info, r, z0); scene.add(grp);
    cap.castShadow = ring.castShadow = true;
    addPick(cap, ci); addPick(ring, ci);
    parts.push({ update() {
      const down = el.classList.contains('down');
      cap.position.z += ((down ? 0.012 : 0.019) - cap.position.z) * 0.6;
      capM.emissiveIntensity = el.classList.contains('lit') ? 0.9 : 0;
    } });
  }
  function buildKnob(rot, ci, info) {
    const r = rel(rot, info.o), knob = rot.querySelector('.knob');
    const type = knob.classList.contains('pistol') ? 'pistol' : knob.classList.contains('key') ? 'key' : 'round';
    const red = knob.classList.contains('red');
    const grp = new THREE.Group();
    const plateZ = 0.004;
    if (type === 'pistol') {
      const hub = new THREE.Mesh(cyl(11 * S, 12 * S, 0.02, 28), red ? MAT.bakeliteRed : MAT.bakelite); hub.position.z = plateZ + 0.01; grp.add(hub);
      const gripG = new THREE.CapsuleGeometry(7.5 * S, 31 * S, 6, 16); gripG.scale(1, 1, 0.8);
      const grip = new THREE.Mesh(gripG, red ? MAT.bakeliteRed : MAT.bakelite); grip.position.set(0, 4 * S, plateZ + 0.026); grp.add(grip);
      const ptr = new THREE.Mesh(new THREE.BoxGeometry(4 * S, 16 * S, 0.002), MAT.white); ptr.position.set(0, 14 * S, plateZ + 0.026 + 7.5 * S * 0.8); grp.add(ptr);
      grip.castShadow = hub.castShadow = true; addPick(grip, ci); addPick(hub, ci);
    } else if (type === 'round') {
      const skirt = new THREE.Mesh(cyl(17 * S, 17.5 * S, 0.006, 32), MAT.bakelite); skirt.position.z = plateZ + 0.003; grp.add(skirt);
      const body = new THREE.Mesh(cyl(13 * S, 14.5 * S, 0.022, 32), MAT.bakelite); body.position.z = plateZ + 0.015; grp.add(body);
      const ptr = new THREE.Mesh(new THREE.BoxGeometry(3 * S, 12 * S, 0.002), MAT.white); ptr.position.set(0, 7 * S, plateZ + 0.027); grp.add(ptr);
      body.castShadow = true; addPick(body, ci);
    } else {
      const cylB = new THREE.Mesh(cyl(13 * S, 13 * S, 0.012, 28), MAT.brass); cylB.position.z = plateZ + 0.006; grp.add(cylB);
      const ring = new THREE.Mesh(cyl(16 * S, 16 * S, 0.004, 28), MAT.bakelite); ring.position.z = plateZ + 0.002; grp.add(ring);
      const key = new THREE.Mesh(new THREE.BoxGeometry(8 * S, 30 * S, 0.004), MAT.chrome); key.position.set(0, 8 * S, plateZ + 0.03); grp.add(key);
      const shank = new THREE.Mesh(new THREE.BoxGeometry(4 * S, 4 * S, 0.02), MAT.chrome); shank.position.z = plateZ + 0.02; grp.add(shank);
      key.castShadow = true; addPick(key, ci); addPick(cylB, ci);
    }
    place(grp, info, r, 0); scene.add(grp);
    let last = null;
    parts.push({ update() {
      const m = /rotate\(([-\d.]+)deg\)/.exec(knob.style.transform || '');
      const a = m ? parseFloat(m[1]) : 0;
      if (a === last) return; last = a;
      grp.rotation.z = -a * Math.PI / 180;
    } });
  }
  function ringTextTexture() {
    const c = cv(256, 256), g = c.getContext('2d');
    const gr = g.createRadialGradient(100, 90, 10, 128, 128, 128); gr.addColorStop(0, '#fbe06a'); gr.addColorStop(0.6, '#e1b10c'); gr.addColorStop(1, '#a07c03');
    g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
    g.fillStyle = '#1f1800'; g.font = '700 19px "Barlow Condensed", "Arial Narrow", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    const txt = 'EMERGENCY STOP · NOT-AUS · EMERGENCY STOP · NOT-AUS · ';
    const R = 108; let a = -Math.PI / 2;
    for (const ch of txt) { const w = g.measureText(ch).width + 2.2; a += w / R / 2; g.save(); g.translate(128 + Math.cos(a) * R, 128 + Math.sin(a) * R); g.rotate(a + Math.PI / 2); g.fillText(ch, 0, 0); g.restore(); a += w / R / 2; }
    return texFrom(c);
  }
  function buildEstop(el, ci, info) {
    const r = rel(el, info.o), R = r.w / 2 * S;
    const grp = new THREE.Group();
    const plateG = cyl(R, R, 0.006, 48);
    const plate = new THREE.Mesh(plateG, [MAT.yellow, new THREE.MeshStandardMaterial({ map: ringTextTexture(), roughness: 0.45 }), MAT.yellow]);
    plate.position.z = 0.003; grp.add(plate);
    const stem = new THREE.Mesh(cyl(10 * S, 12 * S, 0.03, 24), MAT.bakelite); stem.position.z = 0.02; grp.add(stem);
    const mushM = new THREE.MeshStandardMaterial({ color: 0xd3200e, roughness: 0.22, envMapIntensity: 1.1 });
    const capG = new THREE.SphereGeometry(27 * S, 40, 16, 0, Math.PI * 2, 0, Math.PI * 0.42); capG.rotateX(Math.PI / 2); capG.scale(1, 1, 0.9);
    const cap = new THREE.Mesh(capG, mushM); grp.add(cap);
    const rim = new THREE.Mesh(cyl(27 * S * Math.sin(Math.PI * 0.42), 27 * S * Math.sin(Math.PI * 0.42), 0.012, 40), mushM); grp.add(rim);
    place(grp, info, r, 0); scene.add(grp);
    cap.castShadow = rim.castShadow = stem.castShadow = true;
    addPick(cap, ci); addPick(rim, ci); addPick(plate, ci);
    parts.push({ update() {
      const down = el.classList.contains('down');
      const zt = down ? 0.022 : 0.036;
      rim.position.z += (zt - rim.position.z) * 0.5;
      cap.position.z = rim.position.z - 27 * S * 0.9 * Math.cos(Math.PI * 0.42) + 0.006;
    } });
  }
  function buildDsw(el, ci, info) {
    const r = rel(el, info.o), R = r.w / 2 * S;
    const grp = new THREE.Group();
    const ring = new THREE.Mesh(cyl(R + 5 * S, R + 5 * S, 0.004, 40), MAT.grey); ring.position.z = 0.002; grp.add(ring);
    const base = new THREE.Mesh(cyl(R, R * 1.02, 0.014, 40), MAT.bakelite); base.position.z = 0.009; grp.add(base);
    const bar = new THREE.Group();
    const barM = new THREE.Mesh(new THREE.BoxGeometry(18 * S, 60 * S, 0.02), MAT.bakelite); barM.position.z = 0.026; bar.add(barM);
    const lampM = new THREE.MeshStandardMaterial({ color: 0x3a2c10, emissive: 0xffd36a, emissiveIntensity: 0, roughness: 0.3 });
    const lamp = new THREE.Mesh(new THREE.BoxGeometry(8 * S, 40 * S, 0.002), lampM); lamp.position.z = 0.0365; bar.add(lamp);
    grp.add(bar);
    place(grp, info, r, 0); scene.add(grp);
    barM.castShadow = true; addPick(barM, ci); addPick(base, ci);
    parts.push({ update() {
      const ang = el.classList.contains('open') ? -Math.PI / 2 : 0;
      bar.rotation.z += (ang - bar.rotation.z) * 0.35;
      bar.position.z = el.classList.contains('push') ? -0.006 : 0;
      lampM.emissiveIntensity = el.classList.contains('lamp-on') ? 2.2 : 0;
    } });
  }
  function buildLockout(lh, ci, info) {
    const r = rel(lh, info.o), R = r.w / 2 * S;
    const box = lh.closest('.lockout');
    const grp = new THREE.Group();
    const disc = new THREE.Mesh(cyl(R, R, 0.012, 40), MAT.grey); disc.position.z = 0.006; grp.add(disc);
    const arm = new THREE.Mesh(new THREE.BoxGeometry(22 * S, 74 * S, 0.026), MAT.bakelite); arm.position.z = 0.025; grp.add(arm);
    const ptr = new THREE.Mesh(new THREE.BoxGeometry(6 * S, 20 * S, 0.002), MAT.white); ptr.position.set(0, 21 * S, 0.0385); grp.add(ptr);
    place(grp, info, r, 0); scene.add(grp);
    arm.castShadow = true; addPick(arm, ci); addPick(disc, ci);
    const fl = box.querySelector('.lflag'), fr = rel(fl, info.o);
    const flagM = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.6 });
    const flag = place(new THREE.Mesh(new THREE.PlaneGeometry(fr.w * S, fr.h * S), flagM), info, fr, 0.0015); scene.add(flag);
    let last = null;
    parts.push({ update() {
      const t = box.classList.contains('tripped');
      grp.rotation.z += ((t ? -Math.PI / 4 : 0) - grp.rotation.z) * 0.35;
      if (t !== last) { last = t; flagM.color.setHex(t ? 0xf09a12 : 0x111111); flagM.emissive.setHex(t ? 0x553000 : 0); }
    } });
  }
  const stripeTex = (() => { let t; return () => {
    if (t) return t;
    const c = cv(64, 32), g = c.getContext('2d'); g.fillStyle = '#f8efe2'; g.fillRect(0, 0, 64, 32);
    g.fillStyle = '#f26a1b'; for (let x = -32; x < 64; x += 16) { g.beginPath(); g.moveTo(x, 32); g.lineTo(x + 8, 32); g.lineTo(x + 40, 0); g.lineTo(x + 32, 0); g.closePath(); g.fill(); }
    t = texFrom(c); return t;
  }; })();
  function buildRelay(el, ci, info) {
    const r = rel(el, info.o), d = 0.05;
    const o = el.getBoundingClientRect();
    const c = cv(r.w * T, r.h * T), g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 0, c.height); gr.addColorStop(0, '#34352f'); gr.addColorStop(1, '#1d1e1a');
    g.fillStyle = gr; g.fillRect(0, 0, c.width, c.height);
    const faceEl = el.querySelector('.face'), fr0 = rel(faceEl, o);
    g.fillStyle = '#e5dfcb'; rrect(g, fr0.x * T, fr0.y * T, fr0.w * T, fr0.h * T, 2 * T); g.fill();
    const vg = g.createLinearGradient(0, fr0.y * T, 0, (fr0.y + fr0.h) * T); vg.addColorStop(0, 'rgba(255,255,255,.12)'); vg.addColorStop(1, 'rgba(90,80,60,.12)');
    g.fillStyle = vg; g.fill();
    paintSubtree(g, faceEl, o, { skip: MESHY + ', .flag, .pu, .rst' });
    const flE = el.querySelector('.flag'), flr = rel(flE, o);
    g.fillStyle = '#111'; rrect(g, flr.x * T, flr.y * T, flr.w * T, flr.h * T, 2 * T); g.fill();
    const caseM = [MAT.relayCase, MAT.relayCase, MAT.relayCase, MAT.relayCase, new THREE.MeshStandardMaterial({ map: texFrom(c), roughness: 0.55 }), MAT.relayCase];
    const box = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S, r.h * S, d), caseM), info, r, d / 2); scene.add(box);
    box.castShadow = true; addPick(box, ci);
    const glass = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S * 0.97, r.h * S * 0.97, 0.008), MAT.glass), info, r, d + 0.006); scene.add(glass);
    const fr = rel(flE, info.o);
    const flagM = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.6 });
    const flag = place(new THREE.Mesh(new THREE.PlaneGeometry(fr.w * S * 0.86, fr.h * S * 0.7), flagM), info, fr, d + 0.0008); scene.add(flag);
    const puE = el.querySelector('.pu'), pr = rel(puE, info.o);
    const ledM = new THREE.MeshStandardMaterial({ color: 0x3a120e, emissive: 0xff3b23, emissiveIntensity: 0, roughness: 0.2 });
    const led = place(new THREE.Mesh(new THREE.SphereGeometry(pr.w / 2 * S, 12, 8), ledM), info, pr, d); scene.add(led);
    const rstE = el.querySelector('.rst'), rr = rel(rstE, info.o);
    const rst = place(new THREE.Mesh(cyl(rr.w / 2 * S, rr.w / 2 * S, 0.012, 20), MAT.bakelite), info, rr, d + 0.006); scene.add(rst);
    addPick(rst, ci);
    let disk = null;
    const dc = el.querySelector('.face canvas');
    if (dc) {
      const dr = rel(dc, info.o), dt = texFrom(dc);
      disk = { tex: dt };
      scene.add(place(new THREE.Mesh(new THREE.PlaneGeometry(dr.w * S, dr.h * S), new THREE.MeshBasicMaterial({ map: dt })), info, dr, d + 0.0009));
    }
    let lastOp = null, lastPu = null;
    parts.push({ update() {
      const op = el.classList.contains('op'), pu = puE.classList.contains('on');
      if (op !== lastOp) { lastOp = op; flagM.map = op ? stripeTex() : null; flagM.color.setHex(op ? 0xffffff : 0x111111); flagM.needsUpdate = true; }
      if (pu !== lastPu) { lastPu = pu; ledM.emissiveIntensity = pu ? 2.5 : 0; }
      if (disk && frameNo % 3 === 0) disk.tex.needsUpdate = true;
    } });
  }
  function buildAnnunciator(el, ci, info) {
    const r = rel(el, info.o), o = el.getBoundingClientRect(), d = 0.03;
    const c = cv(r.w * T, r.h * T), g = c.getContext('2d');
    const ce = cv(r.w * T, r.h * T), ge = ce.getContext('2d');
    const tex = texFrom(c), etex = texFrom(ce);
    const mat = new THREE.MeshStandardMaterial({ map: tex, emissiveMap: etex, emissive: 0xffffff, emissiveIntensity: 1.6, roughness: 0.35, envMapIntensity: 0.6 });
    const box = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S, r.h * S, d), [MAT.bezel, MAT.bezel, MAT.bezel, MAT.bezel, mat, MAT.bezel]), info, r, d / 2);
    scene.add(box); box.castShadow = true; addPick(box, ci);
    const dec = document.createElement('div');
    const lines = w => w.innerHTML.split(/<br\s*\/?>/i).map(h => { dec.innerHTML = h; return dec.textContent.trim(); }).filter(Boolean);
    const wins = [...el.querySelectorAll('.aw')].map(w => ({ w, r: rel(w, o), txt: lines(w) }));
    const COL = { red: ['#ffb39b', '#ff6a47', '#ff5030'], amb: ['#ffe2a0', '#ffc45c', '#ffb030'], wht: ['#ffffff', '#fff0cc', '#fff0d0'] };
    let sig = '';
    const draw = () => {
      g.fillStyle = '#191917'; g.fillRect(0, 0, c.width, c.height);
      ge.fillStyle = '#000'; ge.fillRect(0, 0, ce.width, ce.height);
      for (const { w, r: wr, txt } of wins) {
        const x = wr.x * T, y = wr.y * T, ww = wr.w * T, hh = wr.h * T;
        const lit = w.classList.contains('lit');
        const col = w.classList.contains('red') ? COL.red : w.classList.contains('amb') ? COL.amb : COL.wht;
        if (lit) {
          const gr = g.createRadialGradient(x + ww / 2, y + hh / 2, 2, x + ww / 2, y + hh / 2, ww * 0.6);
          gr.addColorStop(0, col[0]); gr.addColorStop(1, col[1]);
          g.fillStyle = gr; g.fillRect(x, y, ww, hh);
          const ge2 = ge.createRadialGradient(x + ww / 2, y + hh / 2, 2, x + ww / 2, y + hh / 2, ww * 0.6);
          ge2.addColorStop(0, col[0]); ge2.addColorStop(1, col[2]);
          ge.fillStyle = ge2; ge.fillRect(x, y, ww, hh);
        } else {
          const gr = g.createLinearGradient(0, y, 0, y + hh); gr.addColorStop(0, '#dad7ca'); gr.addColorStop(1, '#b6b3a6');
          g.fillStyle = gr; g.fillRect(x, y, ww, hh);
        }
        g.strokeStyle = 'rgba(0,0,0,.4)'; g.lineWidth = T; g.strokeRect(x + 0.5, y + 0.5, ww - 1, hh - 1);
        g.fillStyle = lit ? '#2b0a00' : '#2a2a26'; g.font = `700 ${9 * T}px "Barlow Condensed", "Arial Narrow", sans-serif`;
        g.textAlign = 'center'; g.textBaseline = 'middle';
        try { g.letterSpacing = 0.45 * T + 'px'; } catch (e) { /* noop */ }
        txt.forEach((s, i) => g.fillText(s.toUpperCase(), x + ww / 2, y + hh / 2 + (i - (txt.length - 1) / 2) * 9.6 * T));
        try { g.letterSpacing = '0px'; } catch (e) { /* noop */ }
      }
      tex.needsUpdate = etex.needsUpdate = true;
    };
    parts.push({ update() {
      let s = ''; for (const { w } of wins) s += w.classList.contains('lit') ? '1' : '0';
      if (s !== sig) { sig = s; draw(); }
    } });
  }
  function buildPrinter(el, ci, info) {
    const r = rel(el, info.o), o = el.getBoundingClientRect(), d = 0.035;
    const base = cv(r.w * T, r.h * T), gb = base.getContext('2d');
    const gr = gb.createLinearGradient(0, 0, 0, base.height); gr.addColorStop(0, '#ddd5bf'); gr.addColorStop(1, '#bdb39a');
    gb.fillStyle = gr; gb.fillRect(0, 0, base.width, base.height);
    const head = el.querySelector('.head'), hr = rel(head, o);
    gb.fillStyle = '#2f2e29'; rrect(gb, hr.x * T, hr.y * T, hr.w * T, hr.h * T, 3 * T); gb.fill();
    paintSubtree(gb, el, o, { skip: MESHY + ', .paper, .head' });
    const paper = el.querySelector('.paper'), pr = rel(paper, o);
    const c = cv(base.width, base.height), g = c.getContext('2d');
    const tex = texFrom(c);
    const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.75 });
    const box = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S, r.h * S, d), [MAT.beige, MAT.beige, MAT.beige, MAT.beige, mat, MAT.beige]), info, r, d / 2);
    scene.add(box); box.castShadow = true; addPick(box, ci);
    let sig = '';
    const draw = () => {
      g.drawImage(base, 0, 0);
      g.fillStyle = '#f5f4ee'; g.fillRect(pr.x * T, pr.y * T, pr.w * T, pr.h * T);
      const lines = [...paper.querySelectorAll('.ln')];
      g.save(); g.beginPath(); g.rect(pr.x * T, pr.y * T, pr.w * T, pr.h * T); g.clip();
      const lh = 14 * T; let y = (pr.y + pr.h) * T - lh;
      for (let i = lines.length - 1; i >= 0 && y > pr.y * T - lh; i--, y -= lh) {
        const ln = lines[i];
        if (i % 6 < 3) { g.fillStyle = 'rgba(120,190,130,.18)'; g.fillRect(pr.x * T, y, pr.w * T, lh); }
        g.fillStyle = ln.classList.contains('trip') ? '#b0150b' : ln.classList.contains('alarm') ? '#8a1a12' : '#2b2a3c';
        g.font = `400 ${14 * T}px VT323, "Courier New", monospace`; g.textBaseline = 'middle'; g.textAlign = 'left';
        g.fillText(ln.textContent, (pr.x + 16) * T, y + lh / 2);
      }
      for (const xx of [pr.x + 6, pr.x + pr.w - 6]) for (let yy = pr.y + 8; yy < pr.y + pr.h; yy += 14) { g.fillStyle = '#9b978b'; g.beginPath(); g.arc(xx * T, yy * T, 2.5 * T, 0, 7); g.fill(); }
      g.restore();
      const sh = g.createLinearGradient(0, (pr.y + pr.h - 10) * T, 0, (pr.y + pr.h) * T); sh.addColorStop(0, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,0,.25)');
      g.fillStyle = sh; g.fillRect(pr.x * T, (pr.y + pr.h - 10) * T, pr.w * T, 10 * T);
      tex.needsUpdate = true;
    };
    parts.push({ update() {
      const last = paper.lastElementChild;
      const s = paper.childElementCount + ':' + (last ? last.textContent : '');
      if (s !== sig) { sig = s; draw(); }
    } });
  }
  function buildCounter(el, ci, info) {
    const r = rel(el, info.o), d = 0.012;
    const digits = [...el.querySelectorAll('.d')];
    const c = cv(r.w * 3, r.h * 3), g = c.getContext('2d');
    const tex = texFrom(c);
    const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.4 });
    const box = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S, r.h * S, d), [MAT.bezel, MAT.bezel, MAT.bezel, MAT.bezel, mat, MAT.bezel]), info, r, d / 2);
    scene.add(box); box.castShadow = true;
    const o = el.getBoundingClientRect();
    const drs = digits.map(dg => ({ dg, r: rel(dg, o), red: dg.classList.contains('r'), strip: dg.querySelector('.s') }));
    const blk = el.classList.contains('blk');
    let sig = '';
    parts.push({ update() {
      const s = drs.map(x => x.strip.style.transform).join('|');
      if (s === sig) return; sig = s;
      g.fillStyle = '#0d0d0d'; g.fillRect(0, 0, c.width, c.height);
      for (const x of drs) {
        const m = /translateY\(([-\d.]+)px\)/.exec(x.strip.style.transform || ''); const pos = m ? -parseFloat(m[1]) / 17 : 0;
        const X = x.r.x * 3, Y = x.r.y * 3, Wd = x.r.w * 3, Hd = x.r.h * 3;
        g.save(); g.beginPath(); g.rect(X, Y, Wd, Hd); g.clip();
        g.fillStyle = x.red ? '#c3271b' : blk ? '#1a1a1a' : '#f4f2ea'; g.fillRect(X, Y, Wd, Hd);
        g.fillStyle = x.red ? '#fff' : blk ? '#f3f1e8' : '#111'; g.font = `500 ${13 * 3}px Jost, Futura, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
        const b = Math.floor(pos), fr = pos - b;
        g.fillText(String(((b % 10) + 10) % 10), X + Wd / 2, Y + Hd / 2 - fr * Hd);
        g.fillText(String((((b + 1) % 10) + 10) % 10), X + Wd / 2, Y + Hd / 2 + Hd - fr * Hd);
        const sh = g.createLinearGradient(0, Y, 0, Y + Hd); sh.addColorStop(0, 'rgba(0,0,0,.5)'); sh.addColorStop(0.3, 'rgba(0,0,0,0)'); sh.addColorStop(0.7, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,0,.5)');
        g.fillStyle = sh; g.fillRect(X, Y, Wd, Hd); g.restore();
      }
      tex.needsUpdate = true;
    } });
  }
  function buildMeter(m, ci, info) {
    const cEl = m.c;
    const isRec = !!cEl.closest('.rec');
    const host = isRec ? cEl.closest('.rec') : cEl;
    const r = rel(host, info.o), cr = rel(cEl, info.o);
    const kind = m.o && m.o.kind;
    const round = kind === 'round' || kind === 'sync' || cEl.classList.contains('clockbox');
    const depth = round ? (kind === 'round' ? 0.06 : 0.055) : isRec ? 0.07 : m.disc !== undefined ? 0.06 : 0.045;
    const tex = texFrom(cEl);
    const faceM = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.45, metalness: 0, envMapIntensity: 0.3 });
    let body, face, glass;
    if (round) {
      const R = r.w / 2 * S;
      body = place(new THREE.Mesh(cyl(R, R * 1.02, depth, 48), kind === 'round' ? MAT.chrome : MAT.bezel), info, r, depth / 2);
      face = place(new THREE.Mesh(new THREE.CircleGeometry(R, 48), faceM), info, r, depth + 0.0006);
      glass = place(new THREE.Mesh(new THREE.CircleGeometry(R * 0.9, 48), MAT.glass), info, r, depth + 0.004);
    } else {
      body = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S, r.h * S, depth), MAT.bezel), info, r, depth / 2);
      face = place(new THREE.Mesh(new THREE.PlaneGeometry(cr.w * S, cr.h * S), faceM), info, cr, depth + 0.0006);
      glass = place(new THREE.Mesh(new THREE.PlaneGeometry(cr.w * S * 0.86, cr.h * S * 0.86), MAT.glass), info, cr, depth + 0.003);
    }
    scene.add(body, face, glass);
    body.castShadow = true; body.receiveShadow = true;
    addPick(body, ci); addPick(face, ci);
    face.geometry.computeBoundingSphere();
    meterTex.push({ m, tex, mesh: face, pos: new THREE.Vector3().copy(face.position) });
  }
  function buildHandle(el, ci, info) {
    const r = rel(el, info.o), d = 0.04;
    const h = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S, r.h * S, d), MAT.bakelite), info, r, d / 2); scene.add(h); h.castShadow = true;
    const base = place(new THREE.Mesh(new THREE.BoxGeometry(r.w * S * 1.3, r.h * S * 0.35, 0.012), MAT.chrome), info, r, 0.006); base.position.y += r.h * S * 0.32; scene.add(base);
    const lk = place(new THREE.Mesh(cyl(4.5 * S, 4.5 * S, 0.006, 16), MAT.brass), info, r, d + 0.003); lk.position.y += r.h * S * 0.38; scene.add(lk);
  }

  /* --------------------------------------------------------- the room */
  function canvasTex(w, h, draw, rep) { const c = cv(w, h); draw(c.getContext('2d'), w, h); const t = texFrom(c); if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); } return t; }
  function buildRoom() {
    const L = rowLen, X0 = -2.4, X1 = L + 2.4, ZB = -DEPTH - 0.03, ZF = 5.6, HC = 3.25;
    const W = X1 - X0, Dp = ZF - ZB;
    // lino floor, 0.3 m tiles
    const floorT = canvasTex(512, 512, (g, w, h) => {
      g.fillStyle = '#3a332b'; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 9000; i++) { g.fillStyle = `rgba(${Math.random() < 0.5 ? '255,250,235' : '0,0,0'},${(Math.random() * 0.06).toFixed(3)})`; g.fillRect(Math.random() * w, Math.random() * h, 2 + Math.random() * 3, 1 + Math.random() * 2); }
      for (const [x, y] of [[0, 0], [256, 0], [0, 256], [256, 256]]) { g.fillStyle = `rgba(0,0,0,${(Math.random() * 0.08).toFixed(3)})`; g.fillRect(x, y, 256, 256); }
      g.strokeStyle = 'rgba(0,0,0,.45)'; g.lineWidth = 2; for (const p of [0, 256]) { g.beginPath(); g.moveTo(p, 0); g.lineTo(p, h); g.stroke(); g.beginPath(); g.moveTo(0, p); g.lineTo(w, p); g.stroke(); }
    }, [W / 0.6, Dp / 0.6]);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, Dp), new THREE.MeshStandardMaterial({ map: floorT, roughness: 0.55, metalness: 0, envMapIntensity: 0.35 }));
    floor.rotation.x = -Math.PI / 2; floor.position.set((X0 + X1) / 2, 0, (ZB + ZF) / 2); floor.receiveShadow = true; scene.add(floor);
    // cable trench cover plates (chequer plate) right in front of the cabinets
    const cheq = canvasTex(256, 256, (g, w, h) => {
      g.fillStyle = '#7d7f7c'; g.fillRect(0, 0, w, h);
      for (let y = 0; y < h; y += 32) for (let x = 0; x < w; x += 32) for (const [dx, dy, a] of [[8, 8, 0.7], [24, 24, -0.7]]) {
        g.save(); g.translate(x + dx, y + dy); g.rotate(a); g.fillStyle = '#a3a5a1'; g.fillRect(-7, -2, 14, 4); g.fillStyle = '#5a5c59'; g.fillRect(-7, 1.5, 14, 1); g.restore();
      }
    }, [L / 0.25, 0.55 / 0.25]);
    const trench = new THREE.Mesh(new THREE.PlaneGeometry(L, 0.55), new THREE.MeshStandardMaterial({ map: cheq, roughness: 0.45, metalness: 0.8, envMapIntensity: 0.6 }));
    trench.rotation.x = -Math.PI / 2; trench.position.set(L / 2, 0.002, 0.33); trench.receiveShadow = true; scene.add(trench);
    for (let x = 0; x <= L; x += 1.0) {
      const seam = new THREE.Mesh(new THREE.PlaneGeometry(0.006, 0.55), new THREE.MeshBasicMaterial({ color: 0x1a1a19 }));
      seam.rotation.x = -Math.PI / 2; seam.position.set(x, 0.003, 0.33); scene.add(seam);
    }
    // black rubber safety mat in front of the panels
    const ribs = canvasTex(64, 64, (g, w, h) => { g.fillStyle = '#151515'; g.fillRect(0, 0, w, h); for (let y = 0; y < h; y += 8) { g.fillStyle = '#262625'; g.fillRect(0, y, w, 3); } }, [L / 0.05, 0.9 / 0.05]);
    const mat = new THREE.Mesh(new THREE.BoxGeometry(L - 0.2, 0.006, 0.9), new THREE.MeshStandardMaterial({ map: ribs, roughness: 0.9 }));
    mat.position.set(L / 2, 0.003, 1.1); mat.receiveShadow = true; scene.add(mat);
    // walls (painted, darker dado), skirting
    const wallT = canvasTex(256, 256, (g, w, h) => {
      g.fillStyle = '#6a7361'; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 4000; i++) { g.fillStyle = `rgba(${Math.random() < 0.5 ? '255,255,255' : '0,0,0'},${(Math.random() * 0.04).toFixed(3)})`; g.fillRect(Math.random() * w, Math.random() * h, 2, 2); }
    }, [W / 1.2, HC / 1.2]);
    const wallM = new THREE.MeshStandardMaterial({ map: wallT, roughness: 0.9, envMapIntensity: 0.2 });
    const back = new THREE.Mesh(new THREE.PlaneGeometry(W, HC), wallM); back.position.set((X0 + X1) / 2, HC / 2, ZB); back.receiveShadow = true; scene.add(back);
    const left = new THREE.Mesh(new THREE.PlaneGeometry(Dp, HC), wallM); left.rotation.y = Math.PI / 2; left.position.set(X0, HC / 2, (ZB + ZF) / 2); left.receiveShadow = true; scene.add(left);
    const right = new THREE.Mesh(new THREE.PlaneGeometry(Dp, HC), wallM); right.rotation.y = -Math.PI / 2; right.position.set(X1, HC / 2, (ZB + ZF) / 2); right.receiveShadow = true; scene.add(right);
    const front = new THREE.Mesh(new THREE.PlaneGeometry(W, HC), wallM); front.rotation.y = Math.PI; front.position.set((X0 + X1) / 2, HC / 2, ZF); scene.add(front);
    const skM = new THREE.MeshStandardMaterial({ color: 0x2f2924, roughness: 0.7 });
    for (const [w, x, z, ry] of [[W, (X0 + X1) / 2, ZB + 0.008, 0], [Dp, X0 + 0.008, (ZB + ZF) / 2, Math.PI / 2], [Dp, X1 - 0.008, (ZB + ZF) / 2, -Math.PI / 2]]) {
      const sk = new THREE.Mesh(new THREE.BoxGeometry(w, 0.1, 0.016), skM); sk.position.set(x, 0.05, z); sk.rotation.y = ry; scene.add(sk);
    }
    // ceiling: acoustic tiles and fluorescent fittings
    const ceilT = canvasTex(256, 256, (g, w, h) => {
      g.fillStyle = '#d9d6cc'; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 2500; i++) { g.fillStyle = 'rgba(80,75,65,.18)'; g.fillRect(Math.random() * w, Math.random() * h, 1.5, 1.5); }
      g.strokeStyle = '#a8a59b'; g.lineWidth = 4; g.strokeRect(0, 0, w, h);
    }, [W / 0.6, Dp / 0.6]);
    const ceil = new THREE.Mesh(new THREE.PlaneGeometry(W, Dp), new THREE.MeshStandardMaterial({ map: ceilT, roughness: 0.95 }));
    ceil.rotation.x = Math.PI / 2; ceil.position.set((X0 + X1) / 2, HC, (ZB + ZF) / 2); scene.add(ceil);
    const tubeM = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff6e2, emissiveIntensity: 2.2, roughness: 0.4 });
    const housingM = new THREE.MeshStandardMaterial({ color: 0xe8e6de, roughness: 0.5, metalness: 0.3 });
    for (let x = X0 + 1.2; x < X1 - 0.6; x += 1.9) for (const z of [0.9, 3.0]) {
      const hsg = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.06, 0.24), housingM); hsg.position.set(x, HC - 0.03, z); scene.add(hsg);
      for (const dz of [-0.05, 0.05]) { const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 1.22, 12), tubeM); tube.rotation.z = Math.PI / 2; tube.position.set(x, HC - 0.075, z + dz); scene.add(tube); }
    }
    // lighting
    scene.add(new THREE.HemisphereLight(0xfff4e0, 0x2a2622, 0.32));
    scene.add(new THREE.AmbientLight(0xfff8ee, 0.05));
    for (let x = X0 + 1.2; x < X1 - 0.6; x += 3.8) {
      const pl = new THREE.PointLight(0xfff3dd, 0.45, 9, 2); pl.position.set(x, HC - 0.2, 1.4); scene.add(pl);
    }
    const key = new THREE.SpotLight(0xfff2dc, 1.15, 14, 1.15, 0.65, 1.2);
    key.position.set(L / 2, HC - 0.1, 2.6); key.target.position.set(L / 2, 1.05, -0.1);
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.015;
    key.shadow.camera.near = 0.5; key.shadow.camera.far = 9;
    scene.add(key, key.target);
    const fill = new THREE.DirectionalLight(0xffeedd, 0.25); fill.position.set(-2, 2.6, 4); scene.add(fill);
    ROOMB = { X0, X1, ZF };
  }
  let ROOMB = { X0: -2, X1: 10, ZF: 5 };
  function environment() {
    const pm = new THREE.PMREMGenerator(renderer);
    const env = new THREE.Scene();
    const roomG = new THREE.BoxGeometry(12, 4, 10); roomG.translate(0, 1.5, 0);
    env.add(new THREE.Mesh(roomG, new THREE.MeshBasicMaterial({ color: 0x3c4236, side: THREE.BackSide })));
    for (const [x, z] of [[-3, -1], [0, -1], [3, -1], [-3, 2], [0, 2], [3, 2]]) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 0.25), new THREE.MeshBasicMaterial({ color: 0xffffff })); p.rotation.x = Math.PI / 2; p.position.set(x, 3.45, z);
      p.material.color.setScalar(6); env.add(p);
    }
    const fl = new THREE.Mesh(new THREE.PlaneGeometry(12, 10), new THREE.MeshBasicMaterial({ color: 0x241f1a })); fl.rotation.x = -Math.PI / 2; fl.position.y = -0.49; env.add(fl);
    scene.environment = pm.fromScene(env, 0.035).texture;
    pm.dispose();
  }

  /* ------------------------------------------------------ cabinets */
  function buildCabinets() {
    const base = cabs[0].getBoundingClientRect();
    cabs.forEach((cab, ci) => {
      const o = cab.getBoundingClientRect();
      const door = cab.querySelector('.door'), plinth = cab.querySelector('.plinth');
      const plr = plinth.getBoundingClientRect();
      const info = { o, x0: (o.left - base.left) * S, h: o.height * S, w: o.width * S };
      const plH = plr.height * S;
      const front = paintCabFront(cab, door, plinth);
      const bodyH = front.H * S;
      const frontM = new THREE.MeshStandardMaterial({ map: front.tex, roughness: 0.58, metalness: 0.08, envMapIntensity: 0.45 });
      const body = new THREE.Mesh(new THREE.BoxGeometry(info.w, bodyH, DEPTH), [MAT.steelDark, MAT.steelDark, MAT.steel, MAT.steel, frontM, MAT.steelDark]);
      body.position.set(info.x0 + info.w / 2, plH + bodyH / 2, -DEPTH / 2);
      body.castShadow = true; body.receiveShadow = true; scene.add(body); addPick(body, ci);
      const pm = new THREE.MeshStandardMaterial({ map: paintPlinth(plinth), roughness: 0.8 });
      const pb = new THREE.Mesh(new THREE.BoxGeometry(info.w - 0.02, plH, DEPTH - 0.04), [MAT.plinth, MAT.plinth, MAT.plinth, MAT.plinth, pm, MAT.plinth]);
      pb.position.set(info.x0 + info.w / 2, plH / 2, -DEPTH / 2 - 0.02); pb.receiveShadow = true; scene.add(pb);
      // roof lip and lifting eyes
      const lip = new THREE.Mesh(new THREE.BoxGeometry(info.w + 0.01, 0.012, DEPTH + 0.01), MAT.steel); lip.position.set(info.x0 + info.w / 2, info.h + 0.006, -DEPTH / 2); lip.castShadow = true; scene.add(lip);
      for (const fx of [0.06, info.w - 0.06]) for (const fz of [-0.08, -DEPTH + 0.08]) {
        const eye = new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.007, 8, 18, Math.PI), MAT.steelDark); eye.position.set(info.x0 + fx, info.h + 0.012, fz); scene.add(eye);
      }
      const hs = [];
      cab.querySelectorAll('.pb, .rot .hit, .dsw, .estop, .lockout .lh, .relay .rst, .card').forEach(el => { const r = rel(el, o); hs.push({ el, ...r }); });
      hits[ci] = { info, hs };
      // parts
      door.querySelectorAll('.lamp').forEach(el => buildLamp(el, ci, info));
      door.querySelectorAll('.pb').forEach(el => buildButton(el, ci, info));
      door.querySelectorAll('.rot').forEach(el => buildKnob(el, ci, info));
      door.querySelectorAll('.estop').forEach(el => buildEstop(el, ci, info));
      door.querySelectorAll('.dsw').forEach(el => buildDsw(el, ci, info));
      door.querySelectorAll('.lockout .lh').forEach(el => buildLockout(el, ci, info));
      door.querySelectorAll('.relay').forEach(el => buildRelay(el, ci, info));
      door.querySelectorAll('.ann').forEach(el => buildAnnunciator(el, ci, info));
      door.querySelectorAll('.printer').forEach(el => buildPrinter(el, ci, info));
      door.querySelectorAll('.ctr').forEach(el => buildCounter(el, ci, info));
      door.querySelectorAll('.handle').forEach(el => buildHandle(el, ci, info));
      U.METERS.forEach(m => { if (m.c && door.contains(m.c)) buildMeter(m, ci, info); });
    });
    const last = cabs[cabs.length - 1].getBoundingClientRect();
    rowLen = (last.right - base.left) * S;
  }

  /* ---------------------------------------------------- camera + input */
  let raycaster, ndc, glEl, held = null, drag = null, lastClick = 0;
  function clampCam() {
    ctl.x = Math.max(ROOMB.X0 + 0.4, Math.min(ROOMB.X1 - 0.4, ctl.x));
    ctl.z = Math.max(0.42, Math.min(ROOMB.ZF - 0.4, ctl.z));
    ctl.pitch = Math.max(-0.9, Math.min(0.6, ctl.pitch));
  }
  function applyCam() {
    camera.position.set(ctl.x, EYE, ctl.z);
    const d = new THREE.Vector3(Math.sin(ctl.yaw) * Math.cos(ctl.pitch), Math.sin(ctl.pitch), -Math.cos(ctl.yaw) * Math.cos(ctl.pitch));
    camera.lookAt(camera.position.clone().add(d));
  }
  function walkTo(x, z, yaw = 0, pitch = -0.12) { ctl.tx = x; ctl.tz = z; ctl.tyaw = yaw; ctl.tpitch = pitch; }
  function cabCenter(i) { const h = hits[i]; return h ? h.info.x0 + h.info.w / 2 : 0; }
  function hitTest(e) {
    const r = glEl.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const hs = raycaster.intersectObjects(pick, false);
    if (!hs.length) return null;
    const h = hs[0], ci = h.object.userData.cab, cab = hits[ci];
    if (!cab) return { point: h.point };
    const px = (h.point.x - cab.info.x0) / S, py = (cab.info.h - h.point.y) / S;
    let best = null;
    for (const t of cab.hs) if (px >= t.x && px <= t.x + t.w && py >= t.y && py <= t.y + t.h) { if (!best || t.w * t.h < best.w * best.h) best = t; }
    return { point: h.point, el: best && best.el, ci };
  }
  function fire(el, type) {
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, button: 0, buttons: type === 'pointerdown' ? 1 : 0, pointerType: 'mouse', isPrimary: true }));
  }
  function bindInput() {
    glEl.addEventListener('contextmenu', e => e.preventDefault());
    glEl.addEventListener('pointerdown', e => {
      glEl.setPointerCapture(e.pointerId);
      const h = e.button === 0 ? hitTest(e) : null;
      if (h && h.el) { held = h.el; fire(held, 'pointerdown'); return; }
      drag = { x: e.clientX, y: e.clientY, yaw: ctl.yaw, pitch: ctl.pitch, cx: ctl.x, cz: ctl.z, move: e.button === 2 || e.shiftKey, moved: 0 };
      ctl.tx = ctl.tz = ctl.tyaw = ctl.tpitch = null;
    });
    glEl.addEventListener('pointermove', e => {
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved = Math.max(drag.moved, Math.abs(dx) + Math.abs(dy));
        if (drag.move) {
          const k = 0.004;
          ctl.x = drag.cx - (Math.cos(ctl.yaw) * dx) * k; ctl.z = drag.cz - (Math.sin(ctl.yaw) * dx) * k + (dy * k * 0);
        } else {
          ctl.yaw = drag.yaw - dx * 0.0042; ctl.pitch = drag.pitch + dy * 0.0035;
        }
        clampCam(); return;
      }
      const h = hitTest(e);
      glEl.style.cursor = h && h.el ? 'pointer' : 'grab';
    });
    const up = e => {
      if (held) { fire(held, 'pointerup'); if (held.matches('.card')) held.click(); held = null; }
      if (drag && drag.moved < 4 && e.type === 'pointerup') {
        const now = performance.now();
        if (now - lastClick < 330) {                       // double-click: step up to that spot
          const h = hitTest(e);
          if (h && h.point && h.point.z < 0.2 && h.point.y > 0.2) walkTo(h.point.x, 0.95, 0, Math.atan2(h.point.y - EYE, 0.95 - h.point.z) * 0.9);
          else walkTo(ctl.x, 2.4, 0, -0.12);
        }
        lastClick = now;
      }
      drag = null;
    };
    glEl.addEventListener('pointerup', up); glEl.addEventListener('pointercancel', up);
    glEl.addEventListener('wheel', e => {
      e.preventDefault();
      const k = (e.deltaMode === 1 ? 0.06 : 0.0016) * e.deltaY;
      ctl.x += Math.sin(ctl.yaw) * -k; ctl.z += -Math.cos(ctl.yaw) * -k;
      ctl.tx = ctl.tz = null; clampCam();
    }, { passive: false });
    window.addEventListener('keydown', e => { if (!active || e.target.closest && e.target.closest('input,textarea')) return; ctl.keys[e.key.toLowerCase()] = true; });
    window.addEventListener('keyup', e => { ctl.keys[e.key.toLowerCase()] = false; });
    window.addEventListener('resize', resize);
  }
  function resize() {
    if (!renderer) return;
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false); glEl.style.width = w + 'px'; glEl.style.height = h + 'px';
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  function controls(dt) {
    const k = ctl.keys, sp = (k.shift ? 2.6 : 1.3) * dt;
    let fx = 0, fz = 0;
    if (k.w || k.arrowup) fz += 1; if (k.s || k.arrowdown) fz -= 1;
    if (k.d || k.arrowright) fx += 1; if (k.a || k.arrowleft) fx -= 1;
    if (fx || fz) {
      ctl.tx = ctl.tz = null;
      ctl.x += (Math.sin(ctl.yaw) * fz + Math.cos(ctl.yaw) * fx) * sp;
      ctl.z += (-Math.cos(ctl.yaw) * fz + Math.sin(ctl.yaw) * fx) * sp;
    }
    const e = 1 - Math.exp(-dt * 4.5);
    if (ctl.tx !== null) { ctl.x += (ctl.tx - ctl.x) * e; ctl.z += (ctl.tz - ctl.z) * e; if (Math.abs(ctl.tx - ctl.x) + Math.abs(ctl.tz - ctl.z) < 0.002) ctl.tx = ctl.tz = null; }
    if (ctl.tyaw !== null) { ctl.yaw += (ctl.tyaw - ctl.yaw) * e; ctl.pitch += (ctl.tpitch - ctl.pitch) * e; if (Math.abs(ctl.tyaw - ctl.yaw) + Math.abs(ctl.tpitch - ctl.pitch) < 0.001) ctl.tyaw = ctl.tpitch = null; }
    clampCam(); applyCam();
  }

  /* ------------------------------------------------------------ frame */
  let frustum, projM, fpsN = 0, fpsT = 0;
  function frame(dt) {
    if (!active) return;
    frameNo++;
    controls(dt);
    for (const p of parts) p.update(dt);
    // meter faces: everything in view at 30 Hz, the ones close by every frame
    projM.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse); frustum.setFromProjectionMatrix(projM);
    for (const mt of meterTex) {
      if (!frustum.containsPoint(mt.pos)) continue;
      const near = mt.pos.distanceTo(camera.position) < 2.2;
      if (near || (frameNo + mt.m.rseed) % 2 === 0) mt.tex.needsUpdate = true;
    }
    renderer.render(scene, camera);
    // quality governor
    fpsN++; fpsT += dt;
    if (fpsT > 2.5) {
      const fps = fpsN / fpsT; fpsN = 0; fpsT = 0;
      if (fps < 26 && quality > 0) {
        quality--;
        if (quality === 1) { renderer.shadowMap.enabled = false; scene.traverse(o => { if (o.material) [].concat(o.material).forEach(m => { m.needsUpdate = true; }); }); }
        renderer.setPixelRatio(quality === 1 ? 1 : 0.75); resize();
      }
    }
  }

  /* ----------------------------------------------------------- start */
  function available() {
    if (!window.THREE) return false;
    try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
  }
  async function start(ctx) {
    THREE = window.THREE; U = ctx; lineup = ctx.lineup;
    cabs = [...lineup.querySelectorAll('.cab')];
    // let the web fonts arrive before painting labels into textures
    // let the web fonts arrive before labels are painted into textures (bounded wait)
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const link = document.querySelector('link[href*="fonts.googleapis"]');
    const t0 = performance.now();
    while (link && link.media !== 'all' && performance.now() - t0 < 2500) await wait(60);
    if (document.fonts) {
      const faces = ['600 12px "Barlow Condensed"', '700 12px "Barlow Condensed"', '500 12px "Barlow Condensed"', '500 16px Caveat', '400 14px VT323', '500 12px Jost'];
      await Promise.race([Promise.all(faces.map(f => document.fonts.load(f).catch(() => null))), wait(2500)]);
    }
    glEl = document.createElement('canvas'); glEl.id = 'gl'; document.body.prepend(glEl);
    renderer = new THREE.WebGLRenderer({ canvas: glEl, antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(1.5, window.devicePixelRatio || 1));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.92;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.physicallyCorrectLights = false;
    scene = new THREE.Scene(); scene.background = new THREE.Color(0x1d201b);
    camera = new THREE.PerspectiveCamera(52, window.innerWidth / window.innerHeight, 0.05, 40);
    raycaster = new THREE.Raycaster(); ndc = new THREE.Vector2();
    frustum = new THREE.Frustum(); projM = new THREE.Matrix4();
    const tb = performance.now();
    materials();
    environment();
    buildCabinets();
    buildRoom();
    renderer.compile(scene, camera);
    console.info(`VIEW3D built in ${Math.round(performance.now() - tb)} ms (${pick.length} pickable, ${parts.length} parts)`);
    const c0 = cabCenter(0), c1 = cabCenter(1);
    ctl.x = (c0 + c1) / 2 - 0.2; ctl.z = 2.5; ctl.yaw = 0.18; ctl.pitch = -0.13;
    applyCam(); resize(); bindInput();
    active = true;
    return true;
  }
  function stop() { active = false; if (glEl) glEl.style.display = 'none'; }
  function resume() { active = true; if (glEl) glEl.style.display = ''; resize(); }
  return {
    available, start, frame, stop, resume,
    get active() { return active; },
    screenOf(el) {            // debug/test helper: where a DOM control appears on screen
      const cab = el.closest('.cab'), ci = cabs.indexOf(cab), info = hits[ci] && hits[ci].info; if (!info) return null;
      const r = rel(el, info.o), v = new THREE.Vector3(info.x0 + (r.x + r.w / 2) * S, info.h - (r.y + r.h / 2) * S, 0.03).project(camera);
      return { x: (v.x + 1) / 2 * window.innerWidth, y: (1 - v.y) / 2 * window.innerHeight };
    },
    walkToCab(i) { walkTo(cabCenter(i), 1.45, 0, -0.1); },
    dolly(d) { ctl.tx = ctl.tz = null; ctl.x += Math.sin(ctl.yaw) * d; ctl.z -= Math.cos(ctl.yaw) * d; clampCam(); },
    home() { walkTo(ctl.x, 2.4, 0, -0.12); },
  };
})();
