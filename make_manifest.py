#!/usr/bin/env python3
"""Generate or verify data/manifest.json for reproducibility.

Usage:
    python make_manifest.py generate   # create manifest from current data/ files
    python make_manifest.py verify     # check data/ files against existing manifest
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
EXTENSIONS = {".parquet", ".zip", ".csv"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate() -> None:
    entries = []
    for p in sorted(DATA_DIR.iterdir()):
        if p.suffix in EXTENSIONS and p.name != "manifest.json":
            entries.append(
                {
                    "file": p.name,
                    "sha256": _sha256(p),
                    "bytes": p.stat().st_size,
                    "recorded_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
    manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(), "files": entries}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {MANIFEST_PATH} with {len(entries)} file(s).")


def verify() -> None:
    if not MANIFEST_PATH.exists():
        print("ERROR: manifest.json not found. Run 'generate' first.", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(MANIFEST_PATH.read_text())
    ok, bad, missing = 0, 0, 0
    for entry in manifest["files"]:
        p = DATA_DIR / entry["file"]
        if not p.exists():
            print(f"MISSING  {entry['file']}")
            missing += 1
            continue
        actual = _sha256(p)
        if actual == entry["sha256"]:
            print(f"OK       {entry['file']}")
            ok += 1
        else:
            print(f"MISMATCH {entry['file']}  expected={entry['sha256'][:16]}…  actual={actual[:16]}…")
            bad += 1

    print(f"\n{ok} ok, {bad} mismatch, {missing} missing")
    if bad or missing:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("generate", "verify"):
        print(__doc__.strip())
        sys.exit(1)
    {"generate": generate, "verify": verify}[sys.argv[1]]()
