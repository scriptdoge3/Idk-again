"""
Entity logic for plain Half-Life: variables, flags and rules built only from
stock hl.dll entities, plus a simulator that mirrors their SDK behaviour so the
logic can be tested without the game.

  integer variable  -> one game_counter per value of interest, all sharing a
                       targetname; +1/-1 arrive as USE_ON / USE_OFF from
                       trigger_relays, and each counter fires "<var>_eq<v>"
                       when the value lands on v.
  boolean flag      -> env_global state (and its negation "n<flag>"), read by
                       multisource masters through their globalstate key.
  condition / rule  -> chains of game_counter_set entities, each locked by a
                       master; a clock fires the chain heads.
  display           -> game_counter_set sends USE_SET <fraction> to a
                       momentary_door pointer (or the pitch of an
                       ambient_generic).
"""
import heapq
from collections import defaultdict

USE_OFF, USE_ON, USE_SET, USE_TOGGLE = 0, 1, 2, 3


def fmt(v):
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, float):
        s = f'{v:.6f}'.rstrip('0').rstrip('.')
        return s if s not in ('', '-0') else '0'
    return str(v)


def vname(name, v):
    return f'{name}_eq{v}' if v >= 0 else f'{name}_eqm{-v}'


class Logic:
    """Collects entities in a deliberate order (edict order = firing order).

    Built twice: the first pass records which flag polarities are read by
    rules, the second pass emits only those env_global / multisource pairs.
    Rules with a common head and common leading conditions share gates (a trie).
    """

    def __init__(self, used=None):
        self.ents = []
        self.flags = {}
        self.vars = {}
        self._fan = defaultdict(list)
        self.used = used            # set of 'x' / '!x' read somewhere, or None in pass 1
        self.reads = set()
        self.rules = []             # (head, conds, action, value, seq)
        self.setters = []           # (event, flag, val)
        self.followers = []         # (flag, target, on_when)
        self.rank = {}

    # ------------------------------------------------------------- basics
    def add(self, cls, keys=None, **kv):
        e = {'classname': cls}
        for k, v in kv.items():
            e[k.rstrip('_')] = fmt(v)
        if keys:
            for k, v in keys.items():
                e[k] = fmt(v)
        self.ents.append(e)
        return e

    def relay(self, name, target, state=USE_ON):
        st = {USE_OFF: 0, USE_ON: 1, USE_TOGGLE: 2}[state]
        return self.add('trigger_relay', targetname=name, target=target, triggerstate=st)

    # ------------------------------------------------------------- flags
    def flag(self, name, init):
        self.flags[name] = init

    def needs(self, pol):
        return self.used is None or pol in self.used

    def setf(self, event, name, val):
        """When `event` fires, flag := val. env_globals are placed on the event itself."""
        self.setters.append((event, name, val))
        for g, gv in ((name, val), (f'n{name}', 1 - val)):
            pol = name if g == name else f'!{name}'
            if not self.needs(pol):
                continue
            kv = dict(targetname=event, globalstate=g, triggermode=gv)
            if not any(e.get('globalstate') == g and e.get('spawnflags') == '1' for e in self.ents):
                init = self.flags[name] if g == name else 1 - self.flags[name]
                kv.update(spawnflags=1, initialstate=init)
            self.add('env_global', **kv)

    def toggle_flag(self, event, name):
        for g, pol in ((name, name), (f'n{name}', f'!{name}')):
            if not self.needs(pol):
                continue
            kv = dict(targetname=event, globalstate=g, triggermode=3)
            if not any(e.get('globalstate') == g and e.get('spawnflags') == '1' for e in self.ents):
                init = self.flags[name] if g == name else 1 - self.flags[name]
                kv.update(spawnflags=1, initialstate=init)
            self.add('env_global', **kv)

    def follow(self, name, target, on_when):
        """target (lamp, device) gets USE_ON when flag == on_when, USE_OFF otherwise."""
        self.followers.append((name, target, on_when))

    def cond(self, c):
        return f'ms_n{c[1:]}' if c.startswith('!') else f'ms_{c}'

    # --------------------------------------------------------- variables
    def var(self, name, lo, hi, init, values=None):
        vals = values if values is not None else range(lo, hi + 1)
        self.vars[name] = {'lo': lo, 'hi': hi, 'init': init, 'vals': list(vals)}
        for v in vals:
            self.add('game_counter', targetname=f'{name}_c', frags=init, health=v, target=vname(name, v))

    def fan(self, fan_name, ent):
        self._fan[fan_name].append(ent)

    def inc_listener(self, var, direction, target, state):
        e = {'classname': 'trigger_relay', 'target': target, 'triggerstate': fmt({USE_OFF: 0, USE_ON: 1, USE_TOGGLE: 2}[state])}
        self.fan(f'{var}_{direction}', e)

    def dir_flag(self, var, flag_up):
        for d, val in (('up', 1), ('dn', 0)):
            for g, gv, pol in ((flag_up, val, flag_up), (f'n{flag_up}', 1 - val, f'!{flag_up}')):
                if self.needs(pol):
                    self.fan(f'{var}_{d}', {'classname': 'env_global', 'globalstate': g, 'triggermode': str(gv)})

    # -------------------------------------------------------- conditions
    def rule(self, head, conds, action, value=0):
        for c in conds:
            self.reads.add(c)
        self.rules.append((head, list(conds), action, value, len(self.rules)))

    gate_chain = rule

    def display(self, event, target, frac, conds=()):
        self.rule(event, list(conds), target, max(0.0, min(1.0, frac)))

    # ------------------------------------------------------------ output
    def finalize(self):
        # followers: a relay on every event that sets the flag
        for (event, name, val) in self.setters:
            for (fname, target, on_when) in self.followers:
                if fname == name:
                    self.relay(event, target, USE_ON if val == on_when else USE_OFF)
        # every global that is read needs an initial state, even if nothing ever sets it
        for c in sorted(self.reads):
            base = c.lstrip('!')
            g = f'n{base}' if c.startswith('!') else base
            if not any(e.get('globalstate') == g and e.get('spawnflags') == '1' for e in self.ents):
                init = self.flags[base] if g == base else 1 - self.flags[base]
                self.add('env_global', targetname='never', globalstate=g, triggermode=init, spawnflags=1, initialstate=init)
        # multisources for every polarity that is read
        for c in sorted(self.reads):
            base = c.lstrip('!')
            g = f'n{base}' if c.startswith('!') else base
            self.add('multisource', targetname=self.cond(c), globalstate=g)
        # rule trie per head; conditions ordered by how often they occur, for sharing
        freq = defaultdict(int)
        for r in self.rules:
            for c in r[1]:
                freq[c] += 1
        order = lambda c: (-freq[c], c)
        trie = {}
        for head, conds, action, value, seq in self.rules:
            node = trie.setdefault(head, {'kids': {}, 'leaves': []})
            cs = sorted(conds, key=order)
            for c in cs[:-1]:
                node = node['kids'].setdefault(c, {'kids': {}, 'leaves': []})
            node['leaves'].append((cs[-1] if cs else None, action, value))
        uid = [0]

        def emit(name, node):
            for c, kid in node['kids'].items():
                uid[0] += 1
                out = f'q{uid[0]}'
                self.add('game_counter_set', targetname=name, master=self.cond(c), target=out, frags=0)
                emit(out, kid)
            for c, action, value in node['leaves']:
                kv = dict(targetname=name, target=action, frags=value)
                if c:
                    kv['master'] = self.cond(c)
                self.add('game_counter_set', **kv)
        for head, node in trie.items():
            emit(head, node)
        # variable fan-outs: direction globals, listeners, then the counters
        for name in self.vars:
            for d, st in (('up', USE_ON), ('dn', USE_OFF)):
                fan = f'{name}_{d}'
                for ent in sorted(self._fan.get(fan, []), key=lambda e: 0 if e['classname'] == 'env_global' else 1):
                    ent = dict(ent); ent['targetname'] = fan
                    self.ents.append(ent)
                self.relay(fan, f'{name}_c', st)
        return self.ents


# =========================================================================
#  SIMULATOR — mirrors hl.dll behaviour for the classes used above
# =========================================================================
class SimEnt:
    def __init__(self, sim, kv):
        self.sim, self.kv = sim, kv
        self.cls = kv['classname']
        self.name = kv.get('targetname')
        self.target = kv.get('target')

    def f(self, k, d=0.0):
        return float(self.kv.get(k, d))

    def master_ok(self):
        m = self.kv.get('master')
        return True if not m else self.sim.master(m)

    def use(self, act, caller, ut, value):
        pass


class Relay(SimEnt):
    def use(self, act, caller, ut, value):
        st = int(self.kv.get('triggerstate', 1))
        t = {0: USE_OFF, 2: USE_TOGGLE}.get(st, USE_ON)
        self.sim.fire(self.target, act, self, t, 0)


class Counter(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        self.frags = int(self.f('frags')); self.init = self.frags; self.limit = int(self.f('health'))
        self.sf = int(self.f('spawnflags'))

    def use(self, act, caller, ut, value):
        if not self.master_ok():
            return
        if ut in (USE_ON, USE_TOGGLE):
            self.frags += 1
        elif ut == USE_OFF:
            self.frags -= 1
        elif ut == USE_SET:
            self.frags = int(value)
        if self.frags == self.limit:
            self.sim.fire(self.target, act, self, USE_TOGGLE, 0)
            if self.sf & 2:
                self.frags = self.init


class CounterSet(SimEnt):
    def use(self, act, caller, ut, value):
        if not self.master_ok():
            return
        self.sim.fire(self.target, act, self, USE_SET, self.f('frags'))


class EnvGlobal(SimEnt):
    def use(self, act, caller, ut, value):
        g = self.kv['globalstate']; mode = int(self.kv.get('triggermode', 3))
        old = self.sim.globals.get(g, 0)
        new = {0: 0, 1: 1, 2: 2}.get(mode, 0 if old == 1 else 1 if old == 0 else old)
        self.sim.globals[g] = new


class Multisource(SimEnt):
    def triggered(self):
        if self.sim.time < 0.1:
            return False
        g = self.kv.get('globalstate')
        return (not g) or self.sim.globals.get(g, 0) == 1


class MultiManager(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        skip = {'classname', 'targetname', 'origin', 'spawnflags'}
        self.targets = sorted(((float(v), k.split('#')[0]) for k, v in kv.items() if k not in skip), key=lambda x: x[0])
        assert len(self.targets) <= 16, f'multi_manager {self.name} has {len(self.targets)} targets'
        self.busy = False

    def use(self, act, caller, ut, value):
        if self.busy:
            self.sim.mm_ignored += 1
            return
        self.busy = True
        t0 = self.sim.time
        for i, (d, tname) in enumerate(self.targets):
            last = i == len(self.targets) - 1
            self.sim.later(t0 + max(d, 0.001), self._fire(tname, act, last))

    def _fire(self, tname, act, last):
        def f():
            if last:
                self.busy = False
            self.sim.fire(tname, act, self, USE_TOGGLE, 0)
        return f


def should_toggle(ut, state):
    if ut not in (USE_TOGGLE, USE_SET):
        if (state and ut == USE_ON) or (not state and ut == USE_OFF):
            return False
    return True


class WallToggle(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        self.on = not (int(self.f('spawnflags')) & 1)

    def use(self, act, caller, ut, value):
        if should_toggle(ut, self.on):
            self.on = not self.on


class Wall(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        self.frame = 0

    def use(self, act, caller, ut, value):
        if should_toggle(ut, self.frame):
            self.frame = 1 - self.frame
    @property
    def on(self):
        return self.frame == 1


class MomentaryDoor(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        self.pos = 0.0

    def use(self, act, caller, ut, value):
        if ut != USE_SET:
            return
        self.pos = min(value, 1.0)


class Ambient(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        sf = int(self.f('spawnflags'))
        self.loop = not (sf & 32)
        self.active = self.loop and not (sf & 16)
        self.pitch = self.f('pitch', 100)
        self.plays = 0

    def use(self, act, caller, ut, value):
        if ut != USE_TOGGLE:
            if (self.active and ut == USE_ON) or (not self.active and ut == USE_OFF):
                return
        if ut == USE_SET and self.active:
            self.pitch = max(0.01, min(1.0, value)) * 255
            return
        if self.loop:
            self.active = not self.active
        else:
            self.plays += 1


class Button(SimEnt):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        self.ready_at = 0
        self.presses = 0
        self.locked = 0

    def press(self):
        if self.sim.time < self.ready_at:
            return 'busy'
        if not self.master_ok():
            self.locked += 1
            return 'locked'
        self.presses += 1
        wait = self.f('wait', 1)
        self.ready_at = self.sim.time + 0.2 + max(wait, 0)
        self.sim.later(self.sim.time + 0.1, lambda: self.sim.fire(self.target, None, self, USE_TOGGLE, 0))
        return 'ok'


class RotButton(Button):
    def __init__(self, sim, kv):
        super().__init__(sim, kv)
        self.pos = 0

    def press(self):
        r = super().press()
        if r == 'ok':
            self.pos = 1 - self.pos
        return r


class Auto(SimEnt):
    pass


CLASSES = {'trigger_relay': Relay, 'game_counter': Counter, 'game_counter_set': CounterSet, 'env_global': EnvGlobal,
           'multisource': Multisource, 'multi_manager': MultiManager, 'func_wall_toggle': WallToggle, 'func_wall': Wall,
           'momentary_door': MomentaryDoor, 'ambient_generic': Ambient, 'func_button': Button, 'func_rot_button': RotButton,
           'trigger_auto': Auto}


class Sim:
    def __init__(self, ents):
        self.time = 0.0
        self.globals = {}
        self.q = []
        self.seq = 0
        self.depth = 0
        self.mm_ignored = 0
        self.fired = defaultdict(int)
        self.ents = []
        self.byname = defaultdict(list)
        for kv in ents:
            cls = CLASSES.get(kv['classname'])
            if not cls:
                continue
            e = cls(self, kv)
            self.ents.append(e)
            if e.name:
                self.byname[e.name].append(e)
        for e in self.ents:                       # env_global "Set Initial State" at spawn
            if isinstance(e, EnvGlobal) and int(e.f('spawnflags')) & 1:
                self.globals.setdefault(e.kv['globalstate'], int(e.f('initialstate')))
        for e in self.ents:
            if isinstance(e, Auto):
                st = int(e.kv.get('triggerstate', 1))
                t = {0: USE_OFF, 2: USE_TOGGLE}.get(st, USE_ON)
                self.later(e.f('delay', 0.2) + 0.2, (lambda e=e, t=t: self.fire(e.target, None, e, t, 0)))

    def master(self, name):
        ms = self.byname.get(name)
        if not ms:
            return True
        return ms[0].triggered() if isinstance(ms[0], Multisource) else True

    def later(self, t, fn):
        self.seq += 1
        heapq.heappush(self.q, (t, self.seq, fn))

    def fire(self, name, act, caller, ut, value):
        if not name:
            return
        self.fired[name] += 1
        self.depth += 1
        assert self.depth < 400, f'runaway recursion at {name}'
        for e in list(self.byname.get(name, [])):
            e.use(act, caller, ut, value)
        self.depth -= 1

    def run(self, seconds, dt=0.01, every=None):
        end = self.time + seconds
        while self.time < end - 1e-9:
            self.time = round(self.time + dt, 6)
            while self.q and self.q[0][0] <= self.time + 1e-9:
                _, _, fn = heapq.heappop(self.q)
                fn()
            if every:
                every(self)

    def ent(self, name):
        return self.byname[name][0]

    def press(self, name):
        r = self.ent(name).press()
        return r

    def counter(self, var):
        return self.byname[f'{var}_c'][0].frags
