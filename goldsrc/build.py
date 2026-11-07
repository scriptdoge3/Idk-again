"""
Build Sable Creek Hydro for plain Half-Life (GoldSrc).

  python3 build.py            -> out/sablecreek.map, out/sablecreek.wad, out/sablecreek.rad,
                                 out/sound/sablecreek/*.wav
Then compile with any Half-Life compile tools (SDHLT / VHLT):
  hlcsg -wadinclude sablecreek sablecreek ; hlbsp sablecreek ; hlvis sablecreek ;
  hlrad -extra sablecreek

Scale: 1 unit = 1 inch for the player; the room is built about 1.3x real size like
Half-Life's own maps, so a 2.1 m cabinet is 108 units tall.
"""
import math, os, sys, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from hlfiles import Box, Poly, prism, ngon, face_map, face_map_up, write_map, write_wad, write_wav
from plant import build as build_logic, ANN, KW, TRIP_WINDOWS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
FONT_B = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
FONT_R = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'
FRONT, BACK, UP, DOWN = (0, -1, 0), (0, 1, 0), (0, 0, 1), (0, 0, -1)
PPU = 8                               # door art texels per unit
CX0 = [-90, -30, 30]                  # cabinet left edges
DOOR_TOP, DOOR_H, DOOR_W = 105, 96, 56
TEX = {}
ESC = (226, 222, 208, 255)            # switch escutcheon plates: cream, so the black handles read
TEXLIGHT, LIGHT_A, LIGHT_B, LIGHT_C = (int(x) for x in os.environ.get('SC_LIGHTS', '200 130 90 60').split())
R = random.Random(7)


# =================================================================== art helpers
def font(px, bold=True):
    return ImageFont.truetype(FONT_B if bold else FONT_R, max(6, int(px)))


def text(d, img, xy, s, px, fill, anchor='mm', bold=True, squeeze=0.86):
    """Condensed text: render wide, squeeze horizontally, paste."""
    f = font(px * 2, bold)
    l, t, r, b = f.getbbox(s)
    w, h = max(1, r - l), max(1, b - t)
    tmp = Image.new('RGBA', (w + 4, h + 4), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((2 - l, 2 - t), s, font=f, fill=fill)
    tmp = tmp.resize((max(1, int((w + 4) * squeeze / 2)), max(1, int((h + 4) / 2))), Image.Resampling.LANCZOS)
    x, y = xy
    if anchor[0] == 'm': x -= tmp.width / 2
    elif anchor[0] == 'r': x -= tmp.width
    if anchor[1] == 'm': y -= tmp.height / 2
    elif anchor[1] == 'b': y -= tmp.height
    img.alpha_composite(tmp, (int(round(x)), int(round(y))))


def noise(img, amt, seed=1):
    a = np.asarray(img).astype(np.int16)
    rng = np.random.default_rng(seed)
    n = rng.integers(-amt, amt + 1, size=a.shape[:2])[..., None]
    a[..., :3] = np.clip(a[..., :3] + n, 0, 255)
    return Image.fromarray(a.astype(np.uint8), img.mode)


def solid(name, rgb, size=(16, 16), n=0):
    im = Image.new('RGB', size, rgb)
    TEX[name] = noise(im, n) if n else im


# =================================================================== room textures
def room_textures():
    solid('sc_black', (22, 22, 22), n=2)
    solid('sc_red', (200, 32, 22))
    solid('sc_needle', (15, 15, 15))
    solid('ORIGIN', (230, 120, 20))
    solid('sc_paint', (163, 168, 165), (64, 64), n=4)
    solid('sc_paintd', (128, 133, 130), (64, 64), n=4)
    solid('sc_rubber', (36, 36, 34), (32, 32), n=3)
    solid('sc_metal', (150, 156, 153), (32, 32), n=6)
    solid('sc_deskm', (128, 132, 126), (32, 32), n=3)
    solid('sc_chair', (45, 48, 54), (32, 32), n=4)
    solid('sc_extg', (190, 24, 24), (32, 32), n=4)
    solid('sc_door', (104, 122, 134), (64, 64), n=3)
    # vinyl composition tile, two tones
    im = Image.new('RGB', (128, 128))
    d = ImageDraw.Draw(im)
    for i in range(2):
        for j in range(2):
            d.rectangle([i * 64, j * 64, i * 64 + 63, j * 64 + 63], fill=(156, 146, 124) if (i + j) % 2 else (108, 101, 86))
    im = noise(im, 9, 3)
    d = ImageDraw.Draw(im)
    for p in (0, 64):
        d.line([(p, 0), (p, 127)], fill=(60, 54, 44)); d.line([(0, p), (127, p)], fill=(60, 54, 44))
    TEX['sc_floor'] = im
    # painted concrete block
    im = Image.new('RGB', (128, 128), (170, 180, 160))
    d = ImageDraw.Draw(im)
    for r in range(4):
        off = 32 if r % 2 else 0
        for c in range(-1, 3):
            x = c * 64 + off
            d.rectangle([x, r * 32, x + 63, r * 32 + 31], outline=(128, 136, 120), width=2)
    TEX['sc_wall'] = noise(im, 6, 4)
    im = Image.new('RGB', (64, 128), (222, 220, 212))
    im = noise(im, 10, 5)
    d = ImageDraw.Draw(im); d.rectangle([0, 0, 63, 127], outline=(240, 239, 233), width=3)
    TEX['sc_ceil'] = im
    im = Image.new('RGB', (64, 128), (255, 252, 240))
    d = ImageDraw.Draw(im)
    for y in range(0, 128, 4):
        for x in range((y // 4) % 2 * 2, 64, 4):
            d.point((x, y), fill=(222, 222, 214))
    d.rectangle([0, 0, 63, 127], outline=(236, 236, 230), width=3)
    TEX['sc_light'] = im
    im = Image.new('RGB', (64, 64), (118, 88, 60)); TEX['sc_wood'] = noise(im, 7, 6)
    # wall clock
    im = Image.new('RGBA', (128, 128), (25, 25, 25, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([6, 6, 121, 121], fill=(240, 238, 230, 255))
    for i in range(12):
        a = i / 12 * 2 * math.pi
        d.line([(64 + 50 * math.sin(a), 64 - 50 * math.cos(a)), (64 + 44 * math.sin(a), 64 - 44 * math.cos(a))], fill=(20, 20, 20, 255), width=4)
    d.line([(64, 64), (64 + 26 * math.sin(4.2), 64 - 26 * math.cos(4.2))], fill=(20, 20, 20, 255), width=6)
    d.line([(64, 64), (64 + 40 * math.sin(1.0), 64 - 40 * math.cos(1.0))], fill=(20, 20, 20, 255), width=4)
    TEX['sc_clock'] = im.convert('RGB')
    # single-line diagram poster
    im = Image.new('RGBA', (256, 192), (242, 240, 232, 255))
    d = ImageDraw.Draw(im)
    text(d, im, (128, 12), 'SABLE CREEK HYDRO  -  SINGLE-LINE DIAGRAM', 11, (20, 20, 20, 255))
    d.ellipse([106, 140, 150, 184], outline=(20, 20, 20, 255), width=2); text(d, im, (128, 162), 'G', 16, (20, 20, 20, 255))
    d.line([(128, 140), (128, 118)], fill=(20, 20, 20, 255), width=2); d.rectangle([120, 102, 136, 118], outline=(20, 20, 20, 255), width=2)
    text(d, im, (170, 110), '52G', 10, (20, 20, 20, 255)); d.line([(128, 102), (128, 90)], fill=(20, 20, 20, 255), width=2)
    d.line([(60, 90), (200, 90)], fill=(20, 20, 20, 255), width=4); text(d, im, (60, 82), '480 V BUS', 8, (20, 20, 20, 255), anchor='lm')
    for cy in (66, 50):
        d.ellipse([116, cy - 12, 140, cy + 12], outline=(20, 20, 20, 255), width=2)
    d.line([(128, 90), (128, 78)], fill=(20, 20, 20, 255), width=2); d.line([(128, 38), (128, 26)], fill=(20, 20, 20, 255), width=2)
    text(d, im, (190, 58), '500 kVA 480/12470', 8, (20, 20, 20, 255)); text(d, im, (128, 186), '300 kVA  480 V  72 POLE  100 RPM', 8, (20, 20, 20, 255))
    TEX['sc_sld'] = im.convert('RGB')


# =================================================================== door art
class Door:
    def __init__(self, ci, title, tag):
        self.ci = ci
        self.img = Image.new('RGBA', (DOOR_W * PPU, DOOR_H * PPU), (163, 168, 165, 255))
        self.img = noise(self.img, 4, 10 + ci)
        self.d = ImageDraw.Draw(self.img)
        self.plate(28, 2.6, 40, 3.2, title, style='wb', px=2.0)
        self.plate(52, 2.6, 6, 3.2, tag, px=1.7)
        # louvres
        for k in range(6):
            for x0 in (6, 34):
                y = 86 + k * 1.4
                self.d.rounded_rectangle([x0 * PPU, y * PPU, (x0 + 16) * PPU, (y + 0.6) * PPU], radius=3, fill=(40, 42, 40, 255))
        self.d.rectangle([0, 0, self.img.width - 1, self.img.height - 1], outline=(70, 74, 72, 255), width=3)

    def P(self, u, v):
        return u * PPU, v * PPU

    def plate(self, u, v, w, h, s, style='bw', px=1.15):
        bg, fg = {'bw': ((18, 18, 18, 255), (240, 238, 228, 255)), 'wb': ((236, 234, 226, 255), (18, 18, 18, 255)),
                  'red': ((180, 20, 24, 255), (250, 246, 238, 255)), 'yel': ((233, 182, 28, 255), (18, 18, 18, 255))}[style]
        x0, y0 = self.P(u - w / 2, v - h / 2); x1, y1 = self.P(u + w / 2, v + h / 2)
        self.d.rounded_rectangle([x0 + 1, y0 + 1, x1 + 1, y1 + 1], radius=3, fill=(60, 62, 60, 140))
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=3, fill=bg)
        lines = s.split('|')
        for i, ln in enumerate(lines):
            yy = (v + (i - (len(lines) - 1) / 2) * px * 1.15) * PPU
            text(self.d, self.img, ((u) * PPU, yy), ln, px * PPU, fg)

    def section(self, u0, v0, w, h, label):
        x0, y0 = self.P(u0, v0); x1, y1 = self.P(u0 + w, v0 + h)
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=6, outline=(70, 74, 70, 255), width=2)
        self.d.rounded_rectangle([x0 + 2, y0 + 2, x1 + 2, y1 + 2], radius=6, outline=(205, 208, 204, 255), width=1)
        lw = 1.2 + len(label) * 0.62
        self.plate(u0 + 1 + lw / 2, v0, lw, 1.8, label, px=1.0)

    def edge_scale(self, u, v, lo, hi, major, minor, unit, red=None, fmt=None):
        """Edgewise meter face: 4.6 x 17 units, scale from v+7 (lo) to v-7 (hi)."""
        x0, y0 = self.P(u - 2.3, v - 8.5); x1, y1 = self.P(u + 2.3, v + 8.5)
        self.d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=(16, 16, 16, 255))
        self.d.rectangle([x0, y0, x1, y1], fill=(242, 238, 226, 255))
        yv = lambda val: (v + 7 - 14 * (val - lo) / (hi - lo)) * PPU
        if red:
            self.d.rectangle([(u + 0.35) * PPU, yv(min(red[1], hi)), (u + 0.75) * PPU, yv(max(red[0], lo))], fill=(195, 40, 30, 255))
        n = int(round((hi - lo) / minor))
        for i in range(n + 1):
            val = lo + i * minor
            maj = abs((val - lo) / major - round((val - lo) / major)) < 1e-6
            y = yv(val)
            self.d.line([((u - 0.2) * PPU, y), ((u + (0.7 if maj else 0.3)) * PPU, y)], fill=(20, 20, 20, 255), width=2 if maj else 1)
            if maj:
                lab = fmt(val) if fmt else (f'{val:g}')
                text(self.d, self.img, ((u + 1.55) * PPU, y), lab, 1.05 * PPU, (20, 20, 20, 255))
        text(self.d, self.img, (u * PPU, (v - 7.9) * PPU), unit, 0.8 * PPU, (20, 20, 20, 255))

    def static_pointer(self, u, v, frac):
        y = (v + 7 - 14 * frac) * PPU
        self.d.rectangle([(u - 2.0) * PPU, y - 1.5, (u + 0.6) * PPU, y + 1.5], fill=(200, 32, 22, 255))

    def ring(self, u, v, r, fill, outline=None):
        x0, y0 = self.P(u - r, v - r); x1, y1 = self.P(u + r, v + r)
        self.d.ellipse([x0, y0, x1, y1], fill=fill, outline=outline)

    def escutcheon(self, u, v, pos, r=2.6):
        # position labels just outside the plate, so the pointer never covers the one it points at
        self.ring(u, v, r, ESC, outline=(90, 90, 86, 255))
        text(self.d, self.img, (u * PPU, (v - r - 0.6) * PPU), pos[0], 0.85 * PPU, (20, 20, 20, 255))
        text(self.d, self.img, ((u + r + 0.3) * PPU, v * PPU), pos[1], 0.85 * PPU, (20, 20, 20, 255), anchor='lm')

    def tape(self, u, v, w, h, s):
        x0, y0 = self.P(u - w / 2, v - h / 2); x1, y1 = self.P(u + w / 2, v + h / 2)
        self.d.polygon([(x0, y0 + 2), (x1, y0), (x1 - 1, y1), (x0 + 1, y1 + 1)], fill=(226, 212, 166, 255))
        lines = s.split('|')
        for i, ln in enumerate(lines):
            text(self.d, self.img, (u * PPU, (v + (i - (len(lines) - 1) / 2) * 1.3) * PPU), ln, 1.05 * PPU, (24, 36, 70, 255), bold=False, squeeze=0.95)

    def vfd(self, u, v, w, h, lines):
        x0, y0 = self.P(u - w / 2, v - h / 2); x1, y1 = self.P(u + w / 2, v + h / 2)
        self.d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=(30, 30, 30, 255))
        self.d.rectangle([x0, y0, x1, y1], fill=(6, 20, 18, 255))
        for i, ln in enumerate(lines):
            text(self.d, self.img, (u * PPU, (v + (i - (len(lines) - 1) / 2) * 1.5) * PPU), ln, 1.1 * PPU, (110, 240, 210, 255), bold=False, squeeze=0.9)

    def tiles(self, prefix):
        out = []
        for t in range(4):
            tile = self.img.crop((0, t * 24 * PPU, DOOR_W * PPU, (t + 1) * 24 * PPU)).convert('RGB')
            TEX[f'{prefix}{t}'] = tile
            out.append(f'{prefix}{t}')
        return out


# =================================================================== small textures
LENS = {'red': ((80, 16, 12), (255, 70, 40)), 'green': ((14, 60, 28), (60, 255, 110)), 'amber': ((84, 54, 10), (255, 176, 40)),
        'white': ((86, 84, 76), (255, 248, 222)), None: ((40, 40, 40), (40, 40, 40))}


def lens(d, box, rgb, lit):
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=(26, 26, 26))
    d.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], fill=rgb)
    if lit:
        d.rectangle([x0 + 5, y0 + 4, x1 - 7, y0 + 8], fill=tuple(min(255, c + 60) for c in rgb))


def lamp_textures(lm):
    """+0 = initial appearance, +A = the other state."""
    on_c, off_c = lm['colors']
    pair = off_c is not None
    W = 80 if pair else 32
    key = f"{'p' if pair else 's'}{on_c[0]}{(off_c or 'n')[0]}{lm['init']}{'i' if lm.get('inv') else ''}"
    names = (f'+0l{key}', f'+al{key}')
    if names[0] in TEX:
        return names, pair
    for frame in (0, 1):
        flag_val = lm['init'] if frame == 0 else 1 - lm['init']
        if lm.get('inv'):
            flag_val = 1 - flag_val
        im = Image.new('RGB', (W, 32), (26, 26, 26))
        d = ImageDraw.Draw(im)
        if pair:
            lens(d, (0, 0, 31, 31), LENS[on_c][1 if flag_val == 1 else 0], flag_val == 1)
            lens(d, (48, 0, 79, 31), LENS[off_c][1 if flag_val == 0 else 0], flag_val == 0)
        else:
            lens(d, (0, 0, 31, 31), LENS[on_c][1 if flag_val == 1 else 0], flag_val == 1)
        TEX[names[frame]] = im
    return names, pair


def ann_textures(i, label, lit0):
    names = (f'+0an{i:02d}', f'+aan{i:02d}')
    trip = i in TRIP_WINDOWS
    for frame in (0, 1):
        lit = (frame == 1) != bool(lit0)
        im = Image.new('RGBA', (96, 48), (0, 0, 0, 255))
        d = ImageDraw.Draw(im)
        base = ((255, 96, 80) if trip else (255, 244, 214)) if lit else ((60, 30, 28) if trip else (62, 60, 54))
        d.rectangle([2, 2, 93, 45], fill=base + (255,))
        fg = (30, 12, 8, 255) if lit else ((150, 110, 104, 255) if trip else (150, 148, 138, 255))
        a, b = label.split('|')
        text(d, im, (48, 16), a, 13, fg); text(d, im, (48, 32), b, 13, fg)
        TEX[names[frame]] = im.convert('RGB')
    return names


def synchro_textures():
    """Synchroscope dial (black, like the gauges; the pointer is a beam) and the dark-lamp sync lamps."""
    S, c = 128, 64
    P = lambda a, r: (c + r * math.sin(a), c - r * math.cos(a))
    im = Image.new('RGBA', (S, S), (17, 17, 18, 255)); d = ImageDraw.Draw(im)
    cream = (236, 230, 210, 255)
    d.pieslice([c - 56, c - 56, c + 56, c + 56], -120, -60, fill=(30, 80, 40, 255))        # in-phase window, +-30 deg
    for k in range(12):
        a = k / 12 * 2 * math.pi
        d.line([P(a, 56), P(a, 47 if k % 3 == 0 else 51)], fill=cream, width=3 if k % 3 == 0 else 2)
    text(d, im, (c - 30, c + 26), 'SLOW', 9, cream); text(d, im, (c + 30, c + 26), 'FAST', 9, cream)
    d.arc([c - 40, c - 40, c + 40, c + 40], 120, 160, fill=cream, width=2)
    d.arc([c - 40, c - 40, c + 40, c + 40], 20, 60, fill=cream, width=2)
    text(d, im, (c, c + 42), 'SYNCHROSCOPE', 7.5, cream)
    d.ellipse([1, 1, S - 2, S - 2], outline=(160, 162, 158, 255), width=3)
    TEX['sc_sync'] = im.convert('RGB')
    for frame, lit in (('+0slmp', False), ('+aslmp', True)):
        im = Image.new('RGB', (80, 32), (26, 26, 26)); d = ImageDraw.Draw(im)
        lens(d, (0, 0, 31, 31), LENS['white'][1 if lit else 0], lit); lens(d, (48, 0, 79, 31), LENS['white'][1 if lit else 0], lit)
        TEX[frame] = im


def button_textures():
    for name, rgb in (('sc_btn_r', (190, 26, 20)), ('sc_btn_g', (24, 130, 58)), ('sc_btn_k', (30, 30, 30)), ('sc_btn_a', (220, 140, 18))):
        im = Image.new('RGB', (32, 32), rgb)
        d = ImageDraw.Draw(im); d.ellipse([6, 5, 22, 13], fill=tuple(min(255, c + 50) for c in rgb))
        TEX[name] = noise(im, 3)
    im = Image.new('RGB', (64, 64), (200, 20, 16)); d = ImageDraw.Draw(im); d.ellipse([10, 8, 40, 24], fill=(240, 90, 80)); TEX['sc_estop'] = im
    solid('sc_knob', (14, 14, 14), (16, 16))
    solid('sc_bezel', (40, 42, 42), (32, 32), n=3)
    solid('sc_white', (236, 234, 226), (16, 16))


# =================================================================== geometry
world = []
ents = [{'classname': 'worldspawn', 'mapversion': '220', 'wad': 'sablecreek.wad', 'message': 'Sable Creek Hydro - Unit 1'}]


def W(*a, **k):
    world.append(Box(*a, **k))


def door_xy(ci, u, v):
    return CX0[ci] + 2 + u, DOOR_TOP - v


def front_box(ci, u, v, w, h, y0, y1, tex, ppu=None, side='sc_black'):
    """Box on a door, front face textured with `tex` stretched to fit (or at ppu)."""
    x, z = door_xy(ci, u, v)
    xl, xr, zb, zt = x - w / 2, x + w / 2, z - h / 2, z + h / 2
    if ppu is None:
        tw, th = TEX[tex].size
        ppu_u = tw / w
        s = 1.0 / ppu_u
        tx = (-xl / s, zt / (h / th), s, h / th)
    else:
        tx = face_map(xl, zt, ppu)
    return Box(xl, y0, zb, xr, y1, zt, tex=side, faces={FRONT: (tex, tx)})


def build_room():
    X0, X1, Y0, Y1, H = -160, 160, -232, 34, 148
    T = 16
    W(X0 - T, Y0 - T, -T, X1 + T, Y1 + T, 0, tex='sc_floor', faces={UP: ('sc_floor', (0, 0, 0.25, 0.25))})
    W(X0 - T, Y0 - T, H, X1 + T, Y1 + T, H + T, tex='sc_ceil', faces={DOWN: ('sc_ceil', (0, 0, 0.5, 0.5))})
    for b in (Box(X0 - T, Y0 - T, 0, X0, Y1 + T, H, tex='sc_wall', scale=0.33), Box(X1, Y0 - T, 0, X1 + T, Y1 + T, H, tex='sc_wall', scale=0.33),
              Box(X0, Y0 - T, 0, X1, Y0, H, tex='sc_wall', scale=0.33), Box(X0, Y1, 0, X1, Y1 + T, H, tex='sc_wall', scale=0.33)):
        world.append(b)
    # vinyl cove base
    for b in (Box(X0, Y0, 0, X0 + 0.6, Y1, 4), Box(X1 - 0.6, Y0, 0, X1, Y1, 4), Box(X0, Y0, 0, X1, Y0 + 0.6, 4), Box(-160, 33.4, 0, 160, 34, 4)):
        b.tex = 'sc_rubber'; world.append(b)
    # troffers (texture lights)
    for x in (-80, 0, 80):
        for y in (-40, -150):
            W(x - 12, y - 24, H - 1, x + 12, y + 24, H, tex='sc_metal', faces={DOWN: ('sc_light', face_map_up(x - 12, y + 24, 64 / 24))})
    # cable ladder tray over the cabinets, hangers, drops into the cabinet roofs
    W(-100, 6, 128, 100, 7, 132, tex='sc_metal'); W(-100, 25, 128, 100, 26, 132, tex='sc_metal')
    for x in range(-96, 100, 12):
        W(x, 7, 128, x + 1.5, 25, 129, tex='sc_metal')
    for x in (-98, 98):
        W(x, 15, 132, x + 1, 16, H, tex='sc_metal')
    for ci in range(3):
        for k in range(3):
            x = CX0[ci] + 14 + k * 9
            W(x, 12, 109, x + 2.5, 14.5, 129, tex='sc_rubber')
    # personnel door, exit sign, extinguisher, clock, SLD poster
    W(X0, -205, 0, X0 + 1.5, -165, 98, tex='sc_door', scale=0.5)
    W(X0, -207, 98, X0 + 2, -163, 100, tex='sc_metal')
    W(X0 + 1.5, -178, 44, X0 + 3, -170, 46, tex='sc_metal')
    W(X0, -140, 30, X0 + 7, -134, 52, tex='sc_extg')
    W(X0, -40, 104, X0 + 1.5, -24, 120, tex='sc_black', faces={(1, 0, 0): ('sc_clock', (40 / 0.125, 120 / 0.125, 0.125, 0.125))})
    sx, sy = 60 / 256, 45 / 192   # right wall faces -X: mirror U so the poster reads left to right
    W(X1 - 1, -110, 56, X1, -50, 101, tex='sc_black', faces={(-1, 0, 0): ('sc_sld', (-50 / sx, 101 / sy, -sx, sy))})
    # operator desk + chair
    W(68, -176, 38, 142, -140, 40, tex='sc_wood', scale=0.5)
    W(118, -174, 0, 140, -142, 38, tex='sc_deskm', scale=0.5)
    W(70, -174, 0, 72, -142, 38, tex='sc_deskm', scale=0.5)
    W(72, -144, 14, 118, -143, 38, tex='sc_deskm', scale=0.5)
    W(92, -196, 18, 112, -178, 21, tex='sc_chair'); W(92, -198, 21, 112, -196, 42, tex='sc_chair'); W(101, -188, 0, 103, -186, 18, tex='sc_metal')
    # cabinets
    for ci in range(3):
        x0 = CX0[ci]
        W(x0, 0, 6, x0 + 60, 32, 108, tex='sc_paintd', faces={FRONT: ('sc_paint', (0, 0, 0.5, 0.5))}, scale=0.5)
        W(x0 + 1, 1, 0, x0 + 59, 31, 6, tex='sc_rubber')
        W(x0 - 0.3, -0.3, 108, x0 + 60.3, 32.3, 109, tex='sc_paintd', scale=0.5)
        W(x0 + 55.5, -1.6, 50, x0 + 56.6, -0.5, 60, tex='sc_metal')
    # lights
    for x in (-80, 0, 80):
        ents.append({'classname': 'light', 'origin': f'{x} -95 132', '_light': f'255 244 226 {LIGHT_A}'})
        ents.append({'classname': 'light', 'origin': f'{x} -160 130', '_light': f'255 244 226 {LIGHT_B}'})
    ents.append({'classname': 'light', 'origin': '0 -30 100', '_light': f'255 246 232 {LIGHT_C}'})
    ents.append({'classname': 'info_player_start', 'origin': '0 -185 36', 'angle': '90'})


# =================================================================== round gauges
# A needle is an env_beam from the dial centre to an invisible momentary_door ("slider") that runs along a
# line GH units above the centre, hidden inside the bezel. The logic sets the slider with USE_SET like any
# pointer; the beam swings with it. Only the part inside the round window shows.
GR, GH, GX = 4.0, 5, 6                 # dial window radius, slider line height over the pivot, slider half travel
GTH = math.atan2(GX, GH)               # needle half sweep: 50.2 degrees
GPH = 5.8                              # bezel half height
DIAL = 128                             # dial texture size: 16 texels per unit
NEEDLE, NEEDLE2 = '255 92 40', '110 190 255'


def warp(f):
    """Slider fraction that puts the needle at fraction f of its sweep (needle angle = atan(offset / GH))."""
    return (math.tan(GTH * (2 * f - 1)) / math.tan(GTH) + 1) / 2


def dial_texture(name, scales, unit, red=None, static=None, angle_of=None):
    """Black dial, cream scale. scales: [(lo, hi, number_step, major, minor, fmt)], outer first, then an inner one."""
    S, c = DIAL, DIAL / 2
    ang = angle_of or (lambda f: GTH * (2 * f - 1))
    P = lambda a, r: (c + r * math.sin(a), c - r * math.cos(a))
    im = Image.new('RGBA', (S, S), (17, 17, 18, 255)); d = ImageDraw.Draw(im)
    cream, inner_c = (236, 230, 210, 255), (150, 205, 225, 255)
    lo, hi = scales[0][:2]
    if red:
        a0, a1 = ang((red[0] - lo) / (hi - lo)), ang((red[1] - lo) / (hi - lo))
        d.arc([c - 55, c - 55, c + 55, c + 55], math.degrees(a0) - 90, math.degrees(a1) - 90, fill=(205, 40, 30, 255), width=5)
    for si, (lo, hi, step, major, minor, fmt) in enumerate(scales):
        inner = si > 0
        col = inner_c if inner else cream
        r0 = 29 if inner else 52
        d.arc([c - r0, c - r0, c + r0, c + r0], math.degrees(ang(0)) - 90, math.degrees(ang(1)) - 90, fill=col, width=1)
        for i in range(int(round((hi - lo) / minor)) + 1):
            val = lo + i * minor
            a = ang((val - lo) / (hi - lo))
            on = lambda q: abs((val - lo) / q - round((val - lo) / q)) < 1e-6
            ln = (7 if on(major) else 3.5) * (0.75 if inner else 1)
            d.line([P(a, r0), P(a, r0 + ln if inner else r0 - ln)], fill=col, width=2 if on(major) else 1)
            if on(step):
                text(d, im, P(a, 21 if inner else 37), fmt(val) if fmt else f'{val:g}', 7.5 if inner else 9.5, col)
    for i, ln in enumerate(unit.split('|')):
        text(d, im, (c, c + 24 + i * 11), ln, 10 if i == 0 else 7, cream if i == 0 else inner_c)
    if static is not None:
        a = ang(static)
        d.line([P(a, 4), P(a, 61)], fill=(255, 120, 60, 255), width=3)
    d.ellipse([1, 1, S - 2, S - 2], outline=(160, 162, 158, 255), width=3)
    TEX[name] = im.convert('RGB')
    return name


def _ray_box(cx, cz, dx, dz, x0, x1, z0, z1):
    ts = [t for t in ((x1 - cx) / dx if dx > 1e-9 else None, (x0 - cx) / dx if dx < -1e-9 else None,
                      (z1 - cz) / dz if dz > 1e-9 else None, (z0 - cz) / dz if dz < -1e-9 else None) if t is not None]
    t = min(ts)
    return (cx + dx * t, cz + dz * t)


def _clean(poly):
    out = []
    for p in poly:
        if not out or math.dist(p, out[-1]) > 1e-3:
            out.append(p)
    if math.dist(out[0], out[-1]) < 1e-3:
        out.pop()
    k = 0
    while k < len(out) and len(out) > 3:          # drop collinear points (they would give duplicate planes)
        a, b, c = out[k - 1], out[k], out[(k + 1) % len(out)]
        if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-4:
            out.pop(k)
        else:
            k += 1
    return out


def holed_plate(cx, cz, x0, x1, z0, z1, y0, y1, n=16):
    """Bezel [x0,x1] x [z0,z1], y0..y1, with a round window (n-gon, radius GR) at (cx, cz): n convex brushes,
    one per window edge, out to the rectangle along the rays through the edge's ends."""
    hole = [(cx + GR * math.cos(2 * math.pi * (k + 0.5) / n), cz + GR * math.sin(2 * math.pi * (k + 0.5) / n)) for k in range(n)]
    corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    out = []
    for k in range(n):
        p0, p1 = hole[k], hole[(k + 1) % n]
        a0 = math.atan2(p0[1] - cz, p0[0] - cx); a1 = math.atan2(p1[1] - cz, p1[0] - cx)
        while a1 <= a0:
            a1 += 2 * math.pi
        mid = []
        for q in corners:
            a = math.atan2(q[1] - cz, q[0] - cx)
            while a <= a0:
                a += 2 * math.pi
            if a < a1:
                mid.append((a, q))
        poly = _clean([p0, _ray_box(cx, cz, p0[0] - cx, p0[1] - cz, x0, x1, z0, z1)] + [q for _, q in sorted(mid)] +
                      [_ray_box(cx, cz, p1[0] - cx, p1[1] - cz, x0, x1, z0, z1), p1])
        out.append(prism(poly, y0, y1, 'y', 'sc_bezel', {len(poly) - 1: 'sc_metal'}))
    return out


def turned(poly, x, z, deg):
    """A polygon drawn pointing up, turned counter-clockwise by deg and placed at (x, z)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x + px * c - pz * s, z + px * s + pz * c) for px, pz in poly]


PISTOL = [(0, 3.3), (0.55, 2.1), (0.95, 0.3), (0.85, -1.1), (0.45, -1.7), (-0.45, -1.7), (-0.85, -1.1), (-0.95, 0.3), (-0.55, 2.1)]
BAR = [(-0.5, -2.0), (0.5, -2.0), (0.5, 1.1), (-0.5, 1.1)]
BAR_TIP = [(-0.5, 1.1), (0.5, 1.1), (0.4, 2.0), (-0.4, 2.0)]


# =================================================================== panels
def build_panels(dev):
    lamps = {lm['name']: lm for lm in dev['lamps']}
    rots = {r['name']: r for r in dev['rots']}
    knobs = {k['name']: k for k in dev['knobs']}
    doors = [Door(0, 'UNIT 1 - UNIT CONTROL', '+CP1'), Door(1, 'UNIT 1 - ANNUNCIATOR / PLC / AVR', '+CP2'),
             Door(2, 'UNIT 1 - AUXILIARIES', '+CP3')]
    E = []
    ndial = [0]

    def gauge_at(x, z, Y0, scales, unit, ptr=None, ptr2=None, red=None, static=None, xl=None, xr=None, angle_of=None):
        """Round gauge facing -Y on a surface at y = Y0 (Y0 + 0.5 must be whole: the beam plane holds the slider origins)."""
        tex = dial_texture(f'scg{ndial[0]}', scales, unit, red, static, angle_of); ndial[0] += 1
        world.extend(holed_plate(x, z, x - (xl or GX + 0.6), x + (xr or GX + 0.6), z - GPH, z + GPH, Y0 - 1.2, Y0))
        W(x - GR - 0.3, Y0 - 0.15, z - GR - 0.3, x + GR + 0.3, Y0 + 0.5, z + GR + 0.3, tex='sc_black',
          faces={FRONT: (tex, face_map(x - GR, z + GR, DIAL / (2 * GR)))})
        world.append(prism(ngon(x, z, 0.55), Y0 - 0.95, Y0 - 0.15, 'y', 'sc_knob'))         # pivot cap
        for p, col, w in ((ptr, NEEDLE, 4), (ptr2, NEEDLE2, 3)):
            if not p:
                continue
            sx, sz, yb = x - GX, z + GH, Y0 - 0.5
            assert sx == int(sx) and sz == int(sz) and yb == int(yb), (p, sx, sz, yb)
            # slider: an invisible tab just in front of the bezel (keeps it in the room's PVS, so the client
            # gets its position) plus the origin brush that the beam ends on; travel = tab width - lip
            E.append({'classname': 'momentary_door', 'targetname': p, 'angle': '0', 'speed': '200', 'lip': f'{0.5 - 2 * GX:g}',
                      'movesnd': '0', 'stopsnd': '0', 'rendermode': '2', 'renderamt': '0',
                      '_brushes': [Box(sx - 0.25, Y0 - 1.8, sz - 0.25, sx + 0.25, Y0 - 1.3, sz + 0.25, tex='sc_black'),
                                   Box(sx - 0.5, yb - 0.5, sz - 0.5, sx + 0.5, yb + 0.5, sz + 0.5, tex='ORIGIN')]})
            # needle: starts at the beam itself (a point entity when the beam is set up), ends on the slider
            E.append({'classname': 'env_beam', 'targetname': f'nd_{p}', 'LightningStart': f'nd_{p}', 'LightningEnd': p,
                      'origin': f'{x:g} {yb:g} {z:g}', 'texture': 'sprites/laserbeam.spr', 'BoltWidth': str(w),
                      'NoiseAmplitude': '0', 'life': '0', 'StrikeTime': '0', 'damage': '0', 'TextureScroll': '0',
                      'framestart': '0', 'renderamt': '255', 'rendercolor': col, 'spawnflags': '1'})

    def gauge(ci, u, v, label, scales, unit, **kw):
        x, z = door_xy(ci, u, v)
        gauge_at(x, z, -0.5, scales, unit, **kw)
        doors[ci].plate(u, v + GPH + 1.3, min(9.4, 0.55 * len(label) + 1.6), 1.4, label, px=0.8)

    def lampw(ci, u, v, name, labels):
        lm = lamps[name]
        (t0, t1), pair = lamp_textures(lm)
        w = 5.0 if pair else 2.0
        E.append({'classname': 'func_wall', 'targetname': name, 'rendermode': '2', 'renderamt': '255',
                  '_brushes': [front_box(ci, u, v, w, 2.0, -1.3, -0.5, t0)]})
        D = doors[ci]
        if pair:
            D.plate(u - 1.5, v + 2.1, 2.6, 1.0, labels[0], px=0.62); D.plate(u + 1.5, v + 2.1, 2.6, 1.0, labels[1], px=0.62)
            if len(labels) > 2:
                D.plate(u, v - 2.0, 7.0, 1.4, labels[2], px=0.8)
        else:
            D.plate(u, v + 2.2, 5.4, 1.5 if '|' not in labels[0] else 2.2, labels[0], px=0.62)

    def rot(ci, u, v, name, dial=False):
        """Maintained rotary switch, 90 degrees clockwise: a bar knob, or a bigger dial with a white pointer."""
        r = rots[name]
        x, z = door_xy(ci, u, v)
        k = 1.4 if dial else 1.0
        doors[ci].escutcheon(u, v, r['pos'], r=2.6 * k)
        doors[ci].plate(u, v - 2.6 * k - 2.3, 7.6, 1.4, r['label'], px=0.8)
        if dial:
            world.append(prism(ngon(x, z, 1.5), -1.4, -0.5, 'y', 'sc_metal'))
            place = lambda poly: [(x + px * k, z + pz * k) for px, pz in poly]
            brushes = [prism(place(BAR), -2.6, -1.4, 'y', 'sc_knob'), prism(place(BAR_TIP), -2.6, -1.4, 'y', 'sc_white')]
        else:
            brushes = [Box(x - 0.45, -1.6, z - 1.7, x + 0.45, -0.6, z + 1.7, tex='sc_knob')]
        E.append({'classname': 'func_rot_button', 'targetname': name, 'target': r['target'], 'spawnflags': str(128 + 32),
                  'distance': '90', 'speed': '240', 'wait': '-1', 'sounds': '21',
                  '_brushes': brushes + [Box(x - 0.5, -1.6, z - 0.5, x + 0.5, -0.6, z + 0.5, tex='ORIGIN')]})

    def cs_switch(ci, u, v, name, plate=None):
        """Control switch: pistol grip, left position = pos[0] (green), right = pos[1] (red).
        func_rot_button about the Y axis turns clockwise seen from the front: -45 -> +45 degrees."""
        r = rots[name]
        x, z = door_xy(ci, u, v); D = doors[ci]
        D.ring(u, v, 4.4, (233, 182, 28, 255) if r.get('grip') == 'red' else ESC, outline=(90, 90, 86, 255))
        for sgn, lab, col in ((-1, r['pos'][0], (16, 110, 50, 255)), (1, r['pos'][1], (170, 26, 18, 255))):
            text(D.d, D.img, ((u + sgn * 2.45) * PPU, (v - 2.45) * PPU), lab, 0.6 * PPU, col)
        lab = r['label']
        D.plate(*(plate or (u, v + 5.6)), min(11.5, 0.5 * len(lab) + 1.6), 1.4, lab, px=0.75)
        world.append(prism(ngon(x, z, 1.35), -1.3, -0.5, 'y', 'sc_metal'))
        E.append({'classname': 'func_rot_button', 'targetname': name, 'target': r['target'], 'spawnflags': str(128 + 32),
                  'distance': str(r['distance']), 'speed': str(r['speed']), 'wait': '-1', 'sounds': '21',
                  '_brushes': [prism(turned(PISTOL, x, z, 45), -2.9, -1.3, 'y', 'sc_red' if r.get('grip') == 'red' else 'sc_knob'),
                               Box(x - 0.5, -2.6, z - 0.5, x + 0.5, -1.6, z + 0.5, tex='ORIGIN')]})

    def synchroscope(ci, u, v):
        """Round dial with a full-turn pointer: a beam to a func_train that circles a hexagon of path_corners
        hidden in the bezel. The corners at 11 and 1 o'clock fire the in-phase window."""
        sc = dev['scope']
        x, z = door_xy(ci, u, v)
        world.extend(holed_plate(x, z, x - 5.7, x + 6.4, z - GPH, z + GPH, -1.7, -0.5))
        W(x - GR - 0.3, -0.65, z - GR - 0.3, x + GR + 0.3, 0, z + GR + 0.3, tex='sc_black',
          faces={FRONT: ('sc_sync', face_map(x - GR, z + GR, DIAL / (2 * GR)))})
        world.append(prism(ngon(x, z, 0.55), -1.45, -0.65, 'y', 'sc_knob'))
        n = len(sc['corners'])
        for i, (ang, msg) in enumerate(sc['corners']):
            a = math.radians(ang)
            e = {'classname': 'path_corner', 'targetname': f'scc{i}', 'target': f'scc{(i + 1) % n}',
                 'origin': f'{x + sc["R"] * math.sin(a):.3f} -1 {z + sc["R"] * math.cos(a):.3f}'}
            if msg:
                e['message'] = msg
            E.append(e)
        # the train's brushes are symmetric about its origin, so func_train puts the origin itself on each corner
        E.append({'classname': 'func_train', 'targetname': 'SCOPE', 'target': 'scc0', 'speed': f'{sc["speed"]:g}',
                  'rendermode': '2', 'renderamt': '0',
                  '_brushes': [Box(x - 0.25, -2.3, z - 0.25, x + 0.25, -1.8, z + 0.25, tex='sc_black'),
                               Box(x - 0.25, -0.2, z - 0.25, x + 0.25, 0.3, z + 0.25, tex='sc_black'),
                               Box(x - 0.5, -1.5, z - 0.5, x + 0.5, -0.5, z + 0.5, tex='ORIGIN')]})
        E.append({'classname': 'env_beam', 'targetname': 'nd_SCOPE', 'LightningStart': 'nd_SCOPE', 'LightningEnd': 'SCOPE',
                  'origin': f'{x:g} -1 {z:g}', 'texture': 'sprites/laserbeam.spr', 'BoltWidth': '5', 'NoiseAmplitude': '0',
                  'life': '0', 'StrikeTime': '0', 'damage': '0', 'TextureScroll': '0', 'framestart': '0', 'renderamt': '255',
                  'rendercolor': '255 70 40', 'spawnflags': '1'})
        doors[ci].plate(u, v + GPH + 1.3, 9, 1.4, 'SYNCHROSCOPE', px=0.8)

    def rotor(name, brushes, x, y, z, yaw=False, distance=3600, speed=120):
        """momentary_rot_button: hold USE to turn; the origin cube sits on whole units (hlcsg truncates it)."""
        E.append({'classname': 'momentary_rot_button', 'targetname': name, 'target': knobs[name]['target'],
                  'spawnflags': '0' if yaw else '128', 'distance': str(distance), 'speed': str(speed), 'returnspeed': '0',
                  'sounds': '21', '_brushes': brushes + [Box(x - 0.5, y - 0.5, z - 0.5, x + 0.5, y + 0.5, z + 0.5, tex='ORIGIN')]})

    def knob_panel(ci, u, v, name, label):
        x, z = door_xy(ci, u, v)
        W(x - 2.6, -0.8, z - 2.6, x + 2.6, -0.5, z + 2.6, tex='sc_metal')
        body = prism(ngon(x, z, 1.9), -2.3, -0.8, 'y', 'sc_knob')
        idx = prism([(x - 0.3, z + 0.4), (x + 0.3, z + 0.4), (x + 0.3, z + 1.7), (x - 0.3, z + 1.7)], -2.8, -2.3, 'y', 'sc_white')
        rotor(name, [body, idx], x, -1.5, z, distance=3600, speed=120)
        doors[ci].plate(u, v - 3.7, 9.5, 1.4, label, px=0.8)

    def wheel_panel(ci, u, v, name, label, R=3.6):
        x, z = door_xy(ci, u, v)
        br = []
        outer, inner = ngon(x, z, R + 0.35), ngon(x, z, R - 0.35)
        for k in range(8):
            br.append(prism([outer[k], outer[(k + 1) % 8], inner[(k + 1) % 8], inner[k]], -2.6, -1.8, 'y', 'sc_knob'))
        for k in range(4):
            a = math.pi / 4 + k * math.pi / 2; c, sn = math.cos(a), math.sin(a); r0, r1, hw = 0.9, R - 0.35, 0.3
            br.append(prism([(x + c * r0 - sn * hw, z + sn * r0 + c * hw), (x + c * r1 - sn * hw, z + sn * r1 + c * hw),
                             (x + c * r1 + sn * hw, z + sn * r1 - c * hw), (x + c * r0 + sn * hw, z + sn * r0 - c * hw)], -2.5, -1.9, 'y', 'sc_knob'))
        br.append(prism(ngon(x, z, 1.0), -2.8, -0.8, 'y', 'sc_metal'))
        br.append(prism([(x - 0.45, z + R - 0.2), (x + 0.45, z + R - 0.2), (x + 0.45, z + R + 0.7), (x - 0.45, z + R + 0.7)], -4.2, -1.8, 'y', 'sc_red'))
        rotor(name, br, x, -1.5, z, distance=3600, speed=180)
        doors[ci].plate(u, v - R - 2.6, 11, 1.4, label, px=0.8)          # clear of the handle on the rim

    hw_fmt = lambda x: f'{x:g}'
    ROW1, ROW2, CTL = 13, 29, 50       # gauge rows at the top, the breaker row across the middle (all three cabinets)

    # ------------------------------------------- left: unit control
    D = doors[0]
    D.section(1.5, 5.5, 53, 32.5, 'METERS')
    gauge(0, 7, ROW1, 'GEN VOLTS', [(0, 600, 200, 100, 20, None)], 'VOLTS AC', ptr='p_volts', xr=5)
    gauge(0, 17, ROW1, 'KILOWATTS', [(0, 320, 80, 80, 20, None), (0, 400, 200, 100, 50, None)], 'kW|AMPS INNER',
          ptr='p_kw', xl=5, xr=5)
    gauge(0, 27, ROW1, 'KILOVARS', [(-200, 200, 200, 100, 25, lambda x: f'{x:+g}' if x else '0')], 'kvar', ptr='p_kvar',
          xl=5, xr=7.3)
    synchroscope(0, 41, ROW1)
    E.append({'classname': 'func_wall', 'targetname': 'SYNCLAMPS', 'rendermode': '2', 'renderamt': '255',
              '_brushes': [front_box(0, 51.5, ROW1 - 1, 5, 2, -1.2, -0.5, '+0slmp')]})
    D.plate(51.5, ROW1 + 1.4, 5.4, 1.0, 'SYNC LAMPS', px=0.62)
    gauge(0, 7, ROW2, 'SPEED', [(0, 150, 50, 25, 5, None)], 'RPM', ptr='p_speed', red=(140, 150), xr=5)
    gauge(0, 17, ROW2, 'WICKET GATE', [(0, 100, 50, 25, 5, None), (0, 90, 30, 30, 10, None)], '% OPEN|CFS INNER',
          ptr='p_gate', xl=5, xr=5)
    gauge(0, 27, ROW2, 'EXCITER FIELD', [(0, 5, 1, 1, 0.2, None), (0, 150, 50, 50, 10, None)], 'AMPS DC|VOLTS INNER',
          ptr='p_exc', xl=5, xr=5)
    gauge(0, 37, ROW2, 'FIRING ANGLE', [(0, 90, 30, 15, 5, None)], 'DEGREES|LOWER = MORE FIELD', ptr='p_fa', xl=5)
    D.section(1.5, 40, 53, 44, 'CONTROLS')
    # breakers, with their lamps under the nameplates
    cs_switch(0, 8, CTL, 'r_ss')
    cs_switch(0, 21, CTL, 'r_52'); lampw(0, 21, CTL + 9, 'LP_cb', ('CLSD', 'OPEN'))
    cs_switch(0, 34, CTL, 'r_exc'); lampw(0, 34, CTL + 9, 'LP_exc', ('ON', 'OFF'))
    cs_switch(0, 47, CTL, 'r_gt'); D.plate(47, CTL + 9, 11, 1.6, 'EMERGENCY STOP', style='red', px=0.8)
    # dials
    wheel_panel(0, 10, CTL + 21, 'k_gate', 'WICKET GATE')
    lampw(0, 10, CTL + 28.5, 'L_k_gate', ('OPEN', 'CLOSE', 'NEXT TURN'))
    rot(0, 27, CTL + 21, 'r_br', dial=True)
    lampw(0, 27, CTL + 28.5, 'LP_brake', ('APPL', 'REL'))
    knob_panel(0, 44, CTL + 21, 'k_fa', 'FIRING ANGLE')
    lampw(0, 44, CTL + 27.5, 'L_k_fa', ('RAISE', 'LOWER'))

    # ------------------------------------------- middle: the annunciator, the PLC and the AVR, nothing else
    D = doors[1]
    W(door_xy(1, 0.5, 0)[0], -0.9, DOOR_TOP - 37.5, door_xy(1, 55.5, 0)[0], -0.5, DOOR_TOP - 4.5, tex='sc_black')
    for i, label in enumerate(ANN):
        c, r = i % 4, i // 4
        u, v = 7.75 + c * 13.5, 9 + r * 8
        lit0 = dev.get('ann_init', {}).get(i, 0)
        t0, t1 = ann_textures(i, label, lit0)
        E.append({'classname': 'func_wall', 'targetname': f'A{i:02d}', 'rendermode': '2', 'renderamt': '255',
                  '_brushes': [front_box(1, u, v, 12.6, 7.0, -1.4, -0.9, t0)]})
    cs_switch(1, 17, CTL, 'r_plc')
    cs_switch(1, 39, CTL, 'r_avr')

    # ------------------------------------------- right: auxiliaries (the pumps and the gauges)
    D = doors[2]
    D.section(1.5, 5.5, 53, 32.5, 'METERS')
    gauge(2, 7, ROW1, 'LUBE OIL', [(0, 60, 20, 10, 2, None)], 'PSI', ptr='p_lube', red=(0, 20), xr=5)
    gauge(2, 17, ROW1, 'COOLING WATER', [(0, 100, 20, 20, 5, None)], 'GPM', ptr='p_cw', red=(0, 35), xl=5, xr=5)
    gauge(2, 27, ROW1, 'BEARING TEMP', [(20, 120, 20, 20, 5, None)], 'DEG C', ptr='p_bt', red=(100, 120), xl=5, xr=5)
    gauge(2, 37, ROW1, 'VIBRATION', [(0, 20, 10, 5, 1, None)], 'MILS P-P', ptr='p_vib', red=(12, 20), xl=5, xr=5)
    gauge(2, 47, ROW1, 'SPIRAL CASE', [(0, 30, 10, 5, 1, None)], 'PSI', ptr='p_scase', xl=5)
    gauge(2, 7, ROW2, 'SERVO OIL', [(0, 400, 100, 100, 20, None)], 'PSI', ptr='p_opu', red=(0, 220), xr=5)
    gauge(2, 17, ROW2, 'BRAKE AIR', [(0, 150, 50, 50, 10, None)], 'PSI', ptr='p_air', red=(0, 50), xl=5, xr=5)
    gauge(2, 27, ROW2, 'HEADWATER', [(509, 515, 1, 1, 0.25, hw_fmt)], 'EL FT', ptr='p_hw', red=(514, 515), xl=5, xr=5)
    gauge(2, 37, ROW2, 'SPILL GATE', [(0, 4, 1, 1, 0.25, None)], 'FT OPEN', ptr='p_spill', xl=5)
    D.section(1.5, 40, 53, 22, 'PUMPS')
    for u, nm in ((8, 'r_lp'), (21, 'r_wp'), (34, 'r_hp'), (47, 'r_ac')):
        cs_switch(2, u, CTL, nm)

    # door tiles -> world brushes
    for ci, Dr in enumerate(doors):
        names = Dr.tiles(f'scd{ci}')
        x0 = CX0[ci] + 2
        for t, nm in enumerate(names):
            zt = DOOR_TOP - t * 24
            W(x0, -0.5, zt - 24, x0 + DOOR_W, 0, zt, tex='sc_paintd', faces={FRONT: (nm, face_map(x0, zt, PPU))})
    return E


# =================================================================== sounds
def make_sounds(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    sr = 22050
    t = np.arange(int(sr * 2.0)) / sr
    rng = np.random.default_rng(3)

    def lowpass(x, a):
        y = np.empty_like(x); acc = 0.0
        for i, v in enumerate(x):
            acc += a * (v - acc); y[i] = acc
        return y

    def loopify(x):
        n = len(x) // 8
        x[:n] = x[:n] * np.linspace(0, 1, n) + x[-n:] * np.linspace(1, 0, n)
        return x[:-n]
    # turbine: blade-pass rumble (15 blades x 1.67 Hz = 25 Hz) + runner whine; pitch-shifted by the game
    turb = 0.45 * np.sin(2 * np.pi * 50 * t) + 0.25 * np.sin(2 * np.pi * 100 * t) + 0.12 * np.sin(2 * np.pi * 150 * t)
    turb *= 0.75 + 0.25 * np.sin(2 * np.pi * 25 * t)
    turb += 0.35 * lowpass(rng.standard_normal(len(t)), 0.05)
    write_wav(os.path.join(dirpath, 'turbine.wav'), loopify(turb * 0.8), sr, loop=True)
    water = lowpass(rng.standard_normal(len(t)), 0.08) * 1.6
    write_wav(os.path.join(dirpath, 'water.wav'), loopify(water * 0.7), sr, loop=True)
    hum = 0.5 * np.sin(2 * np.pi * 120 * t) + 0.25 * np.sin(2 * np.pi * 240 * t) + 0.1 * np.sin(2 * np.pi * 360 * t)
    write_wav(os.path.join(dirpath, 'hum.wav'), hum[:sr] * 0.5, sr, loop=True)
    horn = np.sign(np.sin(2 * np.pi * 440 * t)) * 0.3 + np.sign(np.sin(2 * np.pi * 446 * t)) * 0.3
    horn = lowpass(horn, 0.25)
    write_wav(os.path.join(dirpath, 'horn.wav'), horn[:sr] * 0.6, sr, loop=True)
    pump = 0.4 * np.sin(2 * np.pi * 120 * t) + 0.3 * np.sin(2 * np.pi * 180 * t) + 0.1 * lowpass(rng.standard_normal(len(t)), 0.3)
    write_wav(os.path.join(dirpath, 'pump.wav'), pump[:sr] * 0.4, sr, loop=True)
    tb = np.arange(int(sr * 0.6)) / sr
    brk = (np.sin(2 * np.pi * 70 * tb) * np.exp(-tb * 9) + 0.8 * rng.standard_normal(len(tb)) * np.exp(-tb * 30))
    write_wav(os.path.join(dirpath, 'breaker.wav'), brk * 0.8, sr)
    tr = np.arange(int(sr * 0.15)) / sr
    rel = rng.standard_normal(len(tr)) * np.exp(-tr * 60) + 0.5 * np.sin(2 * np.pi * 1800 * tr) * np.exp(-tr * 40)
    write_wav(os.path.join(dirpath, 'relay.wav'), rel * 0.6, sr)


# =================================================================== main
def main():
    os.makedirs(OUT, exist_ok=True)
    L, logic, dev = build_logic()
    room_textures(); button_textures(); synchro_textures()
    build_room()
    panel_ents = build_panels(dev)
    # sounds placed in the room
    pos = {'s_turb': '0 10 20', 's_water': '0 20 10', 's_hum': '0 10 60', 's_horn': '0 10 116', 's_pump': '60 10 20',
           's_brk': '-60 -2 80', 's_relay': '0 -2 90'}
    snd = []
    for s in dev['sounds']:
        sf = 16 | (0 if s['loop'] else 32) | 4       # start silent, medium radius
        snd.append({'classname': 'ambient_generic', 'targetname': s['name'], 'message': s['wav'], 'health': str(s['vol']),
                    'pitch': '100', 'pitchstart': '100', 'spawnflags': str(sf), 'origin': pos[s['name']]})
    round_ptrs = set(dev['ptrs']) - {k['target'] for k in dev['knobs']}
    for e in logic:                      # gauge needles: a fraction of the sweep -> slider position
        if e['classname'] == 'game_counter_set' and e.get('target') in round_ptrs:
            e['frags'] = f"{warp(float(e.get('frags', 0))):.4f}"
    for e in logic:                      # trim the entity lump: defaults need no key
        if e['classname'] == 'game_counter_set' and e.get('frags') in ('0', '0.0000'):
            del e['frags']
    all_ents = ents + panel_ents + snd + logic
    write_map(os.path.join(OUT, 'sablecreek.map'), world, all_ents)
    write_wad(os.path.join(OUT, 'sablecreek.wad'), TEX)
    open(os.path.join(OUT, 'sablecreek.rad'), 'w').write(f'sc_light 255 244 226 {TEXLIGHT}\n')
    make_sounds(os.path.join(OUT, 'sound', 'sablecreek'))
    brush_models = sum(1 for e in all_ents if e.get('_brushes'))
    print(f'{len(all_ents)} entities ({len(logic)} logic, {brush_models} brush models, {len(snd)} sounds), '
          f'{len(world)} world brushes, {len(TEX)} textures')
    return all_ents, dev


if __name__ == '__main__':
    main()
