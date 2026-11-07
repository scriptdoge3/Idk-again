"""Run the plant logic in the hl.dll-behaviour simulator and check the physics."""
import sys
from hlogic import Sim
from plant import build, KW

L, ents, dev = build()
devs = []
for lm in dev['lamps']: devs.append({'classname': 'func_wall', 'targetname': lm['name']})
for w in dev['walls']: devs.append({'classname': 'func_wall', 'targetname': w})
for p in dev['ptrs']: devs.append({'classname': 'momentary_door', 'targetname': p})
for s in dev['sounds']: devs.append({'classname': 'ambient_generic', 'targetname': s['name'], 'spawnflags': '16' if s['loop'] else '48', 'pitch': '100'})
for b in dev['buttons']: devs.append({'classname': 'func_button', 'targetname': b['name'], 'target': b['target'], 'master': b.get('master', ''), 'wait': '1'})
for r in dev['rots']: devs.append({'classname': 'func_rot_button', 'targetname': r['name'], 'target': r['target'], 'wait': '0.5'})
sim = Sim(ents + devs)
S = lambda: dict(t=round(sim.time, 1), n=sim.counter('n'), g=sim.counter('g'), v=sim.counter('v'), s=sim.counter('s'), o=sim.counter('o'),
                 l=sim.counter('l'), sg=sim.counter('sg'), h=sim.counter('h'), en=sim.counter('en'), d=sim.counter('d'), dv=sim.counter('dv'), el=sim.counter('el'),
                 cb=sim.globals.get('cb'), run=sim.globals.get('run'), exc=sim.globals.get('exc'), lock=sim.globals.get('lock'), kw=round(sim.ent('p_kw').pos * 320))
def show(tag=''):
    print(tag.ljust(8), ' '.join(f'{k}={v}' for k, v in S().items()))
def run_until(cond, limit, tag='', every=None):
    t0 = sim.time
    while sim.time - t0 < limit:
        sim.run(0.5)
        if every and int(sim.time * 2) % every == 0: show(tag)
        if cond(): return sim.time - t0
    return None

sim.run(30); show('idle')
assert sim.globals.get('ready') == 1, 'READY not set'
print('ready lamp', sim.ent('L_ready').on, ' opu', sim.counter('o'), ' pumps p1', sim.globals.get('p1'))
print('press START:', sim.press('b_start'))
tt = run_until(lambda: sim.globals.get('cb') == 1, 120, 'start', every=4)
print(f'--> synchronized after {tt} s'); show('sync')
run_until(lambda: False, 30); show('+30s')
print('kW pointer', round(sim.ent('p_kw').pos * 320), 'kW  (KW[g]=', KW[sim.counter('g')], ')', ' speed ptr', round(sim.ent('p_speed').pos * 150), '%')
run_until(lambda: False, 240, 'online', every=40); show('+4min')
# utility trip: load rejection with the governor in service
pk = [0]
print('UTILITY TRIP:', sim.press('b_util'))
def track(s): pk[0] = max(pk[0], s.counter('n'))
sim.run(30, every=track); show('rej+30')
print(f'--> peak speed {pk[0]*5} %  (trip at 140 %), lockout={sim.globals.get("lock")}, horn={sim.ent("s_horn").active}')
tt = run_until(lambda: sim.globals.get('cb') == 1, 60)
print(f'--> resynchronized after {tt} s more'); show('resync')
sim.press('b_ack'); sim.press('b_annreset')
run_until(lambda: False, 60); show('loaded')
# normal stop
print('STOP:', sim.press('b_stop'))
tt = run_until(lambda: sim.globals.get('cb') == 0, 120); print(f'--> breaker open after {tt} s'); show('open')
tt = run_until(lambda: sim.counter('n') == 0, 400, 'coast', every=20); print(f'--> standstill after {tt} s more'); show('stopped')
run_until(lambda: False, 10); print('ready', sim.globals.get('ready'), 'brake', sim.globals.get('brake'), 'lift', sim.globals.get('lift'), 'cw', sim.globals.get('cw'))
# E-stop from full load
sim.press('b_start'); run_until(lambda: sim.globals.get('cb') == 1, 120); run_until(lambda: False, 60); show('online2')
pk[0] = 0; print('E-STOP:', sim.press('b_estop'))
sim.run(20, every=track); show('estop')
print(f'--> peak speed {pk[0]*5} %, lock={sim.globals.get("lock")}, START now:', sim.press('b_start'))
run_until(lambda: sim.counter('n') == 0, 400); show('stopped')
print('86 reset:', sim.press('b_reset86')); sim.run(2); sim.press('b_ack'); sim.press('b_annreset'); sim.run(2)
print('lock', sim.globals.get('lock'), 'ready', sim.globals.get('ready'), 'windows lit', [w for w in dev['walls'] if w.startswith('A') and sim.ent(w).on])
# oil pumps fail while running
sim.run(3); sim.press('b_start'); run_until(lambda: sim.globals.get('cb') == 1, 120); show('online3')
sim.press('r_pfail'); tt = run_until(lambda: sim.globals.get('lock') == 1, 600, 'pfail', every=40)
print(f'--> oil pressure trip after {tt} s'); show('opu trip')
print('multi_manager re-trigger collisions:', sim.mm_ignored)
