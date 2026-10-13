#!/usr/bin/env bash
# Resumable (curl -C -). Only the Supreme Court file + central legislation; no High Court files.
# Uses HF_TOKEN if present, otherwise tries anonymously.
set -euo pipefail
RAW="${RAW:-$(dirname "$0")/../raw}"
DEST="$RAW/vaquill"; mkdir -p "$DEST"
B=https://huggingface.co/datasets/vaquill/open-india-law/resolve/main
AUTH=(); [ -n "${HF_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $HF_TOKEN")
for f in SHA256SUMS.json in_central_legislation.parquet in_supreme-court_judgments.parquet; do
  curl -fL --retry 5 --retry-delay 5 -C - "${AUTH[@]}" -o "$DEST/$f" "$B/$f"
done
( cd "$DEST" && sha256sum in_*.parquet SHA256SUMS.json > SHA256_LOCAL.txt )
echo done
