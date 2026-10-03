# Head-camera perception → forward-kinematics calibration

The primary input is **labeled 3D positions in the head-camera frame**. No hand orientation estimates, ground-truth parameters, or synthetic truth are needed by `fit_landmarks`.

## Coordinate and timing contract

- Units: positions and translations in meters; encoder angles in radians.
- Arms are ordered `[left, right]`; each arm has seven encoder readings.
- Camera coordinates are optical: X right, Y down, Z forward.
- `T_base_camera[i]` is a 4×4 homogeneous transform that maps a point **from camera coordinates into the torso/base frame** at frame `i`.
- The solver uses its inverse to compare FK-predicted landmark positions against perception in camera coordinates.
- Camera predictions, encoder readings, and the head transform must refer to the same exposure time. Interpolate encoder/head logs before creating the dataset. The current solver consumes aligned samples; it does not estimate time delay.
- A fixed head is represented by the same transform in every frame. A moving head can supply a different known transform for each frame; this is covered by a numerical test.

## JSON arrays

For `N` synchronized observations:

| Key | Shape | Meaning |
| --- | --- | --- |
| `q_rad` | `[N, 2, 7]` | Measured left/right joint encoder angles |
| `positions_camera_m` | `[N, 2, 8, 3]` | Predicted landmark positions in the optical camera frame |
| `visible` | `[N, 2, 8]` | Boolean mask of usable predictions |
| `sigma_camera_m` | `[N, 2, 8, 3]` | Positive per-axis standard deviations, in meters |
| `T_base_camera` | `[N, 4, 4]` | Known camera-to-torso transform per observation |
| `landmark_names` | `[8]` | Exact ordered labels below |
| `confidence` | `[N, 2, 8]` | Optional metadata; the fit uses `sigma_camera_m`, not this raw score |

For missing landmarks, set `visible=false` and use a zero position and positive placeholder sigma. Invisible entries are excluded. A perception confidence score needs a calibrated mapping to position uncertainty; it should not be treated as a metric covariance without validation. The demo increases uncertainty for low-confidence points and uses twice as much depth noise as lateral noise.

## Landmark correspondence

```json
["upper_arm", "elbow", "forearm", "wrist", "palm", "palm_left", "palm_right", "hand_tip"]
```

The points must mean the same physical attachments in perception and FK. The current generic model uses:

| Landmark | Attachment in the model |
| --- | --- |
| `upper_arm` | Midpoint along link 3, with a local lateral offset of +35 mm and local Z offset of +20 mm |
| `elbow` | Joint 4 origin, at the end of the upper-arm link |
| `forearm` | Midpoint along link 4, with a local lateral offset of −30 mm and local Z offset of +20 mm |
| `wrist` | Joint 5 origin, at the end of the forearm link |
| `palm` | Terminal palm-frame origin |
| `palm_left` | Palm-frame point `[0.035, 0.04, 0]` meters |
| `palm_right` | Palm-frame point `[0.035, −0.04, 0]` meters |
| `hand_tip` | Rigid hand reference at palm-frame `[0.09, 0, 0]` meters |

All hand points are rigid in this demo. An articulated fingertip would require finger joint readings and an extended model. The right arm mirrors the generic chain, with a proper right-handed palm rotation. The attachment definitions are implemented in `self_observation.arm`.

**For actual robot data, replace the generic chain and these attachment definitions with the robot's known nominal geometry.** Match the landmark definitions used by the perception model. A predicted silhouette point that changes with viewpoint is not a fixed link landmark. If perception only produces elbow, wrist, and palm centers, mark the other entries invisible and check the resulting parameter rank rather than fabricating extra observations.

## Fit a dataset

Create and fit a reproducible synthetic example:

```bash
python self_observation.py --write-example results/perception_example.json
python self_observation.py \
  --input results/perception_example.json \
  --output results/landmark_fit.json
```

Replace the input path with your aligned perception predictions after adapting the robot model. Select a subset with `--group palm`, `--group hand`, or `--group all`.

The output contains two rows of nine parameters:

```text
[joint_1_offset_deg, ..., joint_7_offset_deg,
 upper_arm_length_correction_mm, forearm_length_correction_mm]
```

Corrections are added to encoder readings and nominal link lengths. The output also includes accepted optimizer history, raw whitened sensitivity singular values, local rank, a condition number where full rank, the number of used landmarks, and a flag if a parameter reaches a fitting bound. A deficient rank indicates that this parameter set is not distinguishable from the selected observations.

## Objective and validation

For a visible landmark `j` at frame `i`:

```text
p_pred_camera = inverse(T_base_camera[i]) · FK_landmark(q[i], theta, j)
residual = (p_pred_camera − perception_position_camera) / sigma_camera
```

We minimize a soft-L1 loss over the whitened residual components. The solver estimates 14 encoder offsets and four link-length corrections. It never receives the demo's ground-truth offsets or any measured orientation. Robust loss limits the influence of occasional large residuals; it cannot guarantee correction of systematic perception bias.

Use independent frames to validate a real calibration. Check residuals by arm, landmark, configuration, and confidence. The dashboard's absolute held-out error is available because its synthetic truth is known; that metric should not be reported as measured hardware accuracy without an independent reference.

The demo models field of view and random missing detections. It does not run image inference, render physically accurate self-occlusion, calibrate the camera/head chain, or enforce collision-free hardware motion. Its role is to implement and visualize the calibration stage behind the assumed perception model.
