# Primary estimand comparison — decision summary

## Purpose

This report compares the association of bilateral mean Co–Me with the two primary DDK outcomes before and after adjustment for height. It also repeats both models in the six sequences shared by the habitual and fast conditions. The models use the author-approved participant-clustered independence-GEE specification with robust sandwich covariance.

## Canonical input

- File: `/mnt/data/v13_work/nested_extracted/V13_REPOSITORY_COMPLIANCE_INPUT_BUNDLE/historical_staging_snapshot/data/derived/analysis_dataset_clean.csv`
- SHA256: `25aaddf2ac0894b19bab058afe1fbe153b5e81b3ed4f744813e4e03c72094084`
- Co–Me mean: 110.988929 mm
- Co–Me sample SD: 10.755122 mm
- Co–Me range: 92.740000–133.390000 mm
- Shared sequences: kukuku, kutapi, pipipi, pitaku, takupi, tatata

## Full dataset

### log_speechrate

- **No height:** -3.424% [-7.334%, +0.650%], P=0.0983786, N=8123/28
- **Height-adjusted:** -6.457% [-11.338%, -1.308%], P=0.0146166, N=8123/28
- Adjustment change: -3.033 percentage points in the transformed +10-mm effect; |beta_adjusted| / |beta_unadjusted| = 1.916.

### log_articulationrate

- **No height:** -1.574% [-4.248%, +1.175%], P=0.259066, N=8123/28
- **Height-adjusted:** -4.650% [-8.175%, -0.989%], P=0.0132388, N=8123/28
- Adjustment change: -3.076 percentage points in the transformed +10-mm effect; |beta_adjusted| / |beta_unadjusted| = 3.001.

## Shared-six-sequence sensitivity

### log_speechrate

- **No height:** -3.549% [-7.778%, +0.873%], P=0.114159, N=6456/28
- **Height-adjusted:** -6.380% [-11.506%, -0.957%], P=0.0217456, N=6456/28

### log_articulationrate

- **No height:** -1.711% [-4.365%, +1.016%], P=0.216467, N=6456/28
- **Height-adjusted:** -4.711% [-8.335%, -0.944%], P=0.0147193, N=6456/28

## Interpretation guardrails

1. The no-height model estimates the association with absolute measured Co–Me under the specified task controls. The height-adjusted model estimates a contrast between speakers who differ in Co–Me at the same modeled stature. These are different estimands.
2. A larger adjusted coefficient can reflect suppression or relative-proportion structure; it does not by itself establish that height adjustment removes confounding or isolates a jaw-specific causal effect.
3. These normal-reference robust-GEE intervals are intended for the estimand decision. They do not replace the existing CR2, cluster-bootstrap, wild-cluster, equal-weight, and leave-one-speaker-out checks. If the no-height model becomes the primary specification, the same small-cluster procedures should be rerun for that specification.
4. The shared-six analysis is a focused design sensitivity. It should not be described as independent replication.

## Author decision to record

Choose one primary construct before rewriting: (a) absolute external mandibular length, or (b) external mandibular length conditional on stature. The title, abstract, Introduction, Results, and Discussion must use the same construct.
