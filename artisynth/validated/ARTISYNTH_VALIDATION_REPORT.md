# ArtiSynth Phase C validation report

## Verdict

# ARTISYNTH CORRECTED RESULT DOES NOT SUPPORT THE PRIOR MECHANISTIC CLAIM

The corrected grids are technically valid and reproducible from the returned archive, but the corrected target removes the previously reported feasibility boundary. Every one of the 684 corrected cells is feasible through the 10 Hz ceiling of the approved grid. Consequently, the simulation does not support the prior claim that increasing mandibular mass and rotational inertia reduced the maximum feasible cyclic frequency under fixed force, and the force-capacity sensitivity does not attenuate or offset an endpoint effect that is no longer present.

## 1. Archive, safety, and provenance

- Corrected return ZIP SHA256: `fdaf193ea80d4c168b529b020196f795ab0b525b301aa52388d8f41b55b688ca`; the supplied sidecar matches.
- ZIP CRC: PASS.
- ZIP entries: 9075 unique entries; no unsafe paths, duplicate names, or symlinks.
- Extracted payload: 8336 files. `RETURN_FILE_MANIFEST.tsv` lists 8335 other payload files; every listed size and SHA256 passed. The only intentionally unlisted payload is the manifest itself.
- Patch manifest: PASS for 24 files.
- Orchestration runner SHA256: `e92cbf733bb1ac7bf839f6466c0fd2633417e7b0d46b1079e1ca87b357c1d5a9`; its sidecar matches.
- Corrected source SHA256: `966878ff64a50c87e287c38fb35fe0cd01c2e6dec727283315bad94bf2c06413`.
- Compiled CURRENT class-tree SHA256: `3388d7fda54372a41d2a94b5f83bdf08aa46d0e62ef9482205552e24006bacf1`.
- Fixed long-table SHA256: `6261db90af5132cd816945c5b3d6fd26b3d61ca7d2e6780c6cf315440f552c96`.
- Force-capacity long-table SHA256: `ffcfdded56148b412b1b1bfefa69570a5694e3cb334d676c07694f617dc3efe4`.

The returned V2.4 patch is not byte-identical to the original 21-file Phase A package because installed-runtime repairs were required. Across common files, 12 are unchanged and 9 changed; three runtime-repair records were added. The science-defining grid driver, strict-prefix calculator, validator, figure generator, target formula, gravity state, scaling exponents, controller settings, and thresholds were not changed. The Java differences implement collision disabling through the installed API and prevent inherited GUI/probe loading from undoing the headless canonical build; the case-runner difference repairs resume handling for a technical failure with no Java output.

## 2. Runtime and commands

The local runs used macOS 26.5.1 on arm64 hardware, an x86_64 Temurin Java 8 runtime (`1.8.0_472`) invoked through `/usr/bin/arch -x86_64`, Python 3.12.7, the recorded ArtiSynth launcher, and the isolated corrected class directory ahead of the base model classes. The launcher rejected `-version`, so an exact semantic ArtiSynth build string was not captured by the run; launcher and base-class hashes nevertheless provide exact runtime identity. The project records and runtime-repair log identify the installation as ArtiSynth 3.9.

The fixed grid ran from 2026-07-20T08:08:43Z to 2026-07-20T09:39:11Z and accumulated 1.494 cell-hours. The force-capacity grid ran from 2026-07-20T18:49:35Z to 2026-07-20T20:19:55Z and accumulated 1.492 cell-hours. Both 342-row invocation manifests contain return code 0 and `success` for every cell. Exact expanded per-cell commands are preserved in the corrected return archive.

## 3. Canonical design checks

| Check | Result |
|---|---|
| Cells per mode | 342 fixed force; 342 force capacity |
| Unique grid | 9 scales x 19 frequencies x 2 amplitudes in each mode |
| Scale grid | 0.80 to 1.20 by 0.05 |
| Frequency grid | 1.0 to 10.0 Hz by 0.5 Hz |
| Amplitude grid | 1.0 and 1.5 mm peak-to-peak |
| Duration / settling / play | 4.0 / 0.5 / 4.8 s in every row |
| Gravity | disabled; vector (0, 0, 0) |
| Geometry | not scaled |
| Mass / inertia exponents | 3 / 5 |
| Fixed-force exponent | 0; multiplier 1; `n_force_scaled=0` |
| Force-capacity exponent | 2; multiplier s^2; `n_force_scaled=24` in every cell |
| Target IDs | `P2P_ONE_SIDED_SIN_ACTIVE_V1`; `P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1` |
| Controller | identical across modes; target weight 100, L2 0.01, excitation damping 0.1 |
| Integration and damping | max step 0.00025 s; frame 2; rotary 4 |
| Collisions / TMJ / probes | collisions verified disabled; two TMJs modified; inherited probes removed |
| Cross-mode identity | PASS for all non-force configuration fields and code/runtime hashes |

## 4. Independent feasibility and strict-prefix endpoints

The independent classifier used only the raw long-form metrics:

- tracking RMSE <= 0.5 mm;
- peak excitation <= 0.95;
- amplitude gain in [0.7, 1.3], inclusive.

It matched every stored criterion flag and every stored cell-level feasibility flag.

| Quantity | Corrected value |
|---|---:|
| Feasible cells | 684 / 684 |
| Maximum RMSE | 0.034671 mm (force_capacity_s2, s=0.80, 8.0 Hz, A=1.5) |
| Maximum peak excitation | 0.835904 (force_capacity_s2, s=0.80, 4.0 Hz, A=1.0) |
| Amplitude-gain range | 0.998349 to 1.007617 |
| Series reaching a first failure | 0 / 36 |
| Locally nonmonotonic feasibility series | 0 / 36 |
| Strict-prefix endpoint | >=10 Hz for all 36 mode x scale x amplitude series |

The numeric `fmax_hz` field is 10 because 10 Hz is the highest tested frequency. It must be reported as **>=10 Hz within the tested grid**, not as a measured physical maximum of exactly 10 Hz.

## 5. Prior versus corrected result

The archived incorrect-target tables contained 268 feasible cells in each mode (536/684 total). Their independently recomputed strict-prefix endpoints ranged from 2.5 to 9.5 Hz in fixed force and 5 to 9.5 Hz in the force-capacity sensitivity. Thirteen archived series had later feasible cells after a first failure, so the old feasibility landscape was locally nonmonotonic.

After correcting the velocity target, all 148 previously infeasible cells become feasible. Every corrected endpoint is >=10 Hz, and the force-capacity-minus-fixed endpoint difference is zero for all 18 scale x amplitude comparisons. The archived Figure 8 and Table S3 therefore cannot be retained as numerical evidence.

Continuous excitation metrics do not provide a stable substitute for the missing endpoint effect. In fixed-force runs, a simple descriptive slope of mean summed-squared excitation against scale is negative in all 38 amplitude x frequency slices; peak-excitation slopes are positive in 14 slices and negative in 24. These locally irregular controller outputs remain below the feasibility threshold and do not establish a monotonic size-related loss of cyclic capacity. The s^2 sensitivity increases normalized excitation below s=1 and decreases it above s=1, as expected when force capacity itself is rescaled, but this produces no difference in strict-prefix endpoints.

## 6. Scientific interpretation and disposition

The corrected result directly invalidates the previous simulation statement that uncompensated increases in mandibular mass properties reduced feasible cyclic speed over the tested grid. It also invalidates the statement that s^2 force scaling attenuated or offset that fixed-force endpoint pattern. The corrected simulation neither estimates living-speaker mandibular mass/inertia nor provides causal evidence in humans.

**Recommended disposition:** remove Figure 8 and the simulation-supported mechanistic-convergence claim from the main manuscript. A concise negative simulation result may be retained in the Supplementary Materials for transparency, provided it states that no feasibility boundary was observed through 10 Hz and does not imply absence of effects beyond the tested grid or under other controller/geometry assumptions. Table S3 is mathematically correct in the new package but scientifically uninformative because all entries are the same lower bound.

## 7. Validation limitations

- The tested grid ends at 10 Hz; no physical maximum was observed.
- Results are controller-, target-, and model-architecture dependent.
- Geometry, lever arms, attachments, and joint constraints were intentionally held fixed.
- Gravity was disabled, so the manipulation is mass-and-inertia scaling, not weight scaling.
- Exact ArtiSynth semantic build text was not captured because the launcher did not support `-version`; binary and class hashes are retained.
- This Phase C analysis did not rerun ArtiSynth. It independently validated the locally generated return package and recomputed its derived evidence.
