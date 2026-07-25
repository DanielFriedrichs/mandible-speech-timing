# ArtiSynth canonical corrected-simulation specification

**Specification ID:** `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`  
**Stage:** Phase A patch for a clean local rerun; no dynamic results are included.  
**Authority:** Author decision D8 and `ARTISYNTH_SIMULATION_STAGE_HANDOFF.md`.

## 1. Scientific scope and interpretation

The corrected primary manipulation is **mandibular mass-and-inertia scaling under fixed geometry and disabled gravity**. It is not weight scaling, full craniofacial growth, or a direct measurement of living-speaker mandibular mass or inertia. The model is a mechanistic simulation extension and must not be presented as causal evidence in humans.

A gravity-enabled model is outside this package. It may be added later only as a separately named sensitivity analysis with separate code, directories, manifests, and interpretation.

## 2. Immutable configuration

| Element | Canonical value |
|---|---|
| Java model class | `artisynth.models.dynjaw.MandibleScalingInverseDDK_CURRENT` |
| Geometry | Fixed; no mesh or attachment scaling |
| Mandibular mass | baseline mass multiplied by `s^3` |
| Rotational inertia | baseline inertia tensor multiplied by `s^5` |
| Center of mass | Preserved |
| Fixed-force mode | `mode=fixed_force`; force exponent `0`; effective multiplier `1`; no force-capacity setter invoked |
| Force-capacity mode | `mode=force_capacity_s2`; force exponent `2`; effective multiplier `s^2`; setter/readback must succeed for at least one muscle in every cell, including `s=1.00` |
| Gravity | Disabled; vector `(0,0,0)` in both modes |
| Collision behavior | Disabled and verified through the available API |
| TMJ behavior | Both left and right connectors found and set to `unilateral=false` |
| Inherited probes | Input and output probes removed and verified |
| Solver | Hybrid solves disabled |
| Target marker | Lower-incisor frame marker, discovered by recorded path/name search; exact resolved name emitted per run |
| Controller | ArtiSynth `TrackingController` with a point target at the lower incisor |
| Target weight | `100.0` |
| L2 regularization | `0.01` |
| Excitation damping | `0.1` |
| Frame damping | `2.0` |
| Rotary damping | `4.0` |
| Maximum integration step | `0.00025 s` |
| Run duration | `4.0 s` |
| Settling period | `0.5 s` |
| Headless play time | `4.8 s`, allowing output finalization after the 4.0-s metric endpoint |
| Open-gap offset | `0.0 mm` |
| Model geometry, muscle paths, attachments, lever arms, joint setup, target, controller architecture | Identical across scales and modes except the approved force-capacity manipulation |

The Java class rejects unknown arguments and any deviation from these canonical values.

## 3. Target trajectory

Let `A` be the requested **peak-to-peak** amplitude, `f` the frequency, `omega = 2*pi*f`, `t_s` the settling endpoint, and `tau=t-t_s`. Let `z_0` be the baseline lower-incisor target position and `g=0` the retained open-gap value.

For the active interval `t >= t_s`, the coded displacement relative to `z_0` is

```text
Delta z(t) = 0.5*A*(sin(omega*tau) - 1) - g.
```

Its range is `[-A-g, -g]`, so the peak-to-peak displacement is exactly `A`. Its ordinary derivative on the active interval is

```text
d(Delta z)/dt = 0.5*A*omega*cos(omega*tau).
```

Before settling, the target remains at baseline and its coded velocity is zero. The approved handoff explicitly retains the historical active-position phase/offset; this patch corrects the active velocity to the exact symbolic derivative, including the factor `0.5`. Formula identifiers emitted by every run are:

- position: `P2P_ONE_SIDED_SIN_ACTIVE_V1`
- velocity: `P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1`

## 4. Grid

The one canonical grid driver is used for both modes.

- scales: `0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20`;
- frequencies: `1.0` through `10.0 Hz` in `0.5-Hz` increments;
- target amplitudes: `1.0` and `1.5 mm` peak-to-peak;
- cells per mode: `9 * 19 * 2 = 342`;
- total cells: `684`.

The full frequency grid is run. Dynamic early stopping is prohibited because all cells are needed to detect local nonmonotonicity and to audit the strict-prefix rule.

## 5. Metrics

Metrics are sampled from `t >= 0.5 s` through `t <= 4.0 s`.

- `tracking_rmse_mm`: square root of the mean squared **three-dimensional Euclidean** distance between source and target lower-incisor points, in millimetres;
- `actual_source_amp_p2p_mm`: maximum minus minimum source `z` over the metric interval;
- `actual_target_amp_p2p_mm`: maximum minus minimum target `z` over the metric interval;
- `amplitude_gain`: source peak-to-peak amplitude divided by target peak-to-peak amplitude;
- `peak_excitation`: maximum absolute excitation across all recorded exciters and metric samples;
- `mean_summed_squared_excitation`: sample mean of the sum of squared excitations across all exciters.

The wrapper also recomputes and records the three feasibility flags. Malformed, nonfinite, incomplete, or configuration-inconsistent Java output is a technical failure, not an infeasible scientific cell.

## 6. Feasibility and strict-prefix `fmax`

A technically successful cell is feasible only when all inclusive criteria hold:

```text
tracking_rmse_mm <= 0.5
peak_excitation <= 0.95
0.7 <= amplitude_gain <= 1.3
```

For each `mode x scale x amplitude` series, frequencies are sorted ascending. A tested frequency is prefix-eligible only when that frequency and every lower tested frequency are feasible. `fmax` is the highest prefix-eligible frequency. The first failed frequency and all criteria failed at that frequency are recorded. Feasible cells after the first failure are retained and flagged as local nonmonotonicity; they do not reopen the prefix.

No two-consecutive-failure rule, gap recovery, smoothing, interpolation, highest-feasible-anywhere rule, or imposed monotonic trend is allowed.

## 7. Failure and resume policy

- Every expected grid cell has exactly one row in the mode long table, including technical failures and not-yet-attempted cells.
- `--fresh` refuses an existing mode or cell directory.
- `--resume` skips only a technically successful cell after verifying canonical configuration content/hash, source and compiled-model hashes, launcher/Java/Python/base-class hashes, command/environment/raw-output/log/result artifact hashes, and the raw Java row itself.
- A matching failed attempt is archived and rerun.
- Any configuration, code, runtime, or artifact mismatch causes resume refusal; no prior result is reused.
- The validator requires 342 unique, technically successful cells per mode before `fmax` or figures may be generated.

## 8. Required outputs

Each mode must produce a 342-row long table plus per-cell raw Java CSV, stdout, stderr, combined log, command, configuration, environment, result CSV/JSON, hashes, grid configuration, grid environment, invocation manifest, and run summary. Postprocessing must produce a PASS validation report, a 684-row independently recomputed feasibility table, a 36-row strict-prefix summary, separate quantitative figures, and programmatic Table S3 source.


## V2 installed-runtime collision implementation

The V2 implementation realizes the unchanged requirement “collisions disabled” through the documented `MechModel` collision-behavior API: clear pair-specific overrides and responses, set all default collision behaviors disabled, and verify the four primary default pairs (Rigid–Rigid, Rigid–Deformable, Deformable–Deformable, Deformable–Self) as disabled. This is an implementation/provenance correction, not a change to the scientific simulation design.
