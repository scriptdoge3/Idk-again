"""Runs the plant in the Source entity simulator: start-up, synchronizing, loading, trips."""
import sys
import hydro
from hydro import build
from srcsim import Sim

m, PROGS, dev = build()
LEVELS = {k: v for p in PROGS for k, v in p.levels.items()}


def bin_ops():
    ops = {}
    for e in m.ents:
        for out, tgt, inp, par, d, t in e.outputs:
            if tgt in LEVELS and inp != 'SetValueNoFire':
                ops[tgt] = inp
    return ops


def new_sim():
    s = Sim(m.ents, check=bin_ops())
    s.run(2.0)
    return s


FAILS = []


def check(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what)
    if not cond:
        FAILS.append(what)


def V(s, name):
    return s.value(name)


def flip(s, sw, settle=0.6):
    s.use(sw); s.run(settle)


def wait_for(s, cond, limit):
    t = 0.0
    while not cond() and t < limit:
        s.run(0.06); t += 0.06
    return t


def to_speed_no_load(s):
    """by hand: gate to 25 %, back to about 15 % from 80 % speed, then trim to 100 %"""
    s.hold('k_gr', 4.6)
    t = wait_for(s, lambda: V(s, 'n') > 80, 60)
    while V(s, 'g') > 16.5:
        s.hold('k_gl', 1.6); s.run(0.6)        # 0.25 %/s for a second, then 2.5 %/s
    while V(s, 'g') > 15.3:
        s.hold('k_gl', 0.4); s.run(0.6)
    wait_for(s, lambda: abs(V(s, 'n') - 100) < 0.5, 30)
    return t


def trim(s, lo=0.04, hi=0.25):
    """short taps on RAISE / LOWER, waiting for the speed to settle after each (it takes 15-20 s), until the
    unit runs a little faster than the grid"""
    for _ in range(40):
        s.run(20.0)
        slip = V(s, 'n') - 100
        if lo <= slip <= hi:
            return True
        s.hold('k_gr' if slip < lo else 'k_gl', 0.3 if abs(slip - 0.1) < 1 else 0.6)
    return False


def kw(s):
    return hydro.PBASE * s.value('cb') * 0.02 * s.value('x') * __import__('math').sin(__import__('math').radians(s.value('dl')))


def start_aux(s):
    for sw in ('r_lp', 'r_wp', 'r_hp', 'r_ac'):
        flip(s, sw, 0.5)
    s.run(16)
    flip(s, 'r_br')                  # BRAKES to RELEASE


def scenario_idle():
    print('idle')
    s = new_sim()
    s.run(10)
    check(not s.errors, f'two-input nodes always got their first value first ({len(s.errors)} errors)')
    check(abs(V(s, 'l') - 7.0) < 0.1, f"forebay holds at 7.0 m ({V(s, 'l'):.2f})")
    fb, sp = s['p_hw'].pos() * 35, s['p_spill'].pos() * 4
    check(abs(fb - 23.0) < 0.4 and abs(sp - V(s, 'sg') * 3.2808) < 0.1, f'FOREBAY LEVEL reads {fb:.1f} ft, spill GATE POS {sp:.2f} ft')
    lit = [w['legend'] for w in dev['windows'] if s[w['ent'].name].on]
    check(set(lit) == {'63Q HPU|PRESS LO', '63Q LUBE OIL|PRESS LO', '80 CW|FLOW LO', '63A BRAKE AIR|PRESS LO',
                       'SPILL GATE|OPEN', 'GOV|IN MANUAL', 'AVR|IN MANUAL'}, f'windows lit at rest: {lit}')
    check(not s['s_horn'].playing, 'no horn at start')
    check(abs(s['k_fa'].pos() - hydro.KNOB0) < 0.01, 'firing-angle knob at rated no-load field')
    flip(s, 'r_lp', 0.8); on = V(s, 'lube'); flip(s, 'r_lp', 0.8)
    check(on == 1 and V(s, 'lube') == 0 and s['r_lp_r'].ang == 0 and s['r_lp_l'].ang == 0,
          'LUBE OIL PUMP: START runs it, STOP stops it, the handle springs back')


def scenario_manual_start():
    print('manual start, sync by hand, load')
    s = new_sim()
    start_aux(s)
    check(V(s, 'hp') > 290, f"hydraulic oil charged ({V(s, 'hp'):.0f} psi)")
    check(V(s, 'air') > 100, f"brake air charged ({V(s, 'air'):.0f} psi)")
    t80 = to_speed_no_load(s)
    check(abs(V(s, 'n') - 100) < 3, f"speed-no-load by hand: n={V(s, 'n'):.2f} g={V(s, 'g'):.2f} (80 % after {t80:.1f} s)")
    flip(s, 'r_avr')                 # AVR AUTO
    flip(s, 'r_exc')                 # 41 close
    check(V(s, 'exc') == 1, '41 closes above 90 % speed')
    peak = 0
    for _ in range(int(12 / 0.06)):
        s.run(0.06); peak = max(peak, V(s, 'v'))
    check(abs(V(s, 'v') - V(s, 'vg')) < 1.5 and peak < 108, f"field flashing, the AVR matches the bus volts ({V(s, 'v') * 4.8:.0f} V, bus {V(s, 'vg') * 4.8:.0f} V, peak {peak * 4.8:.0f} V)")
    flip(s, 'r_ss')
    ok = trim(s)
    check(ok, f"trimmed by hand to {V(s, 'n'):.3f} %")
    th0 = V(s, 'th'); s.run(2); th1 = V(s, 'th')
    check(th1 != th0, f'the phase turns ({th0:.0f} -> {th1:.0f} deg)')
    # wait for the window and close
    t = wait_for(s, lambda: V(s, 'perm') == 1, 120)
    check(V(s, 'perm') == 1, f'SYNC CHECK lamp lit after {t:.1f} s')
    flip(s, 'r_52', 0.3)
    check(V(s, 'cb') == 1, f"52G closes in phase (at {V(s, 'dl'):.1f} deg)")
    check(s['LP_cb_1'].on and not s['LP_cb_0'].on, 'CLOSED lamp lit')
    # the rotor swings into step: the power rocks and settles
    ks = []
    for _ in range(int(6 / 0.06)):
        s.run(0.06); ks.append(kw(s))
    swing = max(ks[:30]) - min(ks[:30]); late = max(ks[-20:]) - min(ks[-20:])
    check(swing > 3 and late < 1, f'the power swings after closing ({swing:.1f} kW peak to peak) and settles ({late:.2f} kW)')
    # load by hand
    s.hold('k_gr', 6); s.run(3)
    check(kw(s) > 100, f"loads by hand: gate {V(s, 'g'):.0f} %, {kw(s):.0f} kW, field {V(s, 'x'):.0f} %")
    # loaded, the water column makes the power dip as the gate starts opening fast
    ks = []
    s.holding.add('k_gr')
    for _ in range(int(4.5 / 0.03)):
        s.run(0.03); ks.append(kw(s))
    s.holding.discard('k_gr'); s.run(3)
    rises = [b - a for a, b in zip(ks, ks[1:])]
    check(min(rises) < -0.2, f'water inertia: the power dips a little when the gate speeds up ({min(rises):.2f} kW per 0.03 s)')
    check(V(s, 'tr') == 0, 'no trip')
    return s


def scenario_plc_start():
    print('PLC start and sync, PLC on line')
    s = new_sim()
    start_aux(s)
    flip(s, 'r_plc'); flip(s, 'r_avr')
    t = wait_for(s, lambda: V(s, 'n') > 90, 60)
    check(15 < t < 40, f'PLC brings the unit to 90 % in {t:.1f} s')
    flip(s, 'r_exc')
    s.run(30)
    n = V(s, 'n')
    check(100.0 < n < 100.2, f'PLC holds a hair fast: {n:.3f} %')
    flip(s, 'r_ss')
    a = V(s, 'th'); s.run(5.0); b = V(s, 'th')
    turn = ((b - a) % 360) / 5.0
    check(10 < turn < 25, f'pointer creeps clockwise, {turn:.1f} deg/s (a turn in {360 / turn:.0f} s)')
    t = wait_for(s, lambda: V(s, 'perm') == 1, 60)
    flip(s, 'r_52', 0.4)
    check(V(s, 'cb') == 1, f'52G closed {t:.1f} s after the switch went on')
    s.run(120)
    check(V(s, 'g') > 50, f"forebay level control passes the river: gate {V(s, 'g'):.1f} %, river {V(s, 'q'):.1f} %, forebay {V(s, 'l'):.2f} m, {kw(s):.0f} kW")
    check(abs(V(s, 'l') - 7.0) < 0.3, 'forebay held near 7.0 m (23 ft)')
    pfa = __import__('math').degrees(__import__('math').atan2(0.02 * V(s, 'x') * __import__('math').cos(__import__('math').radians(V(s, 'dl'))) - 2, kw(s) / hydro.PBASE))
    check(15 < pfa < 22, f"AVR holds 0.95 power factor lagging ({__import__('math').cos(__import__('math').radians(pfa)):.3f}, field {V(s, 'x'):.0f} %)")
    import math
    s.run(1.0)
    p_, q_ = V(s, 'pe'), V(s, 'qe')
    amps_true = 409 * math.hypot(p_, q_) * 100 / V(s, 'v')
    amps = s['p_amps'].pos() * 500
    check(abs(amps - amps_true) < 0.05 * amps_true + 5, f'GEN AMPS reads {amps:.0f} A (|S|/V gives {amps_true:.0f} A at {kw(s):.0f} kW)')
    gridv = s['p_gridv'].pos() * 600
    busf = 54 + 12 * s['p_sfreq'].pos()
    check(abs(gridv - 4.8 * V(s, 'vg')) < 1 and 474 < gridv < 488, f'GRID VOLTS reads {gridv:.0f} V')
    check(abs(busf - 60) < 0.01, f'BUS FREQ reads {busf:.2f} Hz')
    stt = s['p_st'].pos() * 150
    check(30 < stt < 100 and abs(stt - V(s, 'st')) < 1, f"STATOR TEMP reads {stt:.0f} C at {amps:.0f} A")
    return s


def scenario_load_rejection(s):
    print('52G opened at load with the PLC on: load rejection')
    flip(s, 'r_52', 0.1)
    peak = 0
    for _ in range(int(40 / 0.06)):
        s.run(0.06); peak = max(peak, V(s, 'n'))
    check(V(s, 'tr') == 0 and 105 < peak < 130, f'the governor catches it: peak {peak:.1f} %, no trip')
    check(abs(V(s, 'n') - 100) < 1.5, f"back at speed-no-load: {V(s, 'n'):.2f} %, gate {V(s, 'g'):.1f} %")
    return s


def scenario_trip(s):
    print('wicket gate trip on line')
    g0 = V(s, 'g')
    flip(s, 'r_gt', 0.1)
    s.run(0.9)
    check(V(s, 'tr') == 1 and V(s, 'cb') == 0 and V(s, 'exc') == 0, 'immediate shutdown: 52G and 41 open at once')
    check(V(s, 'g') > 5, f"the gates close at the servomotor rate ({g0:.0f} % -> {V(s, 'g'):.0f} % after 1 s)")
    peak = 0
    for _ in range(int(6 / 0.06)):
        s.run(0.06); peak = max(peak, V(s, 'n'))
    check(V(s, 'g') < 1 and 104 < peak < 140, f"gates shut in about {g0 / 20:.1f} s; the unit overspeeds to {peak:.0f} % meanwhile, under the 12 setting")
    check(V(s, 'plc') == 0 and V(s, 'avr') == 0 and s['r_52_r'].ang == 0 and s['r_52_l'].ang == 0 and s['r_gt_r'].ang == 0,
          'GOV and AVR dropped to MAN; the 52G and 86U handles back at normal (spring return)')
    flip(s, 'r_plc')
    check(V(s, 'plc') == 0, 'GOV stays in MAN while locked out')
    check(V(s, 'ua_lock') == 1 and V(s, 'ua_gbkr') == 1, '86U UNIT LOCKOUT and 52G GEN BKR TRIPPED flash')
    flashes = set()
    for _ in range(12):
        s.run(0.12); flashes.add(s['A00'].on)
    check(flashes == {True, False}, 'the windows blink')
    check(s['s_horn'].playing, 'horn')
    s.run(5)
    check(s['s_horn'].playing, 'the horn keeps sounding until acknowledged')
    s.use('b_ack'); s.run(0.6)
    check(not s['s_horn'].playing and V(s, 'aa_lock') == 1 and s['A00'].on, 'ACKNOWLEDGE: horn off, windows steady')
    s.run(3)
    if s['s_horn'].playing:                         # the gate slam drew the oil low: a new alarm
        s.use('b_ack'); s.run(0.6)
    flip(s, 'r_gt', 0.8)
    check(V(s, 'tr') == 0, '86U RESET clears the lockout')
    s.run(0.5)
    check(s['A00'].on, 'the windows stay lit until RESET')
    s.use('b_rst'); s.run(0.6)
    check(not s['A00'].on and not s['A01'].on, 'RESET puts them out')
    s.use('b_test'); s.run(0.6)
    check(all(s[w['ent'].name].on for w in dev['windows']), 'TEST lights every window')
    s.run(3.5)
    s.run(30)
    print(f"    after 30 s: n={V(s, 'n'):.1f} v={V(s, 'v'):.1f} x={V(s, 'x'):.1f}")
    # field again after the trip, AVR in MAN: the knob tracked the AVR, so the field comes back
    flip(s, 'r_plc')
    wait_for(s, lambda: V(s, 'n') > 92, 60)
    flip(s, 'r_exc')
    s.run(8)
    check(V(s, 'exc') == 1 and 95 < V(s, 'v') < 106, f"41 closes after the trip, volts {V(s, 'v') * 4.8:.0f} V in MAN")


def scenario_blind_close():
    print('52G closed with the synchroscope off, out of phase')
    s = new_sim()
    start_aux(s)
    flip(s, 'r_plc'); flip(s, 'r_avr')
    wait_for(s, lambda: V(s, 'n') > 92, 60)
    flip(s, 'r_exc'); s.run(10)
    wait_for(s, lambda: 90 < V(s, 'th') < 270, 60)
    flip(s, 'r_52', 0.6)
    check(V(s, 'tr') == 1 and V(s, 'cb') == 0 and V(s, 'ua_oc') == 1, '50 GEN INST OVERCURRENT trip')
    print('52G refused by the sync check')
    s.run(1.0)
    flip(s, 'r_gt', 0.8)
    flip(s, 'r_plc'); flip(s, 'r_avr')
    wait_for(s, lambda: V(s, 'n') > 92, 60)
    flip(s, 'r_exc'); s.run(10)
    flip(s, 'r_ss')
    wait_for(s, lambda: 90 < V(s, 'th') < 270, 60)
    flip(s, 'r_52', 0.2)
    check(V(s, 'cb') == 0 and V(s, 'tr') == 0, 'refused, no trip')
    s.run(1.0)
    check(s['r_52_r'].ang == 0, 'the handle springs back to normal')


def scenario_rough_close():
    print('52G closed unsupervised 30 deg out')
    s = new_sim()
    start_aux(s)
    flip(s, 'r_plc'); flip(s, 'r_avr')
    wait_for(s, lambda: V(s, 'n') > 92, 60)
    flip(s, 'r_exc'); s.run(25)
    wait_for(s, lambda: 25 < V(s, 'th') < 35, 120)
    th = V(s, 'th')
    flip(s, 'r_52', 0.06)
    ks = []
    for _ in range(int(5 / 0.03)):
        s.run(0.03); ks.append(kw(s))
    check(V(s, 'cb') == 1 and V(s, 'tr') == 0, f'closed at {th:.0f} deg with 25 SYNC off: the breaker holds')
    check(max(ks) - min(ks) > 150 and abs(ks[-1] - ks[-20]) < 5, f'the rotor is wrenched into step: {max(ks):.0f} kW to {min(ks):.0f} kW, then steady')


def scenario_quick_shutdown(s):
    print('lube oil lost at load: 38 trip, quick shutdown')
    flip(s, 'r_lp')
    t = wait_for(s, lambda: V(s, 'tr') == 1, 60)
    check(V(s, 'tr') == 1 and V(s, 'cb') == 1, f'38 THR BRG TEMP HI-HI after {t:.0f} s; 52G stays closed while the gates close')
    peak, tcb = 0, None
    for k in range(int(8 / 0.06)):
        s.run(0.06); peak = max(peak, V(s, 'n'))
        if tcb is None and V(s, 'cb') == 0:
            tcb = (k + 1) * 0.06; gcb = V(s, 'g'); pcb = kw(s)
    check(tcb is not None and gcb < 17 and V(s, 'exc') == 0, f'52G and 41 open {tcb:.1f} s later at {gcb:.0f} % gate')
    check(peak < 102, f'no overspeed: peak {peak:.1f} %')
    check(V(s, 'ua_bthh') == 1 and V(s, 'ua_lock') == 1, 'windows: 38 THR BRG TEMP HI-HI TRIP, 86U UNIT LOCKOUT')


def scenario_overspeed(s):
    print('52G opened by hand at load, PLC off: overspeed')
    flip(s, 'r_52', 0.2)
    peak = 0
    for _ in range(300):
        s.run(0.06); peak = max(peak, V(s, 'n'))
    check(V(s, 'tr') == 1 and (V(s, 'ua_ovsp') or V(s, 'aa_ovsp')), f'12 OVERSPEED trip, peak {peak:.0f} %')


if __name__ == '__main__':
    scenario_idle()
    s = scenario_manual_start()
    scenario_overspeed(s)
    s = scenario_plc_start()
    scenario_trip(s)
    s = scenario_plc_start()
    scenario_load_rejection(s)
    s = scenario_plc_start()
    scenario_quick_shutdown(s)
    scenario_blind_close()
    scenario_rough_close()
    print('FAILED:' if FAILS else 'all passed', *FAILS, sep='\n  ')
    sys.exit(1 if FAILS else 0)
