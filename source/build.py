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
import hlfiles as hlf                                                                # noqa: E402
from srcfiles import Content, VmfWriter, pack_bsp, pow2, fix_face_triangles, fix_tjunctions                              # noqa: E402
import hydro                                                                         # noqa: E402
import srcparts                                                                      # noqa: E402
import srcroom                                                                       # noqa: E402
from srcmdl import write_model                                                       # noqa: E402

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
HIRES = {}                    # texture -> the image its material is made from, finer than its mapping size
SURF = {'sc_floor': 'tile', 'sc_wall': 'concrete', 'sc_walld': 'concrete', 'sc_stripe': 'concrete',
        'sc_ceil': 'ceiling_tile', 'sc_rubber': 'rubber'}       # surface properties (footsteps); the rest are metal
ROOM_PROPS = []               # (model, world position, yaw): the room's furniture, prop_static
srcparts.PARTS.update(srcroom.PARTS); srcparts.MATERIALS.update(srcroom.MATERIALS); srcparts.TEXTURES.update(srcroom.TEXTURES)
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


# annunciator window lenses, kind: (lit, unlit). Backlit acrylic: the engraved legend is black either way.
ANN_LENS = {'trip': ((255, 70, 48), (176, 112, 104)), 'alarm': ((255, 180, 44), (186, 164, 112)),
            'status': ((255, 250, 232), (182, 184, 176))}
ANN_W, ANN_H = 8.4, 5.8       # window size, units


def window_texture(name, legend, kind, lit):
    """one annunciator window: a tinted acrylic lens with its legend engraved and filled black (up to three
    lines), shaded darker towards the edges of its cell; lit, the lamps behind it make a brighter middle"""
    lit_c, off_c = ANN_LENS[kind]
    w, h = 290, 200                                     # drawn at the window's shape, stored square
    base = np.array(lit_c if lit else off_c, float)
    yy, xx = np.mgrid[0:h, 0:w]
    ex = np.minimum(xx, w - 1 - xx) / 26.0; ey = np.minimum(yy, h - 1 - yy) / 26.0
    edge = np.clip(np.minimum(ex, ey), 0, 1)            # 0 at the bezel, 1 inside
    if lit:
        hot = np.exp(-(((xx - w / 2) / (0.42 * w)) ** 2 + ((yy - h / 2) / (0.42 * h)) ** 2))
        shade = 0.80 + 0.10 * edge + 0.16 * hot
        img = base[None, None, :] * shade[..., None] + 26 * hot[..., None]
    else:
        shade = 0.62 + 0.38 * edge - 0.10 * (yy / h)   # the room's light falls off down the lens
        img = base[None, None, :] * shade[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB').convert('RGBA'); d = ImageDraw.Draw(im)
    lines = legend.split('|')
    px, pitch = 38, 47
    y0 = h / 2 - pitch * (len(lines) - 1) / 2
    for k, ln in enumerate(lines):
        gb.text(d, im, (w / 2, y0 + k * pitch), ln, px, (16, 14, 12, 255), squeeze=min(0.86, 262 / (0.64 * px * len(ln))))
    TEX[name] = im.convert('RGB').resize((256, 256), Image.LANCZOS)
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


class CapPoly(Poly):
    """Poly whose front (-Y) face carries a texture placed like a Box face: (texture, (uoff, voff, sx, sy))."""

    def __init__(self, poly, front):
        super().__init__(poly.faces, poly.inside, poly.tex, poly.face_tex)
        self.front = front
        self.wall = False                 # moved onto the spillway wall by gb.to_wall: the front faces +X

    def lines(self):
        out = super().lines()
        for i, pts in enumerate(self.faces):
            p0, p1, p2 = [np.array(p, float) for p in pts]
            n = np.cross(p0 - p1, p2 - p1)
            if np.dot(n, p1 - self.inside) < 0:
                n = -n
            n = n / np.linalg.norm(n)
            tex, (uo, vo, sx, sy) = self.front
            if self.wall and n[0] > 0.999:                        # U runs along +Y there (see gb.to_wall)
                axes = f'[ 0 1 0 {hlf._fmt(uo - gb.SP_TY / sx)} ] [ 0 0 -1 {hlf._fmt(vo)} ]'
            elif not self.wall and n[1] < -0.999:
                axes = f'[ 1 0 0 {hlf._fmt(uo)} ] [ 0 0 -1 {hlf._fmt(vo)} ]'
            else:
                continue
            head = out[i].split(' [ ')[0].rsplit(' ', 1)[0]
            out[i] = f'{head} {tex} {axes} 0 {hlf._fmt(sx)} {hlf._fmt(sy)}'
        return out


def round_knob(x, z, r, y0, y1, tex='sc_knob', cap='sc_knobcap'):
    """Round knob for a brush entity: one 12-sided brush turned so that no side is axial (an axial side and
    the slanted ones next to it would leave empty cells under 1 cubic unit, which the compiler fills, and the
    knob would come out square), its face showing the cap art (pointer at 12 o'clock) centred on it."""
    poly = prism(ngon(x, z, r, 12, phase=0), y0, y1, 'y', tex)
    size = TEX[cap].size[0]
    return CapPoly(poly, (cap, face_map(x - r, z + r, size / (2 * r))))


def knob_cap_texture():
    S = 128; c = S / 2
    im = Image.new('RGB', (S, S), (16, 16, 17)); d = ImageDraw.Draw(im)
    for k in range(48):                                            # knurled skirt
        a = 2 * math.pi * k / 48
        d.line([(c + 54 * math.sin(a), c - 54 * math.cos(a)), (c + 63 * math.sin(a), c - 63 * math.cos(a))], fill=(46, 46, 48), width=2)
    d.ellipse([c - 50, c - 50, c + 50, c + 50], fill=(24, 24, 26), outline=(60, 60, 62), width=2)
    d.rounded_rectangle([c - 5, c - 58, c + 5, c - 8], radius=3, fill=(238, 236, 226))     # pointer line
    TEX['sc_knobcap'] = im


# =================================================================== models
PROPS = []                    # (door index, model, position before the wall turn, parent brush entity or None)


def prop(ci, model, pos, parent=None, name=None, skin=None):
    """A studio model on a panel. Fixed parts are prop_static; a moving part is a prop_dynamic parented to
    the brush entity that moves, which is then not drawn (the player still uses the brush). A part the
    logic changes (a target flag's skin) is a named prop_dynamic."""
    PROPS.append((ci, model, tuple(pos), parent, name, skin))
    if parent is not None:
        parent.kv['rendermode'] = '10'


def angle_matrix(p, y, r):
    """Source AngleMatrix: pitch about Y, yaw about Z, roll about X (degrees)"""
    sp, cp = math.sin(math.radians(p)), math.cos(math.radians(p))
    sy, cy = math.sin(math.radians(y)), math.cos(math.radians(y))
    sr, cr = math.sin(math.radians(r)), math.cos(math.radians(r))
    return np.array([[cp * cy, sr * sp * cy - cr * sy, cr * sp * cy + sr * sy],
                     [cp * sy, sr * sp * sy + cr * cy, cr * sp * sy - sr * cy],
                     [-sp, sr * cp, cr * cp]])


def matrix_angles(M):
    """Source MatrixAngles"""
    fwd, left, up = M[:, 0], M[:, 1], M[:, 2]
    xy = math.hypot(fwd[0], fwd[1])
    if xy > 1e-3:
        return (math.degrees(math.atan2(-fwd[2], xy)), math.degrees(math.atan2(fwd[1], fwd[0])),
                math.degrees(math.atan2(left[2], up[2])))
    return (math.degrees(math.atan2(-fwd[2], xy)), math.degrees(math.atan2(-left[0], left[1])), 0.0)


def prop_entities():
    """the props as point entities, after the wall panel's parts have been turned onto the wall"""
    out = []
    for model, pos, yaw in ROOM_PROPS:
        out.append(('prop_static', {'model': f'models/sablecreek/{model}.mdl', 'origin': ' '.join(f'{c:.3f}' for c in pos),
                                    'angles': f'0 {yaw} 0', 'solid': '0', 'disableshadows': '1'}, [], []))
    for ci, model, pos, parent, name, skin in PROPS:
        base = angle_matrix(0, 90, 0) if ci == gb.SP else np.eye(3)       # the wall panel faces +X
        if ci == gb.SP:
            pos = gb.wall_pt(pos)
        R = base if parent is None else angle_matrix(*map(float, parent.kv.get('angles', '0 0 0').split())) @ base
        ang = ' '.join(f'{a:.3f}' for a in matrix_angles(R))
        kv = {'model': f'models/sablecreek/{model}.mdl', 'origin': ' '.join(f'{c:.3f}' for c in pos), 'angles': ang,
              'solid': '0', 'disableshadows': '1'}
        if parent is None and name is None:
            out.append(('prop_static', kv, [], []))
        elif parent is None:
            kv.update({'targetname': name, 'skin': str(skin or 0), 'DisableShadows': '1'})
            out.append(('prop_dynamic', kv, [], []))
        else:
            kv.update({'parentname': parent.name, 'DisableShadows': '1', 'targetname': f'{parent.name}_mdl'})
            out.append(('prop_dynamic', kv, [], []))
    return out


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
    doors = [gb.Door(0, 'UNIT 1 GENERATOR CONTROL', 'CP-1', louvres=False), gb.Door(1, 'UNIT 1 ANNUNCIATOR', 'CP-2', louvres=False),
             gb.Door(2, 'UNIT 1 AUXILIARIES', 'CP-3', louvres=False), gb.Door(gb.SP, 'SPILLWAY GATE', 'SP-1', w=gb.SP_W, h=gb.SP_H, louvres=False)]
    nd = [0]
    door_xy = gb.door_xy

    def door_art(ci):
        """the door's texture and its mapping, for raised parts that carry the door art on their front"""
        if ci == gb.SP:
            return 'scdsp', face_map(0, gb.SP_TOP, gb.PPU)
        return f'scd{ci}', face_map(gb.CX0[ci] + 2, gb.DOOR_TOP, gb.PPU)

    def raised(ci, u, v, w, h, depth=0.5, side='sc_black'):
        """a part standing proud of the door, its front showing the door art painted under it"""
        x, z = door_xy(ci, u, v)
        world.append(Box(x - w / 2, -0.5 - depth, z - h / 2, x + w / 2, -0.5, z + h / 2, tex=side, faces={FRONT: door_art(ci)}))

    snap = lambda a: round(a * 4) / 4

    def on_grid(u, v, w, h):
        """edges on a 0.25 grid: two parallel edges closer than that split the door face into a sliver the
        compiler drops (edges of 0.2 or less), which shows as a crack"""
        u0, u1, v0, v1 = snap(u - w / 2), snap(u + w / 2), snap(v - h / 2), snap(v + h / 2)
        return (u0 + u1) / 2, (v0 + v1) / 2, u1 - u0, v1 - v0

    def plate(ci, u, v, w, h, s, px=1.15, style='bw', depth=0.5):
        """engraved laminate nameplate, screwed on: painted, then raised"""
        u, v, w, h = on_grid(u, v, w, h)
        doors[ci].plate(u, v, w, h, s, style=style, px=px)
        raised(ci, u, v, w, h, depth, 'sc_white' if style == 'wb' else 'sc_black')

    def esc_plate(ci, u, v, half):
        """square brushed-aluminium escutcheon plate, raised 0.5 off the door"""
        D = doors[ci]
        half = snap(half)
        x0, y0 = D.P(u - half, v - half); x1, y1 = D.P(u + half, v + half)
        D.d.rectangle([x0, y0, x1, y1], fill=(198, 200, 196, 255), outline=(112, 114, 110, 255), width=2)
        for k in range(int(y0) + 4, int(y1) - 3, 3):                     # brushed grain
            D.d.line([(x0 + 3, k), (x1 - 3, k)], fill=(188, 190, 186, 255) if k % 2 else (206, 208, 204, 255))
        raised(ci, u, v, 2 * half, 2 * half, 0.5, 'sc_metal')

    def title_plates(ci):
        w = doors[ci].w
        raised(ci, w / 2, 2.6, w - 16, 3.2, 0.5, 'sc_white')               # title plate (painted by Door)
        raised(ci, w - 4, 2.6, 6, 3.2, 0.5, 'sc_black')                    # cabinet number
    for ci in range(3):
        title_plates(ci)
    holes = {ci: [] for ci in (0, 1, 2, gb.SP)}
    HIT_FRONT, CLIP_FRONT, CLIP_BACK = -3.5, -3.9, -2.75

    # Round parts of brush entities run deep into the cabinet (hidden there): the compiler fills empty cells
    # under 1 cubic unit, and the cells between a small polygon's sides and its bounding box are only a
    # fraction of a square unit across, so they need the depth to survive. A hit box ends at the same depth.
    DEEP = {gb.SP: 5.5}

    def hit(ci, u, v, r, back=-0.6):
        """Invisible disc (player clip) over a control's whole plate, part of the control's own entity, so the
        player's use trace (a thin line from the crosshair) lands on it anywhere over the control. The
        clip layer in front of the panel gets a hole here (see clip_layer)."""
        x, z = door_xy(ci, u, v)
        # the hole reaches further up: you look down at the panel, so the sight line to the top of a control
        # passes the clip layer above it
        holes[ci].append((math.floor(u - r - 1.0), math.floor(v - r - 3.0), math.ceil(u + r + 1.0), math.ceil(v + r + 0.6)))
        # a square, not a disc: the compiler splits an entity's brushes by each other's planes and drops pieces
        # under 1 cubic unit, and a disc's 16 slanted planes would slice the knob into slivers. The square's
        # planes all lie outside the knob, and it covers the whole circle at any angle it is turned to.
        # Player clip, not solid: a solid one would hide the knob's faces.
        return Box(x - r, HIT_FRONT, z - r, x + r, back, z + r, tex='PCLIP')

    def clip_layer(ci, w, h):
        """Player clip over the panel face, just in front of the controls, with a hole over each one. When
        the use line misses, HL2 sweeps 32-unit boxes down from the eye and takes the first usable thing they
        touch (usually the control below the one you aimed at); the boxes hit this layer first instead."""
        hs = [(max(0, a), max(0, b), min(w, c), min(h, d)) for a, b, c, d in holes[ci]]
        us = sorted({0, w} | {a for a, _, _, _ in hs} | {c for _, _, c, _ in hs})
        vs = sorted({0, h} | {b for _, b, _, _ in hs} | {d for _, _, _, d in hs})
        free = lambda u0, v0: not any(a <= u0 < c and b <= v0 < d for a, b, c, d in hs)
        strips = []
        for j in range(len(vs) - 1):
            i = 0
            while i < len(us) - 1:
                if not free(us[i], vs[j]):
                    i += 1; continue
                k = i
                while k + 1 < len(us) - 1 and free(us[k + 1], vs[j]):
                    k += 1
                strips.append([us[i], vs[j], us[k + 1], vs[j + 1]]); i = k + 1
        merged = []                                       # join strips that line up with the one above
        for st in strips:
            up = next((m_ for m_ in merged if m_[0] == st[0] and m_[2] == st[2] and m_[3] == st[1]), None)
            if up: up[3] = st[3]
            else: merged.append(st)
        for u0, v0, u1, v1 in merged:
            x0, z0 = door_xy(ci, u0, v0); x1, z1 = door_xy(ci, u1, v1)
            world.append(Box(min(x0, x1), CLIP_FRONT, min(z0, z1), max(x0, x1), CLIP_BACK, max(z0, z1), tex='PCLIP'))

    BZ = 4.75                                          # meter bezel half size (on the 0.25 grid)

    def meter_case(x, z, Y0, tex, xl=None, xr=None, ci=0):
        """Switchboard meter: the dial behind a square black bezel 1.9 deep. (A round cut-out would put planes
        through the dial, and the compilers drop the thin wedges that leaves.)"""
        o = GR + 0.3
        W(x - o, Y0 - 0.6, z - o, x + o, Y0, z + o, tex='sc_black',
          faces={FRONT: (tex, face_map(x - GR - 0.3, z + o, DIAL / (2 * o)))})
        prop(ci, 'meter', (x, Y0, z))                 # square flange, round window, raised bezel

    def gauge_at(x, z, Y0, tex, ptr, xl=None, xr=None, ci=0):
        """Round meter facing -Y on a surface at y = Y0, and its needle (a momentary_rot_button the logic
        sets), 1 unit deep so the compilers keep it (they drop brush pieces under 1 cubic unit)."""
        meter_case(x, z, Y0, tex, ci=ci)
        place(m[ptr], needle_brushes(x, z, Y0 - 1.6, Y0 - 0.6, GR - 0.45), angles=f'{-SWEEP} 0 0', distance=2 * SWEEP)
        prop(ci, 'needle', (x, Y0 - 1.1, z), m[ptr])

    def gauge(ci, u, v, label, scales, unit, ptr, red=None, xl=None, xr=None, tex=None):
        x, z = door_xy(ci, u, v)
        if tex is None:
            tex = dial_texture(f'scg{nd[0]}', scales, unit, red); nd[0] += 1
        gauge_at(x, z, -0.5, tex, ptr, xl, xr, ci)
        plate(ci, u, v + BZ + 1.15, min(9.4, 0.55 * len(label) + 1.6), 1.4, label, px=0.8)

    def lens(col, on):
        name = f'sc_lens_{col}_{int(on)}'
        if name not in TEX:
            solid_tex(name, gb.LENS[col][1 if on else 0], unlit=on)
        return name

    def lampw(ci, u, v, name, labels):
        """indicating lamps: round lenses in black bezels. A pair (closed / open) is two entities, one of them
        always on, each with one lens lit and the other dark; a single lamp is a lit lens over a dark one."""
        lm = lamps[name]
        colors = lm['colors']
        pair = colors[1] is not None
        cols = colors if pair else (colors[0],)
        us = (u - 1.5, u + 1.5) if pair else (u,)
        for uu in us:
            x, z = door_xy(ci, uu, v)
            prop(ci, 'lamp_bezel', (x, -0.5, z))
            world.append(prism(ngon(x, z, 0.85, 12), -1.45, -0.5, 'y', lens(cols[us.index(uu)], False)))
        # one lit lens per entity: two brushes in one entity would cut each other into pieces the compiler drops
        lensp = lambda uu, col, on: prism(ngon(*door_xy(ci, uu, v), 0.9, 12, phase=0), -1.6, 28, 'y', lens(col, on))
        ents = lm['ents']
        if pair:
            place(ents[0], [lensp(us[0], cols[0], True)])
            place(ents[1], [lensp(us[1], cols[1], True)])
            plate(ci, u - 1.5, v + 2.1, 2.6, 1.0, labels[0], px=0.62); plate(ci, u + 1.5, v + 2.1, 2.6, 1.0, labels[1], px=0.62)
        else:
            place(ents[0], [lensp(u, cols[0], True)])
            plate(ci, u, v + 2.2, 5.4, 1.5, labels[0], px=0.62)

    def rot(ci, u, v, name, dial=False):
        """maintained rotary switch, 90 degrees clockwise: a bar knob, or a bigger dial with a white pointer"""
        r = sw[name]
        x, z = door_xy(ci, u, v)
        k = 1.4 if dial else 1.0
        half = round((2.6 * k + 0.4) * 4) / 4
        D = doors[ci]
        esc_plate(ci, u, v, half)
        gb.text(D.d, D.img, (u * gb.PPU, (v - half - 0.7) * gb.PPU), r['pos'][0], 0.85 * gb.PPU, (20, 20, 20, 255))
        gb.text(D.d, D.img, ((u + half + 0.3) * gb.PPU, v * gb.PPU), r['pos'][1], 0.85 * gb.PPU, (20, 20, 20, 255), anchor='lm')
        plate(ci, u, v - half - 2.4, 7.6, 1.4, r['label'], px=0.8)
        if dial:
            prop(ci, 'boss_l', (x, -1.0, z))
            pl = lambda poly: [(x + px * k, z + pz * k) for px, pz in poly]
            brushes = [prism(pl(gb.BAR), -2.6, -1.4, 'y', 'sc_knob'), prism(pl(gb.BAR_TIP), -2.6, -1.4, 'y', 'sc_white')]
        else:
            brushes = [Box(x - 0.45, -1.6, z - 1.7, x + 0.45, -0.6, z + 1.7, tex='sc_knob')]
        brushes.append(hit(ci, u, v, 2.6 * k + 0.2))
        place(r['ent'], brushes + [Box(x - 0.5, -1.6, z - 0.5, x + 0.5, -0.6, z + 0.5, tex='ORIGIN')])
        if dial:
            prop(ci, 'barknob', (x, -1.1, z), r['ent'])

    def cs_switch(ci, u, v, name):
        """breaker-type control switch, spring return: a black escutcheon engraved with its two positions
        (left = pos[0], right = pos[1]), a target window (red with the breaker closed, the pump running, AUTO
        selected or the lockout tripped; green otherwise, set by the logic) and an L handle hanging at normal.
        Its two buttons take the two halves of the plate: E on the left half turns it left, on the right half
        right; either way it springs back."""
        r = sw[name]
        x, z = door_xy(ci, u, v)
        lt, rt = r['ents']
        prop(ci, f"sb_plate_{srcparts.sb_key(r['pos'])}", (x, -0.5, z))
        prop(ci, 'sb_flag', (x, -0.5, z), name=f'{name}_flag', skin=1)
        plate(ci, u, v + 5.7, min(11.5, 0.5 * len(r['label']) + 1.6), 1.4, r['label'], px=0.75)   # below the grip
        full = hit(ci, u, v, 4.2)                       # one clip hole for the whole plate
        (x0, y0, z0), (x1, y1, z1) = full.lo, full.hi
        org = lambda: Box(x - 0.5, -2.6, z - 0.5, x + 0.5, -1.6, z + 0.5, tex='ORIGIN')
        place(lt, [Box(x0, y0, z0, x, y1, z1, tex='PCLIP'), Box(x - 2.7, -1.7, z - 0.5, x - 1.5, -0.7, z + 0.5, tex='sc_knob'), org()])
        place(rt, [Box(x, y0, z0, x1, y1, z1, tex='PCLIP'), Box(x + 1.5, -1.7, z - 0.5, x + 2.7, -0.7, z + 0.5, tex='sc_knob'), org()])
        rt.kv['rendermode'] = '10'
        prop(ci, 'sb_handle_red' if r['grip'] == 'red' else 'sb_handle', (x, -2.1, z), lt)

    def synchroscope(ci, u, v):
        x, z = door_xy(ci, u, v)
        meter_case(x, z, -0.5, 'sc_sync', ci=ci)
        place(m[dev['scope']], needle_brushes(x, z, -2.1, -1.1, GR - 0.5, tail=1.3, w=0.3), distance=360, angles='0 0 0')
        prop(ci, 'needle_scope', (x, -1.6, z), m[dev['scope']])
        plate(ci, u, v + BZ + 1.15, 9, 1.4, 'SYNCHROSCOPE', px=0.8)

    def knob_panel(ci, u, v, name, label):
        """FIRING ANGLE: a knob whose position is the manual firing angle (90 deg at the left stop, no field;
        0 deg at the right stop, full field), 300 degrees of travel."""
        x, z = door_xy(ci, u, v); D = doors[ci]
        esc_plate(ci, u, v, 4.2)
        deep = DEEP.get(ci, 8.0)
        body = round_knob(x, z, 1.9, -2.4, deep)
        start = -150 + 300 * hydro.KNOB0
        place(dl[name]['ent'], [body, hit(ci, u, v, 2.8, deep), Box(x - 0.5, -2.0, z - 0.5, x + 0.5, -1.0, z + 0.5, tex='ORIGIN')],
              angles=f'{start:.2f} 0 0')
        prop(ci, 'knob', (x, -1.5, z), dl[name]['ent'])
        plate(ci, u, v - 5.6, 9.5, 1.4, label, px=0.8)
        # scale: 90 degrees at the left stop, 0 at the right
        for k in range(11):
            a = math.radians(-150 + 30 * k)
            p0 = ((u + 3.0 * math.sin(a)) * gb.PPU, (v - 3.0 * math.cos(a)) * gb.PPU)
            p1 = ((u + (3.6 if k % 5 == 0 else 3.3) * math.sin(a)) * gb.PPU, (v - (3.6 if k % 5 == 0 else 3.3) * math.cos(a)) * gb.PPU)
            D.d.line([p0, p1], fill=(24, 24, 24, 255), width=2)
        gb.text(D.d, D.img, ((u - 3.2) * gb.PPU, (v + 3.3) * gb.PPU), '90', 0.55 * gb.PPU, (24, 24, 24, 255))
        gb.text(D.d, D.img, ((u + 3.2) * gb.PPU, (v + 3.3) * gb.PPU), '0', 0.55 * gb.PPU, (24, 24, 24, 255))

    def spring_dial(ci, u, v, name):
        """spring-return dial: held, it turns 60 degrees clockwise to its stop; let go, it springs back"""
        x, z = door_xy(ci, u, v); D = doors[ci]
        esc_plate(ci, u, v, 2.8)
        deep = DEEP.get(ci, 8.0)
        body = round_knob(x, z, 1.9, -2.8, deep)
        place(dl[name]['ent'], [body, hit(ci, u, v, 3.0, deep), Box(x - 0.5, -2.0, z - 0.5, x + 0.5, -1.0, z + 0.5, tex='ORIGIN')])
        prop(ci, 'knob', (x, -1.5, z), dl[name]['ent'])
        plate(ci, u, v + 4.4, 5.6, 1.4, dl[name]['label'], px=0.8)

    def pushbutton(ci, u, v, name, tex):
        """illuminated-style pushbutton: a round cap in a chrome bezel; the func_button is 4 units deep (most
        of it inside the cabinet) so it has room to travel 1.2 units in when pressed"""
        x, z = door_xy(ci, u, v); D = doors[ci]
        prop(ci, 'pb_bezel', (x, -0.5, z))
        b = dev['buttons'][name]
        place(b['ent'], [prism(ngon(x, z, 1.35, 12, phase=0), -2.6, 20, 'y', tex), hit(ci, u, v, 2.4, 20)], lip=f'{(20 - HIT_FRONT) - 2 - 1.2:.2f}')
        prop(ci, 'button_amber' if tex == 'sc_btn_a' else 'button_black', (x, -2.6, z), b['ent'])
        plate(ci, u, v + 3.2, 9.5, 1.4, b['label'], px=0.8)

    def frame(D, u0, v0, w, h):
        """grouping line round a block of meters or controls (no label)"""
        x0, y0 = D.P(u0, v0); x1, y1 = D.P(u0 + w, v0 + h)
        D.d.rounded_rectangle([x0, y0, x1, y1], radius=6, outline=(70, 74, 70, 255), width=2)
        D.d.rounded_rectangle([x0 + 2, y0 + 2, x1 + 2, y1 + 2], radius=6, outline=(205, 208, 204, 255), width=1)

    ROW1, ROW2, CTL = 13, 29, 50

    # ------------------------------------------- left: unit control
    D = doors[0]
    frame(D, 1.5, 5.5, 53, 32.5)
    # the generator board: turbine speed, volts, amps and kilowatts on top; firing angle, power factor, grid
    # volts and the synchroscope (with its lamps and the sync-check lamp) below
    gauge(0, 7, ROW1, 'TURBINE RPM', [(0, 150, 25, 25, 5, None)], 'RPM', 'p_speed', red=(140, 150))
    gauge(0, 17, ROW1, 'GEN VOLTS', [(0, 600, 100, 100, 20, None)], 'AC VOLTS', 'p_volts')
    gauge(0, 27, ROW1, 'GEN AMPS', [(0, 500, 100, 50, 10, None)], 'AC AMPS', 'p_amps', red=(450, 500))
    gauge(0, 37, ROW1, 'KW', [(0, 320, 80, 40, 10, None)], 'KW', 'p_kw')
    gauge(0, 7, ROW2, 'EXC FIRING ANGLE', [(0, 90, 15, 15, 5, None)], 'DEG', 'p_fa')
    gauge(0, 17, ROW2, 'POWER FACTOR', None, None, 'p_pf', tex=pf_texture('scg_pf'))
    gauge(0, 27, ROW2, 'GRID VOLTS', [(0, 600, 100, 100, 20, None)], 'AC VOLTS', 'p_gridv')   # beside the scope
    synchroscope(0, 37, ROW2)
    world.append(gb.front_box(0, 49.5, ROW2 - 1, 5, 2, -1.0, -0.5, lens_texture('sc_slmp0', ('white', 'white'), (False, False))))
    sl = Image.new('RGB', (160, 64), (0, 0, 0)); d = ImageDraw.Draw(sl)
    for x0 in (0, 96):
        d.ellipse([x0 + 6, 6, x0 + 57, 57], fill=(255, 236, 190))
    TEX['sc_slmp1'] = sl; UNLIT.add('sc_slmp1'); ADDITIVE.add('sc_slmp1')
    E.append(('func_brush', {'targetname': 'SYNCLAMPS', 'rendermode': '5', 'renderamt': '0', 'Solidity': '1'}, [],
              [gb.front_box(0, 49.5, ROW2 - 1, 5, 2, -1.3, -1.0, 'sc_slmp1')]))
    lampw(0, 49.5, ROW2 + 5, 'L_perm', ('25 PERM',))
    frame(D, 1.5, 40, 53, 44)
    cs_switch(0, 8, CTL, 'r_ss')
    cs_switch(0, 21, CTL, 'r_52'); lampw(0, 21, CTL + 9, 'LP_cb', ('CLOSED', 'OPEN'))
    cs_switch(0, 34, CTL, 'r_exc'); lampw(0, 34, CTL + 9, 'LP_exc', ('CLOSED', 'OPEN'))
    cs_switch(0, 47, CTL, 'r_gt')
    plate(0, 11, CTL + 15.6, 13, 1.4, 'WICKET GATE', px=0.8)
    spring_dial(0, 6, CTL + 21, 'k_gl'); spring_dial(0, 16, CTL + 21, 'k_gr')
    rot(0, 30, CTL + 21, 'r_br', dial=True)
    lampw(0, 30, CTL + 28.5, 'LP_brake', ('APPLIED', 'RELEASED'))
    knob_panel(0, 45, CTL + 21, 'k_fa', dl['k_fa']['label'])

    # ------------------------------------------- middle: the annunciator, the governor and the voltage regulator
    D = doors[1]
    # The annunciator: a lightbox of 24 windows, 4 rows of 6, behind a black bezel grid in a raised frame.
    # Each window is a dark lens in the world and a lit one (a func_brush the logic shows) just in front.
    AU, AV, PU, PV = 6.0, 8.3, 8.8, 6.2                # first window's centre and the pitch
    W(door_xy(1, 1.0, 0)[0], -0.9, gb.DOOR_TOP - 30.6, door_xy(1, 55.0, 0)[0], -0.5, gb.DOOR_TOP - 4.6, tex='sc_black')
    for i, w in enumerate(dev['windows']):
        c, r = i % 6, i // 6
        u, v = AU + c * PU, AV + r * PV
        world.append(gb.front_box(1, u, v, ANN_W, ANN_H, -1.4, -0.9, window_texture(f'scw{i:02d}d', w['legend'], w['kind'], False)))
        place(w['ent'], [gb.front_box(1, u, v, ANN_W, ANN_H, -1.7, -1.4, window_texture(f'scw{i:02d}l', w['legend'], w['kind'], True))])
    ann = lambda u0, v0, u1, v1, y0, tex='sc_black': world.append(Box(door_xy(1, u0, 0)[0], y0, door_xy(1, 0, v1)[1], door_xy(1, u1, 0)[0], -0.9,
                                                                      door_xy(1, 0, v0)[1], tex=tex))
    ul, ur, vt, vb = AU - PU / 2, AU + 5.5 * PU, AV - PV / 2, AV + 3.5 * PV      # the grid's outer edges
    for c in range(1, 6):                              # bezel bars between the windows
        ann(ul + c * PU - 0.2, vt, ul + c * PU + 0.2, vb, -1.9)
    for r_ in range(1, 4):
        ann(ul, vt + r_ * PV - 0.2, ur, vt + r_ * PV + 0.2, -1.9)
    ann(ul - 0.6, vt - 0.6, ur + 0.6, vt + 0.2, -2.2, 'sc_bezel'); ann(ul - 0.6, vb - 0.2, ur + 0.6, vb + 0.6, -2.2, 'sc_bezel')   # frame
    ann(ul - 0.6, vt + 0.2, ul + 0.2, vb - 0.2, -2.2, 'sc_bezel'); ann(ur - 0.2, vt + 0.2, ur + 0.6, vb - 0.2, -2.2, 'sc_bezel')
    gauge(1, 10, 37, 'GATE POS', [(0, 100, 20, 10, 2, None)], 'PERCENT', 'p_gate')          # by GOV MODE
    gauge(1, 22, 37, 'GEN FREQ', [(54, 66, 2, 1, 0.2, None)], 'Hz', 'p_hz')
    gauge(1, 34, 37, 'BUS FREQ', [(54, 66, 2, 1, 0.2, None)], 'Hz', 'p_sfreq')
    gauge(1, 46, 37, 'FIELD AMPS', [(0, 60, 10, 10, 2, None)], 'DC AMPS', 'p_exc')          # by AVR MODE
    cs_switch(1, 17, CTL, 'r_plc')
    cs_switch(1, 39, CTL, 'r_avr')
    # annunciator pushbuttons: ACKNOWLEDGE (amber), RESET and TEST (black)
    frame(D, 1.5, 58.5, 53, 11)
    for u, nm, tex in ((14, 'b_ack', 'sc_btn_a'), (28, 'b_rst', 'sc_btn_k'), (42, 'b_test', 'sc_btn_k')):
        pushbutton(1, u, 63, nm, tex)

    # ------------------------------------------- right: auxiliaries
    D = doors[2]
    frame(D, 1.5, 5.5, 53, 32.5)
    gauge(2, 7, ROW1, 'LUBE OIL PRESS', [(0, 60, 10, 10, 2, None)], 'PSI', 'p_lube', red=(0, 20), xr=5)
    gauge(2, 17, ROW1, 'CW FLOW', [(0, 100, 20, 10, 5, None)], 'GPM', 'p_cw', red=(0, 35), xl=5, xr=5)
    gauge(2, 27, ROW1, 'THRUST BRG TEMP', [(20, 100, 20, 10, 5, None)], 'DEG C', 'p_bt', red=(76, 100), xl=5, xr=5)
    gauge(2, 37, ROW1, 'SHAFT VIB', [(0, 20, 5, 5, 1, None)], 'MILS P-P', 'p_vib', red=(12, 20), xl=5)
    gauge(2, 7, ROW2, 'HPU PRESS', [(0, 400, 100, 50, 10, None)], 'PSI', 'p_opu', red=(0, 220), xr=5)
    gauge(2, 17, ROW2, 'BRAKE AIR PRESS', [(0, 150, 25, 25, 5, None)], 'PSI', 'p_air', red=(0, 50), xl=5, xr=5)
    gauge(2, 27, ROW2, 'NET HEAD', [(0, 60, 10, 10, 2, None)], 'FT', 'p_head', xl=5, xr=5)
    gauge(2, 37, ROW2, 'STATOR TEMP', [(0, 150, 25, 25, 5, None)], 'DEG C', 'p_st', red=(120, 150), xl=5)
    frame(D, 1.5, 40, 53, 22)
    for u, nm in ((8, 'r_lp'), (21, 'r_wp'), (34, 'r_hp'), (47, 'r_ac')):
        cs_switch(2, u, CTL, nm)

    for ci in (0, 1, 2):
        clip_layer(ci, gb.DOOR_W, gb.DOOR_H)

    # ------------------------------------------- spillway panel, on the wall beside the extinguisher
    w0 = len(world)
    wall_ents = []
    D = doors[gb.SP]
    title_plates(gb.SP)
    for nm in ('p_hw', 'p_rq', 'p_spill', 'r_sp', 'k_sl', 'k_sr'):
        wall_ents.append(m[nm])
    gauge(gb.SP, 7, 12, 'FOREBAY LEVEL', [(0, 35, 5, 5, 1, None)], 'FT', 'p_hw', red=(29.5, 35), xl=5.5, xr=6.5)
    gauge(gb.SP, 20, 12, 'INFLOW', [(0, 120, 20, 20, 5, None)], 'CFS', 'p_rq', xl=6.5, xr=6.5)
    gauge(gb.SP, 33, 12, 'GATE POS', [(0, 4, 1, 1, 0.25, None)], 'FT', 'p_spill', xl=6.5, xr=5.5)
    rot(gb.SP, 8, 32, 'r_sp', dial=True)
    plate(gb.SP, 27.5, 26.6, 13, 1.4, 'GATE', px=0.8)
    spring_dial(gb.SP, 22, 32, 'k_sl'); spring_dial(gb.SP, 33, 32, 'k_sr')
    W(-1, 0, gb.SP_TOP - gb.SP_H - 1, gb.SP_W + 1, 6, gb.SP_TOP + 1, tex='sc_paintd', scale=0.5)
    TEX['scdsp'] = D.img.convert('RGB')
    W(0, -0.5, gb.SP_TOP - gb.SP_H, gb.SP_W, 0, gb.SP_TOP, tex='sc_paintd', faces={FRONT: ('scdsp', face_map(0, gb.SP_TOP, gb.PPU))})
    clip_layer(gb.SP, gb.SP_W, gb.SP_H)
    world[w0:] = [gb.to_wall(b) for b in world[w0:]]
    for e in wall_ents:
        e.brushes = [gb.to_wall(b) for b in e.brushes]
        for b in e.brushes:
            if isinstance(b, CapPoly):
                b.wall = True
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

    # cabinet bodies: frame round the door with a real gap, joints, hinges, latch, vents, top cap
    for ci, Dr in enumerate(doors[:3]):
        cabinet_body(ci, Dr)

    # door art -> one texture per door
    for ci, Dr in enumerate(doors[:3]):
        TEX[f'scd{ci}'] = Dr.img.convert('RGB')
        x0 = gb.CX0[ci] + 2
        W(x0, -0.5, gb.DOOR_TOP - gb.DOOR_H, x0 + gb.DOOR_W, 0, gb.DOOR_TOP, tex='sc_paintd',
          faces={FRONT: (f'scd{ci}', face_map(x0, gb.DOOR_TOP, gb.PPU))})


def prism_x(poly_yz, x0, x1, tex):
    """prism along X over a convex polygon in (y, z)"""
    n = len(poly_yz)
    faces = [((x0, *poly_yz[k]), (x1, *poly_yz[k]), (x1, *poly_yz[(k + 1) % n])) for k in range(n)]
    faces.append(tuple((x0, *poly_yz[k]) for k in range(3)))
    faces.append(tuple((x1, *poly_yz[k]) for k in range(3)))
    cy = sum(p[0] for p in poly_yz) / n; cz = sum(p[1] for p in poly_yz) / n
    return Poly(faces, ((x0 + x1) / 2, cy, cz), tex, None)


def cabinet_body(ci, D):
    """The cabinet front round its door: a frame flush with the door and a 0.3 gap all round it with a dark
    gasket at the bottom, black joints between cabinets, two barrel hinges, a latch handle, stamped vents
    with real slats at the foot of the door, and a top cap. Everything is at least 0.25 thick and over 1
    cubic unit, so the compiler keeps it."""
    x0 = gb.CX0[ci]
    xd0, xd1 = x0 + 2, x0 + 2 + gb.DOOR_W
    zd0, zd1 = gb.DOOR_TOP - gb.DOOR_H, gb.DOOR_TOP
    g = 0.3
    paint = lambda *a: W(*a, tex='sc_paintd', scale=0.5, faces={FRONT: ('sc_paint', (0, 0, 0.5, 0.5))})
    xl = x0 + (0 if ci == 0 else 0.15); xr = x0 + 60 - (0 if ci == 2 else 0.15)
    paint(xl, -0.5, 6, xd0 - g, 0, 108)                                     # frame
    paint(xd1 + g, -0.5, 6, xr, 0, 108)
    paint(xd0 - g, -0.5, zd1 + g, xd1 + g, 0, 108)
    paint(xd0 - g, -0.5, 6, xd1 + g, 0, zd0 - g)
    for a in ((xd0 - g, -0.25, zd0 - g, xd0, 0, zd1 + g), (xd1, -0.25, zd0 - g, xd1 + g, 0, zd1 + g),
              (xd0, -0.25, zd1, xd1, 0, zd1 + g), (xd0, -0.25, zd0 - g, xd1, 0, zd0)):
        W(*a, tex='sc_black')                                                # gasket in the gap
    if ci > 0:
        W(x0 - 0.15, -0.5, 6, x0 + 0.15, 0, 108, tex='sc_black')            # joint with the cabinet to the left
    for z in (18, 90):                                                       # hinges on the left edge
        prop(ci, 'hinge', (xd0 - 0.15, -0.75, z + 3))
    prop(ci, 'latch', (xd1 - 3.0, -0.5, 55))                                 # latch: escutcheon and swing handle
    for u0 in (6, 34):                                                       # vents: dark opening, six slats
        x_a, x_b = xd0 + u0, xd0 + u0 + 16
        for k in range(6):
            zt = gb.DOOR_TOP - (85.6 + k * 1.5)
            world.append(prism_x([(-0.5, zt), (-0.5, zt - 1.1), (-1.15, zt - 1.1)], x_a, x_b, 'sc_paintd'))
    W(x0 - (0.6 if ci == 0 else 0), -1.0, 108, x0 + 60 + (0.6 if ci == 2 else 0), 32.6, 109.6,       # top cap
      tex='sc_paintd', scale=0.5, faces={FRONT: ('sc_paint', (0, 0, 0.5, 0.5))})
    # vent openings on the door art
    for u0 in (6, 34):
        x_0, y_0 = D.P(u0, 85.3); x_1, y_1 = D.P(u0 + 16, 94.6)
        D.d.rectangle([x_0, y_0, x_1, y_1], fill=(30, 32, 30, 255))


# =================================================================== room finishes
def _field(rng, shape, cells, order=Image.BICUBIC):
    """smooth random field in -1..1: noise at `cells` resolution, enlarged to `shape` (h, w)"""
    a = (rng.random((cells[0], cells[1])) * 255).astype(np.uint8)
    im = Image.fromarray(a, 'L').resize((shape[1], shape[0]), order)
    return np.asarray(im, float) / 127.5 - 1


def block_texture(rgb, seed):
    """painted concrete block, running bond: two 16 in blocks by four 8 in courses, 1024 px. The joints are
    tooled grooves (shaded above, lit below, the paint a little darker in them); the faces carry the block's
    pores under the paint and a faint mottle."""
    S = 1024; BW, BH, J = 512, 256, 6.5                # block, course and half the joint, px
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:S, 0:S].astype(float)
    row = (yy // BH).astype(int)
    dy = (yy + BH / 2) % BH - BH / 2                    # distance below the nearest bed joint
    xo = xx + (row % 2) * (BW / 2)
    dx = (xo + BW / 2) % BW - BW / 2                    # distance right of the nearest head joint
    gh = np.clip(1 - np.abs(dy) / J, 0, 1); gv = np.clip(1 - np.abs(dx) / J, 0, 1)
    gh, gv = gh * gh * (3 - 2 * gh), gv * gv * (3 - 2 * gv)
    groove = np.maximum(gh, gv)
    lip = np.clip(1 - np.abs(np.abs(dy) - J) / 3.0, 0, 1) * np.sign(dy)        # light on the lower lip, shade on the upper
    shade = 1 - 0.13 * groove + 0.07 * lip * (1 - gv)
    block = (row * 7 + (xo // BW).astype(int) * 13) % 11                         # each block a hair lighter or darker
    shade *= 1 + 0.012 * (block / 5.0 - 1)
    shade *= 1 + 0.007 * _field(rng, (S, S), (9, 9)) + 0.008 * _field(rng, (S, S), (64, 64))
    pores = (rng.random((S, S)) < 0.012).astype(float)
    pores = np.asarray(Image.fromarray((pores * 255).astype(np.uint8), 'L').resize((S // 2, S // 2), Image.BILINEAR)
                       .resize((S, S), Image.BILINEAR), float) / 255
    shade *= 1 - 0.55 * pores * (1 - groove)
    shade += rng.normal(0, 0.008, (S, S))
    return Image.fromarray(np.clip(np.array(rgb, float)[None, None, :] * shade[..., None], 0, 255).astype(np.uint8), 'RGB')


def floor_texture():
    """vinyl composition tile, 12 in, two quiet tones laid checkerwise with the grain turned: 2 x 2 tiles, 1024 px"""
    S, T = 1024, 512
    rng = np.random.default_rng(21)
    img = np.zeros((S, S, 3))
    for i in range(2):
        for j in range(2):
            base = np.array((174, 172, 162) if (i + j) % 2 else (152, 152, 146), float)
            streak = _field(rng, (T, T), (160, 10))                    # long streaks along x
            fleck = _field(rng, (T, T), (128, 128), Image.BILINEAR)
            if (i + j) % 2:
                streak = streak.T
            tone = 1 + 0.035 * streak + 0.025 * np.clip(fleck * 2.5, -1, 1) + rng.normal(0, 0.012, (T, T))
            img[i * T:(i + 1) * T, j * T:(j + 1) * T] = base[None, None, :] * tone[..., None]
    wear = 1 + 0.012 * _field(rng, (S, S), (7, 7))
    img *= wear[..., None]
    for p in (0, T):                                                    # joints: a dark hairline and a faint light edge
        for k, f in ((0, 0.62), (1, 0.78), (2, 1.05), (S - 1, 0.78)):
            q = (p + k) % S
            img[q, :, :] *= f; img[:, q, :] *= f
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')


def ceiling_texture():
    """2 x 4 ft lay-in acoustic tile in a white grid: fissured mineral fibre, 512 x 1024 px"""
    Wd, Hd = 512, 1024
    rng = np.random.default_rng(31)
    im = Image.new('RGB', (Wd, Hd), (232, 230, 222)); d = ImageDraw.Draw(im)
    for _ in range(2200):                                               # pinholes
        x, y = rng.integers(14, Wd - 14), rng.integers(14, Hd - 14)
        g = int(rng.integers(184, 208)); d.point((x, y), fill=(g, g - 1, g - 6)); d.point((x + 1, y), fill=(g, g - 1, g - 6))
    for _ in range(150):                                                # short fissures
        x, y, a, ln = rng.integers(16, Wd - 16), rng.integers(16, Hd - 16), rng.random() * math.pi, rng.integers(4, 12)
        g = int(rng.integers(176, 200))
        d.line([(x, y), (x + ln * math.cos(a), y + ln * math.sin(a))], fill=(g, g - 1, g - 6), width=int(rng.choice((1, 1, 2))))
    a = np.asarray(im, float) + rng.normal(0, 2.0, (Hd, Wd, 1))
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB'); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, Wd - 1, Hd - 1], outline=(176, 174, 166), width=11)     # the tile's shadowed edge in the grid
    d.rectangle([0, 0, Wd - 1, Hd - 1], outline=(244, 243, 238), width=8)      # T-bar, half on each tile
    return im


def door_texture():
    """hollow metal door, 36 x 84 in, painted: shaded edges, a narrow wire-glass lite on the latch side and a
    stainless kick plate; 96 x 224 mapping size, drawn 8 times finer"""
    K = 8; Wd, Hd = 96 * K, 224 * K
    rng = np.random.default_rng(41)
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(float)
    tone = 1 + 0.018 * _field(rng, (Hd, Wd), (6, 60)) + rng.normal(0, 0.006, (Hd, Wd)) - 0.05 * (yy / Hd)
    edge = np.minimum(np.minimum(xx, Wd - 1 - xx), np.minimum(yy, Hd - 1 - yy))
    tone *= 0.82 + 0.18 * np.clip(edge / 10, 0, 1)
    im = Image.fromarray(np.clip(np.array((112, 130, 142), float)[None, None, :] * tone[..., None], 0, 255).astype(np.uint8), 'RGB')
    d = ImageDraw.Draw(im)
    U = 2 * K                                                            # px per unit
    # lite: 5 x 22 in clear, in a frame, wire glass
    x0, y0, x1, y1 = Wd - 16.5 * U, 18 * U, Wd - 7.5 * U, 50 * U
    d.rectangle([x0 - 1.2 * U, y0 - 1.2 * U, x1 + 1.2 * U, y1 + 1.2 * U], fill=(60, 72, 80), outline=(40, 48, 54), width=3)
    for y in range(int(y0), int(y1)):
        g = 22 + 26 * (y - y0) / (y1 - y0)
        d.line([(x0, y), (x1, y)], fill=(int(g), int(g + 6), int(g + 10)))
    step = 1.0 * U
    k = -int((y1 - y0) / step) - 2
    while x0 + k * step < x1:                                            # diamond wire
        for sgn in (1, -1):
            xa = x0 + k * step if sgn > 0 else x1 - k * step
            d.line([(xa, y0), (xa + sgn * (y1 - y0), y1)], fill=(92, 100, 104), width=1)
        k += 1
    d.rectangle([x1 + 1, y0 - 1.2 * U, x1 + 1.2 * U, y1 + 1.2 * U], fill=(60, 72, 80))    # the wires end at the frame
    d.rectangle([x0 - 1.2 * U, y0 - 1.2 * U, x0 - 1, y1 + 1.2 * U], fill=(60, 72, 80))
    d.rectangle([x0 - 1.2 * U, y0 - 1.2 * U, x1 + 1.2 * U, y1 + 1.2 * U], outline=(40, 48, 54), width=3)
    # kick plate, 10 in
    ky = Hd - 14 * U
    kp = np.asarray(im, float)
    kp[int(ky):Hd - 2 * K, 2 * K:Wd - 2 * K] = (np.array((172, 174, 172), float)[None, None, :]
        * (1 + 0.05 * _field(rng, (Hd - 2 * K - int(ky), Wd - 4 * K), (4, 120)))[..., None])
    im = Image.fromarray(np.clip(kp, 0, 255).astype(np.uint8), 'RGB'); d = ImageDraw.Draw(im)
    d.line([(2 * K, ky), (Wd - 2 * K, ky)], fill=(214, 216, 214), width=2)
    for sx in (4 * K, Wd - 4 * K):
        for sy in (ky + 2 * K, Hd - 4 * K):
            d.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], fill=(120, 122, 120))
    return im


def room_finishes():
    """the room's surfaces at 24-32 texels a unit, in place of the GoldSrc map's 128 px ones"""
    HIRES['sc_wall'] = block_texture((198, 204, 186), 3)        # upper wall: pale green
    TEX['sc_walld'] = TEX['sc_wall']; HIRES['sc_walld'] = block_texture((126, 146, 124), 4)   # dado: darker green
    solid_tex('sc_stripe', (66, 84, 68))
    TEX['sc_floor'] = Image.new('RGB', (128, 128)); HIRES['sc_floor'] = floor_texture()
    TEX['sc_ceil'] = Image.new('RGB', (64, 128)); HIRES['sc_ceil'] = ceiling_texture()
    TEX['scdoor'] = Image.new('RGB', (96, 224)); HIRES['scdoor'] = door_texture()
    TEX['sc_doorf'] = gb.noise(Image.new('RGB', (32, 32), (62, 76, 86)), 3)


def build_room():
    gb.build_room()
    gb.ents[:] = [e for e in gb.ents if e['classname'] == 'worldspawn']
    world[:] = [b for b in world if not (isinstance(b, Box) and any(t == 'sc_sld' for t, _ in b.faces.values()))]   # no poster
    old = lambda b: isinstance(b, Box) and ((b.lo[2] == 108 and b.hi[2] == 109) or                  # cap, latch
                                            (b.tex == 'sc_metal' and b.lo[1] == -1.6 and b.lo[2] == 50))
    world[:] = [b for b in world if not old(b)]
    # the furniture is studio models, not blocks: out go the old door, extinguisher, clock, desk and chair
    gone = lambda b: isinstance(b, Box) and (b.tex in ('sc_door', 'sc_extg', 'sc_deskm', 'sc_wood', 'sc_chair')
                                             or any(t == 'sc_clock' for t, _ in b.faces.values())
                                             or (b.tex == 'sc_metal' and b.lo in ((101, -188, 0), (-160, -207, 98), (-158.5, -178, 44))))
    world[:] = [b for b in world if not gone(b)]
    room_finishes()
    # walls: a painted dado five courses high, a stripe, and the lighter wall above
    walls = [b for b in world if isinstance(b, Box) and b.tex == 'sc_wall']
    world[:] = [b for b in world if b not in walls]
    DADO = 5 * 128 / 12                                 # five 8 in courses (the texture's four are 128/3 units)
    for b in walls:
        (x0, y0, z0), (x1, y1, z1) = b.lo, b.hi
        for za, zb, t in ((z0, DADO, 'sc_walld'), (DADO, DADO + 1.6, 'sc_stripe'), (DADO + 1.6, z1, 'sc_wall')):
            world.append(Box(x0, y0, za, x1, y1, zb, tex=t, scale=1 / 3))
    X0 = -160
    # door: 36 x 84 in hollow metal in a steel frame, lever and three hinges
    W(X0, -211, 0, X0 + 1.5, -163, 112, tex='sc_doorf', faces={(1, 0, 0): ('scdoor', (211 / 0.5, 112 / 0.5, 0.5, 0.5))})
    for a in ((X0, -213.7, 0, X0 + 2.3, -211, 114.7), (X0, -163, 0, X0 + 2.3, -160.3, 114.7), (X0, -211, 112, X0 + 2.3, -163, 114.7)):
        W(*a, tex='sc_doorf')
    ROOM_PROPS.append(('lever', (X0 + 1.5, -166.7, 48), 90))
    for z in (13, 56, 99):
        ROOM_PROPS.append(('butt_hinge', (X0 + 1.5, -211, z), 90))
    ROOM_PROPS.append(('extinguisher', (X0, -137, 29), 90))
    ROOM_PROPS.append(('clock', (X0, -32, 112), 90))
    ROOM_PROPS.append(('desk', (105, -158, 0), 0))
    ROOM_PROPS.append(('chair', (101, -191, 0), 14))
    for a in ((X0, -142, 28, X0 + 9, -132, 51), (68, -176, 0, 142, -140, 40), (91, -202, 0, 112, -180, 42)):
        W(*a, tex='PCLIP')                               # the models have no collision of their own
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
    gb.PPU = 16                                        # door art: 16 texels per unit, so nameplates read
    m, P, dev = hydro.build()
    gb.room_textures(); gb.button_textures(); synchro_texture(); knob_cap_texture()
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
    C.tool('tools/toolsplayerclip', ['%compileplayerclip'])
    # materials: every texture, at power-of-two sizes; offsets and scales are rescaled to match
    factors = {}
    for name, img in TEX.items():
        if name.startswith('+'):
            continue                                   # the GoldSrc map's animated lamps
        im = pow2(HIRES.get(name, img), 2048 if name.startswith('scd') else 1024)
        factors[name] = (im.size[0] / img.size[0], im.size[1] / img.size[1])
        mat = f'sablecreek/{name.lower()}'
        if name in ADDITIVE:
            C.material(mat, im, 'UnlitGeneric', {'$additive': 1})
        elif name in UNLIT:
            C.material(mat, im, 'UnlitGeneric', compress=im.size[0] * im.size[1] >= 128 * 128)
        else:
            C.material(mat, im, 'LightmappedGeneric', {'$surfaceprop': SURF.get(name, 'metal')}, compress=im.size[0] * im.size[1] >= 128 * 128)

    def tex(name):
        if name == 'ORIGIN':
            return 'TOOLS/TOOLSORIGIN', 1, 1
        if name in ('NODRAW', 'PCLIP'):
            return {'NODRAW': 'TOOLS/TOOLSNODRAW', 'PCLIP': 'TOOLS/TOOLSPLAYERCLIP'}[name], 1, 1
        fu, fv = factors[name]
        return f'SABLECREEK/{name.upper()}', fu, fv
    snd = os.path.join(game, 'sound', 'sablecreek')
    make_sounds(snd)
    for f in sorted(os.listdir(snd)):
        C.files[f'sound/sablecreek/{f}'] = open(os.path.join(snd, f), 'rb').read()

    # studio models: their materials (solid colours) and files, then the props
    for name, (rgb, unlit) in srcparts.MATERIALS.items():
        im = Image.new('RGB', (16, 16), rgb)
        C.material(f'models/sablecreek/{name}', im, 'UnlitGeneric' if unlit else 'VertexLitGeneric', {'$model': 1} if unlit else {})
    for name, make in srcparts.TEXTURES.items():
        C.material(f'models/sablecreek/{name}', make(), 'VertexLitGeneric', compress=True)
    for model in sorted({p_[1] for p_ in PROPS} | {p_[0] for p_ in ROOM_PROPS}):
        files = write_model(f'models/sablecreek/{model}.mdl', srcparts.PARTS[model](), skins=srcparts.SKINS.get(model, ()))
        for rel, data in files.items():
            C.add(rel, data)
    ents = list(E)
    for e in m.ents:
        ents.append((e.cls, {k: str(v) for k, v in e.kv.items()}, e.outputs, e.brushes))
    props = prop_entities()
    ents += props
    print(f'{sum(1 for p_ in props if p_[0] == "prop_static")} prop_static, {sum(1 for p_ in props if p_[0] == "prop_dynamic")} prop_dynamic')
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
    print(f'T-junctions: {fix_tjunctions(bsp)} corners added to faces')
    bad, nonconvex = fix_face_triangles(bsp)
    print(f'face triangles: compiler lists replaced ({bad} were short); {nonconvex} non-convex faces ear-clipped, the rest fans')
    n = pack_bsp(bsp, C.files)
    print(f'packed {len(C.files)} files ({n / 1e6:.1f} MB); {bsp}: {os.path.getsize(bsp) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
