"""Cube-face convention and ray casting."""
import numpy as np

from app.survey.geometry import CONVENTION as C, Mesh

Q0 = {"x": 0, "y": 0, "z": 0, "w": 1}
YAW90 = {"x": 0, "y": 0, "z": float(np.sin(np.pi / 4)), "w": float(np.cos(np.pi / 4))}


def test_face_centres():
    for face, want in ((0, (0, 0, 1)), (5, (0, 0, -1)), (1, (1, 0, 0))):
        d = C.pixel_to_dir(Q0, face, np.array([1023.5]), np.array([1023.5]), 2048)[0]
        assert np.allclose(d, want, atol=1e-9)


def test_pixel_direction_round_trip():
    rng = np.random.default_rng(0)
    for q in (Q0, YAW90):
        for face in range(6):
            x, y = rng.uniform(0, 2047, 50), rng.uniform(0, 2047, 50)
            f, x2, y2 = C.dir_to_pixel(q, C.pixel_to_dir(q, face, x, y, 2048), 2048)
            assert (f == face).all() and np.allclose(x, x2) and np.allclose(y, y2)


def test_side_image_up_is_world_up():
    d_top = C.pixel_to_dir(YAW90, 2, np.array([1023.5]), np.array([0.0]), 2048)[0]
    d_bot = C.pixel_to_dir(YAW90, 2, np.array([1023.5]), np.array([2047.0]), 2048)[0]
    assert d_top[2] > 0.7 and d_bot[2] < -0.7


def test_ray_hits_floor_plane():
    v = np.array([[-10, -10, 0], [10, -10, 0], [10, 10, 0], [-10, 10, 0]], float)
    m = Mesh(v, np.array([[0, 1, 2], [0, 2, 3]]))
    t, _ = m.intersect(np.array([[1.0, 2.0, 1.4]]), np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]))
    assert abs(t[0] - 1.4) < 1e-5 and np.isnan(t[1])
