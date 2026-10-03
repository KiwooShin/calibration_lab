"""Small, vectorized SE(3) model for a generic seven-joint educational arm.

Column vectors; each local rotation is followed by a local translation.
Distances are meters and angles radians. The fixed palm origin is the final node.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

AXES = np.eye(3)[[2, 1, 0, 1, 0, 1, 2]]
LINKS = np.array([[0, 0, .12], [.07, 0, 0], [.28, 0, 0],
                 [.25, 0, 0], [.065, 0, 0], [.055, 0, 0], [.07, 0, 0]])
BASE = np.array([0., 0., .38])
TRUE_OFFSETS = np.deg2rad([2.1, -1.8, 1.4, 2.5, -.9, 1.6, -2.0])
LIMITS = np.array([2.3, 1.5, 2.2, 2.1, 2.3, 1.5, 2.3])
HOME = np.array([.3, -.45, .25, 1.1, -.2, -.55, .3])


def axis_rotation(axis, angle):
    angle = np.asarray(angle)
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0.]])
    c, s = np.cos(angle)[..., None, None], np.sin(angle)[..., None, None]
    return c * np.eye(3) + (1-c) * np.outer(axis, axis) + s * skew


def fk(q, offsets=None, tool_rotation=None, details=False):
    q = np.asarray(q, dtype=float)
    if q.shape[-1] != 7:
        raise ValueError('Expected seven joint angles')
    angles = q + (np.zeros(7) if offsets is None else offsets)
    shape = angles.shape[:-1]
    r = np.broadcast_to(np.eye(3), shape + (3, 3)).copy()
    p = np.broadcast_to(BASE, shape + (3,)).copy()
    nodes, world_axes = [p.copy()], []
    for j in range(7):
        world_axes.append(np.einsum('...ij,j->...i', r, AXES[j]))
        r = r @ axis_rotation(AXES[j], angles[..., j])
        p = p + np.einsum('...ij,j->...i', r, LINKS[j])
        nodes.append(p.copy())
    if tool_rotation is not None:
        r = r @ Rotation.from_rotvec(tool_rotation).as_matrix()
    if details:
        return p, r, np.stack(nodes, axis=-2), np.stack(world_axes, axis=-2)
    return p, r


def jacobian(q, offsets=None):
    p, _, nodes, axes = fk(q, offsets, details=True)
    linear = np.cross(axes, p[..., None, :] - nodes[..., :-1, :])
    return np.concatenate([linear, axes], axis=-1).swapaxes(-1, -2)


def configurations(n, rng, spread='diverse'):
    if spread == 'clustered':
        return HOME + rng.uniform(-.045, .045, (n, 7))
    return rng.uniform(-1, 1, (n, 7)) * LIMITS * .8


def observe(q, rng, noise_mm=0., offsets=TRUE_OFFSETS, payload=None, compliance=0.):
    p, r = predict(q, offsets, payload, compliance)
    if noise_mm:
        p = p + rng.normal(0, noise_mm / 1000, p.shape)
        # A fixed 0.15 degrees per millimeter of positional-noise setting.
        dr = Rotation.from_rotvec(rng.normal(0, np.deg2rad(noise_mm * .15), p.shape)).as_matrix()
        r = r @ dr
    return p, r


def payload_torque(q, offsets, payload):
    """Gravity torque from a point payload, evaluated at the unloaded pose.

    This is an explicit small-deflection approximation, not an implicit elastic
    equilibrium solver. A single compliance coefficient acts at elbow joint 4.
    """
    j = jacobian(q, offsets)
    mass = np.broadcast_to(np.asarray(payload), np.shape(q)[:-1])
    force = np.zeros(np.shape(q)[:-1] + (3,))
    force[..., 2] = -9.81 * mass
    return np.einsum('...ij,...i->...j', j[..., :3, :], force)


def predict(q, offsets, payload=None, compliance=0.):
    if payload is None or compliance == 0:
        return fk(q, offsets)
    effective = np.asarray(q).copy()
    effective[..., 3] += compliance * payload_torque(q, offsets, payload)[..., 3]
    return fk(effective, offsets)


def pose_error(predicted, observed):
    p, r = predicted
    po, ro = observed
    angular = Rotation.from_matrix(np.swapaxes(ro, -1, -2) @ r).as_rotvec()
    return np.concatenate([p - po, angular], axis=-1)


def residual(parameters, q, observations, payload=None, fit_compliance=False):
    c = parameters[7] * .001 if fit_compliance else 0.
    e = pose_error(predict(q, parameters[:7], payload, c), observations)
    return (e / np.array([.001] * 3 + [np.deg2rad(.15)] * 3)).ravel()


def fit(q, observations, payload=None, fit_compliance=False):
    size = 8 if fit_compliance else 7
    initial = np.zeros(size)
    history = [initial.copy()]
    lower, upper = np.full(size, -.2), np.full(size, .2)
    if fit_compliance:
        lower[7], upper[7] = 0., 10.
    result = least_squares(residual, initial,
                           args=(q, observations, payload, fit_compliance),
                           bounds=(lower, upper), max_nfev=100,
                           ftol=1e-11, xtol=1e-11, gtol=1e-10,
                           callback=lambda x: history.append(x.copy()))
    if not result.success:
        raise RuntimeError(result.message)
    if not np.array_equal(history[-1], result.x):
        history.append(result.x.copy())
    return result.x, history


def metrics(predicted, observed):
    e = pose_error(predicted, observed)
    pos = np.linalg.norm(e[..., :3], axis=-1) * 1000
    rot = np.rad2deg(np.linalg.norm(e[..., 3:], axis=-1))
    return {'position_mm': float(np.sqrt(np.mean(pos ** 2))),
            'orientation_deg': float(np.sqrt(np.mean(rot ** 2))),
            'p95_mm': float(np.percentile(pos, 95)),
            'per_pose_mm': pos.tolist()}


def parameter_jacobian(q, point_only=False, include_tool=False, whiten=True):
    """Finite-difference sensitivity at the nominal model, per radian.

    Tool rotation adds three right-multiplied terminal-frame rotation parameters.
    Its z rotation and final z-joint offset can be redundant in some geometries;
    all rank results are measured, never assumed from parameter counts.
    """
    zero = np.zeros(10 if include_tool else 7)
    reference = fk(q)

    def values(x):
        pose = fk(q, x[:7], x[7:] if include_tool else None)
        e = pose_error(pose, reference)
        if whiten:
            e = e / np.array([.001] * 3 + [np.deg2rad(.15)] * 3)
        return e[..., :3] if point_only else e

    eps = 1e-6
    cols = []
    for k in range(len(zero)):
        dx = zero.copy()
        dx[k] = eps
        cols.append((values(dx) - values(-dx)) / (2 * eps))
    return np.stack(cols, axis=-1)


def scene(q, offsets=None, tool_rotation=None):
    p, r, nodes, _ = fk(q, offsets, tool_rotation, details=True)
    return {'nodes': nodes.tolist(), 'position': p.tolist(), 'rotation': r.tolist()}


def native(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {k: native(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [native(v) for v in value]
    return value
