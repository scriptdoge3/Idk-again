"""
Build Sable Creek Hydro for Half-Life 2 (Source).

  python3 build.py        -> out/sablecreek.vmf, then (with gbsp) out/sablecreek.bsp with its materials and
                             sounds packed inside

The room, the cabinets and the panel art are the GoldSrc map's (goldsrc/build.py is imported for them);
the needles, switches, dials, lamps and windows are Source brush entities driven by the plant logic in
hydro.py. Compiling uses gbsp, an open-source Source map compiler (github.com/drwxor/gbsp): set GBSP to
the folder with its gbsp, gvis and grad binaries. The .vmf also opens in Hammer.
"""
import importlib.util, math, os, shutil, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, '..', 'goldsrc')
sys.path.insert(1, GOLD)
_spec = importlib.util.spec_from_file_location('goldbuild', os.path.join(GOLD, 'build.py'))
gb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gb)
from hlfiles import Box, Poly, prism, ngon, face_map, face_map_up, write_wav       # noqa: E402
from srcfiles import Content, VmfWriter, pack_bsp, pow2                              # noqa: E402
import hydro                                                                         # noqa: E402

OUT = os.path.join(HERE, 'out')
NAME = 'sablecreek'
TEX = gb.TEX
FRONT = gb.FRONT
GR = 4.0                      # dial window radius
GPH = 5.8                     # bezel half height
GX = 6
DIAL = 256                    # dial textures: 32 texels per unit
SWEEP = 125                   # meters sweep 250 degrees: -125 .. +125 from 12 o'clock
CREAM, BLUE = (236, 230, 210, 255), (150, 205, 225, 255)
LIGHT_TEX = os.environ.get('SC_TEXLIGHT', '400')     # troffer brightness (texture light)
LIGHT_FILL = os.environ.get('SC_FILL', '12')
UNLIT = set()                 # textures drawn full bright (lit lenses, windows, needles, troffers)
ADDITIVE = set()


# =================================================================== art
def dial_texture(name, scales, unit, red=None):
    """Black switchboard meter dial, cream scale over 250 degrees, an optional second scale inside."""
    S, c = DIAL, DIAL / 2
    ang = lambda f: math.radians(-SWEEP + 2 * SWEEP * f)
    P = lambda a, r: (c + r * math.sin(a), c - r * math.cos(a))
    im = Image.new('RGBA', (S, S), (17, 17, 18, 255)); d = ImageDraw.Draw(im)
    lo, hi = scales[0][:2]
    arc = lambda r, f0, f1, col, w: d.arc([c - r, c - r, c + r, c + r], math.degrees(ang(f0)) - 90, math.degrees(ang(f1)) - 90, fill=col, width=w)
    if red:
        arc(108, (red[0] - lo) / (hi - lo), (red[1] - lo) / (hi - lo), (205, 40, 30, 255), 10)
    for si, (lo, hi, step, major, minor, fmt) in enumerate(scales):
        inner = si > 0
        col = BLUE if inner else CREAM
        r0 = 62 if inner else 104
        arc(r0, 0, 1, col, 2)
        for i in range(int(round((hi - lo) / minor)) + 1):
            val = lo + i * minor
            a = ang((val - lo) / (hi - lo))
            on = lambda q: abs((val - lo) / q - round((val - lo) / q)) < 1e-6
            ln = (14 if on(major) else 7) * (0.75 if inner else 1)
            d.line([P(a, r0), P(a, r0 + ln if inner else r0 - ln)], fill=col, width=4 if on(major) else 2)
            if on(step):
                gb.text(d, im, P(a, 46 if inner else 78), fmt(val) if fmt else f'{val:g}', 15 if inner else 19, col)
    for i, ln in enumerate(unit.split('|')):
        gb.text(d, im, (c, c + 62 + i * 20), ln, 18 if i == 0 else 13, CREAM if i == 0 else BLUE)
    hub(d, c)
    d.ellipse([2, 2, S - 3, S - 3], outline=(160, 162, 158, 255), width=6)
    TEX[name] = im.convert('RGB')
    return name


def hub(d, c):
    d.ellipse([c - 17, c - 17, c + 17, c + 17], fill=(52, 52, 54, 255), outline=(90, 90, 92, 255), width=2)


def pf_texture(name):
    """Power factor: needle angle linear in the power-factor angle, +-60 deg over the sweep; LEAD left."""
    S, c = DIAL, DIAL / 2
    P = lambda a, r: (c + r * math.sin(a), c - r * math.cos(a))
    ang = lambda phi: math.radians(SWEEP * phi / 60.0)
    im = Image.new('RGBA', (S, S), (17, 17, 18, 255)); d = ImageDraw.Draw(im)
    d.arc([c - 104, c - 104, c + 104, c + 104], -SWEEP - 90, SWEEP - 90, fill=CREAM, width=2)
    for pf, lab, major in ((1.0, '1', 1), (0.95, None, 0), (0.9, '.9', 1), (0.8, '.8', 1), (0.7, '.7', 1), (0.6, None, 0), (0.5, '.5', 1)):
        for sgn in ((1,) if pf == 1.0 else (-1, 1)):
            a = ang(sgn * math.degrees(math.acos(pf)))
            d.line([P(a, 104), P(a, 90 if major else 97)], fill=CREAM, width=4 if major else 2)
            if lab:
                gb.text(d, im, P(a, 76), lab, 19, CREAM)
    gb.text(d, im, P(ang(-40), 46), 'LEAD', 14, BLUE); gb.text(d, im, P(ang(40), 46), 'LAG', 14, BLUE)
    gb.text(d, im, (c, c + 62), 'PF', 18, CREAM)
    hub(d, c)
    d.ellipse([2, 2, S - 3, S - 3], outline=(160, 162, 158, 255), width=6)
    TEX[name] = im.convert('RGB')
    return name


def synchro_texture():
    S, c = DIAL, DIAL / 2
    P = lambda a, r: (c + r * math.sin(a), c - r * math.cos(a))
    im = Image.new('RGBA', (S, S), (17, 17, 18, 255)); d = ImageDraw.Draw(im)
    d.pieslice([c - 112, c - 112, c + 112, c + 112], -100, -80, fill=(30, 80, 40, 255))      # in phase, +-10 deg
    for k in range(12):
        a = k / 12 * 2 * math.pi
        d.line([P(a, 112), P(a, 94 if k % 3 == 0 else 102)], fill=CREAM, width=6 if k % 3 == 0 else 4)
    gb.text(d, im, (c - 60, c + 52), 'SLOW', 18, CREAM); gb.text(d, im, (c + 60, c + 52), 'FAST', 18, CREAM)
    d.arc([c - 80, c - 80, c + 80, c + 80], 120, 160, fill=CREAM, width=4)
    d.arc([c - 80, c - 80, c + 80, c + 80], 20, 60, fill=CREAM, width=4)
    for a0, sgn in ((160, 1), (20, -1)):                                                       # arrow heads
        t = math.radians(a0 + sgn * 4)
        tip = (c + 80 * math.cos(math.radians(a0 + sgn * 0)), c + 80 * math.sin(math.radians(a0)))
        d.polygon([tip, (c + 72 * math.cos(t), c + 72 * math.sin(t)), (c + 88 * math.cos(t), c + 88 * math.sin(t))], fill=CREAM)
    gb.text(d, im, (c, c + 84), 'SYNCHROSCOPE', 14, CREAM)
    hub(d, c)
    d.ellipse([2, 2, S - 3, S - 3], outline=(160, 162, 158, 255), width=6)
    TEX['sc_sync'] = im.convert('RGB')


LENS = gb.LENS


def lens_texture(name, colors, lit):
    """lamp lenses, 2 x 2 units each: one, or a pair 5 units wide. lit: which ones are lit."""
    pair = len(colors) == 2
    W = 160 if pair else 64
    im = Image.new('RGB', (W, 64), (26, 26, 26)); d = ImageDraw.Draw(im)
    boxes = [(0, 0, 63, 63), (96, 0, 159, 63)] if pair else [(0, 0, 63, 63)]
    for (x0, y0, x1, y1), col, on in zip(boxes, colors, lit):
        if col is None:
            col, on = 'white', False
        rgb = LENS[col][1 if on else 0]
        d.ellipse([x0 + 2, y0 + 2, x1 - 2, y1 - 2], fill=(14, 14, 14))
        d.ellipse([x0 + 6, y0 + 6, x1 - 6, y1 - 6], fill=rgb)
        if on:
            d.ellipse([x0 + 16, y0 + 12, x0 + 34, y0 + 24], fill=tuple(min(255, k + 70) for k in rgb))
    TEX[name] = im
    if any(lit):
        UNLIT.add(name)
    return name


def window_texture(name, legend, kind, lit):
    on_c, off_c, off_fg = gb.ANN_COLOURS[kind]
    im = Image.new('RGBA', (256, 128), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    d.rectangle([6, 6, 249, 121], fill=(on_c if lit else off_c) + (255,))
    fg = (24, 14, 10, 255) if lit else off_fg + (255,)
    a, b = legend.split('|')
    gb.text(d, im, (128, 42), a, 32, fg); gb.text(d, im, (128, 86), b, 32, fg)
    TEX[name] = im.convert('RGB')
    if lit:
        UNLIT.add(name)
    return name


def solid_tex(name, rgb, unlit=False, size=(16, 16)):
    TEX[name] = Image.new('RGB', size, rgb)
    if unlit:
        UNLIT.add(name)
    return name


# =================================================================== geometry
world = gb.world
E = []                        # (classname, keyvalues, outputs, brushes)


def W(*a, **k):
    world.append(Box(*a, **k))


def place(ent, brushes, **kv):
    """attach geometry to an entity the plant made"""
    ent.brushes = brushes
    ent.kv.update({k: str(v) for k, v in kv.items()})
    return ent


def needle_brushes(x, z, y0, y1, length, tail=0.9, w=0.25, tex='sc_ndl'):
    """tapered needle drawn pointing up from the pivot. Every edge is over 0.2 units: shorter ones make
    the compiler drop the face (WindingIsTiny), which breaks the brush."""
    poly = [(x - w, z - tail), (x + w, z - tail), (x + 0.15, z + length), (x - 0.15, z + length)]
    return [prism(poly, y0, y1, 'y', tex), Box(x - 0.25, y0, z - 0.25, x + 0.25, y1, z + 0.25, tex='ORIGIN')]


def build_panels(m, dev):
    sw = dev['switches']
    dl = dev['dials']
    lamps = dev['lamps']
    doors = [gb.Door(0, 'UNIT 1 - UNIT CONTROL', '+CP1'), gb.Door(1, 'UNIT 1 - ANNUNCIATOR', '+CP2'),
             gb.Door(2, 'UNIT 1 - AUXILIARIES', '+CP3'), gb.Door(gb.SP, 'SPILLWAY GATE', '+SP1', w=gb.SP_W, h=gb.SP_H, louvres=False)]
    nd = [0]
    door_xy = gb.door_xy

    def meter_case(x, z, Y0, tex, xl, xr):
        """Meter: the dial face in a rectangular case with a deep frame round it. (A round cut-out would put
        planes through the dial, and the compilers drop the thin wedges that leaves.)"""
        o = GR + 0.3
        W(x - o, Y0 - 0.6, z - o, x + o, Y0, z + o, tex='sc_black',
          faces={FRONT: (tex, face_map(x - GR - 0.3, z + o, DIAL / (2 * o)))})
        yf = Y0 - 2.2
        W(x - xl, yf, z + o, x + xr, Y0, z + GPH, tex='sc_bezel')
        W(x - xl, yf, z - GPH, x + xr, Y0, z - o, tex='sc_bezel')
        W(x - xl, yf, z - o, x - o, Y0, z + o, tex='sc_bezel')
        W(x + o, yf, z - o, x + xr, Y0, z + o, tex='sc_bezel')

    def gauge_at(x, z, Y0, tex, ptr, xl=None, xr=None):
        """Round meter facing -Y on a surface at y = Y0, and its needle (a momentary_rot_button the logic
        sets), 1 unit deep so the compilers keep it (they drop brush pieces under 1 cubic unit)."""
        meter_case(x, z, Y0, tex, xl or GX + 0.6, xr or GX + 0.6)
        place(m[ptr], needle_brushes(x, z, Y0 - 1.6, Y0 - 0.6, GR - 0.45), angles=f'{-SWEEP} 0 0', distance=2 * SWEEP)

    def gauge(ci, u, v, label, scales, unit, ptr, red=None, xl=None, xr=None, tex=None):
        x, z = door_xy(ci, u, v)
        if tex is None:
            tex = dial_texture(f'scg{nd[0]}', scales, unit, red); nd[0] += 1
        gauge_at(x, z, -0.5, tex, ptr, xl, xr)
        doors[ci].plate(u, v + GPH + 1.3, min(9.4, 0.55 * len(label) + 1.6), 1.4, label, px=0.8)

    def lampw(ci, u, v, name, labels):
        lm = lamps[name]
        colors = lm['colors']
        pair = colors[1] is not None
        w = 5.0 if pair else 2.0
        cols = colors if pair else (colors[0],)
        dark = lens_texture(f'scl_{name.lower()}_d', cols, (False,) * len(cols))
        world.append(gb.front_box(ci, u, v, w, 2.0, -0.9, -0.5, dark))
        ents = lm['ents']
        place(ents[0], [gb.front_box(ci, u, v, w, 2.0, -1.3, -0.9, lens_texture(f'scl_{name.lower()}_1', cols, (True, False)[:len(cols)]))])
        if pair:
            place(ents[1], [gb.front_box(ci, u, v, w, 2.0, -1.3, -0.9, lens_texture(f'scl_{name.lower()}_0', cols, (False, True)))])
        D = doors[ci]
        if pair:
            D.plate(u - 1.5, v + 2.1, 2.6, 1.0, labels[0], px=0.62); D.plate(u + 1.5, v + 2.1, 2.6, 1.0, labels[1], px=0.62)
        else:
            D.plate(u, v + 2.2, 5.4, 1.5, labels[0], px=0.62)

    def rot(ci, u, v, name, dial=False):
        """maintained rotary switch, 90 degrees clockwise: a bar knob, or a bigger dial with a white pointer"""
        r = sw[name]
        x, z = door_xy(ci, u, v)
        k = 1.4 if dial else 1.0
        doors[ci].escutcheon(u, v, r['pos'], r=2.6 * k)
        doors[ci].plate(u, v - 2.6 * k - 2.3, 7.6, 1.4, r['label'], px=0.8)
        if dial:
            world.append(prism(ngon(x, z, 1.5), -1.4, -0.5, 'y', 'sc_metal'))
            pl = lambda poly: [(x + px * k, z + pz * k) for px, pz in poly]
            brushes = [prism(pl(gb.BAR), -2.6, -1.4, 'y', 'sc_knob'), prism(pl(gb.BAR_TIP), -2.6, -1.4, 'y', 'sc_white')]
        else:
            brushes = [Box(x - 0.45, -1.6, z - 1.7, x + 0.45, -0.6, z + 1.7, tex='sc_knob')]
        place(r['ent'], brushes + [Box(x - 0.5, -1.6, z - 0.5, x + 0.5, -0.6, z + 0.5, tex='ORIGIN')])

    def cs_switch(ci, u, v, name):
        """control switch: pistol grip, left position = pos[0], right = pos[1], -45 -> +45 degrees"""
        r = sw[name]
        x, z = door_xy(ci, u, v); D = doors[ci]
        D.ring(u, v, 4.4, (233, 182, 28, 255) if r['grip'] == 'red' else gb.ESC, outline=(90, 90, 86, 255))
        for sgn, lab, col in ((-1, r['pos'][0], (16, 110, 50, 255)), (1, r['pos'][1], (170, 26, 18, 255))):
            gb.text(D.d, D.img, ((u + sgn * 2.45) * gb.PPU, (v - 2.45) * gb.PPU), lab, 0.6 * gb.PPU, col)
        D.plate(u, v + 5.6, min(11.5, 0.5 * len(r['label']) + 1.6), 1.4, r['label'], px=0.75)
        world.append(prism(ngon(x, z, 1.35), -1.3, -0.5, 'y', 'sc_metal'))
        place(r['ent'], [prism(gb.turned(gb.PISTOL, x, z, 45), -2.9, -1.3, 'y', 'sc_red' if r['grip'] == 'red' else 'sc_knob'),
                         Box(x - 0.5, -2.6, z - 0.5, x + 0.5, -1.6, z + 0.5, tex='ORIGIN')])

    def synchroscope(ci, u, v):
        x, z = door_xy(ci, u, v)
        meter_case(x, z, -0.5, 'sc_sync', 5.7, 6.4)
        place(m[dev['scope']], needle_brushes(x, z, -2.1, -1.1, GR - 0.5, tail=1.3, w=0.3), distance=360, angles='0 0 0')
        doors[ci].plate(u, v + GPH + 1.3, 9, 1.4, 'SYNCHROSCOPE', px=0.8)

    def knob_panel(ci, u, v, name, label):
        """FIRING ANGLE: a knob whose position is the manual firing angle (90 deg at the left stop, no field;
        0 deg at the right stop, full field), 300 degrees of travel."""
        x, z = door_xy(ci, u, v); D = doors[ci]
        W(x - 2.6, -0.8, z - 2.6, x + 2.6, -0.5, z + 2.6, tex='sc_metal')
        body = prism(ngon(x, z, 1.9), -2.3, -0.8, 'y', 'sc_knob')
        idx = prism([(x - 0.3, z + 0.4), (x + 0.3, z + 0.4), (x + 0.3, z + 1.7), (x - 0.3, z + 1.7)], -2.8, -1.3, 'y', 'sc_white')
        start = -150 + 300 * hydro.KNOB0
        place(dl[name]['ent'], [body, idx, Box(x - 0.5, -2.0, z - 0.5, x + 0.5, -1.0, z + 0.5, tex='ORIGIN')],
              angles=f'{start:.2f} 0 0')
        D.plate(u, v - 3.7, 9.5, 1.4, label, px=0.8)
        # scale: LOWER at the left stop, RAISE at the right
        for k in range(11):
            a = math.radians(-150 + 30 * k)
            p0 = ((u + 3.0 * math.sin(a)) * gb.PPU, (v - 3.0 * math.cos(a)) * gb.PPU)
            p1 = ((u + (3.6 if k % 5 == 0 else 3.3) * math.sin(a)) * gb.PPU, (v - (3.6 if k % 5 == 0 else 3.3) * math.cos(a)) * gb.PPU)
            D.d.line([p0, p1], fill=(24, 24, 24, 255), width=2)
        gb.text(D.d, D.img, ((u - 3.2) * gb.PPU, (v + 3.3) * gb.PPU), 'LOWER', 0.55 * gb.PPU, (24, 24, 24, 255))
        gb.text(D.d, D.img, ((u + 3.2) * gb.PPU, (v + 3.3) * gb.PPU), 'RAISE', 0.55 * gb.PPU, (24, 24, 24, 255))

    def spring_dial(ci, u, v, name):
        """spring-return dial: held, it turns 60 degrees clockwise to its stop; let go, it springs back"""
        x, z = door_xy(ci, u, v); D = doors[ci]
        D.ring(u, v, 2.7, gb.ESC, outline=(90, 90, 86, 255))
        D.arrow(u, v, 3.4, False)
        world.append(prism(ngon(x, z, 1.5), -1.1, -0.5, 'y', 'sc_metal'))
        body = prism(ngon(x, z, 1.9), -2.4, -1.1, 'y', 'sc_knob')
        bar = prism([(x - 0.35, z - 1.7), (x + 0.35, z - 1.7), (x + 0.35, z + 1.7), (x - 0.35, z + 1.7)], -3.1, -2.4, 'y', 'sc_knob')
        tip = prism([(x - 0.4, z + 0.5), (x + 0.4, z + 0.5), (x + 0.4, z + 1.8), (x - 0.4, z + 1.8)], -3.4, -2.2, 'y', 'sc_white')
        place(dl[name]['ent'], [body, bar, tip, Box(x - 0.5, -2.0, z - 0.5, x + 0.5, -1.0, z + 0.5, tex='ORIGIN')])
        D.plate(u, v + 4.4, 5.6, 1.4, dl[name]['label'], px=0.8)

    ROW1, ROW2, CTL = 13, 29, 50

    # ------------------------------------------- left: unit control
    D = doors[0]
    D.section(1.5, 5.5, 53, 32.5, 'METERS')
    gauge(0, 7, ROW1, 'GENERATOR VOLTS', [(0, 600, 100, 100, 20, None)], 'AC VOLTS', 'p_volts', xr=5)
    gauge(0, 17, ROW1, 'KILOWATTS', [(0, 320, 80, 40, 10, None)], 'KW', 'p_kw', xl=5, xr=5)
    gauge(0, 27, ROW1, 'POWER FACTOR', None, None, 'p_pf', xl=5, xr=7.3, tex=pf_texture('scg_pf'))
    synchroscope(0, 41, ROW1)
    world.append(gb.front_box(0, 51.5, ROW1 - 1, 5, 2, -1.0, -0.5, lens_texture('sc_slmp0', ('white', 'white'), (False, False))))
    sl = Image.new('RGB', (160, 64), (0, 0, 0)); d = ImageDraw.Draw(sl)
    for x0 in (0, 96):
        d.ellipse([x0 + 6, 6, x0 + 57, 57], fill=(255, 236, 190))
    TEX['sc_slmp1'] = sl; UNLIT.add('sc_slmp1'); ADDITIVE.add('sc_slmp1')
    E.append(('func_brush', {'targetname': 'SYNCLAMPS', 'rendermode': '5', 'renderamt': '0', 'Solidity': '1'}, [],
              [gb.front_box(0, 51.5, ROW1 - 1, 5, 2, -1.3, -1.0, 'sc_slmp1')]))
    D.plate(51.5, ROW1 + 1.4, 5.4, 1.0, 'SYNC LAMPS', px=0.62)
    lampw(0, 51.5, ROW1 + 5, 'L_perm', ('SYNC CHECK',))
    gauge(0, 7, ROW2, 'UNIT SPEED', [(0, 150, 25, 25, 5, None)], 'RPM', 'p_speed', red=(140, 150), xr=5)
    gauge(0, 17, ROW2, 'GATE POSITION', [(0, 100, 20, 10, 2, None)], 'PERCENT OPEN', 'p_gate', xl=5, xr=5)
    gauge(0, 27, ROW2, 'FIELD CURRENT', [(0, 5, 1, 1, 0.2, None)], 'DC AMPS', 'p_exc', xl=5, xr=5)
    gauge(0, 37, ROW2, 'FIRING ANGLE', [(0, 90, 15, 15, 5, None)], 'DEGREES', 'p_fa', xl=5)
    D.section(1.5, 40, 53, 44, 'CONTROLS')
    cs_switch(0, 8, CTL, 'r_ss')
    cs_switch(0, 21, CTL, 'r_52'); lampw(0, 21, CTL + 9, 'LP_cb', ('CLOSED', 'OPEN'))
    cs_switch(0, 34, CTL, 'r_exc'); lampw(0, 34, CTL + 9, 'LP_exc', ('CLOSED', 'OPEN'))
    cs_switch(0, 47, CTL, 'r_gt')
    D.plate(11, CTL + 15.6, 13, 1.4, 'WICKET GATE', px=0.8)
    spring_dial(0, 6, CTL + 21, 'k_gl'); spring_dial(0, 16, CTL + 21, 'k_gr')
    rot(0, 30, CTL + 21, 'r_br', dial=True)
    lampw(0, 30, CTL + 28.5, 'LP_brake', ('APPLIED', 'RELEASED'))
    knob_panel(0, 45, CTL + 21, 'k_fa', 'FIRING ANGLE')

    # ------------------------------------------- middle: the annunciator, the PLC and the AVR
    D = doors[1]
    W(door_xy(1, 0.5, 0)[0], -0.9, gb.DOOR_TOP - 30.5, door_xy(1, 55.5, 0)[0], -0.5, gb.DOOR_TOP - 4.5, tex='sc_black')
    for i, w in enumerate(dev['windows']):
        c, r = i % 5, i // 5
        u, v = 6.55 + c * 10.725, 8 + r * 6.2
        world.append(gb.front_box(1, u, v, 10.3, 5.8, -1.4, -0.9, window_texture(f'scw{i:02d}d', w['legend'], w['kind'], False)))
        place(w['ent'], [gb.front_box(1, u, v, 10.3, 5.8, -1.7, -1.4, window_texture(f'scw{i:02d}l', w['legend'], w['kind'], True))])
    gauge(1, 22, 37, 'GEN FREQUENCY', [(54, 66, 2, 1, 0.2, None)], 'Hz', 'p_hz', xr=6)
    gauge(1, 34, 37, 'STATION FREQUENCY', [(54, 66, 2, 1, 0.2, None)], 'Hz', 'p_sfreq', xl=6)
    cs_switch(1, 17, CTL, 'r_plc')
    cs_switch(1, 39, CTL, 'r_avr')

    # ------------------------------------------- right: auxiliaries
    D = doors[2]
    D.section(1.5, 5.5, 53, 32.5, 'METERS')
    gauge(2, 7, ROW1, 'OIL PRESSURE', [(0, 60, 10, 10, 2, None)], 'PSI', 'p_lube', red=(0, 20), xr=5)
    gauge(2, 17, ROW1, 'WATER FLOW', [(0, 100, 20, 10, 5, None)], 'GPM', 'p_cw', red=(0, 35), xl=5, xr=5)
    gauge(2, 27, ROW1, 'BEARING TEMP', [(20, 100, 20, 10, 5, None)], 'DEG C', 'p_bt', red=(76, 100), xl=5, xr=5)
    gauge(2, 37, ROW1, 'VIBRATION', [(0, 20, 5, 5, 1, None)], 'MILS P-P', 'p_vib', red=(12, 20), xl=5)
    gauge(2, 7, ROW2, 'HYDRAULIC PRESS', [(0, 400, 100, 50, 10, None)], 'PSI', 'p_opu', red=(0, 220), xr=5)
    gauge(2, 17, ROW2, 'BRAKE AIR PRESS', [(0, 150, 25, 25, 5, None)], 'PSI', 'p_air', red=(0, 50), xl=5)
    D.section(1.5, 40, 53, 22, 'PUMPS')
    for u, nm in ((8, 'r_lp'), (21, 'r_wp'), (34, 'r_hp'), (47, 'r_ac')):
        cs_switch(2, u, CTL, nm)

    # ------------------------------------------- spillway panel, on the wall beside the extinguisher
    w0 = len(world)
    wall_ents = []
    D = doors[gb.SP]
    for nm in ('p_hw', 'p_rq', 'p_spill', 'r_sp', 'k_sl', 'k_sr'):
        wall_ents.append(m[nm])
    gauge(gb.SP, 7, 12, 'RIVER DEPTH', [(0, 10, 1, 1, 0.25, None)], 'METERS', 'p_hw', red=(9, 10), xl=5.5, xr=6.5)
    gauge(gb.SP, 20, 12, 'RIVER FLOW', [(0, 120, 20, 20, 5, None)], 'CFS', 'p_rq', xl=6.5, xr=6.5)
    gauge(gb.SP, 33, 12, 'GATE OPENING', [(0, 1.2, 0.2, 0.2, 0.05, lambda v: f'{v:.1f}')], 'METERS', 'p_spill', xl=6.5, xr=5.5)
    rot(gb.SP, 8, 32, 'r_sp', dial=True)
    D.plate(27.5, 26.6, 13, 1.4, 'GATE', px=0.8)
    spring_dial(gb.SP, 22, 32, 'k_sl'); spring_dial(gb.SP, 33, 32, 'k_sr')
    W(-1, 0, gb.SP_TOP - gb.SP_H - 1, gb.SP_W + 1, 6, gb.SP_TOP + 1, tex='sc_paintd', scale=0.5)
    TEX['scdsp'] = D.img.convert('RGB')
    W(0, -0.5, gb.SP_TOP - gb.SP_H, gb.SP_W, 0, gb.SP_TOP, tex='sc_paintd', faces={FRONT: ('scdsp', face_map(0, gb.SP_TOP, gb.PPU))})
    world[w0:] = [gb.to_wall(b) for b in world[w0:]]
    for e in wall_ents:
        e.brushes = [gb.to_wall(b) for b in e.brushes]
        sf = int(e.kv['spawnflags']); assert sf & 128
        sf = (sf & ~128) | 64                         # turns about X now (roll)
        if e.cls == 'func_rot_button':
            sf ^= 2                                   # reversed, so it still turns clockwise seen from the room
        else:
            e.kv['distance'] = str(-float(e.kv['distance']))      # momentary: a negative distance turns the other way
            if 'angles' in e.kv:
                p = float(e.kv['angles'].split()[0])
                e.kv['angles'] = f'0 0 {-p:g}'
        e.kv['spawnflags'] = str(sf)

    # door art -> one texture per door
    for ci, Dr in enumerate(doors[:3]):
        TEX[f'scd{ci}'] = Dr.img.convert('RGB')
        x0 = gb.CX0[ci] + 2
        W(x0, -0.5, gb.DOOR_TOP - gb.DOOR_H, x0 + gb.DOOR_W, 0, gb.DOOR_TOP, tex='sc_paintd',
          faces={FRONT: (f'scd{ci}', face_map(x0, gb.DOOR_TOP, gb.PPU))})


def build_room():
    gb.build_room()
    gb.ents[:] = [e for e in gb.ents if e['classname'] == 'worldspawn']
    # the troffers light the room themselves (texture lights, out/sablecreek.rad); two dim fills
    E.append(('light', {'origin': '0 -60 70', '_light': '255 246 232 ' + LIGHT_FILL}, [], []))
    E.append(('light', {'origin': '-120 -120 80', '_light': '255 246 232 ' + LIGHT_FILL}, [], []))
    E.append(('info_player_start', {'origin': '0 -185 1', 'angles': '0 90 0'}, [], []))
    UNLIT.add('sc_light')
    solid_tex('sc_ndl', (255, 104, 44), unlit=True)


def make_sounds(dirpath):
    gb.make_sounds(dirpath)
    sr = 22050
    t = np.arange(int(sr * 0.08)) / sr
    rng = np.random.default_rng(5)
    click = rng.standard_normal(len(t)) * np.exp(-t * 90) + 0.6 * np.sin(2 * np.pi * 900 * t) * np.exp(-t * 60)
    write_wav(os.path.join(dirpath, 'switch.wav'), click * 0.5, sr)
    # air compressor: a two-cylinder piston compressor thumping at 12 Hz over motor whine
    t = np.arange(int(sr * 2.0)) / sr
    thump = np.maximum(0, np.sin(2 * np.pi * 12 * t)) ** 6
    comp = 0.6 * thump * np.sin(2 * np.pi * 70 * t) + 0.15 * np.sin(2 * np.pi * 240 * t) + 0.12 * rng.standard_normal(len(t)) * thump
    write_wav(os.path.join(dirpath, 'compressor.wav'), comp[:sr] * 0.6, sr, loop=True)



def brush_volume(brush):
    """volume of a convex brush from its face planes (the compilers drop brush pieces under 1 unit^3)"""
    import re as _re
    planes = []
    for ln in brush.lines():
        pts = [np.array([float(c) for c in g.split()]) for g in _re.findall(r'\(\s*([^)]*)\)', ln)[:3]]
        n = np.cross(pts[0] - pts[1], pts[2] - pts[1]); n /= np.linalg.norm(n)
        planes.append((n, float(n @ pts[1])))
    vol = 0.0
    for i, (n, d) in enumerate(planes):
        a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(n, a); u /= np.linalg.norm(u); v = np.cross(n, u)
        c = n * d
        w = [c + 1e4 * (su * u + sv * v) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for j, (m2, d2) in enumerate(planes):
            if i == j or not w:
                continue
            out = []
            for k in range(len(w)):
                p, q = w[k], w[(k + 1) % len(w)]
                dp, dq = p @ m2 - d2, q @ m2 - d2
                if dp <= 0: out.append(p)
                if (dp < 0) != (dq < 0) and abs(dp - dq) > 1e-12:
                    out.append(p + (q - p) * dp / (dp - dq))
            w = out
        if len(w) < 3:
            continue
        area = 0.5 * sum(np.cross(w[k] - w[0], w[k + 1] - w[0]) @ n for k in range(1, len(w) - 1))
        vol += area * d / 3
    return vol


def check_volumes(world, ents, limit=1.1):
    bad = []
    for label, brushes in [('world', world)] + [(f'{c} {kv.get("targetname", "")}', b) for c, kv, _, b in ents]:
        for b in brushes:
            if 'ORIGIN' in ' '.join(b.lines()[0].split()[9:10]) or all('ORIGIN' in ln for ln in b.lines()):
                continue
            v = brush_volume(b)
            if v < limit:
                bad.append((label, round(v, 2), b.lines()[0][:60]))
    return bad

# =================================================================== main
def main():
    os.makedirs(OUT, exist_ok=True)
    m, P, dev = hydro.build()
    gb.room_textures(); gb.button_textures(); synchro_texture()
    build_room()
    build_panels(m, dev)
    pos = {'s_turb': '0 10 20', 's_water': '0 20 10', 's_hum': '0 10 60', 's_horn': '0 10 116', 's_pump': '60 10 20',
           's_brk': '-60 -2 80', 's_relay': '0 -2 90', 's_click': '0 -10 60', 's_comp': '70 12 12'}
    for nm, e in dev['sounds'].items():
        e.kv['origin'] = pos[nm]

    game = os.path.join(OUT, 'game')
    if os.path.isdir(game):
        shutil.rmtree(game)
    C = Content(game)
    C.add('gameinfo.txt', '"GameInfo"\n{\n game "Sable Creek"\n FileSystem\n {\n  SearchPaths\n  {\n'
          '   game+mod "|gameinfo_path|."\n  }\n }\n}\n', pak=False)
    C.tool('tools/toolsorigin', ['%compileorigin'])
    C.tool('tools/toolsnodraw', ['%compilenodraw', '%compilenolight'])
    # materials: every texture, at power-of-two sizes; offsets and scales are rescaled to match
    factors = {}
    for name, img in TEX.items():
        if name.startswith('+'):
            continue                                   # the GoldSrc map's animated lamps
        im = pow2(img, 1024)
        factors[name] = (im.size[0] / img.size[0], im.size[1] / img.size[1])
        mat = f'sablecreek/{name.lower()}'
        if name in ADDITIVE:
            C.material(mat, im, 'UnlitGeneric', {'$additive': 1})
        elif name in UNLIT:
            C.material(mat, im, 'UnlitGeneric', compress=im.size[0] * im.size[1] >= 128 * 128)
        else:
            C.material(mat, im, 'LightmappedGeneric', {'$surfaceprop': 'metal'}, compress=im.size[0] * im.size[1] >= 128 * 128)

    def tex(name):
        if name == 'ORIGIN':
            return 'TOOLS/TOOLSORIGIN', 1, 1
        fu, fv = factors[name]
        return f'SABLECREEK/{name.upper()}', fu, fv
    snd = os.path.join(game, 'sound', 'sablecreek')
    make_sounds(snd)
    for f in sorted(os.listdir(snd)):
        C.files[f'sound/sablecreek/{f}'] = open(os.path.join(snd, f), 'rb').read()

    ents = list(E)
    for e in m.ents:
        ents.append((e.cls, {k: str(v) for k, v in e.kv.items()}, e.outputs, e.brushes))
    bad = check_volumes(world, ents)
    for x in bad[:40]:
        print('  small brush', *x)
    print(f'{len(bad)} brushes under 1.1 cubic units')
    vmf = os.path.join(OUT, f'{NAME}.vmf')
    VmfWriter(tex, lightmapscale=8).write(vmf, {'skyname': 'sky_day01_01', 'message': 'Sable Creek Hydro - Unit 1'}, world, ents)
    net = sum(1 for e in m.ents if e.brushes or e.cls == 'ambient_generic')
    print(f'{len(ents)} entities: {len(m.ents) - net} logic (no network slot), {net} networked, '
          f'{len(E)} lights and start; {len(world)} world brushes, {len(factors)} materials')

    gbsp = os.environ.get('GBSP')
    if not gbsp:
        print('set GBSP to the folder with gbsp, gvis and grad to compile'); return
    maps = os.path.join(game, 'maps'); os.makedirs(maps, exist_ok=True)
    shutil.copy(vmf, maps)
    run = lambda *a: subprocess.run(a, cwd=maps, check=True, capture_output=True, text=True).stdout
    out = run(os.path.join(gbsp, 'gbsp'), '-game', game, f'{NAME}.vmf')
    print('\n'.join(l for l in out.splitlines() if 'eak' in l or 'entities' in l or 'wrote' in l or 'arning' in l)[:2000])
    open(os.path.join(maps, f'{NAME}.rad'), 'w').write(f'sablecreek/sc_light 255 244 226 {LIGHT_TEX}\n')
    run(os.path.join(gbsp, 'gvis'), NAME)
    run(os.path.join(gbsp, 'grad'), NAME)
    bsp = os.path.join(OUT, f'{NAME}.bsp')
    shutil.copy(os.path.join(maps, f'{NAME}.bsp'), bsp)
    n = pack_bsp(bsp, C.files)
    print(f'packed {len(C.files)} files ({n / 1e6:.1f} MB); {bsp}: {os.path.getsize(bsp) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
