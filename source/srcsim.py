"""
Simulator for the Source entities the map uses, written from the Source SDK 2013 server code
(cbase.cpp CEventQueue / CBaseEntityOutput, logicentities.cpp, logicrelay.cpp, buttons.cpp,
modelentities.cpp, sound.cpp):

  * outputs post events to one queue sorted by fire time; events with the same time run first in,
    first out, and an output's actions are posted in reverse order of the keyvalues (AddEventAction
    puts each new action at the head of the list);
  * every server tick (15 ms) entities think first, then the queue is serviced until nothing is due,
    including the events posted while servicing it;
  * think times are rounded to the nearest tick (TIME_TO_TICKS);
  * values are 32-bit floats.
"""
import math, struct

TICK = 0.015


def f32(x):
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def tticks(t):
    return int(0.5 + t / TICK)


class SimEnt:
    def __init__(self, sim, e):
        self.sim, self.e = sim, e
        self.cls, self.kv, self.name = e.cls, e.kv, e.name
        self.outputs = {}
        for out, tgt, inp, par, delay, times in e.outputs:
            self.outputs.setdefault(out.lower(), []).insert(0, (tgt, inp, par, delay))   # reverse order
        self.next_think = None
        self.think = None
        self.inputs_log = []

    def k(self, key, default=0.0):
        v = self.kv.get(key, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def fire(self, output, value=None, activator=None):
        for tgt, inp, par, delay in self.outputs.get(output.lower(), []):
            v = value if par == '' else par
            self.sim.post(tgt, inp, v, delay, activator, self)

    def accept(self, inp, value, activator, caller):
        fn = getattr(self, 'in_' + inp.lower(), None)
        self.inputs_log.append((self.sim.tick, inp, value))
        if fn is None:
            return
        fn(value)

    def spawn(self):
        pass


def fv(v):
    """variant -> float (strings are converted with atof)"""
    if v is None:
        return 0.0
    if isinstance(v, str):
        try:
            return f32(float(v.split()[0]) if v.strip() else 0.0)
        except ValueError:
            return 0.0
    return f32(v)


# ------------------------------------------------------------------ logic
class MathCounter(SimEnt):
    def spawn(self):
        self.min, self.max = f32(self.k('min')), f32(self.k('max'))
        if self.min > self.max:
            self.min, self.max = self.max, self.min
        self.value = f32(int(float(self.kv.get('startvalue', 0))))
        if self.min or self.max:
            self.value = min(max(self.value, self.min), self.max)
        self.hitmax = self.hitmin = False
        self.disabled = bool(int(self.k('StartDisabled')))

    def update(self, nv, activator=None):
        nv = f32(nv)
        if self.min or self.max:
            if nv >= self.max:
                if not self.hitmax:
                    self.hitmax = True
                    self.fire('OnHitMax', None, activator)
            else:
                self.hitmax = False
            if nv <= self.min:
                if not self.hitmin:
                    self.hitmin = True
                    self.fire('OnHitMin', None, activator)
            else:
                self.hitmin = False
            nv = min(max(nv, self.min), self.max)
        self.value = nv
        self.fire('OutValue', nv, activator)

    def in_add(self, v):
        if not self.disabled: self.update(self.value + fv(v))

    def in_subtract(self, v):
        if not self.disabled: self.update(self.value - fv(v))

    def in_multiply(self, v):
        if not self.disabled: self.update(self.value * fv(v))

    def in_divide(self, v):
        if self.disabled: return
        d = fv(v)
        self.update(self.value / d if d != 0 else self.value)

    def in_setvalue(self, v):
        if not self.disabled: self.update(fv(v))

    def in_setvaluenofire(self, v):
        if self.disabled: return
        nv = fv(v)
        if self.min or self.max:
            nv = min(max(nv, self.min), self.max)
        self.value = nv

    def in_getvalue(self, v):
        self.fire('OnGetValue', self.value)

    def in_sethitmax(self, v):
        self.max = fv(v)
        if self.max < self.min: self.min = self.max
        self.update(self.value)

    def in_sethitmin(self, v):
        self.min = fv(v)
        if self.max < self.min: self.max = self.min
        self.update(self.value)

    def in_enable(self, v): self.disabled = False
    def in_disable(self, v): self.disabled = True


class MathRemap(SimEnt):
    def spawn(self):
        self.i1, self.i2, self.o1, self.o2 = (f32(self.k(k)) for k in ('in1', 'in2', 'out1', 'out2'))
        if self.i1 == self.i2:
            self.i1, self.i2 = 0.0, 1.0
        if self.i1 > self.i2:                     # the SDK swaps the inputs but not the outputs
            self.i1, self.i2 = self.i2, self.i1
        self.flags = int(self.k('spawnflags'))
        self.disabled = bool(int(self.k('StartDisabled')))
        self.last = None

    def in_invalue(self, v):
        if self.disabled: return
        x = fv(v)
        cx = min(max(x, self.i1), self.i2)
        if cx == x or not (self.flags & 1):
            y = f32(self.o1 + ((x - self.i1) * (self.o2 - self.o1)) / (self.i2 - self.i1))
            if self.flags & 2:
                y = min(max(y, self.o1), self.o2)      # (with out1 > out2 this gives out2: never used)
            self.last = y
            self.fire('OutValue', y)

    def in_enable(self, v): self.disabled = False
    def in_disable(self, v): self.disabled = True


class LogicRelay(SimEnt):
    def spawn(self):
        self.disabled = bool(int(self.k('StartDisabled')))
        self.wait = False
        self.flags = int(self.k('spawnflags'))

    def in_trigger(self, v):
        if self.disabled or self.wait: return
        self.fire('OnTrigger')
        if not (self.flags & 2):
            self.wait = True
            md = max([d for _, _, _, d in self.outputs.get('ontrigger', [])] + [0])
            self.sim.post(self, 'EnableRefire', None, md + 0.001)

    def in_enablerefire(self, v): self.wait = False
    def in_enable(self, v): self.disabled = False
    def in_disable(self, v): self.disabled = True
    def in_toggle(self, v): self.disabled = not self.disabled


class LogicTimer(SimEnt):
    def spawn(self):
        self.refire = max(self.k('RefireTime'), 0.01)
        self.disabled = True
        if not int(self.k('StartDisabled')):
            self.enable()

    def enable(self):
        self.disabled = False
        self.next_think = tticks(self.sim.curtime + self.refire)
        self.think = self.fire_timer

    def fire_timer(self):
        if not self.disabled:
            self.fire('OnTimer')
            self.enable()

    def in_enable(self, v): self.enable()

    def in_disable(self, v):
        self.disabled = True
        self.next_think = None

    def in_toggle(self, v):
        self.in_disable(v) if not self.disabled else self.enable()

    def in_firetimer(self, v): self.fire_timer()

    def in_refiretime(self, v):
        self.refire = fv(v)
        if not self.disabled: self.enable()


class LogicAuto(SimEnt):
    def spawn(self):
        self.next_think = tticks(self.sim.curtime + 0.2)
        self.think = lambda: self.fire('OnMapSpawn')


# ------------------------------------------------------------------ brush entities
class FuncBrush(SimEnt):
    def spawn(self):
        self.on = not int(self.k('StartDisabled'))

    def in_enable(self, v): self.on = True
    def in_disable(self, v): self.on = False
    def in_toggle(self, v): self.on = not self.on


class Mover(SimEnt):
    """MOVETYPE_PUSH along one rotation axis, in degrees; the move-done callback runs on the first tick
    at or after its time."""
    def spawn(self):
        self.ang = 0.0
        self.avel = 0.0
        self.movedone = None
        self.movedone_at = None

    def physics(self):
        if self.avel:
            self.ang += self.avel * TICK
        if self.movedone and self.movedone_at is not None and self.sim.curtime >= self.movedone_at - 1e-9:
            fn, self.movedone = self.movedone, None
            self.movedone_at = None
            fn()

    def set_movedone(self, fn, dt):
        self.movedone, self.movedone_at = fn, self.sim.curtime + dt


class FuncRotButton(Mover):
    BOTTOM, UP, TOP, DOWN = range(4)

    def spawn(self):
        super().spawn()
        self.dist = self.k('distance', 90)
        self.speed = self.k('speed') or 40
        self.flags = int(self.k('spawnflags'))
        self.state = self.BOTTOM
        self.locked = bool(self.flags & 2048)
        self.wait = self.k('wait') or 1

    def angular_move(self, dest, done):
        delta = dest - self.ang
        if delta == 0:
            done(); return
        t = abs(delta) / self.speed
        self.avel = delta / t
        self.dest = dest

        def fin():
            self.ang, self.avel = dest, 0.0
            done()
        self.set_movedone(fin, t)

    def activate(self):
        self.state = self.UP
        self.angular_move(self.dist, self.at_top)

    def at_top(self):
        self.state = self.TOP
        if not (self.flags & 32) and self.wait != -1:
            self.next_think = tticks(self.sim.curtime + self.wait)
            self.think = self.ret
        self.fire('OnIn')

    def ret(self):
        self.state = self.DOWN
        self.angular_move(0.0, self.at_bottom)

    def at_bottom(self):
        self.state = self.BOTTOM
        self.fire('OnOut')

    def use(self):
        if self.state in (self.UP, self.DOWN):
            return
        if self.locked:
            self.fire('OnUseLocked'); return
        if self.state == self.TOP:
            if self.flags & 32:
                self.fire('OnPressed'); self.ret()
        else:
            self.fire('OnPressed'); self.activate()

    def press(self, code):
        moving = self.state in (self.UP, self.DOWN)
        if code == 'press' and moving: return
        if code == 'in' and self.state in (self.UP, self.TOP): return
        if code == 'out' and self.state in (self.DOWN, self.BOTTOM): return
        if self.locked: return
        if (code == 'press' and self.state == self.TOP) or (code == 'out' and self.state in (self.TOP, self.UP)):
            self.fire('OnPressed'); self.ret()
        elif code == 'press' or (code == 'in' and self.state in (self.BOTTOM, self.DOWN)):
            self.fire('OnPressed'); self.activate()

    def in_press(self, v): self.press('press')
    def in_pressin(self, v): self.press('in')
    def in_pressout(self, v): self.press('out')
    def in_lock(self, v): self.locked = True
    def in_unlock(self, v): self.locked = False


class FuncButton(FuncRotButton):
    pass


class MomentaryRotButton(Mover):
    def spawn(self):
        super().spawn()
        self.dist = abs(self.k('distance', 90)) or 90
        self.speed = self.k('speed') or 100
        self.retspeed = self.k('returnspeed')
        self.flags = int(self.k('spawnflags'))
        sp = self.k('startposition')
        self.ang = sp * self.dist                     # degrees from the start
        self.direction = -1 if sp == 0 else (1 if sp == 1 else 1)
        self.ideal = sp
        self.position = 0.0                           # m_Position (the output's last value)
        self.last_used = 0
        self.locked = bool(self.flags & 2048)
        self.disabled = False
        self.update_target = True

    def pos(self):
        return min(max(self.ang / self.dist, 0.0), 1.0)

    def target(self, value):
        if self.update_target and self.position != value:
            self.position = value
            self.fire('Position', value)

    def update_think(self):
        self.target(f32(self.pos()))
        self.next_think = self.sim.tick + 1
        self.think = self.update_think

    def use(self):
        if self.disabled or self.locked:
            return
        if not self.last_used:
            self.direction = -self.direction
            self.fire('OnPressed')
        self.last_used = 1
        self.update_self(self.pos())
        if self.think is None:
            self.think, self.next_think = self.update_think, self.sim.tick

    def update_self(self, value):
        self.set_movedone(self.use_move_done, 0.1)
        if self.direction > 0 and value >= 1.0:
            self.avel = 0.0; self.ang = self.dist; self.fire('OnFullyClosed'); return
        if self.direction < 0 and value <= 0:
            self.avel = 0.0; self.ang = 0.0; self.fire('OnFullyOpen'); return
        self.avel = self.direction * self.speed

    def use_move_done(self):
        self.avel = 0.0
        self.target(f32(self.pos()))
        self.fire('OnUnpressed')
        self.last_used = 0
        if not (self.flags & 32) and self.retspeed > 0:
            self.direction = -1
            self.set_movedone(self.return_move_done, 0.1)
        else:
            self.think = None; self.next_think = None

    def return_move_done(self):
        if self.pos() <= 0:
            self.avel = 0.0; self.ang = 0.0
            self.target(0.0)
            self.think = None; self.next_think = None
        else:
            self.avel = -self.retspeed
            self.set_movedone(self.return_move_done, 0.1)
            self.think, self.next_think = self.update_think, tticks(self.sim.curtime + 0.01)

    def in_setposition(self, v):
        self.ideal = min(max(fv(v), 0.0), 1.0)
        cur = self.pos()
        if cur < self.ideal:
            self.avel, self.direction = self.speed, 1
        elif cur > self.ideal:
            self.avel, self.direction = -self.speed, -1
        else:
            self.avel = 0.0; return
        self.think, self.next_think = self.update_think, self.sim.tick
        self.schedule_setpos()

    def schedule_setpos(self):
        delta = abs(self.ideal * self.dist - self.ang)
        dt = delta / self.speed
        if dt < TICK:
            dt = TICK
            self.avel = self.direction * delta / TICK
        dt = min(max(dt, TICK), TICK * 6)
        self.set_movedone(self.setpos_done, dt)

    def setpos_done(self):
        cur = self.pos()
        if (cur >= self.ideal and self.direction == 1) or (cur <= self.ideal and self.direction == -1):
            self.avel = 0.0
            self.ang = self.ideal * self.dist
            self.think = None; self.next_think = None
            self.target(self.ideal)
            self.fire('OnReachedPosition')
            return
        self.schedule_setpos()

    def in_setpositionimmediately(self, v):
        self.ideal = min(max(fv(v), 0.0), 1.0)
        self.ang = self.ideal * self.dist

    def in_lock(self, v): self.locked = True
    def in_unlock(self, v): self.locked = False
    def in_enable(self, v): self.disabled = False
    def in_disable(self, v): self.disabled = True


class AmbientGeneric(SimEnt):
    def spawn(self):
        self.playing = not (int(self.k('spawnflags')) & 16)
        self.pitch = self.k('pitch', 100)
        self.vol = self.k('health', 10)
        self.plays = 0

    def in_playsound(self, v):
        self.playing = True; self.plays += 1

    def in_stopsound(self, v): self.playing = False

    def in_togglesound(self, v):
        self.playing = not self.playing
        if self.playing: self.plays += 1

    def in_pitch(self, v): self.pitch = min(max(int(fv(v)), 0), 255)
    def in_volume(self, v): self.vol = fv(v)


CLASSES = {'math_counter': MathCounter, 'math_remap': MathRemap, 'logic_relay': LogicRelay,
           'logic_timer': LogicTimer, 'logic_auto': LogicAuto, 'func_brush': FuncBrush,
           'func_rot_button': FuncRotButton, 'func_button': FuncButton,
           'momentary_rot_button': MomentaryRotButton, 'ambient_generic': AmbientGeneric}


# ------------------------------------------------------------------ the simulator
class Sim:
    def __init__(self, ents, check=None):
        self.tick = 0
        self.curtime = 0.0
        self.queue = []          # [fire time, seq, target, input, value, activator, caller]
        self.seq = 0
        self.ents = [CLASSES.get(e.cls, SimEnt)(self, e) for e in ents]
        self.by_name = {}
        for s in self.ents:
            if s.name:
                self.by_name.setdefault(s.name.lower(), []).append(s)
        self.holding = set()
        self.check = check or {}          # node name -> op input: the two-input nodes to verify
        self.frame_log = {}
        self.errors = []
        for s in self.ents:
            s.spawn()

    def __getitem__(self, name):
        return self.by_name[name.lower()][0]

    def post(self, target, inp, value, delay, activator=None, caller=None):
        t = self.curtime + delay
        self.seq += 1
        ev = [t, self.seq, target, inp, value, activator, caller]
        i = len(self.queue)
        while i > 0 and self.queue[i - 1][0] > t:
            i -= 1
        self.queue.insert(i, ev)

    def service(self):
        while self.queue and self.queue[0][0] <= self.curtime + 1e-9:
            t, _, target, inp, value, act, caller = self.queue.pop(0)
            targets = [target] if isinstance(target, SimEnt) else self.by_name.get(str(target).lower(), [])
            for e in targets:
                if e.name in self.check:
                    self.frame_log.setdefault(e.name, []).append(inp)
                e.accept(inp, value, act, caller)

    def frame(self):
        self.tick += 1
        self.curtime = self.tick * TICK
        for name in list(self.holding):
            self.by_name[name.lower()][0].use()
        for e in self.ents:
            if e.think and e.next_think is not None and e.next_think <= self.tick:
                fn = e.think
                e.think = None if fn != getattr(e, 'think', None) else e.think
                e.next_think = None
                fn()
            if isinstance(e, Mover):
                e.physics()
        self.frame_log = {}
        self.service()
        for name, log in self.frame_log.items():
            op = self.check[name]
            if op in log:
                ok = log.count(op) == 1 and 'SetValueNoFire' in log and log.index('SetValueNoFire') < log.index(op)
                if not ok:
                    self.errors.append((self.tick, name, log))

    def run(self, seconds):
        for _ in range(int(round(seconds / TICK))):
            self.frame()

    # player
    def use(self, name):
        self[name].use()

    def hold(self, name, seconds):
        self.holding.add(name)
        self.run(seconds)
        self.holding.discard(name)

    def value(self, name):
        return self[name].value
