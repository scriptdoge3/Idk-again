"""
The panel hardware as studio models (see srcmdl.py). Units are map units (1 unit = 0.75 in). Model space:
the part faces -Y, Z up, X to the right as you face the panel; each part's origin is the point it is
mounted or pivots on, noted below with the world Y it sits at on a cabinet door (door front y = -0.5).

Fixed parts are prop_static; moving parts are prop_dynamic parented to the brush entity that moves (the
brush is still there for the player to use, but not drawn).
"""
import math
import numpy as np
from srcmdl import MeshBuilder

# material -> (colour, unlit)
MATERIALS = {
    'sc_m_black': ((26, 26, 28), False),        # bakelite
    'sc_m_dark': ((58, 58, 62), False),
    'sc_m_chrome': ((200, 202, 205), False),
    'sc_m_white': ((238, 236, 226), False),
    'sc_m_red': ((178, 26, 22), False),
    'sc_m_amber': ((238, 122, 24), False),
    'sc_m_needle': ((255, 104, 44), True),
    'sc_m_steel': ((158, 162, 160), False),     # brushed steel / spun aluminium
}

GR = 4.0                   # dial radius the meter window shows


def meter():
    """Switchboard meter: square black flange 9.5 across with a round window, and a raised round bezel.
    Origin: dial centre on the door front (world y = -0.5). The dial face (a brush) shows through the window."""
    mb = MeshBuilder()
    S, RW, T, N = 4.75, GR, 0.75, 48
    ang = [2 * math.pi * k / N for k in range(N + 1)]
    circ = lambda a, y: (RW * math.cos(a), y, RW * math.sin(a))
    def sq(a, y):
        dx, dz = math.cos(a), math.sin(a)
        f = S / max(abs(dx), abs(dz))
        return (dx * f, y, dz * f)
    for k in range(N):                          # flange front: between the square edge and the window
        a0, a1 = ang[k], ang[k + 1]
        mb.flat('sc_m_black', [sq(a0, -T), circ(a0, -T), circ(a1, -T), sq(a1, -T)], normal=(0, -1, 0))
    for (x0, z0), (x1, z1), n in (((-S, -S), (S, -S), (0, 0, -1)), ((S, -S), (S, S), (1, 0, 0)),
                                  ((S, S), (-S, S), (0, 0, 1)), ((-S, S), (-S, -S), (-1, 0, 0))):
        mb.flat('sc_m_black', [(x0, 0, z0), (x1, 0, z1), (x1, -T, z1), (x0, -T, z0)], normal=n)
    # bezel ring round the window: chrome inner lip, black rounded rim
    mb.revolve('sc_m_black', [(4.72, T), (4.72, T + 0.55), (4.6, T + 0.85), (4.35, T + 1.0), (4.15, T + 0.95),
                              (4.05, T + 0.8), (RW, T + 0.6), (RW, 0.0)], N,
               mats=['sc_m_black', 'sc_m_black', 'sc_m_black', 'sc_m_black', 'sc_m_chrome', 'sc_m_chrome', 'sc_m_dark'])
    return mb


def needle(length, tail=0.9, w=0.22, hub=0.45):
    """Meter pointer: a thin tapered blade, a counterweight and a hub. Origin: the pivot (world y = -1.6,
    0.5 in front of the dial). Points up (+Z); the brush entity's angles turn it."""
    mb = MeshBuilder()
    t = 0.06
    def plate(mat, poly):
        for y, n in ((-t, (0, -1, 0)), (t, (0, 1, 0))):
            mb.flat(mat, [(x, y, z) for x, z in poly], normal=n)
        cz = sum(z for _, z in poly) / len(poly)
        for k in range(len(poly)):
            (x0, z0), (x1, z1) = poly[k], poly[(k + 1) % len(poly)]
            e = np.array([x1 - x0, 0, z1 - z0]); n = np.cross(e, (0, 1, 0)); n /= np.linalg.norm(n) or 1
            if np.dot(n, [(x0 + x1) / 2, 0, (z0 + z1) / 2 - cz]) < 0:
                n = -n
            mb.flat(mat, [(x0, -t, z0), (x1, -t, z1), (x1, t, z1), (x0, t, z0)], normal=n)
    plate('sc_m_needle', [(-w * 0.8, -0.2), (w * 0.8, -0.2), (0.05, length), (-0.05, length)])   # pointer
    plate('sc_m_dark', [(-0.09, -tail), (0.09, -tail), (0.09, -0.2), (-0.09, -0.2)])           # tail
    mb.revolve('sc_m_dark', [(0.0, -0.1), (0.3, -0.1), (0.3, 0.1), (0.0, 0.1)], 16, center=(0, -tail))   # counterweight
    mb.revolve('sc_m_dark', [(0.0, -0.05), (hub, -0.05), (hub, 0.2), (hub * 0.7, 0.3), (0.0, 0.3)], 20)  # hub cap
    return mb


def knob(k=1.0):
    """Instrument knob: a spun-aluminium skirt with a white index line, a fluted black body and an aluminium
    cap with a black pointer; 12 o'clock is up. k scales its radius. Origin: the knob's pivot (world y = -1.5);
    it sits on its plate at y = +0.5 and stands 2 out."""
    mb = MeshBuilder()
    y0 = 0.5
    S, K = 'sc_m_steel', 'sc_m_black'
    rs, rb = 2.0 * k, 1.5 * k                            # skirt and body radii
    mb.revolve(S, [(0.0, 0.0), (rs, 0.0), (rs, 0.12), (rb + 0.2, 0.5), (rb - 0.05, 0.5)], 36, y0=y0)
    N, L = 72, 12                                        # twelve flutes
    def ring(scale, h):
        out = []
        for j in range(N):
            a = 2 * math.pi * j / N
            r = scale * (rb - 0.13 * k * (0.5 - 0.5 * math.cos(L * a)) ** 1.5)
            out.append((r * math.cos(a), y0 - h, r * math.sin(a)))
        return out
    mb.loft(K, [ring(1.0, 0.5), ring(1.0, 0.7), ring(0.97, 1.8), ring(0.9, 1.97)])
    rc = 0.6 * rb
    mb.revolve(S, [(rc, 1.97), (rc, 2.03), (0.0, 2.03)], 28, y0=y0)                      # cap
    mb.box(K, (-0.09 * k, y0 - 2.05, 0.15 * rc), (0.09 * k, y0 - 2.03, 0.96 * rc))        # pointer on the cap
    n = np.array([0.0, -0.59, 0.81]) * 0.012                                              # index line on the skirt
    q = [(-0.1 * k, y0 - 0.13, rs), (0.1 * k, y0 - 0.13, rs), (0.1 * k, y0 - 0.5, rb + 0.2), (-0.1 * k, y0 - 0.5, rb + 0.2)]
    mb.flat('sc_m_white', [tuple(np.array(p) + n) for p in q], normal=(0, -0.59, 0.81))
    return mb


def button(mat):
    """Pushbutton cap: a short cylinder with a domed face. Origin: the cap face centre (world y = -2.6);
    the cap runs back into its bezel to y = +1.6."""
    mb = MeshBuilder()
    mb.revolve(mat, [(0.0, -1.6), (1.32, -1.6), (1.32, -0.1), (1.25, 0.05), (1.0, 0.18), (0.55, 0.25), (0.0, 0.27)], 32)
    return mb


def lamp_bezel():
    """Indicating-lamp bezel: a black ring with a chrome lip round the lens. Origin: the lens centre on the
    door front (world y = -0.5); the lens shows through it, its face 0.15 back from the lip."""
    mb = MeshBuilder()
    mb.revolve('sc_m_black', [(1.45, 0.0), (1.45, 0.75), (1.3, 1.0), (1.08, 1.12)], 28)
    mb.revolve('sc_m_chrome', [(1.08, 1.12), (0.98, 1.1), (0.95, 0.95), (0.95, 0.0)], 28)
    return mb


def pb_bezel():
    """Pushbutton bezel: a chrome ring the cap travels in. Origin: the door front (world y = -0.5)."""
    mb = MeshBuilder()
    mb.revolve('sc_m_chrome', [(1.95, 0.0), (1.95, 0.35), (1.8, 0.6), (1.5, 0.66), (1.4, 0.55), (1.4, 0.0)], 36)
    return mb


def hinge():
    """Barrel hinge, two knuckles on a pin, vertical. Origin: the middle of the barrel."""
    mb = MeshBuilder()
    mb.merge(_cyl_z('sc_m_chrome', 0.45, -3.0, -0.08)).merge(_cyl_z('sc_m_chrome', 0.45, 0.08, 3.0))
    mb.merge(_cyl_z('sc_m_dark', 0.3, -3.25, 3.25))
    return mb


def _cyl_z(mat, r, z0, z1, seg=16):
    m = MeshBuilder()
    m.revolve(mat, [(0.0, 0.0), (r, 0.0), (r, z1 - z0), (0.0, z1 - z0)], seg)
    # built along -Y from 0: turn it to run along +Z from z0
    return m.transform([[1, 0, 0], [0, 0, 1], [0, -1, 0]], (0, 0, z0))       # (x, y, z) -> (x, z, -y): a rotation


def latch():
    """Cabinet latch: a chrome escutcheon with a swing handle. Origin: on the door front (world y = -0.5),
    at the middle of the escutcheon."""
    mb = MeshBuilder()
    mb.box('sc_m_chrome', (-1.0, -0.35, -6.0), (1.0, 0.0, 6.0))
    mb.revolve('sc_m_chrome', [(0.0, 0.35), (0.7, 0.35), (0.7, 0.75), (0.0, 0.75)], 20, center=(0, 4.2))   # key cylinder
    mb.revolve('sc_m_dark', [(0.0, 0.74), (0.3, 0.74), (0.3, 0.8), (0.0, 0.8)], 12, center=(0, 4.2))
    secs = []
    for z, hw, d in ((-4.6, 0.38, 1.1), (-4.2, 0.5, 1.5), (2.4, 0.5, 1.5), (2.9, 0.42, 1.25)):
        secs.append([(hw * math.copysign(abs(math.cos(a)) ** 0.5, math.cos(a)), -0.35 - d / 2 - d / 2 * math.copysign(abs(math.sin(a)) ** 0.5, math.sin(a)), z)
                     for a in (2 * math.pi * k / 12 for k in range(12))])
    mb.loft('sc_m_dark', secs)
    return mb


# ------------------------------------------------------------------ breaker control switch (SB style)
SB_H = 2.9                 # escutcheon half size as first drawn
K_SW = 1.15                # the control switches and spring dials are this much bigger across (5 in plates)
K_LAMP = 1.25              # and the indicating lamps and pushbuttons this much (2.7 in bezels)


def scaled(mb, k):
    """a part made k times bigger across the panel (its depth unchanged), normals kept true"""
    for verts, lookup, idx in mb.parts.values():
        for i, (p, n, uv) in enumerate(verts):
            n2 = np.array([n[0] / k, n[1], n[2] / k]); n2 /= (np.linalg.norm(n2) or 1)
            verts[i] = ((p[0] * k, p[1], p[2] * k), tuple(n2), uv)
        lookup.clear()
    return mb


def rounded_square(h, r, n=6):
    pts = []
    for cx, cz, a0 in ((h - r, h - r, 0), (-(h - r), h - r, 90), (-(h - r), -(h - r), 180), (h - r, -(h - r), 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return pts


def sb_plate(face, H=SB_H):
    """Control escutcheon: a black plate (half size H) with a bevelled edge, its engraved face as a texture, and
    four screws. Origin: the centre on the door front (world y = -0.5); the face is at y = -0.5."""
    mb = MeshBuilder()
    T, B = 0.5, 0.1
    back = rounded_square(H, 0.45); front = rounded_square(H - B, 0.45 - B)
    n = len(back)
    for k in range(n):
        a0, a1 = back[k], back[(k + 1) % n]; b0, b1 = front[k], front[(k + 1) % n]
        mid = np.array([(a0[0] + a1[0]) / 2, 0, (a0[1] + a1[1]) / 2])
        nrm = mid / np.linalg.norm(mid) + np.array([0, -0.6, 0])
        mb.flat('sc_m_black', [(a0[0], 0, a0[1]), (a1[0], 0, a1[1]), (b1[0], -T, b1[1]), (b0[0], -T, b0[1])], normal=nrm)
    uv = [((x + H) / (2 * H), (H - z) / (2 * H)) for x, z in front]
    mb.flat(face, [(x, -T, z) for x, z in front], uvs=uv, normal=(0, -1, 0))
    for sx in (-1, 1):
        for sz in (-1, 1):
            mb.revolve('sc_m_screw', [(0.3, 0.0), (0.3, 0.06), (0.22, 0.16), (0.0, 0.19)], 14,
                       center=(sx * (H - 0.55), sz * (H - 0.55)), y0=-T)
    return mb


KP_FA = 4.3                # the firing-angle knob's plate, half size: a meter's width


def knob_face_texture(kind):
    """the engraved face of a knob's plate, white on black. 'spring': a spring-return dial, with its rest mark
    at 12 o'clock, its stop 60 degrees clockwise and an arrow between them. 'fa': the firing-angle scale, 90
    degrees at the left stop to 0 at the right, 300 degrees of travel."""
    from PIL import Image, ImageDraw, ImageFont
    H = SB_H if kind == 'spring' else KP_FA
    S = 256 if kind == 'spring' else 512
    ppu = S / (2 * H); c = S / 2
    W = (238, 236, 228)
    im = Image.new('RGB', (S, S), (20, 20, 21)); d = ImageDraw.Draw(im)
    inset = 0.32 * ppu
    d.rounded_rectangle([inset, inset, S - inset, S - inset], radius=int(0.3 * ppu), outline=(196, 198, 200), width=max(2, S // 86))
    pt = lambda r, a: (c + r * ppu * math.sin(math.radians(a)), c - r * ppu * math.cos(math.radians(a)))   # a clockwise from 12
    if kind == 'spring':
        for a in (0, 60):
            d.line([pt(2.12, a), pt(2.62, a)], fill=W, width=4)
        r = 2.37 * ppu
        d.arc([c - r, c - r, c + r, c + r], -90 + 7, -90 + 46, fill=W, width=3)
        tip, b0, b1 = pt(2.37, 54), pt(2.2, 44), pt(2.54, 44)
        d.polygon([tip, b0, b1], fill=W)
    else:
        try:
            font = ImageFont.truetype('DejaVuSans-Bold.ttf', 30)
            small = ImageFont.truetype('DejaVuSans-Bold.ttf', 20)
        except OSError:
            font = small = ImageFont.load_default()
        for k in range(10):                             # every 10 degrees of firing angle, 90 down to 0
            a = -150 + 300 * k / 9
            major = k % 3 == 0
            d.line([pt(2.8, a), pt(3.36 if major else 3.12, a)], fill=W, width=7 if major else 4)
            if major:
                d.text(pt(3.78, a), str(90 - 10 * k), font=font, fill=W, anchor='mm')
        r = 2.8 * ppu
        d.arc([c - r, c - r, c + r, c + r], -90 - 150, -90 + 150, fill=W, width=4)
        d.text(pt(3.55, 180), 'DEG', font=small, fill=W, anchor='mm')
    return im


def sb_face_texture(words, window=True):
    """the engraved face of a control switch, 256 px across the plate: the two positions on an arc and the
    target window"""
    from PIL import Image, ImageDraw, ImageFont
    S = 256; ppu = S / (2 * SB_H); c = S / 2
    im = Image.new('RGB', (S, S), (20, 20, 21)); d = ImageDraw.Draw(im)
    inset = (0.42 - 0.1) * ppu
    d.rounded_rectangle([inset, inset, S - inset, S - inset], radius=int(0.3 * ppu), outline=(196, 198, 200), width=3)
    if window:                                          # target window: a sector above the shaft, framed
        r0, r1, a = 1.05 * ppu, 1.75 * ppu, 20
        d.pieslice([c - r1 - 4, c - r1 - 4, c + r1 + 4, c + r1 + 4], -90 - a - 3, -90 + a + 3, fill=(196, 198, 200))
        d.pieslice([c - r1, c - r1, c + r1, c + r1], -90 - a, -90 + a, fill=(8, 8, 8))
        d.ellipse([c - r0 + 4, c - r0 + 4, c + r0 - 4, c + r0 - 4], fill=(20, 20, 21))
    # ring round the shaft
    rr = 0.62 * ppu
    d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=(226, 224, 216), width=4)
    d.ellipse([c - rr + 5, c - rr + 5, c + rr - 5, c + rr - 5], fill=(36, 36, 38))
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', 21)
    except OSError:
        font = ImageFont.load_default()
    for word, ang, dx in ((words[0], 30, -1.42), (words[1], -30, 1.48)):
        t = Image.new('RGBA', (140, 44), (0, 0, 0, 0)); ImageDraw.Draw(t).text((70, 22), word, font=font, fill=(238, 236, 228), anchor='mm')
        if len(word) > 5:                               # long words condensed to a five-letter width
            t = t.resize((int(140 * 5.4 / len(word)), 44), Image.Resampling.LANCZOS)
        t = t.rotate(ang, resample=Image.Resampling.BICUBIC, expand=True)
        im.paste(t, (int(c + dx * ppu - t.width / 2), int(c - 1.15 * ppu - t.height / 2)), t)
    return im


def sb_flag():
    """Target flag seen through the escutcheon's window: red (skin 0) with the breaker closed, the pump
    running, AUTO selected or the lockout tripped; green (skin 1) otherwise. Origin: as the plate's; it lies just on the plate face."""
    mb = MeshBuilder()
    r0, r1, a, N = 1.08, 1.72, 18, 8
    pts = [(r1 * math.sin(math.radians(-a + 2 * a * k / N)), r1 * math.cos(math.radians(-a + 2 * a * k / N))) for k in range(N + 1)]
    pts += [(r0 * math.sin(math.radians(a - 2 * a * k / N)), r0 * math.cos(math.radians(a - 2 * a * k / N))) for k in range(N + 1)]
    for k in range(N):                                  # the sector as quads (it isn't convex as one polygon)
        q = [pts[k], pts[k + 1], pts[2 * N + 1 - (k + 1)], pts[2 * N + 1 - k]]
        mb.flat('sc_m_flag_red', [(x, -0.53, z) for x, z in q], normal=(0, -1, 0))
    return mb


def sb_handle(grip='sc_m_black'):
    """Breaker control switch handle, hanging at normal: a round shaft out of the plate and a flat grip
    hanging from its end. Origin: the switch's pivot (world y = -2.1); the plate face is at y = +1.1, the
    shaft end at y = -2.18; the grip reaches 4.4 below the pivot."""
    mb = MeshBuilder()
    mb.revolve('sc_m_black', [(0.0, 0.0), (0.5, 0.0), (0.5, 3.1), (0.4, 3.28), (0.0, 3.28)], 22, y0=1.1)
    mb.revolve('sc_m_dark', [(0.0, 3.281), (0.17, 3.281), (0.0, 3.282)], 10, y0=1.1)       # the hole in the end
    secs = []
    for z, hw in ((0.32, 0.6), (0.0, 0.66), (-1.6, 0.66), (-3.5, 0.6), (-4.1, 0.5), (-4.4, 0.28)):
        sec = []
        for k in range(14):
            ang = 2 * math.pi * k / 14
            cx, cy = math.cos(ang), math.sin(ang)
            sec.append((hw * math.copysign(abs(cx) ** 0.55, cx), -1.62 - 0.48 * math.copysign(abs(cy) ** 0.55, cy), z))
        secs.append(sec)
    mb.loft(grip, secs)
    return mb


# the engraved legends (left, right) of the control switches; each gets its face texture and plate model
SB_FACES = [('TRIP', 'CLOSE'), ('OFF', 'ON'), ('RESET', 'TRIP'), ('MAN', 'AUTO'), ('STOP', 'START'), ('OFF', 'AUTO'),
            ('RELEASE', 'APPLY')]
sb_key = lambda words: '_'.join(words).lower()
TEXTURES = {f'sc_m_sb_{sb_key(w)}': (lambda w=w: sb_face_texture(w)) for w in SB_FACES}
TEXTURES.update({'sc_m_kp_spring': lambda: knob_face_texture('spring'), 'sc_m_kp_fa': lambda: knob_face_texture('fa')})
MATERIALS.update({'sc_m_screw': ((150, 152, 155), False), 'sc_m_flag_red': ((205, 30, 24), False),
                  'sc_m_flag_green': ((24, 160, 60), False)})
SKINS = {'sb_flag': [{'sc_m_flag_red': 'sc_m_flag_green'}]}


PARTS = {
    'meter': meter,
    'needle': lambda: needle(GR - 0.45),
    'needle_scope': lambda: needle(GR - 0.5, tail=1.3, w=0.3, hub=0.55),
    'knob': lambda: knob(K_SW),
    'knob_l': lambda: knob(1.3),                  # the firing-angle knob
    'kp_spring': lambda: sb_plate('sc_m_kp_spring', SB_H * K_SW),
    'kp_fa': lambda: sb_plate('sc_m_kp_fa', KP_FA),
    'button_amber': lambda: scaled(button('sc_m_amber'), K_LAMP),
    'button_black': lambda: scaled(button('sc_m_black'), K_LAMP),
    'lamp_bezel': lambda: scaled(lamp_bezel(), K_LAMP),
    'pb_bezel': lambda: scaled(pb_bezel(), K_LAMP),
    'hinge': hinge,
    'latch': latch,
    'sb_flag': lambda: scaled(sb_flag(), K_SW),
    'sb_handle': lambda: scaled(sb_handle(), K_SW),
    'sb_handle_red': lambda: scaled(sb_handle('sc_m_red'), K_SW),   # 86U
}
PARTS.update({f'sb_plate_{sb_key(w)}': (lambda w=w: sb_plate(f'sc_m_sb_{sb_key(w)}', SB_H * K_SW)) for w in SB_FACES})
