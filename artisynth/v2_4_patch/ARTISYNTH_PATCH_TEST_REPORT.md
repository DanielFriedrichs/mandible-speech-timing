# ArtiSynth Phase A patch test report

**Patch specification:** `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`  
**Test date:** 2026-07-19  
**Verdict of this test stage:** **PASS FOR LOCAL COMPILE/SMOKE GATE**

This report covers archive integrity checks, source-level/static checks, wrapper behavior with a deliberately fake launcher, and a fully synthetic 684-cell provenance/validation/fmax/figure pipeline. It does **not** report an ArtiSynth dynamic simulation and does not validate scientific endpoints.

## 1. Evidence-container checks

| Test | Result |
|---|---|
| `PREFLIGHT_EVIDENCE_BUNDLE.zip` CRC/readability and safe-path extraction | PASS; 113 members |
| `BLOCKER_RESOLUTION_BUNDLE.zip` CRC/readability and safe-path extraction | PASS; 62 members |
| `EMPIRICAL_RESOLUTION_OUTPUTS.zip` CRC/readability and safe-path extraction | PASS; 40 members |
| Prior source/output preservation | PASS; patch files were created in a separate package tree |

## 2. Source and algorithm tests

| Test | Method | Result |
|---|---|---|
| Python syntax/import compilation | `python3 -m py_compile ./*_CURRENT.py` | PASS |
| Strict-prefix boundary logic | `python3 compute_fmax_CURRENT.py --self-test` | PASS |
| Inclusive threshold boundaries | Internal self-test at RMSE 0.5, peak excitation 0.95, gain 0.7 and 1.3 | PASS |
| Single-failure prefix closure | Internal self-test: feasible 1.0/1.5, failed 2.0, recovered 2.5 | PASS; `fmax=1.5` |
| Java 8 language/API-shape compilation | Current Java copied into a minimal test-only stub tree and compiled with `javac --release 8` | PASS, with only the compiler's obsolete source/target warnings |
| Unknown/noncanonical model arguments | Static inspection of `parseArgs` and `validateParams` | Fail-closed |
| Architecture execution path | Static inspection confirms `/usr/bin/arch -x86_64` is prepended to the actual launcher and Java version probe when selected | PASS |

The Java stub compile checks Java 8 syntax and the set of methods referenced by the test stubs. It is not a substitute for compilation against the author's installed ArtiSynth core/models classes.

## 3. Single-case runner tests with a fake launcher

The fake launcher emitted the canonical Java schema but executed no mechanics. The tested `run_artisynth_case_CURRENT.py` and Java source hashes matched the final package versions at the time of testing.

| Test | Expected behavior | Result |
|---|---|---|
| Fresh fixed-force cell, `s=1.00`, `f=1.0`, `A=1.0` | Create isolated artifacts and successful standardized row with `n_force_scaled=0` | PASS |
| Exact resume of that cell | Verify stored identity/artifact hashes and skip without changing result | PASS |
| Fresh force-capacity cell, `s=1.00`, `f=10.0`, `A=1.5` | Exercise force-capacity path and require `n_force_scaled>0` even at multiplier 1 | PASS; fake row recorded 24 |
| Resume after changing the model-source content | Refuse reuse | PASS; exit path reported `resume_refused` and configuration-hash mismatch |
| stdout/stderr provenance | Preserve separate logs plus combined log | PASS |

These tests validate wrapper, schema, hashing, and resume behavior only. They do not establish that the real ArtiSynth force-capacity reflection path finds 24 muscles or any particular number; the local smoke test must establish `n_force_scaled>0` with the installed model.

## 4. Synthetic 684-cell end-to-end test

A synthetic test fixture created 342 fixed-force and 342 force-capacity rows with complete per-cell artifacts and matching hashes. Metrics were deliberately varied to exercise RMSE, excitation, and gain failures. One series was deliberately nonmonotonic: it failed at 3.0 Hz, recovered at 3.5 Hz, and then failed again. These numbers are test fixtures, not simulation results.

| Pipeline stage | Result |
|---|---|
| Corrected-grid validator | PASS; 342/342 rows per mode, 0 errors, 0 warnings |
| Artifact and raw-Java hash verification | PASS for all 684 fixture cells |
| Cross-mode parameter identity | PASS apart from approved force fields and synthetic dynamics |
| Independent cell-feasibility output | PASS; 684 rows |
| Strict-prefix series output | PASS; 36 rows |
| Deliberately nonmonotonic series | PASS; first failure 3.0 Hz, strict `fmax=2.5` Hz, one later feasible cell flagged, prefix not reopened |
| Figure/Table S3 source generator | PASS; 22 quantitative PNG/PDF/table outputs plus provenance/readme files |
| Figure generator's validation/hash gate | PASS with the matching validator report |

## 5. Tests intentionally deferred to the author's local environment

The following are mandatory local acceptance gates and were not performed in ChatGPT:

1. compile the corrected class against `/Users/danielfriedrichs/Applications/artisynth_core` and `/Users/danielfriedrichs/Applications/artisynth_models/classes` using the documented x86_64 Temurin Java 8 runtime;
2. start the installed ArtiSynth model and verify that the base `JawDemo`/`JawModel` APIs match the checked calls;
3. verify the actual lower-incisor marker, exactly two TMJ connectors, collision disabling, inherited-probe removal, hybrid-solver state, rest-length reset, and positive exciter count;
4. verify `n_force_scaled>0` and readback success in a real `force_capacity_s2` smoke cell, including at `s=1.00`;
5. inspect the low-frequency trajectory/metrics for physical plausibility and numerical stability;
6. run and validate the two complete corrected grids.

No old endpoint, figure, or manuscript simulation claim is validated by this test report.

## 6. Installed-runtime diagnostic and V2 repair tests (2026-07-20)

The author's V1 low-frequency smoke compiled successfully but failed during model loading because V1 could not verify collision disabling through its reflective API probes. No dynamics ran. V2 uses `clearCollisionBehaviors()`, `clearCollisionResponses()`, `setDefaultCollisionBehavior(false,0.0)`, and explicit verification of the four primary default collision pairs. A separate regression fixture confirmed that an identical failed cell with no Java output is archived and rerun under `--resume` rather than refused. The actual installed-runtime V2 compile and smoke gates remain outstanding.

## 7. Installed-runtime V2.2 finding and V2.3 correction (2026-07-20)

The V2.2 orchestration runner parsed correctly, passed precheck and package-manifest verification, and compiled the V2.1 Java source against the author's installed ArtiSynth 3.9/model classes. The low-frequency smoke stopped before dynamics because the Java verification expected `numBehaviors()==0` after clearing. Source-level inspection of ArtiSynth's `CollisionManager` shows that the four reserved defaults remain in the behavior list and that `clearBehaviors()` removes only entries after `numDefaultPairs()`. V2.3 changes the invariant to `numBehaviors()==numDefaultPairs()` and verifies that collision responses are zero. Package-manifest and ZIP integrity checks pass for the rebuilt package. The author's installed-runtime V2.3 compile and dynamic smoke gates remain mandatory.

## 8. Installed-runtime V2.3 finding and V2.4 attach/working-directory correction (2026-07-20)

The V2.3 package compiled against the author's installed ArtiSynth/model classes,
but the low-frequency smoke stopped in `JawDemo.attach()` because the inherited
working-directory lookup used the isolated CURRENT subclass location.  Official
source inspection shows that `JawDemo.attach()` also reloads probes.  V2.4
therefore anchors the working directory to `JawDemo.class` and supplies a
headless `attach()` override that does not reload probes or control panels.
Static assertions verify the override, the base-class anchor, the absence of a
`super.attach()` call, and preservation of the unchanged scientific
specification.  The author's installed-runtime V2.4 compile and dynamic smoke
gates remain mandatory.
