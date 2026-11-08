"""Runs the plant in the Source entity simulator: start-up, synchronizing, loading, trips."""
import sys
from hydro import build
from srcsim import Sim

m, P, dev = build()


def bin_ops():
    ops = {}
    for e in m.ents:
        for out, tgt, inp, par, d, t in e.outputs:
            if tgt in P.levels and inp != 'SetValueNoFire':
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


def trim(s, lo=100.0, hi=100.2):
    for _ in range(60):
        n = V(s, 'n')
        if lo <= n <= hi:
            return True
        s.hold('k_gr' if n < lo else 'k_gl', 0.35)
        s.run(6.0)
    return False


def start_aux(s):
    for sw in ('r_lp', 'r_wp', 'r_hp', 'r_ac'):
        flip(s, sw, 0.5)
    s.run(16)
    flip(s, 'r_br')                    # BRAKES to RELEASE


def scenario_idle():
    print('idle')
    s = new_sim()
    s.run(10)
    check(not s.errors, f'two-input nodes always got their first value first ({len(s.errors)} errors)')
    check(abs(V(s, 'l') - 7.0) < 0.05, f"river depth holds at 7.0 m ({V(s, 'l'):.2f})")
    lit = [w['legend'] for w in dev['windows'] if s[w['ent'].name].on]
    check(set(lit) == {'HYD OIL|PRESS LOW', 'OIL PUMP|STOPPED', 'WATER PUMP|STOPPED', 'BRAKE AIR|PRESS LOW',
                       'SPILLWAY GATE|OPEN', 'PLC|OFF', 'AVR IN|MANUAL'}, f'windows lit at rest: {lit}')
    check(not s['s_horn'].playing, 'no horn at start')
    check(abs(s['k_fa'].pos() - 0.627) < 0.01, 'firing-angle knob at rated field')


def scenario_manual_start():
    print('manual start, sync by hand, load')
    s = new_sim()
    start_aux(s)
    check(V(s, 'hp') > 290, f"hydraulic oil charged ({V(s, 'hp'):.0f} psi)")
    check(V(s, 'air') > 100, f"brake air charged ({V(s, 'air'):.0f} psi)")
    t80 = to_speed_no_load(s)
    check(abs(V(s, 'n') - 100) < 3, f"speed-no-load by hand: n={V(s, 'n'):.2f} g={V(s, 'g'):.2f} (80 % after {t80:.1f} s)")
    flip(s, 'r_avr')                   # AVR AUTO
    flip(s, 'r_exc')                   # 41 close
    check(V(s, 'exc') == 1, '41 closes above 90 % speed')
    s.run(8)
    check(abs(V(s, 'v') - 100) < 1.5, f"AVR brings the volts to 480 V ({V(s, 'v') * 4.8:.0f} V)")
    flip(s, 'r_ss')
    ok = trim(s)
    check(ok, f"trimmed by hand to {V(s, 'n'):.3f} %")
    th0 = V(s, 'th'); s.run(2); th1 = V(s, 'th')
    check(th1 != th0, f'the phase turns ({th0:.0f} -> {th1:.0f} deg)')
    # wait for the window and close
    t = wait_for(s, lambda: V(s, 'perm') == 1, 120)
    check(V(s, 'perm') == 1, f'SYNC CHECK lamp lit after {t:.1f} s')
    flip(s, 'r_52', 0.4)
    check(V(s, 'cb') == 1, '52G closes in phase')
    check(s['LP_cb_1'].on and not s['LP_cb_0'].on, 'CLOSED lamp lit')
    s.hold('k_gr', 6)
    s.run(1)
    kw = s['p_kw'].pos() * 320
    check(kw > 100, f"loads by hand: gate {V(s, 'g'):.0f} %, {kw:.0f} kW")
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
    s.run(15)
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
    check(V(s, 'g') > 50, f"PLC on line passes the river: gate {V(s, 'g'):.1f} %, river {V(s, 'q'):.1f} %, depth {V(s, 'l'):.2f} m")
    check(abs(V(s, 'l') - 7.0) < 0.3, 'depth held near 7.0 m')
    return s


def scenario_trip(s):
    print('wicket gate trip on line')
    flip(s, 'r_gt', 0.1)
    s.run(0.9)
    check(V(s, 'tr') == 1 and V(s, 'cb') == 0 and V(s, 'exc') == 0, 'tripped: 52G and 41 open')
    check(V(s, 'g') < 1, f"gate shut at once ({V(s, 'g'):.1f} %)")
    s.run(1.0)
    check(V(s, 'plc') == 0 and V(s, 'avr') == 0 and V(s, 'h52') == 0 and V(s, 'hexc') == 0,
          'PLC, AVR, 52G and 41 handles turned to OFF / MAN / TRIP')
    check(s['A01'].on and s['A02'].on, '86 LOCKOUT and 52G GEN BKR TRIPPED lit')
    check(s['s_horn'].playing, 'horn')
    s.run(7)
    check(not s['s_horn'].playing, 'horn silences itself')
    flip(s, 'r_gt', 0.8)
    check(V(s, 'tr') == 0 and not s['A01'].on and not s['A02'].on, 'reset clears the lockout')
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
    flip(s, 'r_52', 0.3)
    check(V(s, 'tr') == 1 and V(s, 'cb') == 0 and s['A03'].on, '52G CLOSED OUT OF PHASE trip')
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
    check(V(s, 'h52') == 0, 'the handle springs back to TRIP')


def scenario_overspeed(s):
    print('52G opened by hand at load, PLC off: overspeed')
    flip(s, 'r_52', 0.2)
    peak = 0
    for _ in range(300):
        s.run(0.06); peak = max(peak, V(s, 'n'))
    check(V(s, 'tr') == 1 and s['A00'].on, f'12 OVERSPEED trip, peak {peak:.0f} %')


if __name__ == '__main__':
    scenario_idle()
    s = scenario_manual_start()
    scenario_overspeed(s)
    s = scenario_plc_start()
    scenario_trip(s)
    scenario_blind_close()
    print('FAILED:' if FAILS else 'all passed', *FAILS, sep='\n  ')
    sys.exit(1 if FAILS else 0)
