# ArtiSynth to final-preflight handoff

## Scientific verdict

# ARTISYNTH CORRECTED RESULT DOES NOT SUPPORT THE PRIOR MECHANISTIC CLAIM

## Canonical files

The canonical Phase C files are those listed in `ARTISYNTH_CANONICAL_FILES_MANIFEST.tsv`. The two long tables derive directly from the validated corrected return archive; all endpoints, figures, and Table S3 derive from independent Phase C recomputation rather than from stored feasibility or fmax fields.

## Superseded simulation evidence

The following are noncanonical and must not be used in the final manuscript or Project Sources:

- `artisynth_scaling_runs_long_twoamp.csv`;
- `artisynth_force_scaled_runs_long_twoamp.csv`;
- `artisynth_fmax_by_scale_twoamp_prefix.csv`;
- `artisynth_fmax_force_scaled_s2.csv`;
- `artisynth_force_scaled_s2_fmax_comparison.csv`;
- the archived Figure 8 and supplementary simulation figure;
- the archived Table S3;
- every manuscript sentence stating that increased mandibular mass properties reduced feasible cyclic frequency or that s^2 force capacity attenuated/offset that endpoint effect.

## Supported claims

- The corrected Java target velocity is the exact derivative of the coded peak-to-peak position target.
- Gravity was disabled; the manipulation is mass-and-inertia scaling.
- The local run contains 342 unique successful cells in each mode, 684 total.
- All 684 corrected cells met RMSE <=0.5 mm, peak excitation <=0.95, and gain in [0.7,1.3].
- All 36 strict-prefix series are feasible through the tested 10-Hz ceiling, so their endpoints are >=10 Hz within the tested grid.
- Force capacity was touched for 24 muscles in every sensitivity cell, including s=1.00.
- No corrected endpoint difference exists between fixed force and s^2 force capacity.

## Prohibited claims

- Do not state that larger mass/inertia reduced corrected fmax.
- Do not state that force-capacity scaling attenuated or offset a corrected fmax effect.
- Do not report fmax as exactly 10 Hz; use >=10 Hz within the tested grid.
- Do not describe the primary manipulation as weight scaling.
- Do not treat s as a direct living-speaker measurement of mandibular mass or inertia.
- Do not treat the simulation as causal evidence in humans.
- Do not imply monotonic scale effects from the locally irregular continuous excitation metrics.

## Recommended manuscript disposition

Remove the simulation as a main-text mechanistic consistency check and remove the current Figure 8 from the main paper. A short negative result and the corrected heatmaps may be retained in the Supplementary Materials for transparency. The title, abstract, Results, Discussion, and conclusion must no longer use the simulation as support for a neuromechanical causal or convergent claim.

## Remaining author query

[AUTHOR QUERY: Can the exact ArtiSynth 3.9 semantic build/commit identifier be recovered from the local installation metadata? The returned run records the launcher and base-class hashes, but the launcher rejected the `-version` probe. This is a documentation improvement, not a blocker to the validated numerical result.]

## Inputs for final combined preflight

- `EMPIRICAL_RESOLUTION_OUTPUTS.zip`;
- `ARTISYNTH_VALIDATED_OUTPUTS.zip` and its SHA256 sidecar;
- completed `09_AUTHOR_VERIFICATION_CURRENT.md`;
- frozen current manuscript source/PDF and bibliography.

The final preflight should build the V4 dossier and source manifest from the corrected negative simulation result, not from any archived endpoint or figure.
