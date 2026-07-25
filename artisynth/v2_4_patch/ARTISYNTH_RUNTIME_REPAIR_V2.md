# ArtiSynth runtime repair V2

**Specification:** `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`  
**Repair date:** 2026-07-20  
**Status:** ready for a new isolated local compile and smoke gate; no corrected dynamic result is included.

## Diagnostic evidence

The first real low-frequency smoke attempt compiled the V1 class but failed while loading the model. ArtiSynth returned launcher code 0, wrote no Java result CSV, and emitted:

```text
java.lang.RuntimeException: Could not verify collision disabling through available APIs
    at artisynth.models.dynjaw.MandibleScalingInverseDDK_CURRENT.disableCollisions(...:465)
```

The V1 code searched reflectively for `setEnableCollisions(boolean)` and `collisionBehaviors()`. Those are not the documented `MechModel` collision-control entry points in the installed API. The model therefore failed before dynamics began.

A second V1 smoke invocation exposed a separate recovery defect: the resume verifier required a raw Java CSV even for a valid technical failure that occurred before Java could create one. It consequently reported `resume_refused` instead of archiving and rerunning the failed attempt.

## V2 corrections

1. `MandibleScalingInverseDDK_CURRENT.java`
   - uses the documented `MechModel` collision-behavior API;
   - records the number of pair-specific override behaviors present before clearing;
   - calls `clearCollisionBehaviors()` and `clearCollisionResponses()`;
   - calls `setDefaultCollisionBehavior(false, 0.0)`;
   - verifies that Rigid–Rigid, Rigid–Deformable, Deformable–Deformable, and Deformable–Self defaults are all present and disabled;
   - fails closed if any verification fails.

2. `run_artisynth_case_CURRENT.py`
   - still requires and hashes stdout, stderr, combined log, command, environment, and result JSON for every attempt;
   - requires the raw Java CSV for successful cells;
   - permits the raw Java CSV and its hash to be jointly absent for a failed attempt that ended before Java output creation;
   - continues to refuse partial, untracked, changed, or hash-mismatched artifacts.

3. Package identity
   - the specification ID, source hashes, manifest, and package ZIP hash are new;
   - the V1 run root must remain preserved and must not be resumed with V2 code;
   - V2 must be compiled in a new timestamped isolated run root.

## Tests performed outside ArtiSynth

- Python syntax compilation: PASS.
- Strict-prefix self-test: PASS.
- Failed-cell regression test: a fake launcher returned 0 without creating Java output; a fresh attempt produced `missing_output`, and an identical `--resume` archived and reran that failed attempt instead of reporting `resume_refused`: PASS.
- Collision API-shape compile using minimal Java 8 stubs for the documented methods: PASS.
- Package manifest verification and ZIP CRC test: PASS.

These are software/provenance tests. The author's actual ArtiSynth compile and two dynamic smoke cells remain mandatory.
