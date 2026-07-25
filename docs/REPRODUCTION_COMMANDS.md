# Reproduction commands

Run from the repository root. Each workflow begins with exact repository-input hash and count checks and fails on missing or altered inputs. Generated outputs go under the ignored `reproduced/` directory.

```bash
python analysis/verify_repository_inputs_V13.py
```

The model-stage CSVs in this package are column-minimized projections of exact canonical inputs. Their source and repository hashes, retained columns, and identity checks are recorded in `docs/source_provenance/DERIVED_DATA_MINIMIZATION_V13.tsv`.

## Primary estimand and shared-six comparison

The exact canonical checker is retained unchanged as `run_primary_estimand_checks.py`. The wrapper changes only its expected input digest to the documented repository projection.

```bash
python analysis/verify_repository_inputs_V13.py && \
python analysis/empirical/run_primary_estimand_checks_REPOSITORY_V13.py \
  --project-root . \
  --data-file data/derived/primary/analysis_dataset_clean.csv \
  --output-dir reproduced/primary_estimand
```

## Small-cluster primary checks

```bash
python analysis/verify_repository_inputs_V13.py && \
python analysis/empirical/primary_effects_small_sample_robustness.py \
  --project-root . \
  --data-file data/derived/primary/analysis_dataset_clean.csv \
  --out-dir reproduced/small_cluster \
  --n-cluster-boot 9999 \
  --n-wild-boot 9999 \
  --seed 20260420
```

## Retained empirical outputs

```bash
python analysis/verify_repository_inputs_V13.py && \
python analysis/empirical/generate_retained_empirical_outputs_V13.py \
  --repository-root . \
  --output-dir reproduced/retained_empirical
```

The exact broad `generate_canonical_empirical_outputs_CURRENT.py` is retained for provenance. A complete broad audit rerun was performed in V13 and matched all seven canonical CSVs numerically. The clean package deliberately excludes phase and coupling inputs/outputs, so the broad script is not represented as a one-command public workflow; use the scoped V13 runner for retained paper analyses.

## Upper-tail models

```bash
python analysis/verify_repository_inputs_V13.py && \
python analysis/empirical/run_upper_tail_models_V13.py \
  --input data/derived/upper_tail/speaker_upper_limits_speech.csv \
  --output reproduced/upper_tail/upper_tail_models_CURRENT_V13.csv
```

## V8 main figures and Table 1

The exact `make_main_figures_V8.py` is retained unchanged. The wrapper changes only the expected primary and secondary digests to the documented repository projections.

```bash
python analysis/verify_repository_inputs_V13.py && \
python analysis/empirical/make_main_figures_REPOSITORY_V13.py \
  --primary-data data/derived/primary/analysis_dataset_clean.csv \
  --secondary-data data/derived/secondary/analysis_ready_trials.csv \
  --primary-estimand-comparison results/primary_estimand/PRIMARY_ESTIMAND_COMPARISON_CURRENT.csv \
  --primary-all-coefficients results/primary_estimand/PRIMARY_ESTIMAND_ALL_COEFFICIENTS_CURRENT.csv \
  --secondary-effects data/derived/figure_model_sources/secondary_effect_sizes_RETAINED_V13.csv \
  --secondary-coefficients data/derived/figure_model_sources/secondary_coefficients_RETAINED_V13.csv \
  --output-dir reproduced/v8_figures \
  --seed 20260722
```

## Corrected Phase C validation from long tables

```bash
python analysis/verify_repository_inputs_V13.py && \
python artisynth/validation/validate_phase_c_tables_V13.py \
  --fixed artisynth/validated/artisynth_scaling_runs_long_CURRENT.csv \
  --force artisynth/validated/artisynth_force_scaled_runs_long_CURRENT.csv \
  --canonical-comparison artisynth/validated/artisynth_fmax_comparison_CURRENT.csv \
  --output-dir reproduced/artisynth_phase_c
```

This table-level validation independently recomputes all feasibility flags, strict-prefix endpoints, and fixed-versus-`s^2` comparisons. It does not relaunch ArtiSynth dynamics. Instructions and code for a dynamic rerun are under `artisynth/v2_4_patch/`, but an exact semantic ArtiSynth build identifier was not recoverable.
