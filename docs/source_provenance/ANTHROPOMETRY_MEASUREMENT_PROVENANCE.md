# Anthropometry measurement provenance

**Issue:** PFL-001  
**Decision:** **REMOVED_UNSUPPORTED for detailed reliability statistics**  
**Version date:** 2026-07-19

## Final evidence search

The supplementary evidence did not contain a genuine assistant × repetition reading table.

- `finalized_anatomy_measurements.csv` has 406 rows, 29 participants, and the fields `participant_id, measure, side, value_mm, value_in, value_kg, value_lb`.
- Co–Me contributes 58 rows: two side-specific finalized values for each of 29 participants.
- The declared primary key is participant × measure × side; no duplicate key rows are present.
- The schema diagnostic reviewed 142 candidate files and marked all 142 as `raw_repeated_reading_candidate=NO`. It found no assistant/rater field and no genuine repeated-reading field.
- The 29 participant-level anatomy files contain 319 finalized rows. Their 319 shared rows exactly match the aggregate table. They add no assistant/repetition information.
- `MANDIBLE_MEASUREMENT_PROTOCOL.md` defines 3D-model landmarks for a separate comparative workflow. It is not evidence for the study’s external repeated-caliper procedure.
- `plot_caliper_violins.py` is descriptive and does not generate repeatability statistics.

## What is supportable

**VERIFIED.** The released evidence stores one finalized left and one finalized right Co–Me value per participant. The analysis uses their arithmetic mean as the participant-level Co–Me predictor.

**UNRESOLVED.** The preserved files do not establish the assistant × repetition structure, handling of missing readings, side-finalization algorithm, within-side SD/range, assistant differences, ICC model or confidence-interval method, SEMs, final-predictor reliability, or attenuation calculation.

## Claims classified `REMOVED_UNSUPPORTED`

All detailed numerical claims about:

- within-side repeated-reading SD, median/IQR, maximum SD, and maximum range;
- differences between assistant-specific three-repeat means;
- ICC[A,1] and ICC[A,2], their confidence intervals, and their unit/definition;
- SEM for one assistant mean, two-assistant side mean, or bilateral participant value;
- reliability of the final predictor and expected attenuation.

No `anthropometry_reliability_CURRENT.csv`, `.py`, or run log is created because doing so would require inventing or reconstructing absent readings.

## Exact replacement Methods language

> External condylion–menton distance (Co–Me) was represented by finalized left- and right-side values in the released anthropometry table. For each participant, the analysis predictor was the arithmetic mean of those two side-specific values. Raw assistant-by-repetition readings and the calculation record used to finalize the side-specific values were unavailable in the preserved evidence package. Consequently, no repeatability coefficient or measurement-error correction is reported.

## Exact limitation language

> The released evidence preserves finalized side-specific anthropometric values but not the underlying repeated caliper readings; repeatability and measurement-error estimates therefore could not be independently reconstructed.

## Source status

| Source | Status | Use |
|---|---|---|
| `anthropometry/finalized_anatomy_measurements.csv` | VERIFIED | Finalized participant–measure–side values |
| Participant finalized anatomy files | VERIFIED_DUPLICATE_REPRESENTATION | Corroborate shared finalized values only |
| `anatomy_measurements_dict.json` | VERIFIED_SCHEMA | Field definitions and key |
| `ANTHROPOMETRY_SCHEMA_SCAN.tsv` | VERIFIED_SEARCH_DIAGNOSTIC | Documents final targeted search; not a source of reliability values |
| `MANDIBLE_MEASUREMENT_PROTOCOL.md` | EXCLUDED_FOR_HUMAN_CALIPER_METHOD | 3D landmarking protocol, not the repeated-caliper procedure |
| Manuscript reliability values | REMOVED_UNSUPPORTED | Must not be carried into the revised manuscript or Project Sources |
