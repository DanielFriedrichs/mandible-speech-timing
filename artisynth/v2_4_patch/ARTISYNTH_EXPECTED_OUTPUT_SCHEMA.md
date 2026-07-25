# ArtiSynth corrected-run output schema

The canonical long table is UTF-8 CSV with one row per expected cell and columns in the order defined by `artisynth_common_CURRENT.py::OUTPUT_COLUMNS`. Both modes use the same schema. The table is initialized with 342 rows; technical failure is represented in place rather than by dropping a cell.

## Identity and design fields

| Field(s) | Meaning / invariant |
|---|---|
| `run_id` | Unique deterministic cell ID containing mode, scale, amplitude, and frequency. |
| `spec_version` | Must equal `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`. |
| `mode` | `fixed_force` or `force_capacity_s2`. |
| `scale`, `freq_hz`, `target_amp_p2p_mm` | Exact canonical grid coordinates. |
| `mass_exp`, `inertia_exp` | `3`, `5`. |
| `mass_multiplier`, `inertia_multiplier` | `s^3`, `s^5`. |
| `force_exp` | `0` in fixed-force; `2` in force-capacity. |
| `effective_force_multiplier` | `1` in fixed-force; `s^2` in force-capacity. |
| `n_force_scaled` | `0` in fixed-force; strictly positive in every successful force-capacity cell, including `s=1.00`. |
| `duration_s`, `settle_s`, `play_time_s`, `open_gap_mm` | `4.0`, `0.5`, `4.8`, `0.0`. |

## Gravity, target, controller, and integration fields

| Field(s) | Canonical value / interpretation |
|---|---|
| `gravity_state`, `gravity_enabled`, `gravity_x/y/z` | `disabled`, `false`, `0/0/0`. |
| `target_position_formula_id` | `P2P_ONE_SIDED_SIN_ACTIVE_V1`. |
| `target_velocity_formula_id` | `P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1`. |
| `target_marker_name` | Resolved lower-incisor marker name; nonempty. |
| `controller_architecture_id` | `TrackingController_point_target_LI_L2_excitation_damping_V1`. |
| `target_weight` | `100`. |
| `l2_regularization` | `0.01`. |
| `excitation_damping` | `0.1`. |
| `frame_damping`, `rotary_damping` | `2`, `4`. |
| `max_step_s` | `0.00025`. |
| `collision_setting`, `collision_api_success`, `collision_behaviors_disabled` | Disabled and API verification outcome/count. V2 clears pair-specific overrides, disables and verifies the four primary default collision group pairs, and records four plus the number of removed overrides. Success requires verified disabling. |
| `tmj_joint_setting`, `tmj_connectors_found`, `tmj_connectors_modified` | `unilateral_false`, `2`, `2`. |
| `rest_lengths_reset`, `n_rest_lengths_reset`, `n_exciters` | Rest-length and exciter audit; successful cells require true and positive counts. |
| `hybrid_solves_disabled`, `input_probes_removed`, `output_probes_removed` | All true in successful cells. |
| `geometry_scaled` | Always false. |
| `model_units` | Resolved `mm` or `m`; metrics are converted to millimetres. |

## Technical status and metrics

| Field | Meaning |
|---|---|
| `return_status` | `success`, `not_attempted`, `timeout`, `launcher_nonzero`, `missing_output`, `malformed_output`, `internal_error`, `case_runner_missing_result`, or `resume_refused`. Only `success` is eligible for scientific evaluation. |
| `return_code` | Case launcher process code when available. |
| `failure_reason` | Nonempty for technical failures. |
| `n_samples` | Number of post-settling metric samples; positive for success. |
| `actual_source_amp_p2p_mm` | Source lower-incisor `z` peak-to-peak amplitude. |
| `actual_target_amp_p2p_mm` | Target `z` peak-to-peak amplitude. |
| `amplitude_gain` | Source amplitude / target amplitude. |
| `tracking_rmse_mm` | 3-D source-target Euclidean tracking RMSE. |
| `peak_excitation` | Maximum absolute muscle excitation. |
| `mean_summed_squared_excitation` | Mean over samples of the sum of squared excitations. |
| `rmse_ok`, `peak_excitation_ok`, `amplitude_gain_ok`, `is_feasible` | Inclusive feasibility flags recomputed by the wrapper. |
| `failed_criteria` | Semicolon-delimited failed scientific criteria, blank when feasible, or `technical_run_failure` for technical failure. |

## Artifact paths and provenance hashes

Each successful row records absolute paths to the cell directory, raw Java CSV, stdout, stderr, combined log, command, configuration, environment, result JSON, and result CSV. It records SHA256 values for:

- corrected Java source and isolated compiled class tree;
- case runner, grid runner, shared module, and play script;
- ArtiSynth launcher, selected Java executable, selected Python executable;
- baseline `JawDemo.class` and `JawModel.class`;
- aggregate code bundle and canonical configuration;
- raw Java output, stdout, stderr, combined log, command, environment, and result JSON.

`started_utc`, `finished_utc`, and `elapsed_seconds` complete the per-cell execution record.

## Grid-level and derived outputs

For each mode, `run_artisynth_grid_CURRENT.py` writes:

```text
<out-root>/<mode>/grid_configuration.json
<out-root>/<mode>/grid_environment.json
<out-root>/<mode>/grid_invocation_manifest.csv
<out-root>/<mode>/grid_run_summary.json
<out-root>/<mode>/artisynth_<mode>_runs_long_CURRENT.csv
<out-root>/<mode>/cells/<run_id>/...
<out-root>/<mode>/case_runner_invocations/...
```

The validator writes `ARTISYNTH_GRID_VALIDATION_CURRENT.{json,md}`, plus an issues TSV. `compute_fmax_CURRENT.py` writes `artisynth_cells_feasibility_CURRENT.csv` (684 rows), `artisynth_fmax_CURRENT.csv` (36 rows), and provenance. The figure script writes separate PNG/PDF panels, `TableS3_CURRENT.csv`, `TableS3_CURRENT.tex`, and figure provenance.
