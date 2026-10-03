import numpy as np
import pytest
from self_observation import (TRUE, T_BASE_CAMERA, arm, predict_landmarks, to_camera, to_base,
                              synthetic_dataset, fit_landmarks, sample_configurations, evaluate,
                              validate_dataset, project)


def test_camera_coordinates_round_trip_and_projection():
    point = np.array([[[[.1, -.1, 1.]]]])
    base = to_base(point)
    np.testing.assert_allclose(to_camera(base), point, atol=1e-14)
    t = T_BASE_CAMERA[None].copy()
    np.testing.assert_allclose(to_camera(base, t), point, atol=1e-14)
    uv, visible = project(point)
    np.testing.assert_allclose(uv.ravel(), [527., 253.])
    assert visible.all()


def test_perception_positions_recover_offsets_and_link_lengths_without_orientation():
    dataset, _ = synthetic_dataset(count=40, noise_mm=0, dropout=0, outliers=0)
    fitted = fit_landmarks(dataset)
    np.testing.assert_allclose(fitted['parameters'], TRUE, atol=1e-6)
    assert fitted['rank'] == 18
    assert 'orientation' not in dataset
    for side in range(2):
        r = arm(dataset['q_rad'][:, side], TRUE[side], side)[2]
        np.testing.assert_allclose(np.linalg.det(r), 1., atol=1e-12)


def test_fit_uses_per_frame_head_camera_transforms():
    from scipy.spatial.transform import Rotation
    dataset, truth = synthetic_dataset(noise_mm=0, dropout=0, outliers=0)
    n = len(dataset['q_rad'])
    t = dataset['T_base_camera'].copy()
    t[:, :3, :3] = t[:, :3, :3] @ Rotation.from_rotvec(np.column_stack([np.linspace(-.15,.15,n),np.zeros(n),np.zeros(n)])).as_matrix()
    t[:, 0, 3] += np.linspace(-.03, .03, n)
    dataset['T_base_camera'] = t
    dataset['positions_camera_m'] = to_camera(truth['truth'], t)
    np.testing.assert_allclose(to_base(dataset['positions_camera_m'], t), truth['truth'], atol=1e-12)
    np.testing.assert_allclose(fit_landmarks(dataset)['parameters'], TRUE, atol=1e-6)


def test_robust_fit_generalizes_with_dropout_and_outliers():
    dataset, _ = synthetic_dataset()
    robust = fit_landmarks(dataset)
    linear = fit_landmarks(dataset, robust=False)
    test = sample_configurations(160, np.random.default_rng(151))
    final = evaluate(test, robust['parameters'])['landmark_mm']
    assert final < 1.
    assert final < evaluate(test, linear['parameters'])['landmark_mm']
    assert final < evaluate(test, np.zeros((2, 9)))['landmark_mm'] / 10


def test_missing_predictions_are_ignored_and_invalid_visible_data_rejected():
    dataset, _ = synthetic_dataset(outliers=0)
    missing = ~dataset['visible']
    dataset['positions_camera_m'][missing] = np.nan
    fitted = fit_landmarks(dataset)
    assert np.isfinite(fitted['parameters']).all()
    # Input validation must not overwrite original perception predictions.
    assert np.isnan(dataset['positions_camera_m'][missing]).all()
    dataset['sigma_camera_m'][dataset['visible']] = 0
    with pytest.raises(ValueError, match='positive finite'):
        validate_dataset(dataset)


def test_arm_landmarks_have_no_dependence_on_downstream_wrist_joints():
    q = np.zeros((1, 2, 7))
    before = predict_landmarks(q, np.zeros((2, 9)))
    q[:, :, 6] = .4
    after = predict_landmarks(q, np.zeros((2, 9)))
    np.testing.assert_allclose(before[:, :, :4], after[:, :, :4])
    assert np.max(np.abs(before[:, :, 4:] - after[:, :, 4:])) > .01
