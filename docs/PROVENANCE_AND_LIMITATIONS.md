# Provenance and limitations

## Reproducible from this repository

The package supports model-stage reproduction of the primary and retained secondary
analyses from minimized deidentified derived inputs. It also supports primary-estimand
comparison, finite-cluster checks, retained sensitivity/exploratory models, publication
figures, and independent table-level validation of the ArtiSynth outputs.

## Derived-data minimization

Before public packaging, the complete canonical tables were verified by hash and row count.
The public tables retain the rows and fields required for the reported analyses while
excluding unrelated participant metadata, direct identifiers, and machine-local paths.
The retained-column map is in `docs/source_provenance/DERIVED_DATA_MINIMIZATION.tsv`.

## Limits of first-principles reproduction

- Raw assistant-by-repetition caliper readings and the side-finalization calculation record
  were not preserved; no repeatability or measurement-error statistic is supported.
- Some raw EMA/audio signals, one named cycle-aggregation script, and complete historical
  extraction run records are unavailable. The included extraction scripts document
  preserved stages but do not reconstruct the entire pipeline from raw signals.
- The exact semantic ArtiSynth build identifier is unavailable. The recorded environment,
  source code, long tables, and file hashes provide the available provenance.

These limitations concern historical extraction and measurement documentation. They do not
change the included model-stage coefficients or the validated ArtiSynth table summaries.
