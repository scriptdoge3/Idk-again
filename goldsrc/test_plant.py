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
for r in dev['rots']: devs.append({'classname': 'func_rot_button', 'targetname': r['name'], 'target': r['target'], 'wait': str(r['wait']),
                                   'spawnflags': '32' if r['toggle'] else '0', 'distance': str(r['distance']), 'speed': str(r['speed'])})
KNOB = {'k_load': (120, 3600), 'k_gate': (180, 3600), 'k_spill': (180, 3600), 'k_river': (100, 300)}
for k in dev['knobs']:
    sp, dist = KNOB[k['name']]
    devs.append({'classname': 'momentary_rot_button', 'targetname': k['name'], 'target': k['target'], 'speed': str(sp), 'distance': str(dist)})
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
print('press START:', sim.press('r_run'))
tt = run_until(lambda: sim.globals.get('cb') == 1, 120, 'start', every=4)
print(f'--> synchronized after {tt} s'); show('sync')
run_until(lambda: False, 30); show('+30s')
print('kW pointer', round(sim.ent('p_kw').pos * 320), 'kW  (KW[g]=', KW[sim.counter('g')], ')', ' speed ptr', round(sim.ent('p_speed').pos * 150), '%')
run_until(lambda: False, 240, 'online', every=40); show('+4min')
# utility trip: load rejection with the governor in service
pk = [0]
print('UTILITY TRIP:', sim.press('r_util'))
def track(s): pk[0] = max(pk[0], s.counter('n'))
sim.run(30, every=track); show('rej+30')
print(f'--> peak speed {pk[0]*5} %  (trip at 140 %), lockout={sim.globals.get("lock")}, horn={sim.ent("s_horn").active}')
tt = run_until(lambda: sim.globals.get('cb') == 1, 60)
print(f'--> resynchronized after {tt} s more'); show('resync')
sim.press('r_ack'); sim.press('r_annrst')
run_until(lambda: False, 60); show('loaded')
# normal stop
print('STOP:', sim.press('r_run'))
tt = run_until(lambda: sim.globals.get('cb') == 0, 120); print(f'--> breaker open after {tt} s'); show('open')
tt = run_until(lambda: sim.counter('n') == 0, 400, 'coast', every=20); print(f'--> standstill after {tt} s more'); show('stopped')
run_until(lambda: False, 10); print('ready', sim.globals.get('ready'), 'brake', sim.globals.get('brake'), 'lift', sim.globals.get('lift'), 'cw', sim.globals.get('cw'))
# E-stop from full load
sim.press('r_run'); run_until(lambda: sim.globals.get('cb') == 1, 120); run_until(lambda: False, 60); show('online2')
pk[0] = 0; print('E-STOP:', sim.press('b_estop'))
sim.run(20, every=track); show('estop')
print(f'--> peak speed {pk[0]*5} %, lock={sim.globals.get("lock")}, START now:', sim.press('r_run'))
run_until(lambda: sim.counter('n') == 0, 400); show('stopped')
print('86 reset:', sim.press('r_86')); sim.run(2); sim.press('r_ack'); sim.press('r_annrst'); sim.run(2)
print('lock', sim.globals.get('lock'), 'ready', sim.globals.get('ready'), 'windows lit', [w for w in dev['walls'] if w.startswith('A') and sim.ent(w).on])
# oil pumps fail while running
sim.run(3); sim.press('r_run'); run_until(lambda: sim.globals.get('cb') == 1, 120); show('online3')
sim.press('r_pfail'); tt = run_until(lambda: sim.globals.get('lock') == 1, 600, 'pfail', every=40)
print(f'--> oil pressure trip after {tt} s'); show('opu trip')
print('multi_manager re-trigger collisions:', sim.mm_ignored)

# ---------------------------------------------------------------- analog knobs
print('\n--- analog knobs ---')
sim.press('r_pfail'); run_until(lambda: sim.counter('n') == 0, 400); sim.press('r_86'); sim.run(1)
sim.press('r_ack'); sim.press('r_annrst'); sim.run(1)
sim.press('r_run'); run_until(lambda: sim.globals.get('cb') == 1, 120); run_until(lambda: False, 40)
sim.press('r_ctl'); sim.run(1)                       # level control off: the load knob owns the setpoint
k = sim.ent('k_load'); lamp = sim.ent('L_k_load')
s0 = sim.counter('s'); k.hold(1.0); sim.run(0.5); s1 = sim.counter('s')
print(f'load knob turn 1 (1.0 s): s {s0} -> {s1}   next-turn lamp frame {lamp.frame} (1 = LOWER)')
k.hold(1.6); sim.run(0.5); s2 = sim.counter('s')
print(f'load knob turn 2 (1.6 s): s {s1} -> {s2}   lamp frame {lamp.frame}')
k.hold(0.05); sim.run(0.04); k.hold(0.6); sim.run(0.5); s3 = sim.counter('s')
print(f'quick re-grab within 0.1 s keeps direction: s {s2} -> {s3}')
run_until(lambda: False, 20); show('loadset')
print('kW setpoint pointer', round(sim.ent('p_kwsp').pos * 320), 'kW')
# manual gate handwheel
sim.press('r_gov'); sim.run(1)                       # governor to MAN
gw = sim.ent('k_gate'); g0 = sim.counter('g')
gw.hold(1.0); sim.run(0.5); g1 = sim.counter('g'); sim.run(0.3)
gw.hold(1.0); sim.run(0.5); g2 = sim.counter('g')
print(f'gate handwheel in MAN: g {g0} -> {g1} -> {g2}')
sim.press('r_gov'); sim.run(1)
# river knob: absolute, drives the flood meter directly and resyncs at its top stop
rk = sim.ent('k_river'); el0 = sim.counter('el')
flood = [e for e in sim.byname['k_river_ev'] if e.cls == 'momentary_door'][0]
rk.hold(3.5); sim.run(0.5)
print(f'river knob to top: r={sim.counter("r")} el {el0} -> {sim.counter("el")}  flood pointer {flood.pos:.2f}  dir flag {sim.globals.get("k_river_u")}')
rk.hold(1.5); sim.run(0.5)
print(f'river knob back half way: r={sim.counter("r")}  flood pointer {flood.pos:.2f}')
print('multi_manager re-trigger collisions:', sim.mm_ignored)

# ------------------------------------------------------------ control switches
print('\n--- breaker control switches ---')
H = lambda: f"52G handle={sim.ent('r_52').pos} h52={sim.globals.get('h52')} cb={sim.globals.get('cb')} | " \
            f"EXC handle={sim.ent('r_exc').pos} exc={sim.globals.get('exc')} | RUN handle={sim.ent('r_run').pos} run={sim.globals.get('run')}"
print('before restart:            ', H(), ' lock', sim.globals.get('lock'), 'ctl', sim.globals.get('ctl'))
sim.press('r_ctl'); sim.run(1)                               # level control back on
run_until(lambda: sim.counter('n') == 0 and sim.globals.get('ready') == 1, 400)
sim.press('r_run'); sim.run(1); print('RUN turned to START:       ', H())
run_until(lambda: sim.globals.get('cb') == 1, 120); sim.run(2)
print('online, after auto-sync:   ', H())
sim.press('r_52'); sim.run(2); print('52G turned to TRIP:        ', H())
sim.press('r_sync'); sim.run(1)                              # synchronizer to MAN
sim.press('r_52'); sim.run(2); print('52G turned to CLOSE (MAN): ', H())
sim.press('r_exc'); sim.run(2); print('EXC OFF while on line:     ', H())
sim.press('r_52'); sim.run(2); sim.press('r_exc'); sim.run(2); print('52G TRIP, then EXC OFF:    ', H())
sim.press('r_52'); sim.run(0.45); p_mid = sim.ent('r_52').pos; sim.run(1.5)
print(f'52G CLOSE with no voltage:  handle reached {p_mid}, then ', H())
sim.press('r_exc'); run_until(lambda: sim.counter('v') >= 20, 30); sim.run(1); sim.press('r_sync'); sim.run(1)
run_until(lambda: sim.globals.get('cb') == 1, 30); sim.run(1); print('EXC ON, sync AUTO:         ', H())
sim.press('b_estop'); sim.run(3); print('E-STOP:                    ', H(), ' lock', sim.globals.get('lock'))
run_until(lambda: sim.counter('n') == 0, 400); sim.press('r_86'); sim.run(1); sim.press('r_ack'); sim.press('r_annrst'); sim.run(2)
print('86 reset at standstill:    lock', sim.globals.get('lock'), 'ready', sim.globals.get('ready'), '|', H())
sim.press('r_run'); run_until(lambda: sim.globals.get('cb') == 1, 120); sim.run(5)
pts = lambda: ' '.join(f"{p}={sim.ent(p).pos:.2f}" for p in ('p_exc', 'p_cw', 'p_lift'))
print('online again:              ', H(), '|', pts())
sim.press('r_run'); sim.run(1); print('RUN turned to STOP:        ', H())
run_until(lambda: sim.counter('n') == 0, 600); sim.run(5); print('stopped:                   ', H(), '|', pts())
print('multi_manager re-trigger collisions:', sim.mm_ignored)
