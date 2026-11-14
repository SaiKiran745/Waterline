"""Panorama pixel -> 3D point in mesh coordinates, by ray-casting against the Matterport mesh.

Facts this rests on (docs/DATA_NOTES.md, section 4):
- Mesh and Model API positions share one frame: z up, metres, floor near z = 0.
- `PanoramicImageLocation.position` is the camera centre (about 1.4 m above its floor anchor).
- `PanoramicImageLocation.rotation` is a quaternion (x, y, z, w); in the data it is a rotation about world z (yaw).
- A skybox has 6 square faces (front, back, left, right, up, down), fetched as faces 0-5.
The face order and each face's image orientation are not documented. They were measured from the data by
multi-view photo-consistency (app.survey.calibrate) and are recorded in CONVENTION below.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

EPS = 1e-7


def load_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    verts, faces = [], []
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                verts.append([float(t) for t in line.split()[1:4]])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):            # fan-triangulate polygons
                    faces.append([idx[0], idx[k], idx[k + 1]])
    v = np.asarray(verts, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    f = np.where(f > 0, f - 1, len(v) + f)                  # OBJ is 1-based; negative = relative
    return v, f


class Mesh:
    """Brute-force Moller-Trumbore ray caster over all triangles, chunked over rays (float32)."""

    def __init__(self, vertices: np.ndarray, faces: np.ndarray):
        tri = vertices[faces].astype(np.float32)
        self.v0 = tri[:, 0]
        self.e1 = tri[:, 1] - tri[:, 0]
        self.e2 = tri[:, 2] - tri[:, 0]
        n = np.cross(self.e1, self.e2)
        self.normals = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), EPS)
        self.bounds = (vertices.min(axis=0), vertices.max(axis=0))

    @classmethod
    def from_obj(cls, path: Path) -> "Mesh":
        return cls(*load_obj(path))

    def intersect(self, origins: np.ndarray, dirs: np.ndarray, chunk: int = 24, max_dist: float = 200.0):
        """Return (t, triangle index) per ray; t is NaN where the ray misses. dirs need not be unit length."""
        origins = np.atleast_2d(origins).astype(np.float32)
        dirs = np.atleast_2d(dirs).astype(np.float32)
        if len(origins) == 1 and len(dirs) > 1:
            origins = np.repeat(origins, len(dirs), axis=0)
        t_out = np.full(len(dirs), np.nan, dtype=np.float64)
        i_out = np.full(len(dirs), -1, dtype=np.int64)
        for s in range(0, len(dirs), chunk):
            o = origins[s:s + chunk, None, :]
            d = dirs[s:s + chunk, None, :]
            p = np.cross(d, self.e2[None])
            det = np.einsum("rtk,tk->rt", p, self.e1)
            ok = np.abs(det) > EPS
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            tv = o - self.v0[None]
            u = np.einsum("rtk,rtk->rt", tv, p) * inv
            q = np.cross(tv, self.e1[None])
            v = np.einsum("rk,rtk->rt", d[:, 0, :], q) * inv
            t = np.einsum("tk,rtk->rt", self.e2, q) * inv
            hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4) & (t < max_dist)
            t = np.where(hit, t, np.inf)
            best = np.argmin(t, axis=1)
            tb = t[np.arange(len(best)), best]
            found = np.isfinite(tb)
            t_out[s:s + chunk][found] = tb[found]
            i_out[s:s + chunk][found] = best[found]
        return t_out, i_out


def quat_matrix(q: dict) -> np.ndarray:
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    n = np.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


@dataclass(frozen=True)
class Convention:
    """How skybox faces 0-5 sit in the camera's local frame.

    world_dir = M(q) @ local_dir, where M is the quaternion matrix (transpose=False) or its transpose.
    For face i: `dirs[i]` is the outward direction of the face centre, `rights[i]` the direction of +x in the
    image (left to right) and `downs[i]` the direction of +y in the image (top to bottom), all local unit axes.
    """
    transpose: bool
    dirs: tuple
    rights: tuple
    downs: tuple

    def rot(self, q: dict) -> np.ndarray:
        m = quat_matrix(q)
        return m.T if self.transpose else m

    def pixel_to_dir(self, q: dict, face: int, x: np.ndarray, y: np.ndarray, size: int) -> np.ndarray:
        """Pixel centres (x, y) on a face of `size` px -> unit world directions."""
        a = 2.0 * (np.asarray(x, dtype=np.float64) + 0.5) / size - 1.0
        b = 2.0 * (np.asarray(y, dtype=np.float64) + 0.5) / size - 1.0
        local = (np.asarray(self.dirs[face])[None] + a[..., None] * np.asarray(self.rights[face])[None]
                 + b[..., None] * np.asarray(self.downs[face])[None])
        world = local @ self.rot(q).T
        return world / np.linalg.norm(world, axis=-1, keepdims=True)

    def dir_to_pixel(self, q: dict, world_dirs: np.ndarray, size: int):
        """Unit world directions -> (face, x, y) with x, y in pixels (float)."""
        local = np.atleast_2d(world_dirs) @ self.rot(q)
        d = np.asarray(self.dirs, dtype=np.float64)
        proj = local @ d.T
        face = np.argmax(proj, axis=1)
        depth = proj[np.arange(len(face)), face]
        r = np.einsum("nk,nk->n", local, np.asarray(self.rights, dtype=np.float64)[face]) / depth
        b = np.einsum("nk,nk->n", local, np.asarray(self.downs, dtype=np.float64)[face]) / depth
        return face, (r + 1.0) * size / 2.0 - 0.5, (b + 1.0) * size / 2.0 - 0.5


# Measured by `python -m app.survey.calibrate` (docs/DATA_NOTES.md, "Panorama geometry"), not assumed:
# photo-consistency NCC 0.884 vs 0.622 for the runner-up on Building H (8 camera pairs, 32 distinct side
# conventions), and the same winner on Building D (0.693 vs 0.252). world = R(q) @ local, local up = +z.
# Faces: 0 up, 1 local +x, 2 local -y, 3 local -x, 4 local +y, 5 down.
CONVENTION = Convention(
    transpose=False,
    dirs=((0, 0, 1), (1, 0, 0), (0, -1, 0), (-1, 0, 0), (0, 1, 0), (0, 0, -1)),
    rights=((0, -1, 0), (0, -1, 0), (-1, 0, 0), (0, 1, 0), (1, 0, 0), (0, -1, 0)),
    downs=((1, 0, 0), (0, 0, -1), (0, 0, -1), (0, 0, -1), (0, 0, -1), (-1, 0, 0)),
)


@lru_cache(maxsize=16)
def mesh_for(path: str) -> Mesh:
    return Mesh.from_obj(Path(path))


def cast_pixel(mesh: Mesh, conv: Convention, position: dict, rotation: dict, face: int, x: float, y: float,
               size: int) -> dict | None:
    """Ray from the camera through pixel (x, y) of `face`; returns the hit point and distance, or None."""
    origin = np.array([position["x"], position["y"], position["z"]])
    d = conv.pixel_to_dir(rotation, face, np.array([x]), np.array([y]), size)[0]
    t, tri = mesh.intersect(origin[None], d[None])
    if not np.isfinite(t[0]):
        return None
    p = origin + d * t[0]
    return {"point": {"x": float(p[0]), "y": float(p[1]), "z": float(p[2])}, "distance_m": float(t[0]),
            "normal_z": float(mesh.normals[tri[0]][2])}


def floor_z_below(mesh: Mesh, position: dict) -> float | None:
    """z of the mesh straight below a camera (the local floor)."""
    origin = np.array([[position["x"], position["y"], position["z"]]])
    t, _ = mesh.intersect(origin, np.array([[0.0, 0.0, -1.0]]))
    return float(position["z"] - t[0]) if np.isfinite(t[0]) else None
