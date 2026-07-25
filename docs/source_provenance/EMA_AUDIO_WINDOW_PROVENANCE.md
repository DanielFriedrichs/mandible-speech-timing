# EMA/audio analysis-window provenance

**Issue:** PFL-004  
**Decision:** **VERIFIED: variable window up to 6.0 s; fixed 4-s statement superseded**

## Code and run-record evidence

The preserved master pipeline invokes the audio and EMA-cycle stages with `--fixed_window_s 6.0`, `--trim_edge_s 0.25`, `--cap_to_next both`, and `--min_analysis_s 2.0`. The added audio extraction script has the same defaults. Its trial segment begins at onset +0.25 s, initially ends 6 s later, and is shortened to 0.25 s before the next onset and/or cue when those boundaries occur. The EMA-cycle command additionally specifies at least three cycles and dropping edge cycles; the named `derive_ema_cycle_metrics.py` file itself remains absent.

The current derived table independently confirms those settings:

| metric                                            | value              | unit   | status   |
|:--------------------------------------------------|:-------------------|:-------|:---------|
| rows                                              | 6134               | trials | VERIFIED |
| analysis-start offset (min/median/max)            | 0.25 / 0.25 / 0.25 | s      | VERIFIED |
| analysis-window minimum                           | 0                  | s      | VERIFIED |
| analysis-window median                            | 5.26676633806      | s      | VERIFIED |
| analysis-window mean                              | 5.07781815166      | s      | VERIFIED |
| analysis-window maximum                           | 6                  | s      | VERIFIED |
| windows equal to 6 s (1e−9 tolerance)             | 1550               | trials | VERIFIED |
| windows shorter than 2 s                          | 78                 | trials | VERIFIED |
| shorter-than-2-s windows marked analysis_ok=False | 78                 | trials | VERIFIED |

Every derived analysis start differs from the stored trial start by 0.25 s within floating-point precision. The maximum window is 6 s, not 4 s. All 78 windows shorter than 2 s are marked unavailable.

## Canonical decision

The actual reported mechanistic analyses use variable trial-aligned windows with a 6-s cap. The earlier fixed-4-s Methods statement is `SUPERSEDED`. The current tables are not changed to agree with the earlier prose.

## Exact corrected Methods language

> For each DDK trial, the EMA and sweep-aligned audio analysis interval began 0.25 s after the trial onset and extended for at most 6.0 s. The interval was truncated to end 0.25 s before the next trial onset or cue boundary when either occurred earlier. Segments shorter than 2.0 s were marked unavailable. Thus, the analyzed intervals were trial-specific and variable in duration rather than fixed at 4 s.

> For the acoustic analysis, the analytic-signal magnitude provided the amplitude envelope, which was smoothed with a 20-ms moving average. For spectral estimation, envelopes were downsampled to 200 Hz when the source sampling rate exceeded 400 Hz, and the dominant modulation frequency was selected within 2–10 Hz from a Welch spectrum using segments up to 4 s.

## Status

`MODEL_STAGE_VERIFIED / EXTRACTION_STAGE_DOCUMENTED_BUT_NOT_RERUN`: the parameterization is established from code, pipeline commands, and derived columns; raw EMA/audio signals were intentionally absent from the supplementary bundle, so extraction was not rerun here.
