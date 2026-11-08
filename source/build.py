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
from srcfiles import Content, VmfWriter, pack_bsp, pow2, strip_prims                              # noqa: E402
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
    sq = lambda ln: min(0.86, 0.86 * 12 / len(ln))       # 13-letter lines a little narrower, clear of the frame
    gb.text(d, im, (128, 42), a, 32, fg, squeeze=sq(a)); gb.text(d, im, (128, 86), b, 32, fg, squeeze=sq(b))
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
    doors = [gb.Door(0, 'UNIT 1 GENERATOR CONTROL', 'CP-1'), gb.Door(1, 'UNIT 1 ANNUNCIATOR', 'CP-2'),
             gb.Door(2, 'UNIT 1 AUXILIARIES', 'CP-3'), gb.Door(gb.SP, 'SPILLWAY GATE CONTROL', 'SP-1', w=gb.SP_W, h=gb.SP_H, louvres=False)]
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

    def pushbutton(ci, u, v, name, tex):
        """illuminated-style pushbutton: a round cap in a chrome bezel; the func_button is 4 units deep (most
        of it inside the cabinet) so it has room to travel 1.2 units in when pressed"""
        x, z = door_xy(ci, u, v); D = doors[ci]
        world.append(prism(ngon(x, z, 1.9), -1.1, -0.5, 'y', 'sc_metal'))
        b = dev['buttons'][name]
        place(b['ent'], [prism(ngon(x, z, 1.35), -2.6, 1.4, 'y', tex)], lip=0.8)
        D.plate(u, v + 3.2, 9.5, 1.4, b['label'], px=0.8)

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
    gauge(0, 27, ROW2, 'FIELD CURRENT', [(0, 60, 10, 10, 2, None)], 'DC AMPS', 'p_exc', xl=5, xr=5)
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
    knob_panel(0, 45, CTL + 21, 'k_fa', dl['k_fa']['label'])

    # ------------------------------------------- middle: the annunciator, the governor and the voltage regulator
    D = doors[1]
    W(door_xy(1, 0.5, 0)[0], -0.9, gb.DOOR_TOP - 30.5, door_xy(1, 55.5, 0)[0], -0.5, gb.DOOR_TOP - 4.5, tex='sc_black')
    for i, w in enumerate(dev['windows']):
        c, r = i % 5, i // 5
        u, v = 6.55 + c * 10.725, 8 + r * 6.2
        world.append(gb.front_box(1, u, v, 10.3, 5.8, -1.4, -0.9, window_texture(f'scw{i:02d}d', w['legend'], w['kind'], False)))
        place(w['ent'], [gb.front_box(1, u, v, 10.3, 5.8, -1.7, -1.4, window_texture(f'scw{i:02d}l', w['legend'], w['kind'], True))])
    gauge(1, 22, 37, 'GEN FREQUENCY', [(54, 66, 2, 1, 0.2, None)], 'HERTZ', 'p_hz', xr=6)
    gauge(1, 34, 37, 'BUS FREQUENCY', [(54, 66, 2, 1, 0.2, None)], 'HERTZ', 'p_sfreq', xl=6)
    cs_switch(1, 17, CTL, 'r_plc')
    cs_switch(1, 39, CTL, 'r_avr')
    # annunciator pushbuttons: ACKNOWLEDGE (amber), RESET and TEST (black)
    D.section(1.5, 58.5, 53, 11, 'ANNUNCIATOR')
    for u, nm, tex in ((14, 'b_ack', 'sc_btn_a'), (28, 'b_rst', 'sc_btn_k'), (42, 'b_test', 'sc_btn_k')):
        pushbutton(1, u, 63, nm, tex)

    # ------------------------------------------- right: auxiliaries
    D = doors[2]
    D.section(1.5, 5.5, 53, 32.5, 'METERS')
    gauge(2, 7, ROW1, 'LUBE OIL PRESS', [(0, 60, 10, 10, 2, None)], 'PSI', 'p_lube', red=(0, 20), xr=5)
    gauge(2, 17, ROW1, 'COOLING WATER', [(0, 100, 20, 10, 5, None)], 'GPM', 'p_cw', red=(0, 35), xl=5, xr=5)
    gauge(2, 27, ROW1, 'THRUST BRG TEMP', [(20, 100, 20, 10, 5, None)], 'DEG C', 'p_bt', red=(76, 100), xl=5, xr=5)
    gauge(2, 37, ROW1, 'SHAFT VIBRATION', [(0, 20, 5, 5, 1, None)], 'MILS P-P', 'p_vib', red=(12, 20), xl=5)
    gauge(2, 7, ROW2, 'GOV OIL PRESS', [(0, 400, 100, 50, 10, None)], 'PSI', 'p_opu', red=(0, 220), xr=5)
    gauge(2, 17, ROW2, 'BRAKE AIR PRESS', [(0, 150, 25, 25, 5, None)], 'PSI', 'p_air', red=(0, 50), xl=5, xr=5)
    gauge(2, 27, ROW2, 'NET HEAD', [(0, 60, 10, 10, 2, None)], 'FEET', 'p_head', xl=5)
    D.section(1.5, 40, 53, 22, 'AUXILIARY MOTORS')
    for u, nm in ((8, 'r_lp'), (21, 'r_wp'), (34, 'r_hp'), (47, 'r_ac')):
        cs_switch(2, u, CTL, nm)

    # ------------------------------------------- spillway panel, on the wall beside the extinguisher
    w0 = len(world)
    wall_ents = []
    D = doors[gb.SP]
    for nm in ('p_hw', 'p_rq', 'p_spill', 'r_sp', 'k_sl', 'k_sr'):
        wall_ents.append(m[nm])
    gauge(gb.SP, 7, 12, 'HEADWATER LEVEL', [(0, 10, 1, 1, 0.25, None)], 'METERS', 'p_hw', red=(9, 10), xl=5.5, xr=6.5)
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


# =================================================================== room details
def tex_img(name, size, bg, unlit=False):
    im = Image.new('RGBA', size, bg + (255,) if len(bg) == 3 else bg)
    TEX[name] = im
    if unlit:
        UNLIT.add(name)
    return im, ImageDraw.Draw(im)


def finish(name, im):
    TEX[name] = im.convert('RGB')


def lines_text(d, im, x, y, lines, px, col, gap=1.35, anchor='lm', bold=False, squeeze=0.9):
    for i, ln in enumerate(lines):
        gb.text(d, im, (x, y + i * px * gap), ln, px, col, anchor=anchor, bold=bold, squeeze=squeeze)


def on_wall_mx(y0, y1, z0, z1, tex, depth=1.0, x_face=160, side='sc_black'):
    """item on the right wall, facing -X (its art mirrored so it reads from the room)"""
    w, h = TEX[tex].size
    su, sv = (y1 - y0) / w, (z1 - z0) / h
    W(x_face - depth, y0, z0, x_face, y1, z1, tex=side, faces={(-1, 0, 0): (tex, (y1 / su, z1 / sv, -su, sv))})


def on_wall_px(y0, y1, z0, z1, tex, depth=1.0, x_face=-160, side='sc_black'):
    """item on the left wall, facing +X"""
    w, h = TEX[tex].size
    su, sv = (y1 - y0) / w, (z1 - z0) / h
    W(x_face, y0, z0, x_face + depth, y1, z1, tex=side, faces={(1, 0, 0): (tex, (-y0 / su, z1 / sv, su, sv))})


def on_wall_py(x0, x1, z0, z1, tex, depth=1.0, y_face=-232, side='sc_black'):
    """item on the back wall, facing +Y (towards the panels)"""
    w, h = TEX[tex].size
    su, sv = (x1 - x0) / w, (z1 - z0) / h
    W(x0, y_face, z0, x1, y_face + depth, z1, tex=side, faces={(0, 1, 0): (tex, (x1 / su, z1 / sv, -su, sv))})


def facing_my(x0, x1, y0, y1, z0, z1, tex, side='sc_black'):
    """box whose -Y face carries art"""
    w, h = TEX[tex].size
    su, sv = (x1 - x0) / w, (z1 - z0) / h
    W(x0, y0, z0, x1, y1, z1, tex=side, faces={(0, -1, 0): (tex, (-x0 / su, z1 / sv, su, sv))})


def top_art(x0, x1, y0, y1, z0, z1, tex, side='sc_black'):
    """box whose top carries art, reading from -Y"""
    w, h = TEX[tex].size
    su, sv = (x1 - x0) / w, (y1 - y0) / h
    W(x0, y0, z0, x1, y1, z1, tex=side, faces={gb.UP: (tex, (-x0 / su, y1 / sv, su, sv))})


def safety_sign(name, header, hdr_bg, hdr_fg, body, size=(256, 192)):
    """ANSI Z535-style sign: signal word panel, then the message"""
    W_, H_ = size
    im, d = tex_img(name, size, (250, 250, 246))
    hh = int(H_ * 0.32)
    d.rectangle([0, 0, W_ - 1, hh], fill=hdr_bg)
    if header == 'DANGER':
        d.ellipse([W_ * 0.18, hh * 0.12, W_ * 0.82, hh * 0.88], fill=(200, 16, 30))
    gb.text(d, im, (W_ / 2, hh / 2), header, hh * 0.55, hdr_fg if header != 'DANGER' else (255, 255, 255))
    px = min((H_ - hh) / (len(body) + 1.6), W_ * 0.92 / (0.62 * 0.86 * max(len(b) for b in body)))
    lines_text(d, im, W_ / 2, hh + (H_ - hh) / (len(body) + 1), body, px, (16, 16, 16),
               gap=(H_ - hh) / (len(body) + 1) / px, anchor='mm', bold=True, squeeze=0.86)
    d.rectangle([0, 0, W_ - 1, H_ - 1], outline=(30, 30, 30), width=3)
    finish(name, im)
    return name


def procedure_sheet(name, title, sections):
    im, d = tex_img(name, (512, 704), (246, 244, 236))
    d.rectangle([0, 0, 511, 703], outline=(60, 60, 60), width=4)
    d.rectangle([0, 0, 511, 64], fill=(28, 60, 120))
    gb.text(d, im, (256, 33), title, 34, (255, 255, 255), squeeze=0.9)
    y = 104
    for head, steps in sections:
        gb.text(d, im, (22, y), head, 27, (28, 60, 120), anchor='lm', squeeze=0.9); y += 42
        for st in steps:
            gb.text(d, im, (28, y), st, 21, (20, 20, 20), anchor='lm', bold=False, squeeze=0.84); y += 34
        y += 20
    gb.text(d, im, (488, 684), 'SABLE CREEK HYDRO  OPS-01  REV 3', 12, (90, 90, 90), anchor='rm', bold=False)
    finish(name, im)
    return name


def build_details():
    """The things a real control room has round the panels: signs, procedures, the log, the operator's desk,
    floor markings, ceiling fittings, conduit. All world brushes (no entities, no cost while playing)."""
    # ------------------------------------------------ door wall (left, x = -160)
    im, d = tex_img('sc_exit', (256, 128), (20, 20, 20), unlit=True)
    gb.text(d, im, (128, 62), 'EXIT', 84, (60, 255, 120), squeeze=1.0)
    finish('sc_exit', im)
    on_wall_px(-193, -177, 102, 110, 'sc_exit', depth=3, side='sc_white')
    # emergency lighting unit: a battery box with two lamp heads
    im, d = tex_img('sc_emerg', (128, 64), (226, 224, 216))
    gb.text(d, im, (64, 46), 'EMERGENCY', 12, (40, 40, 40)); d.ellipse([56, 10, 72, 26], fill=(220, 40, 30))
    finish('sc_emerg', im)
    on_wall_px(-175, -159, 112, 120, 'sc_emerg', depth=4, side='sc_white')
    for y in (-176, -160):
        W(-156, y - 1.5, 115, -153, y + 1.5, 118, tex='sc_lamphead')
    # fire alarm pull station
    im, d = tex_img('sc_firepull', (64, 96), (200, 22, 22))
    gb.text(d, im, (32, 18), 'FIRE', 20, (255, 255, 255)); d.rectangle([14, 38, 50, 58], fill=(240, 240, 240))
    gb.text(d, im, (32, 48), 'PULL', 12, (200, 22, 22)); gb.text(d, im, (32, 76), 'PULL DOWN', 9, (255, 255, 255))
    finish('sc_firepull', im)
    on_wall_px(-160, -155, 44, 51.5, 'sc_firepull', depth=1.5, side='sc_red')
    # light switches and a thermostat
    im, d = tex_img('sc_switchplate', (32, 64), (232, 226, 206))
    d.rectangle([12, 22, 20, 42], fill=(250, 246, 232), outline=(170, 160, 140)); finish('sc_switchplate', im)
    for y in (-161, -158):
        on_wall_px(y, y + 2.5, 44, 49, 'sc_switchplate', depth=0.5, side='sc_white')
    im, d = tex_img('sc_tstat', (64, 64), (232, 226, 206))
    d.rectangle([14, 14, 50, 32], fill=(40, 70, 60)); gb.text(d, im, (32, 23), '21 C', 11, (150, 255, 200))
    finish('sc_tstat', im)
    on_wall_px(-62, -56, 52, 58, 'sc_tstat', depth=1.2, side='sc_white')
    # notice on the door
    safety_sign('sc_sign_auth', 'NOTICE', (24, 64, 160), (255, 255, 255), ['AUTHORIZED', 'PERSONNEL ONLY'], (256, 160))
    on_wall_px(-196, -174, 62, 76, 'sc_sign_auth', depth=0.5, x_face=-158.5, side='sc_white')

    # ------------------------------------------------ right wall (x = 160): procedures, first aid, calendar
    procedure_sheet('sc_proc1', 'UNIT 1 START-UP', [
        ('BEFORE STARTING', ['LUBE OIL PUMP, COOLING WATER PUMP: ON', 'GOVERNOR OIL PUMP, AIR COMPRESSOR: AUTO',
                             'WAIT FOR GOV OIL PRESS 300 PSI', 'BRAKES: RELEASE']),
        ('TO SPEED-NO-LOAD', ['GOVERNOR: AUTO  (OPENS GATE, HOLDS SPEED)', 'OR IN MAN: WICKET GATE RAISE TO 25 %,',
                              '   LOWER TO ABOUT 15 % PAST 80 % SPEED']),
        ('EXCITATION', ['VOLTAGE REGULATOR: AUTO', '41 FIELD BREAKER: CLOSE ABOVE 90 % SPEED', 'CHECK GENERATOR VOLTS 480 V'])])
    procedure_sheet('sc_proc2', 'SYNCHRONIZING / SHUTDOWN', [
        ('SYNCHRONIZING', ['SYNCHRONIZING: ON', 'SET SPEED SO THE POINTER CREEPS CLOCKWISE',
                           '52G: CLOSE WHILE SYNC CHECK IS LIT', 'SYNCHRONIZING: OFF']),
        ('NORMAL SHUTDOWN', ['LOWER THE GATE TO ABOUT 15 %', '52G: TRIP, THEN 41: TRIP', 'GOVERNOR: MAN, LOWER THE GATE TO 0 %',
                             'BRAKES: APPLY BELOW 30 % SPEED']),
        ('ALARMS', ['ACKNOWLEDGE, FIND AND CORRECT THE CAUSE,', 'THEN RESET. TRIPS: RESET THE 86 UNIT', 'LOCKOUT FIRST.'])])
    for (y0, y1), tex in (((-8, 20), 'sc_proc1'), ((-42, -14), 'sc_proc2')):    # start-up on the left as you face the wall
        W(159, y0 - 1, 47, 160, y1 + 1, 88, tex='sc_wood')                       # board
        on_wall_mx(y0, y1, 48.5, 87, tex, depth=1.6)
    im, d = tex_img('sc_firstaid', (128, 128), (250, 250, 250))
    d.rectangle([0, 0, 127, 127], outline=(20, 120, 60), width=8)
    d.rectangle([52, 26, 76, 102], fill=(20, 140, 70)); d.rectangle([26, 52, 102, 76], fill=(20, 140, 70))
    gb.text(d, im, (64, 116), 'FIRST AID', 13, (20, 120, 60)); finish('sc_firstaid', im)
    on_wall_mx(-222, -208, 56, 70, 'sc_firstaid', depth=4, side='sc_white')
    im, d = tex_img('sc_calendar', (128, 192), (248, 248, 244))
    d.rectangle([0, 0, 127, 70], fill=(70, 110, 150)); gb.text(d, im, (64, 36), 'NOVEMBER', 18, (255, 255, 255))
    for r in range(5):
        for c in range(7):
            d.rectangle([6 + c * 17, 80 + r * 21, 20 + c * 17, 98 + r * 21], outline=(150, 150, 150))
            gb.text(d, im, (13 + c * 17, 87 + r * 21), str(r * 7 + c + 1) if r * 7 + c < 30 else '', 8, (60, 60, 60), bold=False)
    finish('sc_calendar', im)
    on_wall_mx(-138, -126, 66, 84, 'sc_calendar', depth=0.5, side='sc_white')
    # conduit from a junction box up the wall to the ceiling, and along under it to the panels
    W(158, 22, 8, 160, 30, 16, tex='sc_metal')
    for y in (24.5, 27.5):
        W(158.4, y - 0.75, 16, 159.8, y + 0.75, 146, tex='sc_metal')
    W(100, 23.5, 144, 158.4, 28.5, 146, tex='sc_metal')

    # ------------------------------------------------ back wall (y = -232): shift log, filing cabinet, sign
    im, d = tex_img('sc_whiteboard', (512, 256), (246, 247, 248))
    d.rectangle([0, 0, 511, 255], outline=(150, 150, 150), width=6)
    gb.text(d, im, (256, 30), 'SHIFT LOG  -  UNIT 1', 26, (20, 40, 120), squeeze=0.95)
    log = ['06:00  TOOK OVER. UNIT 1 AVAILABLE.', '07:15  RIVER RISING - WATCH THE SPILLWAY.',
           '09:40  GOV OIL PUMP CYCLING (270 / 300 PSI).', '11:05  52G CLOSED, HEADWATER HELD AT 7.0 M.',
           '13:30  THRUST BRG 55 C. VIBRATION NORMAL.', 'NOTE: AVOID 25-50 % GATE ON LINE (ROUGH ZONE).']
    lines_text(d, im, 22, 76, log, 18, (30, 30, 40), gap=1.5, bold=False, squeeze=0.82)
    finish('sc_whiteboard', im)
    W(-82, -232, 44, -8, -231, 92, tex='sc_metal')
    on_wall_py(-80, -10, 46, 90, 'sc_whiteboard', depth=1.6, side='sc_metal')
    W(-80, -232, 42, -10, -228, 44, tex='sc_metal')                            # marker tray
    safety_sign('sc_sign_ear', 'WARNING', (250, 160, 20), (20, 20, 20), ['HEARING PROTECTION', 'REQUIRED IN', 'GENERATOR ROOM'], (256, 192))
    on_wall_py(-150, -132, 70, 84, 'sc_sign_ear', depth=0.5, side='sc_white')
    im, d = tex_img('sc_filing', (128, 256), (120, 124, 120))
    for k in range(4):
        y = 8 + k * 62
        d.rectangle([6, y, 121, y + 56], fill=(132, 136, 132), outline=(80, 82, 80), width=2)
        d.rectangle([44, y + 14, 84, y + 22], fill=(200, 200, 196), outline=(60, 60, 60))
        d.rectangle([54, y + 30, 74, y + 40], fill=(226, 222, 200), outline=(90, 90, 90))
    finish('sc_filing', im)
    W(-152, -232, 0, -128, -208, 54, tex='sc_paintd')
    on_wall_py(-151, -129, 1, 53, 'sc_filing', depth=0.5, y_face=-208, side='sc_paintd')
    # trash can by the desk
    world.append(prism(ngon(58, -198, 5, 10), 0, 15, 'z', 'sc_rubber'))

    # ------------------------------------------------ the operator's desk: HMI, keyboard, log book, phone, mug
    im, d = tex_img('sc_hmi', (512, 384), (10, 22, 48), unlit=True)
    d.rectangle([0, 0, 511, 28], fill=(40, 60, 110)); gb.text(d, im, (10, 14), 'SABLE CREEK HYDRO - UNIT 1 OVERVIEW', 16, (255, 255, 255), anchor='lm')
    blue, wht, grn = (70, 160, 255), (220, 230, 240), (60, 220, 120)
    d.rectangle([20, 70, 120, 110], outline=blue, width=3); gb.text(d, im, (70, 90), 'RIVER', 14, wht)
    d.line([(120, 90), (190, 90)], fill=blue, width=6); d.ellipse([190, 70, 230, 110], outline=wht, width=3); gb.text(d, im, (210, 90), 'T', 16, wht)
    d.line([(230, 90), (270, 90)], fill=wht, width=4); d.ellipse([270, 70, 310, 110], outline=wht, width=3); gb.text(d, im, (290, 90), 'G', 16, wht)
    d.line([(310, 90), (350, 90)], fill=grn, width=4); d.rectangle([350, 80, 370, 100], fill=grn); gb.text(d, im, (360, 120), '52G', 12, wht)
    d.line([(370, 90), (420, 90)], fill=grn, width=4); d.ellipse([420, 75, 446, 105], outline=wht, width=3); d.ellipse([436, 75, 462, 105], outline=wht, width=3)
    gb.text(d, im, (480, 90), 'GRID', 12, wht, anchor='lm')
    d.rectangle([20, 150, 492, 360], outline=(60, 80, 120), width=2)
    for k in range(1, 6):
        d.line([(20, 150 + k * 35), (492, 150 + k * 35)], fill=(30, 45, 80))
    gb.text(d, im, (30, 165), 'TREND  -  KW  /  HEADWATER LEVEL', 12, wht, anchor='lm')
    pts = [(20 + i * 6, 300 - 90 * (1 - math.exp(-i / 18)) + 6 * math.sin(i / 3)) for i in range(79)]
    d.line(pts, fill=grn, width=3)
    d.line([(20 + i * 6, 250 + 12 * math.sin(i / 9)) for i in range(79)], fill=blue, width=2)
    finish('sc_hmi', im)
    W(97, -149, 40, 103, -145, 44, tex='sc_knob')                              # stand
    W(84, -150, 44, 116, -146, 64, tex='sc_knob')                              # monitor
    facing_my(85, 115, -151, -150, 45, 63, 'sc_hmi')
    im, d = tex_img('sc_keyboard', (256, 96), (40, 40, 42))
    for r in range(5):
        for c in range(15):
            d.rectangle([6 + c * 16.5, 8 + r * 17, 19 + c * 16.5, 21 + r * 17], fill=(70, 70, 74))
    finish('sc_keyboard', im)
    top_art(88, 112, -170, -162, 40, 41.2, 'sc_keyboard', side='sc_knob')
    im, d = tex_img('sc_logbook', (256, 192), (248, 244, 230))
    d.line([(128, 0), (128, 191)], fill=(150, 140, 120), width=3)
    for k in range(10):
        d.line([(10, 24 + k * 16), (118, 24 + k * 16)], fill=(170, 190, 220)); d.line([(138, 24 + k * 16), (246, 24 + k * 16)], fill=(170, 190, 220))
    lines_text(d, im, 12, 20, ['UNIT 1', 'GATE 65 %', 'HW LEVEL 7.0', 'ALL NORMAL'], 11, (30, 40, 110), gap=1.45, bold=False)
    finish('sc_logbook', im)
    top_art(116, 132, -172, -160, 40, 41.2, 'sc_logbook', side='sc_white')
    im, d = tex_img('sc_phone', (64, 64), (34, 34, 36))
    for r in range(4):
        for c in range(3):
            d.rectangle([22 + c * 12, 14 + r * 11, 30 + c * 12, 21 + r * 11], fill=(190, 190, 186))
    finish('sc_phone', im)
    top_art(72, 82, -170, -160, 40, 43, 'sc_phone', side='sc_knob')
    W(72, -171, 43, 74, -159, 45, tex='sc_knob'); W(72, -171, 43, 76, -167, 44.5, tex='sc_knob')     # handset
    world.append(prism(ngon(134, -150, 1.6, 8), 40, 44.5, 'z', 'sc_white'))                       # mug

    # ------------------------------------------------ floor: anti-fatigue mat and the keep-clear line
    im, d = tex_img('sc_mat', (64, 64), (30, 30, 32))
    for k in range(0, 64, 8):
        d.line([(0, k), (63, k)], fill=(46, 46, 48), width=3)
    finish('sc_mat', im)
    W(-88, -34, 0, 88, -4, 0.5, tex='sc_mat', faces={gb.UP: ('sc_mat', (0, 0, 0.5, 0.5))})
    im, d = tex_img('sc_hazard', (128, 32), (240, 200, 20))
    for k in range(-2, 9):
        d.polygon([(k * 16, 32), (k * 16 + 8, 32), (k * 16 + 24, 0), (k * 16 + 16, 0)], fill=(20, 20, 20))
    finish('sc_hazard', im)
    W(-100, -44, 0, 100, -41, 0.3, tex='sc_hazard', faces={gb.UP: ('sc_hazard', (0, 0, 0.25, 3 / 32))})
    for x in (-100, 97):
        W(x, -41, 0, x + 3, 0, 0.3, tex='sc_hazard', faces={gb.UP: ('sc_hazard', (0, 0, 3 / 32, 0.25))})

    # ------------------------------------------------ ceiling: smoke detectors, return-air grilles, speaker
    for x, y in ((-40, -100), (100, -60)):
        world.append(prism(ngon(x, y, 3.2, 10), 146.5, 148, 'z', 'sc_white'))
    im, d = tex_img('sc_grille', (64, 64), (210, 210, 206))
    for k in range(4, 64, 6):
        d.line([(4, k), (59, k)], fill=(120, 120, 118), width=2)
    finish('sc_grille', im)
    for x, y in ((-120, -95), (120, -200)):
        W(x - 12, y - 12, 147.5, x + 12, y + 12, 148, tex='sc_white', faces={gb.DOWN: ('sc_grille', (0, 0, 24 / 64, 24 / 64))})

    # ------------------------------------------------ cabinets: hinges, danger labels on the ends
    for ci in range(3):
        x0 = gb.CX0[ci]
        for z in (20, 86):
            W(x0 + 1.2, -1.0, z, x0 + 2.4, -0.5, z + 5, tex='sc_metal')
    safety_sign('sc_sign_480', 'DANGER', (16, 16, 16), (255, 255, 255), ['HAZARDOUS VOLTAGE', '480 V', 'AUTHORIZED PERSONNEL ONLY'], (256, 192))
    W(90, 6, 66, 90.5, 26, 81, tex='sc_white', faces={(1, 0, 0): ('sc_sign_480', (-6 / (20 / 256), 81 / (15 / 192), 20 / 256, 15 / 192))})
    W(-90.5, 6, 66, -90, 26, 81, tex='sc_white', faces={(-1, 0, 0): ('sc_sign_480', (26 / (20 / 256), 81 / (15 / 192), -20 / 256, 15 / 192))})
    solid_tex('sc_lamphead', (236, 236, 228))


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
    build_details()
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
    # only the room's shell and the cabinet bodies are structural; the rest is func_detail, which the
    # visibility pass ignores (otherwise every small brush multiplies the portals it has to trace)
    def structural(b):
        if not isinstance(b, Box):
            return False
        size = [h - l for l, h in zip(b.lo, b.hi)]
        return min(size) >= 4 and size[0] * size[1] * size[2] >= 3000
    detail = [b for b in world if not structural(b)]
    world[:] = [b for b in world if structural(b)]
    ents.append(('func_detail', {}, [], detail))
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
    print(f'face triangle lists dropped ({strip_prims(bsp)} did not match their faces)')
    n = pack_bsp(bsp, C.files)
    print(f'packed {len(C.files)} files ({n / 1e6:.1f} MB); {bsp}: {os.path.getsize(bsp) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
