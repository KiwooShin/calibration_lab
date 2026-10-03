import numpy as np
from scipy.spatial.transform import Rotation
from model import (fk, jacobian, TRUE_OFFSETS, HOME, configurations, observe, fit)


def test_fk_is_rigid_and_batch_matches_single():
    q = configurations(12, np.random.default_rng(2))
    p, r = fk(q)
    np.testing.assert_allclose(r @ r.swapaxes(-1, -2), np.broadcast_to(np.eye(3), r.shape), atol=1e-14)
    np.testing.assert_allclose(np.linalg.det(r), 1, atol=1e-14)
    for i in range(len(q)):
        ps, rs = fk(q[i])
        np.testing.assert_allclose(p[i], ps)
        np.testing.assert_allclose(r[i], rs)


def test_motion_jacobian_matches_independent_finite_difference():
    q = HOME.copy()
    _, r = fk(q)
    numerical = []
    eps = 1e-6
    for k in range(7):
        step = np.eye(7)[k] * eps
        p1, r1 = fk(q + step)
        p0, r0 = fk(q - step)
        numerical.append(np.r_[(p1-p0)/(2*eps), Rotation.from_matrix(r1 @ r0.T).as_rotvec()/(2*eps)])
    np.testing.assert_allclose(jacobian(q), np.array(numerical).T, atol=1e-8)


def test_offsets_recovered_from_noise_free_external_poses():
    rng = np.random.default_rng(9)
    q = configurations(25, rng)
    offsets, _ = fit(q, observe(q, rng))
    np.testing.assert_allclose(offsets, TRUE_OFFSETS, atol=1e-9)


def test_null_space_motion_preserves_full_nominal_pose():
    from experiments import self_motion, drift
    q = self_motion(steps=60)
    assert len(q) > 30
    assert np.linalg.norm(q[-1] - q[0]) > .5
    nominal = drift(q, np.zeros(7))
    assert nominal['max_position_mm'] < 1e-4
    assert nominal['max_orientation_deg'] < 1e-4
    assert drift(q, TRUE_OFFSETS)['max_position_mm'] > 1


def test_information_selection_unique_and_positive_information_gain():
    from experiments import information_selection
    q = configurations(40, np.random.default_rng(7))
    selected, scores, logdet = information_selection(q, 12)
    assert len(set(selected)) == 12
    assert np.all(np.diff(logdet) > 0)
    for i, selected_index in enumerate(selected):
        assert selected_index == np.argmax(scores[i])


def test_point_observations_cannot_recover_terminal_orientation():
    from model import parameter_jacobian
    q = configurations(32, np.random.default_rng(11))
    point = parameter_jacobian(q, point_only=True, include_tool=True).reshape(-1, 10)
    full = parameter_jacobian(q, include_tool=True).reshape(-1, 10)
    np.testing.assert_allclose(point[:, 7:], 0, atol=1e-10)
    assert np.linalg.matrix_rank(point, tol=1e-5) == 7
    assert np.linalg.matrix_rank(full, tol=1e-5) == 10
    p0, _ = fk(q)
    p1, _ = fk(q, tool_rotation=np.array([.2, -.3, .4]))
    np.testing.assert_allclose(p0, p1, atol=1e-15)


def test_gravity_torque_matches_negative_potential_energy_gradient():
    from model import payload_torque
    mass, eps = 2., 1e-6
    numerical = []
    for j in range(7):
        step = np.eye(7)[j] * eps
        z1 = fk(HOME + step, TRUE_OFFSETS)[0][2]
        z0 = fk(HOME - step, TRUE_OFFSETS)[0][2]
        numerical.append(-mass * 9.81 * (z1-z0)/(2*eps))
    np.testing.assert_allclose(payload_torque(HOME, TRUE_OFFSETS, mass), numerical, atol=1e-8)


def test_joint_offsets_and_compliance_recovered_from_multiple_payloads():
    from model import predict
    rng = np.random.default_rng(13)
    q = configurations(40, rng)
    masses = np.tile([0., 1., 3., 2.], 10)
    truth = predict(q, TRUE_OFFSETS, masses, .0025)
    params, _ = fit(q, truth, masses, fit_compliance=True)
    np.testing.assert_allclose(params[:7], TRUE_OFFSETS, atol=1e-8)
    np.testing.assert_allclose(params[7] * .001, .0025, atol=1e-9)
