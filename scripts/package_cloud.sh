#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
artifact_dir="$project_root/build/cloud"
artifact_path="$artifact_dir/hr-screening-bot-function.zip"

mkdir -p "$artifact_dir"
rm -f "$artifact_path"

cd "$project_root"
zip -qr "$artifact_path" app function_handler.py requirements.txt \
  -x '*/__pycache__/*' '*.pyc'

printf '%s\n' "$artifact_path"
