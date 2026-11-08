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


# ------------------------------------------------------------------ BSP face fix-up
LUMP_FACES, LUMP_PRIMITIVES, LUMP_PRIMVERTS, LUMP_PRIMINDICES, LUMP_FACES_HDR = 7, 37, 38, 39, 58


def strip_prims(path):
    """Drop the compiler's per-face triangle lists ("primitives") so the engine draws every face as a fan
    of its own polygon. The engine sizes its index buffers as (vertices - 2) * 3 per face; gbsp leaves out
    zero-area triangles where a face has a repeated vertex, so a single short list shifts every index after
    it, and the world draws with the wrong triangles and textures. Returns how many lists didn't match."""
    d = bytearray(open(path, 'rb').read())
    assert d[:4] == b'VBSP'
    lump = lambda i: struct.unpack_from('<ii', d, 8 + 16 * i)
    po, pl = lump(LUMP_PRIMITIVES)
    prims = [struct.unpack_from('<BxHHHH', d, po + 10 * i) for i in range(pl // 10)]
    bad = 0
    for li in (LUMP_FACES, LUMP_FACES_HDR):
        fo, fl = lump(li)
        for i in range(fl // 56):
            o = fo + 56 * i
            ne = struct.unpack_from('<h', d, o + 8)[0]
            nprim, first = struct.unpack_from('<HH', d, o + 48)
            n = nprim & 0x7FFF                      # the top bit is the no-shadows flag: keep it
            if n and li == LUMP_FACES and sum(prims[first + k][2] for k in range(n)) != (ne - 2) * 3:
                bad += 1
            struct.pack_into('<HH', d, o + 48, nprim & 0x8000, 0)
    for li in (LUMP_PRIMITIVES, LUMP_PRIMVERTS, LUMP_PRIMINDICES):
        struct.pack_into('<ii', d, 8 + 16 * li, 0, 0)
    open(path, 'wb').write(d)
    return bad
