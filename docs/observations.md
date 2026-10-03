# Observation dataset contract

The fitter consumes labeled **3D positions in the camera's optical frame**, measured independently of the kinematic model being calibrated. It does not require measured hand orientation or synthetic ground truth.

## Top-level object

```json
{
  "schema_version": 1,
  "intrinsics": {"width": 960, "height": 600, "fx": 470, "fy": 470, "cx": 480, "cy": 300},
  "frames": []
}
```

Supply 12–256 frames, including at least eight training frames and three validation frames. Both arms need at least 18 training landmark observations and six validation landmark observations. Intrinsics are optional and used only for the image-plane visualization: the fit uses 3D points directly. Without intrinsics, the interface explicitly labels the projection as illustrative.

## Each synchronized frame

The following is a frame-format excerpt, not a complete dataset:

```json
{
  "q_rad": [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
  "T_base_camera": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
  "split": "train",
  "landmarks": [
    {
      "arm": "left",
      "name": "wrist",
      "position_camera_m": [0.12, 0.08, 0.65],
      "sigma_m": [0.002, 0.002, 0.004]
    }
  ]
}
```

- `q_rad`: `[left, right]` seven-joint encoder vectors, in radians.
- `T_base_camera`: known rigid 4×4 transform mapping camera column vectors into torso/base coordinates. The solver applies its inverse to FK-predicted landmarks. Supply the actual transform for each exposure, including head motion.
- `split`: `train` or `validation`. Validation observations never enter the fitting objective. For real datasets, choose independent configurations or acquisition sequences rather than splitting nearly identical adjacent frames.
- `landmarks`: visible, usable observations only. Omit missing predictions entirely. Each arm/name pair must be unique within a frame.
- `position_camera_m`: metric optical coordinates, X right, Y down, Z forward. Values must be finite, with positive depth.
- `sigma_m`: three finite, positive per-axis standard deviations, in meters. The fitter uses a diagonal uncertainty model. A network confidence score is not itself a metric standard deviation; calibrate that mapping before using it for weighting.

Encoder readings, head transforms, and camera predictions must refer to the same time. Interpolate or synchronize logs before assembling this input. Time delay is not estimated by this solver.

## Landmark identities and attachments

Both perception and FK must identify the same physical points. The current generic model defines:

| Name | Attachment |
| --- | --- |
| `upper_arm` | Halfway along link 3, with local +35 mm lateral and +20 mm vertical offsets |
| `elbow` | Joint 4 origin, after the upper-arm link |
| `forearm` | Halfway along link 4, with local −30 mm lateral and +20 mm vertical offsets |
| `wrist` | Joint 5 origin, after the forearm link |
| `palm` | Terminal palm-frame origin |
| `knuckle_inner` | Palm-frame reference `[0.035, 0.04, 0]` m |
| `knuckle_outer` | Palm-frame reference `[0.035, −0.04, 0]` m |
| `hand_tip` | Rigid palm-frame reference `[0.09, 0, 0]` m |

The right arm mirrors the generic chain. These are explicit model attachments, not promises about the keypoints predicted by an arbitrary perception network. Replace `calibration.geometry.forward` and its attachments for your robot. If your perception output contains only elbow, wrist, and palm centers, supply only those points and inspect identifiability; do not fabricate additional detections.

An articulated fingertip requires the corresponding finger kinematics and encoder readings. A silhouette point whose physical location varies with viewpoint cannot be treated as a fixed link attachment.

## Objective

```text
predicted_camera_point = inverse(T_base_camera) × FK_landmark(q, parameters)
residual = (predicted_camera_point − perceived_camera_point) / sigma
```

The solver minimizes a soft-L1 loss over all residual components from **training** frames. One model serves every frame. Fourteen joint offsets and four upper/forearm length corrections are estimated; extrinsics and landmark attachments are fixed.

Validation reports unweighted position RMS and median against the held-out perceived points. Noisy or biased perception is not an independent absolute geometric reference. The synthetic demo additionally computes geometric error against its known truth; imported datasets do not receive that metric.

## Output

The exported model has `left` and `right` entries, each with:

- `joint_offsets_rad`: seven additive encoder offsets.
- `upper_arm_delta_m`: additive correction to nominal upper-arm length.
- `forearm_delta_m`: additive correction to nominal forearm length.

The export includes parameter rank and a bound-hit indicator. Internal optimizer scaling uses degrees and millimeters, whereas the exported parameters use radians and meters. Rank is local, evaluated from the whitened calibration Jacobian at the fitted model, with a relative singular-value threshold of `1e-7`. The condition number depends on this parameter scaling.

## Create a complete example

```bash
python -m calibration --example artifacts/observations.json
python -m calibration --input artifacts/observations.json --output artifacts/fit.json
```

The first command writes a synthetic dataset matching this contract. The second uses the real-input pathway, without supplying the solver with synthetic truth.
