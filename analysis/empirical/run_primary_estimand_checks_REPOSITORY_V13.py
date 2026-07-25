#!/usr/bin/env python3
"""Repository-minimized-data wrapper for the exact canonical estimand checker.

The canonical script is retained unchanged as run_primary_estimand_checks.py. This
wrapper changes only the expected input digest to the V13 column-minimized
projection documented in docs/source_provenance/DERIVED_DATA_MINIMIZATION_V13.tsv.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

MINIMIZED_PRIMARY_SHA256 = "4492e389789b7126c2b9f15588b682871f374cf917aa6006134c3090bffcf9ed"

def main() -> int:
    target = Path(__file__).with_name("run_primary_estimand_checks.py")
    spec = importlib.util.spec_from_file_location("canonical_primary_estimand", target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {target}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.CANONICAL_DATA_SHA256 = MINIMIZED_PRIMARY_SHA256
    return int(mod.main())

if __name__ == "__main__":
    raise SystemExit(main())
