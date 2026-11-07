"""
Sable Creek Unit 1 for plain Half-Life: the plant as entity logic.

Every number on the panels is a game_counter variable. A 0.5 s clock made of
two multi_managers runs the rules below; each rule is a chain of
game_counter_set entities locked by multisource masters that read env_global
flags. Nothing is a canned timeline: speed, voltage, gate, oil pressure and the
pond all evolve from the rules, so trips and recoveries play out on their own.

Scales (one step of each variable):
  n  speed        5 % of 100 rpm   (20 = synchronous, 28 = overspeed trip)
  g  wicket gate  5 %
  v  voltage      5 % of 480 V
  s  load setpoint, online gate target = s + 2
  o  governor oil 10 psi above 200 psi (10 = 300 psi)
  l  headwater    0.25 ft above EL 510.0 (12 = 513.0 ft normal)
  sg spill gate   0.5 ft
  h  water hammer 1 psi of spiral-case pressure rise
Difference variables (only their sign is needed):
  en = T(g) - n      speed error: T is the speed the runner settles at for gate g
  d  = (g - 2) - s   online gate error
  dv = n - v         voltage follows speed while excited (capped at 100 %)
  el = river - g - 3 sg   pond balance (river = normal flow + flood knob r)
"""
from hlogic import Logic, USE_ON, USE_OFF, USE_TOGGLE, vname

# runner equilibrium speed (5 % steps) for each gate step: speed-no-load at
# 10 % gate, runaway near 175 % (low specific-speed Francis)
T = [0, 10, 20, 24, 27, 29, 31, 32, 33, 34, 35] + [35] * 10
# electrical kW for each gate step at 40 ft (from the Euler runner model)
KW = [0, 0, 0, 27, 50, 72, 94, 115, 135, 152, 169, 184, 199, 211, 223, 233, 243, 251, 258, 264, 269]
# shaft vibration on line, mils p-p (draft-tube vortex rope between 20 and 45 % gate)
VIB = [0, 1, 3, 6, 6, 7, 8, 8, 7, 6, 4, 3, 2, 2] + [2] * 7

RIVER0 = 15
INIT = dict(n=0, g=0, v=0, s=14, o=10, l=12, sg=5, h=0)
VARS = dict(n=(0, 28), g=(0, 20), v=(0, 21), s=(0, 18), o=(0, 10), l=(0, 16), sg=(0, 8), h=(0, 6))
ANN = ['OVERSPEED|12', '86 LOCKOUT|RELAY', 'EMERGENCY|STOP', 'GEN BREAKER|52G TRIP',
       'GOV OIL|PRESS LOW', 'HEADWATER|HIGH', 'HEADWATER|LOW', 'SPILLWAY|GATE OPEN',
       'UTILITY|LINE TRIP', 'DRAFT TUBE|PULSATION', 'LAG OIL PUMP|RUNNING', 'GOVERNOR|IN MANUAL',
       'LEVEL CONTROL|OFF', 'SYNC IN|PROGRESS', 'BRAKES|APPLIED', 'LOW LEVEL|STOP']


def _build(L):
    dev = {'lamps': [], 'ptrs': [], 'buttons': [], 'rots': [], 'walls': [], 'sounds': [], 'ann': ANN, 'knobs': []}
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
    dinit = dict(en=T[INIT['g']] - INIT['n'], d=(INIT['g'] - 2) - INIT['s'], dv=INIT['n'] - INIT['v'],
                 el=RIVER0 - INIT['g'] - 3 * INIT['sg'])
    for k, v0 in dinit.items():
        L.var(k, -1, 1, v0, values=[-1, 0, 1])
        flag(f'{k}_pos', int(v0 > 0)); flag(f'{k}_neg', int(v0 < 0))
        L.setf(vname(k, 1), f'{k}_pos', 1); L.setf(vname(k, 0), f'{k}_pos', 0)
        L.setf(vname(k, -1), f'{k}_neg', 1); L.setf(vname(k, 0), f'{k}_neg', 0)
    L.var('sy', 0, 6, 0, values=[1, 6])          # auto-synchronizer timer
    L.var('r', 0, 30, 0, values=[0, 1, 29, 30])   # flood inflow added by the river knob

    for name, init in [('run', 0), ('cb', 0), ('exc', 0), ('lock', 0), ('stopping', 0), ('cw', 0), ('lift', 0),
                       ('brake', 1), ('p1', 0), ('p2', 0), ('ready', 1), ('rz', 0)]:
        state(name, init)
    for name, init in [('auto', 1), ('synca', 1), ('ctl', 1), ('spa', 1), ('pfail', 0), ('gdir', 1)]:
        flag(name, init)
    thr('n', 1, 'n_gt0'); thr('n', 6); thr('n', 18); thr('n', 19); thr('n', 20); thr('n', 21); thr('n', 28, 'n_max')
    thr('g', 1, 'g_gt0'); thr('g', 2); thr('g', 3); thr('g', 6); thr('g', 7); thr('g', 20, 'g_max')
    thr('v', 1, 'v_gt0'); thr('v', 19); thr('v', 20, 'v_max')
    thr('s', 1, 's_gt0'); thr('s', 18, 's_max')
    thr('o', 1, 'o_gt0'); thr('o', 10, 'o_full')
    thr('l', 1, 'l_gt0'); thr('l', 9, 'l_ok'); thr('l', 11); thr('l', 12); thr('l', 13, 'l_hi'); thr('l', 14); thr('l', 16, 'l_max')
    thr('sg', 1, 'sg_gt0'); thr('sg', 8, 'sg_max')
    thr('h', 1, 'h_gt0'); thr('h', 6, 'h_max')
    thr('r', 1, 'r_gt0'); thr('r', 30, 'r_max')

    # ------------------------------------------------- coupled increments
    L.inc_listener('n', 'up', 'en_c', USE_OFF); L.inc_listener('n', 'dn', 'en_c', USE_ON)
    L.inc_listener('n', 'up', 'dv_c', USE_ON); L.inc_listener('n', 'dn', 'dv_c', USE_OFF)
    L.inc_listener('v', 'up', 'dv_c', USE_OFF); L.inc_listener('v', 'dn', 'dv_c', USE_ON)
    L.inc_listener('g', 'up', 'd_c', USE_ON); L.inc_listener('g', 'dn', 'd_c', USE_OFF)
    L.inc_listener('s', 'up', 'd_c', USE_OFF); L.inc_listener('s', 'dn', 'd_c', USE_ON)
    L.inc_listener('g', 'up', 'el_c', USE_OFF); L.inc_listener('g', 'dn', 'el_c', USE_ON)
    for _ in range(3):
        L.inc_listener('sg', 'up', 'el_c', USE_OFF); L.inc_listener('sg', 'dn', 'el_c', USE_ON)
    L.inc_listener('r', 'up', 'el_c', USE_ON); L.inc_listener('r', 'dn', 'el_c', USE_OFF)
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
    # every fourth gate step draws 10 psi from the pressure tank (two full strokes per 100 psi)
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
    def lamp(name, flg, colors, lit_when=1):
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

    display('n', ptr('p_speed'), lambda x: x / 30)
    display('n', ptr('p_hz'), lambda x: min(1, max(0, (3 * x - 54) / 12)), vals=range(17, 24))
    display('g', ptr('p_gate'), lambda x: x / 20)                     # gate + turbine discharge meters
    display('g', ptr('p_kw'), lambda x: KW[x] / 320, conds=['cb'])    # kilowatts + generator amperes
    display('s', ptr('p_kwsp'), lambda x: KW[min(20, x + 2)] / 320)
    display('g', ptr('p_vib'), lambda x: VIB[x] / 20, conds=['cb'])
    display('v', ptr('p_volts'), lambda x: x / 25)                    # volts + exciter field A and V
    display('o', ptr('p_opu'), lambda x: (200 + 10 * x) / 400)
    display('l', ptr('p_hw'), lambda x: (1 + 0.25 * x) / 6)
    display('sg', ptr('p_spill'), lambda x: x / 8)
    display('h', ptr('p_scase'), lambda x: (14.5 + x) / 30)
    for p in ('p_kvar', 'p_cw', 'p_lift'):
        ptr(p)

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
    L.relay('p1=1', 's_pump', USE_ON); L.relay('p1=0', 's_pump', USE_OFF)

    # lamp pairs (red = running/closed, green = stopped/open: US practice)
    for nm in ('p1', 'p2', 'cw', 'lift', 'cb', 'exc'):
        lamp(f'LP_{nm}', nm, ('red', 'green'))
    lamp('LP_brake', 'brake', ('red', 'green'))
    lamp('LP_sg', 'sg_gt0', ('red', 'green'))
    lamp('L_run', 'run', ('red', None)); lamp('L_ready', 'ready', ('white', None))
    lamp('L_lock', 'lock', ('amber', None)); lamp('L_opuok', 'o_full', ('white', None))
    for nm, flg in (('L_govman', 'auto'), ('L_ctl', 'ctl'), ('L_spa', 'spa')):
        init = fi[flg]
        dev['lamps'].append({'name': nm, 'colors': ('amber', None) if nm == 'L_govman' else ('red', None),
                             'init': init, 'inv': nm == 'L_govman'})

    # annunciator windows: func_wall, frame 0 = dark
    W = [f'A{i:02d}' for i in range(16)]
    dev['walls'] += W
    for i, flg, lit_when in [(5, 'l_max', 1), (6, 'l_ok', 0), (7, 'sg_gt0', 1), (9, 'rz', 1), (10, 'p2', 1), (14, 'brake', 1)]:
        dev.setdefault('ann_init', {})[i] = int(fi[flg] == lit_when)
        L.follow(flg, W[i], 1 - fi[flg])

    def alarm(event, win):
        L.relay(event, win, USE_ON)
        L.relay(event, 's_horn', USE_ON)
        L.relay(event, 's_relay', USE_ON)

    dev['walls'] += ['SYNCHRO', 'SYNCLAMPS']

    def knob(name, var, up, dn, step, label, wheel=False, absolute=False, desk=False):
        """momentary_rot_button turned by holding USE. It fires its target every frame
        while turning; the logic steps `var` on the `step` clock while that happens.
        Each new turn reverses (stock Half-Life behaviour); the logic sees the turn end
        as two quiet 0.05 s ticks and flips its direction flag, shown on a lamp."""
        ev = f'{name}_ev'
        flag(f'{name}_a', 0); flag(f'{name}_u', 1)
        L.setf(ev, f'{name}_a', 1)                                           # turning this step
        L.add('game_counter_set', targetname=ev, target=f'{name}_ic', frags=0)
        L.add('game_counter', targetname=f'{name}_ic', frags=9, health=2, target=f'{name}_end')
        L.relay('TK', f'{name}_ic', USE_ON)                                  # quiet ticks
        L.toggle_flag(f'{name}_end', f'{name}_u')
        lamp_nm = f'L_{name}'
        dev['lamps'].append({'name': lamp_nm, 'colors': ('amber', 'amber'), 'init': 1})
        L.relay(f'{name}_end', lamp_nm, USE_TOGGLE)
        L.rule(step, [f'{name}_a', f'{name}_u'] + up, f'{var}_up')
        L.rule(step, [f'{name}_a', f'!{name}_u'] + dn, f'{var}_dn')
        L.late('env_global', targetname=step, globalstate=f'{name}_a', triggermode=0)
        if absolute:
            # at the top stop the knob is turning up: resynchronise the direction (USE_SET 1.0 -> count 1)
            L.add('game_counter', targetname=ev, frags=0, health=1, target=f'{name}_top')
            L.setf(f'{name}_top', f'{name}_u', 1)
            L.relay(f'{name}_top', lamp_nm, USE_OFF)
            dev['ptrs'].append(ev)                      # the knob drives its own meter pointer directly
        dev['knobs'].append({'name': name, 'target': ev, 'label': label, 'wheel': wheel, 'absolute': absolute, 'desk': desk,
                             'lamp': lamp_nm})

    # ----------------------------------------------------- start / stop / trip
    dev['buttons'].append({'name': 'b_start', 'target': 'start', 'master': 'ms_ready', 'color': 'green', 'label': 'START'})
    for f_, val in [('run', 1), ('stopping', 0), ('cw', 1), ('lift', 1), ('brake', 0), ('ready', 0)]:
        L.relay('start', f'{f_}={val}')
    dev['buttons'].append({'name': 'b_stop', 'target': 'stop', 'master': 'ms_run', 'color': 'red', 'label': 'STOP'})
    L.relay('stop', 'stopping=1')
    L.rule('T1', ['!run', '!lock', '!n_gt0', '!ready'], 'ready=1')
    L.rule('T1', ['ready', 'run'], 'ready=0')
    L.rule('T1', ['ready', 'lock'], 'ready=0')
    L.rule('T1', ['ready', 'n_gt0'], 'ready=0')
    # normal stop: unload, open 52G at speed-no-load gate, then shut down
    L.rule('T2', ['stopping', 'cb', 's_gt0'], 's_dn')
    L.rule('T1', ['stopping', 'cb', '!s_gt0', '!g_ge3'], 'cb_open')
    L.rule('T1', ['stopping', '!cb'], 'stop_done')
    for f_, val in [('run', 0), ('stopping', 0), ('exc', 0)]:
        L.relay('stop_done', f'{f_}={val}')
    # trips to lockout 86: E-stop, overspeed, low governor oil pressure
    for f_, val in [('lock', 1), ('run', 0), ('stopping', 0), ('exc', 0), ('ready', 0)]:
        L.relay('trip', f'{f_}={val}')
    L.rule('trip', ['cb'], 'cb_trip')
    alarm('trip', W[1])
    dev['buttons'].append({'name': 'b_estop', 'target': 'estop', 'color': 'estop', 'label': 'EMERGENCY STOP'})
    L.relay('estop', 'trip'); alarm('estop', W[2])
    L.relay(vname('n', 28), 'trip'); alarm(vname('n', 28), W[0])
    L.rule(vname('o', 2), ['run'], 'trip_opu'); L.relay('trip_opu', 'trip'); alarm('trip_opu', W[4])
    dev['buttons'].append({'name': 'b_reset86', 'target': 'reset86', 'color': 'black', 'label': '86 RESET'})
    L.rule('reset86', ['!n_gt0'], 'lock=0')
    L.rule(vname('l', 6), ['run', '!stopping'], 'lowlevel')
    L.relay('lowlevel', 'stopping=1'); alarm('lowlevel', W[15])

    # ---------------------------------------------------------- 52G breaker
    L.relay('cb_close', 'cb=1')
    L.relay('cb_close', 's_brk', USE_ON)
    for t in ('SYNCHRO', 'SYNCLAMPS', W[13]):
        L.relay('cb_close', t, USE_OFF)
    L.add('game_counter_set', targetname='cb_close', target='sy_c', frags=0)
    for ev in ('cb_open', 'cb_trip', 'util_trip'):
        L.rule(ev, ['cb'], f'{ev}_x')
        L.relay(f'{ev}_x', 'cb=0'); L.relay(f'{ev}_x', 'rz=0'); L.relay(f'{ev}_x', 's_brk', USE_ON)
        L.display(f'{ev}_x', 'p_kw', 0.0); L.display(f'{ev}_x', 'p_vib', 3.0 / 20)
    alarm('cb_trip_x', W[3]); alarm('util_trip_x', W[8])
    L.display('cb=1', 'p_kvar', 0.65); L.display('cb=0', 'p_kvar', 0.5)
    dev['buttons'].append({'name': 'b_cbclose', 'target': 'm_close', 'color': 'red', 'label': 'CLOSE'})
    dev['buttons'].append({'name': 'b_cbtrip', 'target': 'cb_open', 'color': 'green', 'label': 'TRIP'})
    L.rule('m_close', ['!cb', 'exc', 'n_ge20', '!n_ge21', 'v_ge19', '!lock'], 'cb_close')
    # auto-synchronizer: 3 s of good conditions, then close
    L.rule('T1', ['run', '!cb', 'exc', 'synca', 'n_ge20', '!n_ge21', 'v_ge19', '!lock'], 'sy_inc')
    L.relay('sy_inc', 'sy_c', USE_ON)
    for c in ('!run', 'cb', '!exc', '!synca', '!n_ge20', 'n_ge21', '!v_ge19'):
        L.rule('T1', [c], 'sy_rst')
    L.add('game_counter_set', targetname='sy_rst', target='sy_c', frags=0)
    for t in ('SYNCHRO', 'SYNCLAMPS', W[13]):
        L.relay('sy_rst', t, USE_OFF); L.relay(vname('sy', 1), t, USE_ON)
    L.rule(vname('sy', 6), ['!cb'], 'cb_close')

    # ------------------------------------------------------------ governor
    off = ['run', 'auto', '!cb', '!lock']
    L.rule('T1', off + ['!n_ge18', '!g_ge6', 'o_gt0'], 'g_up')        # start opening, 30 %
    L.rule('T1', off + ['!n_ge18', 'g_ge7'], 'g_dn')
    L.rule('T1', off + ['n_ge18', 'g_ge3'], 'g_dn')                   # back to speed-no-load
    L.rule('T1', off + ['n_ge21', 'g_ge3'], 'g_dn')                   # overspeed: full closing rate
    L.rule('T1', off + ['n_ge18', '!g_ge2', 'o_gt0'], 'g_up')
    on = ['run', 'auto', 'cb', '!lock']
    L.rule('T1', on + ['d_neg', '!g_max', 'o_gt0'], 'g_up')           # follow the load setpoint
    L.rule('T1', on + ['d_pos', 'g_gt0'], 'g_dn')
    L.rule('T1', ['!run', 'g_gt0'], 'g_dn')                           # shutdown
    L.rule('T1', ['lock', 'g_gt0'], 'g_dn')                           # emergency closing, double rate
    knob('k_gate', 'g', ['run', '!auto', '!g_max', '!lock', 'o_gt0'], ['!auto', 'g_gt0'], 'TS2', 'WICKET GATE', wheel=True)
    dev['rots'].append({'name': 'r_gov', 'target': 'gov_tog', 'label': 'GOVERNOR', 'pos': ('AUTO', 'MAN')})
    L.toggle_flag('gov_tog', 'auto'); L.relay('gov_tog', 'L_govman', USE_TOGGLE); L.relay('gov_tog', W[11], USE_TOGGLE)
    knob('k_load', 's', ['!s_max'], ['s_gt0'], 'TS2', 'LOAD SETPOINT')
    dev['rots'].append({'name': 'r_sync', 'target': 'sync_tog', 'label': 'SYNC MODE', 'pos': ('AUTO', 'MAN')})
    L.toggle_flag('sync_tog', 'synca')

    # ---------------------------------------------------------------- speed
    L.rule('T1', ['!cb', 'en_pos', '!n_max'], 'n_up')
    L.rule('T2', ['!cb', 'en_neg', 'g_gt0', 'n_gt0'], 'n_dn')
    L.rule('T8', ['!cb', 'en_neg', '!g_gt0', 'n_gt0', '!brake'], 'n_dn')  # coasting on bearing friction
    L.rule('T1', ['!cb', 'brake', 'n_gt0'], 'n_dn')                       # air brakes
    L.rule('T1', ['!run', '!n_ge6', 'n_gt0', '!brake'], 'brake=1')
    L.rule('T1', ['lift', 'n_ge18'], 'lift=0')
    L.rule('T1', ['!run', '!n_ge18', 'n_gt0', '!lift'], 'lift=1')
    L.rule('T1', ['!run', '!n_gt0', 'lift'], 'lift=0')
    L.rule('T1', ['!run', '!n_gt0', 'cw'], 'cw=0')

    # ----------------------------------------------------------- excitation
    L.rule(vname('n', 19), ['run', 'auto', '!exc', '!lock', '!stopping'], 'exc=1')
    dev['buttons'].append({'name': 'b_excon', 'target': 'm_excon', 'color': 'red', 'label': 'ON'})
    dev['buttons'].append({'name': 'b_excoff', 'target': 'm_excoff', 'color': 'green', 'label': 'OFF'})
    L.rule('m_excon', ['n_ge19', '!lock', '!exc'], 'exc=1')
    L.rule('m_excoff', ['!cb', 'exc'], 'exc=0')
    L.rule('T1', ['exc', 'dv_pos', '!v_max'], 'v_up')
    L.rule('T1', ['exc', 'dv_neg', 'v_gt0'], 'v_dn')
    L.rule('T1', ['!exc', 'v_gt0'], 'v_dn')

    # ------------------------------------------------ governor oil pressure
    L.relay(vname('o', 7), 'p1=1'); L.relay(vname('o', 10), 'p1=0')
    L.relay(vname('o', 5), 'p2=1'); L.relay(vname('o', 10), 'p2=0')
    L.rule('T1', ['p1', '!pfail', '!o_full'], 'o_up')
    L.rule('T1', ['p2', '!pfail', '!o_full'], 'o_up')
    L.rule('T16', ['o_gt0'], 'o_dn')                                   # pilot-valve leakage
    dev['buttons'].append({'name': 'b_air', 'target': 'm_air', 'color': 'black', 'label': 'PUMP TEST'})
    L.rule('m_air', ['!o_full', '!pfail'], 'o_up')

    # ----------------------------------------------------------------- pond
    L.rule('T8', ['el_pos', '!l_max'], 'l_up')
    L.rule('T8', ['el_neg', 'l_gt0'], 'l_dn')
    # PLC level control: move the load setpoint only while the level is still
    # heading away from the band (proportional-plus-rate behaviour), harder when far out
    lc = ['ctl', 'cb', 'run', '!stopping']
    L.rule('T2', lc + ['l_hi', 'el_pos', '!s_max'], 's_up')
    L.rule('T2', lc + ['!l_ge12', 'el_neg', 's_gt0'], 's_dn')
    L.rule('T8', lc + ['l_ge14', '!s_max'], 's_up')
    L.rule('T8', lc + ['!l_ge11', 's_gt0'], 's_dn')
    # spillway automatic: open above 513.5 ft while the pond still rises, close below 513 ft while it falls
    L.rule('T8', ['spa', 'l_ge14', 'el_pos', '!sg_max'], 'sg_up')
    L.rule('T8', ['spa', 'l_max', '!sg_max'], 'sg_up')
    L.rule('T8', ['spa', '!l_hi', 'el_neg', 'sg_gt0'], 'sg_dn')
    L.rule('T16', ['spa', 'ctl', 'cb', 'sg_gt0', '!s_max', '!l_ge14'], 'sg_dn')   # give the water to the unit
    dev['rots'].append({'name': 'r_ctl', 'target': 'ctl_tog', 'label': 'LEVEL CONTROL', 'pos': ('ON', 'OFF')})
    L.toggle_flag('ctl_tog', 'ctl'); L.relay('ctl_tog', 'L_ctl', USE_TOGGLE); L.relay('ctl_tog', W[12], USE_TOGGLE)
    dev['rots'].append({'name': 'r_spa', 'target': 'spa_tog', 'label': 'SPILLWAY', 'pos': ('AUTO', 'MAN')})
    L.toggle_flag('spa_tog', 'spa'); L.relay('spa_tog', 'L_spa', USE_TOGGLE)
    knob('k_spill', 'sg', ['!spa', '!sg_max'], ['!spa', 'sg_gt0'], 'TS2', 'SPILL GATE', wheel=True)
    # draft-tube rope indication: on line between 20 and 45 % gate
    L.rule(vname('g', 4), ['cb', 'gdir'], 'rz=1'); L.rule(vname('g', 9), ['cb', '!gdir'], 'rz=1')
    L.rule(vname('g', 3), ['!gdir'], 'rz=0'); L.rule(vname('g', 10), ['gdir'], 'rz=0')
    L.rule('T1', ['h_gt0'], 'h_dn')                                              # hammer decays

    # ------------------------------------------------ annunciator controls
    dev['buttons'].append({'name': 'b_ack', 'target': 'ann_ack', 'color': 'black', 'label': 'ACK'})
    dev['buttons'].append({'name': 'b_annreset', 'target': 'ann_reset', 'color': 'black', 'label': 'RESET'})
    L.relay('ann_ack', 's_horn', USE_OFF)
    L.rule('ann_reset', ['!lock'], 'ann_clear')
    for i in (0, 1, 2, 3, 4, 8, 15):
        L.relay('ann_clear', W[i], USE_OFF)

    # -------------------------------------------------- instructor console
    dev['buttons'].append({'name': 'b_util', 'target': 'util_trip', 'color': 'amber', 'label': 'UTILITY TRIP', 'desk': True})
    # river: an absolute knob from normal flow (0) to full flood (+30); its own position drives the FLOOD meter
    knob('k_river', 'r', ['!r_max'], ['r_gt0'], 'TS', 'RIVER', absolute=True, desk=True)
    dev['rots'].append({'name': 'r_pfail', 'target': 'pfail_tog', 'label': 'OIL PUMPS', 'pos': ('OK', 'FAIL'), 'desk': True})
    L.toggle_flag('pfail_tog', 'pfail')

    # --------------------------------------------------------------- init
    for var, p, fn in [('o', 'p_opu', lambda x: (200 + 10 * x) / 400), ('l', 'p_hw', lambda x: (1 + 0.25 * x) / 6),
                       ('sg', 'p_spill', lambda x: x / 8), ('s', 'p_kwsp', lambda x: KW[min(20, x + 2)] / 320),
                       ('h', 'p_scase', lambda x: (14.5 + x) / 30)]:
        L.display('init', p, fn(INIT[var]))
    L.display('init', 'p_kvar', 0.5); L.display('init', 'p_vib', 0.02)
    dev['flags_init'] = fi
    return L.finalize(), dev


def build():
    p1 = Logic(used=None)
    _build(p1)
    L = Logic(used=p1.reads)
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
