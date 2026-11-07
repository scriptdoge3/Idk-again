"""
Sable Creek Unit 1 for plain Half-Life: the plant as entity logic.

The unit is run by hand from 13 controls:
  left (unit control)  wicket gate trip (the emergency stop), synchroscope, 41 field and 52G sync breakers,
                       firing-angle dial, wicket gate dial, brake dial
  middle (annunciator) PLC and AVR breakers
  right (auxiliaries)  lube oil pump, cooling water pump, gate servo oil pump, brake air compressor
With the PLC on it runs the gate (speed off line, pond level on line); with the AVR on it runs the field.

Every number is a game_counter variable. A clock made of two multi_managers runs the rules; each rule is
a chain of game_counter_set entities locked by multisource masters that read env_global flags.

Scales (one step of each variable):
  n  speed        1 % of 100 rpm   (100 = synchronous, 140 = overspeed trip)
  g  wicket gate  1 %              (15 = speed-no-load)
  v  voltage      1 % of 480 V
  x  field        1 % of rated field current, set by the thyristor firing angle
  o  servo oil    10 psi above 200 psi (10 = 300 psi)
  a  brake air    12.5 psi (brakes release at 4 = 50 psi)
  bt bearing temp 10 C above 20 C (8 = alarm, 10 = trip)
  l  pond level   0.25 ft above EL 510.0 (12 = 513.0 ft normal)
  sg spill gate   0.5 ft
Difference variables (only their sign is needed):
  en  = T(g) - n          speed error: T is the speed the runner settles at for gate g
  dvn = n - v             the generator can't make more volts than its speed allows
  dvx = x - v             off line, the volts follow the field
  el  = river - g - 15 sg pond balance (in % of full-gate discharge)
"""
import math
from hlogic import Logic, USE_ON, USE_OFF, USE_TOGGLE, vname

def _interp(pts, x):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


# runner equilibrium speed (%) for each gate %: speed-no-load at 15 % gate, about 5 % speed per 1 % gate
# around it (so a notch of the handwheel is a small correction), runaway near 175 %
T = [round(_interp([(0, 0), (2, 0), (5, 30), (10, 70), (15, 100), (20, 120), (25, 132), (30, 140), (40, 152),
                    (55, 163), (75, 171), (100, 175)], g)) for g in range(101)]
# electrical kW on line at 40 ft for each gate % (Euler runner model; zero at speed-no-load)
_KW5 = [0, 0, 0, 27, 50, 72, 94, 115, 135, 152, 169, 184, 199, 211, 223, 233, 243, 251, 258, 264, 269]
_VIB5 = [0, 1, 3, 6, 6, 7, 8, 8, 7, 6, 4, 3, 2, 2] + [2] * 7       # shaft vibration, mils p-p (vortex rope)
_old = lambda g: (10 + (g - 15) * 90 / 85) / 5 if g >= 15 else g / 15 * 2      # gate % -> the 5 % table index
KW = [round(_interp(list(enumerate(_KW5)), _old(g))) for g in range(101)]
VIB = [_interp(list(enumerate(_VIB5)), _old(g)) for g in range(101)]

RIVER0 = 75                     # normal river flow, % of full-gate discharge
INIT = dict(n=0, g=0, v=0, x=0, o=0, a=0, bt=2, l=12, sg=5)
VARS = dict(n=(0, 145), g=(0, 100), v=(0, 120), x=(0, 120), o=(0, 10), a=(0, 10), bt=(0, 10), l=(0, 16), sg=(0, 8))
ANN = ['OVERSPEED|TRIP', 'WICKET GATE|TRIPPED', 'OUT OF PHASE|CLOSE', 'GEN BREAKER|PROT TRIP',
       'SERVO OIL|PRESS LOW', 'LUBE OIL|PUMP OFF', 'BEARING|TEMP HIGH', 'COOLING WATER|PUMP OFF',
       'BRAKE AIR|PRESS LOW', 'BRAKES|APPLIED', 'DRAFT TUBE|PULSATION', 'POND LEVEL|HIGH',
       'POND LEVEL|LOW', 'SPILLWAY|GATE OPEN', 'PLC OFF|GATE MANUAL', 'AVR OFF|FIELD MANUAL']
TRIP_WINDOWS = (0, 1, 2, 3, 4, 5, 6, 7, 8)   # red windows: trips and things that will cause one
# synchroscope pointer path: a hexagon of path_corners (radius R, one turn in 6 s); the corners at 11 and
# 1 o'clock open and close the in-phase window. The train starts at the first corner.
SCOPE = {'R': 5.4, 'speed': 5.4, 'corners': [(-30, 'sc_in'), (30, 'sc_out'), (90, None), (150, None), (210, None), (270, None)]}


def _build(L):
    dev = {'lamps': [], 'ptrs': [], 'rots': [], 'walls': [], 'sounds': [], 'ann': ANN, 'knobs': []}
    fi = {}

    def flag(name, init):
        L.flag(name, init); fi[name] = init

    def state(name, init):
        flag(name, init)
        L.setf(f'{name}=1', name, 1)
        L.setf(f'{name}=0', name, 0)

    def thr(var, k, name=None):
        name = name or f'{var}_ge{k}'
        flag(name, int(INIT.get(var, 0) >= k))
        L.setf(vname(var, k), name, 1)
        L.setf(vname(var, k - 1), name, 0)
        return name

    # --------------------------------------------------------- variables
    for k, (lo, hi) in VARS.items():
        L.var(k, lo, hi, INIT[k])
    dinit = dict(en=T[INIT['g']] - INIT['n'], dvn=INIT['n'] - INIT['v'], dvx=INIT['x'] - INIT['v'],
                 el=RIVER0 - INIT['g'] - 15 * INIT['sg'])
    for k, v0 in dinit.items():
        L.var(k, -1, 1, v0, values=[-20, -19, -5, -4, -1, 0, 1, 4, 5, 19, 20] if k == 'en' else [-1, 0, 1])
        flag(f'{k}_pos', int(v0 > 0)); flag(f'{k}_neg', int(v0 < 0))
        L.setf(vname(k, 1), f'{k}_pos', 1); L.setf(vname(k, 0), f'{k}_pos', 0)
        L.setf(vname(k, -1), f'{k}_neg', 1); L.setf(vname(k, 0), f'{k}_neg', 0)
    # how far speed is from where the gate would settle it: beyond 20 % (hi / lo) and beyond 5 % (md / ml)
    for fl, a_, b_ in (('en_hi', 20, 19), ('en_md', 5, 4), ('en_lo', -20, -19), ('en_ml', -5, -4)):
        flag(fl, 0); L.setf(vname('en', a_), fl, 1); L.setf(vname('en', b_), fl, 0)

    for name, init in [('cb', 0), ('exc', 0), ('tr', 0), ('brake', 1), ('scr', 0),
                       ('inph', 1), ('rz', 0)]:
        state(name, init)
    flag('gdir', 1)
    for nm in ('lube', 'cool', 'plc', 'avr'):
        flag(nm, 0)
    thr('n', 1, 'n_gt0'); thr('n', 50); thr('n', 90); thr('n', 99); thr('n', 102); thr('n', 145, 'n_max')
    thr('g', 1, 'g_gt0'); thr('g', 13); thr('g', 15); thr('g', 16); thr('g', 17); thr('g', 25); thr('g', 26)
    thr('g', 100, 'g_max')
    thr('v', 1, 'v_gt0'); thr('v', 95); thr('v', 106); thr('v', 120, 'v_max')
    thr('x', 1, 'x_gt0'); thr('x', 60); thr('x', 100); thr('x', 101); thr('x', 104); thr('x', 106); thr('x', 120, 'x_max')
    thr('o', 1, 'o_gt0'); thr('o', 2); thr('o', 3); thr('o', 4); thr('o', 10, 'o_full')
    thr('a', 1, 'a_gt0'); thr('a', 4); thr('a', 10, 'a_max')
    thr('bt', 3); thr('bt', 5); thr('bt', 6); thr('bt', 8); thr('bt', 10, 'bt_max')
    thr('l', 1, 'l_gt0'); thr('l', 9, 'l_ok'); thr('l', 11); thr('l', 12); thr('l', 13); thr('l', 14); thr('l', 16, 'l_max')
    thr('sg', 1, 'sg_gt0'); thr('sg', 8, 'sg_max')

    # ------------------------------------------------- coupled increments
    L.inc_listener('n', 'up', 'en_c', USE_OFF); L.inc_listener('n', 'dn', 'en_c', USE_ON)
    L.inc_listener('n', 'up', 'dvn_c', USE_ON); L.inc_listener('n', 'dn', 'dvn_c', USE_OFF)
    L.inc_listener('v', 'up', 'dvn_c', USE_OFF); L.inc_listener('v', 'dn', 'dvn_c', USE_ON)
    L.inc_listener('v', 'up', 'dvx_c', USE_OFF); L.inc_listener('v', 'dn', 'dvx_c', USE_ON)
    L.inc_listener('x', 'up', 'dvx_c', USE_ON); L.inc_listener('x', 'dn', 'dvx_c', USE_OFF)
    made = set()

    def adder(prefix, counter, k, state):
        """Relay group `<prefix><k>` that steps `counter` k times, built from power-of-two subgroups."""
        name = f'{prefix}{k}'
        if name not in made:
            made.add(name)
            if k == 1:
                L.relay(name, counter, state)
            else:
                p = 1 << (k.bit_length() - 1)
                parts = [p // 2, p // 2] if p == k else [p, k - p]
                for q in parts:
                    L.relay(name, adder(prefix, counter, q, state), USE_ON)
        return name

    L.inc_listener('g', 'up', 'el_c', USE_OFF); L.inc_listener('g', 'dn', 'el_c', USE_ON)
    L.inc_listener('sg', 'up', adder('el_sub', 'el_c', 15, USE_OFF), USE_ON)     # a spill step is 15 % of full gate
    L.inc_listener('sg', 'dn', adder('el_add', 'el_c', 15, USE_ON), USE_ON)
    L.dir_flag('g', 'gdir')
    # T(g) lookup: arriving at gate % v adds T(v)-T(v-1) to en; leaving it downward removes it
    for v in range(1, 101):
        dT = T[v] - T[v - 1]
        if dT:
            L.rule(vname('g', v), ['gdir'], adder('en_add', 'en_c', dT, USE_ON))
            L.rule(vname('g', v - 1), ['!gdir'], adder('en_sub', 'en_c', dT, USE_OFF))
    # every 20 % of gate travel draws 10 psi from the servo oil accumulator
    L.inc_listener('g', 'up', 'opu_use', USE_ON); L.inc_listener('g', 'dn', 'opu_use', USE_ON)
    L.add('game_counter', targetname='opu_use', frags=0, health=20, spawnflags=2, target='opu_draw')
    L.rule('opu_draw', ['o_gt0'], 'o_dn')

    # ---------------------------------------------------------------- clock
    L.add('trigger_auto', target='init', delay=0.4, triggerstate=1)
    L.add('trigger_auto', target='clkA', delay=1.2, triggerstate=2)
    L.add('multi_manager', targetname='clkA', keys={'TK': 0, 'clkB': 0.05})
    L.add('multi_manager', targetname='clkB', keys={'TK': 0, 'clkA': 0.05})
    L.add('game_counter', targetname='TK', frags=0, health=2, spawnflags=2, target='TS')     # 0.1 s
    L.add('game_counter', targetname='TS', frags=0, health=2, spawnflags=2, target='TS2')    # 0.2 s
    L.add('game_counter', targetname='TS2', frags=0, health=2, spawnflags=2, target='TS4')   # 0.4 s
    L.add('game_counter', targetname='TS', frags=0, health=5, spawnflags=2, target='T1')     # 0.5 s
    L.add('game_counter', targetname='T1', frags=0, health=2, spawnflags=2, target='T2')
    L.add('game_counter', targetname='T2', frags=0, health=4, spawnflags=2, target='T8')
    L.add('game_counter', targetname='T8', frags=0, health=2, spawnflags=2, target='T16')

    # ------------------------------------------------------------- devices
    def lamp(name, flg, colors):
        """colors = (when flag==1, when flag==0); None = dark. Frame 0 shows the initial state."""
        init = fi[flg]
        dev['lamps'].append({'name': name, 'colors': colors, 'init': init})
        L.follow(flg, name, 1 - init)
        return name

    def ptr(name):
        dev['ptrs'].append(name)
        return name

    def display(var, target, fn, vals=None, conds=()):
        lo, hi = VARS[var]
        vals = list(vals) if vals is not None else list(range(lo, hi + 1))
        for x in vals:
            y = fn(x)
            nb = [fn(z) for z in (x - 1, x + 1) if lo <= z <= hi]
            if nb and all(abs(y - z) < 1e-6 for z in nb):
                continue
            L.display(vname(var, x), target, y, conds)

    def cs(name, flg, label, pos, grip='black', lamp=None):
        """Control switch: pistol grip, maintained, two positions. Each turn fires `<name>_ev`, which
        toggles `flg` (1 = right-hand position). The logic may turn the handle itself (by firing it).
        lamp = (name, colors): a RUN/STOP lamp pair that follows the handle."""
        flag(flg, 0)
        L.toggle_flag(f'{name}_ev', flg)
        d = {'name': name, 'target': f'{name}_ev', 'label': label, 'pos': pos, 'kind': 'cs', 'grip': grip,
             'distance': 90, 'speed': 240, 'wait': 0.5, 'toggle': True}
        if lamp:
            dev['lamps'].append({'name': lamp[0], 'colors': lamp[1], 'init': 0})
            L.relay(f'{name}_ev', lamp[0], USE_TOGGLE)
            d['lamp'] = lamp[0]
        dev['rots'].append(d)

    def selector(name, flg, label, pos):
        flag(flg, 0)
        L.toggle_flag(f'{name}_ev', flg)
        dev['rots'].append({'name': name, 'target': f'{name}_ev', 'label': label, 'pos': pos, 'kind': 'sel',
                            'distance': 90, 'speed': 240, 'wait': 0.5, 'toggle': True})

    def knob(name, var, up, dn, step, label, wheel=False):
        """momentary_rot_button turned by holding USE. It fires its target every frame while turning;
        the logic steps `var` on the `step` clock while that happens. Each new turn reverses (stock
        Half-Life behaviour); the logic sees the turn end as two quiet 0.05 s ticks and flips its
        direction flag, shown on a lamp."""
        ev = f'{name}_ev'
        flag(f'{name}_a', 0); flag(f'{name}_u', 1)
        L.setf(ev, f'{name}_a', 1)                                           # turning this step
        L.add('game_counter_set', targetname=ev, target=f'{name}_ic', frags=0)
        L.add('game_counter', targetname=f'{name}_ic', frags=9, health=2, target=f'{name}_end')
        L.relay('TK', f'{name}_ic', USE_ON)                                  # quiet ticks
        L.setf(f'{name}_end', f'{name}_a', 0)           # a step still pending when the turn ends is dropped
        L.toggle_flag(f'{name}_end', f'{name}_u')
        lamp_nm = f'L_{name}'
        dev['lamps'].append({'name': lamp_nm, 'colors': ('amber', 'amber'), 'init': 1})
        L.relay(f'{name}_end', lamp_nm, USE_TOGGLE)
        L.rule(step, [f'{name}_a', f'{name}_u'] + up, f'{var}_up')
        L.rule(step, [f'{name}_a', f'!{name}_u'] + dn, f'{var}_dn')
        L.late('env_global', targetname=step, globalstate=f'{name}_a', triggermode=0)
        dev['knobs'].append({'name': name, 'target': ev, 'label': label, 'wheel': wheel, 'lamp': lamp_nm})

    W = [f'A{i:02d}' for i in range(16)]
    dev['walls'] += W + ['SYNCLAMPS']
    L.relay('alarm', 's_horn', USE_ON); L.relay('alarm', 's_relay', USE_ON)
    L.add('trigger_relay', targetname='alarm', target='s_horn', triggerstate=0, delay=6)   # the horn silences itself

    def alarm(event, win=None):
        if win:
            L.relay(event, win, USE_ON)
        L.relay(event, 'alarm')

    # ------------------------------------------------- gauges
    # needles move in 1 % steps where they are read closely, 2-4 % elsewhere (each position is two entities)
    display('n', ptr('p_speed'), lambda x: x / 150, vals=list(range(0, 70, 2)) + list(range(70, 146)))
    display('g', ptr('p_gate'), lambda x: x / 100, vals=list(range(0, 41)) + list(range(42, 101, 2)))
    display('g', ptr('p_kw'), lambda x: KW[x] / 320, vals=list(range(13, 101, 2)), conds=['cb'])
    display('g', ptr('p_vib'), lambda x: VIB[x] / 20, vals=list(range(0, 101, 5)), conds=['cb'])
    display('v', ptr('p_volts'), lambda x: x / 125, vals=list(range(0, 72, 4)) + list(range(72, 121)))
    fx = list(range(0, 68, 4)) + list(range(68, 121, 2))
    display('x', ptr('p_exc'), lambda x: x / 120, vals=fx)
    # thyristor firing angle: field current goes as cos(alpha); 90 deg = no field, 0 deg = full field (x = 120)
    display('x', ptr('p_fa'), lambda x: math.degrees(math.acos(x / 120)) / 90, vals=fx)
    display('x', ptr('p_kvar'), lambda x: 0.5 + (x - 100) / 80, vals=list(range(60, 121, 2)), conds=['cb'])
    display('o', ptr('p_opu'), lambda x: (200 + 10 * x) / 400, vals=[0, 2, 4, 6, 8, 10])
    display('a', ptr('p_air'), lambda x: 12.5 * x / 150, vals=[0, 2, 4, 6, 8, 10])
    display('bt', ptr('p_bt'), lambda x: x / 10)
    display('l', ptr('p_hw'), lambda x: (1 + 0.25 * x) / 6)
    display('sg', ptr('p_spill'), lambda x: x / 8)
    for p, flg, ev, val in (('p_lube', 'lube', 'r_lp_ev', 0.6), ('p_cw', 'cool', 'r_wp_ev', 0.62)):
        ptr(p)
        L.display(ev, p, val, [flg]); L.display(ev, p, 0.0, [f'!{flg}'])

    dev['sounds'] += [
        {'name': 's_turb', 'wav': 'sablecreek/turbine.wav', 'vol': 8, 'loop': True},
        {'name': 's_water', 'wav': 'sablecreek/water.wav', 'vol': 6, 'loop': True},
        {'name': 's_hum', 'wav': 'sablecreek/hum.wav', 'vol': 5, 'loop': True},
        {'name': 's_horn', 'wav': 'sablecreek/horn.wav', 'vol': 7, 'loop': True},
        {'name': 's_pump', 'wav': 'sablecreek/pump.wav', 'vol': 4, 'loop': True},
        {'name': 's_brk', 'wav': 'sablecreek/breaker.wav', 'vol': 10, 'loop': False},
        {'name': 's_relay', 'wav': 'sablecreek/relay.wav', 'vol': 9, 'loop': False},
    ]
    # turbine sound pitch follows speed (ambient_generic accepts USE_SET as pitch)
    display('n', 's_turb', lambda x: max(0.02, x / 255), vals=[5, 25, 50, 70, 85, 100, 110, 125])
    L.relay(vname('n', 1), 's_turb', USE_ON); L.relay(vname('n', 0), 's_turb', USE_OFF)
    L.relay(vname('g', 1), 's_water', USE_ON); L.relay(vname('g', 0), 's_water', USE_OFF)
    L.relay(vname('v', 1), 's_hum', USE_ON); L.relay(vname('v', 0), 's_hum', USE_OFF)

    # ---------------------------------------------- panel 1: auxiliaries
    for nm, flg, label in (('r_lp', 'lube', 'LUBE OIL PUMP'), ('r_wp', 'cool', 'COOLING WATER PUMP'),
                           ('r_hp', 'hhp', 'SERVO OIL PUMP'), ('r_ac', 'hac', 'AIR COMPRESSOR')):
        cs(nm, flg, label, ('STOP', 'RUN'))          # a maintained pump switch: the handle shows the state
    L.relay('r_hp_ev', 's_pump', USE_TOGGLE)
    L.relay('r_lp_ev', W[5], USE_TOGGLE); L.relay('r_wp_ev', W[7], USE_TOGGLE)    # PUMP OFF windows
    # bearings: no lube oil wipes them in seconds, no cooling water cooks them in about a minute
    L.rule('T2', ['n_gt0', '!lube', '!bt_max'], 'bt_up')
    L.rule('T8', ['n_ge50', '!cool', '!bt_max'], 'bt_up')
    L.rule('T8', ['n_ge50', '!bt_ge5'], 'bt_up')                      # normal running temperature 70 C
    L.rule('T8', ['cool', 'bt_ge6'], 'bt_dn')
    L.rule('T8', ['!n_ge50', 'bt_ge3'], 'bt_dn')
    alarm(vname('bt', 8))
    # servo oil (wicket gate servomotors)
    L.rule('T1', ['hhp', '!o_full'], 'o_up')
    L.rule('T16', ['o_gt0'], 'o_dn')                                  # pilot-valve leakage
    # brake air; the brakes are spring-applied and air-released
    L.rule('T1', ['hac', '!a_max'], 'a_up')
    L.rule('T16', ['a_gt0'], 'a_dn')
    L.rule('T8', ['!brake', 'a_gt0'], 'a_dn')                         # released brakes leak a little more

    # ------------------------------------------------------- protection
    # 'prot' trips the unit: the gate closes fast, 41 and 52G open, and the gate-trip handle flips to TRIP.
    L.relay('prot', 'tr=1'); L.relay('prot', 'exc=0')
    L.rule('prot', ['cb'], 'cb_prot')
    alarm('prot')
    L.rule('TS', ['tr', 'g_gt0'], 'g_dn')                             # emergency closing, 10 %/s
    L.relay(vname('n', 140), 'prot'); alarm(vname('n', 140), W[0])        # overspeed, 140 %
    L.rule('T1', ['bt_max', '!tr'], 'prot')
    L.rule('T1', ['g_gt0', '!o_ge2', '!tr'], 'prot')                  # servo oil gone with the gate open
    L.rule(vname('v', 115), ['!cb'], 'prot')                          # overvoltage, 115 %
    L.rule(vname('l', 3), ['n_gt0'], 'prot')                          # the intake would draw air
    # wicket gate trip: the emergency stop and the lockout in one handle. Turning it to TRIP trips the unit;
    # protection turns it to TRIP; turning it back to NORMAL resets (it trips again if the cause is still there).
    cs('r_gt', 'hgt', 'WICKET GATE TRIP', ('NORMAL', 'TRIP'), grip='red')
    L.rule('r_gt_ev', ['hgt', '!tr'], 'prot')
    L.rule('r_gt_ev', ['!hgt'], 'reset')
    L.rule('T1', ['tr', '!hgt'], 'r_gt')
    L.relay('reset', 'tr=0')
    for i in (0, 2, 3):
        L.relay('reset', W[i], USE_OFF)

    # ---------------------------------------------------------- brakes
    selector('r_br', 'hbr', 'BRAKES', ('APPLY', 'RELEASE'))            # a rotary dial
    L.rule('T1', ['hbr', 'a_ge4', 'brake'], 'brake=0')
    L.rule('T1', ['!hbr', '!brake'], 'brake=1')
    L.rule('T1', ['!a_ge4', '!brake'], 'brake=1')

    # ---------------------------------------------------------------- speed
    # the runner accelerates hard when far from the speed the gate would settle it at, then eases in:
    # 5 %/s beyond 20 % away, 2.5 %/s within 20 %, 1 %/s for the last 5 %
    L.rule('TS2', ['!cb', 'en_hi', '!n_max', '!brake'], 'n_up')
    L.rule('TS4', ['!cb', 'en_md', '!en_hi', '!n_max', '!brake'], 'n_up')
    L.rule('T2', ['!cb', 'en_pos', '!en_md', '!n_max', '!brake'], 'n_up')
    L.rule('TS2', ['!cb', 'en_lo', 'g_gt0', 'n_gt0', '!brake'], 'n_dn')
    L.rule('TS4', ['!cb', 'en_ml', '!en_lo', 'g_gt0', 'n_gt0', '!brake'], 'n_dn')
    L.rule('T2', ['!cb', 'en_neg', '!en_ml', 'g_gt0', 'n_gt0', '!brake'], 'n_dn')
    L.rule('TS4', ['!cb', 'en_neg', '!g_gt0', 'n_gt0', '!brake'], 'n_dn')      # coasting, 2.5 %/s
    L.rule('TS2', ['!cb', 'brake', 'n_gt0'], 'n_dn')                           # air brakes, 5 %/s

    # ------------------------------------------------------------- wicket gate
    knob('k_gate', 'g', ['!plc', '!tr', '!g_max', 'o_ge3'], ['!plc', '!tr', 'g_gt0', 'o_gt0'], 'TS', 'WICKET GATE', wheel=True)
    # PLC: off line it acts as the governor (open to 25 %, then hold speed-no-load), on line it holds the pond
    base = ['plc', '!cb', '!tr', 'o_ge3', '!brake']
    L.rule('TS', base + ['!n_ge90', '!g_ge25'], 'g_up')
    L.rule('TS', base + ['!n_ge90', 'g_ge26'], 'g_dn')
    L.rule('TS', base + ['n_ge90', 'g_ge16'], 'g_dn')
    L.rule('TS', base + ['n_ge90', '!g_ge15'], 'g_up')
    L.rule('TS', ['plc', '!cb', '!tr', 'brake', 'g_gt0', 'o_gt0'], 'g_dn')   # brakes applied: the PLC shuts the gate
    lc = ['plc', 'cb', '!tr', 'o_ge3']
    L.rule('T1', lc + ['l_ge13', 'el_pos', '!g_max'], 'g_up')
    L.rule('T1', lc + ['!l_ge12', 'el_neg', 'g_ge17'], 'g_dn')
    L.rule('T8', lc + ['l_ge14', '!g_max'], 'g_up')
    L.rule('T8', lc + ['!l_ge11', 'g_ge17'], 'g_dn')
    cs('r_plc', 'plc', 'PLC', ('OFF', 'ON'))
    L.relay('r_plc_ev', W[14], USE_TOGGLE)

    # ----------------------------------------------------------- excitation
    cs('r_exc', 'hexc', '41 FIELD BREAKER', ('OPEN', 'CLOSE'))
    L.rule('r_exc_ev', ['hexc', '!tr'], 'exc=1')
    L.rule('r_exc_ev', ['!hexc'], 'exc=0')
    L.rule('T1', ['hexc', '!exc'], 'r_exc')                          # refused or tripped: handle back to OPEN
    L.rule('TS', ['!exc', 'x_gt0'], 'x_dn')                          # the field discharges, 10 %/s
    knob('k_fa', 'x', ['exc', '!avr', '!x_max'], ['exc', '!avr', 'x_gt0'], 'TS', 'FIRING ANGLE')
    # AVR: rated field off line (100 % volts at speed), a little more on line (slightly lagging)
    L.rule('TS', ['avr', 'exc', '!x_ge100'], 'x_up')
    L.rule('TS', ['avr', 'exc', '!cb', 'x_ge101'], 'x_dn')
    L.rule('TS', ['avr', 'exc', 'cb', '!x_ge104'], 'x_up')
    L.rule('TS', ['avr', 'exc', 'x_ge106'], 'x_dn')
    cs('r_avr', 'avr', 'AVR', ('MAN', 'AUTO'))
    L.relay('r_avr_ev', W[15], USE_TOGGLE)
    # off line the volts follow the field, limited by speed; on line the grid holds them
    L.rule('TS', ['!cb', 'dvn_pos', 'dvx_pos', '!v_max'], 'v_up')      # 10 %/s
    L.rule('TS', ['!cb', 'dvn_neg', 'v_gt0'], 'v_dn')
    L.rule('TS', ['!cb', 'dvx_neg', '!dvn_neg', 'v_gt0'], 'v_dn')     # (exclusive: one step down per tick)

    # ------------------------------------------------------ synchronizing
    # synchroscope: a func_train pointer circling behind the bezel. It turns while the switch is on, the
    # field is on and the unit is within 1 % of synchronous speed. Its path corners at 11 and 1 o'clock
    # fire the in-phase window, so what you see is what the sync check uses.
    cs('r_ss', 'hss', 'SYNCHROSCOPE', ('OFF', 'ON'))
    L.rule('T1', ['hss', 'exc', 'n_ge99', '!n_ge102', '!cb', '!scr'], 'scope_on')
    for c in ('!hss', '!exc', '!n_ge99', 'n_ge102', 'cb'):
        L.rule('T1', ['scr', c], 'scope_off')
    L.relay('scope_on', 'scr=1'); L.relay('scope_on', 'SCOPE', USE_TOGGLE)
    L.rule('scope_on', ['!inph'], 'sl_on')
    L.rule('scope_off', ['scr'], 'scope_off_x')
    L.relay('scope_off_x', 'scr=0'); L.relay('scope_off_x', 'SCOPE', USE_TOGGLE); L.relay('scope_off_x', 'SYNCLAMPS', USE_OFF)
    L.relay('sc_in', 'inph=1'); L.relay('sc_in', 'SYNCLAMPS', USE_OFF)          # dark lamps: in phase
    L.relay('sc_out', 'inph=0'); L.rule('sc_out', ['scr'], 'sl_on')
    L.relay('sl_on', 'SYNCLAMPS', USE_ON)
    # 52G: closing needs the synchroscope switch (sync check). Closing outside the window, off speed or
    # with the wrong voltage is an out-of-phase close, and protection trips the unit.
    cs('r_52', 'h52', '52G SYNC BREAKER', ('TRIP', 'CLOSE'))
    ok = ['h52', 'hss', '!tr', '!cb']
    L.rule('r_52_ev', ok + ['scr', 'inph', 'v_ge95', '!v_ge106'], 'cb_close')
    L.rule('r_52_ev', ok + ['!scr'], 'oop')
    L.rule('r_52_ev', ok + ['scr', '!inph'], 'oop')
    L.rule('r_52_ev', ok + ['scr', 'inph', '!v_ge95'], 'oop')
    L.rule('r_52_ev', ok + ['scr', 'inph', 'v_ge106'], 'oop')
    L.rule('r_52_ev', ['!h52'], 'cb_open')
    L.rule('T1', ['h52', '!cb'], 'r_52')                           # not closed (refused or tripped): back to TRIP
    L.relay('oop', 'prot'); alarm('oop', W[2])
    L.relay('cb_close', 'cb=1'); L.relay('cb_close', 's_brk', USE_ON); L.relay('cb_close', W[3], USE_OFF)
    L.relay('cb_close', 'x_dn'); L.relay('cb_close', 'x_up')      # re-send the field value to the kvar meter
    L.rule('cb_open', ['cb'], 'cb_open_x')
    L.rule('cb_prot', ['cb'], 'cb_prot_x')
    L.relay('cb_prot_x', 'cb_open_x'); alarm('cb_prot_x', W[3])
    L.relay('cb_open_x', 'cb=0'); L.relay('cb_open_x', 'rz=0'); L.relay('cb_open_x', 's_brk', USE_ON)
    L.display('cb_open_x', 'p_kw', 0.0); L.display('cb_open_x', 'p_vib', 3.0 / 20); L.display('cb_open_x', 'p_kvar', 0.5)
    L.rule('T1', ['cb', '!g_ge13'], 'cb_prot')                    # reverse power (32): the unit is motoring
    L.rule('T1', ['cb', '!x_ge60'], 'cb_prot')                    # loss of field (40): below 60 %

    # ----------------------------------------------------------------- pond
    L.rule('T8', ['el_pos', '!l_max'], 'l_up')
    L.rule('T8', ['el_neg', 'l_gt0'], 'l_dn')
    # spillway (automatic): open above 513.5 ft while the pond still rises, close below 513.25 ft while it falls
    L.rule('T8', ['l_ge14', 'el_pos', '!sg_max'], 'sg_up')
    L.rule('T8', ['l_max', '!el_pos', '!sg_max'], 'sg_up')
    L.rule('T8', ['!l_ge13', 'el_neg', 'sg_gt0'], 'sg_dn')
    L.rule('T16', ['plc', 'cb', 'sg_gt0', '!g_max', '!l_ge14'], 'sg_dn')   # the PLC gives the water to the unit
    # draft-tube rope indication: on line between 25 and 50 % gate
    L.rule(vname('g', 26), ['cb', 'gdir'], 'rz=1'); L.rule(vname('g', 50), ['cb', '!gdir'], 'rz=1')
    L.rule(vname('g', 25), ['!gdir'], 'rz=0'); L.rule(vname('g', 51), ['gdir'], 'rz=0')

    # ---------------------------------------------------------- lamps, windows
    lamp('LP_cb', 'cb', ('red', 'green'))
    lamp('LP_brake', 'brake', ('red', 'green'))
    lamp('LP_exc', 'exc', ('red', 'green'))
    for i, flg, lit_when in [(1, 'tr', 1), (4, 'o_ge4', 0), (6, 'bt_ge8', 1),
                             (8, 'a_ge4', 0), (9, 'brake', 1), (10, 'rz', 1), (11, 'l_ge14', 1), (12, 'l_ok', 0),
                             (13, 'sg_gt0', 1)]:
        dev.setdefault('ann_init', {})[i] = int(fi[flg] == lit_when)
        L.follow(flg, W[i], 1 - fi[flg])
    for i, flg in ((5, 'lube'), (7, 'cool'), (14, 'plc'), (15, 'avr')):
        dev['ann_init'][i] = 1 - fi[flg]

    # --------------------------------------------------------------- init
    L.display('init', 'p_kvar', 0.5); L.display('init', 'p_vib', 0.02); L.display('init', 'p_fa', 1.0)
    for var, p, fn in [('l', 'p_hw', lambda x: (1 + 0.25 * x) / 6), ('sg', 'p_spill', lambda x: x / 8),
                       ('bt', 'p_bt', lambda x: x / 10)]:
        L.display('init', p, fn(INIT[var]))
    dev['flags_init'] = fi
    dev['scope'] = SCOPE
    return L.finalize(), dev


def build():
    p1 = Logic(used=None)
    _build(p1)
    L = Logic(used=p1.reads, events=p1.listened)
    ents, dev = _build(L)
    return L, ents, dev


if __name__ == '__main__':
    L, ents, dev = build()
    from collections import Counter
    c = Counter(e['classname'] for e in ents)
    print(len(ents), 'logic entities')
    for k, v in c.most_common():
        print(f'  {k:18s} {v}')
    print('devices:', {k: len(v) for k, v in dev.items() if isinstance(v, list)})
