"""
The room's furniture as studio models: fire extinguisher, wall clock, desk, chair, door lever and hinges.
Units are map units (1 unit = 0.75 in). Wall-mounted parts face -Y with their origin on the wall; the desk
and chair stand on the floor with their origin at the middle of their footprint, the sitter facing +Y.
"""
import math
import numpy as np
from srcmdl import MeshBuilder

MATERIALS = {
    'sc_m_ext': ((184, 22, 18), False),         # extinguisher red
    'sc_m_desk': ((122, 128, 122), False),      # desk steel, grey-green enamel
    'sc_m_vinyl': ((38, 40, 46), False),        # chair upholstery
    'sc_m_steel': ((158, 162, 160), False),     # brushed steel
}

UP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])       # stands a part made about the panel normal upright


def upright(mat, profile, seg=20, at=(0, 0, 0), mats=None):
    """solid of revolution about a vertical axis through `at`; profile: (radius, height) from the bottom up"""
    mb = MeshBuilder()
    mb.revolve(mat, profile, seg, mats=mats)
    return mb.transform(UP, at)


def tube(mat, path, r, seg=10):
    """round tube along a path of 3-D points"""
    P = [np.array(p, float) for p in path]
    secs = []
    for i, p in enumerate(P):
        t = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        a = np.cross(t, (0, 0, 1) if abs(t[2]) < 0.9 else (1, 0, 0)); a /= np.linalg.norm(a)
        b = np.cross(t, a)
        secs.append([p + r * (math.cos(2 * math.pi * k / seg) * a + math.sin(2 * math.pi * k / seg) * b) for k in range(seg)])
    mb = MeshBuilder()
    mb.loft(mat, secs)
    return mb


def rrect(hx, hy, r, n=4):
    """rounded rectangle, half sizes hx, hy, counter-clockwise"""
    pts = []
    for cx, cy, a0 in ((hx - r, hy - r, 0), (-(hx - r), hy - r, 90), (-(hx - r), -(hy - r), 180), (hx - r, -(hy - r), 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def extinguisher():
    """10 lb dry chemical extinguisher on its wall bracket: 5 in shell, valve, lever, gauge and hose"""
    mb = MeshBuilder()
    Y = -4.1                                             # the shell's axis stands this far off the wall
    shell = [(0.0, 0.0), (3.0, 0.0), (3.35, 0.5), (3.35, 7.0), (3.36, 7.0), (3.36, 12.0), (3.35, 12.0), (3.35, 15.2),
             (3.0, 16.6), (2.0, 17.7), (1.1, 18.2), (1.1, 19.0)]
    mats = ['sc_m_black', 'sc_m_ext', 'sc_m_ext', 'sc_m_ext', 'sc_m_white', 'sc_m_ext', 'sc_m_ext', 'sc_m_ext', 'sc_m_ext',
            'sc_m_ext', 'sc_m_chrome']
    mb.merge(upright('sc_m_ext', shell, 24, (0, Y, 0), mats))
    mb.merge(upright('sc_m_chrome', [(1.0, 19.0), (1.0, 20.4), (0.0, 20.4)], 14, (0, Y, 0)))        # valve body
    mb.box('sc_m_black', (-0.55, Y - 4.2, 20.4), (0.55, Y + 0.9, 20.8))                              # squeeze lever
    mb.box('sc_m_black', (-0.55, Y - 3.6, 19.0), (0.55, Y + 0.9, 19.4))                              # carry handle
    g = MeshBuilder()                                                                                  # pressure gauge
    g.revolve('sc_m_chrome', [(0.75, 0.0), (0.75, 0.5), (0.6, 0.6)], 14)
    g.disc_cap('sc_m_white', 0.6, 0.6, 14)
    mb.merge(g.transform(np.eye(3), (0, Y - 1.0, 19.7)))
    mb.merge(tube('sc_m_black', [(1.0, Y, 19.7), (2.3, Y - 0.4, 19.5), (3.6, Y - 1.2, 17.8), (4.0, Y - 1.6, 14.0),
                                 (4.0, Y - 1.6, 7.0)], 0.5))
    mb.merge(upright('sc_m_black', [(0.0, 0.0), (0.75, 0.0), (0.55, 2.6), (0.0, 2.6)], 10, (4.0, Y - 1.6, 4.6)))   # nozzle
    mb.box('sc_m_steel', (-1.3, -0.6, 2.0), (1.3, 0.0, 19.0))                                        # bracket
    mb.box('sc_m_steel', (-3.7, Y - 0.2, 13.2), (3.7, -0.3, 13.9))                                   # strap
    mb.box('sc_m_steel', (-1.6, Y, -0.5), (1.6, 0.0, 0.0))                                           # foot
    return mb


def clock_face():
    from PIL import Image, ImageDraw, ImageFont
    S = 256; c = S / 2
    im = Image.new('RGB', (S, S), (244, 242, 234)); d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype('LiberationSans-Bold.ttf', 30)
    except OSError:
        font = ImageFont.load_default()
    for i in range(60):
        a = i / 60 * 2 * math.pi
        r0 = 112 if i % 5 else 104
        d.line([(c + 120 * math.sin(a), c - 120 * math.cos(a)), (c + r0 * math.sin(a), c - r0 * math.cos(a))],
               fill=(20, 20, 20), width=5 if i % 5 == 0 else 2)
    for h in range(1, 13):
        a = h / 12 * 2 * math.pi
        d.text((c + 84 * math.sin(a), c - 84 * math.cos(a)), str(h), font=font, fill=(20, 20, 20), anchor='mm')
    for a, ln, w in ((4.2, 54, 9), (1.0, 86, 6)):                       # hands
        d.line([(c - 14 * math.sin(a), c + 14 * math.cos(a)), (c + ln * math.sin(a), c - ln * math.cos(a))], fill=(18, 18, 18), width=w)
    d.ellipse([c - 7, c - 7, c + 7, c + 7], fill=(18, 18, 18))
    return im


def clock():
    """12 in wall clock: black case, white dial"""
    mb = MeshBuilder()
    mb.revolve('sc_m_black', [(8.0, 0.0), (8.0, 1.5), (7.5, 1.9), (7.1, 1.9), (6.9, 1.1)], 40)
    mb.disc_cap('sc_m_clock', 6.95, 1.1, 40)
    return mb


def laminate():
    """desk top: walnut-grain laminate"""
    from PIL import Image
    rng = np.random.default_rng(11)
    S = 256
    y, x = np.mgrid[0:S, 0:S] / S
    warp = 0.02 * np.sin(2 * np.pi * (3 * x + rng.random())) + 0.012 * np.sin(2 * np.pi * (7 * x + rng.random()))
    g = np.sin(2 * np.pi * 26 * (y + warp)) * 0.5 + np.sin(2 * np.pi * 61 * (y + 1.7 * warp)) * 0.3
    g += rng.normal(0, 0.25, (S, 1)) + rng.normal(0, 0.1, (S, S))
    base = np.array([112, 78, 50], float)
    img = base[None, None, :] * (1 + 0.11 * g[..., None])
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')


def desk():
    """steel office desk, 55 x 27 in, 30 in high: laminate top with a steel rim, a three-drawer pedestal on the
    right, a centre drawer, a panel leg on the left and a modesty panel at the back"""
    mb = MeshBuilder()
    S, K = 'sc_m_desk', 'sc_m_chrome'
    x0, x1, y0, y1 = -37.0, 37.0, -18.0, 18.0
    for f, n in ((((x0, y0, 40), (x1, y0, 40), (x1, y1, 40), (x0, y1, 40)), (0, 0, 1)),):
        mb.flat('sc_m_laminate', list(f), uvs=[(0, 1), (2, 1), (2, 0), (0, 0)], normal=n)
    mb.box('sc_m_black', (x0, y0, 38.9), (x1, y1, 39.99))                 # edge band
    mb.box(S, (x0 + 0.5, y0 + 0.5, 37.4), (x1 - 0.5, y1 - 0.5, 38.9))    # rim
    mb.box(S, (13.0, -16.0, 3.5), (35.5, 16.0, 37.4))                     # pedestal
    mb.box('sc_m_black', (14.0, -15.0, 0.0), (34.5, 15.0, 3.5))           # its recessed base
    for z0, z1 in ((28.8, 36.6), (20.2, 28.0), (4.6, 19.4)):              # two box drawers and a file drawer
        mb.box(S, (14.0, -16.6, z0), (34.5, -16.0, z1))
        zc = z1 - 2.2
        mb.box(K, (20.0, -17.5, zc - 0.35), (28.5, -17.2, zc + 0.35))
        for xs in (20.4, 28.1):
            mb.box(K, (xs - 0.4, -17.2, zc - 0.3), (xs + 0.4, -16.6, zc + 0.3))
    mb.box(S, (-30.0, -16.6, 33.6), (10.0, -16.0, 37.2))                  # centre drawer
    mb.box(K, (-14.0, -17.5, 35.0), (-6.0, -17.2, 35.7))
    for xs in (-13.6, -6.4):
        mb.box(K, (xs - 0.4, -17.2, 35.05), (xs + 0.4, -16.6, 35.65))
    mb.box(S, (-30.0, -16.0, 33.6), (10.0, 14.0, 37.4))
    mb.box(S, (-35.5, -15.0, 1.0), (-34.0, 15.0, 37.4))                   # panel leg
    mb.box('sc_m_black', (-36.0, -15.5, 0.0), (-33.5, 15.5, 1.0))
    mb.box(S, (-34.0, 14.0, 12.0), (13.0, 15.0, 37.4))                    # modesty panel
    return mb


def chair():
    """swivel task chair: upholstered seat and back, steel post, five-star base on casters"""
    mb = MeshBuilder()
    V = 'sc_m_vinyl'
    sec = lambda hx, hy, r, z: [(x, y, z) for x, y in rrect(hx, hy, r)]
    mb.loft(V, [sec(8.6, 8.2, 2.4, 19.0), sec(9.6, 9.2, 2.8, 19.8), sec(9.6, 9.2, 2.8, 21.4), sec(8.8, 8.4, 2.6, 22.2)])
    back = lambda hx, hz, r, y: [(x, y, 34.0 + z) for x, z in rrect(hx, hz, r)][::-1]
    mb.loft(V, [back(8.2, 6.2, 2.4, -11.3), back(9.0, 7.0, 2.8, -10.5), back(9.0, 7.0, 2.8, -9.7), back(8.2, 6.2, 2.4, -9.0)])
    mb.box('sc_m_black', (-1.3, -11.6, 18.2), (1.3, -10.9, 30.0))        # back support
    mb.box('sc_m_black', (-1.3, -11.6, 17.4), (1.3, -2.0, 18.2))
    mb.box('sc_m_black', (-5.0, -5.0, 17.6), (5.0, 5.0, 19.0))            # seat pan
    mb.merge(upright('sc_m_chrome', [(0.0, 0.0), (1.0, 0.0), (1.0, 10.5), (0.0, 10.5)], 14, (0, 0, 7.2)))
    mb.merge(upright('sc_m_black', [(0.0, 0.0), (2.0, 0.0), (2.0, 3.0), (1.3, 3.8), (0.0, 3.8)], 16, (0, 0, 3.6)))   # hub
    for k in range(5):
        a = math.radians(90 + 72 * k)
        c, s = math.cos(a), math.sin(a)
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        leg = MeshBuilder()
        leg.box('sc_m_black', (1.5, -0.9, 3.4), (11.5, 0.9, 4.8))
        cast = upright('sc_m_black', [(0.0, 0.0), (1.2, 0.3), (1.3, 1.7), (0.6, 3.2), (0.0, 3.4)], 10, (10.6, 0, 0))
        mb.merge(leg.transform(R)); mb.merge(cast.transform(R))
    return mb


def lever():
    """door lever on a round rose, for a door facing -Y: the lever points -X (towards the hinges)"""
    mb = MeshBuilder()
    mb.revolve('sc_m_steel', [(1.7, 0.0), (1.7, 0.35), (1.5, 0.55), (0.7, 0.55), (0.7, 2.6), (0.0, 2.6)], 20)
    mb.merge(tube('sc_m_steel', [(0.0, -2.2, 0.0), (-1.2, -2.3, 0.0), (-5.0, -2.3, 0.0), (-6.0, -2.0, 0.0)], 0.55, 10))
    return mb


def butt_hinge():
    """4.5 in butt hinge knuckle on the door's edge"""
    return upright('sc_m_steel', [(0.0, 0.0), (0.45, 0.0), (0.45, 6.0), (0.0, 6.0)], 10, (0, -0.45, -3.0))


TEXTURES = {'sc_m_clock': clock_face, 'sc_m_laminate': laminate}
PARTS = {'extinguisher': extinguisher, 'clock': clock, 'desk': desk, 'chair': chair, 'lever': lever, 'butt_hinge': butt_hinge}
