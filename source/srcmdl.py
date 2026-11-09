"""
Studio models for Half-Life 2, written directly (there is no model compiler here): .mdl (version 48),
.vvd (version 4) and .dx90.vtx / .dx80.vtx / .sw.vtx (version 7).

Rigid props only, laid out the way studiomdl lays out a $staticprop: one bone ("static_prop"), one hitbox
set with one box, a one-frame "idle" sequence, one body part with one model, one mesh per material, and a
triangle list per mesh. The model is flagged as a static prop, so it works as a prop_static; it also works
as a prop_dynamic, parented to a moving brush entity.

    mb = MeshBuilder()
    mb.revolve('sc_m_black', [(r0, h0), (r1, h1), ...], 24)    # solid of revolution about the Y axis
    files = write_model('models/sablecreek/meter.mdl', mb)       # {path: bytes}
"""
import math, struct, zlib
import numpy as np

STATIC_PROP = 0x10


class MeshBuilder:
    """Triangles per material. Model space: the part faces -Y (out of a panel whose front is at y = 0),
    Z up, X to the right as you face the panel."""

    def __init__(self):
        self.parts = {}                       # material -> (vertex list, {vertex key: index}, index list)

    def tri(self, mat, a, b, c):
        """a, b, c: (pos, normal, uv). Wound clockwise seen from the side the normals point to, as Source
        winds front faces: the order is fixed here if it is the other way."""
        pa, pb, pc = (np.array(v[0], float) for v in (a, b, c))
        navg = np.array(a[1], float) + np.array(b[1], float) + np.array(c[1], float)
        if np.dot(np.cross(pb - pa, pc - pa), navg) > 0:
            b, c = c, b
        verts, lookup, idx = self.parts.setdefault(mat, ([], {}, []))
        for v in (a, b, c):
            p, n, uv = v
            key = tuple(round(float(x), 5) for x in (*p, *n, *uv))
            k = lookup.get(key)
            if k is None:
                k = lookup[key] = len(verts)
                verts.append((tuple(map(float, p)), tuple(map(float, n)), tuple(map(float, uv))))
            idx.append(k)

    def quad(self, mat, a, b, c, d):
        self.tri(mat, a, b, c); self.tri(mat, a, c, d)

    def flat(self, mat, pts, uvs=None, normal=None):
        """flat convex polygon facing `normal` (else the side it is listed clockwise from)"""
        p = [np.array(q, float) for q in pts]
        if normal is None:
            n = np.cross(p[2] - p[0], p[1] - p[0])
        else:
            n = np.array(normal, float)
        n /= np.linalg.norm(n)
        uvs = uvs or [(0.5, 0.5)] * len(p)
        for k in range(1, len(p) - 1):
            self.tri(mat, (p[0], n, uvs[0]), (p[k], n, uvs[k]), (p[k + 1], n, uvs[k + 1]))

    def revolve(self, mat, profile, seg=24, center=(0.0, 0.0), uv=None, smooth=True, mats=None, y0=0.0):
        """Solid of revolution about the Y axis through (x, z) = center. profile: (r, h) points, h measured
        out of the panel (y = -h), listed from the panel outwards and round to the axis. Each profile
        segment is flat-shaded across, smooth round. mats: per-segment materials (else mat)."""
        cx, cz = center
        ring = [(math.cos(2 * math.pi * k / seg), math.sin(2 * math.pi * k / seg)) for k in range(seg + 1)]
        for i in range(len(profile) - 1):
            (r0, h0), (r1, h1) = profile[i], profile[i + 1]
            if abs(r0 - r1) < 1e-9 and abs(h0 - h1) < 1e-9:
                continue
            m = (mats[i] if mats else mat)
            dr, dh = r1 - r0, h1 - h0
            L = math.hypot(dr, dh)
            nr, nh = dh / L, -dr / L                  # outward normal in the (r, h) half plane
            for k in range(seg):
                c0, s0 = ring[k]; c1, s1 = ring[k + 1]
                P = lambda r, h, c, s: (cx + r * c, y0 - h, cz + r * s)
                N = lambda c, s: (nr * c, -nh, nr * s)
                u0, u1 = k / seg, (k + 1) / seg
                a = (P(r0, h0, c0, s0), N(c0, s0), (u0, 0)); b = (P(r1, h1, c0, s0), N(c0, s0), (u0, 1))
                c = (P(r1, h1, c1, s1), N(c1, s1), (u1, 1)); d = (P(r0, h0, c1, s1), N(c1, s1), (u1, 0))
                if not smooth:
                    nf = np.cross(np.array(c[0]) - np.array(a[0]), np.array(b[0]) - np.array(a[0]))
                    if np.linalg.norm(nf) > 1e-12:
                        nf = tuple(nf / np.linalg.norm(nf)); a, b, c, d = [(v[0], nf, v[2]) for v in (a, b, c, d)]
                if r0 < 1e-9:
                    self.tri(m, a, b, c)
                elif r1 < 1e-9:
                    self.tri(m, a, b, d)
                else:
                    self.quad(m, a, b, c, d)

    def disc_cap(self, mat, r, h, seg=24, center=(0.0, 0.0), uv_scale=None):
        """flat disc facing -Y at y = -h, its texture mapped across it (uv 0..1 over the diameter)"""
        cx, cz = center
        pts = [(cx + r * math.cos(-2 * math.pi * k / seg), -h, cz + r * math.sin(-2 * math.pi * k / seg)) for k in range(seg)]
        uvs = [(0.5 + 0.5 * math.cos(-2 * math.pi * k / seg), 0.5 - 0.5 * math.sin(-2 * math.pi * k / seg)) for k in range(seg)]
        self.flat(mat, pts[::-1], uvs[::-1], normal=(0, -1, 0))

    def box(self, mat, lo, hi):
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        c = lambda i: (x1 if i & 1 else x0, y1 if i & 2 else y0, z1 if i & 4 else z0)
        for f, n in (((0, 4, 6, 2), (-1, 0, 0)), ((1, 3, 7, 5), (1, 0, 0)), ((0, 1, 5, 4), (0, -1, 0)),
                     ((2, 6, 7, 3), (0, 1, 0)), ((0, 2, 3, 1), (0, 0, -1)), ((4, 5, 7, 6), (0, 0, 1))):
            self.flat(mat, [c(i) for i in f], normal=n)

    def loft(self, mat, sections):
        """closed tube through cross sections: each a list of 3-D points (same count, same winding), ends
        capped. Smooth normals around."""
        S = [np.array(s, float) for s in sections]
        n = len(S[0])
        for i in range(len(S) - 1):
            A, B = S[i], S[i + 1]
            ca, cb = A.mean(0), B.mean(0)
            for k in range(n):
                k1 = (k + 1) % n
                na = A[k] - ca; nb = B[k] - cb; na1 = A[k1] - ca; nb1 = B[k1] - cb
                nrm = lambda v: v / (np.linalg.norm(v) or 1)
                self.quad(mat, (A[k], nrm(na), (0, 0)), (A[k1], nrm(na1), (1, 0)), (B[k1], nrm(nb1), (1, 1)), (B[k], nrm(nb), (0, 1)))
        ax = S[-1].mean(0) - S[0].mean(0)
        self.flat(mat, list(S[0]), normal=-ax)
        self.flat(mat, list(S[-1]), normal=ax)

    def transform(self, M, t=(0, 0, 0)):
        """apply a 3x3 rotation M and a translation t to every vertex"""
        M = np.array(M, float); t = np.array(t, float)
        for verts, lookup, idx in self.parts.values():
            for k, (p, n, uv) in enumerate(verts):
                verts[k] = (tuple(M @ np.array(p) + t), tuple(M @ np.array(n)), uv)
            lookup.clear()
        return self

    def merge(self, other):
        for mat, (verts, _, idx) in other.parts.items():
            for t in range(0, len(idx), 3):
                self.tri(mat, *(verts[idx[t + j]] for j in range(3)))
        return self

    def check_winding(self):
        """triangles whose winding disagrees with their vertex normals (should be none)"""
        bad = 0
        for verts, _, idx in self.parts.values():
            for t in range(0, len(idx), 3):
                a, b, c = (verts[idx[t + j]] for j in range(3))
                pa, pb, pc = (np.array(v[0]) for v in (a, b, c))
                if np.dot(np.cross(pb - pa, pc - pa), np.array(a[1]) + np.array(b[1]) + np.array(c[1])) > 1e-9:
                    bad += 1
        return bad

    def bounds(self):
        P = np.array([v[0] for verts, _, _ in self.parts.values() for v in verts])
        return P.min(0), P.max(0)


# ------------------------------------------------------------------ writers
def _strings(buf, refs):
    """append the strings; refs: (field position, owner position, text). Offsets are owner-relative."""
    pos = {}
    for field, owner, text in refs:
        if text not in pos:
            pos[text] = len(buf)
            buf += text.encode() + b'\0'
        struct.pack_into('<i', buf, field, pos[text] - owner)


def write_model(path, mb, surfaceprop='metal', cd='models\\sablecreek\\', skins=()):
    """-> {relative path: bytes} for the .mdl, .vvd and the .vtx files. skins: extra skin families, each a
    {material: replacement} dict (skin 0 is the materials as built)."""
    mats = sorted(mb.parts)
    textures = list(mats)
    for fam in skins:
        for v in fam.values():
            if v not in textures:
                textures.append(v)
    families = [list(range(len(mats)))] + [[textures.index(fam.get(m_, m_)) for m_ in mats] for fam in skins]
    nt, nfam = len(textures), len(families)
    allv, meshes = [], []
    for mi, m in enumerate(mats):
        verts, _, idx = mb.parts[m]
        meshes.append((mi, len(allv), len(verts), idx))
        allv += verts
    nv, nm = len(allv), len(meshes)
    assert nv < 65536
    lo, hi = mb.bounds()
    center = (lo + hi) / 2
    radius = float(np.max(np.linalg.norm(np.array([v[0] for v in allv]) - center, axis=1)))
    checksum = zlib.crc32(path.encode() + struct.pack(f'<{3 * nv}f', *[c for v in allv for c in v[0]])) & 0x7FFFFFFF
    name = path[len('models/'):] if path.startswith('models/') else path

    # ---------------------------------------------------------- .mdl
    buf = bytearray(408 + 256)
    refs = []
    def block(n):
        while len(buf) % 4:
            buf.append(0)
        o = len(buf); buf.extend(bytes(n)); return o
    bone = block(216); bonetable = block(4)
    hbset = block(12); hbox = block(68)
    anim = block(100); animdata = block(20)
    seq = block(212); seq_blend = block(4); seq_weight = block(4)
    bodypart = block(16); model = block(148); mesh0 = block(116 * nm)
    tex0 = block(64 * nt); cdt = block(4); skin = block(2 * nm * nfam + 2)

    # header
    struct.pack_into('<4sii64si', buf, 0, b'IDST', 48, checksum, name.encode()[:63], 0)
    struct.pack_into('<18f', buf, 80, 0, 0, 0, *center, *lo, *hi, *lo, *hi)
    struct.pack_into('<11i', buf, 152, STATIC_PROP, 1, bone, 0, 0, 1, hbset, 1, anim, 1, seq)
    struct.pack_into('<13i', buf, 196, 0, 0, nt, tex0, 1, cdt, nm, nfam, skin, 1, bodypart, 0, 0)
    struct.pack_into('<15i', buf, 248, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    refs.append((308, 0, surfaceprop))
    struct.pack_into('<iiiifi', buf, 312, 0, 0, 0, 0, 1.0, 1)              # keyvalues, ik locks, mass, contents
    struct.pack_into('<iii', buf, 336, 0, 0, 0)                             # include models, virtual model
    refs.append((348, 0, ''))                                               # anim block name
    struct.pack_into('<iiiiii', buf, 352, 0, 0, 0, bonetable, 0, 0)
    struct.pack_into('<4Biiifiii', buf, 376, 0, 0, 0, 0, 0, 0, 0, 0.0, 0, 408, 0)
    # studiohdr2_t
    struct.pack_into('<iiifi', buf, 408, 0, 0, 0, 0.0, 0)
    refs.append((408 + 20, 408, name))
    # bone
    struct.pack_into('<ii6i3f4f3f3f3f12f4fiiiiii', buf, bone, 0, -1, *([-1] * 6), 0, 0, 0, 0, 0, 0, 1, 0, 0, 0,
                     0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1,
                     0x3FD00, 0, 0, 0, 0, 1)
    refs.append((bone, bone, 'static_prop')); refs.append((bone + 176, bone, surfaceprop))
    # hitbox set and box
    struct.pack_into('<iii', buf, hbset, 0, 1, hbox - hbset); refs.append((hbset, hbset, 'default'))
    struct.pack_into('<ii6fi', buf, hbox, 0, 0, *lo, *hi, 0)
    # one-frame animation: bone 0 at rest (raw quaternion64 + raw vector48)
    struct.pack_into('<ii f iiii', buf, anim, -anim, 0, 30.0, 0, 1, 0, 0)
    # animblock, animindex, ik rules (3), local hierarchy (2), sections (2), zero frames (span, count, index, stall)
    struct.pack_into('<9ihhif', buf, anim + 52, 0, animdata - anim, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0)
    refs.append((anim + 4, anim, '@idle'))
    q64 = (1 << 20) | ((1 << 20) << 21) | ((1 << 20) << 42)                # x = y = z = 0, w > 0
    struct.pack_into('<BBhQ3H', buf, animdata, 0, 0x21, 0, q64, 0, 0, 0)
    # sequence
    o = seq
    for fmt, vals in (('8i', (-seq, 0, 0, 0, -1, 0, 0, 0)),              # base, label, activity name, flags, activity, weight, events
                      ('6f', (*lo, *hi)),
                      ('3i', (1, seq_blend - seq, 0)),                    # numblends, animindexindex, movementindex
                      ('2i', (1, 1)), ('2i', (-1, -1)), ('2f', (0, 0)), ('2f', (0, 0)),   # groupsize, paramindex, start, end
                      ('i', (0,)), ('2f', (0.2, 0.2)),                    # paramparent, fade in / out
                      ('3i', (0, 0, 0)), ('3f', (0, 0, 0)),               # entry / exit node, nodeflags; entry / exit phase, lastframe
                      ('5i', (0, 0, 0, 0, 0)),                            # nextseq, pose, ik rules, autolayers (2)
                      ('i', (seq_weight - seq,)),                         # weightlistindex
                      ('8i', (0,) * 8), ('5i', (0,) * 5)):                # posekey, ik locks (2), keyvalues (2), cyclepose, activity modifiers (2); unused
        struct.pack_into('<' + fmt, buf, o, *vals); o += struct.calcsize('<' + fmt)
    assert o - seq == 212
    refs.append((seq + 4, seq, 'idle')); refs.append((seq + 8, seq, ''))
    struct.pack_into('<hh', buf, seq_blend, 0, 0)
    struct.pack_into('<f', buf, seq_weight, 1.0)
    # body part, model, meshes
    struct.pack_into('<iiii', buf, bodypart, 0, 1, 1, model - bodypart); refs.append((bodypart, bodypart, 'studio'))
    struct.pack_into('<64sif11i', buf, model, b'studio', 0, radius, nm, mesh0 - model, nv, 0, 0, 0, 0, 0, 0, 0, 0)
    for k, (mi, start, count, idx) in enumerate(meshes):
        o = mesh0 + 116 * k
        P = np.array([v[0] for v in allv[start:start + count]])
        struct.pack_into('<9i3fi8i', buf, o, mi, model - o, count, start, 0, 0, 0, 0, k, *P.mean(0), 0, *([count] * 8))
    for k, t in enumerate(textures):
        to = tex0 + 64 * k
        struct.pack_into('<6i', buf, to, 0, 0, 0, 0, 0, 0)
        refs.append((to, to, t))
    refs.append((cdt, 0, cd))
    struct.pack_into(f'<{nm * nfam}h', buf, skin, *[i for fam in families for i in fam])
    _strings(buf, refs)
    while len(buf) % 4:
        buf.append(0)
    struct.pack_into('<i', buf, 76, len(buf))
    mdl = bytes(buf)

    # ---------------------------------------------------------- .vvd
    vvd = bytearray(struct.pack('<4siii8iiiii', b'IDSV', 4, checksum, 1, *([nv] * 8), 0, 64, 64, 64 + 48 * nv))
    for p, n, uv in allv:
        vvd += struct.pack('<3f3BB3f3f2f', 1.0, 0.0, 0.0, 0, 0, 0, 1, *p, *n, *uv)
    for p, n, uv in allv:
        nn = np.array(n); t = np.cross(nn, (0, 0, 1) if abs(nn[2]) < 0.9 else (1, 0, 0)); t /= np.linalg.norm(t)
        vvd += struct.pack('<4f', *t, 1.0)

    # ---------------------------------------------------------- .vtx (all three the same)
    def vtx_file():
        out = bytearray(struct.pack('<iiHHiiiiii', 7, 24, 53, 9, 3, checksum, 1, 0, 1, 36))
        bp = len(out); out += struct.pack('<ii', 1, 8)                     # body part -> model
        md = len(out); out += struct.pack('<ii', 1, 8)                     # model -> lod
        lod = len(out); out += struct.pack('<iif', nm, 12, 0.0)            # lod -> meshes
        mh0 = len(out); out += bytes(9 * nm)
        for k, (mi, start, count, idx) in enumerate(meshes):
            sg = len(out)
            struct.pack_into('<iiB', out, mh0 + 9 * k, 1, sg - (mh0 + 9 * k), 0)
            out += bytes(25)
            strip = len(out); out += bytes(27)
            bsc = len(out); out += struct.pack('<ii', 0, 0)
            verts = len(out)
            for j in range(count):
                out += struct.pack('<3BBH3b', 0, 0, 0, 1, j, 0, 0, 0)
            inds = len(out)
            out += struct.pack(f'<{len(idx)}H', *idx)
            struct.pack_into('<iiiiiiB', out, sg, count, verts - sg, len(idx), inds - sg, 1, strip - sg, 0x02)
            struct.pack_into('<iiiihBii', out, strip, len(idx), 0, count, 0, 1, 0x01, 1, bsc - strip)
        mrl = len(out); out += struct.pack('<ii', 0, 0)                    # material replacement list (empty)
        struct.pack_into('<i', out, 24, mrl)
        return bytes(out)
    vtx = vtx_file()
    base = path[:-4]
    return {path: mdl, base + '.vvd': bytes(vvd), base + '.dx90.vtx': vtx, base + '.dx80.vtx': vtx, base + '.sw.vtx': vtx}


def read_model(files, path):
    """Read a model back the way the engine walks it (header -> body parts -> models -> meshes, VVD
    vertices, VTX strip groups and strips). Returns [(material, [(pos, normal, uv) x 3], ...)] triangles.
    Used to check the writer."""
    mdl, vvd = files[path], files[path[:-4] + '.vvd']
    vtx = files[path[:-4] + '.dx90.vtx']
    i32 = lambda b, o: struct.unpack_from('<i', b, o)[0]
    assert mdl[:4] == b'IDST' and i32(mdl, 4) == 48 and i32(mdl, 76) == len(mdl)
    ck = i32(mdl, 8)
    assert vvd[:4] == b'IDSV' and i32(vvd, 8) == ck and i32(vtx, 16) == ck
    cstr = lambda b, o: b[o:b.index(b'\0', o)].decode()
    ntex, texi = i32(mdl, 204), i32(mdl, 208)
    texnames = [cstr(mdl, texi + 64 * k + i32(mdl, texi + 64 * k)) for k in range(ntex)]
    cd = cstr(mdl, i32(mdl, i32(mdl, 216)))
    h2 = i32(mdl, 400)
    assert cstr(mdl, h2 + i32(mdl, h2 + 20)) == path[len('models/'):]
    vstart = i32(vvd, 56)
    vert = lambda i: (struct.unpack_from('<3f', vvd, vstart + 48 * i + 16), struct.unpack_from('<3f', vvd, vstart + 48 * i + 28),
                      struct.unpack_from('<2f', vvd, vstart + 48 * i + 40))
    out = []
    bpi = i32(mdl, 236)
    vbp = i32(vtx, 32)
    for bp in range(i32(mdl, 232)):
        mbp = bpi + 16 * bp
        mm = mbp + i32(mdl, mbp + 12)
        vm = vbp + 8 * bp; vm = vm + i32(vtx, vm + 4)
        vl = vm + i32(vtx, vm + 4)
        nmesh, mesh_ofs = i32(mdl, mm + 72), mm + i32(mdl, mm + 76)
        model_vert = i32(mdl, mm + 84) // 48
        vme0 = vl + i32(vtx, vl + 4)
        for me in range(nmesh):
            mo = mesh_ofs + 116 * me
            assert mo + i32(mdl, mo + 4) == mm
            ref = i32(mdl, mo)
            mat = cd.replace('\\', '/') + texnames[struct.unpack_from('<h', mdl, i32(mdl, 228) + 2 * ref)[0]]
            mvs = i32(mdl, mo + 12)
            vme = vme0 + 9 * me
            sg = vme + i32(vtx, vme + 4)
            nverts, voff, nind, ioff, nstrip, soff = struct.unpack_from('<6i', vtx, sg)
            sv = [struct.unpack_from('<H', vtx, sg + voff + 9 * k + 4)[0] for k in range(nverts)]
            ind = struct.unpack_from(f'<{nind}H', vtx, sg + ioff)
            st = sg + soff
            sni, sio = struct.unpack_from('<ii', vtx, st)
            assert struct.unpack_from('<B', vtx, st + 18)[0] & 1               # triangle list
            for t in range(sio, sio + sni, 3):
                out.append((mat, [vert(model_vert + mvs + sv[ind[t + j]]) for j in range(3)]))
    return out
