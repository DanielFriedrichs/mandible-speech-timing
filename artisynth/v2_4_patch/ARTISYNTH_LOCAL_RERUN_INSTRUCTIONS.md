# Exact macOS local rerun instructions — V2

Use the supplied `RUN_ARTISYNTH_SAFE_V2.sh` instead of copying wrapped commands from a PDF. These commands are retained as the underlying auditable sequence.

These commands are tailored to `ARTISYNTH_LOCAL_ENVIRONMENT.txt`:

```text
project root: /Users/danielfriedrichs/Documents/Code/Python/SpeechRateAndMandible
ArtiSynth:    /Users/danielfriedrichs/Applications/artisynth_core/bin/artisynth
models:       /Users/danielfriedrichs/Applications/artisynth_models
Python:       /Users/danielfriedrichs/miniforge3/bin/python3 (3.12.7)
Java:         /Library/Java/JavaVirtualMachines/temurin-8.jdk/Contents/Home (x86_64)
host:         macOS 26.5.1, arm64
```

The isolated CURRENT class is compiled outside the shared models class tree and loaded first on the ArtiSynth `-cp`. No prior source, class, run cell, table, or figure is overwritten.

## 0. Put the downloaded patch ZIP in Downloads

The commands below assume:

```text
$HOME/Downloads/ARTISYNTH_PATCH_PACKAGE_V2.zip
```

Change only `PATCH_ZIP` if the browser saved it elsewhere.

## 1. Create a new timestamped corrected-run root

Copy and paste this block into Terminal:

```bash
set -euo pipefail
umask 077

PROJECT="/Users/danielfriedrichs/Documents/Code/Python/SpeechRateAndMandible"
ARTISYNTH_HOME="/Users/danielfriedrichs/Applications/artisynth_core"
ARTISYNTH_BIN="$ARTISYNTH_HOME/bin/artisynth"
MODELS="/Users/danielfriedrichs/Applications/artisynth_models"
BASE_CLASSES="$MODELS/classes"
PY="/Users/danielfriedrichs/miniforge3/bin/python3"
JAVA_HOME="/Library/Java/JavaVirtualMachines/temurin-8.jdk/Contents/Home"
PATCH_ZIP="${PATCH_ZIP:-$HOME/Downloads/ARTISYNTH_PATCH_PACKAGE_V2.zip}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="$PROJECT/corrected_artisynth_runs/$STAMP"

[ -f "$PATCH_ZIP" ] || { echo "Missing patch ZIP: $PATCH_ZIP" >&2; exit 2; }
[ -x "$ARTISYNTH_BIN" ] || { echo "Missing ArtiSynth launcher: $ARTISYNTH_BIN" >&2; exit 2; }
[ -d "$BASE_CLASSES" ] || { echo "Missing model classes: $BASE_CLASSES" >&2; exit 2; }
[ -x "$PY" ] || { echo "Missing Python: $PY" >&2; exit 2; }
[ -x "$JAVA_HOME/bin/java" ] || { echo "Missing Java 8 executable: $JAVA_HOME/bin/java" >&2; exit 2; }
[ ! -e "$RUN_ROOT" ] || { echo "Refusing existing run root: $RUN_ROOT" >&2; exit 2; }

mkdir -p "$RUN_ROOT"/{patch_extract,prior_backup,corrected_classes,smoke,grids,derived/validation,derived/fmax,derived/figures,logs,environment,return_stage}
printf '%s\n' "$RUN_ROOT" > "$RUN_ROOT/RUN_ROOT_ABSOLUTE_PATH.txt"
printf '%s\n' "$STAMP" > "$RUN_ROOT/RUN_ID_UTC.txt"
cp -p "$PATCH_ZIP" "$RUN_ROOT/"
shasum -a 256 "$RUN_ROOT/$(basename "$PATCH_ZIP")" > "$RUN_ROOT/logs/PATCH_ZIP_SHA256.txt"

ditto -x -k "$PATCH_ZIP" "$RUN_ROOT/patch_extract" 
CODE="$RUN_ROOT/patch_extract/ARTISYNTH_PATCH_PACKAGE"
[ -d "$CODE" ] || { echo "Expected package directory not found: $CODE" >&2; exit 2; }

"$PY" "$CODE/verify_artisynth_patch_manifest_CURRENT.py" "$CODE" \
  > "$RUN_ROOT/logs/verify_patch_manifest.stdout.log" \
  2> "$RUN_ROOT/logs/verify_patch_manifest.stderr.log"
cat "$RUN_ROOT/logs/verify_patch_manifest.stdout.log"

export PROJECT ARTISYNTH_HOME ARTISYNTH_BIN MODELS BASE_CLASSES PY JAVA_HOME PATCH_ZIP STAMP RUN_ROOT CODE
```

Keep this Terminal session open so the exported variables remain defined. The timestamped root is immutable by policy: never point a different patch or configuration at it. `--fresh` and hash-gated `--resume` enforce that policy at cell/grid level.

## 2. Back up and hash all identified prior code without altering it

```bash
set -euo pipefail

while IFS= read -r SRC; do
  [ -n "$SRC" ] || continue
  if [ -f "$SRC" ]; then
    REL="${SRC#/}"
    DEST="$RUN_ROOT/prior_backup/$REL"
    mkdir -p "$(dirname "$DEST")"
    ditto "$SRC" "$DEST"
  else
    printf 'MISSING\t%s\n' "$SRC"
  fi
done < "$CODE/ARTISYNTH_PRIOR_SOURCE_PATHS.txt" \
  > "$RUN_ROOT/logs/prior_backup_missing.tsv" \
  2> "$RUN_ROOT/logs/prior_backup.stderr.log"

while IFS= read -r SRC; do
  [ -f "$SRC" ] && shasum -a 256 "$SRC"
done < "$CODE/ARTISYNTH_PRIOR_SOURCE_PATHS.txt" \
  > "$RUN_ROOT/logs/prior_live_hashes_before_compile.sha256"

find "$RUN_ROOT/prior_backup" -type f -exec shasum -a 256 {} \; \
  | LC_ALL=C sort -k2 \
  > "$RUN_ROOT/logs/prior_backup_hashes.sha256"

chmod -R a-w "$RUN_ROOT/prior_backup"
```

This is a copy-only operation. It does not install the CURRENT source over the old model.

## 3. Compile the corrected class into the isolated directory

```bash
set -euo pipefail

CP="$BASE_CLASSES:$ARTISYNTH_HOME/classes:$ARTISYNTH_HOME/lib/*"
CORRECTED_CLASS="$RUN_ROOT/corrected_classes/artisynth/models/dynjaw/MandibleScalingInverseDDK_CURRENT.class"

{
  echo "JAVA_HOME=$JAVA_HOME"
  /usr/bin/file "$JAVA_HOME/bin/java"
  /usr/bin/arch -x86_64 "$JAVA_HOME/bin/java" -version
  /usr/bin/arch -x86_64 "$JAVA_HOME/bin/javac" -version
  echo "CLASSPATH=$CP"
} > "$RUN_ROOT/logs/compile_environment.stdout.log" \
  2> "$RUN_ROOT/logs/compile_environment.stderr.log"

/usr/bin/arch -x86_64 "$JAVA_HOME/bin/javac" \
  -cp "$CP" \
  -d "$RUN_ROOT/corrected_classes" \
  "$CODE/MandibleScalingInverseDDK_CURRENT.java" \
  > "$RUN_ROOT/logs/javac_CURRENT.stdout.log" \
  2> "$RUN_ROOT/logs/javac_CURRENT.stderr.log"

[ -f "$CORRECTED_CLASS" ] || { echo "Corrected class was not created: $CORRECTED_CLASS" >&2; exit 20; }
shasum -a 256 "$CODE/MandibleScalingInverseDDK_CURRENT.java" "$CORRECTED_CLASS" \
  > "$RUN_ROOT/logs/CURRENT_SOURCE_AND_CLASS.sha256"

while IFS= read -r SRC; do
  [ -f "$SRC" ] && shasum -a 256 "$SRC"
done < "$CODE/ARTISYNTH_PRIOR_SOURCE_PATHS.txt" \
  > "$RUN_ROOT/logs/prior_live_hashes_after_compile.sha256"

diff -u "$RUN_ROOT/logs/prior_live_hashes_before_compile.sha256" \
        "$RUN_ROOT/logs/prior_live_hashes_after_compile.sha256" \
  > "$RUN_ROOT/logs/prior_live_hashes_compile_diff.txt" || {
    echo "ERROR: a prior source/class hash changed during isolated compilation" >&2
    cat "$RUN_ROOT/logs/prior_live_hashes_compile_diff.txt" >&2
    exit 20
  }
```

A nonempty compiler stderr file is not automatically a failure; the command’s exit status and class existence are decisive. Review warnings before smoke testing.

## 4. Low-frequency smoke test: fixed force, `s=1.00`, `f=1.0`, `A=1.0 mm p2p`

```bash
set -euo pipefail

"$PY" "$CODE/run_artisynth_case_CURRENT.py" \
  --mode fixed_force \
  --scale 1.00 \
  --freq-hz 1.0 \
  --amp-p2p-mm 1.0 \
  --out-dir "$RUN_ROOT/smoke" \
  --artisynth-bin "$ARTISYNTH_BIN" \
  --classes-dir "$RUN_ROOT/corrected_classes" \
  --base-classes-dir "$BASE_CLASSES" \
  --source-java "$CODE/MandibleScalingInverseDDK_CURRENT.java" \
  --play-script "$CODE/play_and_quit_CURRENT.jy" \
  --java-home "$JAVA_HOME" \
  --arch-mode x86_64 \
  --timeout-s 600 \
  --fresh \
  > "$RUN_ROOT/logs/smoke_low_fixed.stdout.log" \
  2> "$RUN_ROOT/logs/smoke_low_fixed.stderr.log"

LOW_RESULT="$RUN_ROOT/smoke/fixed_force__s1p00__f1p0__A1p0/result.csv"
[ -f "$LOW_RESULT" ] || { echo "Missing low-smoke result: $LOW_RESULT" >&2; exit 20; }
"$PY" - "$LOW_RESULT" <<'PY'
import csv, math, sys
p=sys.argv[1]
with open(p, newline='', encoding='utf-8') as f:
    rows=list(csv.DictReader(f))
assert len(rows)==1
r=rows[0]
assert r['return_status']=='success', r
assert r['mode']=='fixed_force'
assert r['target_position_formula_id']=='P2P_ONE_SIDED_SIN_ACTIVE_V1'
assert r['target_velocity_formula_id']=='P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1'
assert r['gravity_state']=='disabled' and r['gravity_enabled'].lower()=='false'
assert all(float(r[k])==0 for k in ('gravity_x','gravity_y','gravity_z'))
assert int(r['n_force_scaled'])==0
assert r['geometry_scaled'].lower()=='false'
assert int(r['n_samples'])>0
for k in ('actual_source_amp_p2p_mm','actual_target_amp_p2p_mm','amplitude_gain',
          'tracking_rmse_mm','peak_excitation','mean_summed_squared_excitation'):
    assert math.isfinite(float(r[k])), (k,r[k])
print('LOW SMOKE TECHNICAL ACCEPTANCE: PASS')
print({k:r[k] for k in ('is_feasible','failed_criteria','tracking_rmse_mm','peak_excitation','amplitude_gain','n_force_scaled')})
PY
```

## 5. High-frequency smoke test: force-capacity path at `s=1.00`, `f=10.0`, `A=1.5 mm p2p`

This coordinate both tests high-demand feasibility handling and proves that the `s^2` branch touches force parameters even when the multiplier equals one.

```bash
set -euo pipefail

"$PY" "$CODE/run_artisynth_case_CURRENT.py" \
  --mode force_capacity_s2 \
  --scale 1.00 \
  --freq-hz 10.0 \
  --amp-p2p-mm 1.5 \
  --out-dir "$RUN_ROOT/smoke" \
  --artisynth-bin "$ARTISYNTH_BIN" \
  --classes-dir "$RUN_ROOT/corrected_classes" \
  --base-classes-dir "$BASE_CLASSES" \
  --source-java "$CODE/MandibleScalingInverseDDK_CURRENT.java" \
  --play-script "$CODE/play_and_quit_CURRENT.jy" \
  --java-home "$JAVA_HOME" \
  --arch-mode x86_64 \
  --timeout-s 600 \
  --fresh \
  > "$RUN_ROOT/logs/smoke_high_force.stdout.log" \
  2> "$RUN_ROOT/logs/smoke_high_force.stderr.log"

HIGH_RESULT="$RUN_ROOT/smoke/force_capacity_s2__s1p00__f10p0__A1p5/result.csv"
[ -f "$HIGH_RESULT" ] || { echo "Missing high-smoke result: $HIGH_RESULT" >&2; exit 20; }
"$PY" - "$HIGH_RESULT" <<'PY'
import csv, sys
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    r=next(csv.DictReader(f))
assert r['return_status']=='success', r
assert r['mode']=='force_capacity_s2'
assert float(r['force_exp'])==2.0
assert abs(float(r['effective_force_multiplier'])-1.0)<1e-12
assert int(r['n_force_scaled'])>0, r['n_force_scaled']
failed=[]
if float(r['tracking_rmse_mm'])>0.5: failed.append('tracking_rmse_mm')
if float(r['peak_excitation'])>0.95: failed.append('peak_excitation')
if not (0.7<=float(r['amplitude_gain'])<=1.3): failed.append('amplitude_gain')
is_feasible=r['is_feasible'].lower()=='true'
assert is_feasible == (len(failed)==0), (is_feasible,failed,r['failed_criteria'])
if failed:
    assert set(r['failed_criteria'].split(';'))==set(failed), (failed,r['failed_criteria'])
    print('HIGH SMOKE SCIENTIFIC-FAILURE HANDLING: PASS', failed)
else:
    print('HIGH SMOKE WAS FEASIBLE; no failure may be manufactured. Deterministic prefix self-test follows.')
print({k:r[k] for k in ('is_feasible','failed_criteria','tracking_rmse_mm','peak_excitation','amplitude_gain','n_force_scaled')})
PY

"$PY" "$CODE/compute_fmax_CURRENT.py" --self-test \
  > "$RUN_ROOT/logs/compute_fmax_self_test.stdout.log" \
  2> "$RUN_ROOT/logs/compute_fmax_self_test.stderr.log"
cat "$RUN_ROOT/logs/compute_fmax_self_test.stdout.log"
```

Do not require the high-demand dynamic cell to be infeasible. Its computed status must be accepted as observed. The self-test deterministically exercises an isolated first failure followed by recovery and confirms that the prefix remains closed.

## 6. Complete fixed-force grid: 342 cells

```bash
set -euo pipefail

"$PY" "$CODE/run_artisynth_grid_CURRENT.py" \
  --mode fixed_force \
  --out-root "$RUN_ROOT/grids" \
  --artisynth-bin "$ARTISYNTH_BIN" \
  --classes-dir "$RUN_ROOT/corrected_classes" \
  --base-classes-dir "$BASE_CLASSES" \
  --source-java "$CODE/MandibleScalingInverseDDK_CURRENT.java" \
  --play-script "$CODE/play_and_quit_CURRENT.jy" \
  --java-home "$JAVA_HOME" \
  --arch-mode x86_64 \
  --timeout-s 600 \
  --fresh \
  > "$RUN_ROOT/logs/grid_fixed_force.stdout.log" \
  2> "$RUN_ROOT/logs/grid_fixed_force.stderr.log"
```

If a technical failure stops the grid, resolve the cause without changing code/configuration, then use the same command with `--resume` instead of `--fresh`. Never add `--continue-after-technical-failure` merely to obtain a partial-looking table.

## 7. Complete `s^2` force-capacity grid: 342 cells

```bash
set -euo pipefail

"$PY" "$CODE/run_artisynth_grid_CURRENT.py" \
  --mode force_capacity_s2 \
  --out-root "$RUN_ROOT/grids" \
  --artisynth-bin "$ARTISYNTH_BIN" \
  --classes-dir "$RUN_ROOT/corrected_classes" \
  --base-classes-dir "$BASE_CLASSES" \
  --source-java "$CODE/MandibleScalingInverseDDK_CURRENT.java" \
  --play-script "$CODE/play_and_quit_CURRENT.jy" \
  --java-home "$JAVA_HOME" \
  --arch-mode x86_64 \
  --timeout-s 600 \
  --fresh \
  > "$RUN_ROOT/logs/grid_force_capacity_s2.stdout.log" \
  2> "$RUN_ROOT/logs/grid_force_capacity_s2.stderr.log"
```

The corresponding resume command is identical except for `--resume`. Resume refuses any changed source, class, launcher, Java/Python executable, base model class, play script, path/configuration, or stored artifact hash. It never accepts a cell from the archived pre-correction model.

## 8. Validate both grids

```bash
set -euo pipefail

FIXED_LONG="$RUN_ROOT/grids/fixed_force/artisynth_fixed_force_runs_long_CURRENT.csv"
FORCE_LONG="$RUN_ROOT/grids/force_capacity_s2/artisynth_force_capacity_s2_runs_long_CURRENT.csv"

"$PY" "$CODE/validate_artisynth_grid_CURRENT.py" \
  --fixed "$FIXED_LONG" \
  --force-scaled "$FORCE_LONG" \
  --out-dir "$RUN_ROOT/derived/validation" \
  > "$RUN_ROOT/logs/validate_grids.stdout.log" \
  2> "$RUN_ROOT/logs/validate_grids.stderr.log"

cat "$RUN_ROOT/derived/validation/ARTISYNTH_GRID_VALIDATION_CURRENT.md"
```

Proceed only when status is `PASS`, both row counts are 342, errors are zero, and every successful force-capacity row has `n_force_scaled>0`.

## 9. Independently compute strict-prefix `fmax`

```bash
set -euo pipefail

"$PY" "$CODE/compute_fmax_CURRENT.py" \
  --fixed "$FIXED_LONG" \
  --force-scaled "$FORCE_LONG" \
  --out-dir "$RUN_ROOT/derived/fmax" \
  > "$RUN_ROOT/logs/compute_fmax.stdout.log" \
  2> "$RUN_ROOT/logs/compute_fmax.stderr.log"

[ "$(awk 'END{print NR-1}' "$RUN_ROOT/derived/fmax/artisynth_cells_feasibility_CURRENT.csv")" -eq 684 ]
[ "$(awk 'END{print NR-1}' "$RUN_ROOT/derived/fmax/artisynth_fmax_CURRENT.csv")" -eq 36 ]
```

Then generate quantitative source panels and Table S3 only from validated corrected outputs:

```bash
set -euo pipefail

"$PY" "$CODE/make_artisynth_figures_CURRENT.py" \
  --fixed "$FIXED_LONG" \
  --force-scaled "$FORCE_LONG" \
  --fmax "$RUN_ROOT/derived/fmax/artisynth_fmax_CURRENT.csv" \
  --cells-feasibility "$RUN_ROOT/derived/fmax/artisynth_cells_feasibility_CURRENT.csv" \
  --validation-json "$RUN_ROOT/derived/validation/ARTISYNTH_GRID_VALIDATION_CURRENT.json" \
  --out-dir "$RUN_ROOT/derived/figures" \
  > "$RUN_ROOT/logs/make_figures.stdout.log" \
  2> "$RUN_ROOT/logs/make_figures.stderr.log"
```

Do not manually transfer old endpoints into these outputs.

## 10. Package code, raw logs, manifests, long tables, outputs, and environment

```bash
set -euo pipefail

{
  echo "captured_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sw_vers
  uname -a
  /usr/bin/arch
  "$PY" -VV
  "$PY" - <<'PY'
import platform,sys
print('python_executable='+sys.executable)
print('platform='+platform.platform())
PY
  /usr/bin/file "$JAVA_HOME/bin/java"
  /usr/bin/arch -x86_64 "$JAVA_HOME/bin/java" -version
  /usr/bin/arch -x86_64 "$ARTISYNTH_BIN" -version || true
} > "$RUN_ROOT/environment/ARTISYNTH_LOCAL_ENVIRONMENT_RERUN.txt" \
  2> "$RUN_ROOT/environment/ARTISYNTH_LOCAL_ENVIRONMENT_RERUN.stderr.log"

RETURN_STAGE="$RUN_ROOT/return_stage/ARTISYNTH_CORRECTED_RETURN_$STAMP"
mkdir -p "$RETURN_STAGE"
ditto "$CODE" "$RETURN_STAGE/patch_code"
ditto "$RUN_ROOT/corrected_classes" "$RETURN_STAGE/corrected_classes"
ditto "$RUN_ROOT/smoke" "$RETURN_STAGE/smoke"
ditto "$RUN_ROOT/grids" "$RETURN_STAGE/grids"
ditto "$RUN_ROOT/derived" "$RETURN_STAGE/derived"
ditto "$RUN_ROOT/logs" "$RETURN_STAGE/logs"
ditto "$RUN_ROOT/environment" "$RETURN_STAGE/environment"
cp -p "$RUN_ROOT/RUN_ROOT_ABSOLUTE_PATH.txt" "$RUN_ROOT/RUN_ID_UTC.txt" "$RETURN_STAGE/"

"$PY" - "$RETURN_STAGE" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1]).resolve()
out=root/'RETURN_FILE_MANIFEST.tsv'
rows=[]
for p in sorted(x for x in root.rglob('*') if x.is_file() and x.name!='RETURN_FILE_MANIFEST.tsv'):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    rows.append((p.relative_to(root).as_posix(),p.stat().st_size,h.hexdigest()))
with out.open('w',encoding='utf-8',newline='') as f:
    f.write('relative_path\tsize_bytes\tsha256\n')
    for row in rows: f.write('%s\t%d\t%s\n'%row)
print(f'wrote {out} with {len(rows)} entries')
PY

chmod -R a-w "$RETURN_STAGE"
RETURN_ZIP="$RUN_ROOT/ARTISYNTH_CORRECTED_RETURN_$STAMP.zip"
ditto -c -k --sequesterRsrc --keepParent "$RETURN_STAGE" "$RETURN_ZIP"
shasum -a 256 "$RETURN_ZIP" > "$RETURN_ZIP.sha256"

printf 'Return ZIP: %s\nSHA256: %s\n' \
  "$RETURN_ZIP" "$(awk '{print $1}' "$RETURN_ZIP.sha256")"
```

Return the ZIP and its `.sha256` file to this chat. The package must include the two 342-row long tables, all per-cell logs/raw Java rows/configurations, PASS validation, 684-row feasibility table, 36-row strict-prefix summary, generated figures/Table S3 source, exact code, isolated class, commands, hashes, and rerun environment.

## Safe resume policy, summarized

1. Use only the same `RUN_ROOT`, extracted `CODE`, isolated compiled classes, launcher, Java home, Python executable, base classes, mode, timeout, and paths.
2. Replace `--fresh` with `--resume`; change nothing else.
3. Successful matching cells are hash-verified and skipped.
4. Matching failed/not-attempted cells are rerun.
5. Any configuration/content/hash mismatch is refused. Start a new timestamped run root after any code, compilation, runtime, or canonical-configuration change.
6. Never copy an old result CSV into a CURRENT cell directory.
