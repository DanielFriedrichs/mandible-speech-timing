# Analysis code

Public entry points:

- `verify_repository_inputs.py` - fail-loud hash and row-count checks;
- `empirical/run_primary_estimand_checks_public.py` - primary estimand comparison;
- `empirical/primary_effects_small_sample_robustness.py` - finite-cluster checks;
- `empirical/generate_retained_empirical_outputs.py` - retained sensitivity and exploratory models;
- `empirical/run_upper_tail_models.py` - speaker-level upper-tail models;
- `empirical/make_main_figures.py` - Figures 1 and 2 and their data products;
- `empirical/make_supplementary_figures.py` - supplementary ArtiSynth and read-speech figures.

The scripts operate on the minimized deidentified derived inputs in `data/derived/`. A small
number of ArtiSynth class and formula identifiers preserve the names used by the reported
simulation records.
