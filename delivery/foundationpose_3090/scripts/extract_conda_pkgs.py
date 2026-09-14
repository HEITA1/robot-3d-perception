#!/usr/bin/env python
"""Extract conda packages directly into an env prefix (offline bootstrap).

Bypasses the conda solver entirely (the 3090 machine's channel drift made
solve-then-download closures unreproducible: incident #3). conda packages are
prefix-relative archives: a .conda file is a ZIP holding ``pkg-*.tar.zst``
(the files) and ``info-*.tar.zst`` (metadata). This script unpacks the files
straight into the destination prefix — the same result conda's transaction
produces, minus bookkeeping we do not need.

Run with the BASE miniconda python (needs the ``zstandard`` module — shipped
in offline_packages/wheels_cu124 for cp311 and cp313)::

    python extract_conda_pkgs.py --pkgs-dir <dir> --dest <env-prefix>

Corrupt/HTML downloads are skipped with a warning (zip magic check) so one
bad package cannot poison the run; the caller (INSTALL.sh) validates the
critical entries afterwards.
"""

from __future__ import annotations

import argparse
import io
import shutil
import tarfile
import zipfile
from pathlib import Path

import zstandard


def extract_one(conda_file: Path, dest: Path, tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    for old in tmp.iterdir():
        old.unlink()
    z = zipfile.ZipFile(conda_file)
    z.extractall(tmp)
    z.close()
    pkg_members = sorted(tmp.glob("pkg-*.tar.zst"))
    if not pkg_members:
        raise ValueError(f"no pkg-*.tar.zst inside {conda_file.name}")
    dctx = zstandard.ZstdDecompressor()
    for member in pkg_members:
        raw = member.read_bytes()
        tr = tarfile.open(fileobj=io.BytesIO(dctx.decompress(raw, max_output_size=2_000_000_000)), mode="r:")
        tr.extractall(dest, filter="data")
        tr.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pkgs-dir", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--tmp", default=None)
    args = parser.parse_args()

    pkgs = sorted(Path(args.pkgs_dir).glob("*.conda"))
    if not pkgs:
        print(f"[extract] no *.conda in {args.pkgs_dir}")
        return 1
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    tmp = Path(args.tmp) if args.tmp else Path("/tmp/conda_pkg_extract")

    ok, skipped = 0, []
    for p in pkgs:
        magic = p.read_bytes()[:4]
        if magic != b"PK\x03\x04":
            skipped.append(p.name)
            print(f"[extract] SKIP (not a .conda zip, likely a bad download): {p.name}")
            continue
        try:
            extract_one(p, dest, tmp)
            ok += 1
            print(f"[extract] OK {p.name}")
        except Exception as exc:  # noqa: BLE001 — report every failure explicitly
            print(f"[extract] FAIL {p.name}: {exc!r}")
            skipped.append(p.name)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"[extract] done: {ok} extracted, {len(skipped)} skipped")
    if skipped:
        print("[extract] skipped list:", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
