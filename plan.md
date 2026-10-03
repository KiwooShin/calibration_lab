# Seven-DOF Arm Calibration Lab

Build five small, interactive robotics projects in order, based on the hiring-manager question: given reliable externally measured hand poses, how do we calibrate a seven-joint arm and choose useful calibration motions?

## Shared scope

- Work in the standalone `/home/kiwoos/work/calibration_lab/` project directory.
- Use a generic seven-revolute-joint arm, not a claimed model of 1X NEO.
- Synthetic observations come from a separate, perturbed physical model; camera intrinsics and extrinsics are assumed known.
- Keep a known base frame and palm transform for the first three projects. Record measured joint angles as inputs.
- Use Python, NumPy and SciPy for numerical experiments; a local browser dashboard for interactive 3D views and charts.
- Show position error in millimeters and orientation error in degrees separately. Use held-out configurations for evaluation.
- Use fixed seeds, save numerical results, and provide reproducible commands and meaningful numerical checks.
- These are educational kinematic experiments, not hardware-ready motion controllers. Collision avoidance and actuator dynamics are outside the initial scope.

## 1. Fix the ghost arm

**Question:** Can external hand observations recover joint encoder zero offsets?

**Build:** Perturb seven encoder offsets, collect joint-angle/hand-pose pairs, fit offsets with nonlinear least squares, and evaluate on held-out poses.

**Visuals:** Overlaid physical and predicted arms; position discrepancy vector; actual optimizer-iteration playback; true versus recovered offsets; workspace error map; separate position/orientation metrics.

**Controls/experiment:** Sample count, noise, and clustered versus diverse training configurations.

**Acceptance:** Recover injected offsets from diverse noise-free full poses; lower held-out error; expose a poorly excited dataset rather than hiding it.

## 2. Move the elbow, hold the hand

**Question:** How can a redundant arm expose calibration errors?

**Build:** Trace a nominal fixed-hand self-motion using the geometric Jacobian and pose correction; compare nominal, perturbed, and calibrated predictions. Compare calibration from fixed-hand sweeps, workspace samples, and mixed samples at an equal pose budget.

**Visuals:** Elbow sweep animation, magnified true-hand drift trace with explicit scale, before/after calibration, dataset comparison.

**Acceptance:** Nominal full-pose drift stays small while joints move; injected model error produces measured hand drift; report observability and held-out errors without claiming one sweep identifies every parameter.

## 3. Choose the next calibration pose

**Question:** Can informative pose selection reduce the measurement budget?

**Build:** Score candidate configurations using the scaled, noise-whitened parameter-sensitivity matrix and regularized information gain. Compare greedy selection with seeded random selection on the same candidate observations and held-out set.

**Visuals:** Candidate cloud colored by information gain, selected-pose animation, held-out error versus observation count, random-trial variation.

**Acceptance:** Equal budgets and noise assumptions; actual fitted errors at every budget; no hard-coded promise that greedy selection always wins.

## 4. What can the camera actually identify?

**Question:** Which parameters are distinguishable from the available measurements?

**Build:** Compare point-only versus full-pose measurements and narrow versus broad excitation. Include terminal-frame orientation parameters as an explicit point-only ambiguity. Compute singular values of the scaled calibration Jacobian.

**Visuals:** Singular-value spectrum, rank/conditioning, animation along a weak parameter direction, predicted hand changes and parameter changes.

**Acceptance:** Point-only observations cannot identify terminal-frame orientation at the measured frame origin; full-pose observations add information but may still leave redundant parameter combinations. Explain local rank and parameterization limitations.

## 5. Geometry error or arm flex?

**Question:** Why might unloaded calibration fail with a payload?

**Build:** Add a simple joint-compliance model driven by payload gravity torque. Compare offsets fitted at zero payload with a compact offsets-plus-compliance model fitted using multiple payloads and validated on unseen configurations and an unseen payload.

**Visuals:** Loaded-arm deflection with labeled exaggeration, error versus payload, residual versus torque, geometric-only versus compliance-aware predictions.

**Acceptance:** Zero-payload geometry fit does not explain load-dependent error; joint fitting improves held-out loaded poses; identify the model as synthetic and quasi-static.

## Delivery sequence and status

- [x] Save the options and scope in this plan.
- [x] Shared numerical model and dashboard foundation.
- [x] Project 1 implemented and validated.
- [x] Project 2 implemented and validated.
- [x] Project 3 implemented and validated.
- [x] Project 4 implemented and validated.
- [x] Project 5 implemented and validated.
- [x] Browser smoke checks, reproducible results, screenshots, and usage documentation.

## Completion record — October 2, 2026

Implemented projects 1–5 sequentially in `calibration_lab/`, with a shared NumPy/SciPy model and a local Three.js dashboard. Each module is an independent reproducible experiment. The first module also supports live recalibration from browser controls.

- **Project 1:** Held-out position RMS 27.992 → 0.153 mm for the default noisy dataset. Noise-free offsets recovered numerically.
- **Project 2:** Nominal full-pose invariance verified. Maximum actual hand drift 33.017 → 0.193 mm after replanning with fitted offsets. Three equal-budget calibration datasets compared.
- **Project 3:** Shared-pool, equal-budget greedy/random comparison with ten random selections. At 32 observations, greedy error is 0.201 mm versus random median 0.407 mm. No universal superiority claim.
- **Project 4:** Point-only rank 7/10; full-pose rank 10/10. Full-pose conditioning worsens from 17.1 to 9900.8 under narrow excitation. Actual nonlinear weak-direction playback included.
- **Project 5:** On an unseen 2 kg payload and unseen configurations, unloaded rigid error is 4.158 mm, mixed-load rigid error 3.965 mm, and compliance-aware error 0.096 mm.
- **Validation:** Eight numerical tests pass. Browser checks pass for all modules, live fitting, exports, WebGL, mobile layout, and request validation. Headed Chromium under Xvfb was used because this machine's headless Chromium cannot initialize WebGL.
- **Artifacts:** `results/data.json`, standalone `overview.png` and `overview.pdf`, plus six browser screenshots. The dashboard and its renderer are locally bundled and require no external frontend services.

See [run instructions and limitations](README.md). These results are synthetic, not measurements of NEO.

## References

- [Modern Robotics: Jacobians and redundancy](https://modernrobotics.northwestern.edu/nu-gm-book-resource/5-3-singularities/)
- [Stepanova et al.: self-contained robot calibration](https://arxiv.org/abs/2012.07548)
