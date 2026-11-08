"""
Sable Creek Unit 1 for Half-Life 2: the plant as one tick program of logic entities (see srclogic.py).

The controls are the ones of the GoldSrc map:
  left (unit control)   SYNCHRONIZING, 52G GEN BREAKER, 41 FIELD BREAKER, WICKET GATE TRIP switches;
                        WICKET GATE LOWER and RAISE dials (spring-return), BRAKES dial, FIRING ANGLE knob
  middle (annunciator)  PLC and AVR switches
  right (auxiliaries)   OIL PUMP, WATER PUMP, HYDRAULIC PUMP, AIR COMPRESSOR switches
  spillway panel        CONTROL MODE dial (AUTO / MANUAL), spill GATE LOWER and RAISE dials

Units: speed n, gate g, volts v and field x in % (100 % = 100 rpm, 480 V, rated field); hydraulic oil hp
and brake air in psi; bearing temperature bt in deg C; river depth l in m at the intake; river flow q in %
of full-gate discharge (90 cfs); spill gate opening sg in m; phase th in degrees.
"""
import math
from srclogic import (Map, Program, DT, C, aff, clamp, relu, step, below, AND, OR, NOT, sel, pwl, gate, mul, add, sub)

# --------------------------------------------------------------- the machine
# Per-unit model (1 pu speed = 100 rpm, 1 pu power = PBASE kW, torque in pu of rated torque).
PBASE = 340.0          # kW per pu: full gate at rated head gives about 245 kW
H2 = 6.0               # mechanical starting time 2H, s (runner, shaft and 72-pole rotor)
TW = 1.0               # water starting time of the intake and penstock, s
XS = 0.5               # reactance between the internal EMF and the grid, pu
XT = 0.06              # step-up transformer reactance: the terminal volts rise with the vars
DSW = 0.27             # damper winding damping on line, pu torque per % slip
GOV_KP, GOV_KI, GOV_KD = 1.5, 0.3, 1.0   # PLC governor PID: % gate per % speed error, per % s, per %/s
HEAD0 = 12.2           # rated head, m (40 ft) at 7.0 m river depth; the tailwater is 5.2 m below the intake bed

# Francis runner: torque = A(g) h - B(g) sqrt(h) w (falls linearly with speed), friction and windage
# Tf = 0.005 + 0.08 w^2. A is the stall torque (1.8 pu at full gate); B is set so that off line, with no
# load, the runner settles where the GoldSrc map's curve put it: speed-no-load at 15 % gate, runaway
# 160 % at full gate.
N_EQ = [(0, 0), (2, 0.05), (5, 0.3), (10, 0.7), (15, 1.0), (20, 1.2), (25, 1.32), (30, 1.4), (100, 1.6)]
_neq = lambda g: next(n0 + (n1 - n0) * (g - g0) / (g1 - g0) for (g0, n0), (g1, n1) in zip(N_EQ, N_EQ[1:]) if g0 <= g <= g1)
TF = lambda w: 0.005 + 0.08 * w * w
STALL = lambda g: 1.8 * g / 100
B_PTS = [(0, 0)] + [(g, round((STALL(g) - TF(_neq(g))) / _neq(g), 4)) for g in (2, 5, 10, 15, 20, 25, 30, 40, 50, 65, 80, 100)]
TF_PTS = [(w, round(TF(w / 100), 4)) for w in (0, 25, 50, 75, 100, 125, 150, 175)]
# generator open-circuit curve: volts (%) at rated speed for each % of field current (2 % residual)
OCC_PTS = [(0, 2), (40, 45), (70, 76), (90, 93), (100, 100), (120, 110), (140, 117)]
# static exciter: field (% of rated) for each firing-angle knob position, 140 % at 0 deg (the ceiling)
KNOB_PTS = [(k / 6, round(140 * math.sin(math.radians(15 * k)), 2)) for k in range(7)]
KNOB0 = math.degrees(math.asin(100 / 140)) / 90           # knob position for rated no-load field
ATAN_PTS = [(-2.0, -63.4), (-1.0, -45), (-0.5, -26.6), (0, 0), (0.5, 26.6), (1.0, 45), (2.0, 63.4)]
SIN_PTS = [(a, round(255 * math.sin(math.radians(a / 2)), 1)) for a in range(0, 361, 45)]
SIND = [(a, round(math.sin(math.radians(a)), 5)) for a in range(-180, 181, 15)]
COSD = [(a, round(math.cos(math.radians(a)), 5)) for a in range(-180, 181, 15)]
_VIB5 = [0, 1, 3, 6, 6, 7, 8, 8, 7, 6, 4, 3, 2, 2] + [2] * 7
_gidx = lambda i: 15 + (i * 5 - 10) * 85 / 90 if i >= 2 else i * 7.5
VIB_PTS = [(round(_gidx(i), 2), _VIB5[i]) for i in range(0, 21)]

ANN_WINDOWS = [
    ('ovsp', '12 OVERSPEED|TRIP', 'trip'), ('lock', '86 LOCKOUT|TRIPPED', 'trip'), ('gbkr', '52G GEN BKR|TRIPPED', 'trip'),
    ('oop', '52G CLOSED|OUT OF PHASE', 'trip'), ('rp', '32 REVERSE|POWER', 'trip'),
    ('lof', '40 LOSS OF|FIELD', 'trip'), ('ov', '59 GEN|OVERVOLTAGE', 'trip'), ('bthh', '38 BRG TEMP|HIGH-HIGH', 'trip'),
    ('bth', '38 BRG TEMP|HIGH', 'alarm'), ('vib', '39 VIBRATION|HIGH', 'alarm'),
    ('hyd', 'HYD OIL|PRESS LOW', 'alarm'), ('oilp', 'OIL PUMP|STOPPED', 'alarm'), ('watp', 'WATER PUMP|STOPPED', 'alarm'),
    ('air', 'BRAKE AIR|PRESS LOW', 'alarm'), ('brk', 'BRAKES|APPLIED', 'status'),
    ('rhi', 'RIVER DEPTH|HIGH', 'alarm'), ('rlo', 'RIVER DEPTH|LOW', 'alarm'), ('spill', 'SPILLWAY GATE|OPEN', 'status'),
    ('plc', 'PLC|OFF', 'status'), ('avr', 'AVR IN|MANUAL', 'status')]

INIT = dict(n=0, g=0, v=0, x=0, hp=0, air=0, bt=24, l=7, q=75, sg=0.75)


def build():
    m = Map()
    P = Program(m, 'pl')
    dev = {'needles': {}, 'switches': {}, 'dials': {}, 'lamps': {}, 'windows': [], 'sounds': {}, 'scope': None}
    dt = DT

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

    def switch(name, var, label, pos, grip='black', speed=240, kind='cs'):
        """maintained switch, two positions 90 degrees apart: OUT = pos[0] (left), IN = pos[1] (right).
        The handle's position is the variable."""
        e = m.ent('func_rot_button', name, distance=90, speed=speed, spawnflags=32 + 1024 + 128, sounds=0, wait=-1)
        v = P.flag(var)
        e.out('OnIn', v.ent, 'SetValue', 1)
        e.out('OnOut', v.ent, 'SetValue', 0)
        e.out('OnPressed', 's_click', 'PlaySound')
        dev['switches'][name] = {'ent': e, 'label': label, 'pos': pos, 'grip': grip, 'kind': kind}
        return v

    def dial(name, var, label, spring=True, start=0.0):
        """momentary_rot_button: its position (0..1) is the variable. Spring-return dials turn to their stop
        while held and spring back when let go."""
        e = m.ent('momentary_rot_button', name, distance=60 if spring else 300, speed=240 if spring else 30,
                  returnspeed=300 if spring else 0, spawnflags=1024 + 128, startposition=f'{start:.4f}', sounds=0)
        v = P.var(var, start, 0, 1)
        e.out('Position', v.ent, 'SetValue')
        dev['dials'][name] = {'ent': e, 'label': label, 'spring': spring}
        return v

    def needle(name, frac, imm=False, cond=None):
        e = m.ent('momentary_rot_button', name, distance=250, speed=400, spawnflags=1 + 128, startposition=0)
        f = clamp(frac, 0, 1)
        if cond is not None:
            f = gate(f, cond, 0, 1)
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
    hss = switch('r_ss', 'hss', 'SYNCHRONIZING', ('OFF', 'ON'))
    h52 = switch('r_52', 'h52', '52G GEN BREAKER', ('TRIP', 'CLOSE'), speed=900)
    hexc = switch('r_exc', 'hexc', '41 FIELD BREAKER', ('TRIP', 'CLOSE'))
    hgt = switch('r_gt', 'hgt', 'WICKET GATE TRIP', ('RESET', 'TRIP'), grip='red')
    plc = switch('r_plc', 'plc', 'PLC', ('OFF', 'ON'))
    avr = switch('r_avr', 'avr', 'AVR', ('MAN', 'AUTO'))
    lube = switch('r_lp', 'lube', 'OIL PUMP', ('STOP', 'RUN'))
    cool = switch('r_wp', 'cool', 'WATER PUMP', ('STOP', 'RUN'))
    hhp = switch('r_hp', 'hhp', 'HYDRAULIC PUMP', ('STOP', 'RUN'))
    hac = switch('r_ac', 'hac', 'AIR COMPRESSOR', ('STOP', 'RUN'))
    hbr = switch('r_br', 'hbr', 'BRAKES', ('APPLY', 'RELEASE'), kind='sel')
    sman = switch('r_sp', 'sman', 'CONTROL MODE', ('AUTO', 'MANUAL'), kind='sel')
    kgl = dial('k_gl', 'kgl', 'LOWER')
    kgr = dial('k_gr', 'kgr', 'RAISE')
    ksl = dial('k_sl', 'ksl', 'LOWER')
    ksr = dial('k_sr', 'ksr', 'RAISE')
    kfa = dial('k_fa', 'kfa', 'FIRING ANGLE', spring=False, start=KNOB0)
    rst = P.var('rst', 0, 0, 1)                     # reset request: the trip handle turned back to RESET
    m['r_gt'].out('OnOut', rst.ent, 'SetValue', 1)

    # ------------------------------------------------------------ state
    n = P.var('n', 0, 0, 170)                       # speed, %
    g = P.var('g', 0, 0, 100)                       # wicket gate, %
    v = P.var('v', 0, 0, 140)                       # generator volts, %
    x = P.var('x', 0, 0, 150)                       # field current, % of rated no-load field
    ui = P.var('ui', 100, 0, 140)                   # AVR integrator (field %)
    gi = P.var('gi', 0, 0, 100)                     # PLC governor integrator (gate %)
    tlp = P.var('tlp', 0, -3, 3)                    # water column: the torque the flow has caught up to
    dl = P.var('dl', 0, -BIGT, BIGT, clamp=False)   # load angle on line, deg
    hp = P.var('hp', 0, 0, 320)
    air = P.var('air', 0, 0, 130)
    bt = P.var('bt', INIT['bt'], 0, 130)
    lv = P.var('l', INIT['l'], 3, 9.5)
    q = P.var('q', INIT['q'], 60, 90)
    rup = P.flag('rup', 1)
    sg = P.var('sg', INIT['sg'], 0, 1.2)
    th = P.var('th', 0, -BIGT, BIGT, clamp=False)
    cb = P.flag('cb'); exc = P.flag('exc'); tr = P.flag('tr'); brake = P.flag('brake')
    hpu = P.flag('hpu'); comp = P.flag('comp')     # hydraulic pump and air compressor running
    lp = P.var('lp', 0, 0, 60)                      # lube oil pressure, psi
    cw = P.var('cw', 0, 0, 100)                     # cooling water flow, gpm
    rp_t = P.var('rp_t', 0, 0, 20)
    gr_t = P.var('gr_t', 0, 0, 5); gl_t = P.var('gl_t', 0, 0, 5)       # how long a gate dial has been held
    ph = P.var('ph', 0, 0, 3)                       # tick phase, for things updated every 4th tick
    horn_t = P.var('horn_t', 0, 0, 6)
    n_prev = P.var('n_prev', 0, 0, 170)            # last tick's speed (the governor's derivative)

    N, G, V, X = n.r, g.r, v.r, x.r
    CB, EXC, TR, BRK = cb.r, exc.r, tr.r, brake.r
    w = N / 100
    run = step(N, 50, 1)
    spin = step(N, 1, 0.5)

    # ------------------------------------------------------------ river and head
    # no pond: the intake takes its water straight out of the river (7.0 m normal, 9.0 m bank full), and the
    # head on the runner rises and falls with it (12.2 m at 7.0 m)
    hf = aff(lv.r, 1 / HEAD0, (HEAD0 - 7.0) / HEAD0)              # head, pu
    shf = aff(lv.r, 0.5 / HEAD0, 0.5 + 0.5 * (HEAD0 - 7.0) / HEAD0)  # its square root (near 1)
    qt = G * shf                                    # turbine flow, % of full-gate flow at rated head
    el = q.r - qt - 100 * sg.r                      # river balance, % of full-gate discharge
    P.set(lv, lv.r + dt * 0.004 * el)
    # the river's flow rises and falls between 65 and 85 %, 0.15 % a second
    P.set(q, q.r + dt * 0.15 * (2 * rup.r - 1))
    P.set(rup, clamp(rup.r + below(q.r, 65) - step(q.r, 85), 0, 1))
    # spillway gate: AUTO opens it above 7.5 m while the river still rises (or at 9.0 m) and closes it below
    # 7.25 m while it falls; with the PLC on line it gives the water to the unit first. MANUAL: the dials.
    auto = NOT(sman.r)
    s_open = auto * OR(step(lv.r, 7.5) * step(el, 0.01), step(lv.r, 9.0))
    s_close = auto * below(lv.r, 7.25) * below(el, -0.01)
    s_plc = auto * plc.r * CB * below(lv.r, 7.5) * below(G, 99.5)
    P.set(sg, sg.r + dt * (0.0375 * (s_open - s_close) - 0.01875 * s_plc
                           + 0.15 * sman.r * (step(ksr.r, 0.5) - step(ksl.r, 0.5))))

    # ------------------------------------------------------------ auxiliaries
    P.set(lp, lp.r + dt * 2 * (36 * lube.r - lp.r))
    P.set(cw, cw.r + dt * 2 * (62 * cool.r - cw.r))
    # brake air: the compressor runs on its pressure switch, on below 100 psi and off at 125
    comp_new = hac.r * OR(below(air.r, 100), comp.r * below(air.r, 125))
    P.set(comp, comp_new)
    P.set(air, air.r + dt * (12 * comp_new - 0.6 * step(air.r, 0.5) - 3.1 * BRK * step(air.r, 0.5)))
    # bearings: they warm with speed and load towards 52-60 C with cooling water (a minute's time
    # constant); without it they head for 120 C, and without lube oil they wipe in seconds
    P.set(bt, bt.r + dt * ((sel(cool.r, 24 + 28 * w + 10 * relu(CB * 0.02 * X * pwl(dl.r, SIND)), 24 + 100 * w) - bt.r) / 60
                           + 6 * w * NOT(lube.r)))

    # ------------------------------------------------------------ the wicket gate
    oil_open = step(hp.r, 230)
    oil_close = step(hp.r, 200)
    man = NOT(plc.r) * NOT(TR)
    # dials: 0.25 %/s for the first second held, 2.5 %/s for the next two, then 10 %/s (fine trim for syncing)
    on_r, on_l = step(kgr.r, 0.5), step(kgl.r, 0.5)
    P.set(gr_t, (gr_t.r + dt) * on_r)
    P.set(gl_t, (gl_t.r + dt) * on_l)
    rate = lambda t: 0.25 + 2.25 * step(t, 1.0) + 7.5 * step(t, 3.0)
    d_man = man * (on_r * oil_open * rate(gr_t.r) - on_l * oil_close * rate(gl_t.r))
    # PLC off line: a PI speed governor. It holds the unit a hair fast (100.08 %, so the synchroscope creeps
    # clockwise), with the gate limited to 25 % while starting and 30 % near speed; brakes on: gate shut.
    plc_off = plc.r * NOT(CB) * NOT(TR) * oil_open
    gerr = 100.08 - N
    glim = aff(step(N, 90), 5, 25)
    g_cmd = clamp(gi.r + GOV_KP * gerr - GOV_KD * (N - n_prev.r) / dt, 0, None)
    g_cmd = g_cmd - relu(g_cmd - glim)
    # below 90 % speed the integrator waits at the speed-no-load gate, so the gate comes back as the speed
    # nears 100 % instead of overshooting
    gi_up = sel(step(N, 90), gi.r + dt * GOV_KI * gerr, 15)
    P.set(gi, sel(plc_off, gi_up - relu(gi_up - glim), G))         # follows the gate when not governing
    d_plc_off = plc_off * sel(BRK, -10, clamp((g_cmd - G) * 4, -10, 10))
    # PLC on line: holds the river at 7.0 m (opens the gate as the river rises), never below 17 % gate
    d_on = clamp(0.5 * el + 5 * (lv.r - 7.0), -2, 2)
    d_on = d_on + relu(-d_on) * below(G, 17, 0.5)
    d_plc_on = plc.r * CB * NOT(TR) * oil_open * d_on
    dg = (d_man + d_plc_off + d_plc_on) * dt - TR * (160 * dt)
    g_new = clamp(G + dg, 0, 100)
    P.set(g, g_new)
    travel = relu(g_new - G) + relu(G - g_new)
    # hydraulic oil (wicket gate servomotors): the pump runs on its pressure switch (on below 270 psi, off
    # at 300); the pilot valves leak, and every % of gate travel draws 0.5 psi
    hpu_new = hhp.r * OR(below(hp.r, 270), hpu.r * below(hp.r, 300))
    P.set(hpu, hpu_new)
    P.set(hp, hp.r + dt * (25 * hpu_new - 1.25 * step(hp.r, 0.5)) - 0.5 * travel)

    # ------------------------------------------------------------ the runner and the rotor
    # Francis runner torque falls with speed; the water column (TW) makes it lag the gate and kick the
    # wrong way first (open the gate fast and the power dips before it rises). On line the rotor is tied
    # to the grid through XS: the load angle dl sets the power, the field sets the vars, and the damper
    # windings damp the swings.
    Tt = 0.018 * G * hf - pwl(G, B_PTS) * shf * w
    P.set(tlp, tlp.r + dt * (Tt - tlp.r) / (TW / 2))
    Tm = Tt + clamp(3 * (tlp.r - Tt), -0.3, 0.3)
    sd, cd = pwl(dl.r, SIND), pwl(dl.r, COSD)
    Pe = CB * 0.02 * X * sd                         # electrical power, pu (E = field / 100, XS = 0.5)
    Qe = CB * (0.02 * X * cd - 2)                   # reactive power, pu (lagging +)
    acc = Tm - pwl(N, TF_PTS) - Pe - CB * DSW * (N - 100) - BRK * 0.3 * spin
    n_new = clamp(N + (dt * 100 / H2) * acc, 0, 170)
    P.set(n, n_new)
    P.set(n_prev, N)

    # ------------------------------------------------------------ excitation
    # 41 closes from 90 % speed and stays closed; it opens on a trip or by hand
    exc_new = hexc.r * NOT(TR) * OR(EXC, step(N, 90, 0.05))
    P.set(exc, exc_new)
    # Static exciter fed from the generator's own terminals: its ceiling is 1.4 x the volts, so with no volts
    # it can't build the field; while the volts are under 40 % the station battery flashes the field (30 %).
    flash = EXC * below(V, 40)
    ceiling = 1.4 * V + relu(30 * flash - 1.4 * V)
    # AVR: off line it holds 480 V; on line it holds 0.95 power factor lagging (Q = 0.33 P). PI, and it
    # tracks the manual setting while in MAN so the change-over is bumpless.
    err = sel(CB, 100 * (0.33 * relu(Pe) - Qe), 100 - V)
    u_man = pwl(kfa.r, KNOB_PTS)
    ki = aff(CB, -0.6, 1.2)
    u_cmd = clamp(sel(avr.r, ui.r + 0.8 * err, u_man), 0, 140)
    free = below(u_cmd - ceiling, 0, 0.5)                          # no integrating while at the ceiling
    P.set(ui, sel(EXC, sel(avr.r, ui.r + dt * ki * err * free, u_man), 100))
    u = EXC * (u_cmd - relu(u_cmd - ceiling))
    # the field current follows the exciter through the field winding (1.5 s); opened, it discharges (0.4 s)
    P.set(x, X + dt * (u - X) * aff(EXC, 1 / 1.5 - 1 / 0.4, 1 / 0.4))
    # volts: off line the open-circuit curve times speed; on line the grid's, raised a little by the vars
    occ = pwl(X, OCC_PTS)
    P.set(v, clamp(sel(CB, 100 + 100 * XT * Qe, occ * N / 100), 0, 140))
    # with the AVR on, the firing-angle knob follows it
    k_of = lambda f: pwl(f, [(b, a) for a, b in KNOB_PTS])
    P.sink('k_fa', 'SetPosition', gate(clamp(k_of(u_cmd), 0, 1), avr.r, 0, 1))

    # ------------------------------------------------------------ synchronizing
    # The phase between the generator and the grid turns at the slip, 216 deg/s per % of speed (60 Hz =
    # 100 %, shown at most a turn a second), while the field is on and the unit is within 5 % of
    # synchronous speed. Closed on line the two are the same bus, so the synchroscope reads 12 o'clock.
    phs = EXC * step(N, 95) * below(N, 105) * NOT(CB)
    slip = clamp(216 * (N - 100), -360, 360)
    th1 = th.r + slip * phs * dt
    P.set(th, th1 - 360 * step(th1, 360) + 360 * below(th1, -0.001))
    # in phase: within 10 deg of 12 o'clock, slip under 0.2 Hz (0.33 %), volts within 5 %
    pin = OR(below(th.r, 10), step(th.r, 350))
    pok = phs * pin * step(N, 99.67) * below(N, 100.33) * step(V, 95) * below(V, 106)
    perm = P.flag('perm')
    P.set(perm, pok * hss.r)
    needle('nd_SCOPE', sel(CB, 0, th.r) / 360, imm=True, cond=hss.r)
    dev['scope'] = 'nd_SCOPE'
    P.sink('SYNCLAMPS', 'Alpha', hss.r * phs * pwl(th.r, SIN_PTS))
    # 52G: closes in phase (switch on or off). Out of phase the sync check (switch on) refuses it and the
    # handle springs back; with the switch off nothing stops it: closed out of phase, the unit trips.
    closing = h52.r * NOT(CB) * NOT(TR)
    close = closing * pok
    oop = closing * NOT(pok) * NOT(hss.r)
    cb_new = CB * h52.r * NOT(TR) + close
    P.set(cb, cb_new)
    # the load angle starts at the phase the breaker closed on, then swings with the rotor
    dl1 = dl.r + 216 * dt * (n_new - 100)
    dl1 = dl1 - 360 * step(dl1, 180) + 360 * below(dl1, -180)
    P.set(dl, CB * dl1 + close * (th.r - 360 * step(th.r, 180)))
    back52 = P.flag('back52'); P.set(back52, h52.r * NOT(cb_new))
    back52.on_rise('r_52', 'PressOut', delay=0.3)
    # when 41 opens the manual field setting goes back to the no-load value (the knob turns there), so the
    # next field application in MAN gives 480 V
    exc.on_fall('k_fa', 'SetPosition', round(KNOB0, 4), delay=1.0)
    back41 = P.flag('back41'); P.set(back41, hexc.r * NOT(exc_new))
    back41.on_rise('r_exc', 'PressOut', delay=0.3)

    # ------------------------------------------------------------ protection
    rev = CB * below(Pe, -0.02)                     # motoring: the grid drives the unit
    P.set(rp_t, (rp_t.r + dt) * rev)
    causes = {
        'ovsp': step(N, 140),                               # 12 overspeed, 140 %
        'oop': oop,                                         # 52G closed out of phase
        'rp': step(rp_t.r, 8),                              # 32 reverse power for 8 s
        'lof': CB * OR(below(X, 60), step(dl.r, 120), below(dl.r, -120)),   # 40 loss of field / pole slip
        'ov': NOT(CB) * step(V, 115),                       # 59 overvoltage, 115 %
        'bthh': step(bt.r, 90),                             # 38 bearing temperature high-high, 90 C
    }
    other = OR(step(G, 0.5) * below(hp.r, 210),             # hydraulic oil gone with the gate open
               below(lv.r, 4.75) * spin,                    # the intake would draw air
               hgt.r)                                       # the wicket gate trip handle
    cause = OR(*causes.values(), other)
    tr_new = OR(cause, TR * NOT(rst.r))
    P.set(tr, tr_new)
    P.add(rst, -rst.r)
    tr.on_rise('r_52', 'PressOut').on_rise('r_exc', 'PressOut').on_rise('r_plc', 'PressOut')
    tr.on_rise('r_avr', 'PressOut').on_rise('r_gt', 'PressIn')
    need_gt = P.flag('need_gt'); P.set(need_gt, tr_new * NOT(hgt.r))
    need_gt.on_rise('r_gt', 'PressIn', delay=0.5)

    # ------------------------------------------------------------ brakes
    # generator air brakes: applied by air (50 psi at least), only below 30 % speed; springs release them
    P.set(brake, NOT(hbr.r) * step(air.r, 50) * OR(BRK, below(N, 30)))

    # ------------------------------------------------------------ annunciator
    alarm = m.ent('logic_relay', 'alarm', spawnflags=2, StartDisabled=1)
    alarm.out('OnTrigger', 's_horn', 'PlaySound').out('OnTrigger', 's_relay', 'PlaySound').out('OnTrigger', horn_t.ent, 'SetValue', 6)
    P.add(horn_t, -dt * step(horn_t.r, 0.001))
    horn_t.on_fall('s_horn', 'StopSound')
    keep = NOT(rst.r)
    win = {}
    for key, c in causes.items():
        win[key] = c
    lit = {
        'lock': TR,
        'gbkr': None,                    # latched below
        'bth': step(bt.r, 76), 'vib': CB * step(G, 25) * below(G, 50),
        'hyd': below(hp.r, 240), 'oilp': NOT(lube.r), 'watp': NOT(cool.r), 'air': below(air.r, 50),
        'brk': BRK, 'rhi': step(lv.r, 7.5), 'rlo': below(lv.r, 6.25), 'spill': step(sg.r, 0.01),
        'plc': NOT(plc.r), 'avr': NOT(avr.r)}
    for i, (key, legend, kind) in enumerate(ANN_WINDOWS):
        f = P.flag(f'w_{key}')
        if key in causes:                                          # trips latch until the reset
            P.set(f, OR(causes[key], f.r * keep))
        elif key == 'gbkr':                                        # 52G opened by protection
            P.set(f, OR(CB * TR, f.r * keep * NOT(close)))
        else:
            P.set(f, lit[key])
        e = m.ent('func_brush', f'A{i:02d}', StartDisabled=1, Solidity=1)
        f.on_rise(e, 'Enable').on_fall(e, 'Disable')
        if kind != 'status':
            f.on_rise(alarm, 'Trigger')
        dev['windows'].append({'ent': e, 'legend': legend, 'kind': kind})

    # ------------------------------------------------------------ lamps
    lamp('LP_cb', cb, ('red', 'green'))
    lamp('LP_exc', exc, ('red', 'green'))
    lamp('LP_brake', brake, ('red', 'green'))
    lamp('L_perm', perm, ('green', None))

    # ------------------------------------------------------------ needles
    needle('p_volts', V / 125)                              # 0-600 V
    needle('p_kw', Pe * PBASE / 320)                        # 0-320 kW
    pf_ang = pwl(Qe / clamp(Pe, 0.03, None), ATAN_PTS)
    needle('p_pf', sel(CB, 0.5 + clamp(pf_ang, -60, 60) / 120, 0.5))
    needle('p_speed', N / 150)
    needle('p_gate', G / 100)
    needle('p_exc', X / 120)                                # 0-5 A
    needle('p_fa', 1 - k_of(EXC * u_cmd))                   # firing angle 0-90 deg
    hz = (0.6 * N - 54) / 12                                # 54-66 Hz
    needle('p_hz', hz)
    needle('p_sfreq', sel(CB, 0.5, hz))                     # the station bus: the grid's on line, the unit's off
    needle('p_lube', lp.r / 60)
    needle('p_cw', cw.r / 100)
    needle('p_bt', (bt.r - 20) / 80)
    needle('p_vib', sel(CB, pwl(G, VIB_PTS), 3) / 20)
    needle('p_opu', hp.r / 400)
    needle('p_air', air.r / 150)
    needle('p_hw', lv.r / 10)
    needle('p_rq', 0.9 * q.r / 120)
    needle('p_spill', sg.r / 1.2)

    # ------------------------------------------------------------ sounds
    # the turbine's pitch follows its speed and its loudness the water through it; the generator hums
    # louder with volts and load; the pump and the compressor run when their pressure switches call
    P.set(ph, ph.r + 1 - 4 * step(ph.r, 3))
    slow = below(ph.r, 0.5)
    P.sink('s_turb', 'Pitch', gate(clamp(N, 25, 150), slow, 0, 255))
    P.sink('s_turb', 'Volume', gate(clamp(1.5 + 0.06 * qt + 2 * w, 0, 10), slow, 0, 10))
    P.sink('s_water', 'Volume', gate(clamp(0.5 + 0.11 * qt, 0, 10), slow, 0, 10))
    P.sink('s_hum', 'Volume', gate(clamp(0.035 * V + 6 * relu(Pe), 0, 10), slow, 0, 10))
    for nm, cond in (('s_turb', spin), ('s_water', step(G, 0.5)), ('s_hum', step(V, 3)),
                     ('s_pump', hpu.r), ('s_comp', comp.r)):
        f = P.flag(f'snd_{nm}')
        P.set(f, cond)
        r_on, r_off = armed_relay(f'{nm}_on'), armed_relay(f'{nm}_off')
        f.on_rise(r_on, 'Trigger'); f.on_fall(r_off, 'Trigger')
        r_on.out('OnTrigger', nm, 'PlaySound'); r_off.out('OnTrigger', nm, 'StopSound')
    brk_r = armed_relay('s_brk_r')
    cb.on_rise(brk_r, 'Trigger').on_fall(brk_r, 'Trigger')
    brk_r.out('OnTrigger', 's_brk', 'PlaySound')

    P.compile()
    # arm the sounds and the horn once the first ticks have set every flag
    for e in m.ents:
        if e.cls == 'logic_relay' and (e.name == 'alarm' or e.name.endswith(('_on', '_off', '_brk_r'))):
            P_auto = m['pl_auto']
            P_auto.out('OnMapSpawn', e, 'Enable', None, 1.0)
    return m, P, dev


BIGT = 1.0e4


if __name__ == '__main__':
    from collections import Counter
    m, P, dev = build()
    c = Counter(e.cls for e in m.ents)
    net = sum(v for k, v in c.items() if k not in ('math_counter', 'math_remap', 'logic_relay', 'logic_timer', 'logic_auto'))
    print(len(m.ents), 'entities:', len(m.ents) - net, 'logic (no network slot),', net, 'networked')
    for k, v in c.most_common():
        print(f'  {k:22s} {v}')
    print('deepest level', max(b for a, b in P.levels.values()))
