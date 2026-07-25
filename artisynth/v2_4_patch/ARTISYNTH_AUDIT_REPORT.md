# Phase A audit of the archived ArtiSynth simulation

**Verdict:** `ARTISYNTH PATCH READY FOR LOCAL RERUN`  
**Audit scope:** code, old command provenance, output construction, feasibility, endpoint logic, figures/tables, and local environment.  
**Execution scope:** static audit and patch testing only. No ArtiSynth dynamic simulation was run in ChatGPT.

## 1. Evidence inspected

The audit inspected the safely extracted contents of:

- `PREFLIGHT_EVIDENCE_BUNDLE.zip` (113 members);
- `BLOCKER_RESOLUTION_BUNDLE.zip` (62 members);
- `EMPIRICAL_RESOLUTION_OUTPUTS.zip` (40 members);
- `00_PROJECT_DOSSIER_V3_EMPIRICAL_RESOLVED.md`;
- `07_AUTHOR_DECISIONS_CURRENT.md`;
- `ARTISYNTH_SIMULATION_STAGE_HANDOFF.md`;
- `ARTISYNTH_LOCAL_ENVIRONMENT.txt`.

The three ZIP archives passed Python `ZipFile.testzip()` and safe-path extraction checks in this Phase A workspace. Authority was applied at statement level, with D8 and the simulation handoff governing the corrected design. The empirical V3 dossier excludes all old simulation outputs pending this rerun.

## 2. Target formula audit

Archived Java, `analysis/artisynth/code/MandibleScalingInverseDDK.java:324-328`, codes the active target as

```text
z_target = z_base + 0.5*A*(sin(omega*tau)-1) - OPEN_GAP
v_target = A*omega*cos(omega*tau)
```

where `A=amp` is documented as peak-to-peak, `omega=2*pi*f`, and `tau=t-settle`.

For the coded active displacement,

```text
Delta z = 0.5*A*(sin(omega*tau)-1)-g,
```

the exact ordinary derivative on the active interval is

```text
d(Delta z)/dt = 0.5*A*omega*cos(omega*tau).
```

The archived velocity is therefore exactly two times the active-position derivative. This is not a labeling-only discrepancy: the inverse controller consumes both target position and target velocity, so all archived dynamic metrics and endpoints are noncanonical after correction.

The CURRENT Java implementation is at `MandibleScalingInverseDDK_CURRENT.java::TargetUpdater.apply`. It retains the approved active position and uses the exact derivative, including `0.5`. Before the settling endpoint the target remains at baseline with zero velocity. The historical active formula begins at `-A/2-g` at activation; that active-phase/offset convention is retained because the handoff explicitly specified it. Formula IDs are emitted in every successful row.

## 3. Gravity audit

Every archived location that sets, disables, or zeroes gravity is:

| Location | Behavior |
|---|---|
| `MandibleScalingInverseDDK.java:66` | `disableGravity` defaults to `true`. |
| `MandibleScalingInverseDDK.java:111-112` | `--disableGravity`/`--noGravity` can only set the flag true. |
| `MandibleScalingInverseDDK.java:529-541` | An earlier stabilization block unconditionally calls `setGravity(0,0,0)` inside a best-effort try/catch. |
| `MandibleScalingInverseDDK.java:550-556` | A second call zeroes gravity when `disableGravity` is true. |

No archived Java location enables a nonzero gravity vector in the audited model. The primary prose nevertheless says “mass--inertia--weight scaling” at `manuscript/main_CURRENT.tex:257`, which conflicts with the zero vector.

The CURRENT class accepts only `gravity=disabled` in `MandibleScalingInverseDDK_CURRENT.java::validateParams` and sets `(0,0,0)` once in `::build`. Every row records the state/vector. A gravity-enabled sensitivity is intentionally absent.

## 4. Mass, inertia, geometry, and force scaling

### Archived implementation

- Defaults are mass exponent `3` and inertia exponent `5` at `MandibleScalingInverseDDK.java:41-44`.
- Inertia-only scaling preserves geometry and center of mass, multiplies mass by `s^massExp`, and multiplies the rotational-inertia tensor by `s^inertiaExp` at `190-210`.
- A separate geometry-transform function is reachable at `174-188`.
- At `572-583`, scaling is skipped entirely when `s=1.00`; otherwise a command-line `scaleMode` selects geometry or inertia scaling.
- Reflection-based force-capacity discovery/setters are implemented at approximately `214-298`.
- The force-capacity loop runs only when `abs(forceScale-1)>1e-12` at `664-687`. Consequently all 38 old `s=1.00` force-capacity cells report `n_force_scaled=0`, despite belonging to the sensitivity mode.

### CURRENT implementation

- `MandibleScalingInverseDDK_CURRENT.java::validateParams` rejects noncanonical exponents, multipliers, and grid values.
- `::applyMassAndInertiaScaling` applies mass and rotational-inertia multipliers to the mandible at every scale, including multipliers of one at `s=1.00`; geometry is never transformed.
- `::applyForceCapacitySensitivity` uses setter/readback verification in every `force_capacity_s2` cell, including multiplier one; it fails if no muscle force-capacity property is touched. The reported count is the number of affected muscle objects, while identity-based de-duplication prevents repeated multiplication of shared storage.
- `fixed_force` returns zero force-scaled muscles and `::build` fails if any were modified.
- The wrapper and validator independently enforce `n_force_scaled=0` for fixed-force and `>0` for every successful force-capacity cell.

## 5. Complete parameter and implementation trace

| Item | Archived source / value | CURRENT disposition |
|---|---|---|
| Scale grid | Force grid defaults at `run_force_scaled_artisynth_grid_v3_extraargs.py:56`; fixed archive output also contains nine scales | Exact decimal grid 0.80–1.20 by 0.05 in shared module; Java and drivers reject other values. |
| Frequency grid | Force grid at `:57`; fixed archive output contains 1.0–10.0 by 0.5 | Exact 19 frequencies in shared module; no dynamic early stopping. |
| Amplitudes | Force grid at `:58`; fixed two-amplitude driver | 1.0 and 1.5 mm peak-to-peak only. |
| Cell count | Old long tables each contain 342 unique grid rows | 342 initialized rows per mode, 684 total, all retained. |
| Duration | Java default `4.0` at `MandibleScalingInverseDDK.java:48`; force runner `:51` | Fixed at 4.0 s. |
| Settling | Java default `0.5` at `:49`; force runner `:52` | Fixed at 0.5 s. |
| Play time | Force runner `run_force_scaled...py:53`, command manifest | Fixed at 4.8 s; headless script uses `play(4.8)`. |
| Target weight | Java `:54`; old runner arguments | Fixed at 100.0. |
| L2 regularization | Java `:55`; applied `:689-694` | Fixed at 0.01; effective setting recorded. |
| Excitation damping | Java `:56`; applied best-effort `:695-698` | Fixed at 0.1; application is not silently ignored. |
| Frame/rotary damping | `MandibleScalingInverseDDK.java:537-539` | Fixed at 2.0/4.0 and recorded. |
| Maximum step | `MandibleScalingInverseDDK.java:710` | Fixed at 0.00025 s and recorded. |
| Collision handling | Best-effort reflection/API at `:444-479` | Disabled, counted, and API success required by CURRENT `::disableCollisions`. |
| TMJ handling | Best-effort set unilateral false at `:481-519` | Exactly two connectors must be found/modified by CURRENT `::configureTmj`. |
| Hybrid solves | Best-effort disable at `:558-564` | Must be disabled and recorded. |
| Input/output probes | Best-effort removal at `:544-547` | Both removals must be verified or run fails. |
| Rest lengths | Reset at `:638-658` | Preserved; counts recorded and must be positive. |
| Target marker | Path/name/heuristic search at `:585-628` | Preserved search architecture; exact resolved name emitted. |
| Controller architecture | `TrackingController`, all muscle exciters, lower-incisor point target at `:634-708` | Preserved architecture; explicit architecture ID and effective parameters emitted. |
| Geometry/path/attachments/lever arms | Inertia mode intended to keep fixed, but geometry mode reachable | Geometry branch removed; `geometry_scaled=false` validated. |
| Open-gap | Parsed at `:120-123`; old force manifest leaves blank/default | Canonical 0.0 mm, validated and emitted. |
| Output writer | Single Java metrics row at `:409-423` | Atomic no-overwrite raw Java row plus standardized per-cell provenance record. |

## 6. Metric implementation audit

Archived and CURRENT metrics use the same definitions so that the target correction is isolated rather than combined with a metric change:

- archived sampling interval: `MandibleScalingInverseDDK.java:368-393`;
- archived RMSE: Euclidean point distance accumulated and square-rooted at `372-373,409`;
- archived source/target amplitude: `z` maxima minus minima at `376-379,410-414`;
- archived gain: source peak-to-peak divided by target peak-to-peak at `414`;
- archived peak excitation: maximum absolute excitation at `381-390`;
- archived effort: sample mean of summed squared excitations at `381-390,415`.

CURRENT equivalents are in `MandibleScalingInverseDDK_CURRENT.java::MetricsCollector.apply` and `::MetricsCollector.writeOutput`. CURRENT output additionally requires finite metrics, positive sample count, atomic creation, no overwrite, and full effective configuration.

## 7. Feasibility, prefix, and stopping audit

### Cell feasibility

The approved inclusive rule is:

```text
RMSE <= 0.5 mm
peak excitation <= 0.95
0.7 <= gain <= 1.3
```

The archived `compute_fmax.py:72-75` and `make_fmax_twoamp.py:40-44` contain these limits when called with the supplied arguments. However, `make_artisynth_twoamp_figs.py:416` defaults to gain floor 0.8, creating an alternate rule.

CURRENT scripts centralize the limits in `artisynth_common_CURRENT.py`. The case wrapper, validator, and independent fmax calculator each recompute them; the fmax script ignores stored flags.

### Prefix logic

- `compute_fmax.py:78-100` attempts prefix behavior but groups only by scale and uses `any()` to collapse duplicate-frequency rows, so mixed/duplicate data can be hidden.
- `make_fmax_twoamp.py:23-34` uses a two-consecutive-failure stopping rule.
- `make_artisynth_twoamp_figs.py:65-95,419-422` defaults to the same `kfail=2` rule.
- `summarize_force_scaled_artisynth_s2.py:9-17` selects the first available fmax-like column, so rule identity is not fixed.

CURRENT `compute_fmax_CURRENT.py::read_mode` and `::compute` require exact grids, recompute all flags, close each series at the first failed frequency, report the failed criterion/frequency, and flag later feasible cells as nonmonotonic without reopening the prefix.

### Dynamic stopping

No corrected dynamic cell is skipped because a lower frequency failed. The full grid is required to detect nonmonotonicity. Technical failure is fail-fast by default, but the 342-row table retains the failed cell and all not-attempted rows. After correction, `--resume` reruns only matching failed/not-attempted cells and refuses mismatched artifacts.

## 8. Historical commands and provenance

### Force-capacity sensitivity

The exact expanded old force-capacity commands are preserved row by row in:

```text
PREFLIGHT_EVIDENCE_BUNDLE.zip!/
analysis/artisynth/outputs/force_scaled_s2_manifest.csv
```

The manifest has 342 rows and shows the historical Python executable, case script, scale/inertia exponents, every grid coordinate, `duration=4`, `settle=0.5`, `weight=100`, `l2=0.01`, `damp=0.1`, `play_time=4.8`, output/log paths, and forwarded `--forceScale s^2` / `--forceScaleExp 2` arguments. Its first command begins:

```text
/Users/danielfriedrichs/Documents/Code/Python/SpeechRateAndMandible/.venv/bin/python
.../run_artisynth_case.py --scale 0.8 --scale_mode inertia --mass_exp 3
--inertia_exp 5 --freq_hz 1 --amp_mm 1 --duration 4 --settle 0.5
--weight 100 --l2 0.01 --damp 0.1 --play_time 4.8 ...
--extra_model_arg=--forceScale --extra_model_arg=0.64000000000000012
--extra_model_arg=--forceScaleExp --extra_model_arg=2
```

The generating loop is `run_force_scaled_artisynth_grid_v3_extraargs.py:84-144`. Compilation/smoke installation used `install_compile_and_run_force_scaled_s2.sh:30-90`, which backed up and then compiled into the shared models tree.

### Fixed-force grid

The supplied archive preserves the outer driver `run_two_amp_sweeps.sh`, which:

- deletes `runs` and `logs` at lines 19-25;
- invokes `AMP_MM="$AMP" ./run_sweep.sh` at line 28;
- invokes `quick_qc_artisynth.py` at line 30;
- concatenates the two long tables and calls `make_fmax_twoamp.py` at lines 39-76.

The delegated `run_sweep.sh`, `quick_qc_artisynth.py`, and historical `play_and_quit.jy` are not present in any of the three supplied archives. `ARTISYNTH_LOCAL_ENVIRONMENT.txt` lists local copies of the first two, but listing a path is not the file content. Therefore the exact historical fixed-force cell command cannot be established from the attachments without invention. The fixed long table itself is complete (342 unique cells), but its launch expansion is only partially documented.

### Current command policy

Every corrected cell writes its exact expanded command and hashes it; every grid writes an invocation manifest. No historical command or result cell is reused.

## 9. Cross-source conflicts

The ranked, machine-readable register is `ARTISYNTH_CONFLICT_REGISTER_CURRENT.tsv`. Highest-consequence findings are:

1. position/velocity derivative mismatch;
2. all old dynamic tables/figures/prose inherit the mismatch;
3. permissive two-failure endpoint logic conflicts with strict prefix;
4. Figure 8 and Table S3 use different endpoint rules;
5. force-capacity `s=1.00` cells did not touch a force parameter;
6. disabled gravity conflicts with “weight scaling” wording;
7. old resume/aggregation can reuse or hide incomplete cells;
8. figures omit tested low scales and the supplementary caption does not match its image.

`Figure8_CURRENT.png` panel C begins at `s=0.90`, omitting the tested 0.80 and 0.85 cells. It displays permissive recovered endpoints for at least two fixed-force series, whereas `main_CURRENT.tex:397-414` reports strict-prefix values. `SuppPub2_CURRENT.png` panels are amplitudes 1.0 and 1.5 with an effort colorbar, while `main_CURRENT.tex:464` describes panel A as peak excitation and panel B as effort. Both figures are noncanonical and must be regenerated programmatically.

## 10. Patch disposition

The package is ready for a local compile and smoke gate. It does not contain corrected simulation results. Static and synthetic tests are documented in `ARTISYNTH_PATCH_TEST_REPORT.md`. Resolution of PFL-003/PFL-007 still requires the author’s local ArtiSynth compile, two smoke tests, both 342-cell runs, PASS validation, strict-prefix computation, and returned provenance package.
