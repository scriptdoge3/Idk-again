'use strict';
/* =====================================================================
   MÜHLBACH RUN-OF-RIVER STATION · UNIT 1 · PLANT MODEL
   250 kW vertical Kaplan, direct-coupled 72-pole salient-pole
   synchronous generator, 400 V / 50 Hz / 83.3 min-1, static excitation.
   Everything here is the physics + logic. The cabinets only read it.
   ===================================================================== */
window.PLANT = (() => {

  /* ---------- nameplate & design constants ---------- */
  const R = {
    P: 250, S: 300, V: 400, I: 433, F: 50, POLES: 72, RPM: 83.33,
    Q: 8.6, H: 3.5, IF0: 17.5, RF: 1.6, BLADES: 4,
  };
  const GRAV = 9.81, WB = 2 * Math.PI * 50;
  const KT = R.Q / Math.sqrt(R.H);     // turbine discharge coefficient
  const TW = 1.25;                     // water starting time  [s]
  const HIN = 4.0;                     // inertia constant H   [s] (heavy 72-pole rotor)
  const XD = 1.10, XDP = 0.32, TD0P = 3.2, XE = 0.09, RA = 0.012;
  const WR = 2.7;                      // runaway speed, pu
  const POND_A = 12000, CREST = 214.60, WEIR_L = 18;
  const NL_GATE = 0.095;

  const clamp = (x, a, b) => x < a ? a : x > b ? b : x;
  const rnd = (a = 1) => (Math.random() * 2 - 1) * a;

  /* ---------- turbine characteristics ---------- */
  function etaCam(a) {                 // Kaplan on-cam efficiency vs. gate
    if (a < 0.055) return 0;
    return Math.max(0, 0.915 * (1 - Math.exp(-(a - 0.055) / 0.085)) - 0.10 * (a - 0.72) ** 2);
  }
  function cam(a, h) {                 // combinator: blade vs gate & head
    return clamp(((a - 0.12) / 0.84) * (1 + 0.22 * (h - 1)), 0, 1);
  }
  const bladeDeg = b => -8 + 36 * b;

  /* ---------- state ---------- */
  const P = {};
  function freshState() {
    Object.assign(P, {
      t: 0, tod: 0,
      // river & pond
      qin: 7.6, qinBase: 7.6, qinTarget: 7.6, floodQ: 0, floodT: -1, floodPeak: 0,
      hw: 214.50, tw: 210.82, qspill: 0, qfish: 0.25, qleak: 0, hg: 3.6, debris: 1,
      // turbine water way
      q: 0, hn: 0, G: 0, eff: 0, phyd: 0, rack: 0.03, rackDh: 0.03,
      intake: 1, intakeCmd: 0, intakeEmerg: false,
      // shaft
      w: 0, delta: 0, slips: 0, brakePos: 1, Tm: 0, Pm: 0, shock: 0, damaged: false,
      // governor
      gate: 0, blade: 0.35, bref: 0.35, y: 0, govInt: 0, gateLimit: 0, glTarget: null,
      nref: 1.0, nrefTarget: null, pref: 0, prefTarget: null, levelRef: 214.50, levInt: 0,
      manGate: 0, manBlade: 0.35, govOn: false, startPhase: false, nrefRamp: null, syncArmed: false, emergClose: false,
      govMode: 'SPEED', gateRate: 0, bladeRate: 0, forceLoad: false,
      // oil pressure unit
      oilP: 38.4, oilLvl: 0.62, oilT: 21, pump1: false, pump2: false, pumpDuty: 0,
      p1Run: false, p2Run: false,
      // auxiliaries
      cw: false, cwFlow: 0, lift: false, liftP: 0, acAux: true, dcV: 120.4, dcSoc: 1,
      chargerA: 3.2, rakeRun: false, rakeT: 0, stLoad: 0.012,
      // electrical
      Ep: 0, efd: 0, fcb: false, flashing: false, flashT: 0, flashFail: false,
      avrInt: 0, vref: 1.0, ifRef: 17.5, oelT: 0, limActive: false, vhzLim: false,
      cb: false, cbL: true, cbPend: 0, cbLPend: 0, grid: true, gridF: 1.0, gridFT: 1.0,
      gridV: 1.0, gridVT: 1.0, gridOut: 0, gridSag: 0, feeder: 0.72,
      Vt: 0, Vbus: 1, I: 0, Pe: 0, Qe: 0, id: 0, If: 0, Vf: 0, pf: 1,
      cbTripped: false, syncFail: false, autoSyncT: 0,
      // temperatures °C
      tCw: 11.5, tAmb: 19, tTB: 15, tUGB: 15, tLGB: 15, tTGB: 13, tSt: [16, 16, 16],
      // registers
      kWh: 2840173.4, kvarh: 912455.1, hours: 31842.6, starts: 4127,
      // sequence
      seq: 'STOPPED', seqT: 0, seqFault: false, seqFaultMsg: '',
      req: { cw: false, lift: false, brake: true },
      // protection
      lock86E: false, lock86M: false, estop: false, trips: {}, disk51: 0,
      // instructor faults
      flt: { cw: false, pump1: false, pump2: false, earth: false, diff: false, vtFuse: false,
             avr: false, charger: false, flash: false, bearing: false, oilLeak: false, govSensor: false },
      randomRate: 0, hist: [], histT: 0,
      heater: false, airC: 15, airH: 16, vib: 0, sealP: 0, U0: 0,
    });
    P.sw = {
      unitMode: 'AUTO', cw: 'AUTO', lift: 'AUTO', brake: 'AUTO', rake: 'AUTO',
      pump1: 'AUTO', pump2: 'AUTO', lead: 1, gov: 'LEVEL', blade: 'AUTO', droop: 4,
      avr: 'PF', pf: 0.95, sync: 'OFF', syncCheck: true, tempSel: 0, voltSel: 0, ampSel: 0,
      chart: 1, heater: 'AUTO',
    };
    P.hold = { gateLimit: 0, nref: 0, pref: 0, manGate: 0, manBlade: 0, level: 0, avr: 0 };
    relays.forEach(r => { r.flag = false; r.timer = 0; });
    events.length = 0;
  }

  /* ---------- event log (feeds printer, annunciator and sounds) ---------- */
  const events = [];
  let quiet = false, evId = 0;
  function log(tag, msg, kind = 'info') {
    if (quiet) return;
    events.push({ id: ++evId, t: P.tod, tag, msg, kind });
    if (events.length > 400) events.shift();
  }

  /* =====================================================================
     HYDROLOGY  (slow tick)
     ===================================================================== */
  function hydrology(dt) {
    if (Math.random() < dt / 700) P.qinTarget = clamp(P.qinTarget + rnd(1.8), 3.5, 15);
    P.qinBase += (P.qinTarget - P.qinBase) * dt / 1100;
    if (P.floodT >= 0) {                         // flood hydrograph
      P.floodT += dt;
      const tr = 900, td = 2400;
      P.floodQ = P.floodT < tr ? P.floodPeak * (P.floodT / tr) ** 2
        : P.floodPeak * Math.exp(-(P.floodT - tr) / td);
      P.debris = 1 + 5 * P.floodQ / Math.max(P.floodPeak, 1);
      if (P.floodT > tr + 5 * td) { P.floodT = -1; P.floodQ = 0; P.debris = 1; }
    }
    P.qin = Math.max(0.5, P.qinBase + P.floodQ + 0.12 * Math.sin(P.t / 83) + 0.06 * Math.sin(P.t / 17.3));

    const over = P.hw - CREST;
    P.qspill = over > 0 ? 1.75 * WEIR_L * Math.pow(over, 1.5) : 0;
    P.qfish = 0.25 * clamp((P.hw - 213.6) / 0.5, 0, 1);
    P.qleak = P.gate < 0.01 ? 0.05 * P.intake * Math.sqrt(Math.max(P.hg, 0) / 3.6) : 0;
    const qtot = P.q + P.qspill + P.qfish + P.qleak;
    P.hw += (P.qin - qtot) * dt / POND_A;
    const twT = 210.40 + 0.11 * Math.pow(Math.max(qtot, 0.1), 0.65);
    P.tw += (twT - P.tw) * dt / 45;

    // trash rack fouling
    P.rack += dt * (P.q / R.Q) * P.debris * 1.6e-5;
    if (P.rakeRun) P.rack = Math.max(0.025, P.rack - dt * 0.0022);
    P.rackDh = (P.q / R.Q) ** 2 * (0.04 + P.rack) + 0.004;
  }

  /* =====================================================================
     WATER WAY + TURBINE  (fast)
     ===================================================================== */
  function hydraulics(dt) {
    const Hg = Math.max(0, P.hw - P.tw);
    P.hg = Hg;
    const a = P.gate, b = P.blade;
    let Gc = 0;
    if (a > 0.004) {
      const ga = 1.41421 * a, gb = 1.41421 * (0.3 + 0.7 * b);
      Gc = 1 / Math.sqrt(1 / (ga * ga) + 1 / (gb * gb));
    }
    P.G = Gc;
    const kr = (0.04 + P.rack) / (R.Q * R.Q);
    let Rsum = kr;
    if (P.intake < 0.003) Rsum = Infinity;
    else { const ki = 4 * KT * P.intake; Rsum += 1 / (ki * ki); }
    const Rturb = Gc > 1e-4 ? 1 / ((KT * Gc) ** 2) : Infinity;
    Rsum += Rturb;
    const c = R.Q / (TW * R.H);
    let Q = P.q;
    if (!isFinite(Rsum)) Q = Math.max(0, Q - dt * 4);
    else {                                         // implicit step: stable at any gate
      const A = dt * c * Rsum, B = Q + dt * c * Hg;
      Q = B <= 0 ? 0 : (-1 + Math.sqrt(1 + 4 * A * B)) / (2 * A);
    }
    P.q = Q;
    P.hn = isFinite(Rturb) ? Math.min(Rturb * Q * Q, 2.4 * Hg + 0.4) : Hg;
    const hr = P.hn / R.H;
    const bc = cam(a, hr);
    const eta = etaCam(a) * Math.max(0, 1 - 1.1 * (b - bc) ** 2) * Math.max(0.3, 1 - 0.35 * (hr - 1) ** 2);
    P.eff = eta;
    P.phyd = GRAV * Q * P.hn;                     // kW
    let T0 = eta * P.phyd / R.S;
    if (a < 0.01 && P.intake > 0.5) T0 += 0.0022 * (Hg / 3.6);  // leakage through closed vanes -> creep
    P.Tm = T0 * (WR - P.w) / (WR - 1);
    P.Pm = P.Tm * P.w * R.S;
  }

  /* =====================================================================
     GOVERNOR (electro-hydraulic PID, analog) + servomotors  (fast)
     ===================================================================== */
  function governor(dt) {
    const h = P.hold;
    if (h.gateLimit) P.glTarget = null;
    if (P.glTarget !== null) {
      const d = P.glTarget - P.gateLimit;
      P.gateLimit += clamp(d, -dt / 20, dt / 25);
      if (Math.abs(d) < 1e-4) P.glTarget = null;
    }
    P.gateLimit = clamp(P.gateLimit + h.gateLimit * dt / 25, 0, 1);

    if (h.nref) P.nrefTarget = null;
    if (P.nrefTarget !== null) P.nref += clamp(P.nrefTarget - P.nref, -0.003 * dt, 0.003 * dt);
    P.nref = clamp(P.nref + h.nref * dt * 0.003, 0.90, 1.10);

    if (h.pref) P.prefTarget = null;
    if (P.prefTarget !== null) {
      P.pref += clamp(P.prefTarget - P.pref, -dt / 70, dt / 90);
      if (Math.abs(P.prefTarget - P.pref) < 1e-4) P.prefTarget = null;
    }
    P.levelRef = clamp(P.levelRef + h.level * dt * 0.004, 213.90, 214.80);
    const bp = P.sw.droop / 100;
    const online = P.cb && P.grid && P.cbL;

    let mode = P.sw.gov;
    if (mode !== 'MAN' && !online) mode = 'SPEED';
    if (P.forceLoad && online && mode !== 'MAN') mode = 'LOAD';
    if (mode !== P.govMode) {
      P.govInt = P.y;
      if (mode === 'LOAD' || mode === 'LEVEL') {
        P.pref = clamp(P.Pe, 0, 0.92);
        P.levInt = P.pref - 2.0 * (P.hw - P.levelRef);
      }
      if (mode === 'MAN') P.manGate = P.gate;
      P.govMode = mode;
    }
    if (P.hold.pref && mode === 'LEVEL') { /* setpoint is computed in level mode */ }
    else P.pref = clamp(P.pref + h.pref * dt / 90, 0, 0.92);

    let y;
    if (P.emergClose || !P.govOn) { y = 0; P.govInt = 0; P.startPhase = false; }
    else if (mode === 'MAN') {
      P.manGate = clamp(P.manGate + h.manGate * dt / 30, 0, P.gateLimit);
      y = P.manGate; P.govInt = y;
    } else if (P.startPhase) {
      y = Math.min(0.28, P.gateLimit);
      if (P.w > 0.80) { P.startPhase = false; P.govInt = NL_GATE + 0.05; P.nrefRamp = P.w; }
    } else if (mode === 'SPEED') {
      const wm = P.flt.govSensor ? P.w * 0.97 : P.w;
      if (P.nrefRamp !== null) {
        P.nrefRamp = Math.min(P.nref, P.nrefRamp + 0.012 * dt);
        if (P.nrefRamp >= P.nref || online) P.nrefRamp = null;
      }
      const nr = P.nrefRamp !== null ? P.nrefRamp : P.nref;
      const e = (nr - wm) - (online ? bp : 0) * P.y;
      P.govInt += 0.12 * e * dt;
      y = 1.0 * e + P.govInt;
    } else {
      if (mode === 'LEVEL') {
        const el = P.hw - P.levelRef;
        P.levInt = clamp(P.levInt + 0.004 * el * dt, -0.3, 0.95);
        const target = clamp(2.0 * el + P.levInt, 0.02, 0.92);
        P.pref += clamp(target - P.pref, -dt / 120, dt / 120);
      }
      const fb = bp > 0 ? clamp(-(P.w - 1) / bp, -0.4, 0.4) : 0;
      const e = (P.pref + fb) - P.Pe;
      P.govInt += 0.12 * e * dt;
      y = 0.25 * e + P.govInt;
    }
    const lim = P.gateLimit;
    if (y > lim) { if (mode !== 'MAN') P.govInt -= (y - lim); y = lim; }
    if (y < 0) { P.govInt -= y; y = 0; }
    P.y = y;

    const kp = clamp((P.oilP - 14) / 14, 0, 1);
    const openR = 1 / 14, closeR = P.emergClose ? 1 / 4.5 : 1 / 6;
    let dg = clamp((y - P.gate) / 0.15, -closeR, openR) * kp;
    if (Math.abs(y - P.gate) < 0.0008) dg = 0;
    P.gate = clamp(P.gate + dg * dt, 0, 1);
    P.gateRate = dg;

    let bref;
    if (P.sw.blade === 'MAN') { P.manBlade = clamp(P.manBlade + h.manBlade * dt / 40, 0, 1); bref = P.manBlade; }
    else if ((!P.cb && P.w < 0.85 && P.govOn) || (!P.govOn && P.gate < 0.03)) bref = 0.35;
    else bref = cam(P.gate, P.hn / R.H);
    if (P.sw.blade !== 'MAN') P.manBlade = P.blade;
    P.bref = bref;
    let db = clamp((bref - P.blade) / 0.2, -1 / 28, 1 / 28) * kp;
    if (Math.abs(bref - P.blade) < 0.005) db = 0;
    P.blade = clamp(P.blade + db * dt, 0, 1);
    P.bladeRate = db;
  }

  /* =====================================================================
     OIL PRESSURE UNIT
     ===================================================================== */
  let p1Auto = false, p2Auto = false;
  function opu(dt) {
    const lead = P.sw.lead;
    const pr = P.oilP;
    // automatic lead/lag pressure switches
    const leadOn = pr < 36 ? true : pr > 40 ? false : null;
    const lagOn = pr < 34 ? true : pr > 40 ? false : null;
    if (lead === 1) { if (leadOn !== null) p1Auto = leadOn; if (lagOn !== null) p2Auto = lagOn; }
    else { if (leadOn !== null) p2Auto = leadOn; if (lagOn !== null) p1Auto = lagOn; }
    const want = (sel, a) => sel === 'ON' ? true : sel === 'OFF' ? false : a;
    P.pump1 = want(P.sw.pump1, p1Auto);
    P.pump2 = want(P.sw.pump2, p2Auto);
    P.p1Run = P.pump1 && P.acAux && !P.flt.pump1;
    P.p2Run = P.pump2 && P.acAux && !P.flt.pump2;
    const n = (P.p1Run ? 1 : 0) + (P.p2Run ? 1 : 0);
    let supply = n * 0.42 * clamp((44 - pr) / 4, 0, 1);
    const cons = 0.022 + Math.abs(P.gateRate) * 4.0 + Math.abs(P.bladeRate) * 2.5 + (P.flt.oilLeak ? 0.12 : 0);
    P.oilP = clamp(pr + (supply - cons) * dt, 0, 44.5);
    P.pumpDuty += ((n > 0 ? 1 : 0) - P.pumpDuty) * dt / 300;
    if (P.flt.oilLeak) P.oilLvl = Math.max(0, P.oilLvl - dt * 0.00035);
  }

  /* =====================================================================
     AUXILIARIES: cooling water, oil lift, brakes, rake, intake gate, DC
     ===================================================================== */
  function auxiliaries(dt) {
    const busLive = P.grid && P.cbL;
    const wasAc = P.acAux;
    P.acAux = busLive || (P.cb && P.Vt > 0.7);
    if (wasAc !== P.acAux) log('AUX', P.acAux ? 'AC AUX SUPPLY RESTORED' : 'AC AUX SUPPLY FAILED', P.acAux ? 'info' : 'alarm');
    const sel = (s, r) => s === 'ON' ? true : s === 'OFF' ? false : r;

    P.cw = sel(P.sw.cw, P.req.cw) && P.acAux && !P.flt.cw;
    P.cwFlow += ((P.cw ? 1 : 0) - P.cwFlow) * dt / (P.cw ? 3 : 2);
    P.lift = sel(P.sw.lift, P.req.lift) && P.acAux;
    P.liftP += ((P.lift ? 1 : 0) - P.liftP) * dt / 1.5;

    let applyB = P.sw.brake === 'APPLY' ? true : P.sw.brake === 'RELEASE' ? false : P.req.brake;
    P.brakePos = clamp(P.brakePos + (applyB ? 1 : -1) * dt / 1.4, 0, 1);

    const wasRake = P.rakeRun;
    if (P.sw.rake === 'ON') P.rakeRun = P.acAux;
    else if (P.sw.rake === 'OFF') P.rakeRun = false;
    else {
      if (!P.rakeRun && P.rackDh > 0.20 && P.acAux) { P.rakeRun = true; P.rakeT = 0; }
      if (P.rakeRun) { P.rakeT += dt; if (P.rakeT > 240 || !P.acAux) P.rakeRun = false; }
    }
    if (wasRake !== P.rakeRun) log('AUX', P.rakeRun ? 'TRASH RACK CLEANER RUNNING' : 'TRASH RACK CLEANER STOPPED');

    if (P.intakeEmerg) {
      P.intake = Math.max(0, P.intake - dt / 25);
      if (P.intake <= 0) { P.intakeEmerg = false; log('INT', 'INTAKE GATE CLOSED (EMERGENCY)', 'alarm'); }
    } else if (P.intakeCmd !== 0 && P.acAux) {
      P.intake = clamp(P.intake + P.intakeCmd * dt / 90, 0, 1);
      if ((P.intakeCmd > 0 && P.intake >= 1) || (P.intakeCmd < 0 && P.intake <= 0)) {
        log('INT', P.intakeCmd > 0 ? 'INTAKE GATE OPEN' : 'INTAKE GATE CLOSED');
        P.intakeCmd = 0;
      }
    }

    // station service load, pu of 300 kVA
    P.stLoad = 0.010 + (P.p1Run ? 0.018 : 0) + (P.p2Run ? 0.018 : 0) + (P.cw ? 0.012 : 0)
      + (P.lift ? 0.013 : 0) + (P.rakeRun ? 0.008 : 0) + (P.intakeCmd ? 0.014 : 0);

    // 110 V station battery
    const charger = P.acAux && !P.flt.charger;
    const load = 14 + (P.fcb ? 3 : 0) + (P.flashing ? 22 : 0);
    if (charger) {
      P.dcSoc = Math.min(1, P.dcSoc + dt * 25 / (110 * 3600));
      P.chargerA = load + (P.dcSoc < 0.999 ? 9 : 0.6);
      P.dcV += ((P.dcSoc < 0.999 ? 123.5 : 120.4) - P.dcV) * dt / 6;
    } else {
      P.dcSoc = Math.max(0, P.dcSoc - dt * load / (110 * 3600));
      P.chargerA = 0;
      P.dcV += ((101.5 + 11 * P.dcSoc - 0.08 * load) - P.dcV) * dt / 8;
    }
  }

  /* =====================================================================
     GENERATOR + EXCITATION + NETWORK  (fast)
     ===================================================================== */
  function grid(dt) {
    if (Math.random() < dt / 40) P.gridFT = clamp(1 + rnd(0.0011), 0.997, 1.003);
    P.gridF += (P.gridFT - P.gridF) * dt / 25 + rnd(0.0000035);
    if (Math.random() < dt / 90) P.gridVT = clamp(1.0 + rnd(0.018), 0.97, 1.03);
    P.gridV += (P.gridVT - P.gridV) * dt / 30;
    if (P.gridSag > 0) P.gridSag -= dt;
    if (!P.grid) {
      P.gridOut -= dt;
      if (P.gridOut <= 0) {
        if (P.cbL && P.cb) { if (Math.random() < dt / 5) log('NET', 'UTILITY RECLOSE BLOCKED: LINE LIVE'); }
        else { P.grid = true; P.gridF = 1.0 + rnd(0.0008); P.delta = rnd(Math.PI); log('NET', '20 kV LINE VOLTAGE RESTORED', 'alarm'); }
      }
    }
  }

  function electrical(dt) {
    const busLive = P.grid && P.cbL;
    P.delta += WB * (P.w - P.gridF) * dt;
    if (P.delta > Math.PI) { P.delta -= 2 * Math.PI; if (P.cb && busLive) P.slips++; }
    else if (P.delta < -Math.PI) { P.delta += 2 * Math.PI; if (P.cb && busLive) P.slips++; }

    const w = P.w;
    const E = (P.Ep + 0.025) * w;
    const cd = Math.cos(P.delta), sd = Math.sin(P.delta);
    const Er = E * cd, Ei = E * sd;
    let Ir = 0, Ii = 0, Vr, Vi;
    const vb = P.gridV * (P.gridSag > 0 ? 0.72 : 1);
    if (P.cb && busLive) {
      const X = XDP + XE;
      Ir = Ei / X; Ii = -(Er - vb) / X;
      Vr = vb - XE * Ii; Vi = XE * Ir;
      P.Vbus = vb;
    } else if (P.cb) {
      // island: station service (+ feeder if the line breaker is closed)
      const fl = 1 + 1.2 * (w - 1);
      let Pl = P.stLoad, Ql = P.stLoad * 0.55;
      if (P.cbL) { Pl += P.feeder; Ql += P.feeder * 0.45; }
      const Yg = Math.max(1e-4, Pl * fl), Yb = Ql;
      const den = Yg * Yg + Yb * Yb;
      const Zr = Yg / den, Zi = Yb / den;
      const Tr = Zr, Ti = Zi + XDP, td = Tr * Tr + Ti * Ti;
      Ir = (Er * Tr + Ei * Ti) / td; Ii = (Ei * Tr - Er * Ti) / td;
      Vr = Ir * Zr - Ii * Zi; Vi = Ir * Zi + Ii * Zr;
      P.Vbus = Math.hypot(Vr, Vi);
    } else {
      Vr = Er; Vi = Ei; P.Vbus = busLive ? vb : 0;
    }
    P.Vt = Math.hypot(Vr, Vi);
    P.I = Math.hypot(Ir, Ii);
    P.Pe = Vr * Ir + Vi * Ii;
    P.Qe = Vi * Ir - Vr * Ii;
    P.id = -(Ii * cd - Ir * sd);
    const s = Math.hypot(P.Pe, P.Qe);
    P.pf = s > 0.004 ? P.Pe / s : 1;

    avr(dt);
    const sat = P.Ep > 0.75 ? 0.09 * ((P.Ep - 0.75) / 0.25) ** 2 : 0;
    const tdo = P.fcb ? TD0P : 0.7;
    P.Ep += (P.efd - P.Ep * (1 + sat) - (XD - XDP) * P.id) / tdo * dt;
    if (P.Ep < 0) P.Ep = 0;
    P.If = P.fcb ? Math.max(0, R.IF0 * (P.Ep * (1 + sat) + (XD - XDP) * P.id)) : 0;
    P.Vf = P.fcb ? P.efd * R.IF0 * R.RF : 0;
  }

  function pfTan(pf) {           // selector value: >0 = inductive (lagging), <0 = capacitive
    const a = Math.acos(Math.min(1, Math.abs(pf)));
    return Math.sign(pf) * Math.tan(a);
  }

  function avr(dt) {
    P.limActive = false; P.vhzLim = false;
    if (!P.fcb) { P.efd = 0; P.avrInt = 0; P.flashing = false; return; }
    if (P.flashing) {
      P.efd = P.flt.flash ? 0 : 0.45;
      P.flashT += dt;
      if (P.Vt > 0.40) { P.flashing = false; P.avrInt = 0.9; log('EXC', 'FIELD FLASHING OFF  U>40%'); }
      else if (P.flashT > 10) {
        P.flashing = false; P.fcb = false; P.flashFail = true;
        log('EXC', 'FIELD FLASHING FAILED - FCB OPEN', 'alarm');
      }
      return;
    }
    const ceil = 4.2 * Math.max(P.Vt, 0.0);
    const floor = -0.6 * ceil;
    const mode = P.flt.avr ? 'MAN' : P.sw.avr;
    let target;
    if (mode === 'MAN') {
      P.ifRef = clamp(P.ifRef + P.hold.avr * dt * 0.6, 0, 60);
      const e = (P.ifRef - P.If) / R.IF0;
      P.avrInt += 2.5 * e * dt;
      target = P.avrInt + 1.2 * e;
    } else {
      if (mode === 'AUTO') P.vref = clamp(P.vref + P.hold.avr * dt * 0.004, 0.90, 1.10);
      let vr = P.vref;
      const vhz = 1.06 * P.w;
      if (vr > vhz) { vr = vhz; P.vhzLim = true; }
      if (mode === 'PF' && P.cb && P.grid && P.cbL) {
        const Qref = Math.max(P.Pe, 0) * pfTan(P.sw.pf);
        P.vref = clamp(P.vref + clamp((Qref - P.Qe) * 0.03, -0.006, 0.006) * dt, 0.90, 1.10);
      } else if (mode === 'PF') {
        P.vref = clamp(P.vref + P.hold.avr * dt * 0.004, 0.90, 1.10);
      }
      const e = vr - P.Vt;
      P.avrInt += 6 * e * dt;
      target = P.avrInt + 10 * e;
      P.ifRef = P.If;                               // follow-up of the manual channel
    }
    // over-excitation limiter
    if (P.If > 47) P.oelT += dt; else P.oelT = Math.max(0, P.oelT - dt * 0.5);
    if (P.oelT > 8) {
      const lim = 45 / R.IF0 * 1.0 + 0.6 * (XD - XDP) * 0;
      if (target > P.efd && P.If > 45) { target = Math.min(target, P.efd - 0.3 * dt); P.avrInt = Math.min(P.avrInt, target); }
      P.limActive = true; void lim;
    }
    // under-excitation limiter
    if (P.cb && P.Qe < -0.33 && mode !== 'MAN') {
      target = Math.max(target, P.efd + 0.6 * dt); P.avrInt = Math.max(P.avrInt, target); P.limActive = true;
    }
    if (target > ceil) { target = ceil; P.avrInt = Math.min(P.avrInt, ceil); }
    if (target < floor) { target = floor; P.avrInt = Math.max(P.avrInt, floor); }
    P.efd = target;
  }

  /* =====================================================================
     SHAFT  (fast)
     ===================================================================== */
  function mechanics(dt) {
    const w = P.w;
    const busLive = P.grid && P.cbL;
    const core = P.fcb ? 0.005 * (P.Vt * P.Vt) : 0;
    let Te = (P.cb ? P.Pe + RA * P.I * P.I : 0) + core;
    Te /= Math.max(w, 0.25);
    let Td = (P.cb && busLive) ? clamp(14 * (w - P.gridF), -0.7, 0.7) : 0;
    const churn = P.gate < 0.06 ? 0.030 * (1 - P.gate / 0.06) * w * w : 0;  // runner churning in still water
    const Tl = w > 0 ? 0.0055 + 0.017 * w * w + churn : 0;
    const Tb = P.brakePos * 0.09;
    const drive = P.Tm - Te - Td;
    if (w <= 1e-5 && Math.abs(drive) <= Tb + 0.003) { P.w = 0; return; }
    const net = drive - Tl - (w > 0 ? Tb : 0);
    P.w = Math.max(0, w + net * dt / (2 * HIN));
  }

  /* =====================================================================
     TEMPERATURES (slow)
     ===================================================================== */
  function thermal(dt) {
    const w = P.w, cool = P.cwFlow;
    const ld = clamp(P.q / R.Q, 0, 1.2);
    const tc = P.tCw + (1 - cool) * (P.tAmb - P.tCw);
    const kc = 0.45 + 0.55 * cool;
    let heat = 0.55 * Math.pow(w, 1.5) + 0.40 * w * ld;
    if (w > 0.004 && w < 0.35 && P.liftP < 0.5) heat += 2.4 * (0.35 - w) / 0.35;
    if (P.flt.bearing) heat *= 1.7;
    const n = () => rnd(0.02);
    const wr = Math.min(1, w * 4);
    P.tTB += (tc + 7 * wr + 40 * heat / kc - P.tTB) * dt / 420 + n();
    P.tUGB += (tc + 5 * wr + 26 * w * w / kc - P.tUGB) * dt / 360 + n();
    P.tLGB += (tc + 4 * wr + 23 * w * w / kc - P.tLGB) * dt / 360 + n();
    P.tTGB += (tc + 3 * wr + 20 * w * w * (0.6 + 0.4 * ld) / kc - P.tTGB) * dt / 300 + n();
    const unb = [1.0, 1.015, 0.99];
    for (let k = 0; k < 3; k++) {
      const ex = P.fcb ? P.Vt * P.Vt : 0;
      const tss = tc + 6 * wr + 14 * ex + 58 * (P.I * unb[k]) ** 2 / kc + (k === 1 ? 1.5 : 0);
      P.tSt[k] += (tss - P.tSt[k]) * dt / 700;
    }
    P.oilT += (P.tAmb + 4 + 16 * P.pumpDuty - P.oilT) * dt / 900;
    // generator space heaters and air-water cooler
    P.heater = P.sw.heater === 'ON' || (P.sw.heater === 'AUTO' && w < 0.1 && !P.fcb);
    const i2 = P.I * P.I, ex2 = P.fcb ? P.Vt * P.Vt : 0;
    const cTs = cool > 0.5 ? P.tCw + 9 + 6 * i2 : P.tAmb + 4 + 22 * i2 + 8 * ex2;
    P.airC += (cTs + (P.heater ? 4 : 0) - P.airC) * dt / 240;
    P.airH += (P.airC + 4 * Math.min(1, w) + 20 * i2 + 6 * ex2 + (P.heater ? 5 : 0) - P.airH) * dt / 200;
    // shaft vibration (proximity probes, µm peak-peak)
    const off = Math.abs(P.blade - cam(P.gate, P.hn / R.H));
    const rope = P.cb ? Math.exp(-(((P.gate - 0.30) / 0.07) ** 2)) : 0;
    let vt = w * (16 + 160 * off + 55 * rope) + 260 * P.shock + (P.flt.bearing ? 45 * w : 0) + Math.max(0, w - 1.05) * 300 + (P.slips ? 120 : 0);
    if (P.brakePos > 0.1 && w > 0.05) vt += 60;
    P.vib += (vt - P.vib) * Math.min(1, dt / 1.5);
    P.sealP += ((P.cw ? 2.6 : 0) - P.sealP) * Math.min(1, dt / 3);
    P.U0 = P.flt.earth ? 231 * P.Vt * 0.92 : (P.fcb ? 1.5 + 3.5 * P.Vt * (0.4 + 0.6 * Math.min(1, P.I)) : 0);
  }

  /* =====================================================================
     BREAKERS
     ===================================================================== */
  function syncWindow() {
    const dfHz = Math.abs(P.w - P.gridF) * 50;
    const dv = Math.abs(P.Vt - P.gridV);
    const ang = Math.abs(P.delta) * 180 / Math.PI;
    return { ok: dfHz < 0.25 && dv < 0.10 && ang < 20, dfHz, dv, ang };
  }
  function blockedByTrip() { return P.lock86E || P.lock86M || P.estop || P.damaged; }

  function cmdCbClose(src = 'OPERATOR') {
    if (P.cb || P.cbPend > 0) return false;
    if (blockedByTrip()) { log('52G', 'CLOSE BLOCKED: TRIP RELAY 86 OPERATED'); return false; }
    if (P.dcV < 95) return false;
    const busLive = P.grid && P.cbL;
    if (P.sw.syncCheck) {
      if (busLive) {
        if (P.Vt < 0.5) { log('25', 'CLOSE BLOCKED: GEN VOLTAGE ABSENT'); return false; }
        const s = syncWindow();
        if (!s.ok) { log('25', `CLOSE BLOCKED dF${s.dfHz.toFixed(2)} dU${(s.dv * 100).toFixed(0)}% ${s.ang.toFixed(0)}DEG`); return false; }
      } else if (P.Vt < 0.85) { log('25', 'DEAD BUS CLOSE BLOCKED: GEN U<85%'); return false; }
    }
    P.cbPend = 0.085;  // closing time of the mechanism
    P.cbSrc = src;
    return true;
  }
  function cmdCbOpen(reason = 'OPERATOR', tripped = false) {
    P.cbPend = 0;
    if (!P.cb) return;
    P.cb = false;
    P.cbTripped = tripped;
    P.slips = 0;
    log('52G', tripped ? `GEN CB TRIPPED  ${reason}` : 'GEN CB OPEN', tripped ? 'trip' : 'cb');
    // load rejection logic: snap the governor to no-load opening
    if (P.govOn && P.govMode !== 'MAN') {
      P.govInt = NL_GATE; P.nref = 1.0; P.nrefTarget = null; P.y = NL_GATE;
    }
    P.forceLoad = false;
  }
  function cbCloseNow() {
    P.cb = true; P.cbTripped = false; P.slips = 0;
    if (P.cbSrc === 'AUTOSYNC') P.syncArmed = false;
    const busLive = P.grid && P.cbL;
    const ang = Math.abs(P.delta) * 180 / Math.PI;
    log('52G', busLive ? `GEN CB CLOSED  ${ang.toFixed(0)} DEG ${((P.w - P.gridF) * 50).toFixed(2)} HZ` : 'GEN CB CLOSED ON DEAD BUS', 'cb');
    if (busLive && P.Vt > 0.2) {
      if (ang > 100) {
        P.shock = 1; P.damaged = true;
        log('MECH', 'OUT OF PHASE CLOSURE! SHAFT DAMAGE', 'trip');
        trip('M', 'OUT OF PHASE');
      } else if (ang > 30) {
        P.shock = Math.min(1, ang / 100);
        log('MECH', 'TORQUE SHOCK ON SYNCHRONIZING', 'alarm');
      }
    }
    // bumpless droop insertion: give the unit a little load
    const bp = P.sw.droop / 100;
    if (P.govMode === 'SPEED' && busLive) P.nref = clamp(P.w + bp * (P.y + 0.03), 0.9, 1.1);
  }
  function cmdCbLClose() {
    if (P.cbL || P.cbLPend > 0) return false;
    if (P.dcV < 95) return false;
    if (P.sw.syncCheck && P.grid && P.cb && P.Vt > 0.3) {
      const s = syncWindow();
      if (!s.ok) { log('25', 'LINE CB CLOSE BLOCKED: NOT IN SYNC'); return false; }
    }
    P.cbLPend = 0.12;
    return true;
  }
  function cmdCbLOpen() {
    if (!P.cbL) return;
    P.cbL = false; log('52L', 'LINE CB OPEN', 'cb');
  }
  function breakers(dt) {
    if (P.cbPend > 0) { P.cbPend -= dt; if (P.cbPend <= 0) { P.cbPend = 0; cbCloseNow(); } }
    if (P.cbLPend > 0) {
      P.cbLPend -= dt;
      if (P.cbLPend <= 0) {
        P.cbLPend = 0; P.cbL = true; log('52L', 'LINE CB CLOSED', 'cb');
        if (P.cb && P.grid && Math.abs(P.delta) > 1.75) { P.shock = 1; P.damaged = true; trip('M', 'OUT OF PHASE'); }
      }
    }
    if (P.shock > 0) P.shock = Math.max(0, P.shock - dt * 0.8);
  }

  function cmdExcOn() {
    if (P.fcb) return;
    if (blockedByTrip()) { log('EXC', 'EXCITATION BLOCKED: TRIP ACTIVE'); return; }
    if (P.w < 0.90) { log('EXC', 'EXCITATION BLOCKED: n<90%'); return; }
    P.fcb = true; P.flashFail = false;
    log('41', 'FIELD CB CLOSED', 'cb');
    if (P.Vt < 0.35) { P.flashing = true; P.flashT = 0; log('EXC', 'FIELD FLASHING ON'); }
  }
  function cmdExcOff(force = false) {
    if (!P.fcb) return;
    if (P.cb && !force) { log('EXC', 'DE-EXCITATION BLOCKED: GEN CB CLOSED'); return; }
    P.fcb = false; P.flashing = false;
    log('41', force ? 'FIELD CB TRIPPED' : 'FIELD CB OPEN', 'cb');
  }

  /* =====================================================================
     PROTECTION
     ===================================================================== */
  const maxBrg = () => Math.max(P.tTB, P.tUGB, P.tLGB, P.tTGB);
  const maxSt = () => Math.max(...P.tSt);
  const fGen = () => 50 * P.w;
  const relays = [
    { id: '12', name: 'OVERSPEED', set: 'n> 140 %   t 0.1 s', cls: 'M', delay: 0.1, cond: () => P.w > 1.40 },
    { id: '12M', name: 'MECH. OVERSPEED', set: 'CENTRIF. 155 %', cls: 'M', delay: 0.05, cond: () => P.w > 1.55, intake: true },
    { id: '50/51', name: 'OVERCURRENT', set: 'I> 1.15 In  TMS 0.2', cls: 'E', disk: true },
    { id: '59', name: 'OVERVOLTAGE', set: 'U> 115 %   t 3 s', cls: 'E', delay: 3, cond: () => P.Vt > 1.15 && P.fcb },
    { id: '27', name: 'UNDERVOLTAGE', set: 'U< 80 %   t 2 s', cls: 'N', delay: 2, cond: () => P.cb && !P.flt.vtFuse && P.Vt < 0.80 },
    { id: '81', name: 'FREQUENCY', set: 'f< 47.5  f> 51.5 Hz', cls: 'N', delay: 0.5, cond: () => P.cb && (fGen() < 47.5 || fGen() > 51.5) },
    { id: '32', name: 'REVERSE POWER', set: '-P> 5 %   t 5 s', cls: 'E', delay: 5, cond: () => P.cb && P.Pe < -0.05 },
    { id: '40', name: 'LOSS OF FIELD', set: 'Q< -0.45 pu  t 2 s', cls: 'E', delay: 2, cond: () => P.cb && !P.flt.vtFuse && P.grid && P.cbL && (P.Qe < -0.45 || (P.If < 3 && !P.fcb)) },
    { id: '78', name: 'POLE SLIP', set: '2 SLIPS', cls: 'E', delay: 0, cond: () => P.cb && P.slips >= 2 },
    { id: '64S', name: 'STATOR EARTH FLT', set: 'U0> 10 %   t 0.5 s', cls: 'E', delay: 0.5, cond: () => P.flt.earth && P.Vt > 0.1 },
    { id: '87G', name: 'GEN DIFFERENTIAL', set: 'Id> 15 % In', cls: 'E', delay: 0.04, cond: () => P.flt.diff && P.Vt > 0.1 },
    { id: '49', name: 'STATOR THERMAL', set: 'PT100 > 130 °C', cls: 'E', delay: 5, cond: () => maxSt() > 130 },
    { id: '26', name: 'BEARING TEMP', set: 'PT100 > 80 °C', cls: 'M', delay: 3, cond: () => maxBrg() > 80 },
    { id: '63', name: 'OIL PRESSURE LOW', set: 'p< 28 bar', cls: 'M', delay: 1, cond: () => P.oilP < 28 && (P.w > 0.05 || P.govOn) },
    { id: '71', name: 'OIL SUMP LEVEL', set: 'L< 25 %', cls: 'M', delay: 2, cond: () => P.oilLvl < 0.25 },
    { id: '33', name: 'HEADWATER LOW', set: 'OW< 213.85 m', cls: 'S', delay: 10, cond: () => P.hw < 213.85 && P.w > 0.3 && P.govOn },
  ];
  const relayById = Object.fromEntries(relays.map(r => [r.id, r]));

  function trip(cls, why) {
    if (cls === 'N') {
      if (P.cb) cmdCbOpen(why, true);
      if (P.seq === 'S6_ONLINE') seqGo('S5_SNL');
      return;
    }
    if (cls === 'S') {
      if (/^S\d/.test(P.seq) || P.seq === 'MANUAL') seqGo(P.cb ? 'T1_UNLOAD' : 'T2_DEEXC');
      return;
    }
    if (cls === 'E' && !P.lock86E) { P.lock86E = true; log('86E', 'LOCKOUT ELECTRICAL  ' + why, 'trip'); }
    if (cls === 'M' && !P.lock86M) { P.lock86M = true; log('86M', 'LOCKOUT MECHANICAL  ' + why, 'trip'); }
    if (P.cb) cmdCbOpen(why, true);
    cmdExcOff(true);
    if (cls === 'M') P.emergClose = true;
    P.forceLoad = false;
    if (P.seq !== 'STOPPED' && !P.seq.startsWith('T3') && !P.seq.startsWith('T4') && !P.seq.startsWith('T5')) seqGo('T3_SHUT');
    P.govOn = false;
  }

  function protection(dt) {
    for (const r of relays) {
      if (r.disk) {
        const Is = 1.15, I = P.I;
        if (I > 4.0) r.timer += dt * 20; // instantaneous element
        if (I > Is) {
          const top = 0.14 * 0.2 / (Math.pow(I / Is, 0.02) - 1);
          P.disk51 = Math.min(1.05, P.disk51 + dt / top);
        } else P.disk51 = Math.max(0, P.disk51 - dt / 6);
        if ((P.disk51 >= 1 || r.timer > 1) && !r.flag) { r.flag = true; log(r.id, 'OPERATED ' + r.name, 'trip'); trip('E', r.id + ' ' + r.name); }
        r.timer = Math.max(0, r.timer - dt * 5);
        r.pickup = I > Is;
        continue;
      }
      const c = r.cond();
      r.pickup = c;
      if (c) {
        r.timer += dt;
        if (r.timer >= r.delay && !r.opActive) {
          r.opActive = true;
          if (!r.flag) { r.flag = true; log(r.id, 'OPERATED ' + r.name, 'trip'); }
          trip(r.cls, r.id + ' ' + r.name);
          if (r.intake) { P.intakeEmerg = true; P.intakeCmd = 0; }
        }
      } else { r.timer = Math.max(0, r.timer - dt * 2); r.opActive = false; }
    }
  }

  function resetRelay(id) {
    const r = relayById[id];
    if (!r || !r.flag) return false;
    if (r.disk ? P.I > 1.15 : r.cond()) return false;
    r.flag = false; log(id, 'FLAG RESET');
    if (r.disk) P.disk51 = 0;
    return true;
  }
  function reset86(which) {
    const cls = which === 'E' ? 'E' : 'M';
    const active = relays.filter(r => r.cls === cls && !r.disk && r.cond()).length + (cls === 'M' && P.estop ? 1 : 0);
    if (active) { log('86' + cls, 'RESET REFUSED: TRIP CONDITION PRESENT'); return false; }
    if (cls === 'M' && P.damaged) { log('86M', 'RESET REFUSED: UNIT DAMAGE - INSPECTION'); return false; }
    if (which === 'E' && P.lock86E) { P.lock86E = false; log('86E', 'LOCKOUT RESET'); return true; }
    if (which === 'M' && P.lock86M) { P.lock86M = false; P.emergClose = false; log('86M', 'LOCKOUT RESET'); return true; }
    return false;
  }

  /* =====================================================================
     UNIT SEQUENCER (automatic start / stop)
     ===================================================================== */
  const SEQ_TEXT = {
    STOPPED: 'UNIT STOPPED', S1_AUX: 'START: AUXILIARIES ON', S2_BRAKE: 'START: BRAKES RELEASE',
    S3_ACCEL: 'START: GATES OPENING', S4_EXC: 'START: EXCITATION ON', S5_SNL: 'SPEED NO LOAD - READY TO SYNC',
    S6_ONLINE: 'UNIT ON LINE', T1_UNLOAD: 'STOP: UNLOADING', T2_DEEXC: 'STOP: DE-EXCITATION',
    T3_SHUT: 'STOP: GATES CLOSING', T4_COAST: 'STOP: RUN-DOWN', T5_COOL: 'STOP: COOL-DOWN', MANUAL: 'MANUAL CONTROL',
  };
  function seqGo(s) {
    if (P.seq === s) return;
    P.seq = s; P.seqT = 0;
    log('SEQ', SEQ_TEXT[s] || s, 'seq');
    entry(s);
  }
  function entry(s) {
    switch (s) {
      case 'S1_AUX': P.req.cw = true; P.req.lift = true; P.seqFault = false; break;
      case 'S2_BRAKE': P.req.brake = false; break;
      case 'S3_ACCEL':
        P.govOn = true; P.startPhase = true; P.starts++;
        if (P.gateLimit < 0.30) P.glTarget = 0.30;
        P.nref = 1.0; P.govInt = 0; break;
      case 'S4_EXC': cmdExcOn(); break;
      case 'S6_ONLINE':
        P.glTarget = 1.0;
        if (P.sw.gov === 'LOAD') P.prefTarget = Math.max(P.prefPreset || 0.6, 0.1);
        break;
      case 'T1_UNLOAD': P.forceLoad = true; P.prefTarget = 0; P.pref = Math.min(P.pref, Math.max(P.Pe, 0)); break;
      case 'T2_DEEXC': P.forceLoad = false; if (P.cb) cmdCbOpen('STOP SEQUENCE'); break;
      case 'T3_SHUT': P.glTarget = 0; P.govOn = false; P.forceLoad = false; break;
      case 'T5_COOL': break;
      case 'STOPPED': P.req.cw = false; P.req.lift = false; P.req.brake = true; break;
    }
  }
  function seqFault(msg) {
    P.seqFault = true; P.seqFaultMsg = msg;
    log('SEQ', 'SEQUENCE FAULT: ' + msg, 'alarm');
    seqGo(P.cb ? 'T1_UNLOAD' : (P.fcb ? 'T2_DEEXC' : 'T3_SHUT'));
  }
  function sequence(dt) {
    P.seqT += dt;
    if (P.sw.unitMode === 'MAN') {
      if (P.seq !== 'MANUAL') { P.seq = 'MANUAL'; log('SEQ', 'UNIT CONTROL TRANSFERRED TO MANUAL', 'seq'); }
      P.req.cw = false; P.req.lift = false; P.req.brake = P.w < 0.25 && !P.govOn;
      P.govOn = !blockedByTrip() && P.brakePos < 0.05 && !P.emergClose;
      P.startPhase = false;
      return;
    }
    if (P.seq === 'MANUAL') {
      // back to auto: adopt the present plant state
      if (P.cb) { P.req.cw = true; P.req.lift = false; P.req.brake = false; P.seq = 'S6_ONLINE'; }
      else if (P.w > 0.9 && P.govOn) { P.req.cw = true; P.req.brake = false; P.seq = P.fcb ? 'S5_SNL' : 'S4_EXC'; if (!P.fcb) cmdExcOn(); }
      else if (P.w > 0.01) { P.req.cw = true; P.req.brake = false; P.seq = 'T3_SHUT'; P.glTarget = 0; P.govOn = false; }
      else { P.seq = 'STOPPED'; P.req = { cw: false, lift: false, brake: true }; P.govOn = false; }
      P.seqT = 0; log('SEQ', 'UNIT CONTROL TRANSFERRED TO AUTO', 'seq');
    }
    const w = P.w;
    switch (P.seq) {
      case 'S1_AUX':
        if (P.cwFlow > 0.85 && P.liftP > 0.85 && P.seqT > 4) seqGo('S2_BRAKE');
        else if (P.seqT > 30) seqFault(P.cwFlow < 0.85 ? 'COOLING WATER' : 'OIL LIFT');
        break;
      case 'S2_BRAKE':
        if (P.brakePos < 0.02 && P.seqT > 2) seqGo('S3_ACCEL');
        else if (P.seqT > 15) seqFault('BRAKES NOT RELEASED');
        break;
      case 'S3_ACCEL':
        if (w > 0.90 && P.req.lift) P.req.lift = false;
        if (w > 0.95) seqGo('S4_EXC');
        else if (P.seqT > 180) seqFault('SPEED NOT REACHED');
        break;
      case 'S4_EXC':
        if (P.Vt > 0.92 && P.fcb) seqGo('S5_SNL');
        else if (P.seqT > 30 || (P.flashFail && P.seqT > 1)) seqFault('NO GENERATOR VOLTAGE');
        break;
      case 'S5_SNL':
        P.req.lift = false;
        if (P.cb) seqGo('S6_ONLINE');
        autoSync(dt);
        break;
      case 'S6_ONLINE':
        if (!P.cb) seqGo('S5_SNL');
        break;
      case 'T1_UNLOAD':
        if ((P.Pe < 0.03) || P.seqT > 150) seqGo('T2_DEEXC');
        if (!P.cb) seqGo('T2_DEEXC');
        break;
      case 'T2_DEEXC':
        if (P.cb) cmdCbOpen('STOP SEQUENCE');
        cmdExcOff();
        if (!P.fcb) seqGo('T3_SHUT');
        break;
      case 'T3_SHUT':
        P.govOn = false;
        if (P.gate < 0.01) seqGo('T4_COAST');
        break;
      case 'T4_COAST':
        P.req.cw = true;
        if (w < 0.30) P.req.lift = true;
        if (w < 0.28) P.req.brake = true;
        if (w < 0.0015 && P.seqT > 5) seqGo('T5_COOL');
        if (P.seqT > 900) seqFault('UNIT NOT STOPPING');
        break;
      case 'T5_COOL':
        P.req.lift = false;
        if (P.seqT > 60) seqGo('STOPPED');
        break;
    }
  }

  function readyToStart() {
    return P.seq === 'STOPPED' && !blockedByTrip() && P.oilP > 34 && P.intake > 0.98
      && P.acAux && P.dcV > 105 && P.gate < 0.01 && !P.cb && P.w < 0.02 && P.oilLvl > 0.35;
  }
  function cmdStart() {
    if (P.sw.unitMode !== 'AUTO') { log('SEQ', 'START REFUSED: UNIT IN MANUAL'); return; }
    if (/^S\d/.test(P.seq)) return;
    if (P.seq === 'T4_COAST' || P.seq === 'T5_COOL' || P.seq === 'T3_SHUT') { log('SEQ', 'START REFUSED: UNIT STOPPING'); return; }
    if (!readyToStart()) { log('SEQ', 'START REFUSED: NOT READY'); return; }
    log('SEQ', 'START COMMAND', 'seq');
    seqGo('S1_AUX');
  }
  function cmdStop() {
    if (P.sw.unitMode !== 'AUTO') { log('SEQ', 'STOP REFUSED: UNIT IN MANUAL'); return; }
    if (P.seq === 'STOPPED' || P.seq.startsWith('T')) return;
    log('SEQ', 'STOP COMMAND', 'seq');
    P.prefPreset = Math.max(P.pref, 0.2);
    if (P.cb) seqGo('T1_UNLOAD');
    else if (P.fcb) seqGo('T2_DEEXC');
    else seqGo('T3_SHUT');
  }
  function cmdEstop(on) {
    if (on && !P.estop) {
      P.estop = true; log('ESTOP', 'EMERGENCY STOP PUSHBUTTON', 'trip');
      trip('M', 'EMERGENCY STOP'); P.intakeEmerg = true; P.intakeCmd = 0;
    } else if (!on && P.estop) { P.estop = false; log('ESTOP', 'EMERGENCY STOP RELEASED'); }
  }

  /* ---------- automatic synchronizer ---------- */
  function autoSync(dt) {
    if (P.sw.sync !== 'AUTO' || P.cb || !P.fcb || P.flashing || !P.syncArmed) { P.autoSyncT = 0; return; }
    const busLive = P.grid && P.cbL;
    if (!busLive) return;
    P.autoSyncT += dt;
    // speed matching: aim for slight positive slip (+0.08 Hz)
    if (!P.syncArmed) return;
    const slipT = P.gridF + 0.0016;
    P.nref = clamp(P.nref + clamp((slipT - P.w) * 0.25, -0.0015, 0.0015) * dt, 0.9, 1.1);
    // voltage matching
    if (P.sw.avr !== 'MAN' && !P.flt.avr) P.vref = clamp(P.vref + clamp((P.gridV * 1.01 - P.Vt) * 0.6, -0.01, 0.01) * dt, 0.9, 1.1);
    const s = syncWindow();
    const slipRad = WB * (P.w - P.gridF);
    const adv = slipRad * 0.085;
    const d = P.delta;
    if (s.dfHz < 0.15 && s.dv < 0.05 && slipRad > 0 && d < -adv + 0.05 && d > -adv - 0.10 && P.cbPend === 0) {
      log('25A', 'AUTO SYNCHRONIZER CLOSE PULSE');
      cmdCbClose('AUTOSYNC');
    }
    if (P.autoSyncT > 180 && !P.syncFail) { P.syncFail = true; log('25A', 'SYNCHRONIZING TIME EXCEEDED', 'alarm'); }
  }

  /* ---------- registers ---------- */
  function counters(dt) {
    const exp = P.cb ? (P.Pe - (P.grid && P.cbL ? P.stLoad : 0)) * R.S : 0;
    if (exp > 0 && P.grid && P.cbL) P.kWh += exp * dt / 3600;
    if (P.cb && P.Qe > 0) P.kvarh += P.Qe * R.S * dt / 3600;
    if (P.w > 0.5) P.hours += dt / 3600;
    P.exportKW = exp;
  }

  /* ---------- random malfunctions ---------- */
  const RANDOM_FAULTS = ['cw', 'pump1', 'vtFuse', 'avr', 'charger', 'gridLoss', 'gridSag', 'freqDip', 'flood', 'debris', 'bearing', 'oilLeak'];
  function randomFaults(dt) {
    if (!P.randomRate) return;
    if (Math.random() < dt * P.randomRate / 3600) {
      const f = RANDOM_FAULTS[Math.floor(Math.random() * RANDOM_FAULTS.length)];
      inject(f, true);
    }
  }
  function inject(name, on = true) {
    switch (name) {
      case 'gridLoss':
        if (on && P.grid) { P.grid = false; P.gridOut = 60 + Math.random() * 150; P.feeder = 0.3 + Math.random() * 0.8; log('NET', '20 kV LINE VOLTAGE LOST', 'alarm'); }
        break;
      case 'gridSag': P.gridSag = 0.35 + Math.random() * 0.3; log('NET', 'NETWORK VOLTAGE DIP'); break;
      case 'freqDip': P.gridFT = 0.988 + Math.random() * 0.004; P.gridF -= 0.002; break;
      case 'freqRise': P.gridFT = 1.008 + Math.random() * 0.004; break;
      case 'flood': P.floodT = 0; P.floodPeak = 14 + Math.random() * 24; break;
      case 'drought': P.qinTarget = 2.5 + Math.random(); P.qinBase = Math.min(P.qinBase, 5); break;
      case 'debris': P.rack += 0.12 + Math.random() * 0.1; break;
      case 'trip51': P.disk51 = 1; break;
      default:
        if (name in P.flt) P.flt[name] = on;
    }
  }

  /* =====================================================================
     MAIN STEP
     ===================================================================== */
  let slowAcc = 0;
  const DT = 0.002;
  function step(dt) {
    P.t += dt; P.tod += dt;
    breakers(dt);
    grid(dt);
    governor(dt);
    opu(dt);
    hydraulics(dt);
    electrical(dt);
    mechanics(dt);
    slowAcc += dt;
    if (slowAcc >= 0.02) {
      const s = slowAcc; slowAcc = 0;
      hydrology(s); auxiliaries(s); sequence(s); thermal(s); protection(s); counters(s); randomFaults(s);
      P.histT += s;
      if (P.histT >= 2) { P.histT = 0; P.hist.push([P.t, P.Pe * R.S, P.hw, P.w * 100]); if (P.hist.length > 3200) P.hist.splice(0, 200); }
      if (P.cb && P.cbL && !P.grid && P.seq === 'S6_ONLINE') { /* islanded */ }
    }
  }
  function advance(sec) {
    const n = Math.max(1, Math.ceil(sec / DT));
    const h = sec / n;
    for (let i = 0; i < n; i++) step(h);
  }

  /* ---------- initial conditions ---------- */
  function initOnline() {
    freshState();
    const now = new Date();
    P.tod = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    Object.assign(P, {
      w: 1.0, gridF: 1.0, cb: true, cbL: true, fcb: true, Ep: 1.18, efd: 1.9, avrInt: 1.9, delta: 0.22,
      gate: 0.72, y: 0.72, govInt: 0.72, blade: cam(0.72, 1.02), gateLimit: 1, govOn: true,
      pref: 0.72, levInt: 0.72, govMode: 'LEVEL', q: 7.1, seq: 'S6_ONLINE', brakePos: 0,
      req: { cw: true, lift: false, brake: false }, cw: true, cwFlow: 1, vref: 1.02,
      tTB: 56, tUGB: 41, tLGB: 39, tTGB: 33, tSt: [66, 68, 65], oilT: 31, pumpDuty: 0.3,
      hw: 214.52, qin: 7.6, qinBase: 7.6, qinTarget: 7.8,
    });
    quiet = true;
    P.qinTarget = 7.3 + Math.random() * 1.2;
    advance(240);
    P.qin += 0.6; P.qinBase += 0.6;   // a little freshet so the chart shows some life
    advance(420);
    quiet = false;
    const t0 = P.t; P.hist.forEach(h => { h[0] -= t0; }); P.t = 0;
    events.length = 0;
    log('SYS', 'SIMULATOR READY - INITIAL CONDITION: UNIT ON LINE', 'seq');
  }
  function initStopped() {
    freshState();
    const now = new Date();
    P.tod = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    Object.assign(P, { hw: 214.58, qin: 7.4, qinBase: 7.4, qinTarget: 7.6, tTB: 14, tUGB: 14, tLGB: 14, tTGB: 12.5, tSt: [15, 15.5, 15] });
    quiet = true; advance(300); quiet = false;
    const t0 = P.t; P.hist.forEach(h => { h[0] -= t0; }); P.t = 0; events.length = 0;
    log('SYS', 'SIMULATOR READY - INITIAL CONDITION: UNIT STOPPED', 'seq');
  }
  function repair() {
    P.damaged = false; P.shock = 0;
    for (const k in P.flt) P.flt[k] = false;
    P.oilLvl = Math.max(P.oilLvl, 0.62);
    P.rack = 0.03;
    log('MAINT', 'MAINTENANCE: UNIT INSPECTED AND RELEASED', 'seq');
  }

  freshState();

  return {
    P, R, events, relays, relayById, SEQ_TEXT, step, advance, bladeDeg, cam,
    cmdStart, cmdStop, cmdEstop, cmdExcOn, cmdExcOff,
    cmdCbClose: () => cmdCbClose(), cmdCbOpen: () => cmdCbOpen('OPERATOR', false),
    cmdCbLClose, cmdCbLOpen, resetRelay, reset86, readyToStart, syncWindow, inject, repair,
    initOnline, initStopped, log, CREST,
    intake(cmd) {
      if (P.intakeEmerg) return;
      if (!P.acAux) { log('INT', 'INTAKE GATE: NO AC SUPPLY'); return; }
      if (cmd === 'OPEN' && (P.lock86M || P.estop)) { log('INT', 'INTAKE OPEN BLOCKED: 86M'); return; }
      P.intakeCmd = cmd === 'OPEN' ? 1 : cmd === 'CLOSE' ? -1 : 0;
      log('INT', cmd === 'STOP' ? 'INTAKE GATE STOP' : `INTAKE GATE ${cmd === 'OPEN' ? 'OPENING' : 'CLOSING'}`);
    },
  };
})();
