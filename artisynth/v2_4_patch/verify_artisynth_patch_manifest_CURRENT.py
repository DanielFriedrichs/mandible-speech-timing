#!/usr/bin/env python3
"""Verify the immutable Phase A patch manifest before local use."""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

MANIFEST = "ARTISYNTH_PATCH_MANIFEST.tsv"
ALLOWED_UNLISTED = {MANIFEST}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("package_dir", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    root = args.package_dir.expanduser().resolve()
    manifest = root / MANIFEST
    if not manifest.is_file():
        print(f"ERROR: missing {manifest}", file=sys.stderr)
        return 20
    with manifest.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    expected_header = {"relative_path", "size_bytes", "sha256", "role"}
    if not rows or set(rows[0]) != expected_header:
        print(f"ERROR: unexpected manifest columns: {list(rows[0]) if rows else []}", file=sys.stderr)
        return 20
    errors: list[str] = []
    listed: set[str] = set()
    for row in rows:
        rel = row["relative_path"]
        listed.add(rel)
        p = root / rel
        if not p.is_file():
            errors.append(f"missing file: {rel}")
            continue
        try:
            expected_size = int(row["size_bytes"])
        except ValueError:
            errors.append(f"invalid size in manifest: {rel}")
            continue
        if p.stat().st_size != expected_size:
            errors.append(f"size mismatch: {rel}: {p.stat().st_size} != {expected_size}")
        observed = sha256(p)
        if observed != row["sha256"]:
            errors.append(f"SHA256 mismatch: {rel}: {observed} != {row['sha256']}")
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
    }
    unexpected = sorted(actual - listed - ALLOWED_UNLISTED)
    missing_listed = sorted(listed - actual)
    errors.extend(f"unlisted file: {x}" for x in unexpected)
    errors.extend(f"manifest entry absent: {x}" for x in missing_listed)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"ARTISYNTH patch manifest verification: FAIL ({len(errors)} errors)", file=sys.stderr)
        return 20
    print(f"ARTISYNTH patch manifest verification: PASS ({len(rows)} listed files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
