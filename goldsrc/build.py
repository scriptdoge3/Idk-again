"""
Build Sable Creek Hydro for plain Half-Life (GoldSrc).

  python3 build.py            -> out/sablecreek.map, out/sablecreek.wad, out/lights.rad,
                                 out/sound/sablecreek/*.wav
Then compile with any Half-Life compile tools (SDHLT / VHLT):
  hlcsg -wadinclude sablecreek sablecreek ; hlbsp sablecreek ; hlvis sablecreek ;
  hlrad -lights lights.rad -extra sablecreek
and run  python3 build.py --patch out/sablecreek.bsp  to set pointer travel from the
compiled model bounds (optional, the .map already assumes exact bounds).

Scale: 1 unit = 1 inch for the player; the room is built about 1.3x real size like
Half-Life's own maps, so a 2.1 m cabinet is 108 units tall.
"""
import math, os, sys, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from hlfiles import Box, face_map, face_map_up, write_map, write_wad, write_wav
from plant import build as build_logic, ANN, KW

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
FONT_B = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
FONT_R = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'
FRONT, BACK, UP, DOWN = (0, -1, 0), (0, 1, 0), (0, 0, 1), (0, 0, -1)
PPU = 8                               # door art texels per unit
CX0 = [-90, -30, 30]                  # cabinet left edges
DOOR_TOP, DOOR_H, DOOR_W = 105, 96, 56
TEX = {}
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
    # instructor console top (drawn later once buttons are placed)


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

    def escutcheon(self, u, v, pos):
        self.ring(u, v, 2.6, (20, 20, 20, 255))
        text(self.d, self.img, (u * PPU, (v - 2.0) * PPU), pos[0], 0.85 * PPU, (240, 238, 228, 255))
        text(self.d, self.img, ((u + 2.05) * PPU, v * PPU), pos[1], 0.85 * PPU, (240, 238, 228, 255), anchor='mm')

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
    trip = i < 5 or i in (8, 15)
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
    def face(angle):
        im = Image.new('RGBA', (64, 64), (18, 18, 18, 255))
        d = ImageDraw.Draw(im)
        d.ellipse([3, 3, 60, 60], fill=(240, 236, 224, 255))
        for k in range(12):
            a = k / 12 * 2 * math.pi
            d.line([(32 + 26 * math.sin(a), 32 - 26 * math.cos(a)), (32 + 22 * math.sin(a), 32 - 22 * math.cos(a))], fill=(20, 20, 20, 255), width=2)
        d.polygon([(32, 4), (29, 10), (35, 10)], fill=(190, 30, 20, 255))
        text(d, im, (18, 40), 'SLOW', 6, (20, 20, 20, 255)); text(d, im, (46, 40), 'FAST', 6, (20, 20, 20, 255))
        d.line([(32, 32), (32 + 24 * math.sin(angle), 32 - 24 * math.cos(angle))], fill=(200, 30, 20, 255), width=3)
        d.ellipse([29, 29, 35, 35], fill=(30, 30, 30, 255))
        return im.convert('RGB')
    TEX['+0sync'] = face(0)
    for k, c in enumerate('abcdefghij'):
        TEX[f'+{c}sync'] = face(k / 10 * 2 * math.pi)
    TEX['+0slmp'] = Image.new('RGB', (80, 32), (26, 26, 26))
    d = ImageDraw.Draw(TEX['+0slmp']); lens(d, (0, 0, 31, 31), LENS['white'][0], False); lens(d, (48, 0, 79, 31), LENS['white'][0], False)
    for k, c in enumerate('abcdefghij'):
        im = Image.new('RGB', (80, 32), (26, 26, 26)); d = ImageDraw.Draw(im)
        lit = k < 5
        lens(d, (0, 0, 31, 31), LENS['white'][1 if lit else 0], lit); lens(d, (48, 0, 79, 31), LENS['white'][1 if lit else 0], lit)
        TEX[f'+{c}slmp'] = im


def button_textures():
    for name, rgb in (('sc_btn_r', (190, 26, 20)), ('sc_btn_g', (24, 130, 58)), ('sc_btn_k', (30, 30, 30)), ('sc_btn_a', (220, 140, 18))):
        im = Image.new('RGB', (32, 32), rgb)
        d = ImageDraw.Draw(im); d.ellipse([6, 5, 22, 13], fill=tuple(min(255, c + 50) for c in rgb))
        TEX[name] = noise(im, 3)
    im = Image.new('RGB', (64, 64), (200, 20, 16)); d = ImageDraw.Draw(im); d.ellipse([10, 8, 40, 24], fill=(240, 90, 80)); TEX['sc_estop'] = im
    solid('sc_knob', (14, 14, 14), (16, 16))


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
        ents.append({'classname': 'light', 'origin': f'{x} -60 130', '_light': '255 244 226 260'})
        ents.append({'classname': 'light', 'origin': f'{x} -160 130', '_light': '255 244 226 200'})
    ents.append({'classname': 'light', 'origin': '0 -30 100', '_light': '255 246 232 120'})
    ents.append({'classname': 'info_player_start', 'origin': '0 -185 36', 'angle': '90'})


# =================================================================== panels
LAYOUT = {}


def build_panels(dev):
    lamps = {lm['name']: lm for lm in dev['lamps']}
    buttons = {b['name']: b for b in dev['buttons']}
    rots = {r['name']: r for r in dev['rots']}
    doors = [Door(0, 'UNIT 1 - AUXILIARY SYSTEMS', '+CP1'), Door(1, 'UNIT 1 - TURBINE / GENERATOR', '+CP2'),
             Door(2, 'UNIT 1 - EXCITATION / ANNUNCIATOR / SPILLWAY', '+CP3')]
    E = []

    def edge(ci, u, v, label, scale, ptr=None, ptr2=None, static=None):
        D = doors[ci]
        D.edge_scale(u, v, *scale[:5], red=scale[5] if len(scale) > 5 else None, fmt=scale[6] if len(scale) > 6 else None)
        D.plate(u, v + 10.6, 6.4, 2.4, label, px=0.85)
        x, z = door_xy(ci, u, v)
        for (a, b, c, d_) in ((x - 2.9, x + 2.9, z + 8.5, z + 9.1), (x - 2.9, x + 2.9, z - 9.1, z - 8.5), (x - 2.9, x - 2.3, z - 8.5, z + 8.5), (x + 2.3, x + 2.9, z - 8.5, z + 8.5)):
            W(a, -1.5, c, b, -0.5, d_, tex='sc_black')
        if static is not None:
            D.static_pointer(u, v, static)
        zb = z - 7
        if ptr:
            E.append(pointer(ptr, x - 2.0, x + 0.5, zb, -0.95, -0.6, 'sc_red'))
        if ptr2:
            E.append(pointer(ptr2, x - 0.1, x + 1.9, zb, -1.25, -0.98, 'sc_needle'))

    def pointer(name, xl, xr, zb, y0, y1, tex, h=0.45, travel=14.0):
        return {'classname': 'momentary_door', 'targetname': name, 'angle': '-1', 'speed': '200', 'lip': f'{h - 2 - travel:g}',
                'movesnd': '0', 'stopsnd': '0', '_brushes': [Box(xl, y0, zb - h / 2, xr, y1, zb + h / 2, tex=tex)]}

    def lampw(ci, u, v, name, labels):
        lm = lamps[name]
        (t0, t1), pair = lamp_textures(lm)
        w = 5.0 if pair else 2.0
        e = {'classname': 'func_wall', 'targetname': name, 'rendermode': '2', 'renderamt': '255',
             '_brushes': [front_box(ci, u, v, w, 2.0, -1.3, -0.5, t0)]}
        E.append(e)
        D = doors[ci]
        if pair:
            D.plate(u - 1.5, v + 2.1, 2.6, 1.0, labels[0], px=0.62); D.plate(u + 1.5, v + 2.1, 2.6, 1.0, labels[1], px=0.62)
            if len(labels) > 2:
                D.plate(u, v - 2.0, 7.0, 1.4, labels[2], px=0.8)
        else:
            D.plate(u, v + 2.2, 5.4, 1.5 if '|' not in labels[0] else 2.2, labels[0], px=0.62)

    def button(ci, u, v, name, label=None, size=2.4):
        b = buttons[name]
        tex = {'red': 'sc_btn_r', 'green': 'sc_btn_g', 'black': 'sc_btn_k', 'amber': 'sc_btn_a', 'estop': 'sc_estop'}[b['color']]
        x, z = door_xy(ci, u, v)
        depth, travel = (2.0, 1.0) if b['color'] == 'estop' else (1.2, 0.6)
        W(x - size / 2 - 0.5, -0.8, z - size / 2 - 0.5, x + size / 2 + 0.5, -0.5, z + size / 2 + 0.5, tex='sc_metal')
        e = {'classname': 'func_button', 'targetname': name, 'target': b['target'], 'angle': '90', 'speed': '40',
             'lip': f'{depth - 2 - travel:g}', 'wait': '0.6', 'sounds': '14' if b['color'] != 'estop' else '11', 'locked_sound': '10',
             '_brushes': [Box(x - size / 2, -0.8 - depth, z - size / 2, x + size / 2, -0.8, z + size / 2, tex=tex)]}
        if b.get('master'):
            e['master'] = b['master']
        E.append(e)
        if b['color'] == 'estop':
            doors[ci].ring(u, v, 4.2, (233, 182, 28, 255))
            doors[ci].plate(u, v - 5.2, 9, 1.5, 'EMERGENCY STOP', style='red', px=0.85)
        else:
            doors[ci].plate(u, v - 2.6, 4.6, 1.3, label or b['label'], px=0.75)

    def rot(ci, u, v, name):
        r = rots[name]
        x, z = door_xy(ci, u, v)
        doors[ci].escutcheon(u, v, r['pos'])
        doors[ci].plate(u, v - 4.1, 7.6, 1.4, r['label'], px=0.8)
        E.append({'classname': 'func_rot_button', 'targetname': name, 'target': r['target'], 'spawnflags': str(128 + 32),
                  'distance': '90', 'speed': '240', 'wait': '-1', 'sounds': '21',
                  '_brushes': [Box(x - 0.45, -1.6, z - 1.7, x + 0.45, -0.6, z + 1.7, tex='sc_knob'),
                               Box(x - 0.25, -0.6, z - 0.25, x + 0.25, -0.5, z + 0.25, tex='ORIGIN')]})

    # ------------------------------------------------------- cabinet 1: aux
    D = doors[0]
    D.section(1.5, 6, 53, 27, 'GOVERNOR OIL PRESSURE UNIT')
    edge(0, 6, 18, 'PRESS TANK|PSI', (0, 400, 100, 20, 'PSI', (0, 250)), ptr='p_opu')
    lampw(0, 19, 12, 'LP_p1', ('RUN', 'STOP', 'OIL PUMP 1 (LEAD)'))
    lampw(0, 31, 12, 'LP_p2', ('RUN', 'STOP', 'OIL PUMP 2 (LAG)'))
    lampw(0, 43, 12, 'L_opuok', ('OIL PRESS|NORMAL',))
    button(0, 19, 24, 'b_air', 'PUMP TEST')
    D.tape(38, 24.5, 13, 4.2, 'LEAD PUMP 270-300|LAG PUMP 250')
    D.section(1.5, 35, 53, 27, 'COOLING WATER - HP LIFT - BRAKES')
    edge(0, 6, 47, 'COOLING WATER|GPM', (0, 100, 20, 5, 'GPM', (0, 35)), ptr='p_cw')
    edge(0, 14, 47, 'HP LIFT OIL|PSI', (0, 3000, 1000, 250, 'PSI'), ptr='p_lift')
    lampw(0, 27, 41, 'LP_cw', ('RUN', 'STOP', 'CW PUMP'))
    lampw(0, 40, 41, 'LP_lift', ('RUN', 'STOP', 'LIFT PUMP'))
    lampw(0, 27, 53, 'LP_brake', ('APPL', 'REL', 'AIR BRAKES'))
    D.tape(42, 54, 12, 4.2, 'BRAKES ON BELOW|25 % SPEED')
    D.section(1.5, 64, 53, 20, 'STATION SERVICE - 125 VDC')
    D.edge_scale(6, 74.5, 0, 600, 100, 20, 'VOLTS'); D.static_pointer(6, 74.5, 0.8)
    D.edge_scale(14, 74.5, 0, 150, 25, 5, 'VDC', (0, 115)); D.static_pointer(14, 74.5, 132 / 150)
    for uu in (6, 14):
        x, z = door_xy(0, uu, 74.5)
        for (a, b, c, d_) in ((x - 2.9, x + 2.9, z + 8.5, z + 9.1), (x - 2.9, x + 2.9, z - 9.1, z - 8.5), (x - 2.9, x - 2.3, z - 8.5, z + 8.5), (x + 2.3, x + 2.9, z - 8.5, z + 8.5)):
            W(a, -1.5, c, b, -0.5, d_, tex='sc_black')
    D.plate(32, 70, 20, 4.6, 'DANGER|480 VAC  125 VDC INSIDE', style='red', px=1.0)
    D.plate(32, 77, 20, 3, 'DE-ENERGIZE BEFORE OPENING', style='yel', px=0.8)

    # ------------------------------------------- cabinet 2: turbine / generator
    D = doors[1]
    D.section(1.5, 6, 53, 26, 'GENERATOR 300 kVA 480 V 60 Hz 72 POLE')
    edge(1, 5, 17, 'GEN|VOLTS', (0, 600, 100, 20, 'VOLTS'), ptr='p_volts')
    edge(1, 12.5, 17, 'GEN|AMPERES', (0, 400, 100, 20, 'AMPS'), ptr='p_kw')
    edge(1, 20, 17, 'KILOWATTS|BLK=LOAD SET', (0, 320, 80, 20, 'kW'), ptr='p_kw', ptr2='p_kwsp')
    edge(1, 27.5, 17, 'KILOVARS', (-200, 200, 100, 25, 'kvar'), ptr='p_kvar')
    edge(1, 35, 17, 'FREQUENCY|HZ', (54, 66, 3, 1, 'Hz'), ptr='p_hz')
    lampw(1, 47, 11, 'LP_cb', ('CLOSED', 'OPEN', '52G BREAKER'))
    button(1, 44, 20, 'b_cbclose', 'CLOSE')
    button(1, 50, 20, 'b_cbtrip', 'TRIP')
    D.tape(47, 26.5, 12, 3.2, 'SYNC CHECK|ON CLOSE PB')
    D.section(1.5, 34, 53, 26, 'TURBINE - SYNCHRONIZING')
    edge(1, 5, 45, 'SPEED|RPM', (0, 150, 25, 5, 'RPM', (140, 150)), ptr='p_speed')
    edge(1, 12.5, 45, 'WICKET|GATE %', (0, 100, 20, 5, '%'), ptr='p_gate')
    edge(1, 20, 45, 'DISCHARGE|CFS', (0, 100, 20, 5, 'CFS'), ptr='p_gate')
    edge(1, 27.5, 45, 'SPIRAL CASE|PSI', (0, 30, 5, 1, 'PSI'), ptr='p_scase')
    edge(1, 35, 45, 'VIBRATION|MILS', (0, 20, 5, 1, 'MILS', (12, 20)), ptr='p_vib')
    x, z = door_xy(1, 47, 41)
    E.append({'classname': 'func_wall', 'targetname': 'SYNCHRO', 'rendermode': '2', 'renderamt': '255',
              '_brushes': [front_box(1, 47, 41, 7, 7, -1.0, -0.5, '+0sync')]})
    D.plate(47, 45.6, 9, 1.3, 'SYNCHROSCOPE', px=0.8)
    E.append({'classname': 'func_wall', 'targetname': 'SYNCLAMPS', 'rendermode': '2', 'renderamt': '255',
              '_brushes': [front_box(1, 47, 49, 5, 2, -1.2, -0.5, '+0slmp')]})
    D.plate(47, 51.2, 7, 1.0, 'SYNC LAMPS', px=0.62)
    rot(1, 47, 57, 'r_sync')
    D.section(1.5, 62, 53, 31, 'GOVERNOR - UNIT CONTROL')
    rot(1, 7, 69, 'r_gov')
    lampw(1, 7, 75.5, 'L_govman', ('GOV IN|MANUAL',))
    button(1, 16, 69, 'b_graise', 'GATE +'); button(1, 21.5, 69, 'b_glower', 'GATE -')
    button(1, 30, 69, 'b_sraise', 'LOAD +'); button(1, 35.5, 69, 'b_slower', 'LOAD -')
    D.tape(26, 75, 15, 3.4, 'ROUGH ZONE BELOW|110 kW - AVOID')
    lampw(1, 44, 67, 'L_lock', ('86|LOCKOUT',))
    button(1, 51, 67, 'b_reset86', '86 RESET')
    lampw(1, 7, 82, 'L_ready', ('READY',)); lampw(1, 14, 82, 'L_run', ('RUNNING',))
    button(1, 7, 88.5, 'b_start', 'START'); button(1, 14, 88.5, 'b_stop', 'STOP')
    button(1, 27, 86, 'b_estop')

    # ------------------------- cabinet 3: excitation / annunciator / spillway
    D = doors[2]
    x0, y0 = door_xy(2, 4, 6)
    W(x0 - 0.5, -0.9, DOOR_TOP - 31.5, door_xy(2, 52, 0)[0] + 0.5, -0.5, DOOR_TOP - 5.0, tex='sc_black')
    for i, label in enumerate(ANN):
        c, r = i % 4, i // 4
        u, v = 10 + c * 12, 9.5 + r * 6.2
        lit0 = dev.get('ann_init', {}).get(i, 0)
        t0, t1 = ann_textures(i, label, lit0)
        E.append({'classname': 'func_wall', 'targetname': f'A{i:02d}', 'rendermode': '2', 'renderamt': '255',
                  '_brushes': [front_box(2, u, v, 11.2, 5.6, -1.4, -0.9, t0)]})
    D.plate(28, 4.6, 16, 1.2, 'ANNUNCIATOR', px=0.8)
    button(2, 22, 35, 'b_ack', 'ACK'); button(2, 34, 35, 'b_annreset', 'RESET')
    D.section(1.5, 39, 53, 21, 'BRUSHLESS EXCITATION - AVR')
    edge(2, 5, 49, 'EXCITER|FIELD A', (0, 5, 1, 0.2, 'A DC'), ptr='p_volts')
    edge(2, 12.5, 49, 'EXCITER|FIELD V', (0, 150, 25, 5, 'V DC'), ptr='p_volts')
    D.vfd(30, 44, 16, 4, ['AVR  AUTO  SET 100.0%', 'PF CTRL  0.97 LAG'])
    lampw(2, 24, 51, 'LP_exc', ('ON', 'OFF', 'EXCITATION'))
    button(2, 33, 51, 'b_excon', 'EXC ON'); button(2, 39, 51, 'b_excoff', 'EXC OFF')
    D.tape(48, 51, 9, 4.2, 'PF 0.97|PER UTIL')
    D.section(1.5, 62, 53, 31, 'SPILLWAY - POND LEVEL CONTROL')
    edge(2, 5, 76, 'HEADWATER|EL FT', (509, 515, 1, 0.25, 'EL', (514, 515), lambda x: f'{x:g}'), ptr='p_hw')
    edge(2, 12.5, 76, 'SPILL GATE|OPEN FT', (0, 4, 1, 0.25, 'FT'), ptr='p_spill')
    lampw(2, 24, 67, 'LP_sg', ('OPEN', 'CLOSED', 'SPILL GATE'))
    rot(2, 24, 77, 'r_spa'); lampw(2, 24, 83, 'L_spa', ('SPILL AUTO',))
    button(2, 21, 89, 'b_spraise', 'RAISE'); button(2, 27, 89, 'b_splower', 'LOWER')
    rot(2, 40, 69, 'r_ctl'); lampw(2, 40, 75, 'L_ctl', ('LEVEL CTL|ACTIVE',))
    D.tape(41, 85, 16, 4.6, 'PLC HOLDS 512.75-513.25|SPILLS ABOVE 513.5')

    # door tiles -> world brushes
    for ci, Dr in enumerate(doors):
        names = Dr.tiles(f'scd{ci}')
        x0 = CX0[ci] + 2
        for t, nm in enumerate(names):
            zt = DOOR_TOP - t * 24
            W(x0, -0.5, zt - 24, x0 + DOOR_W, 0, zt, tex='sc_paintd', faces={FRONT: (nm, face_map(x0, zt, PPU))})

    # instructor console on the desk
    im = Image.new('RGBA', (320, 144), (40, 44, 46, 255)); d = ImageDraw.Draw(im)
    text(d, im, (160, 12), 'INSTRUCTOR', 13, (233, 182, 28, 255))
    cons = []
    for k, (nm, lab) in enumerate([('b_riverup', 'RIVER +'), ('b_riverdn', 'RIVER -'), ('b_flood', 'FLOOD'), ('b_util', 'UTILITY|TRIP')]):
        cx = 40 + k * 64
        for i, ln in enumerate(lab.split('|')):
            text(d, im, (cx, 34 + i * 12), ln, 11, (236, 234, 226, 255))
        cons.append((nm, 85 + cx / 8, -150 - 80 / 8))
    text(d, im, (160, 100), 'OIL PUMPS:  OK  /  FAIL', 11, (236, 234, 226, 255))
    TEX['sc_console'] = im.convert('RGB')
    W(85, -168, 40, 125, -150, 44, tex='sc_deskm', faces={UP: ('sc_console', face_map_up(85, -150, 8))})
    for nm, x, y in cons:
        b = buttons[nm]
        tex = {'black': 'sc_btn_k', 'amber': 'sc_btn_a'}[b['color']]
        E.append({'classname': 'func_button', 'targetname': nm, 'target': b['target'], 'angle': '-2', 'speed': '40', 'lip': '-1.4',
                  'wait': '0.6', 'sounds': '9', '_brushes': [Box(x - 1.3, y - 1.3, 44, x + 1.3, y + 1.3, 45.2, tex=tex)]})
    r = rots['r_pfail']
    E.append({'classname': 'func_rot_button', 'targetname': 'r_pfail', 'target': r['target'], 'spawnflags': '32', 'distance': '90',
              'speed': '240', 'wait': '-1', 'sounds': '21',
              '_brushes': [Box(103.3, -166.45, 44, 106.7, -165.55, 45.2, tex='sc_knob'), Box(104.75, -166.25, 44, 105.25, -165.75, 44.2, tex='ORIGIN')]})
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
    pos = {'s_turb': '0 10 20', 's_water': '0 20 10', 's_hum': '0 10 60', 's_horn': '50 10 116', 's_pump': '-60 10 20',
           's_brk': '0 -2 60', 's_relay': '50 -2 80'}
    snd = []
    for s in dev['sounds']:
        sf = 16 | (0 if s['loop'] else 32) | 4       # start silent, medium radius
        snd.append({'classname': 'ambient_generic', 'targetname': s['name'], 'message': s['wav'], 'health': str(s['vol']),
                    'pitch': '100', 'pitchstart': '100', 'spawnflags': str(sf), 'origin': pos[s['name']]})
    for e in logic:                      # trim the entity lump: defaults need no key
        if e['classname'] == 'game_counter_set' and e.get('frags') == '0':
            del e['frags']
    all_ents = ents + panel_ents + snd + logic
    write_map(os.path.join(OUT, 'sablecreek.map'), world, all_ents)
    write_wad(os.path.join(OUT, 'sablecreek.wad'), TEX)
    open(os.path.join(OUT, 'lights.rad'), 'w').write('sc_light 255 244 226 700\n')
    make_sounds(os.path.join(OUT, 'sound', 'sablecreek'))
    brush_models = sum(1 for e in all_ents if e.get('_brushes'))
    print(f'{len(all_ents)} entities ({len(logic)} logic, {brush_models} brush models, {len(snd)} sounds), '
          f'{len(world)} world brushes, {len(TEX)} textures')
    return all_ents, dev


if __name__ == '__main__':
    main()
