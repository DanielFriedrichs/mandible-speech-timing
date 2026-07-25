# ArtiSynth corrected-model smoke-test checklist

Run these checks only after the patch manifest passes and the isolated CURRENT class compiles successfully. Do not start either full grid until all mandatory gates pass.

## A. Compile gate

- [ ] Corrected source is `MandibleScalingInverseDDK_CURRENT.java` and public class name matches.
- [ ] Destination is a newly created isolated `corrected_classes` directory, not `artisynth_models/classes`.
- [ ] Compilation uses the documented x86_64 Temurin Java 8 JDK and actual ArtiSynth/model classpaths.
- [ ] `corrected_classes/artisynth/models/dynjaw/MandibleScalingInverseDDK_CURRENT.class` exists.
- [ ] Compiler stdout/stderr and SHA256 hashes are preserved.
- [ ] No archived source or class file changed hash during compilation.

## B. Low-frequency dynamic smoke: fixed force, `s=1.00`, `f=1.0 Hz`, `A=1.0 mm p2p`

Mandatory technical acceptance:

- [ ] Wrapper exit code is zero and `return_status=success`.
- [ ] Exactly one raw Java row and one standardized result row exist.
- [ ] Mode/grid coordinates match the command exactly.
- [ ] Position formula ID is `P2P_ONE_SIDED_SIN_ACTIVE_V1`.
- [ ] Velocity formula ID is `P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1`.
- [ ] Gravity is disabled with vector `(0,0,0)`.
- [ ] `mass_exp=3`, `inertia_exp=5`, mass/inertia multipliers are one.
- [ ] `force_exp=0`, multiplier is one, `n_force_scaled=0`.
- [ ] `geometry_scaled=false`.
- [ ] Collision disabling succeeded; both TMJs were found and modified; inherited probes were removed; hybrid solves were disabled.
- [ ] Target marker is nonempty; rest-length and exciter counts are positive.
- [ ] Duration/settle/play are `4.0/0.5/4.8 s`; controller and integration values match the specification.
- [ ] `n_samples>0`; all six scientific metrics are finite; target amplitude is close to the requested 1.0-mm p2p trajectory within numerical sampling tolerance.
- [ ] Every referenced artifact exists and its stored SHA256 matches.

Scientific feasibility is not required for technical acceptance, although a low-frequency failure should be investigated before full-grid launch because strict-prefix `fmax` would then be undefined or very low for that series.

## C. High-demand and force-capacity code-path smoke: `force_capacity_s2`, `s=1.00`, `f=10.0 Hz`, `A=1.5 mm p2p`

- [ ] Wrapper exit code is zero and `return_status=success`; scientific infeasibility is not a process failure.
- [ ] `force_exp=2`, multiplier is exactly one at `s=1.00`, and `n_force_scaled>0` despite multiplier one.
- [ ] Force-capacity setter/readback messages are present in the raw run log.
- [ ] All non-force configuration fields match the canonical fixed-force settings.
- [ ] The row contains all three recomputed criterion flags and `failed_criteria`.
- [ ] When infeasible, at least one of `tracking_rmse_mm>0.5`, `peak_excitation>0.95`, or gain outside `[0.7,1.3]` is true and named exactly in `failed_criteria`.
- [ ] When feasible, the row remains feasible; it is not forced to fail. Run `compute_fmax_CURRENT.py --self-test` to exercise the deterministic first-failure/nonmonotonicity logic independently.
- [ ] No dynamic early stopping or endpoint inference is performed from the smoke cell.

The high-frequency coordinate is a handling test, not an assumption that the corrected dynamics must fail. Its observed status controls. A paired fixed-force high-frequency smoke may be added in a separate cell directory, but it is not a substitute for proving that the `s^2` branch touches force capacity at `s=1.00`.

## D. Resume abuse tests

- [ ] Re-running a successful cell with identical `--resume` skips only after full identity verification.
- [ ] Changing the corrected Java source, compiled class, launcher, Java/Python executable, base model class, play script, or configuration causes `resume_refused`/nonzero exit.
- [ ] `--fresh` refuses an existing cell directory.
- [ ] A matching technical failure is archived and rerun rather than skipped.

## Stop conditions

Do not launch full grids if compilation fails, a smoke cell has technical failure, effective configuration cannot be verified, force-capacity `n_force_scaled<=0`, target formula IDs are wrong, artifact hashes fail, or resume accepts a mismatch.
