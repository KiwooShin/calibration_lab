"""Calibrate two arm chains from head-camera 3D landmark predictions.

No hand orientation is supplied to the optimizer. The perception boundary is
labeled camera-frame positions, visibility, and diagonal measurement uncertainty.
Synthetic truth is used only to generate a demo and evaluate held-out errors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from model import AXES, LINKS, axis_rotation, native

NAMES = ['upper_arm', 'elbow', 'forearm', 'wrist', 'palm', 'palm_left', 'palm_right', 'hand_tip']
GROUPS = {'palm': [4], 'hand': [4, 5, 6, 7], 'all': list(range(8))}
TRUE = np.array([[2.1, -1.8, 1.4, 2.5, -.9, 1.6, -2., 3., -4.],
                 [-1.7, 1.3, -2.2, 1.8, 1.1, -1.4, 2.3, -2.5, 3.5]])
CAMERA_ORIGIN = np.array([.04, 0., 1.43])
forward = np.array([.65, 0., -.65]) / np.sqrt(.65**2 * 2)
right = np.array([0., -1., 0.])
CAMERA_ROTATION = np.column_stack([right, np.cross(forward, right), forward])
T_BASE_CAMERA = np.eye(4)
T_BASE_CAMERA[:3, :3] = CAMERA_ROTATION
T_BASE_CAMERA[:3, 3] = CAMERA_ORIGIN
K = np.array([[470., 0., 480.], [0., 470., 300.], [0., 0., 1.]])


def arm(q, parameters, side=0):
    """Return torso-frame landmarks, link nodes, and palm orientation.

    Per arm: 7 encoder offsets [degrees], 2 length corrections [millimeters].
    Right chain is the reflected physical layout; S R S is a proper rotation.
    Upper/forearm features are known fractional link attachment positions.
    """
    q = np.asarray(q, dtype=float)
    parameters = np.asarray(parameters)
    angles = q + np.deg2rad(parameters[:7])
    links = LINKS.copy()
    links[2, 0] += parameters[7] / 1000
    links[3, 0] += parameters[8] / 1000
    r = np.broadcast_to(np.eye(3), q.shape[:-1] + (3, 3)).copy()
    p = np.zeros(q.shape[:-1] + (3,))
    nodes = [p.copy()]
    features = {}
    for j in range(7):
        r = r @ axis_rotation(AXES[j], angles[..., j])
        if j in (2, 3):
            attachment = np.array([links[j, 0] * .5, .035 if j == 2 else -.03, .02])
            features[j] = p + np.einsum('...ij,j->...i', r, attachment)
        p = p + np.einsum('...ij,j->...i', r, links[j])
        nodes.append(p.copy())
    hand = [p + np.einsum('...ij,j->...i', r, v)
            for v in ([.035, .04, 0], [.035, -.04, 0], [.09, 0, 0])]
    landmarks = np.stack([features[2], nodes[3], features[3], nodes[4], p, *hand], axis=-2)
    nodes = np.stack(nodes, axis=-2)
    reflection = np.diag([1., -1. if side else 1., 1.])
    shoulder = np.array([0., -.24 if side else .24, .96])
    landmarks = landmarks @ reflection + shoulder
    nodes = nodes @ reflection + shoulder
    r = reflection @ r @ reflection
    return landmarks, nodes, r


def predict_landmarks(q, parameters):
    parameters = np.asarray(parameters).reshape(2, 9)
    return np.stack([arm(q[:, side], parameters[side], side)[0] for side in range(2)], axis=1)


def to_camera(points, transforms=T_BASE_CAMERA):
    """T_base_camera maps camera column vectors to torso coordinates."""
    t = np.asarray(transforms)
    if t.ndim == 2:
        return (points - t[:3, 3]) @ t[:3, :3]
    return np.einsum('n...j,njk->n...k', points - t[:, None, None, :3, 3], t[:, :3, :3])


def to_base(points, transforms=T_BASE_CAMERA):
    t = np.asarray(transforms)
    if t.ndim == 2:
        return points @ t[:3, :3].T + t[:3, 3]
    return np.einsum('n...j,nkj->n...k', points, t[:, :3, :3]) + t[:, None, None, :3, 3]


def project(points):
    z = points[..., 2]
    uv = points[..., :2] / np.maximum(z[..., None], 1e-9) * np.array([K[0, 0], K[1, 1]]) + K[:2, 2]
    visible = (z > .12) & (z < 2.) & (uv[..., 0] >= 0) & (uv[..., 0] < 960) & (uv[..., 1] >= 0) & (uv[..., 1] < 600)
    return uv, visible


def sample_configurations(count, rng):
    # Reach forward and vary each joint while keeping most points in head view.
    center = np.array([-.25, -.15, .15, .85, 0., -.3, 0.])
    extent = np.array([.42, .42, .8, .55, .8, .6, .9])
    return center + rng.uniform(-1, 1, (count, 2, 7)) * extent


def synthetic_dataset(count=40, noise_mm=2., dropout=.15, outliers=.04, seed=51):
    rng = np.random.default_rng(seed)
    q = sample_configurations(count, rng)
    truth = predict_landmarks(q, TRUE)
    camera_truth = to_camera(truth)
    _, fov = project(camera_truth)
    confidence = rng.uniform(.55, 1., (count, 2, 8))
    sigma = np.maximum(noise_mm, .05) / 1000 * np.array([1., 1., 2.]) / np.sqrt(confidence[..., None])
    observed = camera_truth + rng.normal(size=camera_truth.shape) * sigma * (noise_mm > 0)
    visible = fov & (rng.uniform(size=fov.shape) >= dropout)
    corrupt = visible & (rng.uniform(size=fov.shape) < outliers)
    observed[corrupt] += rng.normal(0, .025, (int(corrupt.sum()), 3))
    return {'q_rad': q, 'positions_camera_m': observed, 'visible': visible,
            'sigma_camera_m': sigma, 'confidence': confidence,
            'T_base_camera': np.broadcast_to(T_BASE_CAMERA, (count, 4, 4)).copy(),
            'landmark_names': NAMES.copy()}, {'truth': truth, 'outliers': corrupt, 'fov': fov}


def validate_dataset(raw):
    """Validate the real perception/encoder interface; no truth is required."""
    data = {}
    for key in ['q_rad', 'positions_camera_m', 'sigma_camera_m', 'T_base_camera']:
        data[key] = np.array(raw[key], dtype=float, copy=True)
    data['visible'] = np.asarray(raw['visible'], dtype=bool)
    n = len(data['q_rad'])
    expected = {'q_rad': (n, 2, 7), 'positions_camera_m': (n, 2, 8, 3),
                'sigma_camera_m': (n, 2, 8, 3), 'visible': (n, 2, 8), 'T_base_camera': (n, 4, 4)}
    if n < 4:
        raise ValueError('At least four synchronized frames are required')
    for key, shape in expected.items():
        if data[key].shape != shape:
            raise ValueError(f'{key} must have shape {shape}')
    if raw.get('landmark_names') != NAMES:
        raise ValueError('Landmark labels must match the documented order and link attachments')
    if not np.all(np.isfinite(data['q_rad'])) or not np.all(np.isfinite(data['T_base_camera'])):
        raise ValueError('Joint readings and camera transforms must be finite')
    mask = data['visible']
    if not np.all(np.isfinite(data['positions_camera_m'][mask])):
        raise ValueError('Visible observations must be finite')
    if not np.all(np.isfinite(data['sigma_camera_m'][mask])) or np.any(data['sigma_camera_m'][mask] <= 0):
        raise ValueError('Visible observations need positive finite uncertainty')
    # Invalid/missing predictions must not leak NaNs through masked residuals.
    data['positions_camera_m'][~mask] = 0.
    data['sigma_camera_m'][~mask] = 1.
    t = data['T_base_camera']
    r = t[:, :3, :3]
    if not np.allclose(r.swapaxes(-1, -2) @ r, np.eye(3), atol=1e-6) or not np.allclose(np.linalg.det(r), 1., atol=1e-6) or not np.allclose(t[:, 3], [0, 0, 0, 1]):
        raise ValueError('Camera transforms must be rigid homogeneous transforms')
    data['landmark_names'] = NAMES.copy()
    return data


def fit_landmarks(raw, group='all', robust=True):
    data = validate_dataset(raw)
    mask = data['visible'].copy()
    allowed = np.zeros(8, dtype=bool)
    allowed[GROUPS[group]] = True
    mask &= allowed
    if np.any(mask.sum(axis=(0, 2)) < 12):
        raise ValueError('Too few visible selected landmarks on one arm; collect more frames')

    def residual(parameters):
        predicted = to_camera(predict_landmarks(data['q_rad'], parameters), data['T_base_camera'])
        return ((predicted - data['positions_camera_m']) / data['sigma_camera_m'])[mask].ravel()

    history = [np.zeros(18)]
    lower = np.tile([-12.] * 7 + [-15., -15.], 2)
    upper = -lower
    fit = least_squares(residual, history[0], bounds=(lower, upper), loss='soft_l1' if robust else 'linear',
                        f_scale=2., x_scale='jac', max_nfev=160,
                        ftol=1e-10, xtol=1e-10, gtol=1e-9,
                        callback=lambda x: history.append(x.copy()))
    if not fit.success:
        raise ValueError(f'Calibration did not converge: {fit.message}')
    if not np.array_equal(history[-1], fit.x):
        history.append(fit.x.copy())
    # Raw whitened sensitivity, not the loss-modified Jacobian from the solver.
    eps = 1e-4
    sensitivity = np.stack([(residual(fit.x + np.eye(18)[i]*eps)-residual(fit.x-np.eye(18)[i]*eps))/(2*eps) for i in range(18)], axis=1)
    s = np.linalg.svd(sensitivity, compute_uv=False)
    rank = int(np.sum(s > s[0] * 1e-7))
    return {'parameters': fit.x.reshape(2, 9), 'history': history,
            'rank': rank, 'singular_values': s,
            'condition': float(s[0]/s[-1]) if rank == 18 else None,
            'used_observations': int(mask.sum()), 'mask': mask,
            'at_bound': bool(np.any(np.abs(fit.x) >= upper-.001))}


def evaluate(q, parameters):
    error = np.linalg.norm(predict_landmarks(q, parameters) - predict_landmarks(q, TRUE), axis=-1) * 1000
    return {'landmark_mm': float(np.sqrt(np.mean(error**2))),
            'palm_mm': float(np.sqrt(np.mean(error[:, :, 4]**2))),
            'per_landmark_mm': np.sqrt(np.mean(error**2, axis=(0, 1)))}


def arm_scene(q, parameters, side):
    landmarks, nodes, r = arm(q, parameters, side)
    return {'nodes': nodes, 'position': landmarks[4], 'rotation': r, 'landmarks': landmarks}


def self_observation(count=40, noise_mm=2., dropout=.15, outliers=.04, group='all', seed=51):
    dataset, truth = synthetic_dataset(count, noise_mm, dropout, outliers, seed)
    test_q = sample_configurations(160, np.random.default_rng(151))
    fitted = {}
    for key in GROUPS:
        try:
            fitted[key] = fit_landmarks(dataset, key)
        except ValueError:
            if key == group:
                raise
    selected = fitted[group]
    comparison = [{'group': key, 'label': {'palm': 'Palm center only', 'hand': 'Hand landmarks', 'all': 'Arm + hand landmarks'}[key],
                   **evaluate(test_q, f['parameters']), 'rank': f['rank'],
                   'used_observations': f['used_observations']} for key, f in fitted.items()]
    frames = [{'parameters': x.reshape(2, 9), 'metrics': evaluate(test_q, x)} for x in selected['history']]
    samples = []
    for i, q in enumerate(dataset['q_rad']):
        observed = dataset['positions_camera_m'][i]
        uv, in_frame = project(observed)
        samples.append({'observed_camera': observed, 'observed_base': to_base(observed), 'observed_uv': uv,
                        'visible': dataset['visible'][i] & in_frame, 'used': selected['mask'][i],
                        'confidence': dataset['confidence'][i], 'sigma_mm': dataset['sigma_camera_m'][i] * 1000,
                        'truth': [arm_scene(q[side], TRUE[side], side) for side in range(2)],
                        'iterations': [[arm_scene(q[side], f['parameters'][side], side) for side in range(2)] for f in frames]})
    return native({'title': 'See your arms. Calibrate the model.', 'count': count,
                   'noise_mm': noise_mm, 'dropout': dropout, 'outliers': outliers, 'group': group,
                   'initial': evaluate(test_q, np.zeros((2, 9))), 'final': evaluate(test_q, selected['parameters']),
                   'frames': frames, 'samples': samples, 'comparison': comparison,
                   'landmark_names': NAMES, 'true_parameters': TRUE, 'estimated_parameters': selected['parameters'],
                   'rank': selected['rank'], 'condition': selected['condition'], 'at_bound': selected['at_bound'],
                   'used_observations': selected['used_observations'], 'camera': {'T_base_camera': T_BASE_CAMERA, 'K': K, 'width': 960, 'height': 600},
                   'note': 'Synthetic perception outputs, not a trained detector. Positions only; no hand orientation enters the fit. Camera-to-torso transforms and landmark attachments are known. Field-of-view checks plus random dropout approximate visibility; no rendered occlusion model. Robust residuals use per-axis uncertainty; depth noise is twice lateral noise. Holdout uses 160 new two-arm configurations.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Real perception and encoder dataset in the documented JSON format')
    parser.add_argument('--output', type=Path, default=Path('results/landmark_fit.json'))
    parser.add_argument('--write-example', type=Path, help='Write a synthetic input dataset for integration')
    parser.add_argument('--group', choices=list(GROUPS), default='all')
    args = parser.parse_args()
    if args.write_example:
        dataset, _ = synthetic_dataset()
        args.write_example.parent.mkdir(parents=True, exist_ok=True)
        args.write_example.write_text(json.dumps(native(dataset), allow_nan=False))
        print(f'Wrote synthetic perception example: {args.write_example}')
        return
    if not args.input:
        parser.error('--input or --write-example is required')
    fit = fit_landmarks(json.loads(args.input.read_text()), args.group)
    fit.pop('mask')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(native(fit), indent=2, allow_nan=False))
    print(f'Wrote fitted parameters to {args.output}; rank {fit["rank"]}/18')


if __name__ == '__main__':
    main()
