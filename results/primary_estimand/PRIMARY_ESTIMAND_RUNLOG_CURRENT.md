# Primary estimand checks — run log

- Start UTC: 2026-07-24T05:56:08.964274+00:00
- End UTC: 2026-07-24T05:56:09.472940+00:00
- Project root: `/mnt/data/v13_work/nested_extracted/V13_REPOSITORY_COMPLIANCE_INPUT_BUNDLE/historical_staging_snapshot`
- Selected canonical data: `/mnt/data/v13_work/nested_extracted/V13_REPOSITORY_COMPLIANCE_INPUT_BUNDLE/historical_staging_snapshot/data/derived/analysis_dataset_clean.csv`
- Canonical data SHA256: `25aaddf2ac0894b19bab058afe1fbe153b5e81b3ed4f744813e4e03c72094084`
- Script: `/mnt/data/v13_work/nested_extracted/DECISION_GATE_KIT/DECISION_GATE_KIT/run_primary_estimand_checks.py`
- Script SHA256: `daedc33528c18607ee3459d0d8ad4f85007c6566b1324faca50e348d91f8862e`
- Software: `{"numpy": "2.3.5", "pandas": "2.2.3", "patsy": "1.0.2", "platform": "Linux-6.12.13-x86_64-with-glibc2.41", "python": "3.13.5", "scipy": "1.17.0", "statsmodels": "0.14.6"}`
- Estimator: participant-clustered Gaussian identity-link GEE; independence working correlation; robust sandwich covariance.
- Intervals: two-sided 95% normal-reference Wald intervals.

## All matching canonical copies found

- `/mnt/data/v13_work/nested_extracted/V13_REPOSITORY_COMPLIANCE_INPUT_BUNDLE/historical_staging_snapshot/data/derived/analysis_dataset_clean.csv`

## Output summary

- Compact Co–Me rows: 8
- Full data models: 4
- Shared-six models: 4

## Scope limitation

This run addresses the required primary-estimand and shared-sequence comparisons only. It does not alter any existing output and does not rerun CR2, bootstrap, wild-cluster, equal-weight, or LOOSO procedures.
