'use strict';
/* =====================================================================
   SABLE CREEK HYDRO · UNIT 1 · PLANT MODEL
   One 250 kW vertical Francis turbine direct-coupled to a 72-pole,
   480 V, 60 Hz salient-pole synchronous generator (100 rpm), brushless
   exciter with PMG, digital governor and AVR, PLC sequencer.
   Everything physical lives here; the cabinets only read this state
   and send commands. Internal units are SI and per-unit (300 kVA base).
   ===================================================================== */
(function (root) {
const PLANT = (() => {

  /* ------------------------------------------------------------ helpers */
  const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
  const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const rnd = (a = 1) => (Math.random() * 2 - 1) * a;
  let gSpare = null;
  function gauss() {
    if (gSpare !== null) { const v = gSpare; gSpare = null; return v; }
    let u, v, s;
    do { u = Math.random() * 2 - 1; v = Math.random() * 2 - 1; s = u * u + v * v; } while (s >= 1 || s === 0);
    const m = Math.sqrt(-2 * Math.log(s) / s); gSpare = v * m; return u * m;
  }
  const G = 9.81, RHO = 1000, FT = 0.3048;
  const M2PSI = RHO * G / 6894.76;          // metres of water -> psi
  const M2INHG = RHO * G / 3386.39;         // metres of water -> inHg

  /* ------------------------------------------------------- nameplate */
  const NP = { P: 250, S: 300, V: 480, I: 360.8, F: 60, POLES: 72, RPM: 100, HN: 12.2, Q: 2.40, PF: 0.85, IFE: 2.7 };
  const DT = 0.005;                          // fast step = penstock MOC step
  const WB = 2 * Math.PI * NP.F;             // electrical rad/s
  const WM = NP.RPM * Math.PI / 30;          // 10.472 mechanical rad/s
  const SB = NP.S * 1000;
  const TQB = SB / WM;                       // torque base, N·m
  const J = 18000;                           // rotor + runner + shaft, kg·m²
  const HIN = J * WM * WM / (2 * SB);        // inertia constant ≈ 3.3 s

  /* ---------- generator (salient pole, subtransient, pu on 300 kVA) */
  const GEN = { xd: 1.20, xq: 0.72, xdp: 0.30, xpp: 0.20, tdop: 2.2, tdopp: 0.035, tqopp: 0.07, ra: 0.012, satA: 0.82, satB: 2.5, res: 0.015, ifdR: 2.05 };
  /* ---------- brushless exciter (rotating armature, diode bridge) */
  const EXC = { te: 0.6, ke: 1.0, kd: 0.45, kc: 0.18, ax: 0.00236, bx: 0.881, vrmax: 9.0, aPerPu: 0.85, rfe: 18 };
  /* ---------- network: 480 V bus -> 500 kVA 480/12470 V xfmr -> 12.47 kV feeder */
  const NET = { rt: 0.0068, xt: 0.0345, rs: 0.0040, xs: 0.0120, flP: 0.55, flQ: 0.22 };

  /* ---------- Francis runner: geometry + loss coefficients (Euler model) */
  const TB = (() => {
    const D1 = 1.95, B1 = 0.205, D2 = 1.35, DH = 0.47;
    const r1 = D1 / 2, r2 = D2 / 2;
    const A1 = Math.PI * D1 * B1 * 0.92, A2 = Math.PI / 4 * (D2 * D2 - DH * DH);
    const Qbep = 2.10, Hd = 12.2;
    const zg = 0.04, zr = 0.13, zdt = 0.30, zs = 0.9, zsw = 1.0;
    const u1 = WM * r1, u2 = WM * r2, cm1 = Qbep / A1, cm2 = Qbep / A2;
    const beta2 = Math.atan2(cm2, u2), cotb2 = 1 / Math.tan(beta2);
    const w2 = cm2 / Math.sin(beta2);
    const lossFixed = zr * w2 * w2 / 2 + zdt * cm2 * cm2 / 2;
    const qa = zg / 2, qb = u1, qc = zg / 2 * cm1 * cm1 + lossFixed - G * Hd;
    const cu1 = (-qb + Math.sqrt(qb * qb - 4 * qa * qc)) / (2 * qa);
    const cotb1 = (u1 - cu1) / cm1;          // blade inlet angle, shock-free at BEP
    return { D1, D2, r1, r2, A1, A2, a1: 1 / A1, a2: 1 / A2, Qbep, Hd, zg, zr, zdt, zs, zsw, cotb1, cotb2,
      tanAmax: Math.tan(13 * Math.PI / 180), r15: Math.pow(r1, 5), blades: 15, gates: 16 };
  })();
  // gH = A Q² + B ω Q + C ω²   (net head needed to pass Q at speed ω, gate y)
  const TC = { A: 0, B: 0, C: 0, cota: 0 };
  function tcoef(y) {
    const ta = Math.max(y, 0.0025) * TB.tanAmax, cota = 1 / ta, sa2 = ta * ta / (1 + ta * ta);
    const a1 = TB.a1, a2 = TB.a2, kq = a1 * (cota + TB.cotb1), cb = TB.cotb2;
    TC.A = TB.zg / 2 * a1 * a1 / sa2 + TB.zs / 2 * kq * kq + TB.zr / 2 * a2 * a2 * (1 + cb * cb) + TB.zsw / 2 * a2 * a2 * cb * cb + TB.zdt / 2 * a2 * a2;
    TC.B = (TB.r1 * a1 * cota + TB.r2 * a2 * cb) - TB.zs * kq * TB.r1 - TB.zsw * TB.r2 * a2 * cb;
    TC.C = -TB.r2 * TB.r2 + TB.zs / 2 * TB.r1 * TB.r1 + TB.zsw / 2 * TB.r2 * TB.r2;
    TC.cota = cota;
    return TC;
  }
  function runnerTorque(qr, w, cota) {           // Euler: T = ρQ(r1·cu1 − r2·cu2) − disc friction − recirculation
    const cu1 = qr * TB.a1 * cota, cu2 = TB.r2 * w - qr * TB.a2 * TB.cotb2;
    const qb = qr / TB.Qbep;
    const tdf = (0.0026 + 0.027 * Math.max(0, 1 - qb / 0.75) ** 2) * RHO * w * Math.abs(w) * TB.r15;
    return RHO * qr * (TB.r1 * cu1 - TB.r2 * cu2) - tdf;
  }
  function steadyQ(y, w, h) {                    // flow at net head h (no waterway)
    const c = tcoef(y), cc = c.C * w * w - G * h;
    const d = c.B * c.B * w * w - 4 * c.A * cc;
    return d > 0 ? Math.max(0, (-c.B * w + Math.sqrt(d)) / (2 * c.A)) : 0;
  }

  /* ---------- waterway */
  const PEN = { L: 80, D: 1.5, a: 1000, f: 0.013, N: 16 };
  PEN.A = Math.PI * PEN.D * PEN.D / 4; PEN.dx = PEN.L / PEN.N;            // 5 m reaches → Δt = 5 ms
  PEN.B = PEN.a / (G * PEN.A); PEN.R = PEN.f * PEN.dx / (2 * G * PEN.D * PEN.A * PEN.A);
  PEN.kv = 1 / (2 * G * PEN.A * PEN.A);
  const EL = { crest: 510.0 * FT, gateTop: 515.25 * FT, deck: 518.0 * FT, normal: 513.0 * FT, tw0: 470.4 * FT,
    runner: 475.0 * FT, gauge: 476.5 * FT, lowLow: 510.6 * FT, low: 511.5 * FT, high: 514.2 * FT };
  const POND_A = 46000;
  const SPW = { b: 5.0, cw: 2.05, cd: 0.62, max: 1.8, rate: 0.005 };
  const C_SC = 0.15;                                                       // spiral-case compliance, m²

  /* ---------- governor, OPU */
  const AVRG = { kp: 8.0, ki: 9.0, kd: 0.25 };
  const GOV = { kpOff: 3.0, kiOff: 0.55, kdOff: 0.6, kpOn: 1.0, kiOn: 2.5, rp: 0.04, tOpen: 12, tClose: 7, start: 0.30, glMax: 0.95 };
  const OPU = { vt: 0.60, kAir: 2.1713e6 * 0.33, pump: 0.00075, leak: 0.00002, gateVol: 0.012, tivVol: 0.008 };

  /* ---------------------------------------------------------- state */
  const S = {};
  const pen = { H: new Float64Array(PEN.N + 1), Q: new Float64Array(PEN.N + 1), Hn: new Float64Array(PEN.N + 1), Qn: new Float64Array(PEN.N + 1) };
  const sw = {};
  const hold = { gl: 0, spd: 0, avr: 0 };
  let timeScale = 1, quiet = false;
  const events = []; let evId = 0;
  function log(tag, msg, kind = 'info') {
    if (quiet) return;
    events.push({ id: ++evId, t: S.tod, tag, msg, kind });
    if (events.length > 300) events.shift();
  }

  const FAULTS = {
    cwPump: 'Cooling water pump fails', strainer: 'Cooling water strainer clogging', opu1: 'OPU pump 1 fails', opu2: 'OPU pump 2 fails',
    oilLeak: 'Governor oil leak', airLoss: 'Pressure tank air loss', liftPump: 'HP lift pump fails', gateJam: 'Debris jams a wicket gate',
    speedProbe: 'Governor speed probe fails', ringJam: 'Gate operating ring seized', ptFuse: 'AVR sensing PT fuse blown',
    diode: 'Exciter rotating diode fails', thrustBrg: 'Thrust bearing degradation', ground64: 'Stator ground fault',
    stator87: 'Stator phase fault', dcGround: 'DC ground (positive)', charger: 'Battery charger fails', sg1: 'Spillway gate 1 hoist trips',
    cbClose: '52G fails to close', unbalance: 'Rotor unbalance grows',
  };

  function fresh() {
    for (const k of Object.keys(S)) delete S[k];
    const now = new Date();
    Object.assign(S, {
      t: 0, tod: now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds(),
      // river, pond, spillway
      qin: 2.9, qinBase: 2.9, qinTarget: 2.9, floodT: -1, floodPeak: 0, floodQ: 0, hw: EL.normal, tw: EL.tw0 + 0.65,
      qspill: 0, qfish: 0, qover: 0, debris: 1, rackFoul: 0.02, rackDh: 0, rakeRun: false, rakeT: 0,
      sg: [0, 0], sgCmd: [0, 0], sgRun: [0, 0], sgTarget: [0, 0], levelSP: EL.normal, lvlInt: 0, spillInt: 0,
      hg: 1, hgCmd: 0, hgEmerg: false,
      // waterway & turbine
      qr: 0, ql: 0, qt: 0, q0: 0, hN: EL.normal, hsc: EL.normal, hnet: 0, pPen: 0, pSc: 0, pDt: 0,
      tiv: 1, tivCmd: 0, byp: 0, bypCmd: 0, tivDp: 0, tivBlock: false,
      rope: 0, ropeTgt: 0, ropePh: 0, ropeH: 0, roughH: 0, roughN: 0, swirl: 0, qb: 0,
      tTurb: 0, pShaft: 0, pHyd: 0, eff: 0, thrust: 186e3,
      // shaft
      wm: 0, w: 0, delta: 0, brake: 1, brakeHeat: 0, slips: 0, shock: 0, shaftDmg: 0, creepT: 0, mu: 0.0026, mix: 0,
      // governor & servo
      y: 0, yref: 0, dy: 0, gl: 0.95, glTarget: null, nref: 1, pref: 0, prefTarget: null, loadSP: 230, govInt: 0,
      govEn: false, esd: false, govStart: true, nramp: null, nMeas: 0, nPrev: 0, nDer: 0, yJam: null, shearPin: false, govMode: 'OFF',
      // OPU
      opuVo: 0.27, opuKair: OPU.kAir, opuP: 300, opuSump: 0.70, p1Auto: false, p2Auto: false, p1Run: false, p2Run: false, airAdd: 0,
      // aux
      acOK: true, vSS: 480, iSS: 0, ssKW: 8, dcV: 132.4, dcSoc: 1, chgA: 6, dcLoad: 5.5, dcSpring: 0,
      cwRun: false, cwFlow: 0, strDp: 1.0, strFoul: 0.08, backwash: 0, liftRun: false, liftP: 0,
      airP: 104, compRun: false, heater: false, dtAir: 0, sump: 0.35, sumpRun: [false, false],
      req: { cw: false, lift: false, brake: true },
      // excitation & AVR
      psq1: 0, psq2: 0, psd2: 0, ve: 0, vfe: 0, vr: 0, ifd: 0, efd: 0, excOn: false, avrInt: 0, avrE: 0, vtm: 0, vRamp: 0,
      vref: 1.0, qref: 0.15, pfref: 0.97, fcrRef: 1.6, oelHeat: 0, oelInt: 0, uelInt: 0, trim: 0, oel: false, uel: false, vhz: false, avrFail: false,
      // breaker, grid
      cb: false, cbClosing: 0, cbTripping: 0, grid: true, recl: true, reclT: 0, reclShots: 0, outage: 0, outageSust: false,
      gridF: 1, gridFT: 1, gridV: 1.0, gridVT: 1.0, gridTh: 0, sag: 0, fEvent: 0, gridOkT: 999,
      Vt: 0, vbus: 0, angGen: 0, angBus: 0, I: 0, Pe: 0, Qe: 0, Pkw: 0, Qkvar: 0, te: 0, pf: 1, fHz: 0, fBus: 60, id: 0, iq: 0, zr: 99, zx: 99,
      syncAng: 0, slipHz: 0, syncOK: false, autoSync: false, syncT: 0,
      // thermal & condition
      tAmb: 22, tCw: 12, tOilT: 24, tPadT: 25, tUGB: 25, tLGB: 24, tTGB: 22, tOilG: 22, tSt: 25, tAirC: 22, tAirH: 23, tPadHot: 0,
      vib: 0.8, vibN: 0, wipe: 0,
      // registers
      kwh: 1846215.4, kvarh: 512033.8, hours: 41237.4, starts: 3618,
      // PLC
      seq: 'STOPPED', stepT: 0, seqMsg: 'UNIT STOPPED', startFail: '', stopReason: '', autoRestart: false, lowLvlStop: false,
      lock86G: false, lock86M: false, estop: false, trips: {}, targets: {}, relayT: {}, alarmT: {}, cwLossT: 0, lowLvlT: 0,
      flt: {}, plcFault: false, lastA: undefined, pGenLoss: 0, wiped: false, unbG: 0, creep: false, cwT: 0, liftT: 0, chargerOK: true,
      cbTripFlag: false, sgAuto: [0, 0], qinEst: 2.9, hwPrev: EL.normal, opuLvl: 0.45, tivRate: 0, tCwOut: 12, avrD: 0, lowLvlT2: 0,
      syncFailFlag: false, startFailFlag: false, lvlActive: false, effF: 0, govFault: false, govFaultT: 0, trackT: 0, lvlTrim: 0, brakePrev: 1,
    });
    for (const k of Object.keys(FAULTS)) S.flt[k] = false;
    Object.assign(sw, {
      unitMode: 'AUTO', govMode: 'AUTO', syncMode: 'AUTO', syncBypass: false, avrMode: 'PF', levelCtl: 'TURB_SPILL',
      p1: 'AUTO', p2: 'AUTO', lead: 1, cw: 'AUTO', lift: 'AUTO', brake: 'AUTO', dtAir: 'AUTO', heater: 'AUTO', sump: 'AUTO',
      sgMode: ['AUTO', 'AUTO'], vSel: 'AB', aSel: 'A', rtd: 1,
    });
    hold.gl = hold.spd = hold.avr = 0;
    for (let i = 0; i <= PEN.N; i++) { pen.H[i] = EL.normal; pen.Q[i] = 0; }
    ANN.forEach(a => { a.st = 'off'; a.prev = false; });
    events.length = 0;
  }

  /* =====================================================================
     WATERWAY — elastic penstock (method of characteristics), intake,
     inlet valve + spiral case, Francis runner (Euler), draft tube
     ===================================================================== */
  function effGate() {
    let y = S.y;
    if (S.yJam !== null && S.shearPin) y = y + (S.yJam - y) / TB.gates * (S.yJam > y ? 1 : 0);
    return y;
  }
  function tivK(o) {
    const ph = o * Math.PI / 2;
    return Math.min(1e8, (1 / (0.7 * (1 - Math.cos(ph)) + 1e-4) - 1) ** 2 + 0.25);
  }
  function waterway(dt) {
    const N = PEN.N, B = PEN.B, R = PEN.R, H = pen.H, Q = pen.Q, Hn = pen.Hn, Qn = pen.Qn;
    for (let i = 1; i < N; i++) {
      const qa = Q[i - 1], qb = Q[i + 1];
      const CP = H[i - 1] + B * qa - R * qa * Math.abs(qa);
      const CM = H[i + 1] - B * qb + R * qb * Math.abs(qb);
      Hn[i] = (CP + CM) / 2; Qn[i] = (CP - CM) / (2 * B);
    }
    // ---- intake: pond -> trash rack -> headgate -> penstock entrance
    {
      const q1 = Q[1], CM = H[1] - B * q1 + R * q1 * Math.abs(q1);
      const o = S.hg;
      const kg = o < 0.0005 ? 1e9 : Math.max(0, 1 / (0.7 * o * 2.0) - 0.5) ** 2;
      const K = (1.5 + kg) * PEN.kv + (0.03 + S.rackFoul) / (NP.Q * NP.Q);
      const d = S.hw - CM;
      const q0 = d >= 0 ? 2 * d / (B + Math.sqrt(B * B + 4 * K * d)) : -2 * (-d) / (B + Math.sqrt(B * B - 4 * K * d));
      Qn[0] = q0; Hn[0] = CM + B * q0;
      S.rackDh = (0.03 + S.rackFoul) * (q0 / NP.Q) ** 2;
    }
    // ---- draft-tube disturbances: vortex rope (part load) and rough zone (low load)
    const w = S.wm;
    S.ropePh += 2 * Math.PI * 0.28 * (w / (2 * Math.PI)) * dt;
    if (S.ropePh > 2 * Math.PI) S.ropePh -= 2 * Math.PI;
    S.roughN += (gauss() * 2.2 - S.roughN) * dt / 0.12;
    const twe = S.tw + S.ropeH * Math.sin(S.ropePh) + S.roughH * S.roughN;
    // ---- downstream boundary
    const qa = Q[N - 1], CP = H[N - 1] + B * qa - R * qa * Math.abs(qa);
    const y = effGate(), tc = tcoef(y);
    let qr = 0, qN, hN;
    const ql = S.ql;
    if (S.tiv >= 0.02) {
      const K = tivK(S.tiv);
      const a = tc.A / G + (K - 1) * PEN.kv, b = tc.B * w / G + B, c = tc.C * w * w / G + twe - CP + B * ql;
      const disc = b * b - 4 * a * c;
      if (disc > 0) qr = Math.max(0, (-b + Math.sqrt(disc)) / (2 * a));
      qN = qr + ql; hN = CP - B * qN;
      S.hsc = hN - K * PEN.kv * qN * qN;
      S.hnet = S.hsc + PEN.kv * qN * qN - S.tw;
    } else {
      const Cb = 0.047 * S.byp + 0.0015, k = 1 / (Cb * Cb), d = CP - S.hsc;
      qN = d >= 0 ? 2 * d / (B + Math.sqrt(B * B + 4 * k * d)) : -2 * (-d) / (B + Math.sqrt(B * B - 4 * k * d));
      hN = CP - B * qN;
      const hn = S.hsc - twe;
      if (hn > 0) {
        const cc = tc.C * w * w - G * hn, disc = tc.B * tc.B * w * w - 4 * tc.A * cc;
        if (disc > 0) qr = Math.max(0, (-tc.B * w + Math.sqrt(disc)) / (2 * tc.A));
      }
      S.hsc += (qN - qr - ql) * dt / C_SC;
      if (S.hsc < S.tw) S.hsc = S.tw;
      S.hnet = S.hsc - S.tw;
    }
    Qn[N] = qN; Hn[N] = hN;
    for (let i = 0; i <= N; i++) {               // column separation guard (air valve at the high point)
      if (Hn[i] < EL.gauge - 7) Hn[i] = EL.gauge - 7;
      H[i] = Hn[i]; Q[i] = Qn[i];
    }
    S.qr = qr; S.hN = hN; S.q0 = Q[0];
    S.ql = 0.016 * TB.Qbep * Math.sqrt(Math.max(0, S.hnet) / TB.Hd) * Math.min(1, S.y / 0.08);
    S.qt = qr + S.ql;
    // ---- runner torque, swirl, rope, thrust
    S.tTurb = runnerTorque(qr, w, tc.cota) * (1 - 0.004 * S.dtAir);
    const cm2 = qr * TB.a2, cu2 = TB.r2 * w - cm2 * TB.cotb2;
    S.swirl = cm2 > 0.05 ? cu2 / cm2 : 0;
    S.qb = qr / TB.Qbep;
    const n = w / WM;
    const ropeZone = sstep(0.45, 1.3, S.swirl) * (1 - sstep(4.0, 6.5, S.swirl)) * sstep(0.55, 0.9, n);
    S.ropeTgt = ropeZone;
    S.rope += (ropeZone - S.rope) * dt / 2.5;
    S.ropeH = 0.035 * Math.max(S.hnet, 0) * S.rope * (1 - 0.65 * S.dtAir);
    S.roughH = 0.010 * Math.max(S.hnet, 0) * (1 - sstep(0.30, 0.45, S.qb)) * sstep(0.5, 0.9, n) * (qr > 0.05 ? 1 : 0);
    S.pHyd = RHO * G * S.qt * Math.max(S.hnet, 0);
    S.pShaft = S.tTurb * w;
    S.eff = S.pHyd > 2000 ? clamp(S.pShaft / S.pHyd, -1, 0.99) : 0;
    S.effF += (S.eff - S.effF) * dt / 4;
    S.thrust = 186e3 + (0.25 * sstep(0, 0.1, S.qb) + 0.6 * Math.min(S.qb, 1.3)) * 145e3 * Math.max(S.hnet, 0) / TB.Hd;
    // gauges
    S.pPen = (hN - EL.gauge) * M2PSI;
    S.pSc = (S.hsc - EL.gauge) * M2PSI;
    S.tivDp = (hN - S.hsc) * M2PSI;
    S.pDt = (twe - EL.runner - 0.8 * cm2 * cm2 / (2 * G));     // m of water relative to atmosphere
  }

  /* =====================================================================
     SHAFT — rotor, bearings (film / mixed / HP lift), brakes, windage
     ===================================================================== */
  function shaft(dt) {
    const w = S.wm, n = w / WM, F = S.thrust;
    const lift = clamp((S.liftP - 900) / 900, 0, 1);
    const deg = S.flt.thrustBrg ? 1 : 0;
    const muHd = (0.0026 + 0.0012 * deg) * Math.sqrt(Math.max(n, 0.01));
    const muMix = (0.13 + 0.10 * deg) * Math.max(0, 1 - n / 0.12) ** 2 * (1 - lift);
    S.mu = muHd + muMix; S.mix = muMix;
    const rTB = 0.36;
    const brakeF = S.brake * 60e3 * clamp(S.airP / 90, 0, 1.15);
    const tFric = S.mu * F * rTB + 120 * n + 140 * n * Math.abs(n)
      + (S.Vt > 0.1 && n > 0.05 ? 2400 * (S.Vt / Math.max(n, 0.05)) ** 2 * Math.pow(n, 1.4) / w : 0)
      + (n > 0.05 ? Math.max(0, S.efd * S.ifd) * 400 / w : 0)
      + brakeF * 0.35 * 1.1;
    const drive = S.tTurb - S.te * TQB;
    if (Math.abs(w) < 0.004) {
      const stat = (0.15 * (1 - lift) + 0.0006) * F * rTB + brakeF * 0.45 * 1.1;
      if (Math.abs(drive) <= stat) { S.wm = 0; }
      else S.wm += (drive - Math.sign(drive) * tFric) * dt / J;
    } else {
      const nw = w + (drive - Math.sign(w) * tFric) * dt / J;
      S.wm = (nw > 0) !== (w > 0) && Math.abs(drive) < tFric ? 0 : nw;
    }
    S.w = S.wm / WM;
    S.delta += WB * (S.w - 1) * dt;
    if (S.delta > Math.PI) S.delta -= 2 * Math.PI; else if (S.delta < -Math.PI) S.delta += 2 * Math.PI;
    // brake lining heat when applied while turning
    S.brakeHeat = Math.max(0, S.brakeHeat + (brakeF * 0.35 * 1.1 * Math.abs(S.wm) / 1000 - S.brakeHeat * 0.02) * dt);
    // torsional shock from the electrical side
    const tq = Math.abs(S.te);
    if (tq > S.shock) S.shock = tq; else S.shock += (tq - S.shock) * dt / 1.5;
    if (tq > 3.0 && S.cb) { S.shaftDmg = Math.min(1, S.shaftDmg + (tq - 3) * dt * 0.08); }
  }

  /* =====================================================================
     GOVERNOR — digital PID, gate limiter, servomotors, ESD
     ===================================================================== */
  function governor(dt) {
    const nRaw = S.flt.speedProbe ? 0 : S.w;
    S.nMeas += (nRaw - S.nMeas) * dt / 0.04;
    const dn = (S.nMeas - S.nPrev) / dt; S.nPrev = S.nMeas;
    S.nDer += (dn - S.nDer) * dt / 0.25;
    if (hold.gl) S.glTarget = null;
    S.gl = clamp(S.gl + hold.gl * dt * 0.025, 0, 1);
    if (S.glTarget !== null) {
      const d = S.glTarget - S.gl; S.gl += clamp(d, -0.04 * dt, 0.04 * dt);
      if (Math.abs(d) < 1e-4) S.glTarget = null;
    }
    const online = S.cb;
    if (online) {
      if (hold.spd && !S.lvlActive) { S.prefTarget = null; S.pref = clamp(S.pref + hold.spd * dt * 4, 0, 290); S.loadSP = S.pref; }
      if (S.prefTarget !== null) {
        const d = S.prefTarget - S.pref; S.pref += clamp(d, -dt * 5, dt * 3);
        if (Math.abs(d) < 0.01) S.prefTarget = null;
      }
    } else {
      S.nref = clamp(S.nref + hold.spd * dt * 0.0025, 0.90, 1.10);
      S.pref = 0;
    }
    const auto = sw.govMode === 'AUTO';
    let y;
    if (!S.govEn || S.esd) { y = 0; S.govInt = 0; S.govStart = true; S.nramp = null; S.govMode = S.esd ? 'ESD' : 'OFF'; S.govFault = false; }
    else if (!auto) { y = S.gl; S.govInt = S.y; S.govStart = S.nMeas < 0.85; S.govMode = 'MAN'; }
    else if (!online) {
      if (S.govStart) {
        y = Math.min(GOV.start, S.gl); S.govMode = 'START';
        if (S.nMeas > 0.85) { S.govStart = false; S.nramp = S.nMeas; S.govInt = Math.min(S.y, 0.16); }
      } else {
        S.govMode = 'SPEED';
        if (S.nramp !== null) { S.nramp += 0.02 * dt; if (S.nramp >= S.nref) S.nramp = null; }
        const nr = S.nramp !== null ? S.nramp : S.nref;
        const e = nr - S.nMeas;
        S.govInt += GOV.kiOff * e * dt;
        y = GOV.kpOff * e + S.govInt - GOV.kdOff * S.nDer;
      }
    } else {
      S.govMode = 'DROOP';
      const e = (S.nref - S.nMeas) + GOV.rp * (S.pref - S.Pkw) / NP.P;
      S.govInt += GOV.kiOn * e * dt;
      y = GOV.kpOn * e + S.govInt;
    }
    if (S.govFault && S.govEn && auto) { y = S.yref; S.govInt = S.yref; S.govMode = 'HOLD'; }
    if (y > S.gl) { if (auto && S.govEn) S.govInt -= (y - S.gl); y = S.gl; }
    if (y < 0) { if (auto) S.govInt -= y; y = 0; }
    S.yref = y;
    // ---- distributing valve + gate servomotors
    const pOK = clamp((S.opuP - 110) / 130, 0, 1);
    let v = clamp(((S.esd ? -0.2 : y) - S.y) / 0.03, -1, 1);
    if (S.flt.ringJam) v = 0;
    let rate = v > 0 ? v / GOV.tOpen : v / GOV.tClose;
    if (v < 0 && S.y < 0.06) rate *= 0.35;                    // closing cushion
    if (Math.abs(v) < 0.02) rate = 0;
    S.dy = rate * Math.sqrt(pOK);
    S.y = clamp(S.y + S.dy * dt, 0, 1);
    // a jammed wicket gate: the ring keeps moving, the shear pin of the stuck gate fails
    if (S.flt.gateJam && S.yJam === null && S.y > 0.05) S.yJam = S.y;
    if (S.yJam !== null && !S.shearPin && S.y < S.yJam - 0.03) { S.shearPin = true; log('GOV', 'WICKET GATE SHEAR PIN FAILED', 'alarm'); }
  }

  /* =====================================================================
     GENERATOR + NETWORK + BRUSHLESS EXCITER + AVR
     ===================================================================== */
  const C = (r, i) => ({ r, i });
  const cmul = (a, b) => C(a.r * b.r - a.i * b.i, a.r * b.i + a.i * b.r);
  const cadd = (a, b) => C(a.r + b.r, a.i + b.i);
  const csub = (a, b) => C(a.r - b.r, a.i - b.i);
  const cdiv = (a, b) => { const d = b.r * b.r + b.i * b.i; return C((a.r * b.r + a.i * b.i) / d, (a.i * b.r - a.r * b.i) / d); };
  const cinv = a => cdiv(C(1, 0), a);
  const ONE = C(1, 0);

  function gridFast(dt) {
    if (Math.random() < dt / 30) S.gridFT = 1 + rnd(0.00025);
    if (S.fEvent > 0) { S.fEvent -= dt; if (S.fEvent <= 0) S.gridFT = 1; }
    S.gridF += (S.gridFT - S.gridF) * dt / 8 + gauss() * 0.0000012;
    if (Math.random() < dt / 60) S.gridVT = 1.0 + rnd(0.012);
    S.gridV += (S.gridVT - S.gridV) * dt / 20;
    if (S.sag > 0) S.sag -= dt;
    S.gridTh += WB * (S.gridF - 1) * dt;
    if (S.gridTh > Math.PI) S.gridTh -= 2 * Math.PI; else if (S.gridTh < -Math.PI) S.gridTh += 2 * Math.PI;
  }

  function electrical(dt) {
    const w = S.w;
    const gridOn = S.grid && S.recl;
    const fn = S.cb ? Math.max(w, 0.05) : gridOn ? S.gridF : 1;
    // subtransient EMF in the network frame
    const sn = Math.sin(S.delta), cs = Math.cos(S.delta);
    const Eq = w * S.psq2, Ed = w * S.psd2;
    const E = C(Ed * sn + Eq * cs, Eq * sn - Ed * cs);
    const Zg = C(GEN.ra, GEN.xpp * fn), Yg = cinv(Zg);
    const Yt = cinv(C(NET.rt, NET.xt * fn)), Ys = cinv(C(NET.rs, NET.xs * fn));
    const ssP = S.ssKW / NP.S;
    const Yss = C(ssP, -0.55 * ssP / fn);
    const Yfl = C(NET.flP * (1 + 1.4 * (fn - 1)), -NET.flQ / fn);
    const vg = S.gridV * (S.sag > 0 ? 0.70 : 1);
    const Vg = C(vg * Math.cos(S.gridTh), vg * Math.sin(S.gridTh));
    let Y11 = cadd(Yss, Yt); if (S.cb) Y11 = cadd(Y11, Yg);
    let Y22 = cadd(Yt, Yfl); if (gridOn) Y22 = cadd(Y22, Ys);
    const Y12 = C(-Yt.r, -Yt.i);
    const I1 = S.cb ? cmul(E, Yg) : C(0, 0), I2 = gridOn ? cmul(Vg, Ys) : C(0, 0);
    const det = csub(cmul(Y11, Y22), cmul(Y12, Y12));
    const V1 = cdiv(csub(cmul(I1, Y22), cmul(Y12, I2)), det);
    let I = C(0, 0), Vt = E;
    if (S.cb) { I = cmul(csub(E, V1), Yg); Vt = V1; }
    S.Vt = Math.hypot(Vt.r, Vt.i);
    S.vbus = Math.hypot(V1.r, V1.i);
    S.angGen = Math.atan2(Vt.i, Vt.r); S.angBus = Math.atan2(V1.i, V1.r);
    S.I = Math.hypot(I.r, I.i);
    S.Pe = Vt.r * I.r + Vt.i * I.i; S.Qe = Vt.i * I.r - Vt.r * I.i;
    S.Pkw = S.Pe * NP.S; S.Qkvar = S.Qe * NP.S;
    const sa = Math.hypot(S.Pe, S.Qe); S.pf = sa > 0.005 ? S.Pe / sa : 1;
    S.fHz = 60 * w; S.fBus = S.cb ? 60 * w : gridOn ? 60 * S.gridF : 60 * w;
    if (S.I > 0.02) { const z = cdiv(Vt, I); S.zr = z.r; S.zx = z.i; } else { S.zr = 99; S.zx = 99; }
    // rotor frame currents
    const Id = I.r * sn - I.i * cs, Iq = I.r * cs + I.i * sn;
    S.id = Id; S.iq = Iq;
    S.te = S.psd2 * Id + S.psq2 * Iq;
    // field & dampers
    const psi = Math.hypot(S.psq2, S.psd2);
    const sat = psi > GEN.satA ? GEN.satB * (psi - GEN.satA) ** 2 : 0;
    S.psq1 += (S.efd + GEN.res - S.psq1 - (GEN.xd - GEN.xdp) * Id - sat * S.psq2 / Math.max(psi, 0.01)) / GEN.tdop * dt;
    S.psq2 += (S.psq1 - S.psq2 - (GEN.xdp - GEN.xpp) * Id) / GEN.tdopp * dt;
    S.psd2 += (-S.psd2 + (GEN.xq - GEN.xpp) * Iq) / GEN.tqopp * dt;
    S.ifd = Math.max(0, S.psq1 + (GEN.xd - GEN.xdp) * Id + sat - GEN.res);
    // 50 instantaneous element sees the current every step
    if (S.cb && S.I > 6.0) relayTrip('50', '86G');
    if (S.cb && S.flt.stator87) relayTrip('87G', '86G');
    // pole slipping (78)
    if (S.cb && gridOn) {
      const a = Math.atan2(Math.sin(S.angGen - S.gridTh), Math.cos(S.angGen - S.gridTh));
      if (S.lastA !== undefined && Math.abs(a - S.lastA) > Math.PI) { S.slips++; log('PROT', 'POLE SLIP DETECTED', 'alarm'); }
      S.lastA = a;
    } else S.lastA = undefined;
    avr(dt);
    exciter(dt);
  }

  function exciter(dt) {
    const se = S.ve > 0 ? EXC.ax * Math.exp(EXC.bx * S.ve) : 0;
    S.vfe = EXC.ke * S.ve + se * S.ve + EXC.kd * S.ifd;
    S.ve = Math.max(0, S.ve + (S.vr - S.vfe) / EXC.te * dt);
    const IN = S.ve > 1e-3 ? EXC.kc * S.ifd / S.ve : 0;
    const fex = IN <= 0.433 ? 1 - 0.577 * IN : IN <= 0.75 ? Math.sqrt(0.75 - IN * IN) : IN <= 1 ? 1.732 * (1 - IN) : 0;
    S.efd = S.flt.diode ? 0 : S.ve * fex * clamp(S.w, 0, 1.3);
  }

  function avr(dt) {
    const w = S.w;
    const sensed = S.flt.ptFuse ? S.Vt * 0.58 : S.Vt;
    S.vtm += (sensed - S.vtm) * dt / 0.02;
    const supply = clamp(w / 0.9, 0, 1.15);               // PMG voltage follows speed
    const online = S.cb && S.grid && S.recl;
    if (!S.excOn) { S.vr = 0; S.avrInt = 0; S.vRamp = 0; S.oel = S.uel = S.vhz = false; S.trim = 0; return; }
    S.vRamp = Math.min(1, S.vRamp + dt / 6);
    const mode = sw.avrMode;
    // operator raise/lower on the active setpoint; others track
    if (hold.avr) {
      if (mode === 'AVR') S.vref = clamp(S.vref + hold.avr * dt * 0.005, 0.90, 1.10);
      else if (mode === 'VAR') S.qref = clamp(S.qref + hold.avr * dt * 0.02, -0.40, 0.60);
      else if (mode === 'PF') S.pfref = clamp(S.pfref - hold.avr * dt * 0.006, 0.80, 1.20);   // >1 = leading
      else S.fcrRef = clamp(S.fcrRef + hold.avr * dt * 0.02, 0, 6);
    }
    // outer loops (online only): VAR / PF trim the voltage reference
    let target = S.vref;
    if (online && (mode === 'VAR' || mode === 'PF')) {
      let qset = S.qref;
      if (mode === 'PF') { const p = Math.max(S.Pe, 0); const pfv = S.pfref <= 1 ? S.pfref : 2 - S.pfref; qset = Math.sign(1 - S.pfref + 1e-9) * p * Math.tan(Math.acos(clamp(pfv, 0.5, 1))); }
      S.trim = clamp(S.trim + clamp((qset - S.Qe) * 0.15, -0.006, 0.006) * dt, -0.12, 0.12);
      target = 1.0 + S.trim;
    } else if (mode !== 'FCR') { S.trim = S.vref - 1.0; }
    // V/Hz limiter
    let vr = Math.min(target, 1.08 * w) * S.vRamp;
    S.vhz = target > 1.08 * w + 0.002 && w > 0.5;
    // reactive droop compensation
    if (S.cb) vr -= 0.04 * S.Qe;
    // over-excitation limiter (inverse time on calculated main-field current)
    const ifdPu = S.ifd / GEN.ifdR;
    S.oelHeat = Math.max(0, S.oelHeat + ((ifdPu > 1.05 ? (ifdPu * ifdPu - 1.1) : -0.2)) * dt);
    if (S.oelHeat > 10 || ifdPu > 1.6) S.oelInt = Math.min(0.3, S.oelInt + (ifdPu - 1.02) * dt * 0.4);
    else S.oelInt = Math.max(0, S.oelInt - dt * 0.01);
    S.oel = S.oelInt > 0.002;
    // under-excitation limiter
    const qmin = -(0.32 - 0.12 * Math.max(S.Pe, 0));
    if (S.cb && S.Qe < qmin) S.uelInt = Math.min(0.2, S.uelInt + (qmin - S.Qe) * dt * 0.6);
    else S.uelInt = Math.max(0, S.uelInt - dt * 0.004);
    S.uel = S.uelInt > 0.002;
    vr += S.uelInt - S.oelInt;
    const vmax = EXC.vrmax * supply;
    if (mode === 'FCR') {
      const e = S.fcrRef - S.vfe;
      S.avrInt = clamp(S.avrInt + 3.0 * e * dt, 0, vmax);
      S.vr = clamp(1.2 * e + S.avrInt, 0, vmax);
      S.vref = clamp(S.Vt, 0.9, 1.1);
    } else {
      const e = vr - S.vtm;
      S.avrD += ((e - S.avrE) / dt - S.avrD) * dt / 0.06; S.avrE = e;
      S.avrInt = clamp(S.avrInt + AVRG.ki * e * dt, -1, vmax);
      S.vr = clamp(AVRG.kp * e + S.avrInt + AVRG.kd * S.avrD, 0, vmax);
      S.fcrRef = S.vfe;
    }
    if (S.flt.avr) S.vr = vmax;
  }

  /* =====================================================================
     BREAKER 52G, SYNCHRONIZING (25 + auto-synchronizer)
     ===================================================================== */
  function breaker(dt) {
    if (S.cbClosing > 0) {
      S.cbClosing -= dt;
      if (S.cbClosing <= 0) {
        S.cbClosing = 0;
        if (S.flt.cbClose) { log('52G', '52G FAILED TO CLOSE', 'alarm'); S.syncFailFlag = true; }
        else if (!S.cb && !anyLock()) {
          S.cb = true; S.dcSpring = 10;
          const ang = Math.abs(S.syncAng) * 180 / Math.PI;
          log('52G', `52G CLOSED  ${ang.toFixed(0)}° ${S.slipHz >= 0 ? '+' : ''}${S.slipHz.toFixed(2)} Hz`, ang > 20 ? 'alarm' : 'info');
          if (ang > 20) log('52G', 'OUT-OF-PHASE CLOSING', 'alarm');
          S.nref = 1.0; S.pref = Math.max(S.Pkw, 8); S.prefTarget = null;
        }
      }
    }
    if (S.cbTripping > 0) {
      S.cbTripping -= dt;
      if (S.cbTripping <= 0) { S.cbTripping = 0; if (S.cb) { S.cb = false; S.dcSpring = 10; log('52G', '52G OPEN'); } }
    }
  }
  function cbClose(src) {
    if (S.cb || S.cbClosing > 0) return;
    if (S.dcV < 90) { log('52G', '52G CLOSE BLOCKED: DC LOW'); return; }
    if (anyLock()) { log('52G', '52G CLOSE BLOCKED: LOCKOUT'); return; }
    const deadBus = S.vbus < 0.2;
    if (!sw.syncBypass && !(S.syncOK && !deadBus)) { log('25', `CLOSE BLOCKED BY 25 (${src})`); return; }
    S.cbClosing = 0.083;
  }
  function cbTrip(why, protective) {
    if (!S.cb && S.cbTripping <= 0) return;
    if (S.cbTripping > 0) return;
    S.cbTripping = 0.05; if (protective && S.cb) S.cbTripFlag = true;
    if (why) log('52G', `52G ${protective ? 'TRIP' : 'OPEN'}: ${why}`, protective ? 'alarm' : 'info');
  }
  function syncCalc(dt) {
    const gridLive = S.vbus > 0.3;
    const genLive = S.Vt > 0.3;
    let a = S.angGen - S.angBus; a = Math.atan2(Math.sin(a), Math.cos(a));
    S.syncAng = (genLive && gridLive && !S.cb) ? a : 0;
    S.slipHz = !S.cb && gridLive ? (S.w - S.gridF) * 60 : 0;
    S.syncOK = !S.cb && genLive && gridLive && Math.abs(S.Vt - S.vbus) < 0.05 && Math.abs(S.slipHz) < 0.2 && Math.abs(a) < 15 * Math.PI / 180;
    // automatic synchronizer
    const want = sw.syncMode === 'AUTO' && !S.cb && S.excOn && S.w > 0.95 && S.govEn && sw.govMode === 'AUTO' && !anyLock()
      && (sw.unitMode === 'MAN' || S.seq === 'SYNC');
    S.autoSync = want;
    if (!want) { S.syncT = 0; return; }
    S.syncT += dt;
    if (!gridLive) return;
    // speed matching: aim for +0.06 Hz slip (generator slightly fast)
    const tgt = S.gridF + 0.06 / 60;
    S.nref += clamp(tgt - S.nref, -0.002 * dt, 0.002 * dt);
    // voltage matching
    const dv = S.vbus - S.Vt;
    if (Math.abs(dv) > 0.008 && sw.avrMode !== 'FCR') S.vref = clamp(S.vref + clamp(dv, -0.01, 0.01) * dt * 1.5, 0.92, 1.08);
    // closing with breaker-time compensation
    if (S.syncOK && S.cbClosing <= 0 && S.slipHz > 0.01) {
      const lead = 2 * Math.PI * S.slipHz * 0.083;
      if (a < 0 && a + lead > -0.03 && a + lead < 0.03) { cbClose('AUTO SYNC'); }
    }
    if (S.syncT > 180 && !S.syncFailFlag) { S.syncFailFlag = true; log('SYNC', 'AUTO SYNC FAILED (180 s)', 'alarm'); }
  }

  /* =====================================================================
     PROTECTION — generator relay (numerical) + PLC mechanical trips
     ===================================================================== */
  const anyLock = () => S.lock86G || S.lock86M || S.estop;
  function relayTrip(id, act) {
    if (S.targets[id]) { if (act === '52G') cbTrip(id, true); return; }
    S.targets[id] = true;
    const names = { 24: 'V/Hz', 27: 'UNDERVOLTAGE', 59: 'OVERVOLTAGE', '81O': 'OVERFREQUENCY', '81U': 'UNDERFREQUENCY', 32: 'REVERSE POWER',
      40: 'LOSS OF FIELD', '51V': 'VOLTAGE-RESTRAINED OVERCURRENT', 50: 'INSTANTANEOUS OVERCURRENT', '87G': 'GENERATOR DIFFERENTIAL',
      '64G': 'STATOR GROUND', 78: 'OUT OF STEP', '12E': 'ELECTRONIC OVERSPEED', '12M': 'MECHANICAL OVERSPEED', 38: 'BEARING TEMPERATURE',
      49: 'STATOR TEMPERATURE', 63: 'GOVERNOR OIL PRESSURE LOW', 39: 'VIBRATION', 71: 'OPU SUMP LEVEL LOW', ES: 'EMERGENCY STOP' };
    log('PROT', `${id} ${names[id] || ''} TRIP`, 'trip');
    if (act === '86G') lockout('86G', id);
    else if (act === '86M') lockout('86M', id);
    else cbTrip(id, true);
  }
  function lockout(which, why) {
    if (which === '86G') { if (!S.lock86G) log('86G', `86G LOCKOUT (${why})`, 'trip'); S.lock86G = true; }
    else { if (!S.lock86M) log('86M', `86M LOCKOUT (${why})`, 'trip'); S.lock86M = true; S.esd = true; S.tivCmd = -1; }
    cbTrip(null, true);
    S.excOn = false;
    S.govEn = false;
    S.autoSync = false;
    if (S.seq !== 'STOPPED') toSeq('DECEL');
    S.trips[why] = true;
  }
  function timer(id, cond, t, dt) {
    if (cond) { S.relayT[id] = (S.relayT[id] || 0) + dt; return S.relayT[id] >= t; }
    S.relayT[id] = 0; return false;
  }
  let disk51 = 0;
  function protection(dt) {
    const online = S.cb;
    const vhz = S.Vt / Math.max(S.w, 0.05);
    if (timer('24a', S.w > 0.5 && vhz > 1.10, 5, dt) || timer('24b', S.w > 0.5 && vhz > 1.18, 1, dt)) relayTrip('24', '86G');
    if (timer('27', online && S.Vt < 0.85, 2.0, dt)) relayTrip('27', '52G');
    if (timer('59', S.Vt > 1.10, 2.0, dt) || timer('59i', S.Vt > 1.20, 0.1, dt)) relayTrip('59', online ? '52G' : '86G');
    if (timer('81O', online && S.fHz > 60.5, 0.16, dt)) relayTrip('81O', '52G');
    if (timer('81U', online && S.fHz < 59.3, 0.16, dt)) relayTrip('81U', '52G');
    if (timer('32', online && S.Pkw < -12, 5, dt)) relayTrip('32', '52G');
    // 40: offset mho, offset X'd/2, diameter Xd
    const zx0 = -GEN.xdp / 2, zr0 = -(GEN.xdp / 2 + GEN.xd / 2);
    const inLof = online && S.I > 0.05 && Math.hypot(S.zr, S.zx - zr0) < GEN.xd / 2 && S.zx < zx0;
    if (timer('40', inLof, 0.5, dt)) relayTrip('40', '86G');
    // 51V: voltage restrained IEC very inverse
    const pk = 1.4 * clamp(S.Vt / 0.9, 0.25, 1);
    if (online && S.I > pk) disk51 += dt / (0.5 * 13.5 / (S.I / pk - 1)); else disk51 = Math.max(0, disk51 - dt / 4);
    if (disk51 >= 1) { relayTrip('51V', '86G'); disk51 = 0; }
    if (timer('64G', S.flt.ground64 && S.Vt > 0.2, 1.0, dt)) relayTrip('64G', '86G');
    if (S.slips >= 2) { relayTrip('78', '86G'); S.slips = 0; }
    // PLC mechanical
    if (S.w > 1.40) relayTrip('12E', '86M');
    if (S.w > 1.50) { relayTrip('12M', '86M'); if (!S.hgEmerg && S.hg > 0) { S.hgEmerg = true; log('INT', 'HEADGATE EMERGENCY CLOSURE', 'alarm'); } }
    if (timer('38', S.tPadT > 90 || S.tUGB > 85 || S.tLGB > 85 || S.tTGB > 85, 3, dt)) relayTrip('38', '86M');
    if (timer('49', S.tSt > 135, 10, dt)) relayTrip('49', '86G');
    if (timer('63', S.opuP < 220, 2, dt)) relayTrip('63', '86M');
    if (timer('39', S.vib > 12, 3, dt)) relayTrip('39', '86M');
    if (timer('71', S.opuSump < 0.15, 3, dt)) relayTrip('71', '86M');
    if (S.estop && !S.trips.ES) { log('UNIT', 'EMERGENCY STOP PUSHED', 'trip'); S.trips.ES = true; lockout('86M', 'ES'); }
  }

  /* =====================================================================
     PLC — unit sequencer, auxiliaries logic, level control, spillway
     ===================================================================== */
  const STEPNO = { STOPPED: 0, PRESTART: 1, TIV: 2, BRAKES: 3, ACCEL: 4, EXCITE: 5, SYNC: 6, ONLINE: 7, UNLOAD: 8, SNL: 9, DECEL: 10, STANDSTILL: 11 };
  const SEQTXT = { STOPPED: 'UNIT STOPPED', PRESTART: 'STARTING AUXILIARIES', BRAKES: 'RELEASING BRAKES', TIV: 'OPENING INLET VALVE',
    ACCEL: 'ACCELERATING', EXCITE: 'EXCITING', SYNC: 'SYNCHRONIZING', ONLINE: 'ON LINE', UNLOAD: 'UNLOADING', SNL: 'SPEED NO LOAD',
    DECEL: 'DECELERATING', STANDSTILL: 'STANDSTILL' };
  function toSeq(s) { if (S.seq === s) return; S.seq = s; S.stepT = 0; S.seqMsg = SEQTXT[s]; if (s !== 'STOPPED') log('SEQ', `STEP ${STEPNO[s]}: ${SEQTXT[s]}`); }
  function permissives() {
    return [
      ['NO LOCKOUT', !S.lock86G && !S.lock86M && !S.estop],
      ['OPU PRESSURE', S.opuP > 260],
      ['STATION AIR', S.airP > 80],
      ['AC STATION SERVICE', S.acOK],
      ['125 VDC', S.dcV > 110],
      ['WICKET GATES CLOSED', S.y < 0.02],
      ['HEADGATE OPEN', S.hg > 0.98],
      ['52G OPEN', !S.cb],
      ['HEADWATER > LOW-LOW', S.hw > EL.lowLow],
      ['UNIT MODE AUTO', sw.unitMode === 'AUTO'],
      ['GOVERNOR AUTO', sw.govMode === 'AUTO'],
    ];
  }
  function startFail(msg) { S.startFail = msg; log('SEQ', `START FAILED: ${msg}`, 'alarm'); S.startFailFlag = true; normalStop('START FAIL'); }
  function normalStop(why) {
    S.stopReason = why || 'OPERATOR';
    if (S.seq === 'STOPPED' || S.seq === 'DECEL' || S.seq === 'STANDSTILL') return;
    log('SEQ', `STOP: ${S.stopReason}`);
    S.autoSync = false;
    if (S.cb) { toSeq('UNLOAD'); S.prefTarget = 0; }
    else { S.excOn = false; S.govEn = false; toSeq('DECEL'); }
  }
  function startUnit() {
    if (sw.unitMode !== 'AUTO') { // manual: START enables the governor only
      if (anyLock()) { log('UNIT', 'START BLOCKED: LOCKOUT'); return; }
      S.govEn = true; S.esd = false; log('GOV', 'GOVERNOR ENABLED (MANUAL)');
      return;
    }
    if (S.seq === 'SNL') { toSeq('SYNC'); return; }
    if (S.seq !== 'STOPPED') return;
    const bad = permissives().filter(p => !p[1]);
    if (bad.length) { log('SEQ', `START BLOCKED: ${bad[0][0]}`, 'alarm'); S.startFail = bad[0][0]; return; }
    S.startFail = ''; S.startFailFlag = false; S.syncFailFlag = false; S.lowLvlStop = false;
    S.starts++; log('SEQ', 'START COMMAND'); toSeq('PRESTART');
  }
  function sequence(dt) {
    S.stepT += dt;
    const n = S.w;
    const wasLvl = S.lvlActive; S.lvlActive = false;
    if (sw.unitMode !== 'AUTO') {
      // manual mode: aux in AUTO follow simple speed logic
      S.req.cw = S.govEn || n > 0.02;
      S.req.lift = n > 0.003 && n < 0.9 || (S.govEn && n < 0.9);
      S.req.brake = !S.govEn && n < 0.25 && !S.cb;
      if (S.seq !== 'MANUAL') { S.seq = 'MANUAL'; S.seqMsg = 'MANUAL CONTROL'; }
      return;
    }
    if (S.seq === 'MANUAL') { S.seq = !S.govEn ? (n > 0.003 ? 'DECEL' : 'STOPPED') : S.cb ? 'ONLINE' : n > 0.9 ? 'SNL' : 'DECEL'; if (S.seq === 'DECEL') S.govEn = false; S.seqMsg = SEQTXT[S.seq]; S.stepT = 0; log('SEQ', `AUTO: ${S.seqMsg}`); }
    switch (S.seq) {
      case 'STOPPED':
        S.req.cw = false; S.req.lift = n > 0.003; S.req.brake = true; S.govEn = false;
        if (S.autoRestart && S.lowLvlStop && S.hw > S.levelSP + 0.1 && permissives().every(p => p[1])) { log('SEQ', 'AUTO RESTART ON LEVEL'); startUnit(); }
        break;
      case 'PRESTART':
        S.req.cw = true; S.req.lift = true;
        if (S.cwFlow > 40 && S.liftP > 1800) toSeq('TIV');
        else if (S.stepT > 40) startFail(S.cwFlow <= 40 ? 'COOLING WATER FLOW' : 'HP LIFT PRESSURE');
        break;
      case 'TIV':
        if (S.tiv >= 0.999) { S.bypCmd = -1; toSeq('BRAKES'); break; }
        if (S.tivCmd <= 0 && S.tiv < 0.02) {
          S.bypCmd = 1;
          if (Math.abs(S.tivDp) < 5 && S.byp > 0.95) { S.tivCmd = 1; log('TIV', 'INLET VALVE OPENING'); }
        }
        if (S.stepT > 240) startFail('INLET VALVE');
        break;
      case 'BRAKES':
        S.req.brake = false;
        if (S.brake < 0.02) { toSeq('ACCEL'); S.govEn = true; S.esd = false; S.gl = 0; S.glTarget = GOV.start; }
        else if (S.stepT > 20) startFail('BRAKES NOT RELEASED');
        break;
      case 'ACCEL':
        S.govEn = true;
        if (n > 0.9 && S.glTarget === null && S.gl < GOV.glMax) S.glTarget = GOV.glMax;
        if (n > 0.92) S.req.lift = false;
        if (n > 0.95 && !S.govStart) { toSeq('EXCITE'); S.excOn = true; S.vRamp = 0; log('EXC', 'EXCITATION ON'); }
        else if (S.stepT > 150) startFail('SPEED NOT REACHED');
        break;
      case 'EXCITE':
        if (S.Vt > 0.95 && S.vRamp >= 1) toSeq(sw.syncMode === 'OFF' ? 'SNL' : 'SYNC');
        else if (S.stepT > 40) startFail('NO GENERATOR VOLTAGE');
        break;
      case 'SYNC':
        if (S.cb) { toSeq('ONLINE'); S.prefTarget = S.loadSP; break; }
        if (sw.syncMode === 'OFF') toSeq('SNL');
        break;
      case 'SNL':
        S.req.lift = false;
        if (!S.excOn && n > 0.95 && !anyLock()) { S.excOn = true; S.vRamp = 0; log('EXC', 'EXCITATION ON'); }
        if (S.cb) { toSeq('ONLINE'); S.prefTarget = S.loadSP; break; }
        if (sw.syncMode === 'AUTO' && S.grid && S.recl && S.gridOkT > 60 && !S.syncFailFlag && !anyLock()) toSeq('SYNC');
        break;
      case 'ONLINE':
        S.req.lift = false;
        if (!S.cb) { log('SEQ', 'BREAKER OPENED: SPEED NO LOAD'); toSeq('SNL'); S.gridOkT = 0; break; }
        S.lvlActive = wasLvl; levelControl(dt);
        break;
      case 'UNLOAD':
        S.prefTarget = 0;
        if (!S.cb) { S.excOn = false; S.govEn = false; toSeq('DECEL'); break; }
        if (S.Pkw < 8 || S.stepT > 120) cbTrip('NORMAL STOP');
        break;
      case 'DECEL':
        S.excOn = false; S.govEn = false; S.autoSync = false;
        if (n < 0.9) S.req.lift = true;
        if (n < 0.25) S.req.brake = true;
        if (n < 0.003) toSeq('STANDSTILL');
        break;
      case 'STANDSTILL':
        S.req.brake = true;
        if (S.stepT > 30) S.req.lift = false;
        if (S.stepT > 120) { S.req.cw = false; toSeq('STOPPED'); log('SEQ', 'UNIT STOPPED'); }
        break;
    }
    // cooling water lost while running -> normal stop after 5 min
    if (S.seq === 'ONLINE' || S.seq === 'SNL') {
      S.cwLossT = S.cwFlow < 25 ? S.cwLossT + dt : 0;
      if (S.cwLossT > 300) { normalStop('COOLING WATER LOST'); S.cwLossT = 0; }
      S.lowLvlT = S.hw < EL.lowLow ? S.lowLvlT + dt : 0;
      if (S.lowLvlT > 20) { normalStop('HEADWATER LOW-LOW'); S.lowLvlStop = true; S.lowLvlT = 0; }
      if (S.startFailFlag === false && S.shearPin && !S.shearStop) { S.shearStop = true; }
    }
  }
  function levelControl(dt) {
    S.lvlActive = sw.levelCtl !== 'OFF' && sw.govMode === 'AUTO';
    if (!S.lvlActive) { S.lvlTrim = 0; return; }
    const err = S.hw - S.levelSP;                       // m
    // inflow estimate x water-to-wire factor = feed-forward; PI on level trims it
    const kwPerQ = RHO * G * Math.max(S.hnet, 6) * 0.89 * 0.955 / 1000;
    const ff = (S.qinEst - S.qfish - S.ql) * kwPerQ;
    S.lvlTrim = clamp(S.lvlTrim + err * 2.0 * dt, -80, 80);
    const tgt = clamp(ff + err * 700 + S.lvlTrim, 100, 260);
    S.prefTarget = null;
    S.pref += clamp(tgt - S.pref, -dt * 2, dt * 1.5);
    S.loadSP = S.pref;
    if (S.pref <= 100.5 && err < -0.3) { S.lowLvlT2 = (S.lowLvlT2 || 0) + dt; if (S.lowLvlT2 > 120) { S.lowLvlT2 = 0; S.lowLvlStop = true; normalStop('LOW HEADWATER AT MINIMUM LOAD'); } }
    else S.lowLvlT2 = 0;
  }
  function spillControl(dt) {
    // PLC: pass the water the unit cannot take, trim on pond level
    const autoSpill = sw.levelCtl === 'TURB_SPILL';
    const err = S.hw - S.levelSP;
    const unitFull = S.seq !== 'ONLINE' || !S.lvlActive || S.pref >= 258 || S.y >= S.gl - 0.01;
    if (autoSpill) {
      const avail = Math.max(0, S.qinEst - S.q0 - S.qfish);
      if (unitFull) S.spillInt = clamp(S.spillInt + err * dt * 0.01, -3, 20);
      else S.spillInt = Math.max(-3, Math.min(S.spillInt, 0) + (0 - Math.min(S.spillInt, 0)) * dt / 60 - Math.max(0, -err) * 0);
      const demand = unitFull ? clamp(avail + S.spillInt + 5 * err, 0, 45) : clamp(5 * (err - 0.06), 0, 45);
      const h = Math.max(0.05, S.hw - EL.crest);
      const inv = q => clamp(q / (SPW.cd * SPW.b * Math.sqrt(2 * G * h)), 0, SPW.max);
      const g1 = inv(demand), q1 = gateQ(g1, h);
      S.sgTarget[0] = g1;
      S.sgTarget[1] = demand - q1 > 0.05 ? inv(demand - q1) : 0;
    }
    for (let i = 0; i < 2; i++) {
      let dir;
      if (sw.sgMode[i] === 'AUTO' && autoSpill) {
        const d = S.sgTarget[i] - S.sg[i];
        if (S.sgAuto[i] === 0 && Math.abs(d) > 0.03) S.sgAuto[i] = Math.sign(d);
        if (S.sgAuto[i] !== 0 && (Math.abs(d) < 0.005 || Math.sign(d) !== S.sgAuto[i])) S.sgAuto[i] = 0;
        dir = S.sgAuto[i]; S.sgCmd[i] = 0;
      } else { S.sgAuto[i] = 0; dir = S.sgCmd[i]; }
      if ((i === 0 && S.flt.sg1) || !S.acOK) dir = 0;
      S.sgRun[i] = dir;
      S.sg[i] = clamp(S.sg[i] + dir * SPW.rate * dt, 0, SPW.max);
      if ((dir > 0 && S.sg[i] >= SPW.max) || (dir < 0 && S.sg[i] <= 0)) { S.sgCmd[i] = 0; S.sgAuto[i] = 0; }
    }
  }
  function gateQ(a, h) {
    if (h <= 0 || a <= 0) return 0;
    const weir = SPW.cw * SPW.b * Math.pow(h, 1.5);
    const orif = SPW.cd * SPW.b * a * Math.sqrt(2 * G * Math.max(h - a / 2, 0.01));
    return Math.min(weir, orif);
  }

  /* ---------- auxiliaries: OPU, cooling water, lift, brakes, air, DC */
  function opu(dt) {
    const p = S.opuP;
    const leadOn = p < 285 ? true : p > 305 ? false : null, lagOn = p < 270 ? true : p > 305 ? false : null;
    if (sw.lead === 1) { if (leadOn !== null) S.p1Auto = leadOn; if (lagOn !== null) S.p2Auto = lagOn; }
    else { if (leadOn !== null) S.p2Auto = leadOn; if (lagOn !== null) S.p1Auto = lagOn; }
    const run = (sel, a) => sel === 'HAND' ? true : sel === 'OFF' ? false : a;
    S.p1Run = run(sw.p1, S.p1Auto) && S.acOK && !S.flt.opu1;
    S.p2Run = run(sw.p2, S.p2Auto) && S.acOK && !S.flt.opu2;
    const relief = p > 330 ? (p - 330) * 0.0002 : 0;
    const qin = ((S.p1Run ? 1 : 0) + (S.p2Run ? 1 : 0)) * OPU.pump * clamp((345 - p) / 40, 0, 1);
    const qout = OPU.leak + Math.abs(S.dy) * OPU.gateVol + Math.abs(S.tivRate || 0) * OPU.tivVol + (S.flt.oilLeak ? 0.0004 : 0) + relief;
    S.opuVo = clamp(S.opuVo + (qin - qout) * dt, 0.02, OPU.vt - 0.03);
    const leakExt = S.flt.oilLeak ? 0.0004 : 0;
    S.opuSump = clamp(S.opuSump + (qout - leakExt - qin) * dt / 1.2, 0, 1);
    if (S.flt.airLoss) S.opuKair *= Math.exp(-dt / 1800);
    else S.opuKair *= Math.exp(-dt / (86400 * 4));
    if (S.airAdd > 0) { S.airAdd -= dt; if (S.airP > 70) S.opuKair += dt * 1800; }
    const vAir = OPU.vt - S.opuVo;
    S.opuP = Math.max(0, (S.opuKair / vAir - 101325) / 6894.76);
    S.opuLvl = S.opuVo / OPU.vt;
  }
  function aux(dt) {
    const hoa = (sel, r) => sel === 'HAND' ? true : sel === 'OFF' ? false : r;
    S.acOK = S.vbus > 0.80 || (S.cb && S.Vt > 0.80);
    S.vSS = (S.cb ? S.Vt : S.vbus) * 480;
    // cooling water: booster pump on a tapping upstream of the inlet valve
    S.cwRun = hoa(sw.cw, S.req.cw) && S.acOK && !S.flt.cwPump;
    if (S.flt.strainer) S.strFoul = Math.min(1, S.strFoul + dt / 900);
    if (S.cwRun) S.strFoul = Math.min(1, S.strFoul + dt * 2e-6 * S.debris);
    if (S.backwash > 0) { S.backwash -= dt; S.strFoul = Math.max(0.05, S.strFoul - dt / 20); }
    else if (S.strDp > 6 && S.cwRun) { S.backwash = 45; log('AUX', 'STRAINER AUTO BACKWASH'); }
    const supply = clamp((S.pPen + 5) / 10, 0, 1);
    const tgt = S.cwRun ? 62 * supply / Math.sqrt(1 + 3 * S.strFoul * S.strFoul) : 0;
    S.cwFlow += (tgt - S.cwFlow) * dt / (S.cwRun ? 3 : 1.5);
    S.strDp = 1.0 * (S.cwFlow / 62) ** 2 * (1 + 9 * S.strFoul * S.strFoul);
    // HP oil lift (thrust bearing)
    S.liftRun = hoa(sw.lift, S.req.lift) && S.acOK && !S.flt.liftPump;
    S.liftP += ((S.liftRun ? 2350 - 600 * S.w : 0) - S.liftP) * dt / (S.liftRun ? 1.2 : 0.6);
    // brakes (station air)
    const apply = sw.brake === 'APPLY' ? true : sw.brake === 'RELEASE' ? false : S.req.brake;
    S.brake = clamp(S.brake + (apply && S.airP > 30 ? 1 : -1) * dt / 1.5, 0, 1);
    const brakeMoving = S.brake !== S.brakePrev && S.brake > S.brakePrev; S.brakePrev = S.brake;
    // station air compressor
    const airUse = (brakeMoving ? 6 : 0) + 0.02 + (S.airAdd > 0 ? 0.8 : 0);
    if (S.airP < 90) S.compRun = S.acOK; else if (S.airP > 110) S.compRun = false;
    if (!S.acOK) S.compRun = false;
    S.airP = clamp(S.airP + ((S.compRun ? 1.6 : 0) - airUse) * dt * 0.5, 0, 125);
    // draft tube air admission
    const rz = S.w > 0.9 && S.y > 0.28 && S.y < 0.64;
    const dtOpen = sw.dtAir === 'OPEN' ? true : sw.dtAir === 'CLOSE' ? false : rz;
    S.dtAir = clamp(S.dtAir + (dtOpen ? 1 : -1) * dt / 4, 0, 1);
    // generator space heaters
    S.heater = sw.heater === 'ON' ? true : sw.heater === 'OFF' ? false : (!S.cb && S.w < 0.1);
    S.heater = S.heater && S.acOK;
    // powerhouse sump
    const sumpIn = 0.0005 + (S.w > 0.1 ? 0.0004 : 0) + 0.0003 * S.y;
    const lead = S.sump > 0.55 ? true : S.sump < 0.15 ? false : S.sumpRun[0];
    const lag = S.sump > 0.72 ? true : S.sump < 0.15 ? false : S.sumpRun[1];
    S.sumpRun[0] = (sw.sump === 'HAND' || (sw.sump === 'AUTO' && lead)) && S.acOK;
    S.sumpRun[1] = sw.sump === 'AUTO' && lag && S.acOK;
    S.sump = clamp(S.sump + (sumpIn - ((S.sumpRun[0] ? 1 : 0) + (S.sumpRun[1] ? 1 : 0)) * 0.006) * dt / 4, 0, 1);
    // headgate hoist
    if (S.hgEmerg) { S.hg = Math.max(0, S.hg - dt / 60); S.hgCmd = 0; if (S.hg <= 0) S.hgEmerg = false; }
    else if (S.hgCmd && S.acOK) {
      S.hg = clamp(S.hg + S.hgCmd * dt / 360, 0, 1);
      if ((S.hgCmd > 0 && S.hg >= 1) || (S.hgCmd < 0 && S.hg <= 0)) { log('INT', S.hgCmd > 0 ? 'HEADGATE FULLY OPEN' : 'HEADGATE CLOSED'); S.hgCmd = 0; }
    }
    // turbine inlet valve (oil to open, counterweight to close) and bypass
    const was = S.tiv;
    if (S.tivCmd > 0) {
      if (S.y > 0.02 || Math.abs(S.tivDp) > 5) { if (S.tiv < 0.02) { S.tivCmd = 0; S.tivBlock = true; log('TIV', 'OPEN BLOCKED: DIFFERENTIAL OR GATES', 'alarm'); } }
      if (S.tivCmd > 0 && S.opuP > 200) S.tiv = Math.min(1, S.tiv + dt / 60);
      if (S.tiv >= 1) { S.tivCmd = 0; log('TIV', 'INLET VALVE OPEN'); }
    } else if (S.tivCmd < 0) {
      S.tiv = Math.max(0, S.tiv - dt / (S.tiv < 0.1 ? 90 : 40));
      if (S.tiv <= 0) { S.tivCmd = 0; log('TIV', 'INLET VALVE CLOSED'); }
    }
    S.tivRate = (S.tiv - was) / dt;
    if (S.bypCmd) {
      S.byp = clamp(S.byp + S.bypCmd * dt / 15, 0, 1);
      if ((S.bypCmd > 0 && S.byp >= 1) || (S.bypCmd < 0 && S.byp <= 0)) S.bypCmd = 0;
    }
    // trash rake
    if (S.rakeRun) { S.rakeT += dt; S.rackFoul = Math.max(0.02, S.rackFoul - dt * 0.002); if (S.rakeT > 240 || !S.acOK) { S.rakeRun = false; log('AUX', 'TRASH RAKE STOPPED'); } }
    // station service load (kW)
    S.ssKW = 3.5 + (S.p1Run ? 7.5 : 0) + (S.p2Run ? 7.5 : 0) + (S.cwRun ? 3.7 : 0) + (S.liftRun ? 5.6 : 0) + (S.compRun ? 4 : 0)
      + (S.sumpRun[0] ? 2.2 : 0) + (S.sumpRun[1] ? 2.2 : 0) + (S.sgRun[0] ? 3 : 0) + (S.sgRun[1] ? 3 : 0) + (S.hgCmd ? 4 : 0)
      + (S.heater ? 3 : 0) + (S.rakeRun ? 3 : 0) + S.chgA * 0.14;
    if (!S.acOK) S.ssKW = 0.3;
    S.iSS = S.acOK ? S.ssKW * 1000 / (1.732 * Math.max(S.vSS, 1) * 0.82) : 0;
  }
  function dcSystem(dt) {
    S.dcSpring = Math.max(0, S.dcSpring - dt);
    S.dcLoad = 5.5 + (S.dcSpring > 0 ? 8 : 0) + (!S.acOK ? 12 : 0) + (S.excOn ? 0.4 : 0);
    const charger = S.acOK && !S.flt.charger;
    if (charger) {
      S.dcSoc = Math.min(1, S.dcSoc + dt * 25 / (200 * 3600));
      S.chgA = S.dcLoad + (S.dcSoc < 0.995 ? 18 * (1 - S.dcSoc) * 20 + 2 : 0.4);
      S.chgA = Math.min(S.chgA, 30);
      S.dcV += ((S.dcSoc < 0.995 ? 135.5 : 132.4) - S.dcV) * dt / 5;
    } else {
      S.dcSoc = Math.max(0, S.dcSoc - dt * S.dcLoad / (200 * 3600));
      S.chgA = 0;
      S.dcV += ((60 * (1.98 + 0.14 * S.dcSoc) - 0.05 * S.dcLoad) - S.dcV) * dt / 4;
    }
  }

  /* ---------- hydrology */
  function hydrology(dt) {
    if (Math.random() < dt / 900) S.qinTarget = clamp(S.qinTarget + rnd(0.5), 1.2, 6);
    S.qinBase += (S.qinTarget - S.qinBase) * dt / 1500;
    if (S.floodT >= 0) {
      S.floodT += dt;
      const tr = 1200, td = 3000;
      S.floodQ = S.floodT < tr ? S.floodPeak * (S.floodT / tr) ** 2 : S.floodPeak * Math.exp(-(S.floodT - tr) / td);
      S.debris = 1 + 4 * S.floodQ / Math.max(1, S.floodPeak);
      if (S.floodT > tr + 6 * td) { S.floodT = -1; S.floodQ = 0; S.debris = 1; }
    }
    S.qin = Math.max(0.3, S.qinBase + S.floodQ + 0.06 * Math.sin(S.t / 91) + 0.03 * Math.sin(S.t / 23));
    const h = S.hw - EL.crest;
    S.qspill = gateQ(S.sg[0], h) + gateQ(S.sg[1], h);
    S.qover = S.hw > EL.gateTop ? 2 * 1.7 * SPW.b * Math.pow(S.hw - EL.gateTop, 1.5) : 0;
    S.qfish = S.hw > EL.crest ? 0.15 * clamp((S.hw - EL.crest) / 0.3, 0, 1) : 0;
    const out = S.q0 + S.qspill + S.qover + S.qfish;
    S.hw += (S.qin - out) * dt / POND_A;
    const qd = S.qt + S.qspill + S.qover + S.qfish;
    const twT = EL.tw0 + 0.40 * Math.pow(Math.max(qd, 0.05), 0.6);
    S.tw += (twT - S.tw) * dt / 60;
    S.rackFoul = Math.min(0.8, S.rackFoul + dt * (S.q0 / NP.Q) * S.debris * 4e-6);
  }

  /* ---------- thermal models (bearings, stator, air) */
  function thermal(dt) {
    const cf = clamp(S.cwFlow / 62, 0, 1);
    const n = S.w;
    const pTB = S.mu * S.thrust * 0.36 * S.wm;                  // W
    const pUGB = 60 * n * n * WM * 0.5 + 300 * n * n;
    const pLGB = 45 * n * n * WM * 0.5 + 220 * n * n + 40 * S.vib * n;
    const pTGB = 60 * n * n * WM * 0.5 + 260 * n * n + 60 * S.vib * n;
    S.tCwOut = S.tCw + (S.cwFlow > 1 ? (pTB + pUGB + pLGB + pTGB + S.pGenLoss * 0.9) / (S.cwFlow * 0.063 * 4186) : 0);
    // thrust / upper guide oil pot
    S.tOilT += ((pTB + pUGB) - 130 * cf * (S.tOilT - S.tCw) - 22 * (S.tOilT - S.tAmb)) * dt / 420e3;
    const pMix = S.mix * S.thrust * 0.36 * S.wm;                 // W dissipated in boundary contact
    S.tPadHot += (pMix / 2500 - S.tPadHot / 30) * (1 - Math.exp(-dt / 1)) * 1;
    if (S.tPadHot < 0) S.tPadHot = 0;
    const padT = S.tOilT + 11 * Math.pow(Math.max(pTB, 0) / 3200, 0.75) + S.tPadHot;
    S.tPadT += (padT - S.tPadT) * dt / 45;
    S.tUGB += ((S.tOilT + 6 * n * n) - S.tUGB) * dt / 60;
    if (S.tPadT > 125 && !S.wiped) { S.wiped = true; S.flt.thrustBrg = true; log('BRG', 'THRUST PADS WIPED', 'trip'); }
    // lower guide (own pot), turbine guide (own pot)
    S.tLGB += (pLGB - 16 * cf * (S.tLGB - S.tCw) - 4 * (S.tLGB - S.tAmb)) * dt / 90e3;
    S.tOilG += (pTGB - 20 * cf * (S.tOilG - S.tCw) - 5 * (S.tOilG - S.tAmb)) * dt / 110e3;
    S.tTGB += ((S.tOilG + 7 * n * n + 0.25 * S.vib) - S.tTGB) * dt / 50;
    // generator: copper + core losses into a closed air circuit with air/water coolers
    const pCu = 3600 * S.I * S.I, pCore = S.Vt > 0.05 ? 2400 * (S.Vt) ** 2 * Math.pow(Math.max(n, 0.05), 0.4) : 0;
    const pWind = 1470 * n * n * n, pFld = 1600 * (S.ifd / GEN.ifdR) ** 2;
    S.pGenLoss = pCu + pCore + pWind + pFld + (S.heater ? 3000 : 0);
    S.tAirC += (S.pGenLoss - 600 * cf * (S.tAirH - S.tCw) - 90 * (S.tAirC - S.tAmb)) * dt / 260e3;
    S.tAirH = S.tAirC + S.pGenLoss / (1800 * Math.max(0.15, n));
    S.tSt += ((pCu + 0.5 * pCore + (S.heater ? 2500 : 0)) - 90 * (S.tSt - S.tAirC)) * dt / 160e3;
    // vibration at the turbine guide bearing (mils p-p)
    const unb = (S.flt.unbalance ? (S.unbG = Math.min(1, (S.unbG || 0) + dt / 1200)) : (S.unbG || 0));
    const vt = 0.35 + 1.15 * n * n + 4.2 * S.rope * (1 - 0.55 * S.dtAir) + 3.0 * (S.roughH > 0 ? (1 - sstep(0.3, 0.45, S.qb)) : 0)
      + 6.5 * unb * n * n + (S.shearPin ? 2.4 * n : 0) + S.shaftDmg * 5 * n + (S.wiped ? 1.5 * n : 0) + Math.max(0, n - 1.15) * 9;
    S.vib += (vt * (n > 0.01 ? 1 : 0.05) - S.vib) * (1 - Math.exp(-dt / 2));
  }

  /* ---------- registers */
  function registers(dt) {
    if (S.Pkw > 0 && S.cb) S.kwh += S.Pkw * dt / 3600;
    if (S.cb) S.kvarh += Math.abs(S.Qkvar) * dt / 3600;
    if (S.w > 0.5) S.hours += dt / 3600;
    if (S.grid && S.recl && S.vbus > 0.9) S.gridOkT += dt; else S.gridOkT = 0;
  }

  /* ---------- utility network events */
  function utility(dt) {
    if (!S.recl) {
      S.reclT -= dt;
      if (S.reclT <= 0) {
        if (S.outageSust && S.outage > 0) { S.reclT = 1e9; }
        else {
          S.recl = true; S.grid = true; S.gridTh = rnd(Math.PI);
          const live = S.cb && S.Vt > 0.3;
          log('NET', live ? 'UTILITY RECLOSED ONTO LIVE ISLAND' : 'UTILITY RECLOSER CLOSED', 'alarm');
        }
      }
    }
    if (S.outage > 0) {
      S.outage -= dt;
      if (S.outage <= 0) { S.outage = 0; if (!S.recl) { S.reclT = 0.5; S.outageSust = false; } }
    }
  }

  /* =====================================================================
     ANNUNCIATOR (ISA-18.1 ringback sequence, 40 windows)
     ===================================================================== */
  const ANN = [
    ['GEN BREAKER\n52G TRIP', () => S.cbTripFlag], ['86G LOCKOUT\nELECTRICAL', () => S.lock86G], ['86M LOCKOUT\nMECHANICAL', () => S.lock86M], ['EMERGENCY\nSTOP', () => S.estop],
    ['OVERSPEED\n12', () => S.trips['12E'] || S.trips['12M']], ['START\nFAILURE', () => S.startFailFlag], ['SYNC\nFAILURE', () => S.syncFailFlag], ['GOVERNOR\nTROUBLE', () => S.govFault || S.trackT > 3 || S.flt.ringJam && S.trackT > 1],
    ['GEN PROT\nTRIP', () => Object.keys(S.targets).length > 0], ['OVER/UNDER\nVOLTAGE 27/59', () => S.targets['27'] || S.targets['59'] || (S.cb && (S.Vt > 1.06 || S.Vt < 0.92))],
    ['OVER/UNDER\nFREQ 81', () => S.targets['81O'] || S.targets['81U']], ['REVERSE\nPOWER 32', () => S.targets['32'] || (S.cb && S.Pkw < -5)],
    ['LOSS OF\nFIELD 40', () => S.targets['40']], ['STATOR\nGROUND 64G', () => S.targets['64G'] || (S.flt.ground64 && S.Vt > 0.2)], ['OVERCURRENT\n50/51V', () => S.targets['50'] || S.targets['51V'] || S.I > 1.12],
    ['UTILITY\nLINE DEAD', () => !(S.grid && S.recl)],
    ['AVR LIMITER\nACTIVE', () => S.oel || S.uel || S.vhz], ['EXCITATION\nFAULT', () => S.flt.diode && S.excOn || S.flt.avr || (S.excOn && S.w > 0.95 && S.Vt < 0.3 && S.vRamp >= 1)],
    ['THRUST BRG\nTEMP HIGH', () => S.tPadT > 80], ['GUIDE BRG\nTEMP HIGH', () => S.tUGB > 75 || S.tLGB > 75 || S.tTGB > 75], ['STATOR\nTEMP HIGH', () => S.tSt > 120],
    ['VIBRATION\nHIGH', () => S.vib > 7], ['DRAFT TUBE\nPULSATION', () => S.rope > 0.55 && S.dtAir < 0.5], ['WICKET GATE\nSHEAR PIN', () => S.shearPin],
    ['GOV OIL\nPRESS LOW', () => S.opuP < 250], ['GOV OIL\nLEVEL ABNORMAL', () => S.opuLvl > 0.70 || S.opuLvl < 0.25 || S.opuSump < 0.35], ['GOV OIL PUMP\nFAILURE', () => (sw.p1 === 'AUTO' && S.p1Auto && !S.p1Run) || (sw.p2 === 'AUTO' && S.p2Auto && !S.p2Run)],
    ['COOLING WATER\nFLOW LOW', () => S.cwFlowLow], ['STRAINER\nDIFF PRESS', () => S.strDp > 5], ['HP LIFT\nPRESS LOW', () => S.req.lift && S.w > 0.003 && S.liftP < 1500 && S.liftT > 5],
    ['BRAKES ON\nWITH ROTATION', () => S.brake > 0.3 && S.w > 0.3], ['UNIT CREEP', () => S.creep],
    ['HEADWATER\nHIGH', () => S.hw > EL.high], ['HEADWATER\nLOW', () => S.hw < EL.low || S.lowLvlStop], ['SPILLWAY\nGATE FAULT', () => S.flt.sg1 && (S.sgCmd[0] !== 0 || (sw.sgMode[0] === 'AUTO' && Math.abs(S.sgTarget[0] - S.sg[0]) > 0.05))],
    ['TRASH RACK\nDIFF HIGH', () => S.rackDh > 0.25], ['STATION SERV\nAC FAIL', () => !S.acOK], ['DC SYSTEM\nTROUBLE', () => S.flt.dcGround || S.dcV < 120 || !S.chargerOK],
    ['SUMP LEVEL\nHIGH', () => S.sump > 0.85], ['INLET VALVE\nNOT OPEN', () => (S.govEn || S.w > 0.3) && S.tiv < 0.99 && S.seq !== 'TIV'],
  ].map(([label, test], i) => ({ i, label, test, st: 'off', prev: false }));
  let horn = false;
  function annunciator(dt) {
    for (const a of ANN) {
      const on = !!a.test();
      if (on && !a.prev) {
        if (a.st === 'off' || a.st === 'ring') { a.st = 'alarm'; horn = true; }
        if (a.st === 'ackRTN') a.st = 'alarm';
      }
      if (!on && a.prev) { if (a.st === 'ack') a.st = 'ring'; else if (a.st === 'alarm') a.st = 'alarmRTN'; }
      a.prev = on;
    }
  }
  function annButton(b) {
    if (b === 'silence') horn = false;
    if (b === 'ack') { horn = false; ANN.forEach(a => { if (a.st === 'alarm') a.st = 'ack'; else if (a.st === 'alarmRTN') a.st = 'ring'; }); }
    if (b === 'reset') ANN.forEach(a => { if (a.st === 'ring') a.st = 'off'; });
  }

  /* =====================================================================
     STEP LOOPS
     ===================================================================== */
  let medAcc = 0, slowAcc = 0;
  function fast(dt) {
    S.t += dt; S.tod = (S.tod + dt) % 86400;
    gridFast(dt);
    governor(dt);
    waterway(dt);
    electrical(dt);
    shaft(dt);
    breaker(dt);
    medAcc += dt;
    if (medAcc >= 0.05 - 1e-9) { medium(medAcc); medAcc = 0; }
    slowAcc += dt;
    if (slowAcc >= 0.25 - 1e-9) { slow(slowAcc); slowAcc = 0; }
  }
  function medium(dt) {
    utility(dt);
    syncCalc(dt);
    protection(dt);
    sequence(dt);
    spillControl(dt);
    opu(dt);
    aux(dt);
    dcSystem(dt);
    // PLC inflow estimate from pond level rate + known outflows
    const dh = (S.hw - S.hwPrev) / dt; S.hwPrev = S.hw;
    S.qinEst += ((dh * POND_A + S.q0 + S.qspill + S.qfish + S.qover) - S.qinEst) * dt / 180;
    // creep detection (stopped unit turning)
    const stopped = S.seq === 'STOPPED' || (sw.unitMode === 'MAN' && !S.govEn);
    S.creepT = stopped && S.w > 0.002 && S.w < 0.1 ? S.creepT + dt : 0;
    if (S.creepT > 10 && !S.creep) { S.creep = true; log('UNIT', 'CREEP DETECTED: BRAKES APPLIED', 'alarm'); S.req.brake = true; }
    if (S.creep && S.w < 0.0005 && S.creepT === 0) S.creep = false;
    const cwReq = S.cwRun || S.req.cw;
    S.cwT = cwReq && S.cwFlow < 35 ? S.cwT + dt : 0;
    S.cwFlowLow = S.cwT > 8;
    S.liftT = S.req.lift ? S.liftT + dt : 0;
    S.chargerOK = !S.flt.charger && S.acOK;
    // governor supervision: speed-probe discrepancy and gate tracking
    const disc = Math.abs(S.nMeas - S.w) > 0.05 && S.w > 0.2;
    S.govFaultT = disc ? S.govFaultT + dt : 0;
    if (S.govFaultT > 0.5 && !S.govFault && S.govEn) { S.govFault = true; log('GOV', 'SPEED PROBE DISCREPANCY: GATE HOLD', 'alarm'); }
    const track = S.govEn && Math.abs(S.yref - S.y) > 0.05 && S.opuP > 250;
    S.trackT = track ? S.trackT + dt : 0;
    if (!quiet) annunciator(dt);
    if (S.cb && !S.wasCb) S.cbTripFlag = false;
    S.wasCb = S.cb;
  }
  function slow(dt) {
    hydrology(dt);
    thermal(dt);
    registers(dt);
  }

  let budgetHit = false;
  function advance(dtReal) {
    const sim = Math.min(dtReal, 0.25) * timeScale;
    let steps = Math.round(sim / DT + (advance.frac || 0));
    advance.frac = sim / DT + (advance.frac || 0) - steps;
    const t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());
    let i = 0;
    for (; i < steps; i++) {
      fast(DT);
      if ((i & 63) === 63 && (typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0 > 24) { budgetHit = true; break; }
    }
    return i * DT;
  }
  function run(seconds) { const n = Math.round(seconds / DT); for (let i = 0; i < n; i++) fast(DT); }

  /* =====================================================================
     INITIAL CONDITIONS
     ===================================================================== */
  function settlePenstock(q) {
    const K = (1.5 + 0.046) * PEN.kv + (0.03 + S.rackFoul) / (NP.Q * NP.Q);
    const h0 = S.hw - K * q * q;
    for (let i = 0; i <= PEN.N; i++) { pen.H[i] = h0 - i * PEN.R * q * q; pen.Q[i] = q; }
  }
  function thermalSoak(seconds) { const n = Math.round(seconds / 5); for (let i = 0; i < n; i++) thermal(5); }
  function scenario(name) {
    quiet = true;
    fresh();
    S.tAmb = 22;
    if (name === 'cold') {
      S.tiv = 0; S.hsc = S.tw; S.byp = 0; S.brake = 1;
      S.tOilT = S.tPadT = S.tUGB = 19; S.tLGB = 18; S.tOilG = S.tTGB = 17; S.tSt = 18; S.tAirC = S.tAirH = 19;
      S.opuP = 300; settlePenstock(0); run(2);
    } else if (name === 'ready') {
      S.tiv = 1; S.brake = 1; settlePenstock(0);
      S.tOilT = 26; S.tPadT = 27; S.tUGB = 26; S.tLGB = 25; S.tOilG = 24; S.tTGB = 24; S.tSt = 27; S.tAirC = 24; S.tAirH = 24;
      run(5);
    } else {   // online
      const pkw = 232;
      S.tiv = 1; S.brake = 0; S.cb = true; S.excOn = true; S.vRamp = 1; S.govEn = true; S.govStart = false;
      S.seq = 'ONLINE'; S.seqMsg = SEQTXT.ONLINE; S.req = { cw: true, lift: false, brake: false };
      S.wm = WM; S.w = 1; S.nMeas = S.nPrev = 1; S.gl = GOV.glMax; S.pref = pkw; S.loadSP = pkw; S.lvlInt = pkw;
      // generator initial state from P, Q at V = 1
      const P = (pkw) / NP.S, Q = 0.16;
      const Iv = C(P, -Q), Vv = ONE;
      const EQ = cadd(Vv, cmul(C(GEN.ra, GEN.xq), Iv));
      const dl = Math.atan2(EQ.i, EQ.r);
      S.delta = dl;
      const sn = Math.sin(dl), cs = Math.cos(dl);
      const Id = Iv.r * sn - Iv.i * cs, Iq = Iv.r * cs + Iv.i * sn;
      const Vd = Vv.r * sn - Vv.i * cs, Vq = Vv.r * cs + Vv.i * sn;
      S.psd2 = (GEN.xq - GEN.xpp) * Iq;
      S.psq2 = Vq + GEN.ra * Iq + GEN.xpp * Id;
      S.psq1 = S.psq2 + (GEN.xdp - GEN.xpp) * Id;
      const psi = Math.hypot(S.psq2, S.psd2), sat = psi > GEN.satA ? GEN.satB * (psi - GEN.satA) ** 2 : 0;
      S.efd = S.psq1 + (GEN.xd - GEN.xdp) * Id + sat * S.psq2 / psi - GEN.res;
      S.ifd = S.efd + GEN.res;
      S.ve = S.efd / 0.9; S.vr = S.ve * 1.01 + EXC.kd * S.ifd; S.avrInt = S.vr; S.vtm = 1; S.vref = 1.0 + 0.04 * Q;
      void Vd;
      // gate for that output at about rated head
      let lo = 0.1, hi = 1;
      for (let k = 0; k < 40; k++) { const mid = (lo + hi) / 2; const q = steadyQ(mid, WM, 12.15); const p = runnerTorque(q, WM, tcoef(mid).cota) * WM; if (p > (pkw + 11) * 1000) hi = mid; else lo = mid; }
      S.y = (lo + hi) / 2; S.govInt = S.y; S.yref = S.y;
      settlePenstock(steadyQ(S.y, WM, 12.15) * 1.016);
      S.cwRun = true; S.cwFlow = 60; S.liftP = 0;
      S.tAirC = 24; S.tSt = 62; S.tOilT = 40; S.tPadT = 54; S.tUGB = 44; S.tLGB = 40; S.tOilG = 40; S.tTGB = 46;
      S.qinBase = S.qinTarget = S.qin = S.qinEst = 2.55;
      sw.avrMode = 'PF'; S.pfref = 0.97;
      run(1); thermalSoak(3 * 3600); run(60);
      S.levelSP = S.hw;
    }
    S.wasCb = S.cb;
    quiet = false;
    S.relayT = {}; S.trips = {}; S.targets = {}; S.cbTripFlag = false; S.startFailFlag = false; S.syncFailFlag = false;
    ANN.forEach(a => { a.prev = !!a.test(); a.st = a.prev ? 'ack' : 'off'; });
    horn = false;
    log('SIM', `INITIAL CONDITION: ${name.toUpperCase()}`);
  }

  /* =====================================================================
     OPERATOR INTERFACE
     ===================================================================== */
  function cmd(c, arg) {
    switch (c) {
      case 'start': startUnit(); break;
      case 'stop':
        if (sw.unitMode !== 'AUTO') { S.govEn = false; log('GOV', 'GOVERNOR SHUTDOWN (MANUAL)'); }
        else normalStop('OPERATOR'); break;
      case 'estop': S.estop = !S.estop; if (!S.estop) { S.trips.ES = false; log('UNIT', 'EMERGENCY STOP RELEASED'); } break;
      case 'reset86':
        if (arg === '86G') {
          if (!S.lock86G) break;
          if (S.flt.stator87 || S.flt.ground64) { log('86G', '86G RESET BLOCKED: FAULT PRESENT'); break; }
          S.lock86G = false; log('86G', '86G RESET');
        } else {
          if (!S.lock86M) break;
          if (S.estop || S.w > 0.02) { log('86M', '86M RESET BLOCKED' + (S.estop ? ': E-STOP IN' : ': UNIT TURNING')); break; }
          S.lock86M = false; S.esd = false; log('86M', '86M RESET');
        }
        if (!anyLock()) { S.trips = {}; S.startFailFlag = false; S.syncFailFlag = false; S.cbTripFlag = false; }
        break;
      case 'gprReset': S.targets = {}; S.slips = 0; log('PROT', 'RELAY TARGETS RESET'); break;
      case 'cbClose': cbClose('MANUAL'); break;
      case 'cbTrip': cbTrip('CONTROL SWITCH', false); break;
      case 'excOn':
        if (anyLock()) { log('EXC', 'EXCITATION BLOCKED: LOCKOUT'); break; }
        if (S.w < 0.9) { log('EXC', 'EXCITATION BLOCKED: SPEED < 90 %'); break; }
        if (!S.excOn) { S.excOn = true; S.vRamp = 0; log('EXC', 'EXCITATION ON'); } break;
      case 'excOff': if (S.cb) { log('EXC', 'EXCITATION OFF BLOCKED: 52G CLOSED'); break; } if (S.excOn) { S.excOn = false; log('EXC', 'EXCITATION OFF'); } break;
      case 'tivOpen':
        if (S.tiv >= 1) break;
        if (Math.abs(S.tivDp) > 5 && S.tiv < 0.02) { S.tivBlock = true; log('TIV', 'OPEN BLOCKED: EQUALIZE FIRST', 'alarm'); break; }
        if (S.y > 0.02) { log('TIV', 'OPEN BLOCKED: GATES NOT CLOSED'); break; }
        S.tivBlock = false; S.tivCmd = 1; log('TIV', 'INLET VALVE OPENING'); break;
      case 'tivClose': if (S.tiv > 0) { S.tivCmd = -1; log('TIV', 'INLET VALVE CLOSING'); } break;
      case 'bypOpen': S.bypCmd = 1; break;
      case 'bypClose': S.bypCmd = -1; break;
      case 'hg': if (!S.hgEmerg) S.hgCmd = arg; if (arg) log('INT', arg > 0 ? 'HEADGATE RAISING' : 'HEADGATE LOWERING'); break;
      case 'sg': { const [i, d] = arg; if (sw.sgMode[i] === 'AUTO') { log('SPW', `GATE ${i + 1} IN AUTO: PUSHBUTTON IGNORED`); break; } S.sgCmd[i] = d; break; }
      case 'airAdd': S.airAdd = 30; log('OPU', 'AIR ADMISSION TO PRESSURE TANK'); break;
      case 'backwash': S.backwash = 45; log('AUX', 'STRAINER BACKWASH'); break;
      case 'rake': if (S.acOK) { S.rakeRun = true; S.rakeT = 0; log('AUX', 'TRASH RAKE RUNNING'); } break;
      case 'ann': annButton(arg); break;
    }
  }
  function set(k, v, i) {
    if (k === 'sgMode') { sw.sgMode[i] = v; S.sgCmd[i] = 0; log('SPW', `GATE ${i + 1} ${v}`); return; }
    const old = sw[k]; sw[k] = v;
    if (old === v) return;
    if (k === 'unitMode') log('UNIT', `UNIT CONTROL ${v === 'AUTO' ? 'AUTOMATIC' : 'MANUAL'}`);
    if (k === 'govMode') { log('GOV', `GOVERNOR ${v}`); if (v === 'MAN' && S.gl > S.y + 0.02 && S.govEn) S.gl = S.y; }
    if (k === 'avrMode') { log('AVR', `AVR MODE ${v}`); if (v === 'PF') S.pfref = S.Pe > 0.05 ? clamp(S.pf * (S.Qe >= 0 ? 1 : -1) < 0 ? 2 - S.pf : S.pf, 0.8, 1.2) : 0.95; if (v === 'VAR') S.qref = S.Qe; }
    if (k === 'syncMode') { log('SYNC', `SYNC MODE ${v}`); S.syncFailFlag = false; S.syncT = 0; }
    if (k === 'levelCtl') log('PLC', `LEVEL CONTROL ${v.replace('_', ' + ')}`);
  }
  function hold_(k, dir) { hold[k] = dir; }

  /* ---------- instructor */
  const instructor = {
    setInflow(q) { S.qinTarget = S.qinBase = clamp(q, 0.3, 40); },
    flood(peak) { S.floodPeak = peak; S.floodT = 0; log('SIM', `RIVER RISING (FLOOD PEAK ${(peak * 35.31).toFixed(0)} CFS)`); },
    gridOutage(sustained) {
      S.recl = false; S.outage = sustained ? 600 : 0; S.outageSust = sustained; S.reclT = sustained ? 1e9 : 2.0;
      log('NET', 'UTILITY RECLOSER OPENED', 'alarm');
    },
    sag() { S.sag = 0.4; log('NET', 'VOLTAGE SAG ON 12.47 kV'); },
    freqDip() { S.gridFT = 0.9925; S.fEvent = 15; log('NET', 'SYSTEM FREQUENCY EXCURSION'); },
    debris() { S.rackFoul = Math.min(0.8, S.rackFoul + 0.3); S.debris = 3; log('SIM', 'DEBRIS ON TRASH RACK'); },
    fault(id, on) {
      S.flt[id] = on;
      if (id === 'gateJam' && !on) { S.yJam = null; S.shearPin = false; }
      if (id === 'unbalance' && !on) S.unbG = 0;
      if (id === 'thrustBrg' && !on) S.wiped = false;
    },
  };

  scenario('online');

  return {
    S, sw, NP, EL, FT, M2PSI, M2INHG, ANN, FAULTS, events, instructor, pen, PEN, TB, GEN,
    advance, run, scenario, cmd, set, hold: hold_, permissives,
    get horn() { return horn; },
    get timeScale() { return timeScale; }, set timeScale(v) { timeScale = v; },
    get budgetHit() { const b = budgetHit; budgetHit = false; return b; },
    STEPNO, SEQTXT,
  };
})();
root.PLANT = PLANT;
if (typeof module !== 'undefined' && module.exports) module.exports = PLANT;
})(typeof window !== 'undefined' ? window : globalThis);
