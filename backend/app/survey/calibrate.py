"""Measure the skybox face convention from data: multi-view photo-consistency against the mesh.

    python -m app.survey.calibrate building-h

For pairs of nearby cameras A and B: cast rays from A onto the mesh, keep surface points that B also sees
(B's ray to the point is not blocked), then compare the image intensity each camera's panorama shows at that
point. Only the true convention makes the two agree. Mesh hits do not depend on the convention, so they are
computed once and every candidate is scored cheaply. Results go to data/cache/geometry/<building>.json.
"""
import itertools
import json
import sys

import numpy as np
from PIL import Image, ImageFilter

from app.config import BUILDINGS, CACHE, MEDIA
from app.sources.cache import write_json
from app.survey.geometry import Convention, Mesh

SIZE = 256
UP = np.array([0.0, 0.0, 1.0])
H_AXES = [np.array(a, dtype=float) for a in ([1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0])]


def side_candidates():
    for transpose in (False, True):
        for fwd in H_AXES:
            for s in (1, -1):
                right = s * np.cross(fwd, UP)
                ring = [fwd, right, -fwd, -right]
                for k in range(4):
                    for rev in (False, True):
                        order = ring[k:] + ring[:k]
                        if rev:
                            order = order[::-1]
                        for t in (1, -1):
                            rights = [t * np.cross(d, UP) for d in order]
                            yield {"transpose": transpose, "side_dirs": order, "side_rights": rights}


def full(c, top=None, bottom=None):
    top = top or (H_AXES[0], H_AXES[2])
    bottom = bottom or (H_AXES[0], H_AXES[2])
    dirs = [UP] + c["side_dirs"] + [-UP]
    rights = [top[0]] + c["side_rights"] + [bottom[0]]
    downs = [top[1]] + [-UP] * 4 + [bottom[1]]
    return Convention(c["transpose"], tuple(map(tuple, dirs)), tuple(map(tuple, rights)), tuple(map(tuple, downs)))


def cap_candidates():
    for r in H_AXES:
        for d in H_AXES:
            if abs(np.dot(r, d)) < 1e-9:
                yield (r, d)


def load_faces(bid, pano_id):
    out = []
    for i in range(6):
        im = Image.open(MEDIA / bid / "panos" / pano_id / f"face{i}.jpg").convert("L").resize((SIZE, SIZE))
        out.append(np.asarray(im.filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float64))
    return np.stack(out)


def sample(faces, face, x, y):
    x = np.clip(x, 0, SIZE - 1.001)
    y = np.clip(y, 0, SIZE - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    f = faces[face]
    return ((1 - fx) * (1 - fy) * f[y0, x0] + fx * (1 - fy) * f[y0, x0 + 1]
            + (1 - fx) * fy * f[y0 + 1, x0] + fx * fy * f[y0 + 1, x0 + 1])


def ncc(a, b):
    if len(a) < 50:
        return np.nan
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


def fibonacci(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)


def pairs_for(panos, n_pairs=8):
    pos = np.array([[p["position"][k] for k in "xyz"] for p in panos])
    out, used = [], set()
    rng = np.random.default_rng(1)
    for i in rng.permutation(len(panos)):
        d = np.linalg.norm(pos - pos[i], axis=1)
        cand = [j for j in np.argsort(d) if 1.5 <= d[j] <= 6 and j not in used]
        if cand and i not in used:
            out.append((i, cand[0]))
            used |= {i, cand[0]}
        if len(out) >= n_pairs:
            break
    return out


def observations(mesh, A, B, n_dirs=3000):
    """Surface points seen by camera A that camera B also sees (convention-independent)."""
    a = np.array([A["position"][k] for k in "xyz"])
    b = np.array([B["position"][k] for k in "xyz"])
    dirs = fibonacci(n_dirs)
    t, _ = mesh.intersect(a[None], dirs)
    ok = np.isfinite(t) & (t < 15)
    P = a + dirs[ok] * t[ok][:, None]
    to_b = P - b
    dist_b = np.linalg.norm(to_b, axis=1)
    tb, _ = mesh.intersect(b[None], to_b / dist_b[:, None])
    vis = np.isfinite(tb) & (np.abs(tb - dist_b) < 0.03 * dist_b + 0.05)
    P = P[vis]
    da = (P - a) / np.linalg.norm(P - a, axis=1, keepdims=True)
    db = (P - b) / np.linalg.norm(P - b, axis=1, keepdims=True)
    return da, db


def score(conv, obs, faces, panos, restrict=None):
    vals_a, vals_b = [], []
    for (i, j), (da, db) in obs.items():
        fa, xa, ya = conv.dir_to_pixel(panos[i]["rotation"], da, SIZE)
        fb, xb, yb = conv.dir_to_pixel(panos[j]["rotation"], db, SIZE)
        keep = np.ones(len(fa), bool) if restrict is None else (np.isin(fa, restrict) | np.isin(fb, restrict))
        if restrict is None:
            keep = (fa >= 1) & (fa <= 4) & (fb >= 1) & (fb <= 4)
        vals_a.append(np.array([sample(faces[i], f, x, y) for f, x, y in zip(fa[keep], xa[keep], ya[keep])]))
        vals_b.append(np.array([sample(faces[j], f, x, y) for f, x, y in zip(fb[keep], xb[keep], yb[keep])]))
    return ncc(np.concatenate(vals_a), np.concatenate(vals_b)), int(sum(len(v) for v in vals_a))


def main(bid: str):
    parts = json.loads((BUILDINGS / bid / "parts.json").read_text())["matterport"]
    panos = parts["panos"]
    mesh = Mesh.from_obj(MEDIA / bid / "mesh" / "mesh_50k.obj")
    pairs = pairs_for(panos)
    print(f"{bid}: {len(pairs)} camera pairs")
    obs = {(i, j): observations(mesh, panos[i], panos[j]) for i, j in pairs}
    print("  co-visible points per pair:", [len(v[0]) for v in obs.values()])
    faces = {k: load_faces(bid, panos[k]["id"]) for pair in pairs for k in pair}

    side, seen = [], set()
    for c in side_candidates():
        key = (c["transpose"], tuple(np.round(np.concatenate(c["side_dirs"] + c["side_rights"]), 6)))
        if key in seen:              # different parameters, identical mapping
            continue
        seen.add(key)
        conv = full(c)
        s, n = score(conv, obs, faces, panos)
        side.append((s, n, c))
    print(f"  distinct side conventions tested: {len(side)}")
    side.sort(key=lambda r: -np.nan_to_num(r[0], nan=-9))
    print("  side faces, top 5 NCC:", [round(s, 3) for s, _, _ in side[:5]], "| median of all", round(float(np.nanmedian([s for s, _, _ in side])), 3))
    best = side[0][2]
    caps = {}
    for face, key in ((0, "top"), (5, "bottom")):
        res = []
        for cap in cap_candidates():
            conv = full(best, **{key: cap})
            s, n = score(conv, obs, faces, panos, restrict=[face])
            res.append((s, n, cap))
        res.sort(key=lambda r: -np.nan_to_num(r[0], nan=-9))
        caps[key] = res[0][2]
        print(f"  {key} face, top 3 NCC:", [round(s, 3) for s, _, _ in res[:3]], "| points", res[0][1])
    conv = full(best, top=caps["top"], bottom=caps["bottom"])
    s_all, n_all = score(conv, obs, faces, panos, restrict=[0, 1, 2, 3, 4, 5])
    result = {"building": bid, "pairs": len(pairs), "best_side_ncc": side[0][0], "second_side_ncc": side[1][0],
              "median_side_ncc": float(np.nanmedian([s for s, _, _ in side])), "all_faces_ncc": s_all, "points": n_all,
              "convention": {"transpose": conv.transpose, "dirs": [list(map(float, d)) for d in conv.dirs],
                             "rights": [list(map(float, d)) for d in conv.rights], "downs": [list(map(float, d)) for d in conv.downs]}}
    write_json(CACHE / "geometry" / f"{bid}.json", result)
    print(json.dumps(result["convention"]))
    print(f"  all faces NCC {s_all:.3f} over {n_all} points")


if __name__ == "__main__":
    main(sys.argv[1])
