"""Deterministic experiments. Each returns the numerical evidence shown in the UI."""
import numpy as np
from scipy.spatial.transform import Rotation
from model import (TRUE_OFFSETS, HOME, LIMITS, fk, fit, observe, configurations, metrics,
                   parameter_jacobian, scene, native, jacobian, pose_error,
                   payload_torque, predict)


def ghost(count=32, noise_mm=.5, spread='diverse', seed=42):
    rng = np.random.default_rng(seed)
    q = configurations(count, rng, spread)
    observations = observe(q, rng, noise_mm)
    fitted, history = fit(q, observations)
    test = configurations(160, np.random.default_rng(194), 'diverse')
    truth = fk(test, TRUE_OFFSETS)
    initial = metrics(fk(test), truth)
    final = metrics(fk(test, fitted), truth)
    sensitivity = parameter_jacobian(q).reshape(-1, 7)
    singular = np.linalg.svd(sensitivity, compute_uv=False)
    frames = [{'truth': scene(HOME, TRUE_OFFSETS), 'estimate': scene(HOME, x),
               'offsets_deg': np.rad2deg(x),
               'metrics': metrics(fk(test, x), truth)} for x in history]
    return native({'title': 'Fix the ghost arm', 'count': count, 'noise_mm': noise_mm,
                   'spread': spread, 'seed': seed, 'initial': initial, 'final': final,
                   'true_offsets_deg': np.rad2deg(TRUE_OFFSETS),
                   'estimated_offsets_deg': np.rad2deg(fitted), 'frames': frames,
                   'test_positions': truth[0], 'singular_values': singular,
                   'condition': singular[0] / singular[-1],
                   'training_positions': observations[0], 'training_q': q})


def self_motion(offsets=None, steps=100):
    """Continuation along the local one-dimensional null space, with retraction.

    The Newton correction preserves the complete SE(3) target after each finite
    joint step. Stops at a joint limit or a failure to converge.
    """
    q = HOME.copy()
    target_p, target_r = fk(q, offsets)
    trajectory = [q.copy()]
    previous = None
    for _ in range(steps):
        j = jacobian(q, offsets)
        _, s, vh = np.linalg.svd(j)
        if s[-1] < 1e-5:
            break
        direction = vh[-1]
        if previous is not None and direction @ previous < 0:
            direction = -direction
        previous = direction
        candidate = q + .035 * direction
        for _ in range(12):
            p, r = fk(candidate, offsets)
            error = np.r_[target_p-p, Rotation.from_matrix(target_r @ r.T).as_rotvec()]
            if np.linalg.norm(error) < 1e-10:
                break
            candidate += np.linalg.pinv(jacobian(candidate, offsets), rcond=1e-9) @ error
        if np.any(np.abs(candidate) > LIMITS * .98):
            break
        if np.linalg.norm(pose_error(fk(candidate, offsets), (target_p, target_r))) > 1e-7:
            break
        q = candidate
        trajectory.append(q.copy())
    return np.array(trajectory)


def drift(q, offsets):
    p, r = fk(q, offsets)
    errors = pose_error((p, r), (np.broadcast_to(p[0], p.shape), np.broadcast_to(r[0], r.shape)))
    return {'max_position_mm': float(np.max(np.linalg.norm(errors[:, :3], axis=1)) * 1000),
            'max_orientation_deg': float(np.rad2deg(np.max(np.linalg.norm(errors[:, 3:], axis=1)))),
            'trace_mm': (p - p[0]) * 1000, 'positions': p}


def redundancy(seed=43):
    rng = np.random.default_rng(seed)
    before_q = self_motion()
    workspace = configurations(32, rng)
    fitted, _ = fit(workspace, observe(workspace, rng, .5))
    after_q = self_motion(fitted)
    test = configurations(160, np.random.default_rng(194))
    truth = fk(test, TRUE_OFFSETS)
    sweep_data = before_q[np.linspace(0, len(before_q)-1, 24).astype(int)]
    diverse = configurations(24, rng)
    datasets = [('Fixed-hand sweep', sweep_data), ('Workspace samples', diverse),
                ('Mixed samples', np.concatenate([sweep_data[::2], diverse[::2]]))]
    comparison = []
    for label, q in datasets:
        estimate, _ = fit(q, observe(q, rng, .5))
        s = np.linalg.svd(parameter_jacobian(q).reshape(-1, 7), compute_uv=False)
        comparison.append({'label': label, 'count': len(q),
                           'rank': int(np.sum(s > s[0] * 1e-8)),
                           'condition': float(s[0] / max(s[-1], 1e-12)),
                           **metrics(fk(test, estimate), truth)})
    def frames(qs, planner):
        return [{'truth': scene(q, TRUE_OFFSETS), 'estimate': scene(q, planner),
                 'q_deg': np.rad2deg(q)} for q in qs]
    return native({'title': 'Move the elbow, hold the hand',
                   'before_frames': frames(before_q, None), 'after_frames': frames(after_q, fitted),
                   'before': drift(before_q, TRUE_OFFSETS), 'after': drift(after_q, TRUE_OFFSETS),
                   'nominal': drift(before_q, np.zeros(7)), 'comparison': comparison,
                   'joint_travel_deg': np.rad2deg(np.linalg.norm(before_q[-1] - before_q[0])),
                   'before_q': before_q, 'after_q': after_q,
                   'note': 'After calibration, a new self-motion is planned with the fitted model. Drift is relative to each trajectory’s first physical hand pose.'})


def information_selection(q, budget):
    # Whiten measurements, then normalize parameters by a 3-degree prior scale.
    a = parameter_jacobian(q) * np.deg2rad(3.)
    contributions = np.einsum('nki,nkj->nij', a, a)
    information = np.eye(7)
    available = np.ones(len(q), dtype=bool)
    selected, scores, logdet_history = [], [], []
    for _ in range(budget):
        current = np.linalg.slogdet(information)[1]
        gains = np.linalg.slogdet(information[None] + contributions)[1] - current
        gains[~available] = -np.inf
        index = int(np.argmax(gains))
        scores.append(np.where(available, gains, 0).tolist())
        selected.append(index)
        available[index] = False
        information += contributions[index]
        logdet_history.append(float(np.linalg.slogdet(information)[1]))
    return selected, scores, logdet_history


def active_selection(seed=44, repeats=10):
    rng = np.random.default_rng(seed)
    # Same pool and same noisy observations for all policies; 2/3 of the pool
    # deliberately contains similar poses to make redundant sampling visible.
    q = np.concatenate([configurations(120, rng, 'clustered'), configurations(60, rng)])
    observations = observe(q, rng, 1.)
    test = configurations(160, np.random.default_rng(194))
    truth = fk(test, TRUE_OFFSETS)
    budgets = [2, 4, 8, 12, 20, 32]
    order, gains, logdet = information_selection(q, max(budgets))
    random_orders = [rng.permutation(len(q))[:max(budgets)] for _ in range(repeats)]
    curve = []
    for count in budgets:
        indices = order[:count]
        params, _ = fit(q[indices], (observations[0][indices], observations[1][indices]))
        greedy = metrics(fk(test, params), truth)
        trials = []
        for random_order in random_orders:
            indices = random_order[:count]
            params, _ = fit(q[indices], (observations[0][indices], observations[1][indices]))
            trials.append(metrics(fk(test, params), truth))
        curve.append({'count': count, 'greedy_mm': greedy['position_mm'],
                      'greedy_deg': greedy['orientation_deg'],
                      'random_median_mm': float(np.median([t['position_mm'] for t in trials])),
                      'random_q25_mm': float(np.percentile([t['position_mm'] for t in trials], 25)),
                      'random_q75_mm': float(np.percentile([t['position_mm'] for t in trials], 75)),
                      'random_median_deg': float(np.median([t['orientation_deg'] for t in trials])),
                      'random_trials_mm': [t['position_mm'] for t in trials]})
    return native({'title': 'Choose the next calibration pose', 'curve': curve,
                   'candidate_positions': fk(q)[0], 'candidate_q': q,
                   'selection': order, 'gain_frames': gains, 'logdet': logdet,
                   'frames': [{'estimate': scene(q[i]), 'truth': scene(q[i], TRUE_OFFSETS)} for i in order],
                   'random_repeats': repeats, 'pool_size': len(q), 'seed': seed,
                   'note': '180 candidates: 120 clustered + 60 diverse. Shared 1 mm / 0.15° noisy observations. Random bands describe selection variability, not confidence intervals. Scores use a fixed nominal model and a 3° isotropic parameter prior.'})


def observability(seed=45):
    rng = np.random.default_rng(seed)
    broad = configurations(32, rng)
    narrow = HOME + rng.uniform(-.002, .002, (32, 7))
    cases = {}
    for coverage, q in [('broad', broad), ('narrow', narrow)]:
        for measurement, point_only in [('point', True), ('pose', False)]:
            a = parameter_jacobian(q, point_only=point_only, include_tool=True)
            # All ten parameters are rotations, normalized by the same 1° scale.
            a = a.reshape(-1, 10) * np.deg2rad(1.) / np.sqrt(len(q))
            _, s, vh = np.linalg.svd(a, full_matrices=False)
            rank = int(np.sum(s > s[0] * 1e-7))
            weak = vh[-1]
            weak *= np.sign(weak[np.argmax(np.abs(weak))])
            frames = []
            for amplitude in np.linspace(-8, 8, 65):
                params = weak * np.deg2rad(amplitude)
                stats = metrics(fk(q, params[:7], params[7:]), fk(q))
                frames.append({'truth': scene(q[0]),
                               'estimate': scene(q[0], params[:7], params[7:]),
                               'parameter_delta_deg': np.rad2deg(params),
                               'amplitude_deg': amplitude, 'metrics': stats})
            cases[f'{measurement}_{coverage}'] = {
                'measurement': measurement, 'coverage': coverage, 'rank': rank,
                'parameter_count': 10, 'singular_values': s,
                'condition': float(s[0]/s[-1]) if rank == 10 else None,
                'weak_direction': weak, 'frames': frames,
                'positions': fk(q)[0], 'q': q}
    return native({'title': 'What can the camera actually identify?', 'cases': cases,
                   'parameter_names': ['J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7', 'Tool x', 'Tool y', 'Tool z'],
                   'note': 'Seven encoder offsets plus three terminal-frame rotations. The measured point is the terminal-frame origin; rotating its coordinate axes cannot move that point. Narrow data varies each joint by only ±0.002 rad. Rank is local, with relative threshold 10⁻⁷; singular values are noise-whitened and normalized per pose and per degree.'})


TRUE_COMPLIANCE = .0025  # rad / Nm at elbow joint 4 only


def loaded_scene(q, offsets, payload, compliance):
    effective = np.asarray(q).copy()
    effective[3] += compliance * payload_torque(q, offsets, payload)[3]
    return scene(effective, offsets)


def compliance(seed=46):
    rng = np.random.default_rng(seed)
    base_q = configurations(32, rng)
    q = np.tile(base_q, (3, 1))
    masses = np.repeat([0., 1., 3.], len(base_q))
    observations = observe(q, rng, .5, payload=masses, compliance=TRUE_COMPLIANCE)
    unloaded_fit, _ = fit(base_q, (observations[0][:32], observations[1][:32]))
    mixed_rigid, _ = fit(q, observations)
    elastic_fit, _ = fit(q, observations, payload=masses, fit_compliance=True)
    estimated_c = elastic_fit[7] * .001
    test = configurations(160, np.random.default_rng(194))
    curve = []
    for mass in [0., .5, 1., 2., 3.]:
        truth = predict(test, TRUE_OFFSETS, mass, TRUE_COMPLIANCE)
        geometric = metrics(fk(test, unloaded_fit), truth)
        mixed = metrics(fk(test, mixed_rigid), truth)
        elastic = metrics(predict(test, elastic_fit[:7], mass, estimated_c), truth)
        curve.append({'payload': mass, 'geometry_mm': geometric['position_mm'],
                      'mixed_geometry_mm': mixed['position_mm'],
                      'elastic_mm': elastic['position_mm'],
                      'geometry_deg': geometric['orientation_deg'],
                      'elastic_deg': elastic['orientation_deg'],
                      'unseen_payload': mass not in [0., 1., 3.]})
    mass = 2.
    truth = predict(test, TRUE_OFFSETS, mass, TRUE_COMPLIANCE)
    scatter = {'torque_nm': np.abs(payload_torque(test, TRUE_OFFSETS, mass)[:, 3]),
               'geometry_mm': metrics(fk(test, unloaded_fit), truth)['per_pose_mm'],
               'elastic_mm': metrics(predict(test, elastic_fit[:7], mass, estimated_c), truth)['per_pose_mm']}
    frames = []
    for mass in np.linspace(0, 3, 61):
        frames.append({'payload': mass,
                       'truth': loaded_scene(HOME, TRUE_OFFSETS, mass, TRUE_COMPLIANCE),
                       'estimate': scene(HOME, unloaded_fit),
                       'elastic': loaded_scene(HOME, elastic_fit[:7], mass, estimated_c),
                       'torque_nm': float(payload_torque(HOME, TRUE_OFFSETS, mass)[3])})
    return native({'title': 'Geometry error or arm flex?', 'curve': curve, 'frames': frames,
                   'scatter': scatter, 'true_compliance': TRUE_COMPLIANCE,
                   'estimated_compliance': estimated_c, 'estimated_offsets_deg': np.rad2deg(elastic_fit[:7]),
                   'note': 'Synthetic small-deflection model: Δq₄ = c · τ₄, with payload gravity torque evaluated at the unloaded pose. No link mass, hysteresis, dynamics, or implicit elastic equilibrium. Training: 32 configurations at 0, 1, 3 kg; evaluation: 160 new configurations. The mixed rigid and elastic fits share all 96 observations; the unloaded rigid fit uses 32.'})
