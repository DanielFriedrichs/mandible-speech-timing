# ArtiSynth installed-runtime repair V2.3

**Scientific specification:** `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`  
**Package/runtime revision:** `V2.3_COLLISION_COUNT_SEMANTICS`  
**Repair date:** 2026-07-20  
**Status:** ready for a new isolated local compile and smoke gate; no corrected dynamic result is included.

## Installed-runtime evidence

The V2.2 runner and V2.1 patch passed ZIP/hash verification, precheck, manifest verification, and isolated Java compilation. The first low-frequency dynamic smoke then stopped during model construction with:

```text
java.lang.RuntimeException:
Pair-specific collision behaviors remained after clearCollisionBehaviors()
```

No Java result row was written and no dynamics ran.

## Root cause

`CollisionManager.numBehaviors()` returns the full collision-behavior-list size. That list contains four reserved default behavior entries plus any pair-specific overrides. `CollisionManager.clearBehaviors()` deliberately removes only indices at or above `numDefaultPairs()`, preserving the reserved defaults. Therefore, after `MechModel.clearCollisionBehaviors()`, the correct invariant is:

```text
numBehaviors() == numDefaultPairs()
```

not `numBehaviors() == 0`. The V2.1 Java source used the wrong zero-count invariant and also counted the defaults as if they were overrides.

## V2.3 correction

`MandibleScalingInverseDDK_CURRENT.java::disableCollisions` now:

1. records `defaultCount = numDefaultPairs()` and `totalBefore = numBehaviors()`;
2. fails if the pre-clear counts are internally impossible;
3. calculates `overrideCount = totalBefore - defaultCount`;
4. calls `clearCollisionBehaviors()` and `clearCollisionResponses()`;
5. requires the post-clear behavior count to equal `defaultCount`;
6. separately requires `numResponses()==0`;
7. disables all defaults with `setDefaultCollisionBehavior(false,0.0)`;
8. verifies Rigid–Rigid, Rigid–Deformable, Deformable–Deformable, and Deformable–Self as present and disabled;
9. records the number of verified disabled defaults plus removed overrides.

The scientific specification is unchanged. Gravity remains disabled, the manipulation remains mass-and-inertia scaling, the target velocity remains the exact derivative of the retained target position, and all grid/feasibility/strict-prefix rules are unchanged.

## Run-root rule

The preserved V2.2 root must not be resumed because the Java source and compiled class changed. Compile this package into a new timestamped V2.3 run root and rerun both smoke cells from fresh directories.
