#!/usr/bin/env python3
"""Checksum every raw file; prove raw/ has not changed since the first manifest.

First run: writes raw/MANIFEST.sha256 (relative path, bytes, sha256) and records the state.
Later runs: recompute and compare; any added, removed or changed file is reported and the
script exits non-zero. Also writes build/downloads.parquet (the content of the `downloads` table).
Read-only over raw/. Run:  .venv/bin/python -I pipeline/04_manifest.py
"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import os
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
BUILD = ROOT / "build"
MANIFEST = RAW / "MANIFEST.sha256"
SKIP = {"MANIFEST.sha256", "SHA256_LOCAL.txt"}  # our own bookkeeping files


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan():
    files = sorted(p for p in RAW.rglob("*") if p.is_file() and p.name not in SKIP)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        digests = list(ex.map(sha256, files))
    return {str(p.relative_to(RAW)): (p.stat().st_size, d, p.stat().st_mtime) for p, d in zip(files, digests)}


def remote_path(rel: str) -> tuple[str, str]:
    if rel.startswith("vanga/"):
        return "vanga", "s3://indian-supreme-court-judgments/" + rel[len("vanga/"):]
    return "vaquill", "hf://datasets/vaquill/open-india-law/" + rel[len("vaquill/"):]


def main() -> int:
    current = scan()
    status = 0
    if MANIFEST.exists():
        old = {}
        for line in MANIFEST.read_text().splitlines():
            rel, size, digest = line.split("\t")
            old[rel] = (int(size), digest)
        added = sorted(set(current) - set(old))
        removed = sorted(set(old) - set(current))
        changed = sorted(r for r in set(old) & set(current) if old[r] != (current[r][0], current[r][1]))
        print(f"files: {len(current)} (manifest {len(old)}); added {len(added)}, removed {len(removed)}, changed {len(changed)}")
        for label, items in (("ADDED", added), ("REMOVED", removed), ("CHANGED", changed)):
            for r in items[:10]:
                print(f"  {label}: {r}")
        if added or removed or changed:
            status = 1
    else:
        MANIFEST.write_text("".join(f"{r}\t{s}\t{d}\n" for r, (s, d, _) in sorted(current.items())))
        print(f"manifest created: {len(current)} files")

    # Cross-check against the hashes recorded right after the Vaquill download.
    local = RAW / "vaquill" / "SHA256_LOCAL.txt"
    if local.exists():
        for line in local.read_text().splitlines():
            digest, name = line.split()
            rel = f"vaquill/{name}"
            if rel in current and current[rel][1] != digest:
                print(f"  MISMATCH vs SHA256_LOCAL.txt: {rel}")
                status = 1

    BUILD.mkdir(exist_ok=True)
    rows = []
    for rel, (size, digest, mtime) in sorted(current.items()):
        source, remote = remote_path(rel)
        rows.append((source, remote, f"raw/{rel}", size, digest,
                     dt.datetime.fromtimestamp(mtime, dt.timezone.utc).replace(tzinfo=None)))
    con = duckdb.connect()
    con.execute("create table d (source varchar, remote_path varchar, local_path varchar, bytes bigint, sha256 varchar, downloaded_at timestamp)")
    con.executemany("insert into d values (?,?,?,?,?,?)", rows)
    con.execute(f"copy (select * from d order by source, remote_path) to '{BUILD}/downloads.parquet' (format parquet, compression zstd)")
    print(f"wrote build/downloads.parquet ({len(rows)} rows)")
    return status


if __name__ == "__main__":
    sys.exit(main())
