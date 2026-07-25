# Provenance and limitations

## What this package reproduces

The clean package supports model-stage reproduction from deidentified derived inputs for the primary GEE, principal secondary models, primary estimand comparisons, small-cluster checks, demographic/female-only checks, strict acoustic sensitivity, primary rate interactions, availability models, upper-tail speaker-level OLS, exploratory read speech, V8 main figures, and table-only corrected Phase C validation.

## Minimum-data projection

V13 first verified the exact canonical input hashes and counts, including the 8,123-row/28-speaker primary table and the 6,134-row/23-speaker secondary parent table. It then created row-preserving column projections for repository distribution. Retained cell strings and row order were checked against the verified sources; no retained value was altered. The projections remove unrelated health, medication, language-background, profession/education, instrumentation, local-path, intermediate extraction, side-specific anatomy, weight/BMI, and other fields not needed for retained reproduction. Exact source and repository hashes are in `source_provenance/DERIVED_DATA_MINIMIZATION_V13.tsv`.

The canonical scripts `run_primary_estimand_checks.py` and `make_main_figures_V8.py` remain byte-unchanged. Their `*_REPOSITORY_V13.py` wrappers alter only the expected data digests so that the minimized projections fail loudly if changed.

## What this package does not reproduce from first principles

1. **Anthropometry repeats.** Only finalized Co-Me and height values needed for the retained read-speech merge are redistributed. Raw assistant-by-repetition readings and the finalization record are absent. No ICC, SEM, repeatability, reliability, attenuation, or measurement-error correction is supportable.
2. **EMA/audio extraction.** Raw BDF/EMA/WAV signals are not redistributed. The named `derive_ema_cycle_metrics.py` and complete historical extraction run records are absent. Retained extraction scripts are documentation only.
3. **Alternative 1-10-Hz extraction.** The exact compact model-stage result is retained, but the clean pre-merge extraction table and raw-signal run record are absent.
4. **Participant sub-185.** All 300 source timing trials were excluded and none retained; the reason-level QC flag or combination is unrecoverable.
5. **Dataset machine linkage.** Version 1.2 is author verified, but no immutable local archive digest links the model inputs to that deposit.
6. **ArtiSynth build identity.** The dynamic run is identified by launcher, base-class, source, compiled-class, and script hashes, but the exact semantic ArtiSynth build/commit identifier is unavailable.
7. **Simulation scope.** Geometry, muscle paths, attachments, lever arms, and joint constraints were fixed; gravity was disabled; the grid ended at 10 Hz. No physical maximum was observed.
8. **Generalizability and design.** The primary anatomical sample is 28 speakers, subset analyses are smaller, and the human design is observational. DDK does not establish connected-speech effects.

Raw participant signals, direct identifiers, obsolete analyses, old simulation outputs, and superseded model specifications are intentionally excluded.

## Public simulation-table projection

The public corrected ArtiSynth long tables omit ten workstation-local artifact-path columns. All scientific values and artifact hashes are preserved. See `artisynth/validated/PUBLIC_TABLE_PROJECTION_V13.md`.
