# ArtiSynth corrected-patch changelog

**Patch specification:** `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`  
**Principle:** preserve every prior source/output; create only new `CURRENT` files and isolated run directories.

## `MandibleScalingInverseDDK_CURRENT.java`

- Created a new public model class rather than modifying `MandibleScalingInverseDDK`.
- Corrected target velocity from `A*omega*cos(omega*tau)` to `0.5*A*omega*cos(omega*tau)`, exactly matching the derivative of the retained active displacement.
- Defined amplitude consistently as peak-to-peak and emitted position/velocity formula identifiers.
- Removed the geometry-scaling option; geometry, paths, attachments, lever arms, target architecture, and joint configuration remain fixed.
- Enforced mass multiplier `s^3` and rotational-inertia multiplier `s^5` for all cells, including `s=1.00`.
- Removed any gravity-enabled branch; the canonical class accepts only disabled gravity and records `(0,0,0)`.
- Split force behavior by explicit mode. Fixed-force never touches capacity. Force-capacity applies and reads back `s^2` in every cell, including multiplier one, and fails when no force property is touched. The count is the number of affected muscle objects; identity-based de-duplication prevents a shared material/capacity object from being multiplied more than once.
- Converted previously best-effort collision, TMJ, inherited-probe, and hybrid-solver changes into checked state with emitted counts/flags.
- Preserved the lower-incisor marker-search architecture, controller type, rest-length reset, exciter set, target weight, L2 term, excitation damping, damping values, maximum step, duration, settling interval, and metric definitions.
- Rejected unknown or noncanonical arguments.
- Expanded the raw Java output to include all effective model/controller/integration settings and metrics.
- Made raw Java output atomic and no-overwrite.

## `run_artisynth_case_CURRENT.py`

- Requires explicit local launcher, classes directories, Java home, architecture mode, corrected source, and play script; no launcher/classpath/Java version is invented.
- Uses the new model class and canonical arguments only. When `--arch-mode x86_64` is selected, `/usr/bin/arch -x86_64` wraps the actual ArtiSynth launcher rather than merely being recorded as metadata.
- Writes isolated per-cell directories and never deletes prior successful evidence.
- Separates stdout and stderr and preserves a combined log.
- Records exact command, configuration, environment, raw Java output, standardized result, timestamps, and SHA256 hashes.
- Treats nonzero launcher return, timeout, missing/malformed output, and identity mismatch as technical failures.
- Validates the raw Java row against the requested cell and canonical effective configuration before accepting success.
- Recomputes inclusive feasibility flags.
- Implements fail-closed resume: success may be skipped only after verifying configuration content/hash, source/compiled/runtime/base-class hashes, all artifact hashes, and the raw Java row. Matching failed attempts are archived and rerun; mismatches are refused.

## `run_artisynth_grid_CURRENT.py`

- Replaces separate/mismatched grid paths with one driver and `--mode fixed_force|force_capacity_s2`.
- Hard-codes the approved exact decimal grid and creates exactly 342 rows per mode.
- Runs every frequency; no scientific early stopping.
- Initializes the long table before execution so missing/failed/not-attempted cells cannot disappear.
- Updates the long table atomically after every attempt.
- Records grid configuration, environment, per-invocation command/stdout/stderr, manifest, and completion summary.
- Defaults to stopping on technical failure while retaining table state for safe hash-verified resume.

## `validate_artisynth_grid_CURRENT.py`

- Requires exactly 342 rows per mode, exact keys, unique run IDs/cells, successful technical status, canonical formulas/settings, complete artifacts, and valid hashes.
- Revalidates each raw Java row against the long table.
- Requires `n_force_scaled=0` in fixed-force and `>0` in every force-capacity cell.
- Checks cross-mode identity for grid, target, controller, integration, geometry/constraint state, and code/runtime provenance, allowing only the approved force-scaling fields and resulting dynamics to differ.
- Emits PASS/FAIL JSON, Markdown, and issue TSV.

## `compute_fmax_CURRENT.py`

- Removed all alternate endpoint definitions.
- Recomputes cell feasibility from metrics with inclusive thresholds.
- Implements only the strict prefix: the first failed frequency closes eligibility permanently.
- Records first failed frequency and criterion for each of 36 series.
- Flags feasible cells after the first failure as local nonmonotonicity without changing `fmax`.
- Includes a deterministic boundary/nonmonotonicity self-test.

## `make_artisynth_figures_CURRENT.py`

- Refuses inputs without a PASS validator report and matching source hashes.
- Requires canonical 342/342 long tables, 684 cell annotations, and 36 strict-prefix series.
- Plots all nine scales and all 19 frequencies without imposed monotonicity.
- Emits separate mode × amplitude × metric PNG/PDF files, avoiding undocumented manual composites.
- Generates `TableS3_CURRENT.csv` and `.tex` from strict-prefix output, including first-failure/nonmonotonicity provenance in the CSV.

## Shared and support files

- `artisynth_common_CURRENT.py`: central canonical constants, exact decimal grid, schema, hashing, atomic I/O, parsing, and feasibility logic.
- `play_and_quit_CURRENT.jy`: fixed 4.8-s headless play script.
- `verify_artisynth_patch_manifest_CURRENT.py`: verifies every listed package file’s size/hash and rejects unlisted files.
- Documentation records the evidence audit, schema, exact local commands, smoke criteria, and remaining provenance limitation for the historical fixed-force command expansion.

## Runtime repair V2 — 2026-07-20

The first installed-ArtiSynth smoke test identified an API mismatch in V1 collision verification and a failed-cell resume edge case. V2 replaces reflective collision calls with the documented `MechModel` collision-behavior API, verifies all four primary defaults as disabled, and permits a failed attempt's raw Java CSV to be jointly absent with its hash while retaining strict verification of every other artifact. See `ARTISYNTH_RUNTIME_REPAIR_V2.md`.

## Runtime repair V2.3 — 2026-07-20

The installed V2.2 smoke test showed that the collision API calls themselves were valid, but the verification interpreted `CollisionManager.numBehaviors()` incorrectly. ArtiSynth's behavior list contains four reserved default entries, and `clearCollisionBehaviors()` removes only entries after those defaults. The CURRENT Java source now computes `overrideCount = numBehaviors() - numDefaultPairs()`, requires the post-clear total to equal `numDefaultPairs()`, verifies `numResponses()==0`, and retains fail-closed verification that all four default behavior pairs are disabled. No scientific model setting, target formula, grid, feasibility threshold, endpoint rule, or metric definition changed.

## Installed-runtime repair V2.4 — isolated subclass attach/working directory

- Added `ArtisynthPath` and `DriverInterface` imports.
- Overrode `setWorkingDir()` to resolve `data/incisorForce` relative to
  `JawDemo.class`, not the isolated CURRENT subclass.
- Overrode `attach()` for the headless canonical run and deliberately skipped
  inherited probe/control-panel loading.
- Added a fail-closed check that the base JawDemo working directory exists.
- Did not change the target trajectory, gravity, mass/inertia/force scaling,
  controller, grid, feasibility thresholds, or strict-prefix endpoint rule.
