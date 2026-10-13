#!/usr/bin/env bash
# Idempotent: sync is resumable. Anonymous access, no AWS account needed.
set -euo pipefail
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=ap-south-1
RAW="${RAW:-$(dirname "$0")/../raw}"
mkdir -p "$RAW/vanga/metadata"
aws s3 sync s3://indian-supreme-court-judgments/metadata/ "$RAW/vanga/metadata" --no-sign-request
