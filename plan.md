# Head-camera self-calibration — fresh start

## Objective

Use a head-mounted camera's labeled 3D arm and hand position predictions to calibrate forward kinematics. The perception model and camera calibration are assumed available. This repository implements the calibration stage and a synthetic demonstration of that interface.

## One focused workflow

1. **Observe:** collect synchronized encoders, known camera-to-torso transforms, and labeled camera-frame 3D landmarks with uncertainties.
2. **Compare:** predict those same landmarks using the nominal arm models and express them in the camera frame.
3. **Calibrate:** robustly fit joint offsets and selected link lengths across many observations.
4. **Validate:** evaluate on frames excluded from the fit; distinguish agreement with noisy perception from absolute accuracy known only in simulation.

## Scope

- Two generic seven-joint arms; replace geometry and landmark attachments for hardware use.
- Fourteen encoder offsets and four link-length corrections.
- Position-only fitting; no measured hand orientation.
- Known per-frame head-camera transform, including head motion.
- Uncertainty weighting, missing observations, outliers, and identifiability reporting.
- A single dashboard with an orbitable robot, head-camera landmark view, calibration progress, and held-out results.
- JSON import/export and CLI calibration for real perception predictions.
- No old ghost-arm, redundancy, experimental-design, observability, or compliance mini-projects.
- No claim to implement or train an image perception model.

## Delivery

- [x] Remove the previous project contents while preserving the GitHub repository and history.
- [x] Build the kinematics, camera-frame observation contract, and robust calibration solver.
- [x] Add a reproducible simulator and held-out validation.
- [x] Build the single-purpose visualization and real-dataset import.
- [x] Test numerical behavior, input handling, browser controls, and mobile rendering.
- [x] Document the model assumptions and Mac launch workflow.
- [x] Restart the local app and deliver the replacement to the GitHub repository.

## Verified implementation

- The four-stage interface shows only perceived landmarks in Observe, adds nominal FK and residuals in Compare, replays accepted solver updates in Calibrate, and restricts the observation control to excluded frames in Validate.
- A selected-landmark inspector shows camera-frame XYZ error and a magnified XY residual with a fixed scale across iterations for that observation.
- Two independent controls change the observation and the model iteration. Recorded observations never move during optimizer playback.
- The default 48-frame demo fits 36 frames and validates on 12. Observation RMS decreases from 30.464 to 9.481 mm; separate synthetic geometry RMS decreases from 29.356 to 0.563 mm. The remaining observation residual includes noise and outliers.
- Real datasets can be imported in the browser or passed to the CLI. Their display excludes synthetic-truth accuracy claims.
- All 13 numerical tests pass, including validation independence and rank-deficient inputs. Browser checks pass for the four stages, both solver endpoints, imports, exports, WebGL, and mobile overflow.
- The new server is running at `http://127.0.0.1:8765`. Generated datasets and test screenshots live in ignored `artifacts/`; only one curated preview is tracked in `docs/`.
