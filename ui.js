'use strict';
/* =====================================================================
   UI · simulator menu (instructor station), tooltips, sound, main loop
   ===================================================================== */
(() => {
  const P = window.PLANT, S = P.S, sw = P.sw, PN = window.PANELS;
  const $ = s => document.querySelector(s);
  const store = {
    get(k, d) { try { const v = localStorage.getItem('sablecreek.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('sablecreek.' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };

  /* ------------------------------------------------------------ tooltip */
  const UNIT = { 'AC VOLTS': 'V', 'AC AMPERES': 'A', KILOWATTS: 'kW', HERTZ: 'Hz', RPM: 'rpm', '% OPEN': '%', PSI: 'psi', CFS: 'cfs', FEET: 'ft', 'MILS P-P': 'mils p-p', GPM: 'gpm', '°C': '°C', 'DC VOLTS': 'V dc', 'DC AMPERES': 'A dc', 'FT WATER': 'ft', '%': '%', EL: 'ft', FT: 'ft' };
  function dec(sc) { return sc.major >= 10 ? 0 : sc.major >= 1 ? 1 : 2; }
  function reading(it) {
    const v = it.get(), sc = it.scale;
    if (sc.pf) { if (S.I < 0.02) return 'no load'; return `${Math.abs(S.pf).toFixed(3)} ${S.Qkvar >= 0 ? 'lagging' : 'leading'}`; }
    if (sc.unit === 'KVAR') return `${Math.abs(v).toFixed(0)} kvar ${v >= 0 ? 'lagging' : 'leading'}`;
    if (sc.compound) return v < 0 ? `${(-v).toFixed(1)} inHg vacuum` : `${v.toFixed(1)} psi`;
    const d = it.t === 'edge' && sc.unit === 'EL' ? 2 : dec(sc);
    return `${v.toFixed(d)} ${UNIT[sc.unit] || sc.unit}`;
  }
  const clean = s => String(s || '').replace(/\n/g, ' ');
  function tipText(ud, point) {
    const it = ud && ud.it; if (!it) return null;
    const name = clean(it.label || '');
    switch (it.t) {
      case 'meter': case 'edge': {
        let r = reading(it);
        if (it.pointer2) r += it.t === 'edge' ? ` · setpoint ${it.pointer2().toFixed(2)}` : ` · limit ${it.pointer2().toFixed(0)} %`;
        return [name, r];
      }
      case 'lamp': { let v = it.on(); v = v === 'flash' ? 'FLASHING' : v === true || v > 0.5 ? 'ON' : 'OFF'; return [name, `Indicator ${v}`]; }
      case 'pb': return [name || 'Push button', it.tip || 'Press'];
      case 'sel': return [name, `${it.pos[Math.max(0, it.get())]} · click the left or right side to turn`, it.tip2];
      case 'rl': return [name, 'Hold the left side to LOWER, the right side to RAISE', it.tip2];
      case 'cs': return [name, `${it.state() ? (it.right === 'CLOSE' ? 'CLOSED' : 'ON') : (it.right === 'CLOSE' ? 'OPEN' : 'OFF')} · left side ${it.left}, right side ${it.right}`];
      case 'estop': return ['EMERGENCY STOP', S.estop ? 'Pushed in. Click to twist-release, then reset 86M' : 'Click to push: trips 86M, closes gates and inlet valve'];
      case 'lockout': return [name, it.get() ? 'TRIPPED · click the handle to reset' : 'Reset (normal)'];
      case 'counter': return [name, it.dec ? it.get().toFixed(1) : Math.floor(it.get()).toLocaleString('en-US')];
      case 'synchro': return ['SYNCHROSCOPE', S.cb ? 'Breaker closed' : S.Vt < 0.2 || S.vbus < 0.2 ? 'No voltage on one side' : `Slip ${S.slipHz >= 0 ? '+' : ''}${S.slipHz.toFixed(2)} Hz · angle ${(S.syncAng * 180 / Math.PI).toFixed(0)}° · ${S.syncOK ? '25 permits' : '25 blocks'}`];
      case 'disp': return [clean(it.label) || 'Display', it.kind === 'led7' ? 'Digital readout' : 'Display'];
      case 'relay': { const t = Object.keys(S.targets); return ['GENERATOR PROTECTION RELAY', t.length ? `Targets: ${t.join(', ')} · press TARGET RESET` : 'No targets']; }
      case 'ann': {
        const p = ROOM.toDoor(ud.ci, point); if (!p) return ['ANNUNCIATOR'];
        const c = Math.floor((p.x - (it.x - it.cols * it.cw / 2)) / it.cw), r = Math.floor((p.y - (it.y - it.rows * it.ch / 2)) / it.ch);
        const a = P.ANN[r * it.cols + c]; if (!a || c < 0 || c >= it.cols) return ['ANNUNCIATOR'];
        const st = { off: 'normal', alarm: 'ALARM (unacknowledged)', ack: 'ALARM (acknowledged)', alarmRTN: 'cleared, unacknowledged', ring: 'cleared · press RESET' }[a.st];
        return [clean(a.label), st];
      }
      default: return [name];
    }
  }
  const tipEl = () => $('#tip');
  let tipHide = 0;
  function onTip(ud, x, y, point, touch) {
    const el = tipEl();
    const t = ud ? tipText(ud, point) : null;
    if (!t) { el.hidden = true; return; }
    el.innerHTML = `<b>${t[0]}</b>${t[1] ? `<span>${t[1]}</span>` : ''}${t[2] ? `<span>${t[2]}</span>` : ''}`;
    el.hidden = false;
    const w = el.offsetWidth, h = el.offsetHeight;
    el.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x + 16)) + 'px';
    el.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, y + 18)) + 'px';
    clearTimeout(tipHide);
    if (touch) tipHide = setTimeout(() => { el.hidden = true; }, 2600);
  }

  /* -------------------------------------------------------------- sound */
  const AU = { on: false, ctx: null };
  function noiseBuf(ctx, color) {
    const n = ctx.sampleRate * 3, b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0);
    let l = 0, b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < n; i++) {
      const w = Math.random() * 2 - 1;
      if (color === 'brown') { l = (l + 0.02 * w) / 1.02; d[i] = l * 3.5; }
      else if (color === 'pink') { b0 = 0.997 * b0 + w * 0.029; b1 = 0.985 * b1 + w * 0.032; b2 = 0.950 * b2 + w * 0.048; d[i] = (b0 + b1 + b2 + w * 0.02) * 0.9; }
      else d[i] = w;
    }
    return b;
  }
  function audioInit() {
    if (AU.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    const ctx = new AC(); AU.ctx = ctx;
    const master = ctx.createGain(); master.gain.value = 0.0; master.connect(ctx.destination); AU.master = master;
    const loop = (buf) => { const s = ctx.createBufferSource(); s.buffer = buf; s.loop = true; s.start(); return s; };
    const brown = noiseBuf(ctx, 'brown'), pink = noiseBuf(ctx, 'pink'), white = noiseBuf(ctx, 'white');
    // machine hall through the wall: water + runner
    const w = loop(brown), wf = ctx.createBiquadFilter(); wf.type = 'lowpass'; wf.frequency.value = 180;
    const wg = ctx.createGain(); wg.gain.value = 0; w.connect(wf); wf.connect(wg); wg.connect(master);
    AU.water = { f: wf, g: wg };
    // generator magnetostriction hum at twice line frequency + harmonics
    AU.hum = [120, 240, 360, 480].map((f, i) => { const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = f; const g = ctx.createGain(); g.gain.value = 0; o.connect(g); g.connect(master); o.start(); return { o, g, k: [1, 0.45, 0.22, 0.08][i], m: i + 1 }; });
    // rough-zone / rope rumble
    const r = loop(pink), rf = ctx.createBiquadFilter(); rf.type = 'bandpass'; rf.frequency.value = 70; rf.Q.value = 1.2;
    const rg = ctx.createGain(); rg.gain.value = 0; r.connect(rf); rf.connect(rg); rg.connect(master); AU.rough = rg;
    // spill roar (outside, muffled)
    const sp = loop(pink), spf = ctx.createBiquadFilter(); spf.type = 'lowpass'; spf.frequency.value = 400;
    const spg = ctx.createGain(); spg.gain.value = 0; sp.connect(spf); spf.connect(spg); spg.connect(master); AU.spill = spg;
    // room HVAC
    const hv = loop(pink), hvf = ctx.createBiquadFilter(); hvf.type = 'highpass'; hvf.frequency.value = 900;
    const hvg = ctx.createGain(); hvg.gain.value = 0.006; hv.connect(hvf); hvf.connect(hvg); hvg.connect(master);
    // pump motors (OPU, CW, lift) as faint 60 Hz induction-motor hum
    const pm = ctx.createOscillator(); pm.type = 'triangle'; pm.frequency.value = 120; const pmg = ctx.createGain(); pmg.gain.value = 0; pm.connect(pmg); pmg.connect(master); pm.start(); AU.pump = pmg;
    // annunciator horn
    const h1 = ctx.createOscillator(), h2 = ctx.createOscillator(); h1.type = 'square'; h2.type = 'square'; h1.frequency.value = 440; h2.frequency.value = 446;
    const hf = ctx.createBiquadFilter(); hf.type = 'bandpass'; hf.frequency.value = 900; hf.Q.value = 0.8;
    const hg = ctx.createGain(); hg.gain.value = 0; h1.connect(hf); h2.connect(hf); hf.connect(hg); hg.connect(master); h1.start(); h2.start(); AU.horn = hg;
    AU.white = white;
  }
  function blip(kind) {
    if (!AU.on || !AU.ctx) return;
    const ctx = AU.ctx, t = ctx.currentTime;
    const src = ctx.createBufferSource(); src.buffer = AU.white;
    const f = ctx.createBiquadFilter(), g = ctx.createGain();
    const spec = { click: [3200, 0.10, 0.025], stop: [1800, 0.05, 0.02], pb: [2400, 0.10, 0.03], release: [2800, 0.05, 0.02], cs: [1500, 0.18, 0.05], estop: [900, 0.25, 0.06], breaker: [180, 0.9, 0.35], relay: [2200, 0.14, 0.05] }[kind] || [2000, 0.1, 0.03];
    f.type = kind === 'breaker' ? 'lowpass' : 'bandpass'; f.frequency.value = spec[0]; f.Q.value = 0.9;
    g.gain.setValueAtTime(spec[1], t); g.gain.exponentialRampToValueAtTime(0.0001, t + spec[2]);
    src.connect(f); f.connect(g); g.connect(AU.master); src.start(t, Math.random() * 2, spec[2] + 0.05);
    if (kind === 'breaker') {
      const o = ctx.createOscillator(), og = ctx.createGain(); o.frequency.setValueAtTime(70, t); o.frequency.exponentialRampToValueAtTime(35, t + 0.3);
      og.gain.setValueAtTime(0.5, t); og.gain.exponentialRampToValueAtTime(0.0001, t + 0.35); o.connect(og); og.connect(AU.master); o.start(t); o.stop(t + 0.4);
    }
  }
  function setSound(on) {
    AU.on = on; store.set('sound', on);
    if (on) { audioInit(); if (AU.ctx && AU.ctx.state === 'suspended') AU.ctx.resume(); }
    if (AU.master) AU.master.gain.setTargetAtTime(on ? 0.9 : 0, AU.ctx.currentTime, 0.1);
    $('#snd').setAttribute('aria-pressed', on ? 'true' : 'false');
    $('#snd').textContent = on ? 'Sound on' : 'Sound off';
  }
  function audioUpdate() {
    if (!AU.on || !AU.ctx) return;
    const t = AU.ctx.currentTime, k = 0.15;
    const n = S.w, q = Math.max(0, S.qt / 2.4);
    const rope = S.rope * (1 - 0.6 * S.dtAir) * (0.6 + 0.4 * Math.sin(S.ropePh));
    AU.water.g.gain.setTargetAtTime(0.05 + 0.28 * Math.min(1.3, q) * (0.3 + 0.7 * Math.min(1, n)) + 0.18 * rope, t, k);
    AU.water.f.frequency.setTargetAtTime(110 + 260 * Math.min(1.3, q) + 120 * n, t, k);
    const ex = Math.min(1.2, S.Vt), ld = Math.min(1.3, S.I);
    AU.hum.forEach(h => { h.o.frequency.setTargetAtTime(Math.max(10, S.fHz) * 2 * h.m, t, 0.05); h.g.gain.setTargetAtTime(h.k * (0.010 * ex * ex + 0.012 * ld * ld) * (n > 0.05 ? 1 : 0), t, k); });
    AU.rough.gain.setTargetAtTime(0.10 * (S.roughH > 0 ? Math.abs(S.roughN) * 0.5 : 0) + 0.10 * rope, t, 0.05);
    AU.spill.gain.setTargetAtTime(Math.min(0.12, 0.012 * (S.qspill + S.qover)), t, 0.4);
    AU.pump.gain.setTargetAtTime(0.004 * ((S.p1Run ? 1 : 0) + (S.p2Run ? 1 : 0) + (S.cwRun ? 1 : 0) + (S.liftRun ? 1.5 : 0)), t, 0.2);
    const hornOn = P.horn && S.dcV > 60;
    AU.horn.gain.setTargetAtTime(hornOn ? 0.05 * ((t * 2.2) % 1 < 0.7 ? 1 : 0.15) : 0, t, 0.015);
  }
  let lastEv = 0;
  function eventSounds() {
    const ev = P.events;
    if (!ev.length) return;
    for (const e of ev) {
      if (e.id <= lastEv) continue;
      lastEv = e.id;
      if (/52G (CLOSED|OPEN)$|52G CLOSED/.test(e.msg) || e.msg === '52G OPEN') blip('breaker');
      else if (/LOCKOUT|TRIP$/.test(e.msg)) blip('relay');
    }
  }

  /* --------------------------------------------------------------- menu */
  const SPEEDS = [0, 1, 2, 5, 10, 30];
  let paused = false;
  function setSpeed(v) {
    paused = v === 0; if (!paused) P.timeScale = v;
    document.querySelectorAll('[data-speed]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.speed === v)));
    const chip = $('#speedchip');
    chip.hidden = v === 1; chip.textContent = paused ? 'PAUSED' : `×${v}`;
  }
  function buildMenu() {
    const fl = $('#faults');
    for (const [id, name] of Object.entries(P.FAULTS)) {
      const l = document.createElement('label'); l.className = 'chk';
      l.innerHTML = `<input type="checkbox" id="f-${id}" data-fault="${id}"><span>${name}</span>`;
      fl.appendChild(l);
    }
    fl.addEventListener('change', e => { const t = e.target; if (t.dataset.fault) P.instructor.fault(t.dataset.fault, t.checked); });
    $('#menuBtn').addEventListener('click', () => toggleMenu());
    $('#menuClose').addEventListener('click', () => toggleMenu(false));
    document.querySelectorAll('[data-speed]').forEach(b => b.addEventListener('click', () => setSpeed(+b.dataset.speed)));
    document.querySelectorAll('[data-go]').forEach(b => b.addEventListener('click', () => { const g = b.dataset.go; if (g === 'home') ROOM.home(); else ROOM.walkToCab(+g); if (window.innerWidth < 700) toggleMenu(false); }));
    document.querySelectorAll('[data-ic]').forEach(b => b.addEventListener('click', () => {
      P.scenario(b.dataset.ic); syncFaultBoxes(); $('#inflow').value = String(Math.round(S.qinBase * 35.3147)); inflowLabel();
    }));
    $('#inflow').addEventListener('input', () => { P.instructor.setInflow(+$('#inflow').value / 35.3147); inflowLabel(); });
    const ev = { flood: () => P.instructor.flood(22), debris: () => P.instructor.debris(), trip: () => P.instructor.gridOutage(false), outage: () => P.instructor.gridOutage(true), sag: () => P.instructor.sag(), fdip: () => P.instructor.freqDip() };
    document.querySelectorAll('[data-ev]').forEach(b => b.addEventListener('click', () => ev[b.dataset.ev]()));
    $('#snd').addEventListener('click', () => setSound(!AU.on));
    $('#hintClose').addEventListener('click', () => { $('#hint').hidden = true; store.set('hint', false); });
    $('#hintBtn').addEventListener('click', () => { $('#hint').hidden = false; });
    window.addEventListener('keydown', e => { if (e.key === 'Escape') toggleMenu(false); });
    inflowLabel();
  }
  function inflowLabel() { $('#inflowV').textContent = `${$('#inflow').value} cfs`; }
  function syncFaultBoxes() { for (const id of Object.keys(P.FAULTS)) { const b = $('#f-' + id); if (b) b.checked = !!S.flt[id]; } }
  function toggleMenu(open) {
    const m = $('#menu'); const show = open === undefined ? m.hidden : open;
    m.hidden = !show; $('#menuBtn').setAttribute('aria-expanded', String(show));
    if (show) refreshMenu();
  }
  function fmtT(t) { return `${String(Math.floor(t / 3600)).padStart(2, '0')}:${String(Math.floor(t / 60) % 60).padStart(2, '0')}:${String(Math.floor(t) % 60).padStart(2, '0')}`; }
  function refreshMenu() {
    if ($('#menu').hidden) return;
    $('#mClock').textContent = fmtT(S.tod);
    $('#mState').textContent = `${S.seqMsg} · ${S.Pkw.toFixed(0)} kW · HW ${(S.hw / P.FT).toFixed(2)} ft · river ${(S.qin * 35.3147).toFixed(0)} cfs`;
    const list = $('#log'); const ev = P.events.slice(-14).reverse();
    const html = ev.map(e => `<li class="${e.kind}"><time>${fmtT(e.t)}</time>${e.msg}</li>`).join('');
    if (list.dataset.h !== html) { list.innerHTML = html; list.dataset.h = html; }
  }

  /* ---------------------------------------------------------- main loop */
  let last = performance.now(), menuAcc = 0;
  function loop(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (!paused) P.advance(dt);
    ROOM.frame(dt);
    eventSounds(); audioUpdate();
    menuAcc += dt; if (menuAcc > 0.5) { menuAcc = 0; refreshMenu(); }
    requestAnimationFrame(loop);
  }
  async function boot() {
    buildMenu();
    if (!ROOM.available()) { $('#nogl').hidden = false; $('#loading').hidden = true; return; }
    const wait = ms => new Promise(r => setTimeout(r, ms));
    if (document.fonts) {
      const faces = ['600 12px "Barlow Semi Condensed"', '700 12px "Barlow Semi Condensed"', '800 12px "Barlow Semi Condensed"', '600 12px "Barlow"', '400 16px "Permanent Marker"'];
      await Promise.race([Promise.all(faces.map(f => document.fonts.load(f).catch(() => null))), wait(3000)]);
    }
    await wait(30);
    ROOM.start({ onTip, onSound: blip });
    $('#loading').hidden = true;
    if (store.get('hint', true)) $('#hint').hidden = false;
    setSound(false);
    setSpeed(1);
    lastEv = P.events.length ? P.events[P.events.length - 1].id : 0;
    requestAnimationFrame(t => { last = t; loop(t); });
  }
  window.SIMUI = { setSpeed, setSound, toggleMenu };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
