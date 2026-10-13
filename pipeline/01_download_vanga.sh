#!/usr/bin/env bash
# Stage 1: download Vanga Supreme Court metadata (public bucket, anonymous access).
# Idempotent and resumable: `aws s3 sync` skips files already present with the same size.
# Downloads parquet + per-year tar (the tar bundles the same JSON files as metadata/json/,
# 231 objects instead of ~43,500, so it is much faster). No PDFs (those are Stage 8).
set -euo pipefail
cd "$(dirname "$0")/.."
RAW=${RAW_DIR:-raw}/vanga/metadata
BUCKET=s3://indian-supreme-court-judgments/metadata
mkdir -p "$RAW" logs
for part in parquet tar; do
  aws s3 sync "$BUCKET/$part/" "$RAW/$part/" --no-sign-request --only-show-errors
done
# Unpack each year's tar into json/ so the raw JSON is browsable (skips years already unpacked).
for t in "$RAW"/tar/year=*/metadata.tar; do
  y=$(basename "$(dirname "$t")")
  dest="$RAW/json/$y"
  if [ ! -f "$dest/.unpacked" ]; then
    mkdir -p "$dest" && tar -xf "$t" -C "$dest" && touch "$dest/.unpacked"
  fi
done
echo "vanga download complete: $(find "$RAW" -type f | wc -l) files"
