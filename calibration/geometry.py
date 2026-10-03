"""Generic two-arm model; this is not a NEO model or hardware controller."""
import numpy as np

LABELS = ['upper_arm', 'elbow', 'forearm', 'wrist', 'palm', 'knuckle_inner', 'knuckle_outer', 'hand_tip']
AXES = np.eye(3)[[2, 1, 0, 1, 0, 1, 2]]
LINKS = np.array([[0, 0, .10], [.06, 0, 0], [.28, 0, 0], [.25, 0, 0],
                  [.065, 0, 0], [.055, 0, 0], [.07, 0, 0]])
INTRINSICS = {'width': 960, 'height': 600, 'fx': 470., 'fy': 470., 'cx': 480., 'cy': 300.}


def rotation(axis, angle):
    x, y, z = axis
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    c, s = np.cos(angle)[..., None, None], np.sin(angle)[..., None, None]
    return c*np.eye(3)+(1-c)*np.outer(axis, axis)+s*cross


def forward(q, parameters, side):
    """Parameters: 7 offsets in degrees + 2 length deltas in mm, per arm.

    Returns torso-frame landmark positions, joint nodes, and palm rotation.
    The right chain mirrors the geometry with a proper palm-frame rotation.
    """
    q = np.asarray(q)
    p = np.zeros(q.shape[:-1]+(3,))
    r = np.broadcast_to(np.eye(3), q.shape[:-1]+(3,3)).copy()
    lengths = LINKS.copy()
    lengths[2, 0] += parameters[7]/1000
    lengths[3, 0] += parameters[8]/1000
    nodes, features = [p.copy()], []
    for j in range(7):
        r = r @ rotation(AXES[j], q[..., j]+np.deg2rad(parameters[j]))
        if j in (2, 3):
            attachment = np.array([lengths[j,0]/2, .035 if j==2 else -.03, .02])
            features.append(p+np.einsum('...ij,j->...i', r, attachment))
        p += np.einsum('...ij,j->...i', r, lengths[j])
        nodes.append(p.copy())
    points = [features[0], nodes[3], features[1], nodes[4], p.copy()]
    points += [p+np.einsum('...ij,j->...i',r,v) for v in ([.035,.04,0],[.035,-.04,0],[.09,0,0])]
    mirror = np.diag([1., 1. if side==0 else -1., 1.])
    shoulder = np.array([0., .24 if side==0 else -.24, .96])
    return (np.stack(points, axis=-2) @ mirror + shoulder,
            np.stack(nodes, axis=-2) @ mirror + shoulder, mirror @ r @ mirror)


def landmarks(q, parameters):
    parameters = np.asarray(parameters).reshape(2,9)
    return np.stack([forward(q[:,s],parameters[s],s)[0] for s in range(2)],axis=1)


def camera_points(points, transforms):
    t = np.asarray(transforms)
    return np.einsum('n...j,njk->n...k',points-t[:,None,None,:3,3],t[:,:3,:3])


def base_points(points, transforms):
    t = np.asarray(transforms)
    return np.einsum('n...j,nkj->n...k',points,t[:,:3,:3])+t[:,None,None,:3,3]


def project(points, k=INTRINSICS):
    z = points[...,2]
    uv = points[...,:2]/np.maximum(z[...,None],1e-9)*[k['fx'],k['fy']]+[k['cx'],k['cy']]
    inside = (z>.10)&(uv[...,0]>=0)&(uv[...,0]<k['width'])&(uv[...,1]>=0)&(uv[...,1]<k['height'])
    return uv, inside


def exported_model(parameters):
    x = np.asarray(parameters).reshape(2,9)
    return {name: {'joint_offsets_rad':np.deg2rad(x[s,:7]).tolist(),
                   'upper_arm_delta_m':float(x[s,7]/1000),
                   'forearm_delta_m':float(x[s,8]/1000)} for s,name in enumerate(['left','right'])}


def native(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,(np.integer,np.floating)): return x.item()
    if isinstance(x,dict): return {k:native(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [native(v) for v in x]
    return x
