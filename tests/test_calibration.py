import copy
import numpy as np
import pytest
from calibration.dataset import simulate,parse
from calibration.geometry import camera_points,base_points,project,landmarks,forward
from calibration.solver import calibrate


def test_camera_roundtrip_and_projection_convention():
    raw,_=simulate(count=24)
    data=parse(raw)
    points=np.broadcast_to([.1,-.1,1.],(24,2,8,3)).copy()
    np.testing.assert_allclose(camera_points(base_points(points,data.transforms),data.transforms),points,atol=1e-14)
    uv,visible=project(points)
    np.testing.assert_allclose(uv[0,0,0],[527,253])
    assert visible.all()


def test_position_only_recovery_with_known_head_motion():
    raw,truth=simulate(noise_mm=0,missing=0,outliers=0)
    result=calibrate(raw,'synthetic',truth)
    np.testing.assert_allclose(result['iterations'][-1]['parameters'],truth['parameters'],atol=1e-6)
    assert result['final']['truth_rms_mm']<1e-6
    assert result['rank']==18
    assert 'orientation' not in str(raw.keys())


def test_validation_observations_do_not_change_fitted_parameters():
    raw,_=simulate(count=24)
    first=calibrate(raw)
    changed=copy.deepcopy(raw)
    for frame in changed['frames']:
        if frame['split']=='validation':
            for point in frame['landmarks']:point['position_camera_m'][0]+=.1
    second=calibrate(changed)
    np.testing.assert_array_equal(first['iterations'][-1]['parameters'],second['iterations'][-1]['parameters'])
    assert second['final']['validation_rms_mm']>first['final']['validation_rms_mm']+50


def test_robust_fit_handles_noise_missing_points_and_outliers():
    raw,truth=simulate()
    robust=calibrate(raw,'synthetic',truth)
    linear=calibrate(raw,'synthetic',truth,robust=False)
    assert robust['final']['truth_rms_mm']<1
    assert robust['final']['truth_rms_mm']<linear['final']['truth_rms_mm']
    assert robust['final']['validation_rms_mm']<robust['initial']['validation_rms_mm']/2
    # Noisy observation agreement is not synthetic physical accuracy.
    assert robust['final']['validation_rms_mm']>robust['final']['truth_rms_mm']*5


def test_imported_data_never_claims_synthetic_ground_truth():
    raw,_=simulate(count=24)
    result=calibrate(raw)
    assert result['simulation_parameters'] is None
    assert 'truth_rms_mm' not in result['final']
    assert not result['projection_is_illustrative']
    del raw['intrinsics']
    assert calibrate(raw)['projection_is_illustrative']


def test_upstream_landmarks_do_not_move_with_terminal_joint():
    q=np.zeros((1,2,7));parameters=np.zeros((2,9))
    before=landmarks(q,parameters)
    q[:,:,6]=.5
    after=landmarks(q,parameters)
    np.testing.assert_allclose(before[:,:,:4],after[:,:,:4])
    assert np.max(np.abs(before[:,:,4:]-after[:,:,4:]))>.01
    for side in range(2):
        r=forward(q[:,side],parameters[side],side)[2]
        np.testing.assert_allclose(np.linalg.det(r),1,atol=1e-14)


@pytest.mark.parametrize('kind',['sigma','duplicate','transform','split','intrinsics','arm'])
def test_invalid_input_rejected(kind):
    raw,_=simulate(count=24)
    if kind=='sigma':raw['frames'][0]['landmarks'][0]['sigma_m'][0]=0
    if kind=='duplicate':raw['frames'][0]['landmarks'].append(raw['frames'][0]['landmarks'][0])
    if kind=='transform':raw['frames'][0]['T_base_camera'][3][3]=2
    if kind=='split':raw['frames'][0]['split']='maybe'
    if kind=='intrinsics':raw['intrinsics']['fx']=-1
    if kind=='arm':raw['frames'][0]['landmarks'][0]['arm']='unknown'
    with pytest.raises(ValueError):parse(raw)


def test_repeated_palm_only_observations_report_rank_deficiency():
    raw,_=simulate(noise_mm=0,missing=0,outliers=0)
    template=next(f for f in raw['frames'] if sum(p['name']=='palm' for p in f['landmarks'])==2)
    for i in range(len(raw['frames'])):
        frame=copy.deepcopy(template)
        frame['split']='validation' if i%4==0 else 'train'
        frame['landmarks']=[p for p in frame['landmarks'] if p['name']=='palm']
        raw['frames'][i]=frame
    result=calibrate(raw)
    assert result['rank']<=6
    assert result['condition'] is None
