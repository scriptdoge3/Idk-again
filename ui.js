'use strict';
/* =====================================================================
   MÜHLBACH HYDRO · UNIT 1 · CONTROL CABINETS
   Panel hardware (meters, lamps, cam switches, relays, recorder,
   printer, sound) and wiring to the plant model in sim.js.
   ===================================================================== */
(() => {
  const PL = window.PLANT, P = PL.P;
  const clamp = (x, a, b) => x < a ? a : x > b ? b : x;
  const D2R = Math.PI / 180;
  const FN = '"Jost", "Futura", "Century Gothic", sans-serif';
  const FL = '"Barlow Condensed", "Arial Narrow", Arial, sans-serif';
  let ZOOM = 1;
  const DPR = Math.min(2, window.devicePixelRatio || 1);
  const kscale = () => Math.min(3.2, Math.max(1, DPR * ZOOM));
  const UPD = [];              // per-frame binders
  const METERS = [];
  const FLASH = { fast: false, slow: false };
  let TIMEACC = 1, EFFACC = 1, AUTOFF = true;

  function el(tag, cls, parent, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  }
  function tag(parent, text, cls = '') { return el('span', 'tag ' + cls, parent, text); }

  /* ===================================================================
     SOUND  (Web Audio: machine hum, water, pumps, relays, horn, printer)
     =================================================================== */
  const AU = {
    on: false, ctx: null, nodes: {},
    init() {
      if (this.ctx) return;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      const c = this.ctx = new AC();
      const m = this.master = c.createGain(); m.gain.value = 0; m.connect(c.destination);
      const nb = c.createBuffer(1, c.sampleRate * 2, c.sampleRate);
      const d = nb.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      this.noiseBuf = nb;
      const noise = () => { const s = c.createBufferSource(); s.buffer = nb; s.loop = true; s.start(); return s; };
      const N = this.nodes;
      // generator / transformer magnetostriction hum
      N.hum = c.createGain(); N.hum.gain.value = 0; N.hum.connect(m);
      N.o100 = c.createOscillator(); N.o100.type = 'sine'; N.o100.frequency.value = 100;
      N.o50 = c.createOscillator(); N.o50.type = 'sawtooth'; N.o50.frequency.value = 50;
      const lp50 = c.createBiquadFilter(); lp50.type = 'lowpass'; lp50.frequency.value = 260;
      const g50 = c.createGain(); g50.gain.value = 0.25;
      N.o300 = c.createOscillator(); N.o300.type = 'triangle'; N.o300.frequency.value = 300;
      const g300 = c.createGain(); g300.gain.value = 0.05;
      N.o100.connect(N.hum); N.o50.connect(lp50).connect(g50).connect(N.hum); N.o300.connect(g300).connect(N.hum);
      [N.o100, N.o50, N.o300].forEach(o => o.start());
      // water + runner rumble, amplitude-modulated at blade passing frequency
      N.water = c.createGain(); N.water.gain.value = 0;
      const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 220; bp.Q.value = 0.6;
      const lpw = c.createBiquadFilter(); lpw.type = 'lowpass'; lpw.frequency.value = 900;
      noise().connect(bp).connect(lpw).connect(N.water);
      N.rumble = c.createGain(); N.rumble.gain.value = 0;
      const lpr = c.createBiquadFilter(); lpr.type = 'lowpass'; lpr.frequency.value = 70; lpr.Q.value = 2;
      noise().connect(lpr).connect(N.rumble);
      N.am = c.createGain(); N.am.gain.value = 1;
      N.water.connect(N.am); N.rumble.connect(N.am); N.am.connect(m);
      N.lfo = c.createOscillator(); N.lfo.frequency.value = 5.5; N.lfoG = c.createGain(); N.lfoG.gain.value = 0;
      N.lfo.connect(N.lfoG).connect(N.am.gain); N.lfo.start();
      // oil pump motor
      N.pump = c.createGain(); N.pump.gain.value = 0; N.pump.connect(m);
      N.op = c.createOscillator(); N.op.type = 'sawtooth'; N.op.frequency.value = 148;
      const lpp = c.createBiquadFilter(); lpp.type = 'lowpass'; lpp.frequency.value = 520;
      N.op.connect(lpp).connect(N.pump); N.op.start();
      const bpn = c.createBiquadFilter(); bpn.type = 'bandpass'; bpn.frequency.value = 1400; bpn.Q.value = 1.4;
      const gpn = c.createGain(); gpn.gain.value = 0.4; noise().connect(bpn).connect(gpn).connect(N.pump);
      // annunciator horn
      N.horn = c.createGain(); N.horn.gain.value = 0; N.horn.connect(m);
      const h1 = c.createOscillator(); h1.type = 'square'; h1.frequency.value = 392;
      const h2 = c.createOscillator(); h2.type = 'square'; h2.frequency.value = 466;
      const lph = c.createBiquadFilter(); lph.type = 'lowpass'; lph.frequency.value = 1800;
      const gh = c.createGain(); gh.gain.value = 0.5;
      h1.connect(gh); h2.connect(gh); gh.connect(lph).connect(N.horn); h1.start(); h2.start();
      N.hornLfo = c.createOscillator(); N.hornLfo.type = 'square'; N.hornLfo.frequency.value = 1.6;
      N.hornLfoG = c.createGain(); N.hornLfoG.gain.value = 0.25; N.hornLfo.connect(N.hornLfoG).connect(gh.gain); N.hornLfo.start();
    },
    toggle() {
      this.init();
      if (!this.ctx) return false;
      this.on = !this.on;
      if (this.ctx.state === 'suspended') this.ctx.resume();
      this.master.gain.setTargetAtTime(this.on ? 0.55 : 0, this.ctx.currentTime, 0.08);
      return this.on;
    },
    set(node, v, tc = 0.15) { if (this.ctx) this.nodes[node].gain.setTargetAtTime(v, this.ctx.currentTime, tc); },
    update(horn) {
      if (!this.ctx || !this.on) return;
      const N = this.nodes, t = this.ctx.currentTime;
      const f = Math.max(1, 50 * P.w);
      const exc = P.fcb ? Math.min(1.2, P.Vt) : 0;
      N.o100.frequency.setTargetAtTime(2 * f, t, 0.1);
      N.o50.frequency.setTargetAtTime(f, t, 0.1);
      N.o300.frequency.setTargetAtTime(6 * f, t, 0.1);
      this.set('hum', 0.05 * exc * exc + 0.10 * exc * Math.min(1.2, P.I) + 0.012 * (P.cbL && P.grid ? 1 : 0));
      const q = P.q / 8.6;
      this.set('water', 0.11 * Math.min(1.3, q) + 0.02 * Math.min(1, P.qspill / 5));
      this.set('rumble', 0.35 * Math.min(1.5, P.w) * (0.3 + q));
      N.lfo.frequency.setTargetAtTime(Math.max(0.1, 4 * 83.33 * P.w / 60), t, 0.2);
      N.lfoG.gain.setTargetAtTime(0.35 * Math.min(1, P.w), t, 0.2);
      const pumps = (P.p1Run ? 1 : 0) + (P.p2Run ? 1 : 0) + (P.cw ? 0.6 : 0) + (P.lift ? 0.8 : 0);
      this.set('pump', 0.022 * pumps, 0.3);
      this.set('horn', horn ? 0.09 : 0, 0.02);
    },
    burst(dur, f, type, gain, q = 1) {
      if (!this.ctx || !this.on) return;
      const c = this.ctx, t = c.currentTime;
      const s = c.createBufferSource(); s.buffer = this.noiseBuf; s.playbackRate.value = 1 + Math.random() * 0.3;
      const fl = c.createBiquadFilter(); fl.type = type; fl.frequency.value = f; fl.Q.value = q;
      const g = c.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      s.connect(fl).connect(g).connect(this.master); s.start(t, Math.random()); s.stop(t + dur + 0.05);
    },
    tone(f, dur, gain, type = 'sine', f2) {
      if (!this.ctx || !this.on) return;
      const c = this.ctx, t = c.currentTime;
      const o = c.createOscillator(); o.type = type; o.frequency.setValueAtTime(f, t);
      if (f2) o.frequency.exponentialRampToValueAtTime(f2, t + dur);
      const g = c.createGain(); g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(this.master); o.start(t); o.stop(t + dur + 0.05);
    },
    click() { this.burst(0.03, 2600, 'highpass', 0.35); this.tone(1900, 0.02, 0.05, 'square'); },
    detent() { this.burst(0.025, 1800, 'bandpass', 0.5, 2); this.tone(700, 0.03, 0.04, 'triangle'); },
    relay() { this.burst(0.02, 3200, 'highpass', 0.25); setTimeout(() => this.burst(0.015, 2400, 'highpass', 0.15), 18); },
    clunk() { this.tone(85, 0.35, 0.5, 'sine', 40); this.burst(0.18, 700, 'lowpass', 0.8); setTimeout(() => this.burst(0.05, 2400, 'highpass', 0.25), 60); },
    printer(n) {
      if (!this.ctx || !this.on) return;
      for (let i = 0; i < n; i++) setTimeout(() => this.tone(1200 + Math.random() * 600, 0.012, 0.025, 'square'), i * 9);
    },
  };

  /* ===================================================================
     METERS
     =================================================================== */
  class Meter {
    constructor(parent, o) {
      this.o = Object.assign({
        w: 96, h: 96, kind: 'din', min: 0, max: 100, a0: -45, a1: 45, pivot: [0.5, 0.86], r: 0.64,
        major: 10, minor: 2, labelEvery: 2, fmt: v => String(Math.round(v)), zones: [], unit: '', title: '',
        maker: 'ELMESS', klass: '1.5', wn: 10, zeta: 0.55, needle: '#151515', map: null, mirror: false,
        marks: null, sub: null, redline: null, skirt: true, value: () => 0, rest: null, live: () => true,
        face: '#f4f1e6', symbol: 'mc',
      }, o);
      const wrap = el('div', 'mwrap' + (this.o.kind === 'round' || this.o.kind === 'sync' ? ' rnd' : ''), parent);
      this.c = el('canvas', 'meter', wrap);
      this.c.style.width = this.o.w + 'px'; this.c.style.height = this.o.h + 'px';
      this.ctx = this.c.getContext('2d');
      this.light = { glow: 0, shade: 0 };
      this.face = document.createElement('canvas');
      this.glass = document.createElement('canvas');
      this.pos = this.o.rest !== null ? this.o.rest : 0; this.vel = 0;
      this.pos2 = this.pos; this.vel2 = 0;
      this.wrap = wrap;
      this.rseed = METERS.length * 7 + 3;
      METERS.push(this);
    }
    frac(v) {
      const o = this.o;
      let f = (v - o.min) / (o.max - o.min);
      if (o.map) f = o.map(clamp(f, 0, 1.2)) * (f < 0 ? -1 : 1) + (f < 0 ? 0 : 0);
      return f;
    }
    ang(f) { return (this.o.a0 + f * (this.o.a1 - this.o.a0)) * D2R; }
    resize() {
      const k = kscale(), o = this.o;
      for (const cv of [this.c, this.face, this.glass]) { cv.width = Math.round(o.w * k); cv.height = Math.round(o.h * k); }
      this.k = k;
      this.drawFace(); this.drawGlass();
    }
    geom() {
      const o = this.o;
      if (o.kind === 'round' || o.kind === 'sync') return { px: o.w / 2, py: o.h / 2, r: o.w * o.r };
      return { px: o.w * o.pivot[0], py: o.h * o.pivot[1], r: o.w * o.r };
    }
    drawBezel(g) {
      const o = this.o, W = o.w, H = o.h;
      if (o.kind === 'round' || o.kind === 'sync') {
        const R = W / 2;
        let gr = g.createRadialGradient(R * 0.7, R * 0.6, R * 0.2, R, R, R);
        gr.addColorStop(0, '#f4f4f0'); gr.addColorStop(0.55, '#a7a7a1'); gr.addColorStop(0.8, '#e1e1dc'); gr.addColorStop(1, '#6d6d68');
        g.fillStyle = gr; g.beginPath(); g.arc(R, R, R, 0, 7); g.fill();
        g.fillStyle = '#2a2a28'; g.beginPath(); g.arc(R, R, R * 0.885, 0, 7); g.fill();
        g.fillStyle = o.face; g.beginPath(); g.arc(R, R, R * 0.86, 0, 7); g.fill();
        return { x: 0, y: 0, w: W, h: H };
      }
      const b = Math.max(5, Math.round(W * 0.075));
      let gr = g.createLinearGradient(0, 0, 0, H);
      gr.addColorStop(0, '#3d3d3a'); gr.addColorStop(0.08, '#1c1c1b'); gr.addColorStop(1, '#0b0b0b');
      g.fillStyle = gr; roundRect(g, 0, 0, W, H, 2.5); g.fill();
      g.strokeStyle = 'rgba(255,255,255,.12)'; g.lineWidth = 1; roundRect(g, 0.5, 0.5, W - 1, H - 1, 2.5); g.stroke();
      // moulded bezel: lit from above, worn corners
      let tg = g.createLinearGradient(0, 0, 0, b);
      tg.addColorStop(0, 'rgba(255,255,255,.22)'); tg.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = tg; g.fillRect(2, 1, W - 4, b);
      tg = g.createLinearGradient(0, H - b, 0, H);
      tg.addColorStop(0, 'rgba(0,0,0,0)'); tg.addColorStop(1, 'rgba(0,0,0,.45)');
      g.fillStyle = tg; g.fillRect(0, H - b, W, b);
      for (const [cx, cy] of [[2, 2], [W - 2, 2], [2, H - 2], [W - 2, H - 2]]) {
        const cg = g.createRadialGradient(cx, cy, 0, cx, cy, 5); cg.addColorStop(0, 'rgba(160,155,140,.35)'); cg.addColorStop(1, 'rgba(160,155,140,0)');
        g.fillStyle = cg; g.fillRect(cx - 5, cy - 5, 10, 10);
      }
      g.fillStyle = '#090909'; g.fillRect(b - 1.5, b - 1.5, W - 2 * b + 3, H - 2 * b + 3);
      g.fillStyle = o.face; g.fillRect(b, b, W - 2 * b, H - 2 * b);
      return { x: b, y: b, w: W - 2 * b, h: H - 2 * b };
    }
    drawFace() {
      const o = this.o, k = this.k, g = this.face.getContext('2d');
      g.setTransform(k, 0, 0, k, 0, 0); g.clearRect(0, 0, o.w, o.h);
      const fr = this.drawBezel(g);
      this.fr = fr;
      g.save(); g.beginPath();
      if (o.kind === 'round' || o.kind === 'sync') g.arc(o.w / 2, o.h / 2, o.w / 2 * 0.86, 0, 7);
      else g.rect(fr.x, fr.y, fr.w, fr.h);
      g.clip();
      // aged face: faint vignette
      const vg = g.createRadialGradient(o.w * 0.5, o.h * 0.45, o.w * 0.1, o.w * 0.5, o.h * 0.5, o.w * 0.75);
      vg.addColorStop(0, 'rgba(255,255,255,0)'); vg.addColorStop(1, 'rgba(120,100,60,.13)');
      g.fillStyle = vg; g.fillRect(0, 0, o.w, o.h);
      { // 35 years behind glass: uneven yellowing and a few foxing spots
        const R = window.LOOK.rng(this.rseed);
        const yg = g.createLinearGradient(0, 0, o.w * (0.3 + R() * 0.6), o.h);
        yg.addColorStop(0, `rgba(190,160,90,${(0.03 + R() * 0.05).toFixed(3)})`); yg.addColorStop(1, 'rgba(190,160,90,0)');
        g.fillStyle = yg; g.fillRect(0, 0, o.w, o.h);
        for (let i = 0; i < 5; i++) {
          const x = R() * o.w, y = R() * o.h, r = 0.6 + R() * 2.2;
          g.fillStyle = `rgba(150,120,70,${(0.05 + R() * 0.08).toFixed(3)})`; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
        }
      }
      if (o.kind === 'edge') this.faceEdge(g, fr);
      else if (o.kind === 'sync') this.faceSync(g);
      else this.faceArc(g, fr);
      g.restore();
    }
    scaleMarks() {
      const o = this.o;
      if (o.marks) return o.marks;
      const out = [];
      const n = Math.round((o.max - o.min) / o.minor);
      for (let i = 0; i <= n; i++) {
        const v = o.min + i * o.minor;
        const isMaj = Math.abs(((v - o.min) / o.major) - Math.round((v - o.min) / o.major)) < 1e-6;
        const ls = o.labelStep || o.major * o.labelEvery;
        const isLab = isMaj && Math.abs(v / ls - Math.round(v / ls)) < 1e-6;
        out.push({ v, M: isMaj, label: isLab ? o.fmt(v) : null, half: !isMaj && Math.abs(((v - o.min) / (o.major / 2)) % 1) < 1e-6 });
      }
      return out;
    }
    faceArc(g, fr) {
      const o = this.o, { px, py, r } = this.geom();
      const a0 = this.ang(0), a1 = this.ang(1);
      const P2 = (a, rr) => [px + Math.sin(a) * rr, py - Math.cos(a) * rr];
      // zones
      for (const z of o.zones) {
        const fa = this.ang(clamp(this.frac(z.f), 0, 1)), fb = this.ang(clamp(this.frac(z.t), 0, 1));
        g.strokeStyle = z.c; g.lineWidth = r * 0.07;
        g.beginPath(); g.arc(px, py, r * 1.035, fa - Math.PI / 2, fb - Math.PI / 2); g.stroke();
      }
      if (o.mirror) {
        const gr = g.createLinearGradient(px - r, py - r, px + r, py);
        gr.addColorStop(0, '#9aa0a4'); gr.addColorStop(0.45, '#eef2f4'); gr.addColorStop(0.55, '#b9c0c4'); gr.addColorStop(1, '#e8ecee');
        g.strokeStyle = gr; g.lineWidth = r * 0.06;
        g.beginPath(); g.arc(px, py, r * 0.885, a0 - Math.PI / 2, a1 - Math.PI / 2); g.stroke();
      }
      // scale line + ticks
      g.strokeStyle = '#141414'; g.lineWidth = 0.9;
      g.beginPath(); g.arc(px, py, r, a0 - Math.PI / 2, a1 - Math.PI / 2); g.stroke();
      const fs = Math.max(6.8, Math.min(o.w * 0.078, 10));
      g.font = `500 ${fs}px ${FN}`; g.fillStyle = '#141414'; g.textAlign = 'center'; g.textBaseline = 'middle';
      for (const m of this.scaleMarks()) {
        const a = this.ang(this.frac(m.v));
        const len = m.M ? r * 0.12 : m.half ? r * 0.085 : r * 0.055;
        const [x1, y1] = P2(a, r), [x2, y2] = P2(a, r - len);
        g.lineWidth = m.M ? 1.25 : 0.75;
        g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
        if (m.label) { const [x, y] = P2(a, r - r * 0.12 - fs * 0.8); g.fillText(m.label, x, y); }
      }
      if (o.redline !== null) {
        const a = this.ang(this.frac(o.redline));
        const [x1, y1] = P2(a, r * 1.08), [x2, y2] = P2(a, r * 0.86);
        g.strokeStyle = '#c4180e'; g.lineWidth = 2.2;
        g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
      }
      // secondary (inner) scale
      if (o.sub) {
        const s = o.sub, rr = r * (s.r || 0.62);
        g.strokeStyle = s.color || '#9a1e14'; g.fillStyle = s.color || '#9a1e14'; g.lineWidth = 0.8;
        const sa = this.ang(this.frac(s.toMain(s.min))), sb = this.ang(this.frac(s.toMain(s.max)));
        g.beginPath(); g.arc(px, py, rr, sa - Math.PI / 2, sb - Math.PI / 2); g.stroke();
        g.font = `500 ${fs * 0.78}px ${FN}`;
        for (let v = s.min; v <= s.max + 1e-6; v += s.step) {
          const a = this.ang(this.frac(s.toMain(v)));
          const isL = Math.abs(((v - s.min) / s.label) - Math.round((v - s.min) / s.label)) < 1e-6;
          const [x1, y1] = P2(a, rr), [x2, y2] = P2(a, rr + (isL ? r * 0.08 : r * 0.045));
          g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
          if (isL) { const [x, y] = P2(a, rr - fs * 0.7); g.fillText(String(v), x, y); }
        }
        if (s.unit) { g.font = `600 ${fs * 0.7}px ${FL}`; const [x, y] = P2(this.ang(0.5), rr - fs * 1.8); g.fillText(s.unit, x, y); }
      }
      // legends
      g.fillStyle = '#141414';
      const span = o.a1 - o.a0;
      if (o.kind === 'round') {
        g.font = `500 ${fs * 1.0}px ${FN}`; g.fillText(o.unit, px, py + r * 0.55);
        if (o.title) { g.font = `600 ${fs * 0.62}px ${FL}`; g.fillText(o.title, px, py + r * 1.12); }
        g.font = `500 ${fs * 0.55}px ${FL}`; g.fillStyle = '#444';
        g.fillText(`${o.maker}  ${o.klass}`, px, py + r * 0.84);
      } else if (span > 180) {
        g.font = `500 ${fs * 1.1}px ${FN}`; g.fillText(o.unit, px, py + r * 0.40);
        if (o.title) { g.font = `600 ${fs * 0.68}px ${FL}`; g.fillText(o.title, px, py - r * 0.36); }
        if (o.title2) { g.font = `500 ${fs * 0.6}px ${FL}`; g.fillText(o.title2, px, py + r * 0.62); }
        g.font = `500 ${fs * 0.5}px ${FL}`; g.fillStyle = '#444';
        g.fillText(`${o.maker}   ${o.klass}  ⊥  ☆2`, px, py + r * 0.80);
      } else {
        g.font = `500 ${fs * 1.08}px ${FN}`; g.fillText(o.unit, px, py - r * 0.50);
        if (o.title) { g.font = `600 ${fs * 0.66}px ${FL}`; g.fillText(o.title, px, py - r * 0.33); }
        g.font = `500 ${fs * 0.58}px ${FL}`; g.fillStyle = '#4a4a46'; g.textAlign = 'left';
        g.fillText(o.maker, fr.x + 3, fr.y + fr.h - 4);
        g.textAlign = 'right'; g.fillText(`${o.klass} ⊥ ☆2`, fr.x + fr.w - 3, fr.y + fr.h - 4);
        g.textAlign = 'center';
      }
    }
    faceEdge(g, fr) {
      const o = this.o;
      const top = fr.y + 12, bot = fr.y + fr.h - 22, x0 = fr.x + fr.w * (o.x0 || 0.58);
      this.eg = { top, bot, x0, fr };
      for (const z of o.zones) {
        const ya = bot - clamp(this.frac(z.f), 0, 1) * (bot - top), yb = bot - clamp(this.frac(z.t), 0, 1) * (bot - top);
        g.fillStyle = z.c; g.fillRect(x0 + 1, yb, 4, ya - yb);
      }
      g.strokeStyle = '#151515'; g.lineWidth = 0.9;
      g.beginPath(); g.moveTo(x0, top); g.lineTo(x0, bot); g.stroke();
      const fs = Math.max(6.5, Math.min(fr.w * 0.19, 8.5));
      g.font = `500 ${fs}px ${FN}`; g.fillStyle = '#151515'; g.textAlign = 'right'; g.textBaseline = 'middle';
      for (const m of this.scaleMarks()) {
        const y = bot - this.frac(m.v) * (bot - top);
        const len = m.M ? 7 : m.half ? 5 : 3;
        g.lineWidth = m.M ? 1.1 : 0.7;
        g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 - len, y); g.stroke();
        if (m.label) g.fillText(m.label, x0 - 9, y);
      }
      if (o.extraMarks) for (const em of o.extraMarks) {
        const y = bot - this.frac(em.v) * (bot - top);
        g.strokeStyle = em.c; g.lineWidth = 1.5; g.beginPath(); g.moveTo(fr.x + 2, y); g.lineTo(fr.x + fr.w - 2, y); g.stroke();
        g.fillStyle = em.c; g.font = `600 ${fs * 0.6}px ${FL}`; g.textAlign = 'left'; g.fillText(em.t, x0 + 6, y - 5);
      }
      g.textAlign = 'center'; g.fillStyle = '#151515';
      g.font = `500 ${fs * 0.95}px ${FN}`; g.fillText(o.unit, fr.x + fr.w / 2, fr.y + fr.h - 12);
      g.font = `500 ${fs * 0.48}px ${FL}`; g.fillStyle = '#4a4a46'; g.fillText(o.maker, fr.x + fr.w / 2, fr.y + fr.h - 4);
    }
    faceSync(g) {
      const o = this.o, cx = o.w / 2, cy = o.h / 2, r = o.w * 0.36;
      const P2 = (a, rr) => [cx + Math.sin(a) * rr, cy - Math.cos(a) * rr];
      g.strokeStyle = '#141414';
      for (let i = 0; i < 72; i++) {
        const a = i * 5 * D2R, maj = i % 6 === 0;
        const [x1, y1] = P2(a, r), [x2, y2] = P2(a, r - (maj ? 9 : 4));
        g.lineWidth = maj ? 1.4 : 0.7; g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
      }
      g.fillStyle = '#1d6d2c';
      g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, r + 4, -Math.PI / 2 - 10 * D2R, -Math.PI / 2 + 10 * D2R); g.closePath(); g.globalAlpha = 0.25; g.fill(); g.globalAlpha = 1;
      g.fillStyle = '#b71c10';
      const [tx, ty] = P2(0, r + 3); g.beginPath(); g.moveTo(tx, ty + 12); g.lineTo(tx - 5, ty - 1); g.lineTo(tx + 5, ty - 1); g.closePath(); g.fill();
      g.fillStyle = '#141414'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.font = `700 ${o.w * 0.07}px ${FL}`;
      g.fillText('SLOW', cx - r * 0.55, cy + r * 0.52); g.fillText('FAST', cx + r * 0.55, cy + r * 0.52);
      g.lineWidth = 1.4;
      arrow(g, cx - r * 0.55, cy + r * 0.30, -1); arrow(g, cx + r * 0.55, cy + r * 0.30, 1);
      g.font = `600 ${o.w * 0.055}px ${FL}`; g.fillText('SYNCHROSCOPE', cx, cy - r * 0.42);
      g.font = `500 ${o.w * 0.045}px ${FL}`; g.fillStyle = '#4a4a46'; g.fillText(`${o.maker}  2×400 V  50 Hz`, cx, cy + r * 0.80);
      function arrow(g, x, y, dir) {
        g.beginPath(); g.arc(x, y + 8, 10, -Math.PI / 2 - 0.9, -Math.PI / 2 + 0.9); g.stroke();
        const ex = x + dir * Math.sin(0.9) * 10, ey = y + 8 - Math.cos(0.9) * 10;
        g.beginPath(); g.moveTo(ex, ey); g.lineTo(ex - dir * 4, ey - 3); g.lineTo(ex - dir * 1, ey + 4); g.closePath(); g.fill();
      }
    }
    drawGlass() {
      const o = this.o, k = this.k, g = this.glass.getContext('2d');
      g.setTransform(k, 0, 0, k, 0, 0); g.clearRect(0, 0, o.w, o.h);
      const fr = this.fr;
      if ((o.kind === 'din') && o.skirt && (o.a1 - o.a0) <= 120) {
        const { px, py, r } = this.geom();
        g.save(); g.beginPath(); g.rect(fr.x, fr.y, fr.w, fr.h); g.clip();
        g.fillStyle = '#2b2b29';
        g.beginPath(); g.arc(px, py, r * 0.25, Math.PI, 0); g.lineTo(fr.x + fr.w, py); g.lineTo(fr.x + fr.w, fr.y + fr.h - 11); g.lineTo(fr.x, fr.y + fr.h - 11); g.lineTo(fr.x, py); g.closePath(); g.fill();
        g.strokeStyle = 'rgba(255,255,255,.12)'; g.lineWidth = 1; g.beginPath(); g.arc(px, py, r * 0.25, Math.PI, 0); g.stroke();
        g.restore();
      }
      // glass reflection
      g.save(); g.beginPath();
      if (o.kind === 'round' || o.kind === 'sync') g.arc(o.w / 2, o.h / 2, o.w / 2 * 0.88, 0, 7); else g.rect(fr.x, fr.y, fr.w, fr.h);
      g.clip();
      const gr = g.createLinearGradient(0, 0, o.w, o.h);
      gr.addColorStop(0, 'rgba(255,255,255,.22)'); gr.addColorStop(0.32, 'rgba(255,255,255,.06)'); gr.addColorStop(0.42, 'rgba(255,255,255,0)');
      gr.addColorStop(0.85, 'rgba(255,255,255,0)'); gr.addColorStop(1, 'rgba(255,255,255,.07)');
      g.fillStyle = gr; g.fillRect(0, 0, o.w, o.h);
      const sh = g.createLinearGradient(0, fr.y, 0, fr.y + 10);
      sh.addColorStop(0, 'rgba(0,0,0,.35)'); sh.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = sh; g.fillRect(0, fr.y, o.w, 10);
      // reflections of the ceiling's fluorescent tubes in the glass
      const R = window.LOOK.rng(this.rseed + 1);
      g.save(); g.translate(o.w / 2, o.h / 2); g.rotate(-0.30 + (R() - 0.5) * 0.08);
      for (const [off, wd, a] of [[-0.30, 0.10, 0.17], [-0.12, 0.05, 0.10]]) {
        const y = off * o.h, bw = wd * o.h;
        const bg = g.createLinearGradient(0, y - bw, 0, y + bw);
        bg.addColorStop(0, 'rgba(255,255,250,0)'); bg.addColorStop(0.5, `rgba(255,255,250,${a})`); bg.addColorStop(1, 'rgba(255,255,250,0)');
        g.fillStyle = bg; g.fillRect(-o.w, y - bw, o.w * 2, bw * 2);
      }
      g.restore();
      // dust specks and the odd fibre on the glass
      for (let i = 0; i < 22; i++) {
        const x = fr.x + R() * fr.w, y = fr.y + R() * fr.h;
        g.fillStyle = `rgba(${R() < 0.5 ? '255,255,255' : '60,55,45'},${(0.10 + R() * 0.22).toFixed(2)})`;
        g.beginPath(); g.arc(x, y, 0.25 + R() * 0.55, 0, 7); g.fill();
      }
      if (R() < 0.6) {
        const x = fr.x + R() * fr.w, y = fr.y + R() * fr.h, a = R() * 6;
        g.strokeStyle = 'rgba(240,240,235,.22)'; g.lineWidth = 0.35;
        g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x + Math.cos(a) * 4, y + Math.sin(a) * 4 + 2, x + Math.cos(a) * 8, y + Math.sin(a) * 8); g.stroke();
      }
      if (R() < 0.35) {   // a thumb smear from someone tapping a sticky needle
        const x = fr.x + fr.w * (0.25 + R() * 0.5), y = fr.y + fr.h * (0.25 + R() * 0.5);
        const sg = g.createRadialGradient(x, y, 0, x, y, fr.w * 0.18);
        sg.addColorStop(0, 'rgba(255,255,255,.08)'); sg.addColorStop(1, 'rgba(255,255,255,0)');
        g.fillStyle = sg; g.beginPath(); g.ellipse(x, y, fr.w * 0.18, fr.w * 0.13, R() * 3, 0, 7); g.fill();
      }
      g.restore();
      // the room light where this meter hangs (same pools and falloff as the steel around it)
      if (this.light.shade > 0 || this.light.glow > 0) {
        g.save(); g.beginPath();
        if (o.kind === 'round' || o.kind === 'sync') g.arc(o.w / 2, o.h / 2, o.w / 2, 0, 7); else roundRect(g, 0, 0, o.w, o.h, 2.5);
        g.clip();
        g.fillStyle = `rgba(28,22,12,${(this.light.shade * 0.85).toFixed(3)})`; g.fillRect(0, 0, o.w, o.h);
        g.fillStyle = `rgba(255,248,226,${(this.light.glow * 0.30).toFixed(3)})`; g.fillRect(0, 0, o.w, o.h);
        g.restore();
      }
      // zero adjuster in the bezel
      if (o.kind === 'din' || o.kind === 'edge') {
        const zb = Math.max(5, Math.round(o.w * 0.075)), zx = o.w / 2, zy = o.h - zb / 2 - 0.5, zr = zb * 0.30;
        const zg = g.createRadialGradient(zx - zr * 0.3, zy - zr * 0.3, 0, zx, zy, zr);
        zg.addColorStop(0, '#4a4a47'); zg.addColorStop(1, '#0a0a0a');
        g.fillStyle = zg; g.beginPath(); g.arc(zx, zy, zr, 0, 7); g.fill();
        g.save(); g.translate(zx, zy); g.rotate(R() * Math.PI);
        g.fillStyle = 'rgba(0,0,0,.9)'; g.fillRect(-zr * 0.9, -0.45, zr * 1.8, 0.9);
        g.fillStyle = 'rgba(255,255,255,.18)'; g.fillRect(-zr * 0.9, 0.45, zr * 1.8, 0.4);
        g.restore();
      }
    }
    step(dt, jitter) {
      const o = this.o;
      const live = o.live();
      let target = live ? this.frac(o.value()) : (o.rest !== null ? o.rest : this.pos);
      if (o.kind === 'sync') { this.stepSync(dt, live); return; }
      target = clamp(target + (live ? jitter * (Math.random() - 0.5) : 0), -0.035, 1.05);
      const n = Math.max(1, Math.ceil(dt / 0.008)), h = dt / n, wn = o.wn, z = o.zeta;
      for (let i = 0; i < n; i++) {
        const a = wn * wn * (target - this.pos) - 2 * z * wn * this.vel;
        this.vel += a * h; this.pos += this.vel * h;
        if (this.pos < -0.035) { this.pos = -0.035; this.vel = -this.vel * 0.25; }
        if (this.pos > 1.05) { this.pos = 1.05; this.vel = -this.vel * 0.25; }
      }
      if (o.value2) {
        const t2 = live ? clamp(this.frac(o.value2()), -0.035, 1.05) : (o.rest !== null ? o.rest : this.pos2);
        for (let i = 0; i < n; i++) {
          const a = wn * wn * (t2 - this.pos2) - 2 * z * wn * this.vel2;
          this.vel2 += a * h; this.pos2 += this.vel2 * h;
          this.pos2 = clamp(this.pos2, -0.035, 1.05);
        }
      }
    }
    stepSync(dt, live) {
      if (!live) { this.vel *= Math.exp(-dt * 1.5); this.pos += this.vel * dt; return; }
      const t = this.o.value();
      let d = t - this.pos; d = Math.atan2(Math.sin(d), Math.cos(d));
      const wn = 14, z = 0.7;
      const n = Math.max(1, Math.ceil(dt / 0.008)), h = dt / n;
      for (let i = 0; i < n; i++) {
        let e = t - this.pos; e = Math.atan2(Math.sin(e), Math.cos(e));
        const a = wn * wn * e - 2 * z * wn * this.vel;
        this.vel += a * h; this.pos += this.vel * h;
      }
      void d;
    }
    draw() {
      const o = this.o, g = this.ctx, k = this.k;
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.clearRect(0, 0, this.c.width, this.c.height);
      g.drawImage(this.face, 0, 0);
      g.setTransform(k, 0, 0, k, 0, 0);
      if (o.kind === 'edge') this.needleEdge(g);
      else if (o.kind === 'sync') this.needleSync(g);
      else {
        if (o.setValue) this.needleArc(g, this.frac(o.setValue()), '#c01d10', 0.92, true);
        if (o.value2) this.needleArc(g, this.pos2, o.needle2 || '#c01d10', 0.95);
        this.needleArc(g, this.pos, o.needle, 0.95);
      }
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.drawImage(this.glass, 0, 0);
    }
    needleArc(g, f, color, lenF, isSet) {
      const o = this.o, { px, py, r } = this.geom();
      const a = this.ang(f);
      const s = Math.sin(a), c = Math.cos(a);
      const L = r * lenF, T = r * (o.kind === 'round' ? 0.22 : 0.12);
      const tip = [px + s * L, py - c * L], tail = [px - s * T, py + c * T];
      if (isSet) {
        const [x, y] = [px + s * r * 1.02, py - c * r * 1.02];
        g.fillStyle = color; g.beginPath();
        g.moveTo(x, y); g.lineTo(x + Math.cos(a) * 3.5 + s * 7, y + Math.sin(a) * 3.5 - c * 7); g.lineTo(x - Math.cos(a) * 3.5 + s * 7, y - Math.sin(a) * 3.5 - c * 7); g.closePath(); g.fill();
        return;
      }
      g.lineCap = 'round';
      g.strokeStyle = 'rgba(0,0,0,.20)'; g.lineWidth = 1.8;
      g.beginPath(); g.moveTo(tail[0] + 1.8, tail[1] + 2.6); g.lineTo(tip[0] + 1.8, tip[1] + 2.6); g.stroke();
      g.strokeStyle = color; g.lineWidth = o.kind === 'round' ? 2.2 : 1.5;
      g.beginPath(); g.moveTo(tail[0], tail[1]); g.lineTo(px + s * L * 0.75, py - c * L * 0.75); g.stroke();
      g.lineWidth = 0.9; g.beginPath(); g.moveTo(px + s * L * 0.74, py - c * L * 0.74); g.lineTo(tip[0], tip[1]); g.stroke();
      if (o.kind === 'round' || (o.a1 - o.a0) > 120) {
        g.fillStyle = '#111'; g.beginPath(); g.arc(px, py, o.kind === 'round' ? r * 0.10 : r * 0.07, 0, 7); g.fill();
        g.fillStyle = 'rgba(255,255,255,.25)'; g.beginPath(); g.arc(px - 1, py - 1, r * 0.03, 0, 7); g.fill();
      }
    }
    needleEdge(g) {
      const { top, bot, fr, x0 } = this.eg;
      const y = bot - this.pos * (bot - top);
      g.fillStyle = 'rgba(0,0,0,.2)'; g.fillRect(x0 + 2, y - 0.2 + 2, fr.x + fr.w - x0 - 4, 1.6);
      g.fillStyle = '#121212'; g.beginPath();
      g.moveTo(x0 + 1, y); g.lineTo(x0 + 7, y - 2.2); g.lineTo(fr.x + fr.w - 2, y - 1); g.lineTo(fr.x + fr.w - 2, y + 1); g.lineTo(x0 + 7, y + 2.2); g.closePath(); g.fill();
      if (this.o.setValue) {
        const ys = bot - clamp(this.frac(this.o.setValue()), 0, 1) * (bot - top);
        g.fillStyle = '#c01d10'; g.beginPath(); g.moveTo(x0 + 2, ys); g.lineTo(x0 + 9, ys - 4); g.lineTo(x0 + 9, ys + 4); g.closePath(); g.fill();
      }
    }
    needleSync(g) {
      const o = this.o, cx = o.w / 2, cy = o.h / 2, r = o.w * 0.34;
      const a = this.pos, s = Math.sin(a), c = Math.cos(a);
      g.lineCap = 'round';
      g.strokeStyle = 'rgba(0,0,0,.22)'; g.lineWidth = 3.4;
      g.beginPath(); g.moveTo(cx - s * r * 0.75 + 2, cy + c * r * 0.75 + 3); g.lineTo(cx + s * r + 2, cy - c * r + 3); g.stroke();
      g.strokeStyle = '#141414'; g.lineWidth = 3;
      g.beginPath(); g.moveTo(cx - s * r * 0.75, cy + c * r * 0.75); g.lineTo(cx + s * r * 0.5, cy - c * r * 0.5); g.stroke();
      g.strokeStyle = '#c0180c'; g.lineWidth = 3;
      g.beginPath(); g.moveTo(cx + s * r * 0.5, cy - c * r * 0.5); g.lineTo(cx + s * r, cy - c * r); g.stroke();
      g.fillStyle = '#111'; g.beginPath(); g.arc(cx, cy, 6, 0, 7); g.fill();
    }
  }
  function roundRect(g, x, y, w, h, r) {
    g.beginPath(); g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.quadraticCurveTo(x + w, y, x + w, y + r);
    g.lineTo(x + w, y + h - r); g.quadraticCurveTo(x + w, y + h, x + w - r, y + h); g.lineTo(x + r, y + h);
    g.quadraticCurveTo(x, y + h, x, y + h - r); g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y); g.closePath();
  }

  /* vibrating-reed frequency meter (two systems) */
  class ReedMeter {
    constructor(parent, o) {
      this.o = Object.assign({ w: 156, h: 112 }, o);
      const wrap = el('div', 'mwrap', parent);
      this.c = el('canvas', 'meter', wrap);
      this.c.style.width = this.o.w + 'px'; this.c.style.height = this.o.h + 'px';
      this.ctx = this.c.getContext('2d');
      this.reeds = []; for (let f = 47.5; f <= 52.501; f += 0.25) this.reeds.push(+f.toFixed(2));
      this.amp = [new Float32Array(this.reeds.length), new Float32Array(this.reeds.length)];
      this.ph = 0;
      METERS.push(this);
    }
    resize() { const k = this.k = kscale(); this.c.width = Math.round(this.o.w * k); this.c.height = Math.round(this.o.h * k); }
    step(dt) {
      this.ph += dt;
      const src = [this.o.f1(), this.o.f2()];
      for (let s = 0; s < 2; s++) {
        const { f, a } = src[s];
        for (let i = 0; i < this.reeds.length; i++) {
          const x = (f - this.reeds[i]) / 0.11;
          const t = a > 0 ? a / (1 + x * x) : 0;
          this.amp[s][i] += (t - this.amp[s][i]) * Math.min(1, dt * 4);
        }
      }
    }
    draw() {
      const o = this.o, g = this.ctx, k = this.k, W = o.w, H = o.h;
      g.setTransform(k, 0, 0, k, 0, 0); g.clearRect(0, 0, W, H);
      let gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, '#3d3d3a'); gr.addColorStop(0.1, '#1c1c1b'); gr.addColorStop(1, '#0b0b0b');
      g.fillStyle = gr; roundRect(g, 0, 0, W, H, 3); g.fill();
      g.fillStyle = '#f2efe3'; g.fillRect(7, 7, W - 14, H - 14);
      const n = this.reeds.length, x0 = 15, x1 = W - 15, dx = (x1 - x0) / (n - 1);
      g.fillStyle = '#141414'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.font = `600 7.5px ${FL}`; g.fillText('GENERATOR', W / 2, 14); g.fillText('LINE', W / 2, H - 39);
      for (let s = 0; s < 2; s++) {
        const yy = s === 0 ? 21 : H - 32, hh = 22;
        g.fillStyle = '#121212'; g.fillRect(x0 - 5, yy, x1 - x0 + 10, hh);
        for (let i = 0; i < n; i++) {
          const a = this.amp[s][i];
          const x = x0 + i * dx;
          const len = 4 + a * 14;
          const alpha = 0.55 + 0.45 * (1 - a * 0.5);
          g.fillStyle = `rgba(250,250,245,${alpha})`;
          g.fillRect(x - 1.8, yy + hh / 2 - len / 2, 3.6, len);
          if (a < 0.1) { g.fillStyle = '#f8f8f2'; g.fillRect(x - 1.8, yy + hh / 2 - 2, 3.6, 4); }
        }
      }
      g.fillStyle = '#141414'; g.font = `500 8px ${FN}`;
      for (let i = 0; i < n; i++) {
        const x = x0 + i * dx, f = this.reeds[i];
        if (Math.abs(f - Math.round(f)) < 1e-6) { g.fillText(String(Math.round(f)), x, H / 2 + 1); g.fillRect(x - 0.4, 44, 0.8, 4); g.fillRect(x - 0.4, H - 47, 0.8, 4); }
        else if (Math.abs(f * 2 - Math.round(f * 2)) < 1e-6) { g.fillRect(x - 0.3, 44, 0.6, 2.5); g.fillRect(x - 0.3, H - 45.5, 0.6, 2.5); }
      }
      g.font = `500 8px ${FN}`; g.fillText('Hz', W - 12, H / 2 - 9);
      g.font = `500 6px ${FL}`; g.fillStyle = '#555'; g.fillText('ELMESS  ZUNGENFREQUENZMESSER  2×400 V', W / 2, H - 9);
      const gl = g.createLinearGradient(0, 0, W, H); gl.addColorStop(0, 'rgba(255,255,255,.18)'); gl.addColorStop(0.4, 'rgba(255,255,255,0)');
      g.fillStyle = gl; g.fillRect(7, 7, W - 14, H - 14);
    }
  }

  /* Ferraris induction kWh meter with rotating disc and cyclometer */
  class Ferraris {
    constructor(parent, o) {
      this.o = Object.assign({ w: 196, h: 136 }, o);
      const wrap = el('div', 'mwrap', parent);
      this.c = el('canvas', 'meter', wrap);
      this.c.style.width = this.o.w + 'px'; this.c.style.height = this.o.h + 'px';
      this.ctx = this.c.getContext('2d'); this.disc = 0;
      METERS.push(this);
    }
    resize() { const k = this.k = kscale(); this.c.width = Math.round(this.o.w * k); this.c.height = Math.round(this.o.h * k); }
    step(dt) { const kw = Math.max(0, this.o.kw()); this.disc += dt * kw * EFFACC * (150 / 100) / 3600; }   // C=150 U/kWh secondary, CT ×100
    draw() {
      const o = this.o, g = this.ctx, k = this.k, W = o.w, H = o.h;
      g.setTransform(k, 0, 0, k, 0, 0); g.clearRect(0, 0, W, H);
      let gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, '#2b2a27'); gr.addColorStop(1, '#0f0f0e');
      g.fillStyle = gr; roundRect(g, 0, 0, W, H, 8); g.fill();
      g.fillStyle = '#e9e5d6'; roundRect(g, 8, 8, W - 16, H - 16, 4); g.fill();
      // register
      const v = o.reg(), nd = 7, dw = 14, dh = 19, rx = W / 2 - (nd * (dw + 1)) / 2, ry = 18;
      g.fillStyle = '#0d0d0d'; g.fillRect(rx - 3, ry - 3, nd * (dw + 1) + 5, dh + 6);
      let carry = 0;
      const scaled = v * 10;
      for (let i = 0; i < nd; i++) {
        const p = Math.pow(10, i);
        let pos = i === 0 ? scaled % 10 : (Math.floor(scaled / p) % 10) + carry;
        carry = (i === 0 ? pos : pos) > 9 ? (pos - 9) : 0;
        if (i === 0) carry = pos > 9 ? pos - 9 : 0;
        const x = rx + (nd - 1 - i) * (dw + 1);
        g.save(); g.beginPath(); g.rect(x, ry, dw, dh); g.clip();
        g.fillStyle = i === 0 ? '#b8231a' : '#f4f2ea'; g.fillRect(x, ry, dw, dh);
        g.fillStyle = i === 0 ? '#fff' : '#111'; g.font = `500 15px ${FN}`; g.textAlign = 'center'; g.textBaseline = 'middle';
        const base = Math.floor(pos), fr = pos - base;
        g.fillText(String(base % 10), x + dw / 2, ry + dh / 2 - fr * dh);
        g.fillText(String((base + 1) % 10), x + dw / 2, ry + dh / 2 + dh - fr * dh);
        const sh = g.createLinearGradient(0, ry, 0, ry + dh); sh.addColorStop(0, 'rgba(0,0,0,.45)'); sh.addColorStop(0.3, 'rgba(0,0,0,0)'); sh.addColorStop(0.7, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,0,.45)');
        g.fillStyle = sh; g.fillRect(x, ry, dw, dh); g.restore();
        if (i > 0) carry = pos > 9 ? pos - 9 : (Math.floor(scaled / p) % 10 === 9 ? carry : 0);
      }
      g.fillStyle = '#111'; g.font = `600 10px ${FL}`; g.textAlign = 'left'; g.fillText('kWh', rx + nd * (dw + 1) + 6, ry + dh / 2 + 1);
      g.font = `600 8px ${FL}`; g.textAlign = 'center'; g.fillText('× 10', rx - 18, ry + dh / 2 + 1);
      // disc window
      const wx = 28, wy = 52, ww = W - 56, wh = 16;
      g.fillStyle = '#151515'; g.fillRect(wx - 2, wy - 2, ww + 4, wh + 4);
      const dg = g.createLinearGradient(0, wy, 0, wy + wh); dg.addColorStop(0, '#6e6e6c'); dg.addColorStop(0.5, '#d9d9d6'); dg.addColorStop(1, '#5d5d5b');
      g.fillStyle = dg; g.fillRect(wx, wy, ww, wh);
      // the red mark travels across the visible arc of the disc
      const ph = (this.disc % 1);
      const mx = wx + ww * (0.5 + 0.62 * Math.sin((ph - 0.5) * Math.PI * 2) * 0.8);
      if (ph > 0.25 && ph < 0.75) { g.fillStyle = '#c31a10'; g.fillRect(mx - 3, wy + 1, 6, wh - 2); }
      for (let i = 0; i < 18; i++) {   // scale marks on the disc rim
        const ang = ((i / 18 + ph) % 1);
        if (ang > 0.25 && ang < 0.75) { const x = wx + ww * (0.5 + 0.5 * Math.sin((ang - 0.5) * Math.PI * 2)); g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(x - 0.4, wy + 1, 0.8, 4); }
      }
      g.fillStyle = '#1b1b1b'; g.font = `600 8px ${FL}`; g.textAlign = 'center';
      g.fillText('ELMESS  DREHSTROM-ZÄHLER  D4', W / 2, 84);
      g.font = `500 7.5px ${FL}`;
      g.fillText('3~ 3×400/230 V   3× 5 A   50 Hz   CT 500/5 A', W / 2, 95);
      g.fillText('C = 150 U/kWh   Kl. 2   Nr. 7 408 233   1987', W / 2, 105);
      g.fillStyle = '#7a1b12'; g.font = `700 8px ${FL}`; g.fillText(o.title, W / 2, 118);
      const gl = g.createLinearGradient(0, 0, W, H); gl.addColorStop(0, 'rgba(255,255,255,.16)'); gl.addColorStop(0.35, 'rgba(255,255,255,0)'); gl.addColorStop(0.9, 'rgba(255,255,255,.05)');
      g.fillStyle = gl; roundRect(g, 8, 8, W - 16, H - 16, 4); g.fill();
    }
  }

  /* synchronous wall clock on the cabinet top */
  class Clock {
    constructor(parent, size) {
      this.s = size;
      this.c = el('canvas', 'meter clockbox', parent);
      this.c.style.width = size + 'px'; this.c.style.height = size + 'px';
      this.ctx = this.c.getContext('2d');
      METERS.push(this);
    }
    resize() { const k = this.k = kscale(); this.c.width = this.c.height = Math.round(this.s * k); }
    step() {}
    draw() {
      const g = this.ctx, k = this.k, S = this.s, R = S / 2;
      g.setTransform(k, 0, 0, k, 0, 0); g.clearRect(0, 0, S, S);
      let gr = g.createRadialGradient(R * 0.8, R * 0.7, R * 0.3, R, R, R);
      gr.addColorStop(0, '#5a5a56'); gr.addColorStop(1, '#151514');
      g.fillStyle = gr; g.beginPath(); g.arc(R, R, R, 0, 7); g.fill();
      g.fillStyle = '#f7f6f0'; g.beginPath(); g.arc(R, R, R * 0.86, 0, 7); g.fill();
      g.strokeStyle = '#111';
      for (let i = 0; i < 60; i++) {
        const a = i * 6 * D2R, maj = i % 5 === 0;
        g.lineWidth = maj ? 3 : 1;
        const r1 = R * 0.8, r2 = R * (maj ? 0.62 : 0.74);
        g.beginPath(); g.moveTo(R + Math.sin(a) * r1, R - Math.cos(a) * r1); g.lineTo(R + Math.sin(a) * r2, R - Math.cos(a) * r2); g.stroke();
      }
      g.fillStyle = '#333'; g.font = `600 7px ${FL}`; g.textAlign = 'center'; g.fillText('SYNCHRON 220 V ~', R, R + R * 0.42);
      const tod = P.tod % 86400, hh = tod / 3600, mm = (tod % 3600) / 60, ss = tod % 60;
      const hand = (a, len, w, col, tail = 0.15) => {
        g.strokeStyle = col; g.lineWidth = w; g.lineCap = 'butt';
        g.beginPath(); g.moveTo(R - Math.sin(a) * R * tail, R + Math.cos(a) * R * tail); g.lineTo(R + Math.sin(a) * len, R - Math.cos(a) * len); g.stroke();
      };
      g.save(); g.translate(1.5, 2); g.globalAlpha = 0.2;
      hand((hh % 12) * 30 * D2R, R * 0.48, 5, '#000'); hand(mm * 6 * D2R, R * 0.72, 3.5, '#000'); g.restore();
      hand((hh % 12) * 30 * D2R, R * 0.48, 5, '#111');
      hand(mm * 6 * D2R, R * 0.72, 3.5, '#111');
      hand(ss * 6 * D2R, R * 0.74, 1.2, '#b51b10', 0.25);
      g.fillStyle = '#111'; g.beginPath(); g.arc(R, R, 3, 0, 7); g.fill();
      const gl = g.createLinearGradient(0, 0, S, S); gl.addColorStop(0, 'rgba(255,255,255,.25)'); gl.addColorStop(0.4, 'rgba(255,255,255,0)');
      g.fillStyle = gl; g.beginPath(); g.arc(R, R, R * 0.86, 0, 7); g.fill();
    }
  }

  /* 3-pen strip-chart recorder */
  class Recorder {
    constructor(parent, o) {
      this.o = Object.assign({ w: 300, h: 262 }, o);
      const box = el('div', 'rec', parent);
      this.c = el('canvas', '', box);
      el('div', 'rglass', box);
      this.c.style.width = this.o.w + 'px'; this.c.style.height = this.o.h + 'px';
      this.ctx = this.c.getContext('2d');
      this.samples = []; this.lastT = -1;
      this.speeds = [300, 1200, 6000];   // mm/h
      METERS.push(this);
    }
    resize() { const k = this.k = kscale(); this.c.width = Math.round(this.o.w * k); this.c.height = Math.round(this.o.h * k); }
    seed() { this.samples = (P.hist || []).map(h => h.slice()); this.lastT = -1; }
    pxPerSec() { return this.speeds[P.sw.chart] / 3600 * 1.25; }
    step() {
      if (P.t - this.lastT >= Math.max(0.5, 1 / this.pxPerSec() / 3) || this.lastT < 0 || P.t < this.lastT) {
        this.lastT = P.t;
        this.samples.push([P.t, P.Pe * 300, P.hw, P.w * 100]);
        const maxAge = (this.o.h + 40) / this.pxPerSec() * 1.05;
        while (this.samples.length > 2 && P.t - this.samples[0][0] > Math.max(maxAge, 300)) this.samples.shift();
        if (this.samples.length > 6000) this.samples.splice(0, this.samples.length - 6000);
      }
    }
    draw() {
      const o = this.o, g = this.ctx, k = this.k, W = o.w, H = o.h;
      g.setTransform(k, 0, 0, k, 0, 0);
      g.fillStyle = '#efeadb'; g.fillRect(0, 0, W, H);
      const top = 30, pens = top + 10, x0 = 14, x1 = W - 14, cw = x1 - x0;
      // scale card
      g.fillStyle = '#fbf8ef'; g.fillRect(0, 0, W, top);
      g.strokeStyle = '#999'; g.lineWidth = 0.6; g.beginPath(); g.moveTo(0, top); g.lineTo(W, top); g.stroke();
      g.font = `600 7.5px ${FL}`; g.textBaseline = 'middle'; g.textAlign = 'center';
      const sc = [['#c0180c', 'kW', 0, 300, [0, 100, 200, 300]], ['#1f47b0', 'm ü.NN', 213.5, 215.5, [213.5, 214, 214.5, 215, 215.5]], ['#1b7a32', '% n', 0, 150, [0, 50, 100, 150]]];
      sc.forEach(([col, u, a, b, ticks], i) => {
        g.fillStyle = col;
        const y = 6 + i * 8.5;
        ticks.forEach(t => g.fillText(String(t), x0 + (t - a) / (b - a) * cw, y));
        g.textAlign = 'left'; g.fillText(u, x0 + cw * 0.10, y); g.textAlign = 'center';
      });
      // paper grid (moves)
      const pps = this.pxPerSec();
      g.save(); g.beginPath(); g.rect(0, top, W, H - top); g.clip();
      g.fillStyle = '#f3efe3'; g.fillRect(0, top, W, H - top);
      g.strokeStyle = 'rgba(46,130,80,.35)'; g.lineWidth = 0.5;
      for (let i = 0; i <= 10; i++) { const x = x0 + i * cw / 10; g.beginPath(); g.moveTo(x, top); g.lineTo(x, H); g.stroke(); }
      const gridSec = 5 / pps;    // a line every 5 px of paper (≈4 mm)
      const t0 = Math.floor(P.t / gridSec) * gridSec;
      for (let j = 0; j < 80; j++) {
        const tt = t0 - j * gridSec;
        const y = pens + (P.t - tt) * pps;
        if (y > H) break;
        const big = Math.round(tt / gridSec) % 5 === 0;
        g.strokeStyle = big ? 'rgba(46,130,80,.45)' : 'rgba(46,130,80,.18)'; g.lineWidth = big ? 0.7 : 0.4;
        g.beginPath(); g.moveTo(x0, y); g.lineTo(x1, y); g.stroke();
        if (big && Math.round(tt / gridSec) % 25 === 0) {
          const tod = (P.tod - (P.t - tt)) % 86400;
          const hh = String(Math.floor(tod / 3600)).padStart(2, '0'), mm = String(Math.floor(tod % 3600 / 60)).padStart(2, '0');
          g.fillStyle = 'rgba(46,110,70,.75)'; g.font = `500 7px ${FN}`; g.textAlign = 'left'; g.fillText(`${hh}:${mm}`, x0 + 2, y - 4);
        }
      }
      const cols = ['#c0180c', '#1f47b0', '#1b7a32'];
      const rng = [[0, 300], [213.5, 215.5], [0, 150]];
      for (let p = 0; p < 3; p++) {
        g.strokeStyle = cols[p]; g.lineWidth = 1; g.globalAlpha = 0.85;
        g.beginPath(); let first = true;
        for (let i = this.samples.length - 1; i >= 0; i--) {
          const s = this.samples[i];
          const y = pens + (P.t - s[0]) * pps;
          const x = x0 + clamp((s[p + 1] - rng[p][0]) / (rng[p][1] - rng[p][0]), 0, 1) * cw;
          if (first) { g.moveTo(x, y); first = false; } else g.lineTo(x, y);
          if (y > H) break;
        }
        g.stroke(); g.globalAlpha = 1;
      }
      g.restore();
      // pen carriages
      const cur = [P.Pe * 300, P.hw, P.w * 100];
      for (let p = 0; p < 3; p++) {
        const x = x0 + clamp((cur[p] - rng[p][0]) / (rng[p][1] - rng[p][0]), 0, 1) * cw;
        g.fillStyle = '#2a2a28'; g.fillRect(x - 3, pens - 9 - p * 0.5, 6, 7);
        g.fillStyle = cols[p]; g.fillRect(x - 1, pens - 2, 2, 3);
      }
      g.fillStyle = '#3a3a36'; g.fillRect(0, pens - 11, W, 1.2);
      g.fillStyle = 'rgba(0,0,0,.6)'; g.font = `600 7px ${FL}`; g.textAlign = 'right';
      g.fillText(`${this.speeds[P.sw.chart]} mm/h`, W - 4, H - 6);
    }
  }

  /* ===================================================================
     PANEL HARDWARE (DOM)
     =================================================================== */
  class Lamp {
    constructor(parent, color, size = '') {
      this.e = el('div', `lamp ${color} ${size}`, parent); el('i', '', this.e);
      this.state = false;
    }
    set(on) { if (on !== this.state) { this.state = on; this.e.classList.toggle('on', on); } }
  }
  let LAMPTEST = false;
  function lamp(parent, color, label, fn, opts = {}) {
    const cell = el('div', 'cell', parent);
    const L = new Lamp(cell, color, opts.size || '');
    if (label) el('div', 'lbl' + (opts.sm ? ' sm' : ''), cell, label);
    UPD.push(() => {
      let v = fn();
      if (v === 'f') v = FLASH.fast; else if (v === 's') v = FLASH.slow;
      L.set(!!v || LAMPTEST);
    });
    return L;
  }
  function pushbutton(parent, color, label, onDown, onUp, opts = {}) {
    const cell = el('div', 'cell', parent);
    if (opts.top) tag(cell, opts.top, 's');
    const b = el('button', 'pb ' + color + (opts.sq ? ' sq' : ''), cell);
    b.type = 'button'; b.setAttribute('aria-label', label.replace(/<[^>]+>/g, ' '));
    if (opts.id) b.id = opts.id;
    el('b', '', b);
    const down = e => { e.preventDefault(); b.classList.add('down'); AU.click(); onDown && onDown(); };
    const up = () => { if (!b.classList.contains('down')) return; b.classList.remove('down'); onUp && onUp(); };
    b.addEventListener('pointerdown', down);
    b.addEventListener('pointerup', up); b.addEventListener('pointerleave', up); b.addEventListener('pointercancel', up);
    b.addEventListener('keydown', e => { if (e.key === ' ' || e.key === 'Enter') { if (!b.classList.contains('down')) down(e); } });
    b.addEventListener('keyup', e => { if (e.key === ' ' || e.key === 'Enter') up(); });
    if (label) el('div', 'lbl', cell, label);
    if (opts.lit) UPD.push(() => b.classList.toggle('lit', !!opts.lit() || LAMPTEST));
    return b;
  }

  /* cam switch / selector with engraved escutcheon */
  function rotary(parent, o) {
    o = Object.assign({ knob: 'pistol', spring: false, label: '', radius: 29, size: 74 }, o);
    const cell = el('div', 'cell', parent);
    const r = el('div', 'rot', cell);
    const half = o.size / 2 - 6;
    if (o.size !== 74) { r.style.width = r.style.height = o.size + 'px'; }
    r.tabIndex = 0; r.setAttribute('role', 'slider');
    r.setAttribute('aria-label', (o.label || '').replace(/<[^>]+>/g, ' '));
    if (o.id) r.id = o.id;
    const plate = el('div', 'plate', r);
    const pls = o.pos.map(p => {
      const a = p.a * D2R, rr = o.radius;
      const s = el('span', 'pl', plate, p.t);
      s.style.left = (half + Math.sin(a) * rr) + 'px'; s.style.top = (half - Math.cos(a) * rr) + 'px';
      return s;
    });
    el('span', 'scr', plate).style.cssText = 'left:3px;bottom:3px';
    el('span', 'scr', plate).style.cssText = 'right:3px;bottom:3px';
    const kw = el('div', 'knobw', r);
    const knob = el('div', 'knob ' + o.knob + (o.red ? ' red' : ''), kw);
    const hl = el('div', 'hit l', r), hr = el('div', 'hit r', r);
    let idx = Math.max(0, o.pos.findIndex(p => p.v === o.get()));
    const show = () => {
      knob.style.transform = `rotate(${o.pos[idx].a}deg)`;
      pls.forEach((s, i) => s.classList.toggle('on', i === idx));
      r.setAttribute('aria-valuetext', o.pos[idx].t || 'neutral');
    };
    const go = (i, silent) => {
      i = clamp(i, 0, o.pos.length - 1);
      if (i === idx) return;
      idx = i; show(); if (!silent) AU.detent();
      o.set(o.pos[idx].v);
    };
    if (o.spring) {
      const center = o.pos.findIndex(p => p.v === 0);
      const press = (d) => e => { e.preventDefault(); e.stopPropagation(); go(center + d); };
      const rel = () => { if (idx !== center) go(center); };
      hl.addEventListener('pointerdown', press(-1)); hr.addEventListener('pointerdown', press(1));
      [hl, hr].forEach(h => { h.addEventListener('pointerup', rel); h.addEventListener('pointerleave', rel); h.addEventListener('pointercancel', rel); });
      r.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') go(center - 1); if (e.key === 'ArrowRight') go(center + 1); });
      r.addEventListener('keyup', e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') rel(); });
      r.addEventListener('blur', rel);
    } else {
      hl.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); go(idx - 1); });
      hr.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); go(idx + 1); });
      r.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') go(idx - 1); if (e.key === 'ArrowRight') go(idx + 1); });
      UPD.push(() => { const j = o.pos.findIndex(p => p.v === o.get()); if (j >= 0 && j !== idx) { idx = j; show(); } });
    }
    show();
    if (o.label) tag(cell, o.label, o.tagcls || 's');
    return cell;
  }
  const spring = (parent, label, key, lo = 'LOWER', hi = 'RAISE', id) => rotary(parent, {
    label, spring: true, knob: 'pistol', id,
    pos: [{ t: lo, a: -45, v: -1 }, { t: '', a: 0, v: 0 }, { t: hi, a: 45, v: 1 }],
    get: () => P.hold[key], set: v => { P.hold[key] = v; },
  });
  const tri = (parent, label, key, labels = ['OFF', 'AUTO', 'ON'], id) => rotary(parent, {
    label, knob: 'pistol', id,
    pos: [{ t: labels[0], a: -45, v: labels[0] }, { t: labels[1], a: 0, v: labels[1] }, { t: labels[2], a: 45, v: labels[2] }],
    get: () => P.sw[key], set: v => { P.sw[key] = v; PL.log('OP', `${label.replace(/<[^>]+>/g, ' ')}: ${v}`); },
  });

  class Counter {
    constructor(parent, nInt, nDec, cls = '') {
      this.e = el('div', 'ctr ' + cls, parent);
      this.n = nInt + nDec; this.dec = nDec; this.strips = [];
      for (let i = 0; i < this.n; i++) {
        const d = el('div', 'd' + (i >= nInt ? ' r' : ''), this.e);
        const s = el('div', 's', d, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0].map(x => `<div>${x}</div>`).join(''));
        this.strips.unshift(s);
      }
      this.last = -1;
    }
    set(v) {
      const x = v * Math.pow(10, this.dec);
      if (Math.abs(x - this.last) < 0.004) return;
      this.last = x;
      let prev = 0;
      for (let i = 0; i < this.n; i++) {
        const p = Math.pow(10, i);
        let pos;
        if (i === 0) pos = x % 10;
        else pos = (Math.floor(x / p) % 10) + (prev > 9 ? prev - 9 : 0);
        this.strips[i].style.transform = `translateY(${-pos * 17}px)`;
        prev = i === 0 ? pos : (Math.floor(x / p) % 10 === 9 ? pos : 0);
      }
    }
  }

  /* ---------- event printer ---------- */
  const PRINTER = {
    lastId: 0, queue: [], busy: 0,
    fmt(e) {
      const t = e.t % 86400;
      const hh = String(Math.floor(t / 3600)).padStart(2, '0'), mm = String(Math.floor(t % 3600 / 60)).padStart(2, '0'), ss = String(Math.floor(t % 60)).padStart(2, '0');
      return `${hh}:${mm}:${ss} ${e.tag.padEnd(5).slice(0, 5)} ${e.msg}`.slice(0, 66);
    },
    pump(dt) {
      for (const e of PL.events) {
        if (e.id <= this.lastId) continue;
        this.lastId = e.id;
        this.queue.push(e);
        if (e.kind === 'cb') AU.clunk();
        else if (e.kind === 'trip' || e.kind === 'seq') AU.relay();
      }
      if (this.queue.length > 30) this.queue.splice(0, this.queue.length - 30);
      this.busy -= dt;
      if (this.busy <= 0 && this.queue.length && this.paper) {
        const e = this.queue.shift();
        const ln = el('div', 'ln ' + (e.kind === 'trip' ? 'trip' : e.kind === 'alarm' ? 'alarm' : ''), this.paper, '');
        ln.textContent = this.fmt(e);
        while (this.paper.children.length > 40) this.paper.removeChild(this.paper.firstChild);
        this.carr.style.left = (8 + Math.random() * 70) + '%';
        AU.printer(18);
        this.busy = 0.28;
      }
    },
  };

  /* ===================================================================
     CABINET SCAFFOLDING
     =================================================================== */
  const lineup = document.getElementById('lineup');
  const CABS = [];
  function cabinet(code, name, sub, width) {
    const cab = el('div', 'cab', lineup);
    cab.style.setProperty('--cw', width + 'px');
    cab.id = 'cab-' + code.replace(/[^A-Za-z0-9]/g, '');
    const top = el('div', 'cab-top', cab);
    const l1 = el('div', 'louv', top); l1.style.left = '24px';
    const l2 = el('div', 'louv', top); l2.style.right = '24px';
    const lf1 = el('div', 'lifting', top); lf1.style.left = '18px';
    const lf2 = el('div', 'lifting', top); lf2.style.right = '18px';
    const door = el('div', 'door', cab);
    const h1 = el('div', 'hinge', door); h1.style.top = '70px';
    const h2 = el('div', 'hinge', door); h2.style.bottom = '70px';
    el('div', 'handle', door);
    const np = el('div', 'np', door);
    el('div', 'code', np, code);
    const nm = el('div', 'name', np, `${name}<small>${sub}</small>`);
    el('span', 'scr', nm).style.cssText = 'left:4px;top:50%;margin-top:-3.5px';
    el('span', 'scr', nm).style.cssText = 'right:4px;top:50%;margin-top:-3.5px';
    el('span', 'lock', door);
    el('div', 'plinth', cab);
    CABS.push({ code, name, el: cab });
    return door;
  }
  function section(parent, title, cls = '') {
    const s = el('div', 'sec ' + cls, parent);
    if (title) { const t = tag(s, title); t.classList.add('st'); }
    return s;
  }
  const row = (p, cls = '') => el('div', 'row ' + cls, p);
  const col = (p, cls = '') => el('div', 'col ' + cls, p);
  function meterCell(parent, opts, label, extra) {
    const cell = el('div', 'cell', parent);
    const m = new Meter(cell, opts);
    if (label) tag(cell, label, 's');
    if (extra) extra(cell);
    return m;
  }

  const AMBER = '#e8a019', RED = '#c9271a', GREEN = '#3f8f45';
  const DSW = [];

  /* ===================================================================
     +A1  UNIT CONTROL
     =================================================================== */
  (() => {
    const d = cabinet('+A1', 'UNIT CONTROL', 'MASCHINENSTEUERUNG · SEQUENCE · AUXILIARIES', 610);
    const r0 = row(d, 'c');
    const ck = el('div', 'cell', r0); new Clock(ck, 118); tag(ck, 'STATION TIME', 's');
    const cnt = col(r0);
    const c1 = el('div', 'cell', cnt); const hrs = new Counter(c1, 6, 1); tag(c1, 'OPERATING HOURS  h', 's');
    const c2 = el('div', 'cell', cnt); const sts = new Counter(c2, 5, 0, 'blk'); tag(c2, 'STARTS', 's');
    UPD.push(() => { hrs.set(P.hours); sts.set(P.starts); });
    meterCell(r0, { w: 96, h: 96, min: 0, max: 150, major: 25, minor: 5, labelStep: 50, unit: 'V', title: 'DC 110 V', redline: 105, value: () => P.dcV, zones: [{ f: 0, t: 100, c: RED }] }, 'BATTERY 110 V DC');
    meterCell(r0, { w: 96, h: 96, min: 0, max: 40, major: 10, minor: 2, labelStep: 20, unit: 'A', title: 'CHARGER', value: () => P.chargerA }, 'CHARGER CURRENT');

    const sq = section(d, 'UNIT SEQUENCE · AUTOMATIC START / STOP');
    const sr = row(sq);
    const steps = el('div', '', sr);
    steps.style.cssText = 'display:grid;grid-template-columns:repeat(2,auto);gap:5px 14px;padding-top:6px';
    const stepDef = [
      ['READY TO START', () => PL.readyToStart(), 'white'],
      ['AUXILIARIES ON', () => P.cwFlow > 0.85 && (P.liftP > 0.85 || P.w > 0.9), 'red'],
      ['BRAKES RELEASED', () => P.brakePos < 0.02, 'red'],
      ['GOVERNOR ON', () => P.govOn, 'red'],
      ['SPEED > 95 %', () => P.w > 0.95, 'red'],
      ['EXCITATION ON', () => P.fcb, 'red'],
      ['READY TO SYNC', () => P.seq === 'S5_SNL' && P.Vt > 0.9 ? true : false, 'white'],
      ['UNIT ON LINE', () => P.cb, 'red'],
      ['STOP SEQUENCE', () => P.seq.startsWith('T') ? 'f' : false, 'amber'],
      ['UNIT STOPPED', () => P.w < 0.002 && !P.govOn, 'green'],
      ['SEQUENCE FAULT', () => P.seqFault ? 's' : false, 'amber'],
      ['MANUAL CONTROL', () => P.sw.unitMode === 'MAN', 'amber'],
    ];
    for (const [t, fn, c] of stepDef) {
      const r = el('div', '', steps); r.style.cssText = 'display:flex;align-items:center;gap:7px';
      const L = new Lamp(r, c, 'sm'); el('span', 'lbl', r, t).style.cssText = 'font:600 9.5px/1 var(--f-label);letter-spacing:.07em';
      UPD.push(() => { let v = fn(); if (v === 'f') v = FLASH.fast; if (v === 's') v = FLASH.slow; L.set(!!v || LAMPTEST); });
      // also blink the step currently in progress
      if (t === 'GOVERNOR ON') UPD.push(() => { if (P.seq === 'S3_ACCEL') L.set(FLASH.slow || P.govOn); });
    }
    const ctl = col(sr);
    rotary(ctl, {
      label: 'UNIT CONTROL', knob: 'key', id: 'unitMode',
      pos: [{ t: 'MAN', a: -45, v: 'MAN' }, { t: 'AUTO', a: 45, v: 'AUTO' }],
      get: () => P.sw.unitMode, set: v => { P.sw.unitMode = v; },
    });
    const pbr = row(ctl);
    pushbutton(pbr, 'green', 'START', () => PL.cmdStart(), null, { id: 'btnStart', lit: () => /^S[1-4]/.test(P.seq) && FLASH.slow });
    pushbutton(pbr, 'red', 'STOP', () => PL.cmdStop(), null, { id: 'btnStop', lit: () => P.seq.startsWith('T') && FLASH.slow });
    const es = el('div', 'cell', sr);
    const estop = el('div', 'estop', es);
    estop.id = 'estop'; estop.setAttribute('role', 'button'); estop.tabIndex = 0; estop.setAttribute('aria-label', 'Emergency stop');
    el('div', 'mush', estop);
    estop.insertAdjacentHTML('beforeend', `<svg viewBox="0 0 84 84" aria-hidden="true"><defs><path id="eRing" d="M42,42 m-35.5,0 a35.5,35.5 0 1,1 71,0 a35.5,35.5 0 1,1 -71,0"/></defs>
      <text><textPath href="#eRing" startOffset="2%">EMERGENCY STOP · NOT-AUS · EMERGENCY STOP · NOT-AUS ·</textPath></text></svg>`);
    const toggleE = () => { const on = !P.estop; PL.cmdEstop(on); AU.clunk(); };
    estop.addEventListener('pointerdown', e => { e.preventDefault(); toggleE(); });
    estop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleE(); } });
    UPD.push(() => estop.classList.toggle('down', P.estop));
    tag(es, 'EMERGENCY STOP');
    el('div', 'lbl sm', es, 'PUSH · CLICK AGAIN<br>TO TWIST-RELEASE');

    const ax = section(d, 'AUXILIARIES · NEBENANTRIEBE');
    const ar = row(ax); ar.style.paddingTop = '6px';
    const auxCol = (title, key, labels, runFn, faultFn, runTxt = 'RUN') => {
      const c = col(ar);
      const lr = row(c); lr.style.gap = '12px';
      lamp(lr, 'red', runTxt, runFn, { sm: true });
      lamp(lr, 'amber', 'FAULT', faultFn, { sm: true });
      tri(c, title, key, labels);
    };
    auxCol('COOLING<br>WATER PUMP', 'cw', ['OFF', 'AUTO', 'ON'], () => P.cw, () => (P.flt.cw && (P.sw.cw === 'ON' || P.req.cw)) ? 'f' : false);
    auxCol('OIL LIFT<br>PUMP (HP)', 'lift', ['OFF', 'AUTO', 'ON'], () => P.lift, () => (P.w > 0.01 && P.w < 0.3 && P.liftP < 0.5) ? 'f' : false);
    auxCol('GENERATOR<br>BRAKES', 'brake', ['RELEASE', 'AUTO', 'APPLY'], () => P.brakePos > 0.98, () => (P.brakePos > 0.1 && P.w > 0.35) ? 'f' : false, 'APPLIED');
    auxCol('TRASH RACK<br>CLEANER', 'rake', ['OFF', 'AUTO', 'ON'], () => P.rakeRun, () => P.rackDh > 0.25 ? 's' : false);

    const ig = section(d, 'INTAKE GATE · EINLAUFSCHÜTZ');
    const igr = row(ig, 'c'); igr.style.paddingTop = '6px';
    meterCell(igr, { kind: 'edge', w: 50, h: 150, min: 0, max: 100, major: 20, minor: 5, labelEvery: 1, unit: '%', value: () => P.intake * 100, wn: 6 }, 'POSITION');
    const igc = col(igr);
    const igb = row(igc);
    pushbutton(igb, 'red', 'OPEN', () => PL.intake('OPEN'), null, { lit: () => P.intakeCmd > 0 && FLASH.slow });
    pushbutton(igb, 'black', 'STOP', () => PL.intake('STOP'));
    pushbutton(igb, 'green', 'CLOSE', () => PL.intake('CLOSE'), null, { lit: () => (P.intakeCmd < 0 || P.intakeEmerg) && FLASH.slow });
    const igl = row(igc);
    lamp(igl, 'red', 'OPEN', () => P.intake > 0.995, { sm: true });
    lamp(igl, 'green', 'CLOSED', () => P.intake < 0.005, { sm: true });
    lamp(igl, 'amber', 'EMERG.<br>CLOSING', () => P.intakeEmerg ? 'f' : false, { sm: true });
    const sup = col(igr);
    tag(sup, 'STATION SUPPLY', 's');
    const sl = row(sup);
    lamp(sl, 'white', 'AC AUX<br>400 V', () => P.acAux, { sm: true });
    lamp(sl, 'white', 'CHARGER<br>ON', () => P.acAux && !P.flt.charger, { sm: true });
    lamp(sl, 'amber', 'DC<br>LOW', () => P.dcV < 108, { sm: true });
    const card = el('div', 'card', sup);
    card.innerHTML = '<b>START-UP (AUTO)</b><br>1 UNIT CONTROL → AUTO<br>2 Check READY lamp<br>3 Push START<br>4 Sync: +A4 selector AUTO<br>&nbsp;&nbsp;or MAN + 52G switch<br><i>full manual → MANUAL btn</i>';
    card.style.maxWidth = '178px';
    card.addEventListener('click', () => openManual());
    const tp = el('span', 'dymo red', d, 'DO NOT OPEN DOOR WHILE UNIT ON LINE'); tp.style.alignSelf = 'center';
    // shift log on a clipboard hanging from the door
    const cb = el('div', 'clip', d);
    el('div', 'clamp', cb);
    const sheet = el('div', 'logsheet', cb);
    const dt = new Date(), dd = String(dt.getDate()).padStart(2, '0'), mo = String(dt.getMonth() + 1).padStart(2, '0');
    sheet.innerHTML = `<div class="lh">SHIFT LOG · UNIT 1 · ${dd}.${mo}.88</div>
      <div>06:00&nbsp; Shift A on. U1 on line 228 kW, OW 214.51</div>
      <div>06:40&nbsp; Rack cleaner ran, Δh 0.22 → 0.06</div>
      <div>08:15&nbsp; OPU pump 2 noisy again — told maint.</div>
      <div>10:30&nbsp; Utility phoned: line work Oberdorf Thu.</div>
      <div>12:10&nbsp; Thrust brg 56°, all temps normal. — K.B.</div>`;
  })();

  /* ===================================================================
     +A2  TURBINE GOVERNOR
     =================================================================== */
  (() => {
    const d = cabinet('+A2', 'TURBINE GOVERNOR', 'TURBINENREGLER · ELECTRO-HYDRAULIC PID · KAPLAN DOUBLE REGULATION', 630);
    const r1 = row(d, 'c');
    meterCell(r1, {
      w: 150, h: 150, a0: -120, a1: 120, pivot: [0.5, 0.55], r: 0.37, min: 0, max: 150, major: 10, minor: 5, labelEvery: 2.5,
      fmt: v => String(v), unit: '% n', title: 'TURBINE SPEED', title2: '100 % = 83.3 min⁻¹', mirror: true, klass: '1.0', wn: 7, zeta: 0.6,
      marks: (() => { const m = []; for (let v = 0; v <= 150; v += 5) m.push({ v, M: v % 25 === 0, half: v % 10 === 0 && v % 25 !== 0, label: v % 25 === 0 ? String(v) : null }); return m; })(),
      zones: [{ f: 110, t: 140, c: AMBER }, { f: 140, t: 150, c: RED }],
      value: () => P.w * 100,
    }, 'SPEED  (TACHO GENERATOR)');
    const r1b = col(r1);
    const r1c = row(r1b);
    meterCell(r1c, { min: 0, max: 100, major: 10, minor: 2, labelStep: 20, unit: '%', title: 'GUIDE VANES', value: () => P.gate * 100, wn: 8 }, 'GATE OPENING');
    meterCell(r1c, {
      min: -8, max: 28, major: 5, minor: 1, labelStep: 10, unit: '°', title: 'RUNNER BLADES', value: () => PL.bladeDeg(P.blade), wn: 8,
      marks: (() => { const m = []; for (let v = -8; v <= 28; v++) m.push({ v, M: v % 5 === 0, half: false, label: v % 10 === 0 ? String(v) : null }); return m; })(),
    }, 'BLADE ANGLE');
    meterCell(r1c, { min: 0, max: 12, major: 2, minor: 0.5, labelStep: 4, unit: 'm³/s', title: 'WINTER-KENNEDY', value: () => P.q, wn: 5, redline: 8.6 }, 'TURBINE DISCHARGE');
    const r2 = row(d, 'c');
    meterCell(r2, { min: 0, max: 100, major: 10, minor: 2, labelStep: 20, unit: '%', title: 'GATE LIMIT', value: () => P.gateLimit * 100, wn: 6, needle: '#9b1a10' }, 'GATE LIMITER');
    meterCell(r2, { min: 90, max: 110, major: 5, minor: 1, labelStep: 5, unit: '% n', title: 'SPEED REF', value: () => P.nref * 100, wn: 6, needle: '#9b1a10' }, 'SPEED SETPOINT');
    meterCell(r2, { min: 0, max: 300, major: 50, minor: 10, labelStep: 100, unit: 'kW', title: 'LOAD REF', value: () => P.pref * 300, wn: 6, needle: '#9b1a10', redline: 250 }, 'LOAD SETPOINT');
    meterCell(r2, {
      kind: 'round', w: 118, h: 118, a0: -135, a1: 135, r: 0.35, min: 0, max: 60, major: 10, minor: 2, labelStep: 10, unit: 'bar', title: 'ACCUMULATOR',
      zones: [{ f: 0, t: 28, c: RED }, { f: 28, t: 34, c: AMBER }, { f: 36, t: 40, c: GREEN }], klass: 'Kl.1.6', maker: 'MANO-WERK', wn: 9, zeta: 0.75, value: () => P.oilP,
    }, 'OIL PRESSURE');

    const gc = section(d, 'GOVERNOR CONTROL');
    const g1 = row(gc); g1.style.paddingTop = '6px';
    rotary(g1, {
      label: 'GOVERNOR MODE', knob: 'pistol', id: 'govMode', size: 96, radius: 38,
      pos: [{ t: 'MAN', a: -72, v: 'MAN' }, { t: 'SPEED', a: -26, v: 'SPEED' }, { t: 'LOAD', a: 26, v: 'LOAD' }, { t: 'LEVEL', a: 72, v: 'LEVEL' }],
      get: () => P.sw.gov, set: v => { P.sw.gov = v; PL.log('GOV', 'GOVERNOR MODE ' + v); },
    });
    rotary(g1, {
      label: 'PERM. DROOP bp', knob: 'round', size: 84, radius: 32,
      pos: [{ t: '0', a: -66, v: 0 }, { t: '2', a: -22, v: 2 }, { t: '4', a: 22, v: 4 }, { t: '6 %', a: 66, v: 6 }],
      get: () => P.sw.droop, set: v => { P.sw.droop = v; },
    });
    spring(g1, 'GATE LIMIT', 'gateLimit', 'LOWER', 'RAISE', 'swGateLimit');
    spring(g1, 'SPEED SETPOINT', 'nref', 'LOWER', 'RAISE', 'swNref');
    spring(g1, 'LOAD SETPOINT', 'pref', 'LOWER', 'RAISE', 'swPref');
    const g2 = row(gc);
    spring(g2, 'MANUAL GATE', 'manGate', 'CLOSE', 'OPEN', 'swManGate');
    rotary(g2, {
      label: 'BLADE CONTROL', knob: 'pistol',
      pos: [{ t: 'CAM', a: -45, v: 'AUTO' }, { t: 'MAN', a: 45, v: 'MAN' }],
      get: () => P.sw.blade, set: v => { P.sw.blade = v; PL.log('GOV', 'BLADE CONTROL ' + (v === 'AUTO' ? 'CAM (AUTO)' : 'MANUAL')); },
    });
    spring(g2, 'MANUAL BLADES', 'manBlade', 'CLOSE', 'OPEN');
    spring(g2, 'LEVEL SETPOINT', 'level', 'LOWER', 'RAISE', 'swLevel');
    const gl = col(g2); gl.style.gap = '6px';
    const glr1 = row(gl);
    lamp(glr1, 'red', 'GOV<br>ON', () => P.govOn, { sm: true });
    lamp(glr1, 'amber', 'START<br>OPEN', () => P.startPhase, { sm: true });
    const glr2 = row(gl);
    lamp(glr2, 'amber', 'LIMIT<br>ACTIVE', () => P.govOn && P.y >= P.gateLimit - 0.002 && P.gateLimit < 0.999, { sm: true });
    lamp(glr2, 'red', 'EMERG.<br>CLOSE', () => P.emergClose ? 'f' : false, { sm: true });

    const op = section(d, 'OIL PRESSURE UNIT · DRUCKÖLANLAGE  40 bar');
    const o1 = row(op, 'c'); o1.style.paddingTop = '6px';
    meterCell(o1, { kind: 'edge', w: 46, h: 120, min: 0, max: 100, major: 25, minor: 5, labelEvery: 1, unit: '%', value: () => P.oilLvl * 100, zones: [{ f: 0, t: 25, c: RED }, { f: 25, t: 35, c: AMBER }], wn: 4 }, 'SUMP LEVEL');
    const pc = col(o1);
    const pr = row(pc);
    lamp(pr, 'red', 'PUMP 1<br>RUN', () => P.p1Run, { sm: true });
    lamp(pr, 'amber', 'PUMP 1<br>FAULT', () => P.flt.pump1 && P.pump1 ? 'f' : false, { sm: true });
    lamp(pr, 'red', 'PUMP 2<br>RUN', () => P.p2Run, { sm: true });
    lamp(pr, 'amber', 'PUMP 2<br>FAULT', () => P.flt.pump2 && P.pump2 ? 'f' : false, { sm: true });
    const pr2 = row(pc);
    tri(pr2, 'PUMP 1', 'pump1');
    tri(pr2, 'PUMP 2', 'pump2');
    rotary(pr2, { label: 'LEAD PUMP', knob: 'round', pos: [{ t: '1', a: -45, v: 1 }, { t: '2', a: 45, v: 2 }], get: () => P.sw.lead, set: v => { P.sw.lead = v; } });
    const ol = col(o1);
    lamp(ol, 'amber', 'p < 32 bar', () => P.oilP < 32, { sm: true });
    lamp(ol, 'amber', 'CREEP<br>DETECTOR', () => P.seq === 'STOPPED' && P.w > 0.002 ? 'f' : false, { sm: true });
    lamp(ol, 'white', 'BLADES<br>START POS', () => Math.abs(P.blade - 0.35) < 0.01 && !P.cb, { sm: true });
    const tu = section(d, 'TURBINE · WATER WAY');
    const tr = row(tu, 'c'); tr.style.paddingTop = '6px';
    meterCell(tr, { min: 0, max: 5, major: 1, minor: 0.1, labelStep: 1, unit: 'm', title: 'OW − UW − Δh', value: () => P.hn, wn: 4, redline: 3.5 }, 'NET HEAD');
    meterCell(tr, {
      min: 0, max: 250, major: 50, minor: 10, labelStep: 100, unit: 'µm', title: 'SHAFT p-p', value: () => P.vib, wn: 5, zeta: 0.7,
      zones: [{ f: 120, t: 180, c: AMBER }, { f: 180, t: 250, c: RED }],
    }, 'SHAFT VIBRATION');
    meterCell(tr, {
      kind: 'round', w: 104, h: 104, a0: -135, a1: 135, r: 0.35, min: 0, max: 6, major: 1, minor: 0.2, labelStep: 1, unit: 'bar', title: 'SEAL WATER',
      zones: [{ f: 0, t: 1.5, c: RED }], klass: 'Kl.2.5', maker: 'MANO-WERK', wn: 7, zeta: 0.7, value: () => P.sealP,
    }, 'SHAFT SEAL');
    const tl = col(tr);
    lamp(tl, 'amber', 'SEAL WATER<br>LOW', () => P.w > 0.1 && P.sealP < 1.5, { sm: true });
    lamp(tl, 'amber', 'VIBRATION<br>HIGH', () => P.vib > 120 ? 's' : false, { sm: true });
    const dy = el('span', 'dymo', d, 'PUMP 2 NOISY - SEE LOGBOOK 14.10.'); dy.style.alignSelf = 'flex-end';
  })();

  /* ===================================================================
     +A3  GENERATOR & EXCITATION
     =================================================================== */
  (() => {
    const d = cabinet('+A3', 'GENERATOR & EXCITATION', 'GENERATOR · ERREGUNG · AVR', 630);
    const pl = el('div', 'plate-metal', d);
    pl.innerHTML = `<b>SYNCHRON-GENERATOR  3~</b> &nbsp; Typ SGV 72/315 &nbsp; Nr. 88-4471 &nbsp; Bj. 1988
      <table><tr><td>300 kVA</td><td>400 V Y</td><td>433 A</td><td>cos φ 0.85</td><td>50 Hz</td></tr>
      <tr><td>83.3 min⁻¹</td><td>72 poles</td><td>Exc. 62 V 44 A</td><td>Isol.-Kl. F</td><td>IP 23</td></tr></table>`;
    [[3, 3], [3, null], [null, 3], [null, null]].forEach(([l, t]) => { const r = el('span', 'rv', pl); if (l !== null) r.style.left = l + 'px'; else r.style.right = '3px'; if (t !== null) r.style.top = '3px'; else r.style.bottom = '3px'; });

    const vsel = ['L1-L2', 'L2-L3', 'L3-L1', 'L1-N', 'L2-N', 'L3-N'];
    const vRead = () => {
      const s = P.sw.voltSel, f = P.flt.vtFuse;
      const ll = [1, 1.004, 0.997][s] || 1, ln = [0.998, 1.003, 1.0][s - 3] || 1;
      if (s < 3) { const k = f && (s === 0 || s === 2) ? 0.5 : 1; return P.Vt * 400 * ll * k; }
      return (f && s === 3) ? 0 : P.Vt * 231 * ln;
    };
    const m1 = row(d, 'c');
    const vc = el('div', 'cell', m1);
    const vr = row(vc, 'c');
    new Meter(vr, { min: 0, max: 500, major: 100, minor: 20, labelStep: 100, unit: 'V', title: 'STATOR', redline: 440, value: vRead, symbol: 'mi' });
    rotary(vr, {
      label: '', knob: 'round', radius: 30,
      size: 88, radius: 34,
      pos: vsel.map((t, i) => ({ t: t.replace('L', '').replace('-L', '-').replace('-N', 'N'), a: -75 + i * 30, v: i })),
      get: () => P.sw.voltSel, set: v => { P.sw.voltSel = v; },
    });
    tag(vc, 'GEN VOLTAGE · SELECTOR', 's');
    const ac = el('div', 'cell', m1);
    const ar = row(ac, 'c');
    new Meter(ar, {
      min: 0, max: 600, major: 100, minor: 20, labelEvery: 1, unit: 'A', title: 'CT 600/5 A', redline: 433, map: f => Math.pow(f, 1.22),
      marks: (() => { const m = []; for (let v = 0; v <= 600; v += 20) m.push({ v, M: v % 100 === 0, half: v % 50 === 0 && v % 100 !== 0, label: v % 200 === 0 ? String(v) : null }); return m; })(),
      value: () => P.I * 433 * [1, 1.012, 0.993][P.sw.ampSel],
    });
    rotary(ar, { label: '', knob: 'round', pos: [{ t: 'L1', a: -45, v: 0 }, { t: 'L2', a: 0, v: 1 }, { t: 'L3', a: 45, v: 2 }], get: () => P.sw.ampSel, set: v => { P.sw.ampSel = v; } });
    tag(ac, 'STATOR CURRENT · SELECTOR', 's');

    const m2 = row(d, 'c');
    meterCell(m2, { min: 45, max: 55, major: 1, minor: 0.2, labelStep: 5, unit: 'Hz', title: 'GENERATOR', value: () => P.Vt > 0.08 ? 50 * P.w : 0, rest: -0.03, live: () => P.Vt > 0.08, fmt: v => String(Math.round(v)), mirror: true }, 'FREQUENCY');
    meterCell(m2, {
      min: -50, max: 300, major: 50, minor: 10, labelStep: 100, unit: 'kW', title: '3~ ACTIVE', redline: 250, value: () => P.Pe * 300,
      zones: [{ f: -50, t: 0, c: RED }],
    }, 'ACTIVE POWER');
    meterCell(m2, {
      min: -150, max: 250, major: 50, minor: 10, labelStep: 100, unit: 'kvar', title: 'CAP  ←  → IND', value: () => P.Qe * 300,
      zones: [{ f: -150, t: -100, c: AMBER }],
    }, 'REACTIVE POWER');
    // power factor (crossed-coil): scale linear in φ, labelled in cos φ
    const pfMarks = []; [0.5, 0.6, 0.7, 0.8, 0.9, 0.95].forEach(c => { const a = Math.acos(c) * 180 / Math.PI; const lb = (c === 0.5 || c === 0.8) ? String(c).slice(1) : null; pfMarks.push({ v: -a, M: c !== 0.95, label: lb }); pfMarks.push({ v: a, M: c !== 0.95, label: lb }); });
    pfMarks.push({ v: 0, M: true, label: '1' });
    let lastPf = 0;
    meterCell(m2, {
      min: -60, max: 60, marks: pfMarks, unit: 'cos φ', title: 'CAP          IND', klass: '2.5',
      value: () => { if (P.I > 0.02) { const s = Math.hypot(P.Pe, P.Qe); lastPf = Math.atan2(P.Qe, Math.abs(P.Pe)) * 180 / Math.PI; void s; } return lastPf; },
      wn: 6,
    }, 'POWER FACTOR');

    const m3 = row(d, 'c');
    meterCell(m3, { min: 0, max: 60, major: 10, minor: 2, labelStep: 20, unit: 'A', title: 'FIELD  60 mV', redline: 44, value: () => P.If, wn: 7 }, 'FIELD CURRENT');
    meterCell(m3, { min: 0, max: 150, major: 25, minor: 5, labelStep: 50, unit: 'V', title: 'FIELD', value: () => P.Vf, wn: 7 }, 'FIELD VOLTAGE');
    const tc = el('div', 'cell', m3);
    const trr = row(tc, 'c');
    const tvals = [() => P.tTB, () => P.tUGB, () => P.tLGB, () => P.tTGB, () => P.tSt[0], () => P.tSt[1], () => P.tSt[2], () => P.oilT];
    new Meter(trr, { min: 0, max: 150, major: 25, minor: 5, labelStep: 50, unit: '°C', title: 'PT 100', value: () => tvals[P.sw.tempSel](), wn: 4, zeta: 0.8 });
    const tsel = col(trr); tsel.style.gap = '2px';
    rotary(tsel, {
      label: '', knob: 'round', size: 84, radius: 32,
      pos: [1, 2, 3, 4, 5, 6, 7, 8].map((n, i) => ({ t: String(n), a: -105 + i * 30, v: i })),
      get: () => P.sw.tempSel, set: v => { P.sw.tempSel = v; },
    });
    const leg = el('div', 'tag w s', tsel);
    leg.style.cssText = 'text-align:left;line-height:1.25;font-size:8px;white-space:pre';
    leg.textContent = '1 THRUST BRG   5 STATOR U\n2 UPPER GUIDE  6 STATOR V\n3 LOWER GUIDE  7 STATOR W\n4 TURB. GUIDE  8 OPU OIL';
    tag(tc, 'TEMPERATURE SCANNER', 's');

    const ex = section(d, 'EXCITATION · STATIC THYRISTOR · AVR');
    const e1 = row(ex); e1.style.paddingTop = '6px';
    const eb = col(e1);
    const ebr = row(eb);
    pushbutton(ebr, 'red', 'EXC<br>ON', () => PL.cmdExcOn(), null, { id: 'btnExcOn' });
    pushbutton(ebr, 'green', 'EXC<br>OFF', () => PL.cmdExcOff(), null, { id: 'btnExcOff' });
    const ebl = row(eb);
    lamp(ebl, 'red', 'FCB 41<br>CLOSED', () => P.fcb, { sm: true });
    lamp(ebl, 'green', 'FCB 41<br>OPEN', () => !P.fcb, { sm: true });
    lamp(ebl, 'amber', 'FIELD<br>FLASHING', () => P.flashing, { sm: true });
    rotary(e1, {
      label: 'AVR MODE', knob: 'pistol', id: 'avrMode', size: 92, radius: 36,
      pos: [{ t: 'MAN If', a: -62, v: 'MAN' }, { t: 'AUTO U', a: 0, v: 'AUTO' }, { t: 'cos φ', a: 62, v: 'PF' }],
      get: () => P.sw.avr, set: v => { P.sw.avr = v; PL.log('AVR', 'AVR MODE ' + v); },
    });
    spring(e1, 'VOLTAGE / FIELD', 'avr', 'LOWER', 'RAISE', 'swAvr');
    rotary(e1, {
      label: 'cos φ SETPOINT', knob: 'round', size: 92, radius: 36,
      pos: [{ t: '.85i', a: -76, v: 0.85 }, { t: '.90i', a: -38, v: 0.90 }, { t: '.95i', a: 0, v: 0.95 }, { t: '1.0', a: 38, v: 1.0 }, { t: '.95c', a: 76, v: -0.95 }],
      get: () => P.sw.pf, set: v => { P.sw.pf = v; },
    });
    const el2 = col(e1); el2.style.gap = '5px';
    const elr = row(el2);
    lamp(elr, 'amber', 'LIMITER<br>OEL/UEL', () => P.limActive, { sm: true });
    lamp(elr, 'amber', 'U/f<br>LIMIT', () => P.vhzLim && P.fcb, { sm: true });
    const elr2 = row(el2);
    lamp(elr2, 'amber', 'AVR AUTO<br>FAULT', () => P.flt.avr && P.fcb ? 's' : false, { sm: true });
    lamp(elr2, 'white', 'MAN<br>FOLLOW-UP', () => P.fcb && P.sw.avr !== 'MAN' && !P.flt.avr, { sm: true });
    meterCell(e1, { kind: 'edge', w: 46, h: 104, min: 90, max: 110, major: 5, minor: 1, labelEvery: 1, unit: '%U', value: () => P.vref * 100, wn: 5 }, 'U SET');

    const ga = section(d, 'GENERATOR AUXILIARIES · INSULATION');
    const gr = row(ga, 'c'); gr.style.paddingTop = '6px';
    meterCell(gr, {
      min: 0, max: 100, major: 20, minor: 5, labelStep: 20, unit: '°C', title: 'COLD blk · HOT red', value: () => P.airC, value2: () => P.airH, needle2: '#b5180c', wn: 3, zeta: 0.8,
      zones: [{ f: 70, t: 100, c: AMBER }],
    }, 'COOLER AIR');
    meterCell(gr, {
      min: 0, max: 250, major: 50, minor: 10, labelStep: 100, unit: 'V', title: 'U0 NEUTRAL VT', value: () => P.U0, wn: 8,
      zones: [{ f: 23, t: 250, c: RED }],
    }, 'STATOR E/F 64S');
    const hc = col(gr);
    tri(hc, 'SPACE<br>HEATERS', 'heater');
    lamp(hc, 'white', 'HEATERS ON', () => P.heater && P.acAux, { sm: true });
    const gl2 = col(gr);
    lamp(gl2, 'white', 'COOLER<br>WATER ON', () => P.cwFlow > 0.6, { sm: true });
    lamp(gl2, 'amber', 'AIR TEMP<br>HIGH', () => P.airH > 70, { sm: true });
    const sp = el('div', 'blank', d);
    el('span', 'dymo blk', sp, 'RESERVED: POWER SYSTEM STABILIZER (1990)');
  })();

  /* ===================================================================
     +A4  SYNCHRONIZING · MIMIC · METERING
     =================================================================== */
  (() => {
    const d = cabinet('+A4', 'SYNCHRONIZING & NETWORK', 'SYNCHRONISIERUNG · 20 kV ANSCHLUSS · ZÄHLUNG', 650);
    const syncOn = () => P.sw.sync !== 'OFF' && P.dcV > 95;
    const genV = () => P.Vt, lineV = () => (P.grid ? P.gridV * (P.gridSag > 0 ? 0.72 : 1) : 0);
    const sp = section(d, 'SYNCHRONIZING PANEL · 25');
    const s1 = row(sp, 'c'); s1.style.paddingTop = '8px';
    meterCell(s1, {
      w: 122, h: 122, min: 0, max: 500, major: 100, minor: 20, labelStep: 100, unit: 'V', title: 'GEN ▬ red   LINE ▬ blk',
      value: () => lineV() * 400, value2: () => genV() * 400, needle2: '#b5180c', live: syncOn, rest: 0,
    }, 'DOUBLE VOLTMETER');
    const sc = col(s1); sc.style.gap = '6px';
    const sl = row(sc); sl.style.gap = '26px';
    // dark-lamp method: the lamps see the voltage difference between generator and line
    const lampV = (phase) => () => {
      if (!syncOn() || !P.grid || genV() < 0.1) return false;
      const dv = Math.hypot(genV() * Math.cos(P.delta + phase) - lineV() * Math.cos(phase), genV() * Math.sin(P.delta + phase) - lineV() * Math.sin(phase));
      return dv > 0.35;
    };
    const syncLamps = [0, 0, 0].map(() => new Lamp(sl, 'white', 'big'));
    UPD.push(() => {
      const on = syncOn() && P.grid && genV() > 0.1 && !P.cb;
      const dv = on ? Math.hypot(genV() * Math.cos(P.delta) - lineV(), genV() * Math.sin(P.delta)) : 0;
      const b = clamp(dv / 1.6, 0, 1);
      syncLamps.forEach(L => { L.set(b > 0.18 || LAMPTEST); L.e.firstChild.style.opacity = LAMPTEST ? 1 : (0.35 + 0.65 * b); });
    });
    void lampV;
    new Meter(sc, { kind: 'sync', w: 156, h: 156, r: 0.36, value: () => P.delta, live: () => syncOn() && P.grid && genV() > 0.2 && !P.cb });
    const rc = el('div', 'cell', s1);
    new ReedMeter(rc, {
      f1: () => ({ f: 50 * P.w, a: syncOn() && genV() > 0.1 ? Math.min(1, genV()) : 0 }),
      f2: () => ({ f: 50 * P.gridF, a: syncOn() && lineV() > 0.1 ? 1 : 0 }),
    });
    tag(rc, 'DOUBLE FREQUENCY METER', 's');
    const s2 = row(sp, 'c');
    rotary(s2, {
      label: 'SYNCHRONIZING', knob: 'pistol', id: 'syncSel', size: 86, radius: 33,
      pos: [{ t: 'OFF', a: -50, v: 'OFF' }, { t: 'MAN', a: 0, v: 'MAN' }, { t: 'AUTO', a: 50, v: 'AUTO' }],
      get: () => P.sw.sync, set: v => { P.sw.sync = v; P.syncArmed = v === 'AUTO'; P.syncFail = false; P.autoSyncT = 0; PL.log('25', 'SYNC SELECTOR ' + v); },
    });
    rotary(s2, {
      label: 'SYNC CHECK 25', knob: 'key', id: 'syncCheck',
      pos: [{ t: 'BYPASS', a: -45, v: false }, { t: 'ON', a: 45, v: true }],
      get: () => P.sw.syncCheck, set: v => { P.sw.syncCheck = v; PL.log('25', v ? 'SYNC CHECK IN SERVICE' : 'SYNC CHECK BYPASSED', v ? 'info' : 'alarm'); },
    });
    const sll = col(s2);
    const sr1 = row(sll);
    lamp(sr1, 'green', 'SYNC<br>PERMIT', () => syncOn() && P.grid && !P.cb && P.Vt > 0.5 && PL.syncWindow().ok, { sm: true });
    lamp(sr1, 'white', 'AUTO SYNC<br>ACTIVE', () => P.sw.sync === 'AUTO' && P.syncArmed && P.seq === 'S5_SNL' && P.fcb ? 's' : false, { sm: true });
    lamp(sr1, 'amber', 'SYNC<br>FAIL', () => P.syncFail, { sm: true });
    lamp(sr1, 'amber', 'CHECK<br>BYPASSED', () => !P.sw.syncCheck ? 's' : false, { sm: true });
    tag(sll, 'MANUAL SYNC: speed & volt via +A2/+A3 RAISE-LOWER', 'w s');

    // ---- mimic diagram ----
    const mm = section(d, 'SINGLE LINE DIAGRAM');
    const mim = el('div', 'mimic', mm);
    mim.style.marginTop = '4px';
    mim.innerHTML = `<svg viewBox="0 0 586 270" aria-label="Single line diagram">
      <g fill="none" stroke-linecap="square">
        <path d="M60 12 V46" stroke="var(--mimic-hv)" stroke-width="5"/>
        <path d="M60 106 V132" stroke="var(--mimic-hv)" stroke-width="5"/>
        <circle cx="60" cy="146" r="16" stroke="var(--mimic-hv)" stroke-width="4"/>
        <circle cx="60" cy="168" r="16" stroke="var(--mimic-lv)" stroke-width="4"/>
        <path d="M60 184 V200 H520" stroke="var(--mimic-lv)" stroke-width="5"/>
        <path d="M300 200 V186" stroke="var(--mimic-lv)" stroke-width="5"/>
        <path d="M300 128 V112" stroke="var(--mimic-lv)" stroke-width="5"/>
        <circle cx="300" cy="92" r="22" stroke="var(--mimic-lv)" stroke-width="4"/>
        <path d="M440 200 V232" stroke="var(--mimic-lv)" stroke-width="4"/>
        <path d="M430 232 h20 l-10 14 z" stroke="var(--mimic-lv)" stroke-width="3" fill="var(--mimic-lv)"/>
        <path d="M150 200 V230" stroke="var(--mimic-lv)" stroke-width="4"/>
        <rect x="135" y="230" width="30" height="20" stroke="var(--mimic-lv)" stroke-width="3"/>
      </g>
      <g font-family="Barlow Condensed, Arial Narrow, sans-serif" font-weight="700" fill="#1b1b18" font-size="11" letter-spacing=".06em">
        <text x="74" y="22">20 kV LINE  "MÜHLBACH - OBERDORF"</text>
        <text x="86" y="152">T1  315 kVA</text>
        <text x="86" y="164" font-weight="500">20 / 0.4 kV  Dyn5  uk 4 %</text>
        <text x="292" y="97" font-size="16">G</text>
        <text x="327" y="86">G1  300 kVA</text>
        <text x="327" y="98" font-weight="500">400 V · 72 P · 83.3 min⁻¹</text>
        <text x="350" y="194">0.4 kV BUS</text>
        <text x="458" y="244" font-weight="500">STATION</text>
        <text x="458" y="255" font-weight="500">SERVICE</text>
        <text x="172" y="244" font-weight="500">CAPACITOR</text>
        <text x="172" y="255" font-weight="500">(OUT OF SERV.)</text>
        <text x="96" y="80">52L</text>
        <text x="336" y="160">52G</text>
      </g>
    </svg>`;
    const mkDsw = (x, y, isGen) => {
      const s = el('div', 'dsw', mim); s.style.left = x + 'px'; s.style.top = y + 'px';
      s.setAttribute('role', 'button'); s.tabIndex = 0; s.id = isGen ? 'dsw52G' : 'dsw52L';
      s.setAttribute('aria-label', isGen ? 'Generator breaker 52G control switch' : 'Line breaker 52L control switch');
      const bar = el('div', 'bar', s); el('i', '', bar);
      let knobClosed = isGen ? P.cb : P.cbL, pre = 0;
      const actual = () => isGen ? P.cb : P.cbL;
      const act = () => {
        AU.detent();
        if (knobClosed !== actual() && pre > 0) {           // push to execute
          s.classList.add('push'); setTimeout(() => s.classList.remove('push'), 140);
          if (knobClosed) (isGen ? PL.cmdCbClose() : PL.cmdCbLClose());
          else (isGen ? PL.cmdCbOpen() : PL.cmdCbLOpen());
          pre = 0;
          return;
        }
        knobClosed = !knobClosed;
        pre = knobClosed !== actual() ? 5 : 0;
      };
      s.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); act(); });
      s.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
      DSW.push(() => { knobClosed = actual(); pre = 0; });
      UPD.push((dt) => {
        if (pre > 0) pre = Math.max(0, pre - dt);
        if (knobClosed === actual()) pre = 0;
        const disc = knobClosed !== actual();
        s.classList.toggle('open', !knobClosed);
        s.classList.toggle('lamp-on', (disc && FLASH.fast) || LAMPTEST);
      });
      return s;
    };
    mkDsw(60, 76, false);
    mkDsw(300, 157, true);
    const pos = (x, y, n) => { n.style.position = 'absolute'; n.style.left = x + 'px'; n.style.top = y + 'px'; return n; };
    const lpos = (x, y, color, fn, label) => { const c = pos(x, y, el('div', 'cell', mim)); const L = new Lamp(c, color, 'sm'); if (label) el('div', 'lbl sm', c, label); UPD.push(() => L.set(!!fn() || LAMPTEST)); };
    lpos(8, 52, 'red', () => P.cbL, '52L<br>ON');
    lpos(8, 92, 'green', () => !P.cbL, 'OFF');
    lpos(238, 140, 'red', () => P.cb, '52G<br>ON');
    lpos(238, 180, 'green', () => !P.cb, 'OFF');
    lpos(300, 30, 'white', () => P.grid, '20 kV<br>LIVE');
    lpos(530, 186, 'white', () => P.Vbus > 0.3 || (P.grid && P.cbL), 'BUS<br>LIVE');
    lpos(370, 112, 'white', () => P.Vt > 0.3, 'GEN<br>VOLTS');
    const hint = pos(410, 8, el('div', 'tag w s', mim));
    hint.style.cssText += ';white-space:normal;width:160px;text-align:left;line-height:1.25';
    hint.innerHTML = 'BREAKER CONTROL: TURN knob<br>(lamp flashes) then PUSH<br>within 5 s to execute.';

    const mt = section(d, 'METERING · ZÄHLUNG');
    const mr = row(mt, 'c'); mr.style.paddingTop = '6px';
    const fc = el('div', 'cell', mr);
    new Ferraris(fc, { kw: () => P.exportKW > 0 && P.grid && P.cbL ? P.exportKW : 0, reg: () => P.kWh / 10, title: 'EXPORT kWh  (UTILITY SEAL)' });
    tag(fc, 'ENERGY EXPORT', 's');
    const kc = col(mr);
    const kv = el('div', 'cell', kc); const kvc = new Counter(kv, 7, 0, 'blk'); tag(kv, 'kvarh  IND', 's');
    UPD.push(() => kvc.set(P.kvarh));
    meterCell(kc, { w: 96, h: 96, min: 0, max: 25, major: 5, minor: 1, labelStep: 10, unit: 'kV', title: 'LINE VT 20000/100', value: () => lineV() * 20, redline: 22 }, '20 kV LINE VOLTAGE');
  })();

  /* ===================================================================
     +A5  PROTECTION
     =================================================================== */
  (() => {
    const d = cabinet('+A5', 'GENERATOR PROTECTION', 'GENERATORSCHUTZ · RELAYS 86E / 86M HAND RESET', 610);
    const grid = el('div', 'relays', d);
    for (const r of PL.relays) {
      const box = el('div', 'relay', grid);
      const face = el('div', 'face', box);
      el('div', 'ansi', face, r.id);
      el('div', 'fn', face, r.name);
      el('div', 'set', face, r.set);
      let disk = null;
      if (r.disk) {
        const cv = el('canvas', '', face); cv.style.width = '64px'; cv.style.height = '28px';
        disk = cv;
      } else {
        el('div', 'mk', face, ({ E: '→ 86E ELECTRICAL', M: '→ 86M MECHANICAL', N: '→ 52G TRIP ONLY', S: '→ NORMAL STOP' })[r.cls]);
      }
      const fr = el('div', 'flagrow', face);
      const pu = el('div', 'pu', fr); pu.title = 'pick-up';
      el('div', 'flag', fr);
      const rst = el('button', 'rst', fr); rst.type = 'button'; rst.setAttribute('aria-label', 'Reset flag ' + r.id);
      rst.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); AU.click(); PL.resetRelay(r.id); });
      el('div', 'glass', box);
      el('span', 'scr', box).style.cssText = 'left:50%;top:-1px;margin-left:-3.5px';
      el('span', 'scr', box).style.cssText = 'left:50%;bottom:-1px;margin-left:-3.5px';
      let lastFlag = false;
      UPD.push(() => {
        box.classList.toggle('op', r.flag);
        pu.classList.toggle('on', !!r.pickup || LAMPTEST);
        if (r.flag !== lastFlag) { lastFlag = r.flag; if (r.flag) AU.relay(); }
        if (disk) drawDisk(disk);
      });
    }
    function drawDisk(cv) {
      const k = kscale(), W = 64, H = 28;
      if (cv.width !== Math.round(W * k)) { cv.width = Math.round(W * k); cv.height = Math.round(H * k); }
      const g = cv.getContext('2d'); g.setTransform(k, 0, 0, k, 0, 0);
      g.fillStyle = '#222'; g.fillRect(0, 0, W, H);
      const ph = P.disk51;
      const dg = g.createLinearGradient(0, 0, 0, H); dg.addColorStop(0, '#5a5a57'); dg.addColorStop(0.5, '#d8d8d4'); dg.addColorStop(1, '#4a4a47');
      g.fillStyle = dg; g.fillRect(3, 8, W - 6, 12);
      const x = 3 + (W - 6) * (0.08 + 0.84 * ph);
      g.fillStyle = '#b11b10'; g.fillRect(x - 2, 8, 4, 12);
      g.fillStyle = '#ddd'; g.font = `600 6.5px ${FL}`; g.textAlign = 'left'; g.fillText('INDUCTION DISC', 3, 6);
      g.fillStyle = '#e6c14a'; g.fillRect(W - 6, 6, 2, 16);
    }
    const lk = el('div', 'lockouts', d);
    for (const [which, title, sub] of [['E', '86E', 'ELECTRICAL LOCKOUT<br>52G · 41 TRIP · STOP'], ['M', '86M', 'MECHANICAL LOCKOUT<br>52G · 41 · EMERG. CLOSE']]) {
      const b = el('div', 'lockout', lk);
      const h = el('div', 'lh', b); h.setAttribute('role', 'button'); h.tabIndex = 0; h.id = 'lock86' + which;
      h.setAttribute('aria-label', 'Hand reset lockout relay ' + title);
      el('div', 'arm', h);
      const t = el('div', 'lt', b);
      el('b', '', t, title); el('span', '', t, sub); el('div', 'lflag', t);
      el('span', '', t, 'TURN HANDLE TO RESET');
      const doReset = () => { AU.detent(); PL.reset86(which); };
      h.addEventListener('pointerdown', e => { e.preventDefault(); doReset(); });
      h.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); doReset(); } });
      let last = false;
      UPD.push(() => {
        const on = which === 'E' ? P.lock86E : P.lock86M;
        b.classList.toggle('tripped', on);
        if (on !== last) { last = on; if (on) AU.clunk(); }
      });
    }
    const tcs = section(d, 'TRIP CIRCUIT SUPERVISION · 110 V DC');
    const tr = row(tcs); tr.style.paddingTop = '6px';
    lamp(tr, 'white', 'TRIP COIL 1<br>52G HEALTHY', () => P.dcV > 95, { sm: true });
    lamp(tr, 'white', 'TRIP COIL 2<br>52G HEALTHY', () => P.dcV > 95, { sm: true });
    lamp(tr, 'white', '41 TRIP<br>HEALTHY', () => P.dcV > 95, { sm: true });
    lamp(tr, 'amber', 'VT FUSE<br>FAIL 60', () => P.flt.vtFuse ? 's' : false, { sm: true });
    lamp(tr, 'red', 'UNIT<br>DAMAGED', () => P.damaged ? 'f' : false, { sm: true });
    pushbutton(tr, 'black', 'RESET<br>ALL FLAGS', () => PL.relays.forEach(r => PL.resetRelay(r.id)), null, { sq: true });
  })();

  /* ===================================================================
     +A6  ANNUNCIATOR · RECORDING · LEVELS
     =================================================================== */
  const ANN = [];
  let hornOn = false;
  (() => {
    const d = cabinet('+A6', 'ALARMS & RECORDING', 'STÖRMELDUNGEN · SCHREIBER · PEGEL · PROTOKOLL', 650);
    const an = el('div', 'ann', d);
    const maxB = () => Math.max(P.tTB, P.tUGB, P.tLGB, P.tTGB);
    const anyFlag = cls => PL.relays.some(r => r.cls === cls && r.flag);
    const rel = id => PL.relayById[id].flag;
    const defs = [
      ['OVERSPEED<br>TRIP', 'red', () => rel('12') || rel('12M')],
      ['BEARING TEMP<br>TRIP', 'red', () => rel('26')],
      ['OIL PRESSURE /<br>LEVEL TRIP', 'red', () => rel('63') || rel('71')],
      ['GENERATOR<br>ELECTRICAL TRIP', 'red', () => P.lock86E],
      ['EMERGENCY<br>STOP', 'red', () => P.estop],
      ['NETWORK PROT.<br>TRIP 27/81', 'red', () => anyFlag('N')],
      ['BEARING TEMP<br>HIGH 72 °C', 'amb', () => maxB() > 72],
      ['STATOR TEMP<br>HIGH 120 °C', 'amb', () => Math.max(...P.tSt) > 120],
      ['OIL PRESSURE<br>LOW 32 bar', 'amb', () => P.oilP < 32],
      ['OPU SUMP<br>LEVEL LOW', 'amb', () => P.oilLvl < 0.35],
      ['OIL PUMP<br>FAULT', 'amb', () => (P.flt.pump1 && P.pump1) || (P.flt.pump2 && P.pump2)],
      ['COOLING WATER<br>FLOW LOW', 'amb', () => (P.sw.cw === 'ON' || P.req.cw) && P.cwFlow < 0.5 && (P.seqT > 6 || P.w > 0.1)],
      ['EXCITATION<br>FAULT', 'amb', () => P.flashFail || (P.flt.avr && P.fcb)],
      ['AVR LIMITER<br>ACTIVE', 'amb', () => P.limActive],
      ['VT FUSE<br>FAILURE', 'amb', () => P.flt.vtFuse],
      ['20 kV LINE<br>VOLTAGE LOST', 'amb', () => !P.grid],
      ['GEN CB 52G<br>TRIPPED', 'amb', () => P.cbTripped],
      ['SYNCHRONIZING<br>FAILURE', 'amb', () => P.syncFail],
      ['TRASH RACK<br>Δh HIGH', 'amb', () => P.rackDh > 0.25],
      ['HEADWATER<br>HIGH', 'amb', () => P.hw > 214.75],
      ['HEADWATER<br>LOW', 'amb', () => P.hw < 214.05],
      ['AC AUX SUPPLY<br>FAILURE', 'amb', () => !P.acAux],
      ['DC SUPPLY<br>FAULT', 'amb', () => P.flt.charger || P.dcV < 108],
      ['CREEP<br>DETECTED', 'amb', () => P.seq === 'STOPPED' && P.w > 0.002],
      ['INTAKE GATE<br>NOT OPEN', 'amb', () => P.intake < 0.99],
      ['BRAKES APPLIED<br>n > 35 %', 'amb', () => P.brakePos > 0.1 && P.w > 0.35],
      ['SEQUENCE<br>FAULT', 'amb', () => P.seqFault],
      ['OIL LIFT<br>PRESSURE LOW', 'amb', () => P.w > 0.01 && P.w < 0.3 && P.liftP < 0.5],
      ['SPILLWAY<br>OVERFLOW', 'wht', () => P.qspill > 0.3],
      ['TORQUE SHOCK /<br>OUT OF STEP', 'red', () => P.shock > 0.05 || P.slips > 0 || P.damaged],
    ];
    for (const [t, c, fn] of defs) {
      const w = el('div', 'aw', an, t);
      ANN.push({ t: t.replace('<br>', ' '), c, fn, e: w, st: 'off', tOn: 0, delay: c === 'red' ? 0 : 3 });
    }
    const ab = row(d, 'c');
    pushbutton(ab, 'black', '', () => { hornOn = false; ANN.silenced = true; }, null, { sq: true, top: 'SILENCE HORN' });
    pushbutton(ab, 'yellow', '', () => annAck(), null, { sq: true, top: 'ACKNOWLEDGE', id: 'btnAck' });
    pushbutton(ab, 'blue', '', () => annReset(), null, { sq: true, top: 'RESET', id: 'btnReset' });
    pushbutton(ab, 'white', '', () => { LAMPTEST = true; }, () => { LAMPTEST = false; }, { sq: true, top: 'LAMP TEST' });
    lamp(ab, 'red', 'HORN', () => hornOn, { sm: true });

    const rr = row(d);
    const rc = el('div', 'cell', rr);
    new Recorder(rc, { w: 300, h: 262 });
    tag(rc, '3-PEN RECORDER  ·  RED kW  ·  BLUE HEADWATER  ·  GREEN SPEED', 's');
    const rside = col(rr);
    const lv = el('div', '', rside); lv.style.cssText = 'display:flex;gap:5px;align-items:flex-start';
    meterCell(lv, {
      kind: 'edge', w: 64, h: 200, min: 213.5, max: 215.5, major: 0.5, minor: 0.1, labelEvery: 1, unit: 'm', value: () => P.hw, setValue: () => P.levelRef, wn: 4, x0: 0.66,
      fmt: v => v.toFixed(1), zones: [{ f: 213.5, t: 213.85, c: RED }, { f: 213.85, t: 214.05, c: AMBER }, { f: 214.75, t: 215.5, c: AMBER }],
      extraMarks: [{ v: 214.60, c: '#1f47b0', t: 'CREST' }],
    }, 'HEADWATER<br>OW m ü.NN');
    meterCell(lv, {
      kind: 'edge', w: 64, h: 200, min: 210, max: 212.5, major: 0.5, minor: 0.1, labelEvery: 1, unit: 'm', value: () => P.tw, wn: 4, x0: 0.66,
      fmt: v => v.toFixed(1),
    }, 'TAILWATER<br>UW m ü.NN');
    meterCell(lv, {
      kind: 'edge', w: 50, h: 200, min: 0, max: 0.6, major: 0.1, minor: 0.02, labelEvery: 1, unit: 'm', value: () => P.rackDh, wn: 4,
      fmt: v => v.toFixed(1), zones: [{ f: 0.25, t: 0.6, c: AMBER }],
    }, 'RACK<br>Δh');
    rotary(rside, {
      label: 'CHART SPEED mm/h', knob: 'round', radius: 27,
      pos: [{ t: '300', a: -50, v: 0 }, { t: '1200', a: 0, v: 1 }, { t: '6000', a: 50, v: 2 }],
      get: () => P.sw.chart, set: v => { P.sw.chart = v; },
    });

    const pr = el('div', 'printer', d);
    const head = el('div', 'head', pr); const carr = el('div', 'carr', head);
    const paper = el('div', 'paper', pr);
    const front = el('div', 'front', pr);
    el('span', 'brandp', front, 'EVENT LOGGER  ·  DOT MATRIX 80');
    const plr = row(front); plr.style.gap = '12px';
    lamp(plr, 'green', 'POWER', () => P.dcV > 95, { sm: true });
    lamp(plr, 'amber', 'ON LINE', () => true, { sm: true });
    PRINTER.paper = paper; PRINTER.carr = carr;
  })();

  function annAck() { ANN.forEach(a => { if (a.st === 'alarm') a.st = a.fn() ? 'ack' : 'ring'; }); hornOn = false; }
  function annReset() { ANN.forEach(a => { if (a.st === 'ring' && !a.fn()) a.st = 'off'; }); }
  function annUpdate(dtSim) {
    let anyNew = false;
    for (const a of ANN) {
      const raw = a.fn();
      a.tOn = raw ? a.tOn + dtSim : 0;
      const act = raw && a.tOn >= a.delay;
      if (act && (a.st === 'off' || a.st === 'ring')) { a.st = 'alarm'; anyNew = true; PL.log('ANN', a.t, a.c === 'red' ? 'trip' : 'alarm'); }
      else if (!act && a.st === 'ack') { a.st = 'ring'; PL.log('ANN', 'CLEARED ' + a.t); }
      const lit = LAMPTEST || (a.st === 'alarm' && FLASH.fast) || a.st === 'ack' || (a.st === 'ring' && FLASH.slow);
      if (lit !== a.lit) { a.lit = lit; a.e.classList.toggle('lit', lit); a.e.classList.toggle(a.c, lit); }
    }
    if (anyNew) hornOn = true;
    if (!ANN.some(a => a.st === 'alarm')) hornOn = false;
  }

  /* ===================================================================
     ROOM, ZOOM, PANNING
     =================================================================== */
  const room = document.getElementById('room'), stage = document.getElementById('stage'), floor = document.getElementById('floor');
  let fitMode = true;
  // camera: fixed eye height, distance CAM_P (lineup px) from the cabinet fronts
  const CAM_P = window.LOOK.CAM_P;
  let camY = 500, viewPending = false, depthTimer = 0;
  void floor;
  const bg = document.createElement('canvas'); bg.id = 'bg'; stage.prepend(bg);
  function layout() {
    const natW = lineup.offsetWidth, natH = lineup.offsetHeight;
    const avail = room.clientHeight - 6;
    if (fitMode) ZOOM = clamp(avail * 0.88 / natH, 0.32, 1.25);   // leave room for the floor
    lineup.style.transform = `scale(${ZOOM})`;
    stage.style.width = natW * ZOOM + 'px';
    const h = Math.max(natH * ZOOM + avail * 0.12, room.clientHeight);
    stage.style.height = h + 'px';
    const c0 = lineup.querySelector('.cab');
    if (c0) camY = c0.offsetTop + c0.offsetHeight * 0.40;
    view(true);
    METERS.forEach(m => m.resize());
  }
  function view(now) {
    const cw = room.clientWidth, ch = stage.offsetHeight;
    const vxS = room.scrollLeft + cw / 2;
    bg.style.left = room.scrollLeft + 'px';
    bg.style.width = cw + 'px'; bg.style.height = ch + 'px';
    window.LOOK.drawRoom(bg, { Z: ZOOM, sl: room.scrollLeft, cw, ch, vx: vxS / ZOOM, vy: camY, dpr: Math.min(2, window.devicePixelRatio || 1) });
    // hardware thickness follows the camera once panning settles (repainting every part per frame is costly)
    const setDepth = () => { lineup.style.setProperty('--vpx', (vxS / ZOOM).toFixed(1)); lineup.style.setProperty('--vpy', camY.toFixed(1)); };
    clearTimeout(depthTimer);
    if (now) setDepth(); else depthTimer = setTimeout(setDepth, 140);
  }
  room.addEventListener('scroll', () => {
    if (viewPending) return;
    viewPending = true;
    requestAnimationFrame(() => { viewPending = false; view(false); });
  }, { passive: true });
  let drag = null;
  room.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    if (e.target.closest('.pb,.rot,.dsw,.estop,.lh,.rst,.card,button')) return;
    drag = { x: e.clientX, y: e.clientY, sl: room.scrollLeft, st: room.scrollTop, moved: false };
    room.classList.add('drag');
  });
  window.addEventListener('pointermove', e => {
    if (!drag) return;
    room.scrollLeft = drag.sl - (e.clientX - drag.x);
    room.scrollTop = drag.st - (e.clientY - drag.y);
  });
  window.addEventListener('pointerup', () => { drag = null; room.classList.remove('drag'); });
  room.addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.ctrlKey && room.scrollHeight <= room.clientHeight + 2) {
      room.scrollLeft += e.deltaY; e.preventDefault();
    }
  }, { passive: false });
  const setZoom = z => { fitMode = false; ZOOM = clamp(z, 0.35, 1.6); layout(); };
  document.getElementById('zFit').onclick = () => { fitMode = true; layout(); };
  document.getElementById('zIn').onclick = () => setZoom(ZOOM * 1.15);
  document.getElementById('zOut').onclick = () => setZoom(ZOOM / 1.15);
  const jump = document.getElementById('jump');
  CABS.forEach(c => {
    const b = el('button', '', jump, c.code); b.type = 'button'; b.title = c.name;
    b.onclick = () => room.scrollTo({ left: Math.max(0, (c.el.offsetLeft) * ZOOM - 20), behavior: 'smooth' });
  });
  const tg = document.getElementById('tgrp');
  const tBtns = [1, 2, 5, 10, 20].map(n => {
    const b = el('button', n === 1 ? 'on' : '', tg, '×' + n); b.type = 'button';
    b.onclick = () => setAccel(n);
    return b;
  });
  function setAccel(n) { TIMEACC = n; tBtns.forEach(b => b.classList.toggle('on', b.textContent === '×' + n)); document.querySelectorAll('[data-acc]').forEach(b => b.classList.toggle('on', +b.dataset.acc === n)); }
  const ffBtn = el('button', 'on', tg, 'AUTO-FF'); ffBtn.type = 'button'; ffBtn.id = 'ff';
  ffBtn.title = 'Fast-forward ×10 through automatic start/stop waits';
  ffBtn.onclick = () => { AUTOFF = !AUTOFF; ffBtn.classList.toggle('on', AUTOFF); };
  const ffInd = el('span', 'ffind', tg); ffInd.hidden = true;
  const waiting = () => /^(S[1-4]|T[1-5])/.test(P.seq) || (P.seq === 'S5_SNL' && P.sw.sync === 'AUTO' && P.syncArmed && P.fcb);
  const snd = document.getElementById('snd');
  snd.onclick = () => { const on = AU.toggle(); snd.textContent = on ? 'SOUND ON' : 'SOUND OFF'; snd.classList.toggle('on', on); };

  /* ===================================================================
     INSTRUCTOR STATION + OPERATING MANUAL
     =================================================================== */
  const insOvl = document.getElementById('insOvl'), manOvl = document.getElementById('manOvl');
  function buildInstructor() {
    insOvl.innerHTML = '';
    const c = el('div', 'crt', insOvl);
    const cl = el('button', 'close', c, '[ESC] CLOSE'); cl.onclick = () => { insOvl.hidden = true; };
    el('h2', '', c, 'INSTRUCTOR STATION  ·  UNIT 1 TRAINER');
    el('div', '', c, 'The operator in the control room cannot see this screen.');
    const sec = (t) => { el('h3', '', c, t); return el('div', 'btns', c); };
    const b = (p, t, fn, cls) => { const x = el('button', cls || '', p, t); x.type = 'button'; x.onclick = () => { fn(x); }; return x; };
    const ic = sec('> INITIAL CONDITION');
    b(ic, 'UNIT ON LINE (LEVEL CONTROL)', () => { PL.initOnline(); resetUi(); });
    b(ic, 'UNIT STOPPED, READY', () => { PL.initStopped(); resetUi(); });
    const tm = sec('> SIMULATION TIME');
    [1, 2, 5, 10, 20].forEach(n => { const x = b(tm, '×' + n, () => setAccel(n), TIMEACC === n ? 'on' : ''); x.dataset.acc = n; });
    const nw = sec('> NETWORK EVENTS');
    b(nw, 'LOSS OF 20 kV LINE', () => PL.inject('gridLoss'));
    b(nw, 'VOLTAGE DIP', () => PL.inject('gridSag'));
    b(nw, 'FREQUENCY DIP', () => PL.inject('freqDip'));
    b(nw, 'FREQUENCY RISE', () => PL.inject('freqRise'));
    const rv = sec('> RIVER');
    b(rv, 'FLOOD WAVE', () => PL.inject('flood'));
    b(rv, 'LOW FLOW / DROUGHT', () => PL.inject('drought'));
    b(rv, 'DEBRIS SURGE ON RACK', () => PL.inject('debris'));
    b(rv, 'INFLOW +1 m³/s', () => { P.qinTarget += 1; P.qinBase += 1; });
    b(rv, 'INFLOW -1 m³/s', () => { P.qinTarget = Math.max(1, P.qinTarget - 1); P.qinBase = Math.max(1, P.qinBase - 1); });
    const mf = sec('> MALFUNCTIONS (TOGGLE)');
    const F = [['cw', 'COOLING WATER PUMP TRIP'], ['pump1', 'OIL PUMP 1 FAILED'], ['pump2', 'OIL PUMP 2 FAILED'], ['oilLeak', 'OPU OIL LEAK'],
      ['vtFuse', 'VT FUSE L1 BLOWN'], ['avr', 'AVR AUTO CHANNEL FAIL'], ['flash', 'FIELD FLASHING FAIL'], ['charger', 'BATTERY CHARGER FAIL'],
      ['bearing', 'THRUST BEARING DETERIORATION'], ['earth', 'STATOR EARTH FAULT'], ['diff', 'GEN INTERNAL FAULT (87)'], ['govSensor', 'SPEED SENSOR DRIFT -3 %']];
    for (const [k, t] of F) {
      const x = b(mf, t, (x) => { P.flt[k] = !P.flt[k]; x.classList.toggle('on', P.flt[k]); PL.log('INSTR', `${P.flt[k] ? 'FAULT' : 'CLEAR'} ${t}`); }, P.flt[k] ? 'on' : '');
      void x;
    }
    const rf = sec('> RANDOM MALFUNCTIONS');
    [[0, 'OFF'], [2, '2 PER HOUR'], [6, '6 PER HOUR']].forEach(([n, t]) => b(rf, t, (x) => { P.randomRate = n; [...rf.children].forEach(c => c.classList.remove('on')); x.classList.add('on'); }, P.randomRate === n ? 'on' : ''));
    const mt = sec('> MAINTENANCE');
    b(mt, 'REPAIR UNIT / CLEAR ALL FAULTS', () => { PL.repair(); buildInstructor(); });
    el('h3', '', c, '> PLANT TRUTH (NOT METERED)');
    const st = el('div', 'stat', c);
    INS.stat = st;
  }
  const INS = { stat: null };
  function insStat() {
    if (insOvl.hidden || !INS.stat) return;
    INS.stat.innerHTML = [
      `RIVER INFLOW  ${P.qin.toFixed(2)} m³/s`, `SPILL         ${P.qspill.toFixed(2)} m³/s`, `TURBINE FLOW  ${P.q.toFixed(2)} m³/s`,
      `GROSS HEAD    ${P.hg.toFixed(2)} m`, `NET HEAD      ${P.hn.toFixed(2)} m`, `TURBINE η     ${(P.eff * 100).toFixed(1)} %`,
      `SHAFT POWER   ${P.Pm.toFixed(1)} kW`, `LOAD ANGLE δ  ${(P.delta * 180 / Math.PI).toFixed(1)}°`, `FEEDER LOAD   ${(P.feeder * 300).toFixed(0)} kW`,
      `RACK FOULING  ${P.rack.toFixed(3)} m`, `GRID f        ${(P.gridF * 50).toFixed(3)} Hz`, `SEQUENCE      ${P.seq}`,
    ].map(s => `<span>${s.replace(/ /g, '&nbsp;')}</span>`).join('');
  }
  document.getElementById('ins').onclick = () => { buildInstructor(); insOvl.hidden = false; };
  insOvl.addEventListener('pointerdown', e => { if (e.target === insOvl) insOvl.hidden = true; });

  function openManual() {
    manOvl.innerHTML = '';
    const s = el('div', 'sheet', manOvl);
    const cl = el('button', 'close', s, 'CLOSE ✕'); cl.onclick = () => { manOvl.hidden = true; };
    s.insertAdjacentHTML('beforeend', `
      <div class="stamp">CONTROLLED COPY</div>
      <h2>MÜHLBACH HYDRO STATION — UNIT 1</h2>
      <div>OPERATING INSTRUCTION BA-01 · Rev. C · 03/1989</div>
      <h3>PLANT</h3>
      Vertical Kaplan turbine, 4 blades, net head 3.5 m, rated discharge 8.6 m³/s. Direct-coupled
      72-pole synchronous generator, 300 kVA, 400 V, 50 Hz, 83.3 min⁻¹. Static thyristor excitation,
      self-fed, field flashing from the 110 V battery. Step-up T1 0.4/20 kV to the utility line.
      Headwater is held by the electro-hydraulic governor in LEVEL mode; weir crest 214.60 m.
      <h3>HOW TO USE THE PANELS</h3>
      <ul>
        <li>Selector switches: click the LEFT or RIGHT half of the knob to turn it.</li>
        <li>RAISE/LOWER switches spring back: hold the mouse on the half you want.</li>
        <li>Breakers 52G / 52L (+A4 mimic): click once to TURN (lamp flashes), click again within 5 s to PUSH.</li>
        <li>Lockout relays 86E/86M (+A5): click the handle to reset once the cause is cleared.</li>
        <li>Annunciator (+A6): ACK silences the horn, RESET clears windows that have returned to normal.</li>
        <li>Drag the room or use the mouse wheel to walk along the cabinets. SIM TIME speeds things up.</li>
      </ul>
      <h3>A. AUTOMATIC START</h3>
      <ol>
        <li>+A1 UNIT CONTROL key on AUTO. Auxiliary selectors on AUTO. READY TO START lamp lit.</li>
        <li>Push START. Sequence: cooling water + oil lift → brakes release → gates to start opening →
            at 95 % speed excitation ON (field flashing) → SPEED NO LOAD.</li>
        <li>+A4 SYNCHRONIZING on AUTO: the synchronizer trims speed and voltage and closes 52G.
            On MAN: see C.</li>
        <li>After 52G closes the governor goes to the mode set on +A2 (LEVEL, LOAD or SPEED/droop).</li>
      </ol>
      <h3>B. NORMAL STOP</h3>
      Push STOP. The unit unloads, 52G opens, field breaker opens, gates close, brakes apply at 28 % speed.
      Run-down from full speed takes about four minutes (the trainer fast-forwards automatic waits ×10; AUTO-FF in the top bar turns that off).
      <h3>C. MANUAL SYNCHRONIZING</h3>
      <ol>
        <li>Unit at speed no load, excitation on. SYNCHRONIZING selector to MAN.</li>
        <li>Match voltage with VOLTAGE/FIELD (+A3) and frequency with SPEED SETPOINT (+A2).
            Double voltmeter needles together, reeds of both rows on the same frequency.</li>
        <li>Let the synchroscope turn slowly CLOCKWISE (FAST), about one turn in 10 s. Sync lamps (dark method)
            go dark when in phase.</li>
        <li>Turn 52G to CLOSE a little before 12 o'clock and PUSH. The breaker needs 85 ms.</li>
        <li>Never bypass sync check 25 unless instructed. Closing far out of phase damages the shaft.</li>
      </ol>
      <h3>D. ALARM LIMITS</h3>
      Bearing 72 °C alarm / 80 °C trip · Stator 120 / 130 °C · Oil pressure 32 bar alarm / 28 bar trip ·
      Overspeed 140 % electrical, 155 % mechanical (also closes intake gate) · Headwater low-low 213.85 m.
      <h3>E. LOSS OF THE 20 kV LINE</h3>
      Network protection (27/81) opens 52G; the unit stays at speed no load with 86 not operated.
      With the line dead, station service is lost: watch oil pressure. Either stop the unit, or open 52L
      and close 52G onto the dead bus to supply the station from the generator (island, SPEED mode).
      When the line returns: open 52G (or synchronize across 52L), re-close 52L, resynchronize.
      <h3>F. AFTER A TRIP</h3>
      Read the relay flags (+A5) and the event printer (+A6). Clear the cause, reset flags, reset 86E/86M,
      ACK and RESET the annunciator, then restart.
    `);
    manOvl.hidden = false;
  }
  document.getElementById('man').onclick = openManual;
  manOvl.addEventListener('pointerdown', e => { if (e.target === manOvl) manOvl.hidden = true; });
  window.addEventListener('keydown', e => { if (e.key === 'Escape') { insOvl.hidden = true; manOvl.hidden = true; } });

  function resetUi() {
    PRINTER.lastId = 0; PRINTER.queue.length = 0;
    if (PRINTER.paper) PRINTER.paper.innerHTML = '';
    ANN.forEach(a => { a.st = a.fn() ? 'ack' : 'off'; a.tOn = 0; });
    DSW.forEach(f => f());
    METERS.forEach(m => { if (m.seed) m.seed(); });
  }

  /* ===================================================================
     NOISE TEXTURE + BOOT + MAIN LOOP
     =================================================================== */
  // paint the (still dead) cabinets first, then warm the plant up
  layout();
  window.LOOK.apply(lineup);
  METERS.forEach(m => {
    if (!m.light) return;
    const p = window.LOOK.relPos(m.c, lineup), cab = m.c.closest('.cab');
    m.light = window.LOOK.lightAt(p.x + p.w / 2, p.y + p.h / 2, cab.offsetTop, cab.offsetHeight);
  });
  layout();
  METERS.forEach(m => { if (!m.samples) m.draw(); });
  window.addEventListener('resize', layout);
  if (window.ResizeObserver) { let lastH = 0; new ResizeObserver(() => { if (room.clientHeight !== lastH) { lastH = room.clientHeight; layout(); } }).observe(room); }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layout);

  // first-visit hint
  const hint = document.getElementById('hint');
  hint.innerHTML = `<b>Unit 1 is on line</b>, holding the headwater in LEVEL mode.<br>
    Drag or scroll to walk along the six cabinets. Click the left/right half of a knob to turn it;
    hold spring-return switches. Automatic start/stop waits fast-forward ×10. Turn <b>SOUND</b> on for the machine hall.<br><button type="button" id="hintOk">GOT IT</button>`;
  document.getElementById('hintOk').onclick = () => { hint.hidden = true; };

  let last = performance.now(), flashT = 0;
  function frame(now) {
    const dtReal = Math.min(0.1, (now - last) / 1000); last = now;
    const ff = AUTOFF && TIMEACC < 10 && waiting() && !ANN.some(a => a.st === 'alarm' && a.c === 'red');
    EFFACC = ff ? 10 : TIMEACC;
    if (ff !== !ffInd.hidden) ffInd.hidden = !ff;
    if (ff) ffInd.textContent = '▶▶ ×10  ' + (PL.SEQ_TEXT[P.seq] || '').replace(/^(START|STOP): /, '');
    const simDt = dtReal * EFFACC;
    PL.advance(simDt);
    flashT += dtReal;
    FLASH.fast = (flashT % 0.6) < 0.32;
    FLASH.slow = (flashT % 1.4) < 0.7;
    annUpdate(simDt);
    for (const u of UPD) u(dtReal);
    const jit = P.w > 0.05 ? 0.0016 * Math.min(1.2, P.w) * (1 + 6 * P.shock) : 0;
    for (const m of METERS) { m.step(dtReal, jit); m.draw(); }
    PRINTER.pump(dtReal);
    AU.update(hornOn);
    insStat();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(() => setTimeout(() => {
    PL.initOnline();
    resetUi();
    hint.hidden = false;
    last = performance.now();
    requestAnimationFrame(frame);
  }, 0));
  window.UNIT1 = { PL, P, AU, ANN, setAccel };
})();
