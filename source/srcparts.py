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
}

GR = 4.0                   # dial radius the meter window shows


def rot_y(deg):
    """rotation about Y (the panel normal): +deg turns a part counter-clockwise as you face the panel"""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])


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


def pistol(mat='sc_m_black'):
    """Control-switch pistol grip, turned 45 degrees anticlockwise (its left position). Origin: the
    switch's pivot (world y = -2.1); the grip runs from y = +0.8 (on the boss) to -0.8."""
    mb = MeshBuilder()
    # half width along the grip (pointing up): hub end at z = -1.7, tip at z = 3.3
    prof = [(-1.7, 0.45), (-1.4, 0.75), (-1.0, 0.88), (-0.2, 0.96), (0.6, 0.92), (1.4, 0.78), (2.1, 0.56), (2.7, 0.36), (3.15, 0.16)]
    secs = []
    for z, hw in prof:
        hd = 0.8 * (0.75 + 0.25 * hw / 0.96)        # a little thinner towards the tip
        sec = []
        for k in range(16):
            a = 2 * math.pi * k / 16
            cx, cy = math.cos(a), math.sin(a)
            sx = math.copysign(abs(cx) ** 0.6, cx); sy = math.copysign(abs(cy) ** 0.6, cy)   # rounded box section
            sec.append((hw * sx, (0.8 - hd) - hd * sy, z))            # back face on the boss at y = +0.8
        secs.append(sec)
    mb.loft(mat, secs)
    mb.revolve(mat, [(0.0, -0.8), (1.0, -0.8), (1.05, -0.4), (1.05, 0.5), (0.0, 0.5)], 24)   # hub
    return mb.transform(rot_y(45))


def knob():
    """Round knurled knob with a white pointer line at 12 o'clock. Origin: the knob's pivot (world
    y = -1.5); it sits on its escutcheon at y = +0.5 and stands 2 out to y = -1.5."""
    mb = MeshBuilder()
    y0 = 0.5
    N = 40
    # skirt, then a fluted body (alternate radii give the knurl), then a chamfered top
    mb.revolve('sc_m_black', [(0.0, 0.0), (1.95, 0.0), (1.95, 0.35), (1.7, 0.55)], N, y0=y0)
    ring = []
    for k in range(N):
        a = 2 * math.pi * k / N
        r = 1.55 if k % 2 == 0 else 1.47
        ring.append((r * math.cos(a), r * math.sin(a)))
    bot = [(x, y0 - 0.55, z) for x, z in ring]; topr = [(x * 0.95, y0 - 1.75, z * 0.95) for x, z in ring]
    mb.loft('sc_m_black', [bot, topr])
    mb.revolve('sc_m_black', [(1.47, 1.75), (1.3, 1.95), (0.0, 1.95)], N, y0=y0)
    mb.box('sc_m_white', (-0.11, y0 - 2.0, 0.25), (0.11, y0 - 1.93, 1.28))               # pointer line on the face
    mb.box('sc_m_white', (-0.11, y0 - 1.95, 1.28), (0.11, y0 - 0.6, 1.45))               # and down the side
    return mb


def barknob():
    """Selector-switch bar handle (brakes, spillway mode): a bar across a round hub, the top end white.
    Origin: the pivot (world y = -1.1); the handle stands from y = -0.3 to -1.6."""
    mb = MeshBuilder()
    mb.revolve('sc_m_black', [(0.0, 0.3), (1.15, 0.3), (1.15, 0.9), (1.0, 1.05), (0.0, 1.05)], 28)
    def section(z, hw, mat):
        return [(hw * math.copysign(abs(math.cos(a)) ** 0.5, math.cos(a)), -0.95 - 0.55 * math.copysign(abs(math.sin(a)) ** 0.5, math.sin(a)), z)
                for a in (2 * math.pi * k / 12 for k in range(12))]
    mb.loft('sc_m_black', [section(z, hw, None) for z, hw in ((-2.75, 0.45), (-2.5, 0.65), (1.4, 0.65))])
    mb.loft('sc_m_white', [section(z, hw, None) for z, hw in ((1.4, 0.65), (2.6, 0.5), (2.8, 0.3))])
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


def boss(r):
    """Chrome boss a switch or knob turns on. Origin: on its escutcheon (world y = -1.0)."""
    mb = MeshBuilder()
    mb.revolve('sc_m_chrome', [(r, 0.0), (r, 0.3), (r - 0.18, 0.48), (0.0, 0.48)], 32)
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


PARTS = {
    'meter': meter,
    'needle': lambda: needle(GR - 0.45),
    'needle_scope': lambda: needle(GR - 0.5, tail=1.3, w=0.3, hub=0.55),
    'pistol': pistol,
    'pistol_red': lambda: pistol('sc_m_red'),
    'knob': knob,
    'barknob': barknob,
    'button_amber': lambda: button('sc_m_amber'),
    'button_black': lambda: button('sc_m_black'),
    'lamp_bezel': lamp_bezel,
    'boss': lambda: boss(1.35),
    'boss_l': lambda: boss(1.5),
    'pb_bezel': pb_bezel,
    'hinge': hinge,
    'latch': latch,
}
