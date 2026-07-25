# Mandibular length and speech timing - repository-ready package

**Status:** release candidate `1.0.0` prepared for public repository publication.  
**Repository:** `https://github.com/DanielFriedrichs/mandible-speech-timing`; verify the live commit and release after pushing.  
**Analyzed dataset:** SWISSUbase/LaRS Version 1.2 (`10.48656/vc7s-pt02`; canonical DOI `10.48656/6y1s-px92`).

This directory is the clean, auditable source tree for the retained analyses and figures accompanying the mandibular-length and speech-timing manuscript. Cite a tagged release and its immutable commit; cite an archival DOI only after a live archive exists.

## Included

- column-minimized, deidentified projections of the exact canonical primary, secondary, read-speech, and finalized-anatomy model-stage inputs;
- exact current retained empirical outputs;
- primary-estimand and small-cluster results;
- exact canonical analysis scripts plus repository-specific hash wrappers for the minimized inputs;
- V8 main-figure code, data products, vector/raster figures, and Table 1 source;
- table-source CSVs for Tables S1-S4;
- the retained exploratory read-speech result and figure;
- the corrected V2.4 ArtiSynth patch, validated 342+342 long tables, compact endpoint comparison, negative supplementary heatmap, and independent table validator;
- stage-separated environments, hashes, commands, and explicit limitations.

Before minimization, V13 verified the exact canonical source hashes and counts: 8,123 primary trials from 28 speakers and 6,134 secondary parent rows from 23 speakers. The repository projections preserve row order and every retained field value exactly while omitting unrelated participant metadata, local file paths, intermediate extraction fields, and unused measurements. See `docs/source_provenance/DERIVED_DATA_MINIMIZATION_V13.tsv`.

## Excluded intentionally

Raw participant signals and direct identifiers; unrelated demographic, health, language-background, and instrumentation metadata; old manuscript/bibliography files; phase, coupling, trade-off, example, and deleted figure material; obsolete simulation code/outputs; archived endpoint claims; superseded exchangeable-GEE outputs; caches and chat transcripts.

## Quick verification

```bash
python analysis/verify_repository_inputs_V13.py
```

Then follow `docs/REPRODUCTION_COMMANDS.md`.

## Interpretation boundary

Human findings are observational associations. Speech rate, articulation rate, and speech tempo remain distinct. The corrected simulation is negative: all 684 cells were feasible through 10 Hz, the highest tested frequency, and fixed-force and `s^2` force-capacity endpoints did not differ. It does not mechanically support the human association.

## License and release

Original project code and documentation are released under the MIT License unless otherwise noted. Dataset-derived materials are distributed under the applicable CC BY 4.0 terms; see `DATA_LICENSE_AND_ATTRIBUTION.md`. Third-party dependencies retain their own licenses; see `THIRD_PARTY_NOTICES.md`.

The intended first release is `1.0.0` at `https://github.com/DanielFriedrichs/mandible-speech-timing`. Record and cite the immutable commit SHA, release URL, and any live archival DOI after publication.
