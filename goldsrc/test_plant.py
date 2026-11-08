"""Run the plant logic in the hl.dll-behaviour simulator and check the physics, operating it by hand."""
import math
from hlogic import Sim
from plant import build, KW

L, ents, dev = build()
devs = []
for lm in dev['lamps']: devs.append({'classname': 'func_wall', 'targetname': lm['name']})
for w in dev['walls']: devs.append({'classname': 'func_wall', 'targetname': w})
for p in dev['ptrs']: devs.append({'classname': 'momentary_door', 'targetname': p})
for s in dev['sounds']: devs.append({'classname': 'ambient_generic', 'targetname': s['name'], 'spawnflags': '16' if s['loop'] else '48', 'pitch': '100'})
for r in dev['rots']: devs.append({'classname': 'func_rot_button', 'targetname': r['name'], 'target': r['target'], 'wait': str(r['wait']),
                                   'spawnflags': '32' if r['toggle'] else '0', 'distance': str(r['distance']), 'speed': str(r['speed'])})
for k in dev['knobs']:                     # as build.py makes them
    kv = dict(speed=240, distance=60, returnspeed=300, spawnflags=144) if k.get('spring') else dict(speed=120, distance=3600, spawnflags=128)
    devs.append({'classname': 'momentary_rot_button', 'targetname': k['name'], 'target': k['target'], **{a: str(b) for a, b in kv.items()}})
sc = dev['scope']
devs.append({'classname': 'func_tracktrain', 'targetname': 'SCOPE', 'speed': str(sc['speed'])})
devs.append({'classname': 'func_wall_toggle', 'targetname': 'SLCOVER'})
sim = Sim(ents + devs)
sim.train_nodes['SCOPE'] = [(msg, sc['R'] * math.sin(math.radians(a)), sc['R'] * math.cos(math.radians(a))) for a, msg in sc['nodes']]
G = lambda k: sim.globals.get(k)
depth = lambda: 4 + 0.25 * sim.counter('l')          # river depth, m
C = sim.counter
S = lambda: dict(t=round(sim.time, 1), n=C('n'), g=C('g'), v=C('v'), x=C('x'), o=C('o'), a=C('a'), bt=C('bt'), l=C('l'), sg=C('sg'),
                 cb=G('cb'), exc=G('exc'), tr=G('tr'), brake=G('brake'), kw=round(sim.ent('p_kw').pos * 320))
def show(tag=''):
    print(tag.ljust(10), ' '.join(f'{k}={v}' for k, v in S().items()))
def run_until(cond, limit, step=0.5):
    t0 = sim.time
    while sim.time - t0 < limit:
        sim.run(step)
        if cond(): return round(sim.time - t0, 1)
    return None
def turn(knob, var, target, limit=60):
    """Turn a knob like a player: hold it until the gauge shows the target, let go, correct if it went one past.
    Each new grab turns the other way (stock momentary_rot_button), so a quick tap is used to reverse.
    A step already pending when you let go can still land, so after a few tries one step off is accepted."""
    k = sim.ent(knob); t0 = sim.time; tries = 0
    while C(var) != target and sim.time - t0 < limit and not (tries >= 3 and abs(C(var) - target) <= 1):
        tries += 1
        want_up = C(var) < target
        if bool(G(f'{knob}_u')) != want_up:
            k.hold(0.01); sim.run(0.4); continue
        while C(var) != target and (C(var) < target) == want_up and sim.time - t0 < limit:
            k.hold(0.02)
        sim.run(0.4)
    return C(var)
def gate_to(target, raise_='k_gr', lower='k_gl', var='g', limit=60):
    """Hold RAISE or LOWER like a player until the gauge shows the target, let go, correct if it went past."""
    t0 = sim.time
    while C(var) != target and sim.time - t0 < limit:
        up = C(var) < target
        k = sim.ent(raise_ if up else lower)
        while C(var) != target and (C(var) < target) == up and sim.time - t0 < limit:
            k.hold(0.02)
        sim.run(0.8)
    return C(var)
def scope_turn(seconds=3.0):
    """degrees the synchroscope pointer turns in `seconds` (+ = clockwise, FAST)"""
    sc_ = sim.ent('SCOPE'); tot = [0.0]; last = [sc_.angle()]
    def acc(s_):
        a_ = sc_.angle(); tot[0] += (a_ - last[0] + 180) % 360 - 180; last[0] = a_
    sim.run(seconds, every=acc)
    return round(tot[0])
def pf_reading():
    f = sim.ent('p_pf').pos; phi = (f - 0.5) * 120
    return f"{math.cos(math.radians(phi)):.2f} {'LAG' if phi > 0.5 else 'LEAD' if phi < -0.5 else ''}".strip()
def flip(name, settle=0.6):
    r = sim.press(name); sim.run(settle); return r
def windows():
    return [dev['ann'][i].replace('|', ' ') for i, w in enumerate(dev['walls'][:16]) if sim.ent(w).on != bool(dev['ann_init'].get(i, 0))]
def lit():
    return [dev['ann'][i].replace('|', ' ') for i in range(16) if sim.ent(f'A{i:02d}').on != bool(dev['ann_init'].get(i, 0)) ^ False]

sim.run(5); show('dark')
riv = []; sim.run(600, every=lambda s_: riv.append(C('rq')) if round(s_.time * 100) % 3200 == 0 else None)
print('river flow, % every 32 s for 10 min (the unit stopped):', [65 + 5 * q for q in riv], f' river depth {depth()} m, spill gate {C("sg")}')
print('try to release brakes with no air:', flip('r_br', 2), ' brake', G('brake'))
for sw in ('r_lp', 'r_wp', 'r_hp', 'r_ac'):
    flip(sw, 0.5)
tt = run_until(lambda: C('o') >= 10 and C('a') >= 6, 30); print(f'aux running, hydraulic and air charged after {tt} s'); show('aux')
sim.run(1); print('brakes released:', G('brake') == 0)
# manual run-up: open the gate, then back to speed-no-load as speed comes up
k = sim.ent('k_gr'); k.hold(1.0); g_rel = C('g'); sim.run(0.15); g_015 = C('g'); sim.run(1.5)
print(f'RAISE held 1 s: gate {g_rel} % at release, {g_015} % 0.15 s later, {C("g")} % after the dial sprang back '
      f'({k.return_fires} fires on the way back, ignored); dial at {k.pos:.2f}')
for t in (0.02, 0.05, 0.1, 0.3):
    g0 = C('g'); sim.ent('k_gr').hold(t); sim.run(1.0); print(f'  tap RAISE {t:.2f} s: +{C("g") - g0} %')
print('gate', gate_to(25))
tt = run_until(lambda: C('n') >= 80, 60); print(f'80 % speed after {tt} s'); gate_to(15)
tt = run_until(lambda: C('n') == 100, 60); print(f'100 % speed {tt} s later'); show('snl')
for gg in (16, 14, 15):
    gate_to(gg); run_until(lambda: False, 12); print(f'  gate {C("g")} % -> speed settles at {C("n")} %')
flip('r_exc'); print('41 closed, exc', G('exc'), ' field', turn('k_fa', 'x', 100))
run_until(lambda: C('v') == 100, 20); show('excited')
scope = sim.ent('SCOPE')
print(f'phase running {G("phs")} with the synchroscope still off; lamps covered {sim.ent("SLCOVER").on}')
flip('r_ss', 1); print(f'synchroscope on: lamps covered {sim.ent("SLCOVER").on}')
print(f'  at exactly 100 % speed the phase stands still: {scope_turn(5.5)} deg in 5.5 s, at {scope.angle():.0f} deg')
bad = []
def window_check(s_):
    """the logic's in-phase flag against where the pointer is; the edges fire when the point the train looks
    0.1 s ahead to passes them, so the window leads the pointer by that much (3 deg at the sync slip)"""
    if G('phs'):
        a_ = (scope.angle() + 180) % 360 - 180
        lead = math.degrees(abs(scope.speed) * 0.1 / sc['R']) + 2
        if (abs(a_) < 30 - lead and not G('inph')) or (abs(a_) > 30 + lead and G('inph')): bad.append(round(a_))
for gg in (14, 16):
    gate_to(gg); run_until(lambda: C('n') in (94, 104), 30)
    gate_to(15); trace = []
    for _ in range(14):
        n0 = C('n'); d = scope_turn(0.5); trace.append((n0, d))
        sim.run(0, every=window_check)
    print(f'  speed {"rising" if gg == 14 else "falling"} to 100 % (speed, pointer deg per 0.5 s, + = FAST):', trace)
for gg in (14, 15, 16, 15):
    gate_to(gg); sim.run(8, every=window_check)
print('  in-phase flag disagreeing with the pointer (deg):', bad[:10], len(bad))
run_until(lambda: C('n') == 100, 30); sim.run(4)
lev = []
run_until(lambda: lev.append((round(scope.angle()), sim.ent('SYNCLAMPS').amt)) or False, 12, 0.5)
print('  sync lamps (pointer deg, brightness):', lev[:12])
def nudge_in(limit=180):
    """Bring the phase into the window like a player: tap RAISE (or LOWER) once, and when the speed reaches
    101 % (99 %) and the pointer starts to turn, tap the other one; the speed comes back to 100 % and the
    pointer stops. Returns how far each touch moved it."""
    t0 = sim.time; moves = []
    while not G('perm') and sim.time - t0 < limit:
        a_ = scope.angle(); cw = not (30 < a_ < 180)          # the short way round to 12 o'clock
        up, back = ('k_gr', 'k_gl') if cw else ('k_gl', 'k_gr')
        sim.ent(up).hold(0.05); run_until(lambda: C('n') != 100, 10, 0.05)
        sim.ent(back).hold(0.05); run_until(lambda: C('n') == 100 and C('g') == 15, 10, 0.05); sim.run(0.3)
        moves.append(round(((scope.angle() - a_ + 180) % 360) - 180))
    return moves
sim.run(2); a0 = scope.angle()
print(f'  phase at {a0:.0f} deg, SYNC OK {G("perm")}; nudged into the window, deg per touch {nudge_in()}: now {scope.angle():.0f} deg, '
      f'stays there: {scope_turn(4.0)} deg in 4 s, SYNC OK {G("perm")}')
a_press = scope.angle()
sim.press('r_52'); sim.run(0.1); print(f'52G turned to CLOSE with SYNC OK lit (phase {a_press:.0f} deg) -> cb={G("cb")}')
sim.run(1); show('on line')
print(f'  phase locked at {scope.angle():.0f} deg once on line, phase running {G("phs")}')
print('PF just after closing:', pf_reading(), ' (x', C('x'), ')')
for gg in (25, 40, 60):
    gate_to(gg); sim.run(1); print(f'  gate {gg} %: {round(sim.ent("p_kw").pos * 320)} kW, PF {pf_reading()}')
print('kW', C('g'), '->', round(sim.ent('p_kw').pos * 320), 'kW (KW[60]=', KW[60], ')')
print('field to 115 (overexcited):', turn('k_fa', 'x', 115), ' PF', pf_reading())
print('field to 94 (underexcited):', turn('k_fa', 'x', 94), ' PF', pf_reading()); turn('k_fa', 'x', 115)
run_until(lambda: False, 30); show('loaded')

# emergency stop from load: the gate trip
pk = [0]; track = lambda s: pk.__setitem__(0, max(pk[0], s.counter('n')))
print('WICKET GATE TRIP:', sim.press('r_gt')); sim.run(10, every=track); show('tripped')
print(f'  peak speed {pk[0]} %, handles: 52G {sim.ent("r_52").pos} 41 {sim.ent("r_exc").pos} gate-trip {sim.ent("r_gt").pos}')
run_until(lambda: C('n') <= 30, 200); flip('r_br'); tt = run_until(lambda: C('n') == 0, 120); print(f'brakes applied at 30 %, stopped {tt} s later')
flip('r_gt', 1); print('gate trip reset: tr', G('tr'))

# out-of-phase close, run up with the PLC and AVR doing the work
flip('r_plc'); flip('r_avr'); flip('r_br', 1)
tt = run_until(lambda: C('n') == 100 and C('g') == 15, 120); print(f'PLC ran the unit up to speed-no-load in {tt} s'); show('plc')
flip('r_exc'); run_until(lambda: C('v') == 100, 30); print('AVR excited it: v', C('v'), 'x', C('x'))
print(f'  with the PLC the unit is held a hair fast: the phase creeps {scope_turn(5.5)} deg in 5.5 s')
run_until(lambda: G('phs') == 1 and G('inph') == 0, 15, 0.05)
sim.press('r_52'); sim.run(0.15); a_try = scope.angle(); sim.run(1.0)
print(f'52G turned to CLOSE outside the window (pointer {a_try:.0f} deg): refused, cb={G("cb")} tr={G("tr")} handle back={sim.ent("r_52").pos == 0}')
flip('r_ss', 1)                                              # synchroscope (sync check) off
run_until(lambda: G('inph') == 0 and 60 < scope.angle() < 300, 20, 0.05); a_try = scope.angle()
sim.press('r_52'); sim.run(0.5); print(f'52G closed blind with the synchroscope off, phase {a_try:.0f} deg -> cb={G("cb")} tr={G("tr")} OUT OF PHASE lit={sim.ent("A02").on}')
flip('r_ss', 1)
run_until(lambda: C('n') <= 30, 200); flip('r_br'); run_until(lambda: C('n') == 0, 120); flip('r_br', 0.5); flip('r_gt', 1)
print('reset: tr', G('tr'), 'OUT OF PHASE lit', sim.ent('A02').on)

# PLC/AVR on line, then lose the oil pump
run_until(lambda: C('n') == 100, 120); flip('r_exc'); run_until(lambda: C('v') == 100, 30)
flip('r_ss', 1); run_until(lambda: G('pok') == 1, 30, 0.05); a_try = scope.angle()
sim.press('r_52'); sim.run(1); print(f'52G closed blind with the synchroscope off but the phase at {a_try:.0f} deg: closed {G("cb")}, tr {G("tr")}')
flip('r_ss', 1)
print('52G turned to TRIP by hand:', sim.press('r_52')); sim.run(1); print('  cb', G('cb'), 'handle', sim.ent('r_52').pos)
print('41 turned to OPEN by hand:', sim.press('r_exc')); sim.run(1); print('  exc', G('exc'), 'handle', sim.ent('r_exc').pos)
flip('r_exc'); run_until(lambda: C('v') == 100, 30); run_until(lambda: G('perm') == 1, 30, 0.05)
sim.press('r_52'); sim.run(1); print('re-synchronized:', G('cb'))
hist = []; sim.run(400, every=lambda s_: hist.append((C('l'), C('g'), C('rq'), C('sg'))) if round(s_.time * 100) % 100 == 0 else None)
show('PLC level')
print(f'  PLC following the river for 400 s: river flow {65 + 5 * min(h[2] for h in hist)}-{65 + 5 * max(h[2] for h in hist)} %, '
      f'river depth {4 + 0.25 * min(h[0] for h in hist)}-{4 + 0.25 * max(h[0] for h in hist)} m, gate {min(h[1] for h in hist)}-{max(h[1] for h in hist)} %, '
      f'spill gate {min(h[3] for h in hist)}-{max(h[3] for h in hist)}, still on line {G("cb")}')
flip('r_lp'); tt = run_until(lambda: G('tr') == 1, 60); print(f'oil pump stopped: bearing trip after {tt} s, bt={C("bt")}'); show('lube trip')
flip('r_lp'); run_until(lambda: C('n') == 0, 400)
flip('r_gt', 1); print('oil pump restarted, reset: tr', G('tr'))
flip('r_ac'); tt = run_until(lambda: G('brake') == 1 and G('hbr') == 1, 120)
print(f'compressor off, brakes released: air fell and the brakes re-applied after {tt} s (a={C("a")})')

# spillway panel: manual control
sg0 = C('sg'); sim.ent('k_sr').hold(2.0); sim.run(0.5)
print(f'spill gate {sg0} in AUTO; RAISE held 2 s does nothing: {C("sg")}')
flip('r_sp'); print('CONTROL to MANUAL:', G('sman'))
tt = sim.time; print('  RAISE to 8 (4 ft):', gate_to(8, 'k_sr', 'k_sl', 'sg'), f'in {sim.time - tt:.1f} s; pointer', round(sim.ent('p_spill').pos * 8))
print('  LOWER to 2:', gate_to(2, 'k_sr', 'k_sl', 'sg'), ' river depth', depth(), 'm')
l0 = C('l'); run_until(lambda: False, 120); print(f'  in MANUAL the gate stays at {C("sg")}; river depth {4 + 0.25 * l0} -> {depth()} m (9.0 = bank full)')
flip('r_sp'); run_until(lambda: False, 200); print(f'  back to AUTO: gate {C("sg")}, river depth {depth()} m')
print('multi_manager re-trigger collisions:', sim.mm_ignored)

import re
stuck = [m for m in re.findall(r'"classname" "func_rot_button"(.*?)\}', open('out/sablecreek.map').read(), re.S) if '"wait" "-1"' in m]
print('func_rot_buttons in the map with wait -1 (they would never come back):', len(stuck))
