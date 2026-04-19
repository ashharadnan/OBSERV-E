#!/usr/bin/env bash
set -euo pipefail

MODEL_ID="${1:-google/gemma-4-E2B-it}"
MODEL_DIR="${2:-models/gemma-4-E2B-it}"

python -m pip install -U pip
python -m pip install -r requirements.txt

if ! command -v hf >/dev/null 2>&1; then
  echo "Hugging Face CLI not found after install. Activate the VLM_Environment venv first." >&2
  exit 1
fi

mkdir -p "$(dirname "$MODEL_DIR")"
echo "If prompted, accept the Gemma model terms in your browser first."
echo "Run: hf auth login"
hf auth login
hf download "$MODEL_ID" --local-dir "$MODEL_DIR"

echo "Gemma model downloaded to $MODEL_DIR"
