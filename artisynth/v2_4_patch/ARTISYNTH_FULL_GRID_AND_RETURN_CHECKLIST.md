# Full-grid completion and return-package checklist

## Corrected run identity

- [ ] Patch manifest verification is PASS.
- [ ] A unique timestamped `RUN_ROOT` was used.
- [ ] Archived sources/classes were backed up and hashed before compilation.
- [ ] Before/after hashes show no archived file changed.
- [ ] The CURRENT class was compiled into an isolated classes directory.
- [ ] Source, compiled class, launcher, Java, Python, base classes, and environment are hashed/recorded.

## Smoke gates

- [ ] Low fixed-force smoke is technically successful and canonically configured.
- [ ] High-demand force-capacity smoke is technically successful, records feasibility/failure criteria correctly, and has `n_force_scaled>0` at `s=1.00`.
- [ ] Strict-prefix self-test passes.
- [ ] Resume mismatch tests refuse altered code/configuration/artifacts.

## Fixed-force grid

- [ ] Exactly 342 rows.
- [ ] Exactly 342 unique run IDs/cell keys.
- [ ] All `return_status=success`; no `not_attempted` or technical failure rows.
- [ ] Every row has fixed-force exponent 0, multiplier 1, and `n_force_scaled=0`.
- [ ] Every row has corrected formula IDs and canonical gravity/controller/integration/geometry/constraint fields.
- [ ] Every per-cell raw output/log/command/config/environment/result exists and matches its stored hash.

## Force-capacity `s^2` grid

- [ ] Exactly 342 rows.
- [ ] Exactly 342 unique run IDs/cell keys.
- [ ] All `return_status=success`.
- [ ] Force exponent is 2 and multiplier is `s^2` for every row.
- [ ] `n_force_scaled>0` in all 342 rows, including all 38 `s=1.00` cells.
- [ ] All non-force design/configuration fields match fixed-force at each coordinate.
- [ ] Every per-cell artifact exists and matches its stored hash.

## Validator and derived outputs

- [ ] `ARTISYNTH_GRID_VALIDATION_CURRENT.json` status is PASS, errors 0.
- [ ] Validator confirms 342 + 342 rows, no duplicates/missing cells, canonical identity, raw-row consistency, artifact hashes, and cross-mode identity.
- [ ] `artisynth_cells_feasibility_CURRENT.csv` has exactly 684 rows.
- [ ] `artisynth_fmax_CURRENT.csv` has exactly 36 rows.
- [ ] Feasibility was recomputed from metrics using inclusive 0.5/0.95/[0.7,1.3] thresholds.
- [ ] Every series records first failed frequency and criterion, or explicit all-frequencies-feasible state.
- [ ] Locally nonmonotonic series are flagged; no monotonicity is imposed.
- [ ] Figures show every scale 0.80–1.20 and derive only from validated corrected outputs.
- [ ] `TableS3_CURRENT.csv/.tex` derive from the strict-prefix table, not old endpoints.

## Return package

- [ ] Exact patch source and package manifest included.
- [ ] Isolated compiled CURRENT class and compilation logs included.
- [ ] Original and rerun environment reports included.
- [ ] Prior-file before/after hashes and backup-hash list included.
- [ ] Low/high smoke directories and outer logs included.
- [ ] Both complete mode directories included, including every cell’s raw Java CSV, stdout, stderr, combined log, command, configuration, environment, result, and hashes.
- [ ] Both 342-row long tables, grid configurations, grid environments, invocation manifests, and summaries included.
- [ ] PASS validator JSON/Markdown/issues TSV included.
- [ ] 684-row feasibility and 36-row strict-prefix outputs/provenance included.
- [ ] Generated quantitative figures, Table S3 source, and figure provenance included.
- [ ] Return-stage manifest lists size and SHA256 for every included file.
- [ ] Return ZIP and separate SHA256 sidecar created and supplied to the chat.

## Interpretation guardrails before manuscript restoration

- [ ] No old endpoint/table/figure is promoted.
- [ ] Primary manipulation is called mass-and-inertia scaling, not weight scaling.
- [ ] Scale is not described as a direct living-speaker mass/inertia measurement.
- [ ] No causal human claim is made from the simulation.
- [ ] No monotonic trend is claimed unless the corrected grid supports it.
- [ ] If corrected qualitative behavior differs from the archived result, the corrected result replaces it.
