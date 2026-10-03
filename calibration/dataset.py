"""Explicit observation contract and a reproducible synthetic perception source."""
from dataclasses import dataclass
import numpy as np
from .geometry import LABELS, INTRINSICS, landmarks, camera_points, project, rotation, native


@dataclass
class Dataset:
    q: np.ndarray
    transforms: np.ndarray
    points: np.ndarray
    sigma: np.ndarray
    visible: np.ndarray
    validation: np.ndarray


def parse(raw):
    if not isinstance(raw,dict) or raw.get('schema_version')!=1:
        raise ValueError('Expected a dataset object with schema_version: 1')
    if 'intrinsics' in raw:
        k=raw['intrinsics']
        try:
            if any(type(k[key]) not in (int,float) or not np.isfinite(k[key]) for key in INTRINSICS):
                raise ValueError('Non-finite camera intrinsics')
            if any(k[key]<=0 for key in ('width','height','fx','fy')):
                raise ValueError('Image dimensions and focal lengths must be positive')
        except (TypeError,KeyError) as error:
            raise ValueError('intrinsics needs width, height, fx, fy, cx, cy') from error
    frames = raw.get('frames')
    if not isinstance(frames,list) or not 12<=len(frames)<=256:
        raise ValueError('Provide 12–256 synchronized frames')
    n = len(frames)
    q = np.empty((n,2,7)); transforms = np.empty((n,4,4))
    points = np.zeros((n,2,8,3)); sigma = np.ones_like(points)
    visible = np.zeros((n,2,8),dtype=bool); validation = np.zeros(n,dtype=bool)
    for i,frame in enumerate(frames):
        try:
            angles = np.array(frame['q_rad'],dtype=float)
            transform = np.array(frame['T_base_camera'],dtype=float)
            if angles.shape!=(2,7) or not np.isfinite(angles).all():
                raise ValueError('q_rad must be finite [2,7] encoder readings')
            if transform.shape!=(4,4) or not np.isfinite(transform).all():
                raise ValueError('T_base_camera must be a finite 4×4 transform')
            r = transform[:3,:3]
            if not np.allclose(r.T@r,np.eye(3),atol=1e-6) or not np.isclose(np.linalg.det(r),1,atol=1e-6) or not np.allclose(transform[3],[0,0,0,1]):
                raise ValueError('T_base_camera must be a rigid camera-to-torso transform')
            q[i],transforms[i] = angles,transform
            if frame['split'] not in ('train','validation'):
                raise ValueError('Every frame needs split: train or validation')
            validation[i] = frame['split']=='validation'
            for obs in frame['landmarks']:
                side = ['left','right'].index(obs['arm']); k = LABELS.index(obs['name'])
                p = np.array(obs['position_camera_m'],dtype=float)
                s = np.array(obs['sigma_m'],dtype=float)
                if visible[i,side,k]: raise ValueError('Duplicate arm/landmark observation')
                if p.shape!=(3,) or s.shape!=(3,) or not np.isfinite(p).all() or not np.isfinite(s).all() or np.any(s<=0) or p[2]<=0:
                    raise ValueError('Landmarks need finite 3D positions, positive depth, and positive per-axis sigma')
                points[i,side,k],sigma[i,side,k],visible[i,side,k] = p,s,True
        except (KeyError,TypeError,IndexError,ValueError) as error:
            raise ValueError(f'Frame {i}: {error}') from error
    if validation.sum()<3 or (~validation).sum()<8:
        raise ValueError('Need at least eight training and three validation frames')
    if np.any(visible[~validation].sum(axis=(0,2))<18) or np.any(visible[validation].sum(axis=(0,2))<6):
        raise ValueError('Both arms need enough training and validation observations')
    return Dataset(q,transforms,points,sigma,visible,validation)


def simulate(count=48, noise_mm=2., missing=.15, outliers=.04, seed=52):
    if type(count) is not int or not 24<=count<=96: raise ValueError('Demo frame count must be 24–96')
    for value,maximum in [(noise_mm,8),(missing,.4),(outliers,.15)]:
        if type(value) not in (int,float) or not np.isfinite(value) or not 0<=value<=maximum:
            raise ValueError('Invalid noise, missing-detection, or outlier setting')
    rng = np.random.default_rng(seed)
    center = np.array([-.25,-.15,.15,.85,0,-.3,0])
    extent = np.array([.42,.42,.8,.55,.8,.6,.9])
    q = center+rng.uniform(-1,1,(count,2,7))*extent
    truth_parameters = np.array([[2.1,-1.8,1.4,2.5,-.9,1.6,-2,3,-4],[-1.7,1.3,-2.2,1.8,1.1,-1.4,2.3,-2.5,3.5]])
    transforms = np.broadcast_to(np.eye(4),(count,4,4)).copy()
    forward = np.array([np.cos(.65),0,-np.sin(.65)])
    right = np.array([0.,-1.,0.]); down = np.cross(forward,right)
    transforms[:,:3,:3] = np.column_stack([right,down,forward])
    # Known gentle head yaw. The calibration does not estimate camera extrinsics.
    transforms[:,:3,:3] = rotation(np.array([0,0,1]),np.linspace(-.10,.10,count)) @ transforms[:,:3,:3]
    transforms[:,:3,3] = [.04,0,1.43]
    truth = landmarks(q,truth_parameters)
    camera = camera_points(truth,transforms)
    _,fov = project(camera)
    confidence = rng.uniform(.6,1,(count,2,8))
    sigma = max(noise_mm,.05)/1000*np.array([1.,1.,2.])/np.sqrt(confidence[...,None])
    points = camera+rng.normal(size=camera.shape)*sigma*(noise_mm>0)
    visible = fov&(rng.uniform(size=fov.shape)>=missing)
    corrupt = visible&(rng.uniform(size=fov.shape)<outliers)
    points[corrupt] += rng.normal(0,.025,(int(corrupt.sum()),3))
    frames=[]
    for i in range(count):
        observations=[]
        for side,k in zip(*np.where(visible[i])):
            observations.append({'arm':['left','right'][side],'name':LABELS[k],
                                 'position_camera_m':points[i,side,k], 'sigma_m':sigma[i,side,k]})
        frames.append({'q_rad':q[i],'T_base_camera':transforms[i],
                       'split':'validation' if i%4==0 else 'train','landmarks':observations})
    raw = native({'schema_version':1,'intrinsics':INTRINSICS,'frames':frames})
    return raw,{'parameters':truth_parameters,'positions':truth,
                'settings':{'count':count,'noise_mm':noise_mm,'missing':missing,'outliers':outliers,'seed':seed}}
