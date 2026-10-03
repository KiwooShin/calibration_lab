"""Fit camera-frame 3D positions, then evaluate independent validation frames."""
import numpy as np
from scipy.optimize import least_squares
from .dataset import parse
from .geometry import landmarks,camera_points,exported_model,forward,base_points,native,LABELS,INTRINSICS


def calibrate(raw, source='imported', simulation=None, robust=True):
    data = parse(raw)
    training = data.visible & (~data.validation)[:,None,None]
    validation = data.visible & data.validation[:,None,None]

    def predicted(x): return camera_points(landmarks(data.q,x),data.transforms)
    def residual(x): return ((predicted(x)-data.points)/data.sigma)[training].ravel()

    history=[np.zeros(18)]
    bounds=np.tile([12.]*7+[15.,15.],2)
    result=least_squares(residual,history[0],bounds=(-bounds,bounds),loss='soft_l1' if robust else 'linear',
                         f_scale=2.,x_scale='jac',max_nfev=180,ftol=1e-10,xtol=1e-10,gtol=1e-9,
                         callback=lambda x:history.append(x.copy()))
    if not result.success: raise ValueError(f'Calibration did not converge: {result.message}')
    if not np.array_equal(history[-1],result.x):history.append(result.x.copy())
    step=1e-4
    sensitivity=np.stack([(residual(result.x+np.eye(18)[j]*step)-residual(result.x-np.eye(18)[j]*step))/(2*step) for j in range(18)],axis=1)
    s=np.linalg.svd(sensitivity,compute_uv=False)
    rank=int(np.sum(s>s[0]*1e-7))

    def metrics(x):
        error=np.linalg.norm(predicted(x)-data.points,axis=-1)*1000
        val=error[validation]
        metrics={'train_rms_mm':float(np.sqrt(np.mean(error[training]**2))),
                 'validation_rms_mm':float(np.sqrt(np.mean(val**2))),
                 'validation_median_mm':float(np.median(val)),
                 'per_landmark_mm':[float(np.sqrt(np.mean(error[:,:,j][validation[:,:,j]]**2))) if validation[:,:,j].any() else None for j in range(8)]}
        if simulation is not None:
            physical=landmarks(data.q,x)-simulation['positions']
            metrics['truth_rms_mm']=float(np.sqrt(np.mean(np.sum(physical[data.validation]**2,axis=-1)))*1000)
        return metrics

    models=[x.reshape(2,9) for x in history]
    samples=[]
    world_observed=base_points(data.points,data.transforms)
    for i,q in enumerate(data.q):
        snapshots=[]
        for x in models:
            arms=[]
            for side in range(2):
                points,nodes,r=forward(q[side],x[side],side)
                arms.append({'nodes':nodes,'points':points,'rotation':r})
            snapshots.append(arms)
        samples.append({'T_base_camera':data.transforms[i],'observed_camera':data.points[i],
                        'observed_world':world_observed[i],'visible':data.visible[i],
                        'sigma_mm':data.sigma[i]*1000,'split':'validation' if data.validation[i] else 'train',
                        'snapshots':snapshots})
    return native({'source':source,'settings':simulation['settings'] if simulation else None,
                   'landmark_names':LABELS,'intrinsics':raw.get('intrinsics',INTRINSICS),
                   'projection_is_illustrative':'intrinsics' not in raw,'model':exported_model(result.x),
                   'initial':metrics(history[0]),'final':metrics(result.x),
                   'iterations':[{'parameters':x.reshape(2,9),'metrics':metrics(x)} for x in history],
                   'samples':samples,'train_frames':int((~data.validation).sum()),'validation_frames':int(data.validation.sum()),
                   'training_points':int(training.sum()),'validation_points':int(validation.sum()),
                   'rank':rank,'singular_values':s,'condition':float(s[0]/s[-1]) if rank==18 else None,
                   'at_bound':bool(np.any(np.abs(result.x)>bounds-.001)),
                   'simulation_parameters':simulation['parameters'] if simulation else None})
