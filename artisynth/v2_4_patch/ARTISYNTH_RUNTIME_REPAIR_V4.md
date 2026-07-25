# ArtiSynth installed-runtime repair V2.4

**Scientific specification:** `ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2`  
**Package/runtime revision:** `V2.4_ATTACH_WORKDIR_ANCHOR`  
**Repair date:** 2026-07-20  
**Status:** ready for a new isolated local compile and smoke gate; no corrected dynamic result is included.

## Installed-runtime evidence

The V2.3 collision-count package passed ZIP/hash verification, precheck, manifest verification, and isolated Java compilation.  The first low-frequency dynamic smoke then completed model construction but failed during the inherited `JawDemo.attach()` lifecycle step:

```text
java.lang.IllegalArgumentException:
File .../corrected_classes/artisynth/models/dynjaw/data/incisorForce is not a folder
```

No Java result row was written and no dynamics ran.

## Root cause

`JawDemo.setWorkingDir()` resolves `data/incisorForce` with
`ArtisynthPath.getSrcRelativePath(this, workingDirname)`.  For an object argument,
`ArtisynthPath` uses the object's runtime class.  Because the CURRENT subclass is
intentionally loaded from the isolated `corrected_classes` directory, the
inherited lookup points below that directory rather than below the installed
`JawDemo` source tree.

The inherited `JawDemo.attach()` then calls `loadProbes()`.  Simply copying or
symlinking the data directory below `corrected_classes` would therefore also
reload the archived incisor probes after the canonical build had deliberately
removed all inherited probes.

## V2.4 correction

`MandibleScalingInverseDDK_CURRENT.java` now:

1. overrides `setWorkingDir()` and anchors the lookup to `JawDemo.class`;
2. fails closed if the base `data/incisorForce` directory cannot be resolved;
3. overrides `attach(DriverInterface)` for the headless canonical rerun;
4. sets the correctly anchored working directory;
5. deliberately does not call `JawDemo.attach()`, `loadProbes()`, or GUI control-panel loading;
6. preserves the probe-removal invariant established during `build()`.

The scientific specification is unchanged.  Gravity remains disabled, the
manipulation remains mass-and-inertia scaling, the target velocity remains the
exact derivative of the retained target position, force capacity scales as
`s^2` only in the sensitivity, and all grid/feasibility/strict-prefix rules are
unchanged.

## Run-root rule

The preserved V2.3 root must not be resumed because the Java source and compiled
class changed.  Compile this package into a new timestamped V2.4 run root and
rerun both smoke cells from fresh directories.
