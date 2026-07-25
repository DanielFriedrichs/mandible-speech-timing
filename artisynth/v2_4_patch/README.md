# ArtiSynth Phase A corrected patch package

**Verdict:** `ARTISYNTH PATCH READY FOR LOCAL RERUN`

This package contains code and provenance infrastructure for a clean local rerun of the mandibular mass-and-inertia simulation. It contains **no corrected dynamic simulation results**.

Start with:

1. `ARTISYNTH_AUDIT_REPORT.md`
2. `ARTISYNTH_CANONICAL_SPECIFICATION.md`
3. `ARTISYNTH_LOCAL_RERUN_INSTRUCTIONS.md`
4. `ARTISYNTH_SMOKE_TEST_CHECKLIST.md`
5. `ARTISYNTH_PATCH_TEST_REPORT.md`
6. `ARTISYNTH_FULL_GRID_AND_RETURN_CHECKLIST.md`

Verify the package before use:

```bash
/Users/danielfriedrichs/miniforge3/bin/python3 \
  verify_artisynth_patch_manifest_CURRENT.py .
```

The corrected class has a new name and must be compiled into a new isolated classes directory. Do not replace the archived `MandibleScalingInverseDDK.java` or its class file. Do not reuse any prior cell after the target-velocity correction.

## Installed-runtime repairs

The original runtime repair replaced reflective collision calls and fixed failed-cell resume handling. A second installed-runtime smoke test then exposed a count-semantics defect: ArtiSynth keeps four reserved default behaviors in the same behavior list after `clearCollisionBehaviors()`. This V2.3 package verifies that the post-clear count equals `numDefaultPairs()`, not zero, and separately verifies that collision responses are empty. Use a new timestamped V2.3 run root; never resume a V1, V2.1, or V2.2 root with this package.

## Installed-runtime revision V2.4

This package includes `ARTISYNTH_RUNTIME_REPAIR_V4.md`.  V2.4 corrects the
isolated-subclass `JawDemo.attach()` working-directory failure and prevents the
inherited attach step from reloading archived probes.  Use only the matching
V2.4 runner and a new V2.4 run root.
