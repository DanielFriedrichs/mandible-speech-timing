# Reproduction commands

Run all commands from the repository root. Generated files should be written to the ignored
`reproduced/` directory.

## Verify inputs

```bash
python analysis/verify_repository_inputs.py
```

## Primary estimand comparison

```bash
python analysis/empirical/run_primary_estimand_checks_public.py \
  --project-root . \
  --data-file data/derived/primary/analysis_dataset_clean.csv \
  --output-dir reproduced/primary_estimand
```

## Finite-cluster checks

```bash
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
python analysis/empirical/generate_retained_empirical_outputs.py \
  --repository-root . \
  --output-dir reproduced/retained_empirical
```

## Upper-tail models

```bash
python analysis/empirical/run_upper_tail_models.py \
  --input data/derived/upper_tail/speaker_upper_limits_speech.csv \
  --output reproduced/upper_tail/upper_tail_models.csv
```

## Main figures and Table 1

```bash
python analysis/empirical/make_main_figures.py \
  --primary-data data/derived/primary/analysis_dataset_clean.csv \
  --secondary-data data/derived/secondary/analysis_ready_trials.csv \
  --primary-estimand-comparison results/primary_estimand/comparison.csv \
  --primary-all-coefficients results/primary_estimand/all_coefficients.csv \
  --secondary-effects data/derived/figure_model_sources/secondary_effect_sizes.csv \
  --secondary-coefficients data/derived/figure_model_sources/secondary_coefficients.csv \
  --output-dir reproduced/figures \
  --seed 20260722
```

## Supplementary figures

```bash
python analysis/empirical/make_supplementary_figures.py \
  --read-speech data/derived/read_speech/read_speech_envelope.csv \
  --anatomy data/derived/anatomy/anatomy_measurements.csv \
  --read-effects results/canonical_empirical/read_speech_effects.csv \
  --artisynth-fixed artisynth/validated/fixed_force_grid.csv \
  --artisynth-force artisynth/validated/force_capacity_s2_grid.csv \
  --output-dir reproduced/figures
```

## ArtiSynth table validation

```bash
python artisynth/validation/validate_phase_c_tables.py \
  --fixed artisynth/validated/fixed_force_grid.csv \
  --force artisynth/validated/force_capacity_s2_grid.csv \
  --canonical-comparison artisynth/validated/endpoint_comparison.csv \
  --output-dir reproduced/artisynth_validation
```

This final command validates the included tables; it does not relaunch the dynamic model.
