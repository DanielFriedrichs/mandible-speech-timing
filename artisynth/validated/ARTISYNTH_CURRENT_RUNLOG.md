# ARTISYNTH_CURRENT_RUNLOG

**Status:** validated corrected local run  
**Dynamic execution location:** author's macOS workstation  
**Phase C computation location:** ChatGPT analysis environment; no ArtiSynth dynamics were rerun here

## Source archives

| Archive | SHA256 |
|---|---|
| `ARTISYNTH_CORRECTED_RETURN_20260720T072821Z.zip` | `fdaf193ea80d4c168b529b020196f795ab0b525b301aa52388d8f41b55b688ca` |
| `PREFLIGHT_EVIDENCE_BUNDLE.zip` historical comparator | `0cff796dc4ab4bcddbbdd2dc212ef69f5fa966c7acfb78fbdba0c57694465998` |
| Original Phase A patch package | `31e0160a16c319976e08d0b98fcad778fb12b752a72dee3827eacb2ebfcc7bcc` |

## Local run identity

- Run ID: `20260720T072821Z`
- Run root recorded by author: `/Users/danielfriedrichs/Documents/Code/Python/SpeechRateAndMandible/corrected_artisynth_runs/V2_4_ATTACH_WORKDIR_20260720T072821Z`
- Canonical spec: `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`
- Corrected Java source SHA256: `966878ff64a50c87e287c38fb35fe0cd01c2e6dec727283315bad94bf2c06413`
- Compiled class-tree SHA256: `3388d7fda54372a41d2a94b5f83bdf08aa46d0e62ef9482205552e24006bacf1`
- Grid driver SHA256: `0bcb8f7628678d3bd8a51b26fb64563736a9fd3db76ddb26b02b0412720df2fd`
- Case runner SHA256: `59b24829bba6ca2512029d36ac1a408579102ebde95f71196a706d877cdbdfa7`
- Common module SHA256: `9e06e9cd46696fc466e38f833699185f30f816580cb0aa7238a903e2416b578f`
- Play script SHA256: `f5d273c66a6998340c7558c48aaa4890f4517969d21c6a72e5a51e2292d5599b`
- ArtiSynth launcher SHA256: `3da9f19b2e42b9ab137ee0ab16be199e13a2b8c0c8a2e698fadc510cb8594e2c`
- Java executable SHA256: `97d3a26c54ee4715ba4be0d06fc158db9c10a107390ab6f702fe1f1a680b2f45`
- Python executable SHA256: `c1feb24febf3d370ae11d6b09b84dfc46167b4fbbd5929476ad2abf8e29377ff`
- Base `JawDemo.class` SHA256: `d8fe0b6f128483ecfdd86808ee63d3b4a3356dbb137a71620f53c9e91d4dbb52`
- Base `JawModel.class` SHA256: `3c4f0329be222eed4892da7f0fd020f2ff59471ff42f5de462e378236e85fa19`

## Exact command architecture

Each cell invoked the x86_64 ArtiSynth launcher headlessly with the isolated CURRENT class directory before the base model classes, passed all model arguments between `[` and `]`, and executed `play_and_quit_CURRENT.jy`. The return archive preserves 684 expanded model commands plus 684 case-runner invocation commands and their stdout/stderr logs.

Representative fixed-force model command:

```text
/usr/bin/arch -x86_64 .../artisynth -noGui -cp <corrected_classes>:<base_classes> -model artisynth.models.dynjaw.MandibleScalingInverseDDK_CURRENT [ --mode fixed_force --scale 1.2 --freq_hz 10 --amp_p2p_mm 1.5 --mass_exp 3 --inertia_exp 5 --force_exp 0 --force_multiplier 1 --duration_s 4 --settle_s 0.5 --target_weight 100 --l2_regularization 0.01 --excitation_damping 0.1 --frame_damping 2 --rotary_damping 4 --max_step_s 0.00025 --open_gap_mm 0 --gravity disabled --out <raw_java_result.csv> --verbose ] -script <play_and_quit_CURRENT.jy>
```

Representative force-capacity command is identical except `--mode force_capacity_s2`, `--force_exp 2`, and `--force_multiplier s^2`.

## Grid completion

| Mode | Start UTC | Finish UTC | Rows | Status | Cell-time sum |
|---|---|---|---:|---|---:|
| fixed force | 2026-07-20T08:08:43Z | 2026-07-20T09:39:11Z | 342 | all success | 1.494 h |
| force capacity s^2 | 2026-07-20T18:49:35Z | 2026-07-20T20:19:55Z | 342 | all success | 1.492 h |

## Phase C independent derivation

1. Verified corrected-return ZIP digest, CRC, safe member paths, and manifest hashes.
2. Verified current 24-file patch manifest and documented differences from the original Phase A package.
3. Loaded the two raw 342-row long tables.
4. Recomputed every criterion and feasibility flag from RMSE, peak excitation, and gain without trusting stored feasibility fields.
5. Recomputed the strict feasible prefix independently for all 36 series.
6. Recomputed archived prior endpoints from the two prior long tables using the same thresholds and prefix rule.
7. Generated all canonical CSVs and figures from the independently derived tables.

The output manifest intentionally excludes its own hash and the outer ZIP to avoid self-referential hashing. The ZIP has a separate SHA256 sidecar.
