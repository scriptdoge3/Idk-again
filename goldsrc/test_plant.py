"""Run the plant logic in the hl.dll-behaviour simulator and check the physics, operating it by hand."""
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
KNOB = {'k_gate': (180, 3600), 'k_fa': (120, 3600)}
for k in dev['knobs']:
    sp, dist = KNOB[k['name']]
    devs.append({'classname': 'momentary_rot_button', 'targetname': k['name'], 'target': k['target'], 'speed': str(sp), 'distance': str(dist)})
sc = dev['scope']
devs.append({'classname': 'func_train', 'targetname': 'SCOPE', 'speed': str(sc['speed'])})
sim = Sim(ents + devs)
sim.train_path['SCOPE'] = [(f'sc{i}', msg, sc['R'], ang) for i, (ang, msg) in enumerate(sc['corners'])]
G = lambda k: sim.globals.get(k)
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
    Each new grab turns the other way (stock momentary_rot_button), so a quick tap is used to reverse."""
    k = sim.ent(knob); t0 = sim.time
    while C(var) != target and sim.time - t0 < limit:
        want_up = C(var) < target
        if bool(G(f'{knob}_u')) != want_up:
            k.hold(0.01); sim.run(0.4); continue
        while C(var) != target and (C(var) < target) == want_up and sim.time - t0 < limit:
            k.hold(0.02)
        sim.run(0.4)
    return C(var)
def flip(name, settle=0.6):
    r = sim.press(name); sim.run(settle); return r
def windows():
    return [dev['ann'][i].replace('|', ' ') for i, w in enumerate(dev['walls'][:16]) if sim.ent(w).on != bool(dev['ann_init'].get(i, 0))]
def lit():
    return [dev['ann'][i].replace('|', ' ') for i in range(16) if sim.ent(f'A{i:02d}').on != bool(dev['ann_init'].get(i, 0)) ^ False]

sim.run(5); show('dark')
print('try to release brakes with no air:', flip('r_br', 2), ' brake', G('brake'))
for sw in ('r_lp', 'r_wp', 'r_hp', 'r_ac'):
    flip(sw, 0.5)
tt = run_until(lambda: C('o') >= 10 and C('a') >= 6, 30); print(f'aux running, servo oil and air charged after {tt} s'); show('aux')
sim.run(1); print('brakes released:', G('brake') == 0)
# manual run-up: open the gate, then back to speed-no-load as speed comes up
print('gate', turn('k_gate', 'g', 6))
tt = run_until(lambda: C('n') >= 32, 60); print(f'80 % speed after {tt} s'); turn('k_gate', 'g', 2)
tt = run_until(lambda: C('n') == 40, 60); print(f'100 % speed {tt} s later'); show('snl')
flip('r_exc'); print('41 closed, exc', G('exc'), ' field', turn('k_fa', 'x', 40))
run_until(lambda: C('v') == 40, 20); show('excited')
flip('r_ss', 1); print('synchroscope on, rotating', G('scr'))
scope = sim.ent('SCOPE')
run_until(lambda: G('inph') == 0, 10, 0.05); run_until(lambda: G('inph') == 1, 10, 0.05)   # wait for the window to open
sim.press('r_52'); sim.run(0.4); print(f'52G turned to CLOSE at pointer {scope.angle():.0f} deg -> cb={G("cb")}')
sim.run(1); show('on line')
print('kW', turn('k_gate', 'g', 12), '->', round(sim.ent('p_kw').pos * 320), 'kW (KW[12]=', KW[12], ')')
print('field to 46 (overexcited):', turn('k_fa', 'x', 46), ' kvar pointer', round(sim.ent('p_kvar').pos * 400 - 200), 'kvar')
run_until(lambda: False, 30); show('loaded')

# emergency stop from load: the gate trip
pk = [0]; track = lambda s: pk.__setitem__(0, max(pk[0], s.counter('n')))
print('WICKET GATE TRIP:', sim.press('r_gt')); sim.run(10, every=track); show('tripped')
print(f'  peak speed {pk[0] * 2.5} %, handles: 52G {sim.ent("r_52").pos} 41 {sim.ent("r_exc").pos} gate-trip {sim.ent("r_gt").pos}')
run_until(lambda: C('n') <= 12, 200); flip('r_br'); tt = run_until(lambda: C('n') == 0, 120); print(f'brakes applied at 30 %, stopped {tt} s later')
flip('r_gt', 1); print('gate trip reset: tr', G('tr'))

# out-of-phase close, run up with the PLC and AVR doing the work
flip('r_plc'); flip('r_avr'); flip('r_br', 1)
tt = run_until(lambda: C('n') == 40 and C('g') == 2, 120); print(f'PLC ran the unit up to speed-no-load in {tt} s'); show('plc')
flip('r_exc'); run_until(lambda: C('v') == 40, 30); print('AVR excited it: v', C('v'), 'x', C('x'))
run_until(lambda: G('scr') == 1 and G('inph') == 0, 15, 0.05)
sim.press('r_52'); sim.run(0.4); print(f'52G closed OUT of phase at pointer {scope.angle():.0f} deg -> cb={G("cb")} tr={G("tr")} OUT OF PHASE lit={sim.ent("A02").on}')
run_until(lambda: C('n') <= 12, 200); flip('r_br'); run_until(lambda: C('n') == 0, 120); flip('r_br', 0.5); flip('r_gt', 1)
print('reset: tr', G('tr'), 'OUT OF PHASE lit', sim.ent('A02').on)

# PLC/AVR on line, then lose the lube oil pump
run_until(lambda: C('n') == 40, 120); flip('r_exc'); run_until(lambda: C('v') == 40, 30); run_until(lambda: G('scr') == 1 and G('inph') == 0, 30, 0.05); run_until(lambda: G('inph') == 1, 10, 0.05)
sim.press('r_52'); sim.run(1); print('back on line:', G('cb'))
print('52G turned to TRIP by hand:', sim.press('r_52')); sim.run(1); print('  cb', G('cb'), 'handle', sim.ent('r_52').pos)
print('41 turned to OPEN by hand:', sim.press('r_exc')); sim.run(1); print('  exc', G('exc'), 'handle', sim.ent('r_exc').pos)
flip('r_exc'); run_until(lambda: C('v') == 40, 30); run_until(lambda: G('scr') == 1 and G('inph') == 0, 30, 0.05); run_until(lambda: G('inph') == 1, 10, 0.05)
sim.press('r_52'); sim.run(1); print('re-synchronized:', G('cb'))
l0 = C('l'); run_until(lambda: False, 180); show('PLC level'); print(f'  PLC holding the pond: level {l0} -> {C("l")} (12 = 513.0 ft), gate {C("g")}')
flip('r_lp'); tt = run_until(lambda: G('tr') == 1, 60); print(f'lube oil pump stopped: bearing trip after {tt} s, bt={C("bt")}'); show('lube trip')
flip('r_lp'); run_until(lambda: C('n') == 0, 400)
flip('r_gt', 1); print('lube oil pump restarted, reset: tr', G('tr'))
flip('r_ac'); tt = run_until(lambda: G('brake') == 1 and G('hbr') == 1, 120)
print(f'compressor off, brakes released: air fell and the brakes re-applied after {tt} s (a={C("a")})')
print('multi_manager re-trigger collisions:', sim.mm_ignored)

import re
stuck = [m for m in re.findall(r'"classname" "func_rot_button"(.*?)\}', open('out/sablecreek.map').read(), re.S) if '"wait" "-1"' in m]
print('func_rot_buttons in the map with wait -1 (they would never come back):', len(stuck))
