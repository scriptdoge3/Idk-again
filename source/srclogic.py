"""
Plant logic for Source as server-only logic entities (they take no network slots).

The plant is one program that a logic_timer runs every DT seconds. Each state variable is a math_counter.
At the start of a tick the timer's relay asks every variable it reads for its value (GetValue); the
values flow through math_remap nodes (functions of one value: scale, offset, clamp) and math_counter
nodes (two values: + - * /) to the variables' new values and to the needles, lamps and sounds.

Source runs the outputs of one tick as a first-in first-out queue (CEventQueue::ServiceEvents), so an
event's level (how many hops it is from the timer) decides when it runs. A two-input node takes its
first value silently (SetValueNoFire) and computes when the second one arrives (Add, Multiply, ...),
so the compiler makes sure the second always comes at a later level, delaying it through identity
remaps where it must. The simulator (srcsim.py) checks that on every tick.
"""
import math

DT = 0.06          # tick program period: 4 server ticks of 15 ms (think times round to whole ticks)
BIG = 1.0e4


# ======================================================================= entities
class Ent:
    def __init__(self, cls, name=None, **kv):
        self.cls = cls
        self.kv = {}
        if name:
            self.kv['targetname'] = name
        self.kv.update({k: v for k, v in kv.items() if v is not None})
        self.outputs = []          # (output, target, input, param, delay, times)
        self.brushes = []          # filled in by the map builder

    @property
    def name(self):
        return self.kv.get('targetname')

    def out(self, output, target, inp, param=None, delay=0.0, times=-1):
        tname = target.name if isinstance(target, Ent) else target
        self.outputs.append((output, tname, inp, '' if param is None else _num(param), delay, times))
        return self

    def __repr__(self):
        return f'<{self.cls} {self.name}>'


def _num(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, int) or float(v).is_integer():
        return str(int(v))
    return f'{v:.6g}'


class Map:
    def __init__(self):
        self.ents = []
        self.by_name = {}

    def add(self, e):
        if e.name:
            assert e.name not in self.by_name, f'duplicate name {e.name}'
            self.by_name[e.name] = e
        self.ents.append(e)
        return e

    def ent(self, cls, name=None, **kv):
        return self.add(Ent(cls, name, **kv))

    def __getitem__(self, name):
        return self.by_name[name]


# ======================================================================= expressions
class X:
    lo = -math.inf
    hi = math.inf

    def __add__(self, o): return add(self, o)
    def __radd__(self, o): return add(o, self)
    def __sub__(self, o): return sub(self, o)
    def __rsub__(self, o): return sub(o, self)
    def __mul__(self, o): return mul(self, o)
    def __rmul__(self, o): return mul(o, self)
    def __truediv__(self, o): return div(self, o)
    def __rtruediv__(self, o): return div(o, self)
    def __neg__(self): return aff(self, -1, 0)


class Const(X):
    def __init__(self, v):
        self.v = float(v)
        self.lo = self.hi = self.v

    def key(self):
        return ('c', self.v)


class Read(X):
    """A state variable's value at the start of the tick."""
    def __init__(self, var):
        self.var = var
        self.lo, self.hi = var.lo, var.hi

    def key(self):
        return ('r', self.var.name)


class Aff(X):
    """k * x + c, optionally clamped to [clo, chi]: one math_remap."""
    def __init__(self, x, k, c, clo=None, chi=None, gate=None):
        self.x, self.k, self.c, self.clo, self.chi, self.gate = x, float(k), float(c), clo, chi, gate
        a, b = sorted((k * x.lo + c, k * x.hi + c)) if k else (c, c)
        if clo is not None:
            a, b = max(a, clo), max(b, clo)
        if chi is not None:
            a, b = min(a, chi), min(b, chi)
        self.lo, self.hi = a, b

    def key(self):
        return ('a', id(self.x), self.k, self.c, self.clo, self.chi, self.gate)


class Bin(X):
    """a op b: one math_counter, optionally clamped."""
    def __init__(self, op, a, b, clo=None, chi=None):
        self.op, self.a, self.b, self.clo, self.chi = op, a, b, clo, chi
        if op == '+':
            lo, hi = a.lo + b.lo, a.hi + b.hi
        elif op == '-':
            lo, hi = a.lo - b.hi, a.hi - b.lo
        elif op == '*':
            ps = [p for p in (a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi) if not math.isnan(p)]
            lo, hi = min(ps), max(ps)
        else:
            lo, hi = -math.inf, math.inf
        if clo is not None:
            lo, hi = max(lo, clo), max(hi, clo)
        if chi is not None:
            lo, hi = min(lo, chi), min(hi, chi)
        self.lo, self.hi = lo, hi

    def key(self):
        return ('b', self.op, id(self.a), id(self.b), self.clo, self.chi)


_memo = {}
_DIG = '0123456789abcdefghijklmnopqrstuvwxyz'


def _short(k):
    out = ''
    while True:
        out += _DIG[k % 36]
        k //= 36
        if not k:
            return out


def reset():
    _memo.clear()


def _cse(node):
    k = node.key()
    if k not in _memo:
        _memo[k] = node
    return _memo[k]


def C(v):
    return v if isinstance(v, X) else _cse(Const(v))


def aff(x, k, c, clo=None, chi=None):
    x = C(x)
    k, c = float(k), float(c)
    if isinstance(x, Const):
        v = k * x.v + c
        if clo is not None: v = max(v, clo)
        if chi is not None: v = min(v, chi)
        return C(v)
    if isinstance(x, Aff) and x.clo is None and x.chi is None and x.gate is None:
        k, c, x = k * x.k, k * x.c + c, x.x
    if k == 0:
        return C(c if clo is None else max(c, clo) if chi is None else min(max(c, clo), chi))
    # a clamp that can never act is left out
    lo, hi = sorted((k * x.lo + c, k * x.hi + c))
    if clo is not None and lo >= clo: clo = None
    if chi is not None and hi <= chi: chi = None
    if k == 1 and c == 0 and clo is None and chi is None:
        return x
    if k < 0 and (clo is not None or chi is not None):
        # math_remap only clamps rising maps: map first, clamp after
        return _cse(Aff(_cse(Aff(x, k, c)), 1, 0, clo, chi))
    return _cse(Aff(x, k, c, clo, chi))


def add(a, b):
    a, b = C(a), C(b)
    if isinstance(a, Const) and isinstance(b, Const): return C(a.v + b.v)
    if isinstance(b, Const): return aff(a, 1, b.v)
    if isinstance(a, Const): return aff(b, 1, a.v)
    return _cse(Bin('+', a, b))


def sub(a, b):
    a, b = C(a), C(b)
    if isinstance(a, Const) and isinstance(b, Const): return C(a.v - b.v)
    if isinstance(b, Const): return aff(a, 1, -b.v)
    if isinstance(a, Const): return aff(b, -1, a.v)
    return _cse(Bin('-', a, b))


def mul(a, b):
    a, b = C(a), C(b)
    if isinstance(a, Const) and isinstance(b, Const): return C(a.v * b.v)
    if isinstance(b, Const): return aff(a, b.v, 0)
    if isinstance(a, Const): return aff(b, a.v, 0)
    return _cse(Bin('*', a, b))


def div(a, b):
    a, b = C(a), C(b)
    if isinstance(b, Const): return aff(a, 1 / b.v, 0)
    return _cse(Bin('/', a, b))


def clamp(x, lo=None, hi=None):
    x = C(x)
    if isinstance(x, Bin) and x.clo is None and x.chi is None:
        # fold the clamp into the counter if neither value can be clamped on loading
        inside = lambda e: (lo is None or e.lo >= lo - 1e-9) and (hi is None or e.hi <= hi + 1e-9)
        if inside(x.a) and (x.op in '-/' or inside(x.b)):
            return _cse(Bin(x.op, x.a, x.b, lo, hi))
    return aff(x, 1, 0, lo, hi)


def relu(x):
    return clamp(x, 0, None)


def step(x, t, w=1e-3):
    """1 when x >= t, 0 below t - w (linear in between)."""
    return aff(x, 1 / w, -(t - w) / w, 0, 1)


def below(x, t, w=1e-3):
    """1 when x <= t, 0 above t + w."""
    return aff(x, -1 / w, (t + w) / w, 0, 1)


def AND(*xs):
    out = C(xs[0])
    for x in xs[1:]:
        out = mul(out, x)
    return out


def OR(*xs):
    out = C(xs[0])
    for x in xs[1:]:
        out = clamp(add(out, x), 0, 1)
    return out


def NOT(x):
    return aff(x, -1, 1)


def sel(cond, a, b):
    """cond ? a : b, for cond a 0/1 value."""
    a, b = C(a), C(b)
    if isinstance(b, Const) and b.v == 0:
        return mul(cond, a)
    if isinstance(a, Const) and a.v == 0:
        return mul(NOT(cond), b)
    return add(mul(cond, sub(a, b)), b)


def lim(x, lo, hi):
    return clamp(x, lo, hi)


def absx(x):
    return add(relu(x), relu(neg(x)))


def neg(x):
    return aff(x, -1, 0)


def sq(x):
    return mul(x, x)


def sin_deg(x):
    """sin of x degrees, x in -180..180: 4s(1-|s|) with s = x/180, then y(0.775 + 0.225|y|)"""
    s = aff(x, 1 / 180, 0)
    y = mul(s, aff(absx(s), -4, 4))
    return mul(y, aff(absx(y), 0.225, 0.775))


def cos_deg(x):
    """cos of x degrees, x in -180..180: sin(90 - |x|)"""
    return sin_deg(aff(absx(x), -1, 90))


def pwl(x, pts):
    """Piecewise linear function through pts [(x0, y0), (x1, y1), ...], flat outside."""
    x = C(x)
    out = C(pts[0][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dy = y1 - y0
        if dy == 0:
            continue
        seg = aff(x, abs(dy) / (x1 - x0), -abs(dy) * x0 / (x1 - x0), 0, abs(dy))
        out = add(out, seg) if dy > 0 else sub(out, seg)
    return out


# ======================================================================= variables
class Var:
    def __init__(self, prog, name, init=0.0, lo=-BIG, hi=BIG, clamp=True):
        self.prog, self.name, self.init, self.lo, self.hi = prog, name, float(init), float(lo), float(hi)
        self.clamped = clamp
        self.ent = prog.m.ent('math_counter', name,
                              min=_num(lo) if clamp else '0', max=_num(hi) if clamp else '0',
                              startvalue=_num(int(init)) if float(init).is_integer() else '0')
        if not float(init).is_integer():
            prog.init_values.append((self, init))
        self._read = None

    @property
    def r(self):
        if self._read is None:
            self._read = _cse(Read(self))
            self.prog.reads.add(self)
        return self._read

    def on_rise(self, target, inp, param=None, delay=0.0):
        assert self.clamped
        self.ent.out('OnHitMax', target, inp, param, delay)
        return self

    def on_fall(self, target, inp, param=None, delay=0.0):
        assert self.clamped
        self.ent.out('OnHitMin', target, inp, param, delay)
        return self

    def on_value(self, target, inp, delay=0.0):
        self.ent.out('OutValue', target, inp, None, delay)
        return self


# ======================================================================= the program
class Program:
    def __init__(self, m, name='plant', period=DT):
        self.m, self.name, self.period = m, name, period
        self.vars = {}
        self.reads = set()
        self.writes = []           # (var, expr, mode)
        self.sinks = []            # (ent name, input, expr)
        self.init_values = []
        self.start_delay = 0.1     # programs start on different server ticks so their ticks never coincide

    def share_names(self):
        self.shared = _share_names(self)

    def mirror(self, var, name=None):
        """A copy of another program's variable that this program can read: the original's OutValue sets it
        silently (SetValueNoFire), so this program sees the value from the original's last tick. (Only
        one program may ask a variable for its value: GetValue answers every reader at once.)"""
        mv = self.var(name or f'{var.name}_m', var.init, var.lo, var.hi, clamp=False)
        var.ent.out('OutValue', mv.ent, 'SetValueNoFire')
        return mv

    def var(self, name, init=0.0, lo=-BIG, hi=BIG, clamp=True):
        v = Var(self, name, init, lo, hi, clamp)
        self.vars[name] = v
        return v

    def flag(self, name, init=0):
        return self.var(name, init, 0, 1)

    def set(self, var, expr):
        self.writes.append((var, C(expr), 'SetValue'))

    def add(self, var, expr):
        self.writes.append((var, C(expr), 'Add'))

    def sink(self, target, inp, expr):
        self.sinks.append((target.name if isinstance(target, Ent) else target, inp, C(expr)))

    # ------------------------------------------------------------------ compile
    def compile(self):
        m = self.m
        timer = m.ent('logic_timer', f'{self.name}_clk', RefireTime=_num(self.period), StartDisabled=1)
        tick = m.ent('logic_relay', f'{self.name}_tick', spawnflags=2)
        late = m.ent('logic_relay', f'{self.name}_late', spawnflags=2)
        timer.out('OnTimer', tick, 'Trigger')
        tick.out('OnTrigger', late, 'Trigger')
        emit = {}        # node id -> (entity, output name)
        level = {}       # node id -> level its value arrives at a consumer
        hops = {}
        n = [0]
        self.nodes = []

        def new(cls, **kv):
            n[0] += 1
            e = m.ent(cls, _short(n[0]) + self.name[-1], **kv)
            self.nodes.append(e)
            return e

        def hop(node, k):
            """the node's value k levels later"""
            key = (id(node), k)
            if k == 0:
                return emit[id(node)], level[id(node)]
            if key not in hops:
                (pe, po), pl = hop(node, k - 1)
                r = new('math_remap', in1=0, in2=1, out1=0, out2=1)
                pe.out(po, r, 'InValue')
                hops[key] = ((r, 'OutValue'), pl + 1)
            return hops[key]

        def connect(node, target, inp, at_least):
            """deliver node's value to target.inp at a level >= at_least; returns the level"""
            build(node)
            k = max(0, at_least - level[id(node)])
            (e, o), lv = hop(node, k)
            e.out(o, target, inp)
            return lv

        def build(node):
            if id(node) in level:
                return
            if isinstance(node, Read):
                assert node.var.prog is self, f'{self.name} reads {node.var.name} of program {node.var.prog.name}: use a mirror'
                tick.out('OnTrigger', node.var.ent, 'GetValue')
                emit[id(node)], level[id(node)] = (node.var.ent, 'OnGetValue'), 2
            elif isinstance(node, Const):
                raise ValueError('a constant has no emitter')
            elif isinstance(node, Aff):
                build(node.x)
                kw = {}
                if node.k == 0:
                    raise ValueError('constant affine')
                if node.gate is not None:
                    glo, ghi = node.gate
                    r = new('math_remap', in1=_num(glo), in2=_num(ghi), out1=_num(node.k * glo + node.c),
                            out2=_num(node.k * ghi + node.c), spawnflags=1)
                elif node.clo is not None or node.chi is not None:
                    xlo, xhi = sorted((node.k * node.x.lo + node.c, node.k * node.x.hi + node.c))
                    lo = node.clo if node.clo is not None else (xlo - 1 if math.isfinite(xlo) else -BIG * 10)
                    hi = node.chi if node.chi is not None else (xhi + 1 if math.isfinite(xhi) else BIG * 10)
                    if node.k > 0:
                        i1, i2 = (lo - node.c) / node.k, (hi - node.c) / node.k
                        r = new('math_remap', in1=_num(i1), in2=_num(i2), out1=_num(lo), out2=_num(hi), spawnflags=2)
                    else:
                        raise ValueError('decreasing clamp: negate first')
                else:
                    r = new('math_remap', in1=0, in2=1, out1=_num(node.c), out2=_num(node.k + node.c))
                lv = connect(node.x, r, 'InValue', 0)
                emit[id(node)], level[id(node)] = (r, 'OutValue'), lv + 1
            elif isinstance(node, Bin):
                op = {'+': 'Add', '-': 'Subtract', '*': 'Multiply', '/': 'Divide'}[node.op]
                a, b = node.a, node.b
                lo = node.clo if node.clo is not None else 0
                hi = node.chi if node.chi is not None else 0
                if node.clo is not None and node.chi is None: hi = BIG * 10
                if node.chi is not None and node.clo is None: lo = -BIG * 10
                cnt = new('math_counter', min=_num(lo), max=_num(hi))
                if isinstance(a, Const):
                    tick.out('OnTrigger', cnt, 'SetValueNoFire', a.v)
                    la = 1
                    first, trig = a, b
                else:
                    build(a); build(b)
                    la, lb = level[id(a)], level[id(b)]
                    if node.op in '+*' and lb < la:
                        a, b, la, lb = b, a, lb, la
                    elif node.op == '-' and lb + 1 < la and node.clo is None and node.chi is None:
                        # a - b with b early: add a to -b (one remap) instead of delaying b
                        nb = _cse(Aff(b, -1, 0))
                        build(nb)
                        a, b = nb, a
                        op = 'Add'
                    first, trig = a, b
                    la = connect(first, cnt, 'SetValueNoFire', 0)
                if node.clo is not None or node.chi is not None:
                    # the first value is clamped when it is loaded: only safe if it can't leave the range
                    flo = first.lo
                    fhi = first.hi
                    assert (node.clo is None or flo >= node.clo - 1e-9) and (node.chi is None or fhi <= node.chi + 1e-9), \
                        f'clamped {node.op} node whose first operand ({flo}, {fhi}) leaves ({node.clo}, {node.chi})'
                lb = connect(trig, cnt, op, la + 1)
                emit[id(node)], level[id(node)] = (cnt, 'OutValue'), lb + 1
                cnt.kv['_first'] = la
                cnt.kv['_trig'] = lb

        for var, expr, mode in self.writes:
            if isinstance(expr, Const):
                late.out('OnTrigger', var.ent, mode, expr.v)
            else:
                connect(expr, var.ent, mode, 2)
        for tname, inp, expr in self.sinks:
            if isinstance(expr, Const):
                late.out('OnTrigger', tname, inp, expr.v)
            else:
                connect(expr, tname, inp, 2)
        # strip bookkeeping keys
        self.levels = {}
        for e in self.nodes:
            if '_first' in e.kv:
                self.levels[e.name] = (e.kv.pop('_first'), e.kv.pop('_trig'))
        self.share_names()
        # start: set the non-integer initial values, then start the clock
        auto = m.ent('logic_auto', f'{self.name}_auto', spawnflags=1)
        for v, val in self.init_values:
            auto.out('OnMapSpawn', v.ent, 'SetValue', val)
        auto.out('OnMapSpawn', timer, 'Enable', None, self.start_delay)
        self.timer = timer
        return self


def _share_names(prog):
    """math_remaps that take their only input from the same output share one name, so one event reaches all
    of them (the engine's lookup scans every named entity for each event anyway)."""
    m = prog.m
    remaps = {e.name: e for e in prog.nodes if e.cls == 'math_remap'}
    incoming = {}
    for e in m.ents:
        for o in e.outputs:
            if o[1] in remaps:
                incoming.setdefault(o[1], []).append((e, o))
    groups = {}
    for name, inc in incoming.items():
        if len(inc) == 1:
            src, (out, tgt, inp, par, delay, times) = inc[0]
            groups.setdefault((id(src), out, inp, par, delay), (src, []))[1].append(name)
    shared = 0
    for (sid, out, inp, par, delay), (src, names) in groups.items():
        if len(names) < 2:
            continue
        keep = names[0]
        for nm in names[1:]:
            remaps[nm].kv['targetname'] = keep
            shared += 1
        drop = set(names[1:])
        src.outputs = [o for o in src.outputs if not (o[0] == out and o[1] in drop and o[2] == inp)]
    m.by_name = {}
    for e in m.ents:
        if e.name:
            m.by_name.setdefault(e.name, e)
    return shared


def gate(x, cond, lo, hi):
    """x, passed on only on ticks where cond (0/1) is 1 (x must lie within [lo, hi])."""
    y = add(x, aff(cond, -BIG, BIG))
    return _cse(Aff(y, 1, 0, gate=(lo, hi)))
