"""
Sable Creek Unit 1 for plain Half-Life: the plant as entity logic.

The unit is run by hand from 15 controls:
  panel 1 (aux)        lube oil pumps 1 and 2, cooling water pumps 1 and 2, gate servo oil pump,
                       brake air compressor
  panel 2 (unit)       52G sync breaker, synchroscope switch, brake release, wicket gate trip (the emergency
                       stop), wicket gate handwheel
  panel 3 (exc / ann)  41 exciter field breaker, firing-angle knob, PLC and AVR selectors
With the PLC on it runs the gate (speed off line, pond level on line); with the AVR on it runs the field.

Every number is a game_counter variable. A clock made of two multi_managers runs the rules; each rule is
a chain of game_counter_set entities locked by multisource masters that read env_global flags.

Scales (one step of each variable):
  n  speed        5 % of 100 rpm   (20 = synchronous, 28 = overspeed trip)
  g  wicket gate  5 %
  v  voltage      5 % of 480 V
  x  field        5 % of rated field current (set by the thyristor firing angle)
  o  servo oil    10 psi above 200 psi (10 = 300 psi)
  a  brake air    12.5 psi (brakes release at 4 = 50 psi)
  bt bearing temp 10 C above 20 C (8 = alarm, 10 = trip)
  l  headwater    0.25 ft above EL 510.0 (12 = 513.0 ft normal)
  sg spill gate   0.5 ft
  h  water hammer 1 psi of spiral-case pressure rise
Difference variables (only their sign is needed):
  en  = T(g) - n          speed error: T is the speed the runner settles at for gate g
  dvn = n - v             the generator can't make more volts than its speed allows
  dvx = x - v             off line, the volts follow the field
  el  = river - g - 3 sg  pond balance
"""
from hlogic import Logic, USE_ON, USE_OFF, USE_TOGGLE, vname

# runner equilibrium speed (5 % steps) for each gate step: speed-no-load at 10 % gate, runaway near 175 %
T = [0, 10, 20, 24, 27, 29, 31, 32, 33, 34, 35] + [35] * 10
# electrical kW for each gate step at 40 ft (from the Euler runner model)
KW = [0, 0, 0, 27, 50, 72, 94, 115, 135, 152, 169, 184, 199, 211, 223, 233, 243, 251, 258, 264, 269]
# shaft vibration on line, mils p-p (draft-tube vortex rope between 20 and 45 % gate)
VIB = [0, 1, 3, 6, 6, 7, 8, 8, 7, 6, 4, 3, 2, 2] + [2] * 7

RIVER0 = 15
INIT = dict(n=0, g=0, v=0, x=0, o=0, a=0, bt=2, l=12, sg=5, h=0)
VARS = dict(n=(0, 28), g=(0, 20), v=(0, 24), x=(0, 24), o=(0, 10), a=(0, 10), bt=(0, 10), l=(0, 16), sg=(0, 8), h=(0, 6))
ANN = ['OVERSPEED|TRIP', 'WICKET GATE|TRIPPED', 'OUT OF PHASE|CLOSE', 'GEN BREAKER|PROT TRIP',
       'SERVO OIL|PRESS LOW', 'LUBE OIL|PUMPS OFF', 'BEARING|TEMP HIGH', 'COOLING WATER|PUMPS OFF',
       'BRAKE AIR|PRESS LOW', 'BRAKES|APPLIED', 'DRAFT TUBE|PULSATION', 'HEADWATER|HIGH',
       'HEADWATER|LOW', 'SPILLWAY|GATE OPEN', 'PLC OFF|GATE MANUAL', 'AVR OFF|FIELD MANUAL']
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
                 el=RIVER0 - INIT['g'] - 3 * INIT['sg'])
    for k, v0 in dinit.items():
        L.var(k, -1, 1, v0, values=[-1, 0, 1])
        flag(f'{k}_pos', int(v0 > 0)); flag(f'{k}_neg', int(v0 < 0))
        L.setf(vname(k, 1), f'{k}_pos', 1); L.setf(vname(k, 0), f'{k}_pos', 0)
        L.setf(vname(k, -1), f'{k}_neg', 1); L.setf(vname(k, 0), f'{k}_neg', 0)

    for name, init in [('cb', 0), ('exc', 0), ('tr', 0), ('brake', 1), ('lube', 0), ('cool', 0), ('scr', 0),
                       ('inph', 1), ('rz', 0)]:
        state(name, init)
    flag('gdir', 1)
    for nm in ('hlp1', 'hlp2', 'hwp1', 'hwp2', 'plc', 'avr'):
        flag(nm, 0)
    thr('n', 1, 'n_gt0'); thr('n', 10); thr('n', 18); thr('n', 20); thr('n', 21); thr('n', 28, 'n_max')
    thr('g', 1, 'g_gt0'); thr('g', 2); thr('g', 3); thr('g', 4); thr('g', 6); thr('g', 7); thr('g', 20, 'g_max')
    thr('v', 1, 'v_gt0'); thr('v', 19); thr('v', 22); thr('v', 24, 'v_max')
    thr('x', 1, 'x_gt0'); thr('x', 12); thr('x', 20); thr('x', 21); thr('x', 22); thr('x', 24, 'x_max')
    thr('o', 1, 'o_gt0'); thr('o', 2); thr('o', 3); thr('o', 4); thr('o', 10, 'o_full')
    thr('a', 1, 'a_gt0'); thr('a', 4); thr('a', 10, 'a_max')
    thr('bt', 3); thr('bt', 5); thr('bt', 6); thr('bt', 8); thr('bt', 10, 'bt_max')
    thr('l', 1, 'l_gt0'); thr('l', 9, 'l_ok'); thr('l', 11); thr('l', 12); thr('l', 13); thr('l', 14); thr('l', 16, 'l_max')
    thr('sg', 1, 'sg_gt0'); thr('sg', 8, 'sg_max')
    thr('h', 1, 'h_gt0'); thr('h', 6, 'h_max')

    # ------------------------------------------------- coupled increments
    L.inc_listener('n', 'up', 'en_c', USE_OFF); L.inc_listener('n', 'dn', 'en_c', USE_ON)
    L.inc_listener('n', 'up', 'dvn_c', USE_ON); L.inc_listener('n', 'dn', 'dvn_c', USE_OFF)
    L.inc_listener('v', 'up', 'dvn_c', USE_OFF); L.inc_listener('v', 'dn', 'dvn_c', USE_ON)
    L.inc_listener('v', 'up', 'dvx_c', USE_OFF); L.inc_listener('v', 'dn', 'dvx_c', USE_ON)
    L.inc_listener('x', 'up', 'dvx_c', USE_ON); L.inc_listener('x', 'dn', 'dvx_c', USE_OFF)
    L.inc_listener('g', 'up', 'el_c', USE_OFF); L.inc_listener('g', 'dn', 'el_c', USE_ON)
    for _ in range(3):
        L.inc_listener('sg', 'up', 'el_c', USE_OFF); L.inc_listener('sg', 'dn', 'el_c', USE_ON)
    L.dir_flag('g', 'gdir')
    # T(g) lookup: arriving at gate step v adds T(v)-T(v-1) to en; leaving it downward removes it
    for k in sorted({T[v] - T[v - 1] for v in range(1, 21) if T[v] != T[v - 1]}):
        if k == 10:                       # 10 = 4 + 3 + 2 + 1, reuse the smaller groups
            for part in (4, 3, 2, 1):
                L.relay('en_add10', f'en_add{part}', USE_ON); L.relay('en_sub10', f'en_sub{part}', USE_ON)
            continue
        for _ in range(k):
            L.relay(f'en_add{k}', 'en_c', USE_ON)
            L.relay(f'en_sub{k}', 'en_c', USE_OFF)
    for v in range(1, 21):
        dT = T[v] - T[v - 1]
        if dT:
            L.rule(vname('g', v), ['gdir'], f'en_add{dT}')
            L.rule(vname('g', v - 1), ['!gdir'], f'en_sub{dT}')
    # every fourth gate step draws 10 psi from the servo oil accumulator
    L.inc_listener('g', 'up', 'opu_use', USE_ON); L.inc_listener('g', 'dn', 'opu_use', USE_ON)
    L.add('game_counter', targetname='opu_use', frags=0, health=4, spawnflags=2, target='opu_draw')
    L.rule('opu_draw', ['o_gt0'], 'o_dn')
    # closing gates raises spiral-case pressure (water hammer)
    L.inc_listener('g', 'dn', 'hammer', USE_ON)
    L.rule('hammer', ['!h_max'], 'h_up')

    # ---------------------------------------------------------------- clock
    L.add('trigger_auto', target='init', delay=0.4, triggerstate=1)
    L.add('trigger_auto', target='clkA', delay=1.2, triggerstate=2)
    L.add('multi_manager', targetname='clkA', keys={'TK': 0, 'clkB': 0.05})
    L.add('multi_manager', targetname='clkB', keys={'TK': 0, 'clkA': 0.05})
    L.add('game_counter', targetname='TK', frags=0, health=2, spawnflags=2, target='TS')     # 0.1 s
    L.add('game_counter', targetname='TS', frags=0, health=2, spawnflags=2, target='TS2')    # 0.2 s
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
             'distance': 90, 'speed': 240, 'wait': -1, 'toggle': True}
        if lamp:
            dev['lamps'].append({'name': lamp[0], 'colors': lamp[1], 'init': 0})
            L.relay(f'{name}_ev', lamp[0], USE_TOGGLE)
            d['lamp'] = lamp[0]
        dev['rots'].append(d)

    def selector(name, flg, label, pos):
        flag(flg, 0)
        L.toggle_flag(f'{name}_ev', flg)
        dev['rots'].append({'name': name, 'target': f'{name}_ev', 'label': label, 'pos': pos, 'kind': 'sel',
                            'distance': 90, 'speed': 240, 'wait': -1, 'toggle': True})

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
    # needles step coarsely away from normal values and finely near rated (saves entities)
    display('n', ptr('p_speed'), lambda x: x / 30, vals=[0, 4, 8, 12, 14, 16, 17, 18, 19, 20, 21, 22, 24, 26, 28])
    display('g', ptr('p_gate'), lambda x: x / 20)
    display('g', ptr('p_kw'), lambda x: KW[x] / 320, conds=['cb'])
    display('g', ptr('p_vib'), lambda x: VIB[x] / 20, conds=['cb'])
    display('v', ptr('p_volts'), lambda x: x / 25, vals=[0, 4, 8, 12, 16, 18, 19, 20, 21, 22, 24])
    display('x', ptr('p_exc'), lambda x: x / 24, vals=list(range(0, 18, 2)) + list(range(18, 25)))
    display('x', ptr('p_kvar'), lambda x: 0.5 + (x - 20) / 16, vals=[12, 14, 16, 18, 19, 20, 21, 22, 24], conds=['cb'])
    display('o', ptr('p_opu'), lambda x: (200 + 10 * x) / 400)
    display('a', ptr('p_air'), lambda x: 12.5 * x / 150)
    display('bt', ptr('p_bt'), lambda x: x / 10)
    display('l', ptr('p_hw'), lambda x: (1 + 0.25 * x) / 6)
    display('sg', ptr('p_spill'), lambda x: x / 8)
    display('h', ptr('p_scase'), lambda x: (14.5 + x) / 30)
    for p, a_, b_, two, one in (('p_lube', 'hlp1', 'hlp2', 0.72, 0.6), ('p_cw', 'hwp1', 'hwp2', 0.75, 0.62)):
        ptr(p)
        L.display('T2', p, two, [a_, b_]); L.display('T2', p, one, [a_, f'!{b_}'])
        L.display('T2', p, one, [f'!{a_}', b_]); L.display('T2', p, 0.0, [f'!{a_}', f'!{b_}'])

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
    display('n', 's_turb', lambda x: max(0.02, 5 * x / 255), vals=[1, 6, 12, 17, 20, 22, 25])
    L.relay(vname('n', 1), 's_turb', USE_ON); L.relay(vname('n', 0), 's_turb', USE_OFF)
    L.relay(vname('g', 1), 's_water', USE_ON); L.relay(vname('g', 0), 's_water', USE_OFF)
    L.relay(vname('v', 1), 's_hum', USE_ON); L.relay(vname('v', 0), 's_hum', USE_OFF)

    # ---------------------------------------------- panel 1: auxiliaries
    for nm, flg, label in (('r_lp1', 'hlp1', 'LUBE OIL PUMP 1'), ('r_lp2', 'hlp2', 'LUBE OIL PUMP 2'),
                           ('r_wp1', 'hwp1', 'COOLING WATER PUMP 1'), ('r_wp2', 'hwp2', 'COOLING WATER PUMP 2'),
                           ('r_hp', 'hhp', 'SERVO OIL PUMP'), ('r_ac', 'hac', 'AIR COMPRESSOR')):
        cs(nm, flg, label, ('STOP', 'RUN'))          # a maintained pump switch: the handle shows the state
    L.relay('r_hp_ev', 's_pump', USE_TOGGLE)
    # either pump of a pair is enough
    for both, a_, b_ in (('lube', 'hlp1', 'hlp2'), ('cool', 'hwp1', 'hwp2')):
        L.rule('T1', [a_, f'!{both}'], f'{both}=1'); L.rule('T1', [b_, f'!{both}'], f'{both}=1')
        L.rule('T1', [f'!{a_}', f'!{b_}', both], f'{both}=0')
    # bearings: no lube oil wipes them in seconds, no cooling water cooks them in about a minute
    L.rule('T2', ['n_gt0', '!lube', '!bt_max'], 'bt_up')
    L.rule('T8', ['n_ge10', '!cool', '!bt_max'], 'bt_up')
    L.rule('T8', ['n_ge10', '!bt_ge5'], 'bt_up')                      # normal running temperature 70 C
    L.rule('T8', ['cool', 'bt_ge6'], 'bt_dn')
    L.rule('T8', ['!n_ge10', 'bt_ge3'], 'bt_dn')
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
    L.rule('TS2', ['tr', 'g_gt0'], 'g_dn')
    L.relay(vname('n', 28), 'prot'); alarm(vname('n', 28), W[0])
    L.rule('T1', ['bt_max', '!tr'], 'prot')
    L.rule('T1', ['g_gt0', '!o_ge2', '!tr'], 'prot')                  # servo oil gone with the gate open
    L.rule(vname('v', 23), ['!cb'], 'prot')                           # overvoltage
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
    cs('r_br', 'hbr', 'BRAKES', ('APPLY', 'RELEASE'))
    L.rule('T1', ['hbr', 'a_ge4', 'brake'], 'brake=0')
    L.rule('T1', ['!hbr', '!brake'], 'brake=1')
    L.rule('T1', ['!a_ge4', '!brake'], 'brake=1')

    # ---------------------------------------------------------------- speed
    L.rule('T1', ['!cb', 'en_pos', '!n_max', '!brake'], 'n_up')
    L.rule('T2', ['!cb', 'en_neg', 'g_gt0', 'n_gt0'], 'n_dn')
    L.rule('T8', ['!cb', 'en_neg', '!g_gt0', 'n_gt0'], 'n_dn')       # coasting on bearing friction
    L.rule('T1', ['!cb', 'brake', 'n_gt0'], 'n_dn')                  # air brakes

    # ------------------------------------------------------------- wicket gate
    knob('k_gate', 'g', ['!plc', '!tr', '!g_max', 'o_ge3'], ['!plc', '!tr', 'g_gt0', 'o_gt0'], 'TS2', 'WICKET GATE', wheel=True)
    # PLC: off line it acts as the governor (open to 30 %, then hold speed-no-load), on line it holds the pond
    base = ['plc', '!cb', '!tr', 'o_ge3', '!brake']
    L.rule('T1', base + ['!n_ge18', '!g_ge6'], 'g_up')
    L.rule('T1', base + ['!n_ge18', 'g_ge7'], 'g_dn')
    L.rule('T1', base + ['n_ge18', 'g_ge3'], 'g_dn')
    L.rule('T1', base + ['n_ge18', '!g_ge2'], 'g_up')
    L.rule('T1', ['plc', '!cb', 'brake', 'g_gt0', 'o_gt0'], 'g_dn')      # brakes applied: the PLC shuts the gate
    lc = ['plc', 'cb', '!tr', 'o_ge3']
    L.rule('T2', lc + ['l_ge13', 'el_pos', '!g_max'], 'g_up')
    L.rule('T2', lc + ['!l_ge12', 'el_neg', 'g_ge4'], 'g_dn')
    L.rule('T8', lc + ['l_ge14', '!g_max'], 'g_up')
    L.rule('T8', lc + ['!l_ge11', 'g_ge4'], 'g_dn')
    selector('r_plc', 'plc', 'PLC GATE CONTROL', ('OFF', 'ON'))
    L.relay('r_plc_ev', W[14], USE_TOGGLE)

    # ----------------------------------------------------------- excitation
    cs('r_exc', 'hexc', '41 FIELD BREAKER', ('OPEN', 'CLOSE'))
    L.rule('r_exc_ev', ['hexc', '!tr'], 'exc=1')
    L.rule('r_exc_ev', ['!hexc'], 'exc=0')
    L.rule('T1', ['hexc', '!exc'], 'r_exc')                          # refused or tripped: handle back to OPEN
    L.rule('TS2', ['!exc', 'x_gt0'], 'x_dn')                         # the field discharges
    knob('k_fa', 'x', ['exc', '!avr', '!x_max'], ['exc', '!avr', 'x_gt0'], 'TS2', 'FIRING ANGLE')
    # AVR: rated field off line (100 % volts at speed), a little more on line (slightly lagging)
    L.rule('TS2', ['avr', 'exc', '!x_ge20'], 'x_up')
    L.rule('TS2', ['avr', 'exc', '!cb', 'x_ge21'], 'x_dn')
    L.rule('TS2', ['avr', 'exc', 'cb', '!x_ge21'], 'x_up')
    L.rule('TS2', ['avr', 'exc', 'x_ge22'], 'x_dn')
    selector('r_avr', 'avr', 'AVR', ('MAN', 'AUTO'))
    L.relay('r_avr_ev', W[15], USE_TOGGLE)
    # off line the volts follow the field, limited by speed; on line the grid holds them
    L.rule('T1', ['!cb', 'dvn_pos', 'dvx_pos', '!v_max'], 'v_up')
    L.rule('T1', ['!cb', 'dvn_neg', 'v_gt0'], 'v_dn')
    L.rule('T1', ['!cb', 'dvx_neg', '!dvn_neg', 'v_gt0'], 'v_dn')     # (exclusive: one step down per tick)

    # ------------------------------------------------------ synchronizing
    # synchroscope: a func_train pointer circling behind the bezel. It turns while the switch is on, the
    # field is on and the unit is within 2.5 % of synchronous speed. Its path corners at 11 and 1 o'clock
    # fire the in-phase window, so what you see is what the sync check uses.
    cs('r_ss', 'hss', 'SYNCHROSCOPE', ('OFF', 'ON'))
    L.rule('T1', ['hss', 'exc', 'n_ge20', '!n_ge21', '!cb', '!scr'], 'scope_on')
    for c in ('!hss', '!exc', '!n_ge20', 'n_ge21', 'cb'):
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
    L.rule('r_52_ev', ok + ['scr', 'inph', 'v_ge19', '!v_ge22'], 'cb_close')
    L.rule('r_52_ev', ok + ['!scr'], 'oop')
    L.rule('r_52_ev', ok + ['scr', '!inph'], 'oop')
    L.rule('r_52_ev', ok + ['scr', 'inph', '!v_ge19'], 'oop')
    L.rule('r_52_ev', ok + ['scr', 'inph', 'v_ge22'], 'oop')
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
    L.rule('T1', ['cb', '!g_ge2'], 'cb_prot')                     # reverse power (32): the unit is motoring
    L.rule('T1', ['cb', '!x_ge12'], 'cb_prot')                    # loss of field (40)

    # ----------------------------------------------------------------- pond
    L.rule('T8', ['el_pos', '!l_max'], 'l_up')
    L.rule('T8', ['el_neg', 'l_gt0'], 'l_dn')
    # spillway (automatic): open above 513.5 ft while the pond still rises, close below 513.25 ft while it falls
    L.rule('T8', ['l_ge14', 'el_pos', '!sg_max'], 'sg_up')
    L.rule('T8', ['l_max', '!el_pos', '!sg_max'], 'sg_up')
    L.rule('T8', ['!l_ge13', 'el_neg', 'sg_gt0'], 'sg_dn')
    L.rule('T16', ['plc', 'cb', 'sg_gt0', '!g_max', '!l_ge14'], 'sg_dn')   # the PLC gives the water to the unit
    # draft-tube rope indication: on line between 20 and 45 % gate
    L.rule(vname('g', 4), ['cb', 'gdir'], 'rz=1'); L.rule(vname('g', 9), ['cb', '!gdir'], 'rz=1')
    L.rule(vname('g', 3), ['!gdir'], 'rz=0'); L.rule(vname('g', 10), ['gdir'], 'rz=0')
    L.rule('T1', ['h_gt0'], 'h_dn')                                              # hammer decays

    # ---------------------------------------------------------- lamps, windows
    lamp('LP_cb', 'cb', ('red', 'green'))
    lamp('LP_brake', 'brake', ('red', 'green'))
    lamp('LP_exc', 'exc', ('red', 'green'))
    lamp('LP_sg', 'sg_gt0', ('red', 'green'))
    for i, flg, lit_when in [(1, 'tr', 1), (4, 'o_ge4', 0), (5, 'lube', 0), (6, 'bt_ge8', 1), (7, 'cool', 0),
                             (8, 'a_ge4', 0), (9, 'brake', 1), (10, 'rz', 1), (11, 'l_ge14', 1), (12, 'l_ok', 0),
                             (13, 'sg_gt0', 1)]:
        dev.setdefault('ann_init', {})[i] = int(fi[flg] == lit_when)
        L.follow(flg, W[i], 1 - fi[flg])
    dev['ann_init'][14] = 1 - fi['plc']; dev['ann_init'][15] = 1 - fi['avr']

    # --------------------------------------------------------------- init
    L.display('init', 'p_kvar', 0.5); L.display('init', 'p_vib', 0.02)
    for var, p, fn in [('l', 'p_hw', lambda x: (1 + 0.25 * x) / 6), ('sg', 'p_spill', lambda x: x / 8),
                       ('h', 'p_scase', lambda x: (14.5 + x) / 30), ('bt', 'p_bt', lambda x: x / 10)]:
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
