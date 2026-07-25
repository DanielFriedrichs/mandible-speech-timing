# Public projection of corrected ArtiSynth long tables

The two public long tables preserve all 684 scientific rows, row order,
configuration values, metrics, feasibility flags, identifiers, and artifact
hash fields from the validated Phase C package. Ten machine-local path
columns were removed because those paths refer to the author workstation and
the per-cell files are not part of this compact public repository.

Removed columns:

- `cell_directory`
- `raw_java_csv_path`
- `raw_stdout_path`
- `raw_stderr_path`
- `raw_run_log_path`
- `command_path`
- `configuration_path`
- `environment_path`
- `result_json_path`
- `result_csv_path`

Original validated-file identities:

- `artisynth/validated/artisynth_scaling_runs_long_CURRENT.csv`: 342 rows;
  original Phase C SHA256 `6261db90af5132cd816945c5b3d6fd26b3d61ca7d2e6780c6cf315440f552c96`;
  public projection SHA256 `510f2e249fa2dcf62e8437bce17aefa425f999cbbed5efdbfcb2b4d42af8ebad`.
- `artisynth/validated/artisynth_force_scaled_runs_long_CURRENT.csv`: 342 rows;
  original Phase C SHA256 `ffcfdded56148b412b1b1bfefa69570a5694e3cb334d676c07694f617dc3efe4`;
  public projection SHA256 `59f84b7d5f8f1b7e7bc4455af6bacee121e278e1c82eb5d56cc9729424b58d02`.

The repository-specific Phase C validator independently recomputes all
feasibility flags and strict-prefix endpoints from the projected tables.
The archived Phase C manifest and validation report remain the provenance
record for the unprojected local-run files.
