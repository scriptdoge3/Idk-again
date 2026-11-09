"""Writers for Source file formats: VTF 7.2 textures, VMT materials, Hammer .vmf maps, and the BSP
pakfile (so the map carries its own materials and sounds)."""
import io, os, re, struct, zipfile
import numpy as np
from PIL import Image

# ------------------------------------------------------------------ VTF 7.2
IMAGE_BGR888, IMAGE_BGRA8888 = 3, 12
TEXF_POINTSAMPLE, TEXF_TRILINEAR, TEXF_CLAMPS, TEXF_CLAMPT = 0x1, 0x2, 0x4, 0x8
TEXF_NOMIP, TEXF_NOLOD, TEXF_EIGHTBITALPHA = 0x100, 0x200, 0x2000


IMAGE_DXT1 = 13


def dxt1(img):
    """DXT1 (BC1) blocks for an RGB image whose sides are multiples of 4: per 4x4 block, the two end
    colours are the extremes along the block's main colour axis, every texel takes the nearest of the
    four colours between them."""
    a = np.asarray(img.convert('RGB')).astype(np.float32)
    h, w = a.shape[:2]
    blk = a.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3)
    mean = blk.mean(axis=1, keepdims=True)
    c = blk - mean
    cov = np.einsum('nki,nkj->nij', c, c)
    v = np.ones((len(blk), 3), np.float32)
    for _ in range(6):
        v = np.einsum('nij,nj->ni', cov, v)
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-6)
    t = np.einsum('nki,ni->nk', c, v)
    lo = blk[np.arange(len(blk)), t.argmin(1)]
    hi = blk[np.arange(len(blk)), t.argmax(1)]
    to565 = lambda q: ((np.clip(np.round(q[:, 0] * 31 / 255), 0, 31).astype(np.uint16) << 11) |
                       (np.clip(np.round(q[:, 1] * 63 / 255), 0, 63).astype(np.uint16) << 5) |
                       np.clip(np.round(q[:, 2] * 31 / 255), 0, 31).astype(np.uint16))
    from565 = lambda u: np.stack([((u >> 11) & 31) * 255 / 31, ((u >> 5) & 63) * 255 / 63, (u & 31) * 255 / 31], 1).astype(np.float32)
    c0, c1 = to565(hi), to565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = from565(c0), from565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)              # 4-colour mode (c0 > c1)
    eq = c0 == c1
    d = ((blk[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = d.argmin(-1).astype(np.uint32)
    idx[eq] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((len(blk), 8), np.uint8)
    out[:, 0:2] = c0.astype('<u2').view(np.uint8).reshape(-1, 2)
    out[:, 2:4] = c1.astype('<u2').view(np.uint8).reshape(-1, 2)
    out[:, 4:8] = bits.astype('<u4').view(np.uint8).reshape(-1, 4)
    return out.tobytes()


def vtf_bytes(img, flags=0, mips=True, compress=False):
    """img: PIL image, power-of-two sides. RGB -> BGR888, RGBA -> BGRA8888, with a full mip chain."""
    alpha = img.mode == 'RGBA'
    img = img.convert('RGBA' if alpha else 'RGB')
    w, h = img.size
    assert w & (w - 1) == 0 and h & (h - 1) == 0, f'not a power of two: {img.size}'
    compress = compress and not alpha and w >= 4 and h >= 4
    fmt = IMAGE_BGRA8888 if alpha else (IMAGE_DXT1 if compress else IMAGE_BGR888)
    if alpha:
        flags |= TEXF_EIGHTBITALPHA
    levels = [img]
    if mips:
        while levels[-1].size != (1, 1):
            lw, lh = levels[-1].size
            levels.append(levels[-1].resize((max(1, lw // 2), max(1, lh // 2)), Image.Resampling.BOX))
    else:
        flags |= TEXF_NOMIP | TEXF_NOLOD
    a = np.asarray(img.convert('RGB')).astype(np.float64) / 255.0
    refl = (a ** 2.2).reshape(-1, 3).mean(axis=0)
    hdr = b'VTF\0' + struct.pack('<III', 7, 2, 80)
    hdr += struct.pack('<HHI', w, h, flags)
    hdr += struct.pack('<HH', 1, 0) + b'\0' * 4
    hdr += struct.pack('<fff', *refl) + b'\0' * 4
    hdr += struct.pack('<fIB', 1.0, fmt, len(levels))
    hdr += struct.pack('<IBB', 0xFFFFFFFF, 0, 0) + struct.pack('<H', 1)
    hdr += b'\0' * (80 - len(hdr))
    body = b''
    for lv in reversed(levels):                       # smallest mip first
        if compress:
            lw, lh = lv.size
            if lw < 4 or lh < 4:
                pad = Image.new('RGB', (max(4, lw), max(4, lh))); pad.paste(lv.resize((max(4, lw), max(4, lh)))); lv = pad
            body += dxt1(lv)
            continue
        px = np.asarray(lv)
        px = px[..., [2, 1, 0, 3]] if alpha else px[..., [2, 1, 0]]
        body += px.astype(np.uint8).tobytes()
    return hdr + body


def pow2(img, max_side=1024):
    """Resize to the nearest power-of-two sides (rounding up, at most max_side)."""
    w, h = img.size
    p = lambda n: min(max_side, 1 << max(0, (n - 1).bit_length()))
    W, H = p(w), p(h)
    return img if (W, H) == (w, h) else img.resize((W, H), Image.Resampling.LANCZOS)


class Content:
    """The files the map needs: written to a game folder for the compile, and kept for the pakfile."""

    def __init__(self, game_dir):
        self.game = game_dir
        self.files = {}
        os.makedirs(game_dir, exist_ok=True)

    def add(self, rel, data, pak=True):
        if isinstance(data, str):
            data = data.encode()
        if pak:
            self.files[rel] = data
        p = os.path.join(self.game, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(data)

    def material(self, name, img, shader='LightmappedGeneric', params=None, flags=0, mips=True, compress=False):
        self.add(f'materials/{name}.vtf', vtf_bytes(img, flags, mips, compress))
        kv = {'$basetexture': name}
        kv.update(params or {})
        body = ''.join(f'\t"{k}" "{v}"\n' for k, v in kv.items())
        self.add(f'materials/{name}.vmt', f'"{shader}"\n{{\n{body}}}\n')

    def tool(self, name, flags):
        """a tool material for the compile only (the game has the real one)"""
        body = ''.join(f'\t"{k}" "1"\n' for k in flags)
        self.add(f'materials/{name}.vmt', f'"LightmappedGeneric"\n{{\n\t"$basetexture" "{name}"\n{body}}}\n', pak=False)


# ------------------------------------------------------------------ VMF
_LINE = re.compile(r'\(\s*([^)]*)\)\s*\(\s*([^)]*)\)\s*\(\s*([^)]*)\)\s*(\S+)\s*\[\s*([^\]]*)\]\s*\[\s*([^\]]*)\]\s*(\S+)\s+(\S+)\s+(\S+)')


class VmfWriter:
    """Turns GoldSrc-style brushes (hlfiles.Box / Poly, Valve 220 face lines) into a .vmf.
    tex(name) -> (material, u factor, v factor): the factors rescale texture offsets and scales when
    the Source texture has a different size than the art was laid out for."""

    def __init__(self, tex, lightmapscale=16):
        self.tex = tex
        self.lms = lightmapscale
        self.n = 0

    def id(self):
        self.n += 1
        return self.n

    def solid(self, brush):
        out = ['\tsolid', '\t{', f'\t\t"id" "{self.id()}"']
        for ln in brush.lines():
            m = _LINE.match(ln)
            assert m, ln
            p0, p1, p2, tname, U, Vv, rot, sx, sy = m.groups()
            mat, fu, fv = self.tex(tname)
            u = [float(c) for c in U.split()]
            v = [float(c) for c in Vv.split()]
            sx, sy = float(sx) / fu, float(sy) / fv
            u[3] *= fu; v[3] *= fv
            f = lambda q: ' '.join(_fmt(float(c)) for c in q.split())
            out += ['\t\tside', '\t\t{', f'\t\t\t"id" "{self.id()}"',
                    f'\t\t\t"plane" "({f(p0)}) ({f(p1)}) ({f(p2)})"',
                    f'\t\t\t"material" "{mat}"',
                    f'\t\t\t"uaxis" "[{_fmt(u[0])} {_fmt(u[1])} {_fmt(u[2])} {_fmt(u[3])}] {_fmt(sx)}"',
                    f'\t\t\t"vaxis" "[{_fmt(v[0])} {_fmt(v[1])} {_fmt(v[2])} {_fmt(v[3])}] {_fmt(sy)}"',
                    '\t\t\t"rotation" "0"', f'\t\t\t"lightmapscale" "{self.lms}"', '\t\t\t"smoothing_groups" "0"', '\t\t}']
        out.append('\t}')
        return '\n'.join(out)

    def write(self, path, world_kv, world_brushes, ents):
        """ents: (classname, keyvalues dict, outputs [(out, target, input, param, delay, times)], brushes)"""
        L = ['versioninfo', '{', '\t"editorversion" "400"', '\t"editorbuild" "8864"', '\t"mapversion" "1"',
             '\t"formatversion" "100"', '\t"prefab" "0"', '}', 'world', '{', f'\t"id" "{self.id()}"',
             '\t"mapversion" "1"', '\t"classname" "worldspawn"']
        L += [f'\t"{k}" "{v}"' for k, v in world_kv.items()]
        L += [self.solid(b) for b in world_brushes]
        L.append('}')
        for cls, kv, outputs, brushes in ents:
            L += ['entity', '{', f'\t"id" "{self.id()}"', f'\t"classname" "{cls}"']
            L += [f'\t"{k}" "{v}"' for k, v in kv.items()]
            if outputs:
                L += ['\tconnections', '\t{']
                for out, tgt, inp, par, delay, times in outputs:
                    L.append(f'\t\t"{out}" "{tgt},{inp},{par},{_fmt(delay)},{times}"')
                L.append('\t}')
            L += [self.solid(b) for b in brushes]
            L.append('}')
        open(path, 'w').write('\n'.join(L) + '\n')


def _fmt(v):
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


# ------------------------------------------------------------------ BSP pakfile
def pack_bsp(path, files):
    """Replace the BSP's pakfile lump (40) with an uncompressed zip of `files` plus what was in it."""
    d = bytearray(open(path, 'rb').read())
    assert d[:4] == b'VBSP'
    ofs, ln = struct.unpack_from('<ii', d, 8 + 40 * 16)
    old = zipfile.ZipFile(io.BytesIO(bytes(d[ofs:ofs + ln]))) if ln > 22 else None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
        if old:
            for n in old.namelist():
                if n not in files:
                    z.writestr(n, old.read(n))
        for n, data in sorted(files.items()):
            z.writestr(zipfile.ZipInfo(n, (2020, 1, 1, 0, 0, 0)), data)
    pak = buf.getvalue()
    if ofs + ln == len(d):            # the pakfile is the last lump: cut it off
        del d[ofs:]
    while len(d) % 4:
        d.append(0)
    new_ofs = len(d)
    d += pak
    struct.pack_into('<ii', d, 8 + 40 * 16, new_ofs, len(pak))
    open(path, 'wb').write(d)
    return len(pak)


# ------------------------------------------------------------------ BSP face triangles
LUMP_PLANES, LUMP_VERTEXES, LUMP_EDGES, LUMP_SURFEDGES = 1, 3, 12, 13
LUMP_FACES, LUMP_PRIMITIVES, LUMP_PRIMVERTS, LUMP_PRIMINDICES, LUMP_FACES_HDR = 7, 37, 38, 39, 58


def _ear_clip(P, n):
    """Triangulate a simple polygon (3-D points P, normal n) into exactly len(P) - 2 triangles, allowing
    zero-area ones where corners are collinear or repeated. Returns index triples."""
    ax = int(np.argmax(np.abs(n)))
    u, v = [i for i in range(3) if i != ax]
    Q = np.array([(p[u], p[v]) for p in P], float)
    if np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1]) < 0:
        sign = -1.0                                     # walk the polygon anticlockwise in (u, v)
    else:
        sign = 1.0
    cross = lambda a, b, c: sign * ((Q[b, 0] - Q[a, 0]) * (Q[c, 1] - Q[a, 1]) - (Q[b, 1] - Q[a, 1]) * (Q[c, 0] - Q[a, 0]))
    def inside(p, a, b, c):
        if any(np.allclose(Q[p], Q[k], atol=1e-4) for k in (a, b, c)):
            return False
        return cross(a, b, p) > 1e-6 and cross(b, c, p) > 1e-6 and cross(c, a, p) > 1e-6
    idx, tris = list(range(len(P))), []
    while len(idx) > 3:
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(a, b, c) >= -1e-6 and not any(inside(p, a, b, c) for p in idx if p not in (a, b, c)):
                tris.append((a, b, c)); idx.pop(k); break
        else:                                           # numerically stuck: fan the rest
            tris += [(idx[0], idx[j], idx[j + 1]) for j in range(1, len(idx) - 1)]
            idx = idx[:3]; tris.pop()
    tris.append(tuple(idx))
    assert len(tris) == len(P) - 2
    return tris


LUMP_VERTNORMALINDICES = 31


def fix_tjunctions(path):
    """Add to each world face the corners of its neighbours that lie part way along its edges (T-junctions),
    as vbsp does. Otherwise the two triangle edges there don't meet exactly and the game shows a hairline
    crack of sparkles. The corners already exist; faces get new edges and a rebuilt surfedge list, and the
    per-corner normal indices are rebuilt to match. Returns the number of corners added."""
    d = bytearray(open(path, 'rb').read())
    lump = lambda i: struct.unpack_from('<ii', d, 8 + 16 * i)
    vo, vl = lump(LUMP_VERTEXES); eo, el = lump(LUMP_EDGES); so, sl = lump(LUMP_SURFEDGES)
    fo, fl = lump(LUMP_FACES); no_, nl = lump(LUMP_VERTNORMALINDICES); plo = lump(LUMP_PLANES)[0]
    V = np.array(struct.unpack_from(f'<{vl // 4}f', d, vo), float).reshape(-1, 3)
    E = [tuple(struct.unpack_from('<HH', d, eo + 4 * i)) for i in range(el // 4)]
    SE = list(struct.unpack_from(f'<{sl // 4}i', d, so))
    VN = list(struct.unpack_from(f'<{nl // 2}H', d, no_))
    m0_first, m0_num = struct.unpack_from('<ii', d, lump(14)[0] + 40)
    nf = fl // 56
    faces = []
    for i in range(nf):
        o = fo + 56 * i
        pn = struct.unpack_from('<H', d, o)[0]; fe, ne = struct.unpack_from('<ih', d, o + 4)
        vs = [E[abs(se)][1 if se < 0 else 0] for se in SE[fe:fe + ne]]
        faces.append((pn, vs))
    # corners by plane: a T-junction only matters between faces on the same plane
    plane_key = lambda pn: tuple(np.round(struct.unpack_from('<4f', d, plo + 20 * pn), 3))
    by_plane = {}
    for i, (pn, vs) in enumerate(faces):
        if m0_first <= i < m0_first + m0_num:
            by_plane.setdefault(plane_key(pn), set()).update(vs)
    edge_ix = {}
    for k, (a, b) in enumerate(E):
        edge_ix.setdefault((a, b), k)
    added, new_se, new_vn, firsts, vn_pos = 0, [], [], [], 0
    for i, (pn, vs) in enumerate(faces):
        ne0 = len(vs)
        out = vs
        if m0_first <= i < m0_first + m0_num:
            cand = [c for c in by_plane.get(plane_key(pn), ()) if c not in vs]
            out = []
            for k in range(ne0):
                a, b = vs[k], vs[(k + 1) % ne0]
                out.append(a)
                pa, ab = V[a], V[b] - V[a]
                L2 = ab @ ab
                if L2 < 1e-8:
                    continue
                ins = []
                for c in cand:
                    t = (V[c] - pa) @ ab / L2
                    if 1e-3 < t < 1 - 1e-3 and np.linalg.norm(pa + t * ab - V[c]) < 2e-3:
                        ins.append((t, c))
                out += [c for _, c in sorted(ins)]
            if len(out) > 64:                            # keep within what the engine takes per face
                out = vs
        added += len(out) - ne0
        firsts.append(len(new_se))
        for k in range(len(out)):
            a, b = out[k], out[(k + 1) % len(out)]
            if (a, b) in edge_ix:
                new_se.append(edge_ix[(a, b)])
            elif (b, a) in edge_ix:
                new_se.append(-edge_ix[(b, a)])
            else:
                edge_ix[(a, b)] = len(E); E.append((a, b)); new_se.append(edge_ix[(a, b)])
        # normal index per corner: the face's own corners keep theirs; an added corner takes the one before it
        own = dict(zip(vs, VN[vn_pos:vn_pos + ne0])) if vn_pos + ne0 <= len(VN) else {}
        last = VN[vn_pos] if vn_pos < len(VN) else 0
        for c in out:
            last = own.get(c, last); new_vn.append(last)
        vn_pos += ne0
        faces[i] = (pn, out)
    for i, (pn, out) in enumerate(faces):
        for li in (LUMP_FACES, LUMP_FACES_HDR):
            lo_, ll = lump(li)
            if ll == fl:
                struct.pack_into('<ih', d, lo_ + 56 * i + 4, firsts[i], len(out))
    for li, blob in ((LUMP_EDGES, struct.pack(f'<{2 * len(E)}H', *[x for e in E for x in e])),
                     (LUMP_SURFEDGES, struct.pack(f'<{len(new_se)}i', *new_se)),
                     (LUMP_VERTNORMALINDICES, struct.pack(f'<{len(new_vn)}H', *new_vn))):
        while len(d) % 4:
            d.append(0)
        struct.pack_into('<ii', d, 8 + 16 * li, len(d), len(blob))
        d += blob
    open(path, 'wb').write(d)
    return added


def fix_face_triangles(path):
    """Replace the compiler's per-face triangle lists ("primitives"). The engine reserves (corners - 2) * 3
    indices for every face; gbsp leaves zero-area triangles out where a face repeats a corner, and one short
    list shifts every index after it, so the whole map draws with wrong triangles and textures. Convex faces
    get no list (the engine draws a fan); a non-convex face (gbsp merges some) gets an ear-clipped list of
    exactly corners - 2 triangles, since a fan of it would fold over. Returns (lists that were wrong,
    non-convex faces)."""
    d = bytearray(open(path, 'rb').read())
    assert d[:4] == b'VBSP'
    lump = lambda i: struct.unpack_from('<ii', d, 8 + 16 * i)
    po, pl = lump(LUMP_PRIMITIVES)
    old = [struct.unpack_from('<BxHHHH', d, po + 10 * i) for i in range(pl // 10)]
    fo, fl = lump(LUMP_FACES)
    vo = lump(LUMP_VERTEXES)[0]; eo = lump(LUMP_EDGES)[0]; so = lump(LUMP_SURFEDGES)[0]; plo = lump(LUMP_PLANES)[0]
    prims, indices, bad, nonconvex, rows = b'', [], 0, 0, []
    for i in range(fl // 56):
        o = fo + 56 * i
        pn = struct.unpack_from('<H', d, o)[0]
        fe, ne = struct.unpack_from('<ih', d, o + 4)
        nprim, first = struct.unpack_from('<HH', d, o + 48)
        if nprim & 0x7FFF and sum(old[first + k][2] for k in range(nprim & 0x7FFF)) != (ne - 2) * 3:
            bad += 1
        P = []
        for k in range(ne):
            se = struct.unpack_from('<i', d, so + 4 * (fe + k))[0]
            e = struct.unpack_from('<HH', d, eo + 4 * abs(se))
            P.append(np.array(struct.unpack_from('<3f', d, vo + 12 * e[1 if se < 0 else 0])))
        n = np.array(struct.unpack_from('<3f', d, plo + 20 * pn))
        turn = [np.dot(np.cross(P[k] - P[k - 1], P[(k + 1) % ne] - P[k]), n) for k in range(ne)]
        if min(turn) >= -1e-3 or max(turn) <= 1e-3:
            rows.append((i, nprim & 0x8000, 0))         # convex: a fan
            continue
        nonconvex += 1
        tris = _ear_clip(P, n)
        rows.append((i, (nprim & 0x8000) | 1, len(prims) // 10))
        prims += struct.pack('<BxHHHH', 0, len(indices), 3 * len(tris), 0, 0)
        indices += [k for t in tris for k in t]
    for li in (LUMP_FACES, LUMP_FACES_HDR):
        lo_, ll = lump(li)
        if ll != fl:
            continue
        for i, np_, first in rows:
            struct.pack_into('<HH', d, lo_ + 56 * i + 48, np_, first)
    for li, blob in ((LUMP_PRIMITIVES, prims), (LUMP_PRIMINDICES, struct.pack(f'<{len(indices)}H', *indices))):
        while len(d) % 4:
            d.append(0)
        struct.pack_into('<ii', d, 8 + 16 * li, len(d) if blob else 0, len(blob))
        d += blob
    struct.pack_into('<ii', d, 8 + 16 * LUMP_PRIMVERTS, 0, 0)
    open(path, 'wb').write(d)
    return bad, nonconvex
