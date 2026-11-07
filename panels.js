'use strict';
/* =====================================================================
   PANELS · the three cabinet fronts
   Layout in millimetres on each door (origin top-left, x right, y down,
   item x/y = centre). Every device binds to the plant model. Static art
   (nameplates, meter dials, escutcheons) is painted into atlases here;
   the 3D room turns the layout into hardware.
   ===================================================================== */
window.PANELS = (() => {
  const P = window.PLANT, S = P.S, sw = P.sw, FT = P.FT;
  const DOOR = { w: 1140, h: 1900 };
  const FONT = '"Barlow Semi Condensed", "Arial Narrow", "Helvetica Neue", Arial, sans-serif';
  const DIAL = '"Barlow", "Helvetica Neue", Arial, sans-serif';
  const MARK = '"Permanent Marker", "Comic Sans MS", cursive';

  const f1 = x => x.toFixed(1), f0 = x => x.toFixed(0), f2 = x => x.toFixed(2);
  const ft = m => m / FT;
  const blink = (hz = 1.6) => (performance.now() / 1000 * hz) % 1 < 0.5;
  const onOff = b => (b ? 'ON' : 'OFF');

  /* ------------------------------------------------------------ layout */
  // lamp(x,y,color,label,on) on() may return true/false or 'flash'
  const L = (x, y, color, label, on, extra = {}) => ({ t: 'lamp', x, y, color, label, on, ...extra });
  const PB = (x, y, color, label, press, extra = {}) => ({ t: 'pb', x, y, color, label, press, ...extra });
  const SEL = (x, y, label, pos, get, set, extra = {}) => ({ t: 'sel', x, y, label, pos, get, set, ...extra });
  const RL = (x, y, label, hold, extra = {}) => ({ t: 'rl', x, y, label, hold, left: 'LOWER', right: 'RAISE', ...extra });
  const M = (x, y, label, scale, get, extra = {}) => ({ t: 'meter', x, y, s: 110, label, scale, get, ...extra });
  const E = (x, y, label, scale, get, extra = {}) => ({ t: 'edge', x, y, w: 40, h: 170, label, scale, get, ...extra });
  const SEC = (x, y, w, h, label) => ({ t: 'section', x, y, w, h, label });
  const hoa = (k) => [() => ['HAND', 'OFF', 'AUTO'].indexOf(sw[k]), i => P.set(k, ['HAND', 'OFF', 'AUTO'][i])];

  const sc = (min, max, major, minor, opts = {}) => ({ min, max, major, minor, ...opts });
  const gndTest = () => !!(window.ROOM && ROOM.held && ROOM.held.userData.it && ROOM.held.userData.it.label === 'GND TEST');

  const CABS = [];

  /* ======================= CABINET 1 · AUXILIARY ===================== */
  CABS.push({
    id: 'aux', name: 'Auxiliary systems', title: 'UNIT 1  ·  AUXILIARY SYSTEMS', no: '+CP1',
    items: [
      SEC(570, 92, 1080, 270, 'STATION SERVICE 480 V  ·  125 VDC'),
      M(130, 200, 'STATION SERVICE\nVOLTS', sc(0, 600, 100, 20, { unit: 'AC VOLTS' }), () => S.vSS),
      M(275, 200, 'STATION SERVICE\nAMPERES', sc(0, 150, 25, 5, { unit: 'AC AMPERES' }), () => S.iSS * (1 + 0.01 * Math.sin(S.t * 0.7))),
      M(420, 200, 'BATTERY\nVOLTS', sc(0, 150, 25, 5, { unit: 'DC VOLTS', red: [0, 115] }), () => S.dcV),
      M(565, 200, 'CHARGER\nAMPERES', sc(0, 50, 10, 2, { unit: 'DC AMPERES' }), () => S.chgA),
      L(700, 170, 'white', 'AC AVAILABLE', () => S.acOK),
      L(700, 255, 'amber', 'CHARGER\nTROUBLE', () => !S.chargerOK),
      L(830, 200, 'white', '+ GND', () => (gndTest() ? 1 : S.flt.dcGround ? 0.12 : 0.6) * (S.dcV > 60 ? 1 : 0), { dim: true }),
      L(930, 200, 'white', '− GND', () => (gndTest() ? 1 : S.flt.dcGround ? 1 : 0.6) * (S.dcV > 60 ? 1 : 0), { dim: true }),
      { t: 'plate', x: 880, y: 135, text: 'DC GROUND DETECTOR', w: 190, h: 18, size: 8 },
      PB(880, 280, 'black', 'GND TEST', () => {}, { small: true, tip: 'Hold to test both lamps. In service, the lamp on the grounded pole goes dim' }),

      SEC(570, 378, 1080, 280, 'GOVERNOR OIL PRESSURE UNIT'),
      M(130, 480, 'PRESSURE TANK\nPSI', sc(0, 400, 50, 10, { unit: 'PSI', red: [0, 250] }), () => S.opuP),
      E(240, 480, 'TANK\nLEVEL', sc(0, 100, 25, 5, { unit: '%', red: [70, 100] }), () => S.opuLvl * 100),
      E(310, 480, 'SUMP\nLEVEL', sc(0, 100, 25, 5, { unit: '%', red: [0, 30] }), () => S.opuSump * 100),
      L(395, 430, 'red', 'RUN', () => S.p1Run), L(455, 430, 'green', 'STOP', () => !S.p1Run),
      SEL(425, 525, 'OIL PUMP 1', ['HAND', 'OFF', 'AUTO'], ...hoa('p1')),
      L(545, 430, 'red', 'RUN', () => S.p2Run), L(605, 430, 'green', 'STOP', () => !S.p2Run),
      SEL(575, 525, 'OIL PUMP 2', ['HAND', 'OFF', 'AUTO'], ...hoa('p2')),
      SEL(720, 525, 'LEAD PUMP', ['1', '2'], () => sw.lead - 1, i => P.set('lead', i + 1)),
      L(720, 430, 'white', 'OPU READY', () => S.opuP > 260 && S.opuSump > 0.3),
      L(850, 430, 'amber', 'AIR VALVE\nOPEN', () => S.airAdd > 0),
      PB(850, 525, 'black', 'ADD AIR', () => P.cmd('airAdd'), { tip: 'Admit station air to the governor pressure tank (30 s)' }),
      { t: 'tape', x: 985, y: 500, w: 120, h: 70, rot: -0.05, text: 'ADD AIR WHEN\nTANK LVL > 65%' },

      SEC(570, 674, 1080, 250, 'COOLING WATER  ·  DRAFT TUBE AIR  ·  HEATERS'),
      M(130, 785, 'COOLING WATER\nFLOW', sc(0, 100, 20, 5, { unit: 'GPM', red: [0, 35] }), () => S.cwFlow),
      M(275, 785, 'STRAINER\nDIFF PRESSURE', sc(0, 10, 2, 0.5, { unit: 'PSI', red: [6, 10] }), () => S.strDp),
      L(375, 735, 'red', 'RUN', () => S.cwRun), L(435, 735, 'green', 'STOP', () => !S.cwRun),
      SEL(405, 830, 'CW PUMP', ['HAND', 'OFF', 'AUTO'], ...hoa('cw')),
      L(545, 735, 'amber', 'BACKWASH', () => S.backwash > 0),
      PB(545, 830, 'black', 'BACKWASH', () => P.cmd('backwash'), { tip: 'Start a 45 s strainer backwash' }),
      L(680, 735, 'red', 'OPEN', () => S.dtAir > 0.5), L(740, 735, 'green', 'CLOSED', () => S.dtAir <= 0.5),
      SEL(710, 830, 'DRAFT TUBE AIR', ['CLOSE', 'AUTO', 'OPEN'], () => ['CLOSE', 'AUTO', 'OPEN'].indexOf(sw.dtAir), i => P.set('dtAir', ['CLOSE', 'AUTO', 'OPEN'][i])),
      L(880, 735, 'amber', 'HEATERS ON', () => S.heater),
      SEL(880, 830, 'GEN HEATERS', ['OFF', 'AUTO', 'ON'], () => ['OFF', 'AUTO', 'ON'].indexOf(sw.heater), i => P.set('heater', ['OFF', 'AUTO', 'ON'][i])),
      M(1025, 785, 'CW OUTLET\nTEMP', sc(0, 50, 10, 2, { unit: '°C' }), () => S.tCwOut || 12),

      SEC(570, 940, 1080, 250, 'THRUST BEARING HP LIFT  ·  BRAKES  ·  STATION AIR  ·  SUMP'),
      M(130, 1050, 'HP LIFT OIL\nPRESSURE', sc(0, 3000, 500, 100, { unit: 'PSI' }), () => S.liftP),
      L(235, 1000, 'red', 'RUN', () => S.liftRun), L(295, 1000, 'green', 'STOP', () => !S.liftRun),
      SEL(265, 1095, 'LIFT PUMP', ['HAND', 'OFF', 'AUTO'], ...hoa('lift')),
      M(410, 1050, 'STATION AIR\nPSI', sc(0, 160, 20, 5, { unit: 'PSI', red: [0, 80] }), () => S.airP),
      L(515, 1000, 'red', 'APPLIED', () => S.brake > 0.5), L(575, 1000, 'green', 'RELEASED', () => S.brake < 0.05),
      SEL(545, 1095, 'BRAKES', ['RELEASE', 'AUTO', 'APPLY'], () => ['RELEASE', 'AUTO', 'APPLY'].indexOf(sw.brake), i => P.set('brake', ['RELEASE', 'AUTO', 'APPLY'][i])),
      L(680, 1000, 'red', 'COMPR RUN', () => S.compRun),
      E(790, 1050, 'SUMP\nLEVEL', sc(0, 100, 25, 5, { unit: '%', red: [85, 100] }), () => S.sump * 100),
      L(880, 1000, 'red', 'PUMP 1', () => S.sumpRun[0]), L(950, 1000, 'red', 'PUMP 2', () => S.sumpRun[1]),
      SEL(915, 1095, 'SUMP PUMPS', ['HAND', 'OFF', 'AUTO'], ...hoa('sump')),

      SEC(570, 1206, 1080, 250, 'INTAKE HEADGATE  ·  TRASH RACK'),
      E(110, 1320, 'HEADGATE\nPOSITION', sc(0, 100, 25, 5, { unit: '% OPEN' }), () => S.hg * 100),
      L(205, 1270, 'red', 'OPEN', () => S.hg > 0.995), L(265, 1270, 'green', 'CLOSED', () => S.hg < 0.005),
      PB(205, 1365, 'red', 'RAISE', () => P.cmd('hg', 1), { tip: 'Raise the intake headgate (runs to full open)' }),
      PB(265, 1365, 'black', 'STOP', () => P.cmd('hg', 0)),
      PB(325, 1365, 'green', 'LOWER', () => P.cmd('hg', -1), { tip: 'Lower the intake headgate (runs to closed)' }),
      L(325, 1270, 'amber', 'MOVING', () => (S.hgCmd !== 0 || S.hgEmerg ? 'flash' : false)),
      M(480, 1320, 'TRASH RACK\nDIFFERENTIAL', sc(0, 2, 0.5, 0.1, { unit: 'FT WATER', red: [0.8, 2], fmt: v => v.toFixed(1) }), () => ft(S.rackDh)),
      L(610, 1270, 'red', 'RAKE RUN', () => S.rakeRun),
      PB(610, 1365, 'black', 'RAKE START', () => P.cmd('rake'), { tip: 'Run one trash-rake cleaning cycle' }),
      M(760, 1320, 'PENSTOCK\nPRESSURE', sc(0, 30, 5, 1, { unit: 'PSI' }), () => S.pPen),
      { t: 'warn', x: 960, y: 1330, w: 200, h: 110 },
    ],
  });

  /* ================= CABINET 2 · TURBINE – GENERATOR ================= */
  const vSelPos = ['A-B', 'B-C', 'C-A'], aSelPos = ['A', 'B', 'C'];
  const phaseV = () => S.Vt * 480 * [1, 0.997, 1.004][vSelPos.indexOf(sw.vSel === 'AB' ? 'A-B' : sw.vSel === 'BC' ? 'B-C' : 'C-A')];
  const phaseA = () => S.I * P.NP.I * [1, 1.006, 0.993][aSelPos.indexOf(sw.aSel)];
  CABS.push({
    id: 'tg', name: 'Turbine & generator', title: 'UNIT 1  ·  TURBINE – GENERATOR', no: '+CP2',
    items: [
      SEC(570, 92, 1080, 270, 'GENERATOR  ·  72 POLE  ·  300 kVA  ·  480 V  ·  60 Hz  ·  100 RPM'),
      M(115, 195, 'GENERATOR\nVOLTS', sc(0, 600, 100, 20, { unit: 'AC VOLTS' }), phaseV),
      M(260, 195, 'GENERATOR\nAMPERES', sc(0, 500, 100, 20, { unit: 'AC AMPERES', red: [400, 500] }), phaseA),
      M(405, 195, 'KILOWATTS', sc(-50, 350, 50, 10, { unit: 'KILOWATTS' }), () => S.Pkw),
      M(550, 195, 'KILOVARS', sc(-200, 200, 50, 10, { unit: 'KVAR', fmt: v => (v > 0 ? v : v < 0 ? -v : 0).toFixed(0), sub: ['LEAD', 'LAG'] }), () => S.Qkvar),
      M(695, 195, 'FREQUENCY', sc(55, 65, 1, 0.2, { unit: 'HERTZ' }), () => (S.Vt > 0.05 ? S.fHz : 55)),
      M(840, 195, 'POWER FACTOR', sc(-0.5, 0.5, 0.1, 0.05, { unit: 'POWER FACTOR', pf: true }), () => (S.I > 0.02 ? Math.sign(S.Qkvar || 1) * (1 - Math.abs(S.pf)) * 1 : 0)),
      SEL(115, 322, 'VOLTMETER', vSelPos, () => ['AB', 'BC', 'CA'].indexOf(sw.vSel), i => P.set('vSel', ['AB', 'BC', 'CA'][i]), { small: true, noPlate: true }),
      SEL(260, 322, 'AMMETER', aSelPos, () => aSelPos.indexOf(sw.aSel), i => P.set('aSel', aSelPos[i]), { small: true, noPlate: true }),
      { t: 'counter', x: 1005, y: 150, w: 130, digits: 8, label: 'KILOWATT-HOURS', get: () => S.kwh },
      { t: 'counter', x: 1005, y: 222, w: 130, digits: 7, dec: 1, label: 'RUNNING HOURS', get: () => S.hours },
      { t: 'counter', x: 1005, y: 294, w: 130, digits: 5, label: 'STARTS', get: () => S.starts },

      SEC(570, 378, 1080, 280, 'SYNCHRONIZING  ·  GENERATOR BREAKER 52G'),
      M(115, 480, 'INCOMING\nVOLTS', sc(0, 600, 100, 20, { unit: 'AC VOLTS' }), () => S.Vt * 480),
      M(260, 480, 'RUNNING\nVOLTS', sc(0, 600, 100, 20, { unit: 'AC VOLTS' }), () => S.vbus * 480),
      L(360, 470, 'white', 'SYNC', () => syncLamp(), { dim: true }),
      { t: 'synchro', x: 465, y: 480, s: 140, label: 'SYNCHROSCOPE' },
      L(570, 470, 'white', 'SYNC', () => syncLamp(), { dim: true }),
      L(670, 420, 'amber', 'AUTO SYNC\nACTIVE', () => (S.autoSync ? 'flash' : false)),
      SEL(670, 530, 'SYNC MODE', ['OFF', 'MAN', 'AUTO'], () => ['OFF', 'MAN', 'AUTO'].indexOf(sw.syncMode), i => P.set('syncMode', ['OFF', 'MAN', 'AUTO'][i])),
      L(785, 420, 'white', '25 PERMIT', () => S.syncOK),
      SEL(785, 530, 'SYNC CHECK', ['NORMAL', 'BYPASS'], () => (sw.syncBypass ? 1 : 0), i => P.set('syncBypass', i === 1), { key: true, tip2: 'Bypass the sync-check relay (allows closing onto a dead bus, or out of phase)' }),
      L(895, 408, 'green', 'OPEN', () => !S.cb), L(985, 408, 'red', 'CLOSED', () => S.cb),
      { t: 'cs', x: 940, y: 548, label: '52G GENERATOR BREAKER', left: 'TRIP', right: 'CLOSE', act: s => P.cmd(s > 0 ? 'cbClose' : 'cbTrip'), state: () => S.cb, flag: () => (S.cb ? 'red' : 'green') },
      L(1070, 408, 'white', 'SPRING\nCHARGED', () => S.dcV > 90),

      SEC(570, 674, 1080, 250, 'TURBINE  ·  VERTICAL FRANCIS  ·  250 kW  ·  40 FT NET HEAD'),
      M(115, 780, 'SPEED', sc(0, 200, 20, 5, { unit: 'RPM', red: [140, 200] }), () => S.w * 100),
      M(260, 780, 'WICKET GATE', sc(0, 100, 10, 2, { unit: '% OPEN' }), () => S.y * 100, { pointer2: () => S.gl * 100 }),
      M(405, 780, 'SPIRAL CASE\nPRESSURE', sc(0, 30, 5, 1, { unit: 'PSI' }), () => S.pSc),
      M(550, 780, 'DRAFT TUBE\nPRESSURE', sc(-10, 5, 2.5, 0.5, { unit: 'INHG VAC   PSI', compound: true }), () => (S.pDt < 0 ? S.pDt * P.M2INHG : S.pDt * P.M2PSI)),
      M(695, 780, 'TURBINE\nDISCHARGE', sc(0, 120, 20, 5, { unit: 'CFS' }), () => S.qt * 35.3147),
      M(840, 780, 'NET HEAD', sc(0, 60, 10, 2, { unit: 'FEET' }), () => ft(Math.max(0, S.hnet))),
      M(985, 780, 'SHAFT\nVIBRATION', sc(0, 20, 5, 1, { unit: 'MILS P-P', red: [12, 20] }), () => S.vib * (1 + 0.06 * Math.sin(S.t * 2 * Math.PI * 1.667)) + S.rope * 0.8 * Math.sin(S.ropePh)),

      SEC(570, 940, 1080, 250, 'GOVERNOR  ·  TURBINE INLET VALVE'),
      { t: 'disp', x: 175, y: 1014, w: 250, h: 58, kind: 'vfd', cols: 20, rows: 2, text: govText, label: 'DIGITAL GOVERNOR' },
      L(345, 995, 'red', 'GOV\nENABLED', () => S.govEn), L(410, 995, 'amber', 'ESD', () => S.esd),
      SEL(95, 1110, 'GOVERNOR', ['MAN', 'AUTO'], () => (sw.govMode === 'AUTO' ? 1 : 0), i => P.set('govMode', i ? 'AUTO' : 'MAN')),
      RL(215, 1110, 'GATE LIMIT', d => P.hold('gl', d)),
      RL(335, 1110, 'SPEED / LOAD', d => P.hold('spd', d), { tip2: 'Off line: speed reference. On line: load reference (kW)' }),
      { t: 'tape', x: 430, y: 1120, w: 108, h: 58, rot: 0.06, text: 'ROUGH ZONE\n< 110 kW' },
      L(545, 985, 'red', 'OPEN', () => S.tiv > 0.995), L(605, 985, 'green', 'CLOSED', () => S.tiv < 0.005),
      PB(545, 1105, 'red', 'OPEN', () => P.cmd('tivOpen'), { tip: 'Open the turbine inlet valve (needs <5 psi differential)' }),
      PB(605, 1105, 'green', 'CLOSE', () => P.cmd('tivClose'), { tip: 'Close the turbine inlet valve' }),
      { t: 'plate', x: 575, y: 1045, text: 'INLET VALVE', w: 130, h: 18, size: 9 },
      L(700, 985, 'red', 'OPEN', () => S.byp > 0.98), L(760, 985, 'green', 'CLOSED', () => S.byp < 0.02),
      PB(700, 1105, 'red', 'OPEN', () => P.cmd('bypOpen'), { tip: 'Open the inlet valve bypass (equalizes the spiral case)' }),
      PB(760, 1105, 'green', 'CLOSE', () => P.cmd('bypClose')),
      { t: 'plate', x: 730, y: 1045, text: 'BYPASS VALVE', w: 130, h: 18, size: 9 },
      M(880, 1060, 'VALVE\nDIFFERENTIAL', sc(0, 20, 5, 1, { unit: 'PSI', red: [5, 20] }), () => Math.max(0, S.tivDp)),
      { t: 'disp', x: 1035, y: 1030, w: 130, h: 50, kind: 'led7', digits: 4, text: () => rtdValue(), label: 'RTD SCANNER  °C' },
      { t: 'disp', x: 1035, y: 1080, w: 130, h: 26, kind: 'lcdtag', text: () => rtdName() },
      PB(1000, 1135, 'black', '▼', () => { sw.rtd = sw.rtd > 1 ? sw.rtd - 1 : RTD.length; }, { small: true, tip: 'Previous RTD channel' }),
      PB(1070, 1135, 'black', '▲', () => { sw.rtd = sw.rtd < RTD.length ? sw.rtd + 1 : 1; }, { small: true, tip: 'Next RTD channel' }),

      SEC(570, 1206, 1080, 250, 'UNIT CONTROL  ·  LOCKOUTS  ·  GENERATOR PROTECTION'),
      SEL(95, 1335, 'UNIT CONTROL', ['MAN', 'AUTO'], () => (sw.unitMode === 'AUTO' ? 1 : 0), i => P.set('unitMode', i ? 'AUTO' : 'MAN')),
      L(195, 1270, 'white', 'READY', () => S.seq === 'STOPPED' && P.permissives().every(p => p[1])),
      L(270, 1270, 'red', 'RUNNING', () => (S.seq !== 'STOPPED' && S.seq !== 'STANDSTILL' && S.seq !== 'MANUAL' ? (S.seq === 'ONLINE' || S.seq === 'SNL' ? true : 'flash') : S.govEn)),
      PB(195, 1360, 'green', 'START', () => P.cmd('start'), { big: true, tip: 'AUTO: run the start sequence. MAN: enable the governor' }),
      PB(270, 1360, 'red', 'STOP', () => P.cmd('stop'), { big: true, tip: 'AUTO: normal stop (unload, open 52G, shut down). MAN: governor shutdown' }),
      { t: 'estop', x: 385, y: 1345 },
      { t: 'lockout', x: 505, y: 1345, label: '86G\nELECTRICAL', which: '86G', get: () => S.lock86G },
      { t: 'lockout', x: 610, y: 1345, label: '86M\nMECHANICAL', which: '86M', get: () => S.lock86M },
      { t: 'relay', x: 860, y: 1335, w: 300, h: 190 },
    ],
  });
  function syncLamp() {          // dark-lamp method: lamps are dark at synchronism
    if (S.cb || S.Vt < 0.2 || S.vbus < 0.2) return 0;
    const d = Math.hypot(S.Vt * Math.cos(S.syncAng) - S.vbus, S.Vt * Math.sin(S.syncAng)) / 2;
    return Math.min(1, d);
  }
  const RTD = [
    ['TB PAD', () => S.tPadT], ['TB OIL', () => S.tOilT], ['UGB PAD', () => S.tUGB], ['LGB PAD', () => S.tLGB], ['TGB PAD', () => S.tTGB], ['TGB OIL', () => S.tOilG],
    ['STATOR A1', () => S.tSt + 0.4], ['STATOR B1', () => S.tSt + 2.1], ['STATOR C1', () => S.tSt - 1.3], ['STATOR A2', () => S.tSt + 3.2], ['STATOR B2', () => S.tSt + 0.7], ['STATOR C2', () => S.tSt - 0.6],
    ['COLD AIR', () => S.tAirC], ['HOT AIR', () => S.tAirH], ['CW IN', () => S.tCw], ['CW OUT', () => S.tCwOut || S.tCw],
  ];
  function rtdValue() { const r = RTD[sw.rtd - 1]; return r[1]().toFixed(0).padStart(4, ' '); }
  function rtdName() { return String(sw.rtd).padStart(2, '0') + '  ' + RTD[sw.rtd - 1][0]; }
  function govText() {
    const gate = `GATE ${f1(S.y * 100).padStart(5)}% LIM ${f0(S.gl * 100).padStart(3)}`;
    let l2;
    if (S.cb) l2 = `LOAD REF ${f0(S.pref).padStart(4)} KW ${S.lvlActive ? 'LVL' : 'DRP'}`;
    else l2 = `SPD REF ${f1(S.nref * 100).padStart(5)}% ${S.govMode.slice(0, 5).padStart(5)}`;
    return [gate.padEnd(20), l2.padEnd(20)];
  }

  /* ====== CABINET 3 · EXCITATION · PLC · ANNUNCIATOR · SPILLWAY ======= */
  const sgPos = i => () => ft(S.sg[i]);
  const levelPos = ['OFF', 'TURB', 'TURB_SPILL'];
  CABS.push({
    id: 'exc', name: 'Excitation, PLC & spillway', title: 'UNIT 1  ·  EXCITATION  ·  CONTROL  ·  SPILLWAY', no: '+CP3',
    items: [
      { t: 'ann', x: 570, y: 262, cols: 8, rows: 5, cw: 112, ch: 62 },
      PB(390, 470, 'black', 'TEST', () => {}, { small: true, test: true, tip: 'Annunciator lamp test (hold)' }),
      PB(510, 470, 'black', 'SILENCE', () => P.cmd('ann', 'silence'), { small: true }),
      PB(630, 470, 'black', 'ACK', () => P.cmd('ann', 'ack'), { small: true, tip: 'Acknowledge alarms' }),
      PB(750, 470, 'black', 'RESET', () => P.cmd('ann', 'reset'), { small: true, tip: 'Reset cleared alarms' }),

      SEC(570, 520, 1080, 260, 'BRUSHLESS EXCITATION  ·  DIGITAL AVR'),
      M(115, 630, 'EXCITER FIELD\nAMPERES', sc(0, 8, 1, 0.2, { unit: 'DC AMPERES' }), () => S.vfe * 0.85),
      M(260, 630, 'EXCITER FIELD\nVOLTS', sc(0, 150, 25, 5, { unit: 'DC VOLTS' }), () => Math.max(0, S.vr) * 15.3),
      { t: 'disp', x: 470, y: 585, w: 250, h: 58, kind: 'vfd', cols: 20, rows: 2, text: avrText, label: 'AUTOMATIC VOLTAGE REGULATOR' },
      { t: 'leds', x: 470, y: 640, items: [['AVR OK', () => S.excOn && !S.flt.avr, 'green'], ['OEL', () => S.oel, 'red'], ['UEL', () => S.uel, 'red'], ['V/Hz', () => S.vhz, 'red'], ['FCR', () => sw.avrMode === 'FCR' && S.excOn, 'amber']] },
      SEL(405, 738, 'AVR MODE', ['FCR', 'AVR', 'VAR', 'PF'], () => ['FCR', 'AVR', 'VAR', 'PF'].indexOf(sw.avrMode), i => P.set('avrMode', ['FCR', 'AVR', 'VAR', 'PF'][i])),
      RL(535, 738, 'AVR SETPOINT', d => P.hold('avr', d)),
      L(670, 583, 'green', 'OFF', () => !S.excOn), L(760, 583, 'red', 'ON', () => S.excOn),
      { t: 'cs', x: 715, y: 718, label: 'EXCITATION', left: 'OFF', right: 'ON', act: s => P.cmd(s > 0 ? 'excOn' : 'excOff'), state: () => S.excOn, flag: () => (S.excOn ? 'red' : 'green') },
      M(1000, 630, 'GENERATOR\nKILOVARS', sc(-200, 200, 50, 10, { unit: 'KVAR', fmt: v => Math.abs(v).toFixed(0), sub: ['LEAD', 'LAG'] }), () => S.Qkvar),
      { t: 'tape', x: 870, y: 700, w: 112, h: 56, rot: -0.04, text: 'PF 0.97 LAG\nPER UTILITY' },

      SEC(570, 796, 1080, 330, 'PROGRAMMABLE CONTROLLER  ·  OPERATOR INTERFACE'),
      { t: 'plc', x: 335, y: 965, w: 560, h: 270 },
      { t: 'oit', x: 860, y: 965, w: 330, h: 280 },

      SEC(570, 1142, 1080, 320, 'SPILLWAY GATES  ·  POND LEVEL CONTROL'),
      E(85, 1300, 'HEADWATER\nEL FT', sc(505, 517, 2, 0.5, { unit: 'EL', fmt: v => v.toFixed(0), red: [514.2, 517] }), () => ft(S.hw), { h: 220, pointer2: () => ft(S.levelSP) }),
      E(160, 1300, 'TAILWATER\nEL FT', sc(468, 480, 2, 0.5, { unit: 'EL', fmt: v => v.toFixed(0) }), () => ft(S.tw), { h: 220 }),
      ...gateGroup(0, 245), ...gateGroup(1, 545),
      L(980, 1210, 'red', 'LEVEL CTL\nACTIVE', () => S.lvlActive && S.seq === 'ONLINE' || (sw.levelCtl === 'TURB_SPILL' && S.sgAuto.some(d => d !== 0))),
      SEL(980, 1310, 'LEVEL CONTROL', ['OFF', 'TURB', 'T+SPILL'], () => levelPos.indexOf(sw.levelCtl), i => P.set('levelCtl', levelPos[i])),
      { t: 'disp', x: 980, y: 1405, w: 150, h: 50, kind: 'led7', digits: 4, text: () => f0(S.qspill * 35.3147 + S.qover * 35.3147).padStart(4, ' '), label: 'SPILL CFS' },
    ],
  });
  function gateGroup(i, x0) {
    const n = i + 1;
    return [
      E(x0 + 10, 1300, `GATE ${n}\nOPENING FT`, sc(0, 6, 1, 0.2, { unit: 'FT', fmt: v => v.toFixed(0) }), sgPos(i), { h: 220 }),
      L(x0 + 100, 1215, 'red', 'OPEN', () => S.sg[i] > 0.02), L(x0 + 165, 1215, 'green', 'CLOSED', () => S.sg[i] <= 0.02),
      L(x0 + 230, 1215, 'amber', 'MOTOR', () => (S.sgRun[i] !== 0 ? 'flash' : (i === 0 && S.flt.sg1 ? true : false))),
      PB(x0 + 100, 1310, 'red', 'RAISE', () => P.cmd('sg', [i, 1]), { tip: `Raise spillway gate ${n} (runs until STOP or full open; MAN only)` }),
      PB(x0 + 165, 1310, 'black', 'STOP', () => P.cmd('sg', [i, 0])),
      PB(x0 + 230, 1310, 'green', 'LOWER', () => P.cmd('sg', [i, -1]), { tip: `Lower spillway gate ${n} (MAN only)` }),
      SEL(x0 + 165, 1405, `GATE ${n} MODE`, ['MAN', 'AUTO'], () => (sw.sgMode[i] === 'AUTO' ? 1 : 0), k => P.set('sgMode', k ? 'AUTO' : 'MAN', i), { small: true }),
    ];
  }
  function avrText() {
    const m = sw.avrMode;
    let l1;
    if (!S.excOn) l1 = 'EXCITATION OFF      ';
    else if (m === 'AVR') l1 = `AVR  SET ${f1(S.vref * 100).padStart(5)}% V   `;
    else if (m === 'VAR') l1 = `VAR  SET ${f0(S.qref * 300).padStart(4)} KVAR  `;
    else if (m === 'PF') { const pf = S.pfref <= 1 ? S.pfref : 2 - S.pfref; l1 = `PF   SET ${pf.toFixed(3)} ${S.pfref <= 1 ? 'LAG ' : 'LEAD'}  `; }
    else l1 = `FCR  SET ${(S.fcrRef * 0.85).toFixed(2).padStart(5)} A    `;
    const l2 = `VT ${f1(S.Vt * 100).padStart(5)}% IF ${(S.ifd).toFixed(2).padStart(4)}PU`;
    return [l1.slice(0, 20).padEnd(20), l2.slice(0, 20).padEnd(20)];
  }

  /* ---------------------------------------------- OIT (PLC terminal) */
  const OIT = { page: 0, scroll: 0, pages: ['STATUS', 'PERMISSIVES', 'LEVEL CONTROL', 'LOAD SETPOINT', 'SPILLWAY', 'EVENTS', 'MACHINE DATA'] };
  function oitText() {
    const pg = OIT.pages[OIT.page];
    const L4 = [];
    const hdr = (t) => `${String(OIT.page + 1)}/${OIT.pages.length} ${t}`.slice(0, 20).padEnd(20);
    const clock = () => { const t = S.tod; const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = Math.floor(t) % 60; return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`; };
    if (pg === 'STATUS') {
      L4.push(`UNIT 1     ${clock()}`);
      L4.push(`${String(P.STEPNO[S.seq] ?? '-').padStart(2)} ${S.seqMsg}`.slice(0, 20));
      L4.push(`${f0(S.Pkw).padStart(4)}KW ${(Math.abs(S.pf)).toFixed(2)}PF ${f1(S.fHz).padStart(4)}HZ`);
      L4.push(`HW ${f2(ft(S.hw))} SP ${f2(ft(S.levelSP))}`);
    } else if (pg === 'PERMISSIVES') {
      const ps = P.permissives();
      L4.push(hdr('START PERMIT'));
      for (let i = 0; i < 3; i++) { const p = ps[(OIT.scroll + i) % ps.length]; L4.push(`${p[1] ? ' OK ' : '>NO<'}${p[0]}`.slice(0, 20)); }
    } else if (pg === 'LEVEL CONTROL') {
      L4.push(hdr('POND LEVEL'));
      L4.push(`SETPOINT ${f2(ft(S.levelSP))} FT`);
      L4.push(`INFLOW EST ${f0(S.qinEst * 35.3147).padStart(4)} CFS`);
      L4.push(`AUTO RESTART  ${S.autoRestart ? 'ON ' : 'OFF'}`);
    } else if (pg === 'LOAD SETPOINT') {
      L4.push(hdr('LOAD'));
      L4.push(`LOAD SP   ${f0(S.loadSP).padStart(4)} KW`);
      L4.push(`LOAD REF  ${f0(S.pref).padStart(4)} KW`);
      L4.push(S.lvlActive ? 'SET BY LEVEL CONTROL' : 'UP/DN ADJUSTS SP');
    } else if (pg === 'SPILLWAY') {
      L4.push(hdr('SPILLWAY'));
      L4.push(`G1 ${f2(ft(S.sg[0]))}FT G2 ${f2(ft(S.sg[1]))}FT`);
      L4.push(`SPILL ${f0((S.qspill + S.qover) * 35.3147).padStart(5)} CFS`);
      L4.push(`RIVER ${f0(S.qin * 35.3147).padStart(5)} CFS`);
    } else if (pg === 'EVENTS') {
      const ev = P.events.slice().reverse();
      L4.push(hdr('EVENTS'));
      for (let i = 0; i < 3; i++) {
        const e = ev[OIT.scroll + i];
        if (!e) { L4.push(''); continue; }
        const t = e.t; const hm = `${String(Math.floor(t / 3600)).padStart(2, '0')}${String(Math.floor(t / 60) % 60).padStart(2, '0')}`;
        L4.push(`${hm} ${e.msg}`.slice(0, 20));
      }
    } else {
      L4.push(hdr('MACHINE'));
      L4.push(`EFF ${f1(S.effF * 100).padStart(4)}% Q ${f0(S.qt * 35.3147).padStart(3)}CFS`);
      L4.push(`HRS ${f0(S.hours)} ST ${S.starts}`);
      L4.push(`MWH ${(S.kwh / 1000).toFixed(1)}`);
    }
    return L4.map(l => l.slice(0, 20).padEnd(20));
  }
  function oitKey(k) {
    const pg = OIT.pages[OIT.page];
    if (k === 'F1') { OIT.page = 0; OIT.scroll = 0; }
    else if (k === 'F2') { OIT.page = 2; OIT.scroll = 0; }
    else if (k === 'F3') { OIT.page = 5; OIT.scroll = 0; }
    else if (k === 'F4') { OIT.page = 1; OIT.scroll = 0; }
    else if (k === 'RIGHT') { OIT.page = (OIT.page + 1) % OIT.pages.length; OIT.scroll = 0; }
    else if (k === 'LEFT') { OIT.page = (OIT.page + OIT.pages.length - 1) % OIT.pages.length; OIT.scroll = 0; }
    else if (k === 'UP' || k === 'DOWN') {
      const d = k === 'UP' ? 1 : -1;
      if (pg === 'LEVEL CONTROL') S.levelSP = Math.max(511.5 * FT, Math.min(514.2 * FT, S.levelSP + d * 0.05 * FT));
      else if (pg === 'LOAD SETPOINT') { if (!S.lvlActive) { S.loadSP = Math.max(0, Math.min(270, S.loadSP + d * 5)); if (S.cb && S.seq === 'ONLINE') S.prefTarget = S.loadSP; } }
      else if (pg === 'EVENTS') OIT.scroll = Math.max(0, OIT.scroll - d);
      else if (pg === 'PERMISSIVES') OIT.scroll = (OIT.scroll + (d < 0 ? 1 : P.permissives().length - 1)) % P.permissives().length;
    } else if (k === 'ENT') {
      if (pg === 'LEVEL CONTROL') S.autoRestart = !S.autoRestart;
    }
  }

  /* =====================================================================
     DRAWING
     ===================================================================== */
  function cv(w, h) { const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c; }
  function rng(seed) { let s = (seed * 2654435761) >>> 0 || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
  function rrect(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  function fitText(g, text, maxW, size, weight = 600, font = FONT) {
    let s = size; g.font = `${weight} ${s}px ${font}`;
    while (g.measureText(text).width > maxW && s > 4) { s -= 0.5; g.font = `${weight} ${s}px ${font}`; }
    return s;
  }

  /* ---------- atlas (shelf packer) */
  function Atlas(size = 2048) {
    const pages = [];
    function newPage() { const c = cv(size, size); const g = c.getContext('2d'); pages.push({ c, g, x: 2, y: 2, rowH: 0 }); return pages[pages.length - 1]; }
    newPage();
    return {
      pages, size,
      alloc(w, h) {
        w = Math.ceil(w) + 4; h = Math.ceil(h) + 4;
        let p = pages[pages.length - 1];
        if (p.x + w > size) { p.x = 2; p.y += p.rowH; p.rowH = 0; }
        if (p.y + h > size) { p = newPage(); }
        const r = { page: pages.indexOf(p), x: p.x + 2, y: p.y + 2, w: w - 4, h: h - 4, g: p.g };
        p.x += w; p.rowH = Math.max(p.rowH, h);
        return r;
      },
    };
  }

  /* ---------- engraved lamacoid nameplate */
  function drawPlate(g, x, y, w, h, text, opt = {}) {
    const style = opt.style || 'bw';
    const bg = style === 'bw' ? '#141414' : style === 'wb' ? '#ecebe4' : style === 'red' ? '#b3121a' : style === 'yellow' ? '#e9b81c' : '#141414';
    const fg = style === 'bw' ? '#f4f2ea' : style === 'wb' ? '#121212' : style === 'red' ? '#fbf6ee' : style === 'yellow' ? '#141414' : '#f4f2ea';
    g.save();
    rrect(g, x, y, w, h, Math.min(w, h) * 0.08); g.fillStyle = bg; g.fill();
    // bevelled edge from the engraving cutter
    g.strokeStyle = style === 'bw' ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.18)'; g.lineWidth = Math.max(1, h * 0.04); g.stroke();
    const lines = String(text).split('\n');
    const px = opt.size || h / (lines.length * 1.25 + 0.25);
    g.fillStyle = fg; g.textAlign = 'center'; g.textBaseline = 'middle';
    const lh = px * 1.12, y0 = y + h / 2 - (lines.length - 1) * lh / 2;
    lines.forEach((l, i) => {
      const s = fitText(g, l, w * 0.92, px, opt.weight || 600);
      g.font = `${opt.weight || 600} ${s}px ${FONT}`;
      if (opt.track) g.letterSpacing = `${opt.track}px`;
      g.fillText(l, x + w / 2, y0 + i * lh + px * 0.05);
    });
    g.restore();
  }

  /* ---------- switchboard meter dial (250°) */
  function niceNum(v, step) { const d = step < 1 ? (step < 0.1 ? 2 : 1) : 0; return v.toFixed(d); }
  function drawDial(g, x, y, s, m) {
    const sc = m.scale;
    g.save(); g.translate(x, y);
    // face
    const gr = g.createLinearGradient(0, 0, 0, s);
    gr.addColorStop(0, '#f6f3ea'); gr.addColorStop(1, '#ebe6d8');
    g.fillStyle = gr; g.fillRect(0, 0, s, s);
    const cx = s / 2, cy = s * 0.56, R = s * 0.40;
    const a0 = (-125 - 90) * Math.PI / 180, a1 = (125 - 90) * Math.PI / 180;
    const ang = v => a0 + (a1 - a0) * (v - sc.min) / (sc.max - sc.min);
    // red band
    if (sc.red) {
      g.strokeStyle = '#c22a1f'; g.lineWidth = s * 0.035;
      g.beginPath(); g.arc(cx, cy, R * 0.93, ang(Math.max(sc.red[0], sc.min)), ang(Math.min(sc.red[1], sc.max))); g.stroke();
    }
    g.strokeStyle = '#141414'; g.lineWidth = s * 0.008;
    g.beginPath(); g.arc(cx, cy, R, a0, a1); g.stroke();
    const nMinor = Math.round((sc.max - sc.min) / sc.minor);
    for (let i = 0; i <= nMinor; i++) {
      const v = sc.min + i * sc.minor, a = ang(v);
      const major = Math.abs(((v - sc.min) / sc.major) - Math.round((v - sc.min) / sc.major)) < 1e-6;
      const half = !major && sc.major / sc.minor >= 4 && Math.abs(((v - sc.min) / (sc.major / 2)) - Math.round((v - sc.min) / (sc.major / 2))) < 1e-6;
      const l = major ? s * 0.075 : half ? s * 0.05 : s * 0.032;
      g.lineWidth = major ? s * 0.012 : s * 0.006;
      g.beginPath(); g.moveTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R); g.lineTo(cx + Math.cos(a) * (R - l), cy + Math.sin(a) * (R - l)); g.stroke();
      if (major) {
        let lab = sc.fmt ? sc.fmt(v) : niceNum(v, sc.major);
        if (sc.pf) lab = (1 - Math.abs(v)).toFixed(1).replace(/^0/, '') === '1.0' ? '1.0' : (1 - Math.abs(v)).toFixed(1).replace(/^0/, '');
        if (sc.compound) lab = v < 0 ? String(-v) : String(v);
        g.fillStyle = '#141414'; g.font = `600 ${s * 0.085}px ${DIAL}`; g.textAlign = 'center'; g.textBaseline = 'middle';
        g.fillText(lab, cx + Math.cos(a) * (R - s * 0.135), cy + Math.sin(a) * (R - s * 0.135));
      }
    }
    // legends
    g.fillStyle = '#141414'; g.textAlign = 'center';
    g.font = `600 ${s * 0.068}px ${FONT}`;
    g.fillText(sc.unit || '', cx, cy + R * 0.48);
    if (sc.sub) { g.font = `600 ${s * 0.058}px ${FONT}`; g.fillText(sc.sub[0], cx - R * 0.62, cy + R * 0.78); g.fillText(sc.sub[1], cx + R * 0.62, cy + R * 0.78); }
    if (sc.pf) { g.font = `600 ${s * 0.058}px ${FONT}`; g.fillText('LEAD', cx - R * 0.62, cy + R * 0.78); g.fillText('LAG', cx + R * 0.62, cy + R * 0.78); }
    if (sc.compound) { g.font = `600 ${s * 0.05}px ${FONT}`; g.fillText('VACUUM', cx - R * 0.55, cy + R * 0.78); g.fillText('PRESSURE', cx + R * 0.62, cy + R * 0.78); }
    // maker-neutral class mark and the pivot boss
    g.font = `500 ${s * 0.04}px ${FONT}`; g.fillStyle = '#555';
    g.fillText('CLASS 1.0  ⊓  60 Hz', cx, s * 0.93);
    g.fillStyle = '#2a2a2a'; g.beginPath(); g.arc(cx, cy, s * 0.05, 0, 7); g.fill();
    // aging: faint yellowing from the top and a thin shadow under the bezel lip
    const sh = g.createLinearGradient(0, 0, 0, s * 0.18); sh.addColorStop(0, 'rgba(60,45,20,0.20)'); sh.addColorStop(1, 'rgba(60,45,20,0)');
    g.fillStyle = sh; g.fillRect(0, 0, s, s * 0.18);
    g.restore();
    return { cx: cx / s, cy: cy / s, R: R / s, a0, a1 };
  }
  function meterAngle(m, v) {
    const sc = m.scale, a0 = (-125) * Math.PI / 180, a1 = 125 * Math.PI / 180;
    const t = Math.max(-0.03, Math.min(1.03, (v - sc.min) / (sc.max - sc.min)));
    return a0 + (a1 - a0) * t;
  }
  /* ---------- edgewise (vertical) meter scale */
  function drawEdge(g, x, y, w, h, m) {
    const sc = m.scale;
    g.save(); g.translate(x, y);
    g.fillStyle = '#f3efe4'; g.fillRect(0, 0, w, h);
    const top = h * 0.06, bot = h * 0.94;
    const yv = v => bot - (bot - top) * (v - sc.min) / (sc.max - sc.min);
    if (sc.red) { g.fillStyle = '#c22a1f'; const ya = yv(Math.min(sc.red[1], sc.max)), yb = yv(Math.max(sc.red[0], sc.min)); g.fillRect(w * 0.08, ya, w * 0.1, yb - ya); }
    g.strokeStyle = '#141414'; g.fillStyle = '#141414';
    const n = Math.round((sc.max - sc.min) / sc.minor);
    for (let i = 0; i <= n; i++) {
      const v = sc.min + i * sc.minor, yy = yv(v);
      const major = Math.abs(((v - sc.min) / sc.major) - Math.round((v - sc.min) / sc.major)) < 1e-6;
      g.lineWidth = major ? w * 0.03 : w * 0.015;
      g.beginPath(); g.moveTo(w * 0.2, yy); g.lineTo(w * (major ? 0.48 : 0.36), yy); g.stroke();
      if (major) { g.font = `600 ${w * 0.26}px ${DIAL}`; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText(sc.fmt ? sc.fmt(v) : niceNum(v, sc.major), w * 0.52, yy); }
    }
    g.restore();
  }
  function edgeFrac(m, v) { const sc = m.scale; return Math.max(-0.02, Math.min(1.02, (v - sc.min) / (sc.max - sc.min))); }

  /* ---------- synchroscope face */
  function drawSyncFace(g, x, y, s) {
    g.save(); g.translate(x, y);
    g.fillStyle = '#121212'; g.fillRect(0, 0, s, s);
    const cx = s / 2, cy = s / 2, R = s * 0.42;
    const gr = g.createRadialGradient(cx, cy * 0.9, 0, cx, cy, R);
    gr.addColorStop(0, '#f7f4ea'); gr.addColorStop(1, '#e6e1d2');
    g.fillStyle = gr; g.beginPath(); g.arc(cx, cy, R, 0, 7); g.fill();
    g.strokeStyle = '#141414'; g.lineWidth = s * 0.006;
    for (let i = 0; i < 36; i++) {
      const a = i / 36 * Math.PI * 2 - Math.PI / 2, l = i % 9 === 0 ? s * 0.08 : i % 3 === 0 ? s * 0.05 : s * 0.03;
      g.lineWidth = i % 9 === 0 ? s * 0.012 : s * 0.006;
      g.beginPath(); g.moveTo(cx + Math.cos(a) * R * 0.97, cy + Math.sin(a) * R * 0.97); g.lineTo(cx + Math.cos(a) * (R * 0.97 - l), cy + Math.sin(a) * (R * 0.97 - l)); g.stroke();
    }
    // the in-phase index at 12 o'clock
    g.fillStyle = '#c22a1f'; g.beginPath(); g.moveTo(cx, cy - R * 0.98); g.lineTo(cx - s * 0.035, cy - R * 0.80); g.lineTo(cx + s * 0.035, cy - R * 0.80); g.closePath(); g.fill();
    g.fillStyle = '#141414'; g.font = `700 ${s * 0.07}px ${FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('SLOW', cx - R * 0.5, cy + R * 0.15); g.fillText('FAST', cx + R * 0.5, cy + R * 0.15);
    g.font = `600 ${s * 0.05}px ${FONT}`;
    g.fillText('◄', cx - R * 0.5, cy + R * 0.32); g.fillText('►', cx + R * 0.5, cy + R * 0.32);
    g.fillText('SYNCHROSCOPE', cx, cy + R * 0.55);
    g.fillStyle = '#2a2a2a'; g.beginPath(); g.arc(cx, cy, s * 0.04, 0, 7); g.fill();
    g.restore();
  }

  /* ---------- selector / control-switch escutcheon with position legends */
  function drawEscutcheon(g, x, y, s, pos, angles, opt = {}) {
    g.save(); g.translate(x + s / 2, y + s / 2);
    g.fillStyle = opt.cs ? '#1c1c1c' : '#161616';
    g.beginPath(); g.arc(0, 0, s * 0.48, 0, 7); g.fill();
    g.strokeStyle = 'rgba(255,255,255,0.08)'; g.lineWidth = s * 0.012; g.stroke();
    g.fillStyle = '#f4f2ea'; g.textAlign = 'center'; g.textBaseline = 'middle';
    pos.forEach((p, i) => {
      const a = angles[i] - Math.PI / 2, r = s * 0.37;
      const fs = fitText(g, p, s * 0.34, s * (pos.length > 3 ? 0.10 : 0.12), 700);
      g.font = `700 ${fs}px ${FONT}`;
      g.fillText(p, Math.cos(a) * r, Math.sin(a) * r);
      g.strokeStyle = '#f4f2ea'; g.lineWidth = s * 0.012;
      g.beginPath(); g.moveTo(Math.cos(a) * s * 0.20, Math.sin(a) * s * 0.20); g.lineTo(Math.cos(a) * s * 0.25, Math.sin(a) * s * 0.25); g.stroke();
    });
    g.restore();
  }
  function selAngles(n) {
    if (n === 2) return [-Math.PI / 4, Math.PI / 4];
    if (n === 3) return [-Math.PI / 4, 0, Math.PI / 4];
    return [-Math.PI * 0.375, -Math.PI * 0.125, Math.PI * 0.125, Math.PI * 0.375];
  }

  /* ---------- door base texture (paint, wear, section mimic boxes) */
  function drawDoor(cab, ppm, seed) {
    const W = DOOR.w * ppm / 1000, H = DOOR.h * ppm / 1000, k = ppm / 1000;
    const c = cv(W, H), g = c.getContext('2d');
    const R = rng(seed);
    // ANSI 61 gray powder coat
    g.fillStyle = '#a3a8a5'; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 26000; i++) { const v = R(); g.fillStyle = v < 0.5 ? `rgba(255,255,255,${(R() * 0.05).toFixed(3)})` : `rgba(0,0,0,${(R() * 0.05).toFixed(3)})`; g.fillRect(R() * W, R() * H, 1.2, 1.2); }
    // soft light falloff, grime low down and around the handle
    let gr = g.createLinearGradient(0, 0, 0, H);
    gr.addColorStop(0, 'rgba(255,255,255,0.10)'); gr.addColorStop(0.35, 'rgba(255,255,255,0)'); gr.addColorStop(0.8, 'rgba(40,36,28,0.05)'); gr.addColorStop(1, 'rgba(40,36,28,0.20)');
    g.fillStyle = gr; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 14; i++) {
      const x = R() * W, y = R() * H, r = (30 + R() * 140) * k;
      const b = g.createRadialGradient(x, y, 0, x, y, r); b.addColorStop(0, 'rgba(70,62,46,0.06)'); b.addColorStop(1, 'rgba(70,62,46,0)');
      g.fillStyle = b; g.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    // section boxes: thin engraved-looking outlines
    for (const it of cab.items) {
      if (it.t !== 'section') continue;
      const x = (it.x - it.w / 2) * k, y = it.y * k, w = it.w * k, h = it.h * k;
      g.strokeStyle = 'rgba(30,32,30,0.45)'; g.lineWidth = Math.max(1, 1.6 * k);
      rrect(g, x, y, w, h, 6 * k); g.stroke();
      g.strokeStyle = 'rgba(255,255,255,0.22)'; g.lineWidth = Math.max(1, 1 * k);
      rrect(g, x + 1.5 * k, y + 1.5 * k, w, h, 6 * k); g.stroke();
    }
    // grime where hands go: around every operable device
    for (const it of cab.items) {
      if (!['sel', 'pb', 'rl', 'cs', 'estop', 'lockout'].includes(it.t)) continue;
      const x = it.x * k, y = it.y * k, r = (it.t === 'cs' ? 70 : 45) * k;
      const b = g.createRadialGradient(x + 6 * k, y + 10 * k, 0, x, y, r);
      b.addColorStop(0, `rgba(66,56,40,${(0.10 + R() * 0.10).toFixed(3)})`); b.addColorStop(1, 'rgba(66,56,40,0)');
      g.fillStyle = b; g.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    // ventilation louvres near the bottom
    for (let i = 0; i < 2; i++) {
      const lx = (i === 0 ? 120 : 760) * k, ly = 1560 * k;
      for (let j = 0; j < 9; j++) {
        const yy = ly + j * 26 * k;
        g.fillStyle = 'rgba(20,20,18,0.55)'; rrect(g, lx, yy, 260 * k, 9 * k, 4 * k); g.fill();
        g.fillStyle = 'rgba(255,255,255,0.25)'; g.fillRect(lx + 4 * k, yy + 9 * k, 252 * k, 1.2 * k);
      }
    }
    // door edge seam and fasteners
    g.strokeStyle = 'rgba(20,20,18,0.6)'; g.lineWidth = 3 * k; g.strokeRect(1.5 * k, 1.5 * k, W - 3 * k, H - 3 * k);
    // scratches near the handle
    g.strokeStyle = 'rgba(255,255,250,0.35)'; g.lineWidth = 0.8;
    for (let i = 0; i < 16; i++) { const x = W - (30 + R() * 110) * k, y = (820 + R() * 300) * k; g.beginPath(); g.moveTo(x, y); g.lineTo(x + (R() - 0.5) * 50 * k, y + (R() - 0.3) * 18 * k); g.stroke(); }
    return c;
  }

  /* ---------- 5x7 dot-matrix font (columns, LSB at top) */
  const F57 = [0x00,0x00,0x00,0x00,0x00, 0x00,0x00,0x5F,0x00,0x00, 0x00,0x07,0x00,0x07,0x00, 0x14,0x7F,0x14,0x7F,0x14, 0x24,0x2A,0x7F,0x2A,0x12, 0x23,0x13,0x08,0x64,0x62, 0x36,0x49,0x56,0x20,0x50, 0x00,0x05,0x03,0x00,0x00,
    0x00,0x1C,0x22,0x41,0x00, 0x00,0x41,0x22,0x1C,0x00, 0x2A,0x1C,0x7F,0x1C,0x2A, 0x08,0x08,0x3E,0x08,0x08, 0x00,0x50,0x30,0x00,0x00, 0x08,0x08,0x08,0x08,0x08, 0x00,0x60,0x60,0x00,0x00, 0x20,0x10,0x08,0x04,0x02,
    0x3E,0x51,0x49,0x45,0x3E, 0x00,0x42,0x7F,0x40,0x00, 0x42,0x61,0x51,0x49,0x46, 0x21,0x41,0x45,0x4B,0x31, 0x18,0x14,0x12,0x7F,0x10, 0x27,0x45,0x45,0x45,0x39, 0x3C,0x4A,0x49,0x49,0x30, 0x01,0x71,0x09,0x05,0x03,
    0x36,0x49,0x49,0x49,0x36, 0x06,0x49,0x49,0x29,0x1E, 0x00,0x36,0x36,0x00,0x00, 0x00,0x56,0x36,0x00,0x00, 0x08,0x14,0x22,0x41,0x00, 0x14,0x14,0x14,0x14,0x14, 0x00,0x41,0x22,0x14,0x08, 0x02,0x01,0x51,0x09,0x06,
    0x32,0x49,0x79,0x41,0x3E, 0x7E,0x11,0x11,0x11,0x7E, 0x7F,0x49,0x49,0x49,0x36, 0x3E,0x41,0x41,0x41,0x22, 0x7F,0x41,0x41,0x22,0x1C, 0x7F,0x49,0x49,0x49,0x41, 0x7F,0x09,0x09,0x09,0x01, 0x3E,0x41,0x49,0x49,0x7A,
    0x7F,0x08,0x08,0x08,0x7F, 0x00,0x41,0x7F,0x41,0x00, 0x20,0x40,0x41,0x3F,0x01, 0x7F,0x08,0x14,0x22,0x41, 0x7F,0x40,0x40,0x40,0x40, 0x7F,0x02,0x0C,0x02,0x7F, 0x7F,0x04,0x08,0x10,0x7F, 0x3E,0x41,0x41,0x41,0x3E,
    0x7F,0x09,0x09,0x09,0x06, 0x3E,0x41,0x51,0x21,0x5E, 0x7F,0x09,0x19,0x29,0x46, 0x46,0x49,0x49,0x49,0x31, 0x01,0x01,0x7F,0x01,0x01, 0x3F,0x40,0x40,0x40,0x3F, 0x1F,0x20,0x40,0x20,0x1F, 0x3F,0x40,0x38,0x40,0x3F,
    0x63,0x14,0x08,0x14,0x63, 0x07,0x08,0x70,0x08,0x07, 0x61,0x51,0x49,0x45,0x43, 0x00,0x7F,0x41,0x41,0x00, 0x02,0x04,0x08,0x10,0x20, 0x00,0x41,0x41,0x7F,0x00, 0x04,0x02,0x01,0x02,0x04, 0x40,0x40,0x40,0x40,0x40];
  const GLYPH_EXTRA = { '°': [0x00, 0x06, 0x09, 0x09, 0x06], '►': [0x7F, 0x3E, 0x1C, 0x08, 0x00], '◄': [0x00, 0x08, 0x1C, 0x3E, 0x7F], '▲': [0x20, 0x30, 0x38, 0x30, 0x20], '▼': [0x02, 0x06, 0x0E, 0x06, 0x02] };
  function glyph(ch) {
    if (GLYPH_EXTRA[ch]) return GLYPH_EXTRA[ch];
    let c = ch.toUpperCase().charCodeAt(0);
    if (c < 32 || c > 95) c = 32;
    const o = (c - 32) * 5; return F57.slice(o, o + 5);
  }
  // draws a cols x rows character matrix display (VFD or LCD) into g
  function drawMatrix(g, w, h, lines, cols, rows, kind) {
    const vfd = kind === 'vfd';
    g.fillStyle = vfd ? '#05110f' : '#8f9a78'; g.fillRect(0, 0, w, h);
    const padX = w * 0.04, padY = h * 0.1;
    const cw = (w - 2 * padX) / cols, ch = (h - 2 * padY) / rows;
    const dot = Math.min(cw / 6, ch / 8.4);
    const on = vfd ? '#6ff2d6' : '#1d2414', off = vfd ? 'rgba(80,200,180,0.06)' : 'rgba(30,40,20,0.08)';
    if (vfd) { g.shadowColor = 'rgba(90,255,220,0.65)'; g.shadowBlur = dot * 1.4; }
    for (let r = 0; r < rows; r++) {
      const line = (lines[r] || '').padEnd(cols);
      for (let c = 0; c < cols; c++) {
        const gl = glyph(line[c]);
        const x0 = padX + c * cw + (cw - dot * 5.6) / 2, y0 = padY + r * ch + (ch - dot * 7.6) / 2;
        for (let gx = 0; gx < 5; gx++) for (let gy = 0; gy < 7; gy++) {
          const lit = (gl[gx] >> gy) & 1;
          g.fillStyle = lit ? on : off;
          g.fillRect(x0 + gx * dot * 1.12, y0 + gy * dot * 1.08, dot * 0.92, dot * 0.92);
        }
      }
    }
    g.shadowBlur = 0;
    if (!vfd) { const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, 'rgba(255,255,255,0.10)'); gr.addColorStop(1, 'rgba(0,0,0,0.12)'); g.fillStyle = gr; g.fillRect(0, 0, w, h); }
  }
  /* ---------- seven-segment LED */
  const SEG = { '0': 0x3F, '1': 0x06, '2': 0x5B, '3': 0x4F, '4': 0x66, '5': 0x6D, '6': 0x7D, '7': 0x07, '8': 0x7F, '9': 0x6F, '-': 0x40, ' ': 0, 'E': 0x79, 'r': 0x50, 'o': 0x5C };
  function draw7(g, w, h, text, digits) {
    g.fillStyle = '#140504'; g.fillRect(0, 0, w, h);
    const dw = w / digits, sx = dw * 0.18, sy = h * 0.14, L = dw * 0.56, T = Math.max(1.5, dw * 0.1), H2 = (h - 2 * sy) / 2;
    const segs = (cx, mask) => {
      const pts = [[cx + T, sy, L, T], [cx + L + T, sy + T, T, H2 - T], [cx + L + T, sy + H2 + T, T, H2 - T], [cx + T, sy + 2 * H2, L, T], [cx, sy + H2 + T, T, H2 - T], [cx, sy + T, T, H2 - T], [cx + T, sy + H2, L, T]];
      pts.forEach((p, i) => { g.fillStyle = (mask >> i) & 1 ? '#ff3a1c' : 'rgba(255,60,30,0.07)'; g.save(); g.translate(p[0] + p[2] / 2, p[1] + p[3] / 2); g.transform(1, 0, -0.08, 1, 0, 0); g.fillRect(-p[2] / 2, -p[3] / 2, p[2], p[3]); g.restore(); });
    };
    g.shadowColor = 'rgba(255,60,20,0.8)'; g.shadowBlur = T * 1.5;
    const t = String(text).padStart(digits).slice(-digits);
    for (let i = 0; i < digits; i++) segs(i * dw + sx, SEG[t[i]] ?? 0);
    g.shadowBlur = 0;
  }

  /* ---------- annunciator face (redrawn when state changes) */
  function drawAnn(g, w, h, it, test) {
    const cols = it.cols, rows = it.rows, cw = w / cols, ch = h / rows;
    g.fillStyle = '#0d0d0d'; g.fillRect(0, 0, w, h);
    const fast = (performance.now() / 1000 * 3.2) % 1 < 0.5, slow = (performance.now() / 1000 * 0.9) % 1 < 0.5;
    P.ANN.forEach((a, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      const x = c * cw + cw * 0.05, y = r * ch + ch * 0.07, ww = cw * 0.9, hh = ch * 0.86;
      const lit = test || a.st === 'ack' || (a.st === 'alarm' && fast) || (a.st === 'alarmRTN' && fast) || (a.st === 'ring' && slow);
      const trip = r === 0 || i === 8;
      const lensOff = trip ? '#2c1513' : '#2e2d29', lensOn = trip ? '#ff5b46' : '#fff4d8';
      const gr = g.createLinearGradient(x, y, x, y + hh);
      gr.addColorStop(0, lit ? lensOn : lensOff); gr.addColorStop(1, lit ? (trip ? '#e8402c' : '#f6e3b6') : (trip ? '#241110' : '#262522'));
      g.fillStyle = gr; g.fillRect(x, y, ww, hh);
      g.fillStyle = lit ? 'rgba(20,10,5,0.92)' : (trip ? 'rgba(255,190,180,0.42)' : 'rgba(255,250,235,0.40)');
      g.textAlign = 'center'; g.textBaseline = 'middle';
      const lines = a.label.split('\n');
      lines.forEach((l, k) => {
        const s = fitText(g, l, ww * 0.9, hh * 0.24, 700);
        g.font = `700 ${s}px ${FONT}`;
        g.fillText(l, x + ww / 2, y + hh / 2 + (k - (lines.length - 1) / 2) * hh * 0.30);
      });
      if (!lit) { g.fillStyle = 'rgba(255,255,255,0.05)'; g.fillRect(x, y, ww, hh * 0.25); }
    });
  }

  /* ---------- PLC rack seen through the door window */
  const PLC_IO = [
    ['DI', 'DIGITAL IN 1', () => [S.cb, !S.cb, S.tiv > 0.995, S.tiv < 0.005, S.byp > 0.98, S.byp < 0.02, S.y < 0.02, S.brake > 0.5, S.brake < 0.05, S.hg > 0.995, S.hg < 0.005, S.w > 0.01, S.w > 0.3, S.w > 0.9, S.w > 0.95, S.w > 1.15]],
    ['DI', 'DIGITAL IN 2', () => [S.opuP > 285, S.opuP > 250, S.opuP < 220, S.liftP > 1800, S.cwFlow > 40, S.airP > 80, S.p1Run, S.p2Run, S.cwRun, S.liftRun, S.estop, S.lock86G, S.lock86M, S.excOn && S.Vt > 0.9, S.syncOK, sw.unitMode === 'AUTO']],
    ['DO', 'DIGITAL OUT 1', () => [S.req.cw, S.req.lift, S.req.brake, S.tivCmd > 0, S.tivCmd < 0, S.bypCmd > 0, S.bypCmd < 0, S.govEn, S.esd, S.excOn, S.cbClosing > 0, S.cbTripping > 0, S.autoSync, P.horn, S.sgRun[0] > 0, S.sgRun[0] < 0]],
    ['DO', 'DIGITAL OUT 2', () => [S.sgRun[1] > 0, S.sgRun[1] < 0, S.hgCmd > 0, S.hgCmd < 0, S.dtAir > 0.5, S.heater, S.sumpRun[0], S.sumpRun[1], S.backwash > 0, S.rakeRun, S.airAdd > 0, S.lvlActive, false, false, false, S.seq !== 'STOPPED']],
    ['AI', 'ANALOG IN 8CH', () => [1, 1, 1, 1, 1, 1, 1, 1]],
    ['AO', 'ANALOG OUT 4CH', () => [1, 1, 1, 1]],
  ];
  function drawPLC(g, w, h) {
    g.fillStyle = '#5f6466'; g.fillRect(0, 0, w, h);
    // back panel, wireway, terminal strips
    g.fillStyle = '#e8e6df'; g.fillRect(w * 0.02, h * 0.06, w * 0.96, h * 0.09); g.fillRect(w * 0.02, h * 0.83, w * 0.96, h * 0.12);
    g.fillStyle = 'rgba(0,0,0,0.25)'; for (let x = w * 0.03; x < w * 0.97; x += w * 0.012) { g.fillRect(x, h * 0.06, w * 0.004, h * 0.09); g.fillRect(x, h * 0.83, w * 0.004, h * 0.12); }
    const x0 = w * 0.05, y0 = h * 0.18, rh = h * 0.6;
    g.fillStyle = '#2b2d2f'; g.fillRect(x0 - 4, y0 - 4, w * 0.90 + 8, rh + 8);
    const slots = 8, sw2 = w * 0.90 / slots;
    const t = performance.now() / 1000;
    for (let i = 0; i < slots; i++) {
      const x = x0 + i * sw2 + 2, ww = sw2 - 4;
      g.fillStyle = i === 0 ? '#3a3d40' : '#3d4144'; g.fillRect(x, y0, ww, rh);
      g.fillStyle = 'rgba(255,255,255,0.08)'; g.fillRect(x, y0, ww, 3);
      g.fillStyle = '#d8d6cd'; g.font = `600 ${ww * 0.13}px ${FONT}`; g.textAlign = 'center';
      if (i === 0) {
        g.fillText('POWER', x + ww / 2, y0 + rh * 0.08);
        led(g, x + ww * 0.5, y0 + rh * 0.18, ww * 0.07, S.dcV > 100, '#3cff5a');
        g.fillStyle = '#222'; g.fillRect(x + ww * 0.15, y0 + rh * 0.55, ww * 0.7, rh * 0.3);
      } else if (i === 1) {
        g.fillText('CPU', x + ww / 2, y0 + rh * 0.08);
        const labs = [['RUN', S.dcV > 100 && !S.plcFault, '#3cff5a'], ['FLT', S.plcFault, '#ff3b2a'], ['BATT', false, '#ff3b2a'], ['FORCE', false, '#ffb21c'], ['COMM', (t * 7) % 1 < 0.4, '#3cff5a']];
        labs.forEach(([l, on, c], k) => { led(g, x + ww * 0.25, y0 + rh * (0.18 + k * 0.08), ww * 0.06, on, c); g.fillStyle = '#d8d6cd'; g.textAlign = 'left'; g.font = `600 ${ww * 0.11}px ${FONT}`; g.fillText(l, x + ww * 0.38, y0 + rh * (0.18 + k * 0.08) + ww * 0.04); });
        g.fillStyle = '#151515'; g.fillRect(x + ww * 0.2, y0 + rh * 0.65, ww * 0.6, rh * 0.12);
        g.fillStyle = '#d8d6cd'; g.font = `600 ${ww * 0.09}px ${FONT}`; g.textAlign = 'center'; g.fillText('RUN  REM  PROG', x + ww / 2, y0 + rh * 0.85);
      } else {
        const io = PLC_IO[i - 2];
        g.fillText(io[0], x + ww / 2, y0 + rh * 0.07);
        const bits = io[2]();
        const n = bits.length;
        for (let k = 0; k < n; k++) {
          const col = n > 8 ? Math.floor(k / 8) : 0, row = n > 8 ? k % 8 : k;
          const lx = x + ww * (n > 8 ? (col ? 0.68 : 0.32) : 0.5), ly = y0 + rh * (0.15 + row * 0.055);
          led(g, lx, ly, ww * 0.055, io[0] === 'DI' || io[0] === 'DO' ? !!bits[k] : false, io[0] === 'DO' ? '#ff9a1c' : '#ff3b2a');
          if (io[0] === 'DI' || io[0] === 'DO') { g.fillStyle = '#b9b7b0'; g.font = `500 ${ww * 0.08}px ${FONT}`; g.textAlign = 'center'; g.fillText(String(k), lx + (col ? ww * 0.13 : -ww * 0.13), ly + ww * 0.03); }
        }
        if (io[0] === 'AI' || io[0] === 'AO') led(g, x + ww * 0.5, y0 + rh * 0.15, ww * 0.06, true, '#3cff5a');
        // terminal block with coloured wires leaving downwards
        g.fillStyle = '#26292b'; g.fillRect(x + ww * 0.1, y0 + rh * 0.62, ww * 0.8, rh * 0.34);
        for (let k = 0; k < 8; k++) { g.fillStyle = ['#e33', '#ddd', '#39f', '#ddd', '#e33', '#fc3', '#ddd', '#39f'][k]; g.fillRect(x + ww * (0.16 + k * 0.09), y0 + rh * 0.95, ww * 0.03, h * 0.10); }
      }
    }
  }
  function led(g, x, y, r, on, color) {
    g.fillStyle = on ? color : 'rgba(40,20,15,0.85)';
    if (on) { g.shadowColor = color; g.shadowBlur = r * 3; }
    g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); g.shadowBlur = 0;
    if (!on) { g.fillStyle = 'rgba(255,255,255,0.12)'; g.beginPath(); g.arc(x - r * 0.3, y - r * 0.3, r * 0.4, 0, 7); g.fill(); }
  }

  /* ---------- generator protection relay front (LCD + target LEDs) */
  const GPR_T = [['24', 'V/Hz'], ['27', 'UNDERVOLT'], ['59', 'OVERVOLT'], ['81O', 'OVER FREQ'], ['81U', 'UNDER FREQ'], ['32', 'REV POWER'], ['40', 'LOSS FIELD'], ['51V', 'OVERCURR'], ['50', 'INST OC'], ['87G', 'DIFF'], ['64G', 'STATOR GND'], ['78', 'OUT OF STEP']];
  function gprText() {
    const trips = Object.keys(S.targets);
    if (trips.length) return ['TRIP TARGETS:   ', trips.join(' ').slice(0, 16).padEnd(16)];
    const k = Math.floor(performance.now() / 3000) % 3;
    if (k === 0) return [`V ${f0(S.Vt * 480).padStart(3)}V  F ${f2(S.fHz).padStart(5)}`, `I ${f0(S.I * P.NP.I).padStart(3)}A  P ${f0(S.Pkw).padStart(4)}K`];
    if (k === 1) return [`Q ${f0(S.Qkvar).padStart(4)}KVAR     `, `Z ${S.I > 0.05 ? f2(Math.hypot(S.zr, S.zx)) : '----'} PU      `];
    return ['RELAY OK  52G ' + (S.cb ? 'CL' : 'OP'), `SLIP ${(S.slipHz).toFixed(2).padStart(6)} HZ  `];
  }
  function drawGPR(g, w, h, lcdLines) {
    g.fillStyle = '#26292c'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#33373b'; g.fillRect(w * 0.02, h * 0.03, w * 0.96, h * 0.94);
    g.fillStyle = '#d8d6cd'; g.font = `700 ${h * 0.065}px ${FONT}`; g.textAlign = 'left'; g.textBaseline = 'middle';
    g.fillText('GENERATOR PROTECTION', w * 0.06, h * 0.1);
    g.font = `500 ${h * 0.05}px ${FONT}`; g.fillStyle = '#9da1a3'; g.fillText('MULTIFUNCTION  24 27 32 40 50/51V 59 64G 78 81 87G', w * 0.06, h * 0.18);
    // LCD
    const lx = w * 0.06, ly = h * 0.25, lw = w * 0.52, lh = h * 0.26;
    const sub = cv(lw, lh); drawMatrix(sub.getContext('2d'), lw, lh, lcdLines, 16, 2, 'lcd'); g.drawImage(sub, lx, ly);
    // target LEDs
    GPR_T.forEach(([id, name], i) => {
      const col = Math.floor(i / 6), row = i % 6;
      const x = w * (0.64 + col * 0.18), y = h * (0.26 + row * 0.085);
      led(g, x, y, h * 0.018, !!S.targets[id], '#ff3b2a');
      g.fillStyle = '#d8d6cd'; g.font = `600 ${h * 0.042}px ${FONT}`; g.textAlign = 'left';
      g.fillText(`${id} ${name}`, x + h * 0.03, y);
    });
    led(g, w * 0.08, h * 0.62, h * 0.02, true, '#3cff5a'); g.fillStyle = '#d8d6cd'; g.font = `600 ${h * 0.045}px ${FONT}`; g.fillText('RELAY OK', w * 0.11, h * 0.62);
    led(g, w * 0.28, h * 0.62, h * 0.02, Object.keys(S.targets).length > 0, '#ff3b2a'); g.fillText('TRIP', w * 0.31, h * 0.62);
  }

  /* ---------- masking-tape note */
  function drawTape(g, x, y, w, h, text, seed) {
    const R = rng(seed);
    g.save(); g.translate(x, y);
    g.fillStyle = '#e4d6a8'; g.beginPath(); g.moveTo(0, 2); for (let i = 0; i <= 10; i++) g.lineTo(w * i / 10, (R() - 0.5) * 3); for (let i = 10; i >= 0; i--) g.lineTo(w * i / 10 + (R() - 0.5) * 2, h + (R() - 0.5) * 3); g.closePath(); g.fill();
    g.fillStyle = 'rgba(120,100,60,0.12)'; for (let i = 0; i < 60; i++) g.fillRect(R() * w, R() * h, 2, 2);
    g.fillStyle = '#16233f'; g.textAlign = 'center'; g.textBaseline = 'middle';
    const lines = text.split('\n');
    lines.forEach((l, i) => { const s = fitText(g, l, w * 0.9, h / (lines.length + 0.6), 400, MARK); g.font = `400 ${s}px ${MARK}`; g.fillText(l, w / 2, h / 2 + (i - (lines.length - 1) / 2) * s * 1.12); });
    g.restore();
  }
  /* ---------- warning label */
  function drawWarn(g, x, y, w, h) {
    g.save(); g.translate(x, y);
    g.fillStyle = '#f2efe6'; rrect(g, 0, 0, w, h, h * 0.05); g.fill();
    g.fillStyle = '#c8102e'; rrect(g, w * 0.03, h * 0.05, w * 0.94, h * 0.30, h * 0.03); g.fill();
    g.fillStyle = '#fff'; g.font = `800 ${h * 0.2}px ${FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('⚠ DANGER', w / 2, h * 0.21);
    g.fillStyle = '#141414'; g.font = `700 ${h * 0.13}px ${FONT}`;
    g.fillText('HAZARDOUS VOLTAGE', w / 2, h * 0.50);
    g.font = `600 ${h * 0.095}px ${FONT}`;
    g.fillText('480 VAC  ·  125 VDC INSIDE', w / 2, h * 0.67);
    g.fillText('DE-ENERGIZE BEFORE OPENING', w / 2, h * 0.82);
    g.restore();
  }

  return {
    DOOR, CABS, FONT, OIT, oitText, oitKey, RTD, GPR_T, gprText, PLC_IO,
    cv, rng, rrect, Atlas, drawPlate, drawDial, drawEdge, drawSyncFace, drawEscutcheon, selAngles, drawDoor,
    drawMatrix, draw7, drawAnn, drawPLC, drawGPR, drawTape, drawWarn, meterAngle, edgeFrac, blink, onOff,
  };
})();
