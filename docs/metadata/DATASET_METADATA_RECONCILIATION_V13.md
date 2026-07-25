# Dataset metadata reconciliation — V13

**Checked:** 2026-07-24  
**Analyzed release:** Version 1.2  
**Version-specific DOI:** `10.48656/vc7s-pt02`  
**Canonical DOI:** `10.48656/6y1s-px92`

## Live official record

The live SWISSUbase Version 1.2 record gives the exact title *A multimodal speech-production dataset with time-aligned articulography, EEG, audio, and vocal-tract anatomy*, publication date 12 March 2026, and version note “Minor updates to data documentaion, code, and README file.” It applies Creative Commons Attribution 4.0. Its current displayed bibliographical citation contains five creators: D. Friedrichs, V. Vyshnevetska, M. P. Lancheros Pompeyo, E. Bolt, and S. Moran.

The live version history also records Version 1.3, published 26 May 2026, with the note “Minor changes: make_sync_validation_figure.py and parse_status_and_pair_sweeps.py.” Version 1.3 was not analyzed and is not substituted for Version 1.2.

## Conflicting creator evidence

The author explicitly verifies that **Volker Dellwo is a Version 1.2 dataset author**. The controlled manuscript BibTeX and the supplied local `dataset_description.json` both contain six creators and include Dellwo. The local metadata identifies full names but contains internal `version=1.0.0`; it therefore cannot by itself establish the public Version 1.2 release metadata. A live official Version 1.0 citation also lists six creators including V. Dellwo, which demonstrates that Dellwo appeared in the repository’s public citation history.

The supplied evidence cannot determine conclusively whether the five-person Version 1.2 citation reflects an intentional creator change, an incomplete public record, or a distinction between deposit creator roles and a paper-author list. It would be improper either to delete Dellwo silently or to assert without confirmation that SWISSUbase is wrong.

## V13 disposition

The proposed BibTeX patch preserves the existing six-creator record **provisionally** under the unchanged key `FriedrichsEtAl2026Dataset`, uses Version 1.2, and does not invent names.

## Single required author action

Before submission, ask SWISSUbase/LaRS to confirm the official creator metadata for Version 1.2 and, if incomplete, correct the public record to include Volker Dellwo. After the repository confirms the record, reconcile the manuscript bibliography to the authoritative Version 1.2 citation without changing the analyzed version.

## Live source locations checked

- SWISSUbase Version 1.2 usage-license/citation page
- SWISSUbase Version 1.2 version-history page
- SWISSUbase historical Version 1.0 overview
