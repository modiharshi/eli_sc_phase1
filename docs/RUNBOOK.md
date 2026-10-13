# Runbook

## Setup
```
uv sync                      # Python deps into .venv
```

## Stage 1: download Vanga metadata (resumable)
```
pipeline/01_download_vanga.sh          # needs aws CLI; anonymous, no credentials
```
New years appear in the bucket twice a month; re-running picks them up.

## Stage 2: profile
```
.venv/bin/python pipeline/02_profile_vanga.py
```
Writes `docs/manifests/` and `docs/profile/`. Re-runnable.

## Vaquill
Place `in_supreme-court_judgments.parquet`, `in_central_legislation.parquet` and `SHA256SUMS.json` in `raw/vaquill/`, or set `HF_TOKEN` as a secret with `huggingface.co` allowed in network settings.
