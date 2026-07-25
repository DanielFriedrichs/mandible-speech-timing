#!/usr/bin/env python3
"""Repository-minimized-data wrapper for the exact V8 figure generator.

The canonical script is retained unchanged as make_main_figures_V8.py. This
wrapper changes only the expected primary and secondary digests to the V13
column-minimized projections documented in
`docs/source_provenance/DERIVED_DATA_MINIMIZATION_V13.tsv`.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

MINIMIZED_PRIMARY_SHA256 = "4492e389789b7126c2b9f15588b682871f374cf917aa6006134c3090bffcf9ed"
MINIMIZED_SECONDARY_SHA256 = "10c3eedaf2f91990cc128639cf0475eb1c1583c821171d99a1a26d7dddb7b6e0"

def main() -> int:
    target = Path(__file__).with_name("make_main_figures_V8.py")
    spec = importlib.util.spec_from_file_location("canonical_v8_figures", target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {target}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.PRIMARY_SHA256 = MINIMIZED_PRIMARY_SHA256
    mod.SECONDARY_SHA256 = MINIMIZED_SECONDARY_SHA256
    return int(mod.main())

if __name__ == "__main__":
    raise SystemExit(main())
