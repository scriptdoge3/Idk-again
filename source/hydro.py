"""
Sable Creek Unit 1 for Half-Life 2: the plant as four tick programs of logic entities (see srclogic.py):
fast (0.03 s), medium (0.12 s), slow (0.24 s) and the annunciator (0.24 s).

The controls (nameplates as engraved; the variable names inside are the GoldSrc map's):
  CP-1  25 SYNC, 52G GEN BKR, 41 FIELD BKR, 86U LOCKOUT switches; WICKET GATE LOWER / RAISE dials
        (spring-return), BRAKES dial, FIRING ANGLE knob
  CP-2  GOV MODE and AVR MODE switches (MAN / AUTO; plc, avr inside); ACK, RESET, TEST
  CP-3  LUBE OIL PUMP, CW PUMP (OFF / ON), HPU PUMP, AIR COMP (OFF / AUTO)
  SP-1  GATE MODE dial (AUTO / MAN), spill GATE LOWER / RAISE dials

Units: speed n, gate g, volts v and field x in % (100 % = 100 rpm, 480 V, rated field); hydraulic oil hp
and brake air in psi; bearing temperature bt in deg C; river depth l in m at the intake; river flow q in %
of full-gate discharge (90 cfs); spill gate opening sg in m; phase th in degrees.
"""
import math
from srclogic import (Map, Program, C, aff, clamp, relu, step, below, OR, NOT, sel, pwl, gate, sq, sin_deg, cos_deg, reset, absx)

# --------------------------------------------------------------- the machine
# Per-unit model (1 pu speed = 100 rpm, 1 pu power = PBASE kW, torque in pu of rated torque).
PBASE = 340.0          # kW per pu: full gate at rated head gives about 245 kW
H2 = 6.0               # mechanical starting time 2H, s (runner, shaft and 72-pole rotor)
TW = 0.4               # water starting time, s: an open-flume unit has no penstock, only the flume and draft tube
XS = 0.5               # reactance between the internal EMF and the grid, pu
XT = 0.06              # step-up transformer reactance: the terminal volts rise with the vars
DSW = 0.27             # damper winding damping on line, pu torque per % slip
GOV_KP, GOV_KI, GOV_KD = 1.5, 0.3, 1.0   # PLC governor PID: % gate per % speed error, per % s, per %/s
FL = 0.02              # trash rack, flume and draft tube head loss at full flow, pu
HEAD0 = 12.19          # rated head, 40 ft (12.19 m) at 7.0 m river depth; the tailwater is 5.19 m below the intake bed

# Francis runner: torque = A(g) h - B(g) sqrt(h) w (falls linearly with speed), friction and windage
# Tf = 0.005 + 0.08 w^2. A is the stall torque (1.8 pu at full gate); B is set so that off line, with no
# load, the runner settles where the GoldSrc map's curve put it: speed-no-load at 15 % gate, runaway
# 160 % at full gate.
N_EQ = [(0, 0), (2, 0.05), (5, 0.3), (10, 0.7), (15, 1.0), (20, 1.2), (25, 1.32), (30, 1.4), (100, 1.6)]
_neq = lambda g: next(n0 + (n1 - n0) * (g - g0) / (g1 - g0) for (g0, n0), (g1, n1) in zip(N_EQ, N_EQ[1:]) if g0 <= g <= g1)
TF = lambda w: 0.005 + 0.08 * w * w
STALL = lambda g: 1.8 * g / 100
B_PTS = [(0, 0)] + [(g, round((STALL(g) - TF(_neq(g))) / _neq(g), 4)) for g in (2, 5, 15, 30, 100)]
# generator open-circuit curve: volts (%) at rated speed for each % of field current (2 % residual)
OCC_PTS = [(0, 2), (80, 85), (100, 100), (140, 117)]
# static exciter: field (% of rated) for each firing-angle knob position, 140 % at 0 deg (the ceiling)
KNOB_PTS = [(k / 4, round(140 * math.sin(math.radians(22.5 * k)), 2)) for k in range(5)]
KNOB0 = math.degrees(math.asin(100 / 140)) / 90           # knob position for rated no-load field
ATAN_PTS = [(-2.0, -63.4), (-0.7, -35), (0, 0), (0.7, 35), (2.0, 63.4)]
# shaft vibration (mils p-p) on line for each gate %: the draft-tube vortex rope rough zone around 25-50 %
VIB_PTS = [(0, 1), (15, 3), (27, 8), (45, 6), (60, 2)]
DT_FAST, DT_MED, DT_SLOW = 0.03, 0.12, 0.24

ANN_WINDOWS = [
    ('ovsp', '12 OVERSPEED|TRIP', 'trip'), ('lock', '86U LOCKOUT|TRIP', 'trip'), ('gbkr', '52G|TRIP', 'trip'),
    ('oop', '52G OOP|CLOSE', 'trip'), ('rp', '32 REV PWR|TRIP', 'trip'),
    ('lof', '40 LOF|TRIP', 'trip'), ('ov', '59 OV|TRIP', 'trip'), ('bthh', '38 BRG TEMP|HH TRIP', 'trip'),
    ('bth', '38 BRG TEMP|HI', 'alarm'), ('vib', '39 VIB|HI', 'alarm'),
    ('hyd', 'HPU PRESS|LO', 'alarm'), ('oilp', 'LUBE OIL|PRESS LO', 'alarm'), ('watp', 'CW FLOW|LO', 'alarm'),
    ('air', 'BRAKE AIR|PRESS LO', 'alarm'), ('brk', 'BRAKES|APPLIED', 'status'),
    ('rhi', 'HW LEVEL|HI', 'alarm'), ('rlo', 'HW LEVEL|LO', 'alarm'), ('spill', 'SPILL GATE|OPEN', 'status'),
    ('plc', 'GOV|IN MAN', 'status'), ('avr', 'AVR|IN MAN', 'status')]

INIT = dict(n=0, g=0, v=0, x=0, hp=0, air=0, bt=24, l=7, q=75, sg=0.75)


def build():
    reset()
    m = Map()
    F = Program(m, 'f', DT_FAST)          # fast: gate travel, runner, rotor, synchronizing, 52G
    M = Program(m, 'm', DT_MED)           # medium: gate commands, governor, excitation, protection, brakes
    S = Program(m, 's', DT_SLOW)          # slow: river, spillway, auxiliaries, bearings, sound levels
    A = Program(m, 'a', DT_SLOW)          # annunciator
    # fast ticks fall on odd server ticks, medium ones on 6 mod 8, slow and annunciator ones on 0 mod 8,
    # half a period apart: no two loops ever share a tick
    F.start_delay, M.start_delay, S.start_delay, A.start_delay = 0.1, 0.115, 0.145, 0.265
    dev = {'needles': {}, 'switches': {}, 'dials': {}, 'lamps': {}, 'windows': [], 'sounds': {}, 'scope': None}
    df, dm, ds = DT_FAST, DT_MED, DT_SLOW

    # ---------------------------------------------------------- devices
    def sound(name, wav, vol, loop=True, radius=600):
        e = m.ent('ambient_generic', name, message=wav, health=vol, pitch=100, pitchstart=100, radius=radius,
                  spawnflags=16 | (0 if loop else 32))
        dev['sounds'][name] = e
        return e

    def armed_relay(name):
        """sounds the logic starts go through a relay that is enabled 1 s after the map starts, so the first
        tick (which sets every flag) stays quiet"""
        return m.ent('logic_relay', name, spawnflags=2, StartDisabled=1)

    def switch(P, name, var, label, pos, grip='black', speed=240, kind='cs'):
        """maintained switch, two positions 90 degrees apart: OUT = pos[0] (left), IN = pos[1] (right).
        The handle's position is the variable (of program P)."""
        e = m.ent('func_rot_button', name, distance=90, speed=speed, spawnflags=32 + 1024 + 128, sounds=0, wait=-1)
        v = P.flag(var)
        e.out('OnIn', v.ent, 'SetValue', 1)
        e.out('OnOut', v.ent, 'SetValue', 0)
        e.out('OnPressed', 's_click', 'PlaySound')
        dev['switches'][name] = {'ent': e, 'label': label, 'pos': pos, 'grip': grip, 'kind': kind}
        return v

    def breaker_switch(P, name, label, pos=('TRIP', 'CLOSE'), grip='black'):
        """Breaker-type control switch, spring return: the handle hangs at normal; turned right (pos[1]) or
        left (pos[0]) it sends a pulse and springs back. It is two buttons, one each way, on the two halves of
        the plate; the left one is parented to the right one, so the one handle shows both. The state lives in
        the logic and shows on the target flag. Returns the right and left pulses (one tick each)."""
        rt = m.ent('func_rot_button', f'{name}_r', distance=45, speed=600, spawnflags=1024 + 128, sounds=0, wait=0.35)
        lt = m.ent('func_rot_button', f'{name}_l', distance=45, speed=600, spawnflags=1024 + 128 + 2, sounds=0, wait=0.35,
                   parentname=f'{name}_r')
        vr, vl = P.var(f'{name}_rp', 0, 0, 1), P.var(f'{name}_lp', 0, 0, 1)
        rt.out('OnIn', vr.ent, 'SetValue', 1); lt.out('OnIn', vl.ent, 'SetValue', 1)
        for e in (rt, lt):
            e.out('OnPressed', 's_click', 'PlaySound')
        P.add(vr, -vr.r); P.add(vl, -vl.r)
        dev['switches'][name] = {'ents': (lt, rt), 'label': label, 'pos': pos, 'grip': grip, 'kind': 'breaker'}
        return vr, vl

    def held(P, var, on, off):
        """the state a spring-return switch sets: on with its right pulse, off with its left"""
        f = P.flag(var)
        P.set(f, OR(on.r, f.r * NOT(off.r)))
        return f

    def target(flag, name):
        """the switch's target flag: red (skin 0) while the flag is on, green (skin 1) while off"""
        flag.on_rise(f'{name}_flag', 'Skin', 0).on_fall(f'{name}_flag', 'Skin', 1)

    def dial(P, name, var, label, spring=True, start=0.0):
        """momentary_rot_button: its position (0..1) is the variable. Spring-return dials turn to their stop
        while held and spring back when let go."""
        e = m.ent('momentary_rot_button', name, distance=60 if spring else 300, speed=240 if spring else 30,
                  returnspeed=300 if spring else 0, spawnflags=1024 + 128, startposition=f'{start:.4f}', sounds=0)
        v = P.var(var, start, 0, 1)
        e.out('Position', v.ent, 'SetValue')
        dev['dials'][name] = {'ent': e, 'label': label, 'spring': spring}
        return v

    def needle(P, name, frac, imm=False, cond=None, speed=None):
        """meter needle: a momentary_rot_button set to the value (0..1; the button clamps it). Its speed is
        matched to how often its loop updates it, so it glides from one value to the next like a damped
        switchboard movement instead of jumping and waiting."""
        speed = speed or {'f': 300, 'm': 150, 's': 70}[P.name]
        e = m.ent('momentary_rot_button', name, distance=250, speed=speed, spawnflags=1 + 128, startposition=0)
        f = C(frac)
        if cond is not None:
            f = gate(clamp(f, 0, 1), cond, 0, 1)
        P.sink(e, 'SetPositionImmediately' if imm else 'SetPosition', f)
        dev['needles'][name] = e
        return e

    def lamp(name, flag, colors):
        """(lit colour when the flag is 1, lit colour when it is 0); None = dark"""
        on_c, off_c = colors
        e1 = m.ent('func_brush', f'{name}_1', StartDisabled=1, Solidity=1)
        flag.on_rise(e1, 'Enable'); flag.on_fall(e1, 'Disable')
        ents = [e1]
        if off_c:
            e0 = m.ent('func_brush', f'{name}_0', StartDisabled=0, Solidity=1)
            flag.on_rise(e0, 'Disable'); flag.on_fall(e0, 'Enable')
            ents.append(e0)
        dev['lamps'][name] = {'ents': ents, 'colors': colors}

    # ------------------------------------------------------------ sounds
    sound('s_turb', 'sablecreek/turbine.wav', 8)
    sound('s_water', 'sablecreek/water.wav', 6)
    sound('s_hum', 'sablecreek/hum.wav', 5)
    sound('s_horn', 'sablecreek/horn.wav', 7)
    sound('s_pump', 'sablecreek/pump.wav', 4)
    sound('s_comp', 'sablecreek/compressor.wav', 5)
    sound('s_brk', 'sablecreek/breaker.wav', 10, loop=False)
    sound('s_relay', 'sablecreek/relay.wav', 9, loop=False)
    sound('s_click', 'sablecreek/switch.wav', 8, loop=False, radius=300)

    # ------------------------------------------------------------ controls
    ss_on, ss_off = breaker_switch(F, 'r_ss', '25 SYNC', ('OFF', 'ON'))
    c52, t52 = breaker_switch(F, 'r_52', '52G GEN BKR')
    c41, t41 = breaker_switch(M, 'r_exc', '41 FIELD BKR')
    gt_trip, gt_rst = breaker_switch(M, 'r_gt', '86U LOCKOUT', ('RESET', 'TRIP'), grip='red')
    plc_a, plc_mn = breaker_switch(F, 'r_plc', 'GOV MODE', ('MAN', 'AUTO'))
    avr_a, avr_mn = breaker_switch(F, 'r_avr', 'AVR MODE', ('MAN', 'AUTO'))
    lube = held(S, 'lube', *breaker_switch(S, 'r_lp', 'LUBE OIL PUMP', ('STOP', 'START')))
    cool = held(S, 'cool', *breaker_switch(S, 'r_wp', 'CW PUMP', ('STOP', 'START')))
    hhp = held(S, 'hhp', *breaker_switch(S, 'r_hp', 'HPU PUMP', ('OFF', 'AUTO')))
    hac = held(S, 'hac', *breaker_switch(S, 'r_ac', 'AIR COMP', ('OFF', 'AUTO')))
    hss = held(F, 'hss', ss_on, ss_off)
    plc, avr = F.flag('plc'), F.flag('avr')         # GOV / AVR in AUTO (set below: a trip drops them to MAN)
    for f_, nm in ((hss, 'r_ss'), (plc, 'r_plc'), (avr, 'r_avr'), (lube, 'r_lp'), (cool, 'r_wp'), (hhp, 'r_hp'), (hac, 'r_ac')):
        target(f_, nm)
    hbr_m = switch(M, 'r_br', 'hbr', 'BRAKES', ('APPLY', 'RELEASE'), kind='sel')
    sman = switch(S, 'r_sp', 'sman', 'GATE MODE', ('AUTO', 'MAN'), kind='sel')
    kgl = dial(M, 'k_gl', 'kgl', 'LOWER')
    kgr = dial(M, 'k_gr', 'kgr', 'RAISE')
    ksl = dial(S, 'k_sl', 'ksl', 'LOWER')
    ksr = dial(S, 'k_sr', 'ksr', 'RAISE')
    kfa_m = dial(M, 'k_fa', 'kfa', 'FIRING ANGLE', spring=False, start=KNOB0)

    # ------------------------------------------------------------ state
    # fast
    n = F.var('n', 0, 0, 170)                       # speed, %
    g = F.var('g', 0, 0, 100)                       # wicket gate, %
    qf = F.var('qf', 0, 0, 2)                       # water column: flow through the turbine, pu of full-gate flow
    dl = F.var('dl', 0, -BIGT, BIGT, clamp=False)   # load angle on line, deg
    th = F.var('th', 0, -BIGT, BIGT, clamp=False)   # phase between the unit and the grid, deg
    pe = F.var('pe', 0, -5, 5, clamp=False)         # electrical power, pu
    qe = F.var('qe', 0, -5, 5, clamp=False)         # reactive power, pu
    cb = F.flag('cb')
    c_oop = F.flag('c_oop')                         # 52G closed out of phase
    # medium
    n_prev = M.var('n_prev', 0, 0, 170)             # the last medium tick's speed (the governor's derivative)
    v = M.var('v', 0, 0, 140)                       # generator volts, %
    x = M.var('x', 0, 0, 150)                       # field current, % of rated no-load field
    ui = M.var('ui', 100, 0, 140)                   # AVR integrator (field %)
    gi = M.var('gi', 0, 0, 100)                     # PLC governor integrator (gate %)
    grate = M.var('grate', 0, -200, 20)             # the gate's speed, %/s (the fast program moves it)
    exc = M.flag('exc'); tr = M.flag('tr'); brake = M.flag('brake')
    rp_t = M.var('rp_t', 0, 0, 20)
    gr_t = M.var('gr_t', 0, 0, 5); gl_t = M.var('gl_t', 0, 0, 5)       # how long a gate dial has been held
    # slow
    hp = S.var('hp', 0, 0, 320)
    odraw = S.var('odraw', 0, 0, 1000)              # oil drawn by the gate's travel since the last slow tick
    air = S.var('air', 0, 0, 130)
    bt = S.var('bt', INIT['bt'], 0, 130)
    lv = S.var('l', INIT['l'], 3, 9.5)
    q = S.var('q', INIT['q'], 60, 90)
    rup = S.flag('rup', 1)
    sg = S.var('sg', INIT['sg'], 0, 1.2)
    hpu = S.flag('hpu'); comp = S.flag('comp')     # hydraulic pump and air compressor running
    lp = S.var('lp', 0, 0, 60)                      # lube oil pressure, psi
    cw = S.var('cw', 0, 0, 100)                     # cooling water flow, gpm
    c_bt = S.flag('c_bt')                           # bearing at the high-high trip
    # each program reads the others' values through mirrors (one tick of theirs late)
    x_f, v_f, exc_f, tr_f, grate_f, lv_f = (F.mirror(vv, vv.name + '_f') for vv in (x, v, exc, tr, grate, lv))
    n_m, g_m, cb_m, pe_m, qe_m, dl_m, oop_m = (M.mirror(vv, vv.name + '_m') for vv in (n, g, cb, pe, qe, dl, c_oop))
    hp_m, air_m, lv_m, q_m, sg_m, cbt_m = (M.mirror(vv, vv.name + '_m') for vv in (hp, air, lv, q, sg, c_bt))
    plc_m, avr_m = M.mirror(plc, 'plc_m'), M.mirror(avr, 'avr_m')
    n_s, g_s, v_s, pe_s, cb_s, plc_s, avr_s, brk_s, qf_s = (S.mirror(vv, vv.name + '_s') for vv in (n, g, v, pe, cb, plc, avr, brake, qf))
    qf_m = M.mirror(qf, 'qf_m')
    head = lambda lvr: aff(lvr, 1 / HEAD0, (HEAD0 - 7.0) / HEAD0)                  # head, pu
    shead = lambda lvr: aff(lvr, 0.5 / HEAD0, 0.5 + 0.5 * (HEAD0 - 7.0) / HEAD0)   # its square root (near 1)

    # ================================================================ FAST (0.03 s)
    N, G, CB = n.r, g.r, cb.r
    w = N / 100
    # ------------------------------------------------------------ the wicket gate moves at the commanded speed
    g_new = clamp(G + grate_f.r * df, 0, 100)
    F.set(g, g_new)
    F.add(odraw, 0.5 * (relu(g_new - G) + relu(G - g_new)))     # oil drawn by the travel (the slow program's)

    # ------------------------------------------------------------ the runner and the rotor
    # Francis runner torque falls with speed; the water column (TW) makes it lag the gate and kick the
    # wrong way first (open the gate fast and the power dips before it rises). On line the rotor is tied
    # to the grid through XS: the load angle dl sets the power, the field sets the vars, and the damper
    # windings damp the swings.
    X = x_f.r
    # Open-flume Francis unit: the runner sits in an open concrete flume off the headrace, with no penstock
    # and no scroll case. The water in the flume and draft tube still has some momentum (inelastic water
    # column, as in the IEEE hydro turbine models: TW dq/dt = h0 - h - FL q^2, and the turbine passes
    # q = G sqrt(h)), solved semi-implicitly so it stays stable as the gate closes. With TW only 0.4 s the
    # power dips just a little when the gate opens fast, and a fast closure only piles the water up in the
    # flume (a surge of a few feet, not water hammer).
    Ge = clamp(G * 0.01, 0.005, None)               # gate opening, pu (closed gates still leak a little)
    cw_ = df / TW
    q_new = (qf.r + cw_ * (head(lv_f.r) - FL * sq(qf.r))) / (1 + cw_ * qf.r / sq(Ge))
    F.set(qf, q_new)
    # the free surface in the flume limits a closure surge to about 0.7 m (2.4 ft: wave speed x flow
    # velocity / g), so the head can rise at most 0.06 pu over the river's
    rh = clamp(q_new / Ge, 0, None)
    rh = rh - relu(rh - (shead(lv_f.r) + 0.03))     # sqrt of the head at the turbine, pu
    hh = sq(rh)                                     # head at the turbine, pu
    Tt = 0.018 * G * hh - pwl(G, B_PTS) * rh * w
    Tm = Tt
    Pe = CB * 0.02 * X * sin_deg(dl.r)              # electrical power, pu (E = field / 100, XS = 0.5)
    Qe = CB * (0.02 * X * cos_deg(dl.r) - 2)        # reactive power, pu (lagging +)
    F.set(pe, Pe)
    F.set(qe, Qe)
    tf = aff(sq(N), 8e-6, 0.005)                    # friction and windage, 0.005 + 0.08 w^2
    acc = Tm - tf - Pe - CB * DSW * (N - 100) - F.mirror(brake, 'brake_f').r * 0.3 * step(N, 1, 0.5)
    n_new = clamp(N + (df * 100 / H2) * acc, 0, 170)
    F.set(n, n_new)

    # ------------------------------------------------------------ synchronizing
    # The phase between the generator and the grid turns at the slip, 216 deg/s per % of speed (60 Hz =
    # 100 %, shown at most a turn a second), while the field is on and the unit is within 5 % of
    # synchronous speed. Closed on line the two are the same bus, so the synchroscope reads 12 o'clock.
    V_f, EXC_f, TR_f = v_f.r, exc_f.r, tr_f.r
    # GOV / AVR MODE: AUTO and MAN from the switches; a trip drops both to MAN and holds them there until reset
    F.set(plc, OR(plc_a.r, plc.r * NOT(plc_mn.r)) * NOT(TR_f))
    F.set(avr, OR(avr_a.r, avr.r * NOT(avr_mn.r)) * NOT(TR_f))
    phs = EXC_f * step(N, 95) * below(N, 105) * NOT(CB)
    th1 = th.r + clamp(216 * (N - 100), -360, 360) * phs * df
    F.set(th, th1 - 360 * step(th1, 360) + 360 * below(th1, -0.001))
    # in phase: within 10 deg of 12 o'clock, slip under 0.2 Hz (0.33 %), volts within 5 %
    pin = OR(below(th.r, 10), step(th.r, 350))
    pok = phs * pin * step(N, 99.67) * below(N, 100.33) * step(V_f, 95) * below(V_f, 106)
    perm = F.flag('perm')
    F.set(perm, pok * hss.r)
    needle(F, 'nd_SCOPE', sel(CB, 0, th.r) / 360, imm=True, cond=hss.r)
    dev['scope'] = 'nd_SCOPE'
    # sync lamps, dark at 12 o'clock: 255 |sin(phase / 2)|
    tu = th.r / 360
    F.sink('SYNCLAMPS', 'Alpha', hss.r * phs * (1020 * tu * (1 - tu)))
    # 52G: closes in phase (switch on or off). Out of phase the sync check (switch on) refuses it and the
    # handle springs back; with the switch off nothing stops it: closed out of phase, the unit trips.
    closing = c52.r * NOT(CB) * NOT(TR_f)
    close = closing * pok
    # held until the trip it causes: the close is a one-tick pulse, shorter than the medium loop's tick
    F.set(c_oop, OR(closing * NOT(pok) * NOT(hss.r), c_oop.r * NOT(TR_f)))
    cb_new = CB * NOT(t52.r) * NOT(TR_f) + close
    F.set(cb, cb_new)
    # the load angle starts at the phase the breaker closed on, then swings with the rotor
    dl1 = dl.r + 216 * df * (n_new - 100)
    dl1 = dl1 - 360 * step(dl1, 180) + 360 * below(dl1, -180)
    F.set(dl, CB * dl1 + close * (th.r - 360 * step(th.r, 180)))

    # ------------------------------------------------------------ fast meters and lamps
    needle(F, 'p_kw', Pe * PBASE / 320)                     # 0-320 kW
    needle(F, 'p_head', hh * 40 / 60)                       # net head, 0-60 ft (40 ft rated)
    pf_ang = pwl(Qe / clamp(Pe, 0.03, None), ATAN_PTS)
    needle(F, 'p_pf', sel(CB, 0.5 + pf_ang / 120, 0.5))
    needle(F, 'p_speed', N / 150)
    needle(F, 'p_gate', G / 100)
    hz = (0.6 * N - 54) / 12                                # 54-66 Hz
    needle(F, 'p_hz', hz)
    needle(F, 'p_sfreq', sel(CB, 0.5, hz))                  # the station bus: the grid's on line, the unit's off
    lamp('LP_cb', cb, ('red', 'green'))
    cb.on_rise('r_52_flag', 'Skin', 0).on_fall('r_52_flag', 'Skin', 1)      # 52G switch target: red closed, green tripped
    lamp('L_perm', perm, ('green', None))

    # ================================================================ MEDIUM (0.12 s)
    Nm, Gm, CBm = n_m.r, g_m.r, cb_m.r
    X, V, EXC, TR, BRK = x.r, v.r, exc.r, tr.r, brake.r
    Pm, Qm = pe_m.r, qe_m.r
    # ------------------------------------------------------------ the wicket gate's speed
    oil_open = step(hp_m.r, 230)
    oil_close = step(hp_m.r, 200)
    man = NOT(plc_m.r) * NOT(TR)
    # dials: 0.25 %/s for the first second held, 2.5 %/s for the next two, then 10 %/s (fine trim for syncing)
    on_r, on_l = step(kgr.r, 0.5), step(kgl.r, 0.5)
    M.set(gr_t, (gr_t.r + dm) * on_r)
    M.set(gl_t, (gl_t.r + dm) * on_l)
    rate = lambda t: 0.25 + 2.25 * step(t, 1.0) + 7.5 * step(t, 3.0)
    d_man = man * (on_r * oil_open * rate(gr_t.r) - on_l * oil_close * rate(gl_t.r))
    # PLC off line: a PID speed governor. It holds the unit a hair fast (100.08 %, so the synchroscope
    # creeps clockwise), with the gate limited to 25 % while starting and 30 % near speed; brakes on: gate
    # shut. Below 90 % speed the integrator waits at the speed-no-load gate, so the gate comes back as the
    # speed nears 100 % instead of overshooting.
    plc_off = plc_m.r * NOT(CBm) * NOT(TR) * oil_open
    gerr = 100.08 - Nm
    glim = aff(step(Nm, 90), 5, 25)
    g_cmd = clamp(gi.r + GOV_KP * gerr - GOV_KD * (Nm - n_prev.r) / dm, 0, None)
    g_cmd = g_cmd - relu(g_cmd - glim)
    gi_up = sel(step(Nm, 90), gi.r + dm * GOV_KI * gerr, 15)
    M.set(gi, sel(plc_off, gi_up - relu(gi_up - glim), Gm))       # follows the gate when not governing
    M.set(n_prev, Nm)
    d_plc_off = plc_off * sel(BRK, -10, clamp((g_cmd - Gm) * 4, -10, 10))
    # PLC on line: holds the river at 7.0 m (opens the gate as the river rises), never below 17 % gate
    el_m = q_m.r - Gm * shead(lv_m.r) - 100 * sg_m.r
    d_on = clamp(0.5 * el_m + 5 * (lv_m.r - 7.0), -2, 2)
    d_on = d_on + relu(-d_on) * below(Gm, 17, 0.5)
    d_plc_on = plc_m.r * CBm * NOT(TR) * oil_open * d_on
    # a trip shuts the gate at once (160 %/s)

    # ------------------------------------------------------------ excitation
    # 41 closes from 90 % speed and stays closed; it opens on a trip or by hand
    exc_new = NOT(TR) * NOT(t41.r) * OR(EXC, c41.r * step(Nm, 90, 0.05))
    M.set(exc, exc_new)
    # Static exciter fed from the generator's own terminals: its ceiling is 1.4 x the volts, so with no volts
    # it can't build the field; while the volts are under 40 % the station battery flashes the field (30 %).
    flash = EXC * below(V, 40)
    ceiling = 1.4 * V + relu(30 * flash - 1.4 * V)
    # AVR: off line it holds 480 V; on line it holds 0.95 power factor lagging (Q = 0.33 P). PI, and it
    # tracks the manual setting while in MAN so the change-over is bumpless.
    err = sel(CBm, 100 * (0.33 * relu(Pm) - Qm), 100 - V)
    u_man = pwl(kfa_m.r, KNOB_PTS)
    ki = aff(CBm, -0.6, 1.2)
    u_cmd = clamp(sel(avr_m.r, ui.r + 0.8 * err, u_man), 0, 140)
    free = below(u_cmd - ceiling, 0, 0.5)                          # no integrating while at the ceiling
    M.set(ui, sel(EXC, sel(avr_m.r, ui.r + dm * ki * err * free, u_man), 100))
    u = EXC * (u_cmd - relu(u_cmd - ceiling))
    # the field current follows the exciter through the field winding (1.5 s); opened, it discharges (0.4 s)
    M.set(x, X + dm * (u - X) * aff(EXC, 1 / 1.5 - 1 / 0.4, 1 / 0.4))
    # volts: off line the open-circuit curve times speed; on line the grid's, raised a little by the vars
    M.set(v, clamp(sel(CBm, 100 + 100 * XT * Qm, pwl(X, OCC_PTS) * Nm / 100), 0, 140))
    # with the AVR on, the firing-angle knob follows it
    k_cmd = clamp(pwl(u_cmd, [(b, a) for a, b in KNOB_PTS]), 0, 1)
    M.sink('k_fa', 'SetPosition', gate(k_cmd, avr_m.r, 0, 1))
    # when 41 opens the manual field setting goes back to the no-load value (the knob turns there), so the
    # next field application in MAN gives 480 V
    exc.on_fall('k_fa', 'SetPosition', round(KNOB0, 4), delay=1.0)

    # ------------------------------------------------------------ protection
    rev = CBm * below(Pm, -0.02)                    # motoring: the grid drives the unit
    M.set(rp_t, (rp_t.r + dm) * rev)
    causes = {
        'ovsp': step(Nm, 140),                              # 12 overspeed, 140 %
        'oop': oop_m.r,                                     # 52G closed out of phase
        'rp': step(rp_t.r, 8),                              # 32 reverse power for 8 s
        'lof': CBm * OR(below(X, 60), step(dl_m.r, 120), below(dl_m.r, -120)),   # 40 loss of field / pole slip
        'ov': NOT(CBm) * step(V, 115),                      # 59 overvoltage, 115 %
        'bthh': cbt_m.r,                                    # 38 bearing temperature high-high, 90 C
    }
    other = OR(step(Gm, 0.5) * below(hp_m.r, 210),          # hydraulic oil gone with the gate open
               below(lv_m.r, 4.75) * step(Nm, 1, 0.5),      # the intake would draw air
               gt_trip.r)                                   # 86U turned to TRIP
    tr_new = OR(*causes.values(), other, TR * NOT(gt_rst.r))      # latched until 86U is turned to RESET
    M.set(tr, tr_new)
    target(tr, 'r_gt')                                       # 86U target: red while locked out
    M.set(grate, (d_man + d_plc_off + d_plc_on) * NOT(tr_new) - 160 * tr_new)
    # generator air brakes: applied by air (50 psi at least), only below 30 % speed; springs release them
    M.set(brake, NOT(hbr_m.r) * step(air_m.r, 50) * OR(BRK, below(Nm, 30)))

    # ------------------------------------------------------------ medium meters and lamps
    needle(M, 'p_volts', V / 125)                           # 0-600 V
    # stator current: apparent power over volts. |S| by alpha-max-plus-beta-min (within 4 %; the logic has no
    # square root); 409 A per pu of S at 480 V (1 pu = PBASE kW), 0-500 A
    aP, aQ = absx(Pm), absx(Qm)
    smax = aQ + relu(aP - aQ)
    s_app = 0.96 * smax + 0.398 * (aP + aQ - smax)
    needle(M, 'p_amps', 409 * s_app * 100 / clamp(V, 50, None) / 500)
    needle(M, 'p_exc', X / 120)                             # 0-60 A
    needle(M, 'p_fa', 1 - EXC * k_cmd)                      # firing angle 0-90 deg
    lamp('LP_exc', exc, ('red', 'green'))
    exc.on_rise('r_exc_flag', 'Skin', 0).on_fall('r_exc_flag', 'Skin', 1)   # 41 switch target
    lamp('LP_brake', brake, ('red', 'green'))

    # ================================================================ SLOW
    Ns, Gs = n_s.r, g_s.r
    ws = Ns / 100
    spin_s = step(Ns, 1, 0.5)
    # ------------------------------------------------------------ river
    # no pond: the intake takes its water straight out of the river (7.0 m normal, 9.0 m bank full), and the
    # head on the runner rises and falls with it (12.2 m at 7.0 m)
    qt = 100 * qf_s.r                               # turbine flow, % of full-gate flow at rated head
    el = q.r - qt - 100 * sg.r                      # river balance, % of full-gate discharge
    S.set(lv, lv.r + ds * 0.004 * el)
    # the river's flow rises and falls between 65 and 85 %, 0.15 % a second
    S.set(q, q.r + ds * 0.15 * (2 * rup.r - 1))
    S.set(rup, clamp(rup.r + below(q.r, 65) - step(q.r, 85), 0, 1))
    # spillway gate: AUTO opens it above 7.5 m while the river still rises (or at 9.0 m) and closes it below
    # 7.25 m while it falls; with the PLC on line it gives the water to the unit first. MANUAL: the dials.
    auto = NOT(sman.r)
    s_open = auto * OR(step(lv.r, 7.5) * step(el, 0.01), step(lv.r, 9.0))
    s_close = auto * below(lv.r, 7.25) * below(el, -0.01)
    s_plc = auto * plc_s.r * cb_s.r * below(lv.r, 7.5) * below(Gs, 99.5)
    S.set(sg, sg.r + ds * (0.0375 * (s_open - s_close) - 0.01875 * s_plc
                           + 0.15 * sman.r * (step(ksr.r, 0.5) - step(ksl.r, 0.5))))

    # ------------------------------------------------------------ auxiliaries
    S.set(lp, lp.r + ds * 2 * (36 * lube.r - lp.r))
    S.set(cw, cw.r + ds * 2 * (62 * cool.r - cw.r))
    # hydraulic oil (wicket gate servomotors): the pump runs on its pressure switch (on below 270 psi, off
    # at 300); the pilot valves leak, and every % of gate travel draws 0.5 psi
    hpu_new = hhp.r * OR(below(hp.r, 270), hpu.r * below(hp.r, 300))
    S.set(hpu, hpu_new)
    S.set(hp, hp.r + ds * (25 * hpu_new - 1.25 * step(hp.r, 0.5)) - odraw.r)
    S.add(odraw, -odraw.r)
    # brake air: the compressor runs on its pressure switch, on below 100 psi and off at 125
    comp_new = hac.r * OR(below(air.r, 100), comp.r * below(air.r, 125))
    S.set(comp, comp_new)
    S.set(air, air.r + ds * (12 * comp_new - 0.6 * step(air.r, 0.5) - 3.1 * brk_s.r * step(air.r, 0.5)))
    # bearings: they warm with speed and load towards 52-60 C with cooling water (a minute's time
    # constant); without it they head for 120 C, and without lube oil they wipe in seconds
    S.set(bt, bt.r + ds * ((sel(cool.r, 24 + 28 * ws + 10 * relu(pe_s.r), 24 + 100 * ws) - bt.r) / 60
                           + 6 * ws * NOT(lube.r)))
    S.set(c_bt, step(bt.r, 90))

    # ------------------------------------------------------------ slow meters
    # grid volts: the 480 V bus the utility feeds through the step-up transformer. The grid is stiff (the sync
    # check compares the generator against 100 %), so it reads 480 V whether 52G is open or closed.
    needle(S, 'p_gridv', 100 / 125)                          # 0-600 V
    needle(S, 'p_lube', lp.r / 60)
    needle(S, 'p_cw', cw.r / 100)
    needle(S, 'p_bt', (bt.r - 20) / 80)
    needle(S, 'p_vib', sel(cb_s.r, pwl(Gs, VIB_PTS), 3) / 20)
    needle(S, 'p_opu', hp.r / 400)
    needle(S, 'p_air', air.r / 150)
    needle(S, 'p_hw', lv.r / 10)
    needle(S, 'p_rq', 0.9 * q.r / 120)
    needle(S, 'p_spill', sg.r / 1.2)

    # ------------------------------------------------------------ annunciator
    # ISA manual-reset sequence (ISA-18.1 "M"): a new alarm flashes its window and sounds the horn;
    # ACKNOWLEDGE makes it steady and silences the horn; once the condition has cleared, RESET puts the
    # window out; TEST lights every window while held in. Trip windows take the protective relays' targets,
    # which stay up until the 86 lockout is reset.
    ack = A.var('ack', 0, 0, 1); arst = A.var('arst', 0, 0, 1); atest = A.flag('atest')
    for name, label, var, wait in (('b_ack', 'ACK', ack, 0.4), ('b_rst', 'RESET', arst, 0.4), ('b_test', 'TEST', atest, 3)):
        e = m.ent('func_button', name, spawnflags=1024, speed=20, lip=1, wait=wait, movedir='0 90 0', sounds=0)
        if var is atest:
            e.out('OnIn', var.ent, 'SetValue', 1).out('OnOut', var.ent, 'SetValue', 0)
        else:
            e.out('OnPressed', var.ent, 'SetValue', 1)
        e.out('OnPressed', 's_click', 'PlaySound')
        dev.setdefault('buttons', {})[name] = {'ent': e, 'label': label}
    blink = A.flag('blink')
    A.set(blink, NOT(blink.r))                      # windows flash at about 2 Hz
    ACK, RST, TEST = ack.r, arst.r, atest.r
    A.add(ack, -ACK); A.add(arst, -RST)
    am = lambda vv: A.mirror(vv, vv.name + '_a').r
    keep = NOT(gt_rst.r)
    trips = {}
    for key in ('ovsp', 'lock', 'gbkr', 'oop', 'rp', 'lof', 'ov', 'bthh'):
        t = M.flag(f't_{key}')
        if key in causes:                                          # protective relay targets: latch until the reset
            M.set(t, OR(causes[key], t.r * keep))
        elif key == 'gbkr':                                        # 52G opened by protection (cleared when it closes again)
            M.set(t, OR(CBm * tr_new, t.r * keep * NOT(CBm)))
        else:                                                      # 86 lockout
            M.set(t, TR)
        trips[key] = A.mirror(t, f't_{key}_a').r
    raw = dict(trips)
    ga, cba = am(g), am(cb)
    lva = am(lv)
    raw.update({
        'bth': step(am(bt), 76), 'vib': cba * step(ga, 25) * below(ga, 50),
        'hyd': below(am(hp), 240), 'oilp': below(am(lp), 20), 'watp': below(am(cw), 35), 'air': below(am(air), 50),
        'brk': am(brake), 'rhi': step(lva, 7.5), 'rlo': below(lva, 6.25), 'spill': step(am(sg), 0.01),
        'plc': NOT(am(plc)), 'avr': NOT(am(avr))})
    unacked, news = [], []
    for i, (key, legend, kind) in enumerate(ANN_WINDOWS):
        lit = A.flag(f'w_{key}')
        if kind == 'status':                                       # status points: lit while true, no horn
            A.set(lit, OR(raw[key], TEST))
        else:
            ua, aa = A.flag(f'ua_{key}'), A.flag(f'aa_{key}')    # unacknowledged (flashing), acknowledged (steady)
            new = raw[key] * NOT(ua.r) * NOT(aa.r)
            ua_new = OR(ua.r * NOT(ACK), new)
            aa_new = OR(aa.r * NOT(RST * NOT(raw[key])), ua.r * ACK)
            A.set(ua, ua_new); A.set(aa, aa_new)
            A.set(lit, OR(aa_new, ua_new * blink.r, TEST))
            unacked.append(ua_new); news.append(new)
        e = m.ent('func_brush', f'A{i:02d}', StartDisabled=1, Solidity=1)
        lit.on_rise(e, 'Enable').on_fall(e, 'Disable')
        dev['windows'].append({'ent': e, 'legend': legend, 'kind': kind})
    # the horn sounds while any alarm is unacknowledged; a relay clicks for each new one
    horn, anew = A.flag('horn'), A.flag('anew')
    tot_u, tot_n = unacked[0], news[0]
    for u_, n_ in zip(unacked[1:], news[1:]):
        tot_u, tot_n = tot_u + u_, tot_n + n_
    A.set(horn, step(tot_u, 0.5)); A.set(anew, step(tot_n, 0.5))
    h_on, h_off, r_new = armed_relay('horn_on'), armed_relay('horn_off'), armed_relay('anew_on')
    horn.on_rise(h_on, 'Trigger').on_fall(h_off, 'Trigger'); anew.on_rise(r_new, 'Trigger')
    h_on.out('OnTrigger', 's_horn', 'PlaySound'); h_off.out('OnTrigger', 's_horn', 'StopSound')
    r_new.out('OnTrigger', 's_relay', 'PlaySound')
    dev['ack_at_start'] = ack

    # ------------------------------------------------------------ sounds
    # the turbine's pitch follows its speed and its loudness the water through it; the generator hums
    # louder with volts and load; the pump and the compressor run when their pressure switches call
    # (pitch and loudness from the medium loop, 8 times a second, so they slide smoothly)
    qtm = 100 * qf_m.r
    M.sink('s_turb', 'Pitch', clamp(Nm, 25, 150))
    M.sink('s_turb', 'Volume', clamp(1.5 + 0.06 * qtm + 0.02 * Nm, 0, 10))
    M.sink('s_water', 'Volume', clamp(0.5 + 0.11 * qtm, 0, 10))
    M.sink('s_hum', 'Volume', clamp(0.035 * V + 6 * relu(Pm), 0, 10))
    for nm, cond in (('s_turb', spin_s), ('s_water', step(Gs, 0.5)), ('s_hum', step(v_s.r, 3)),
                     ('s_pump', hpu.r), ('s_comp', comp.r)):
        f = S.flag(f'snd_{nm}')
        S.set(f, cond)
        r_on, r_off = armed_relay(f'{nm}_on'), armed_relay(f'{nm}_off')
        f.on_rise(r_on, 'Trigger'); f.on_fall(r_off, 'Trigger')
        r_on.out('OnTrigger', nm, 'PlaySound'); r_off.out('OnTrigger', nm, 'StopSound')
    brk_r = armed_relay('s_brk_r')
    cb.on_rise(brk_r, 'Trigger').on_fall(brk_r, 'Trigger')
    brk_r.out('OnTrigger', 's_brk', 'PlaySound')

    F.compile()
    M.compile()
    S.compile()
    A.compile()
    # the alarms standing when the map starts are acknowledged, as an operator would have left them;
    # then the sounds and the horn are armed
    m['a_auto'].out('OnMapSpawn', dev['ack_at_start'].ent, 'SetValue', 1, 0.6)
    for e in m.ents:
        if e.cls == 'logic_relay' and e.name.endswith(('_on', '_off', '_brk_r')):
            m['f_auto'].out('OnMapSpawn', e, 'Enable', None, 1.5)
    return m, (F, M, S, A), dev


BIGT = 1.0e4


def stats(m, progs):
    from collections import Counter
    c = Counter(e.cls for e in m.ents)
    logic = sum(v for k, v in c.items() if k in ('math_counter', 'math_remap', 'logic_relay', 'logic_timer', 'logic_auto'))
    return c, logic, len(m.ents) - logic


if __name__ == '__main__':
    m, progs, dev = build()
    c, logic, net = stats(m, progs)
    print(len(m.ents), 'entities:', logic, 'logic (no network slot),', net, 'networked')
    for k, v in c.most_common():
        print(f'  {k:22s} {v}')
    for p in progs:
        print(p.name, 'nodes', len(p.nodes), 'deepest level', max(b for a, b in p.levels.values()))
