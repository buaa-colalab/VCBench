#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIDEO_DIR="${VIDEO_DIR:-data/videos}"
INPUT_JSONL="${INPUT_JSONL:-data/vcbench_eval.jsonl}"
LIMIT="${LIMIT:-5}"
MODEL="${MODEL:-gemini-3-flash-preview}"
FPS="${FPS:-1}"

usage() {
  cat <<'EOF'
Usage:
  bash run_gemini_eval.sh [--video-dir PATH] [--input PATH] [--limit N] [--model NAME] [--fps N]

Environment variables with the same names are also supported:
  VIDEO_DIR, INPUT_JSONL, LIMIT, MODEL, FPS, GEMINI_API_KEY
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --video-dir)
      VIDEO_DIR="$2"
      shift 2
      ;;
    --input)
      INPUT_JSONL="$2"
      shift 2
      ;;
    --limit)
      LIMIT="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --fps)
      FPS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "Set GEMINI_API_KEY before running this script." >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/outputs"
TS="$(date +%Y%m%d_%H%M%S)"
RAW_OUTPUT="$ROOT_DIR/outputs/vcbench_gemini_demo_${TS}.jsonl"
UNIFIED_OUTPUT="$ROOT_DIR/outputs/vcbench_gemini_demo_${TS}_unified.jsonl"

cd "$ROOT_DIR"

python eval/demo_gemini.py \
  --video-dir "$VIDEO_DIR" \
  --input "$INPUT_JSONL" \
  --limit "$LIMIT" \
  --model "$MODEL" \
  --fps "$FPS" \
  --output "$RAW_OUTPUT"

python eval/unify_results.py "$RAW_OUTPUT" "$UNIFIED_OUTPUT"
python eval/compute_metrics.py "$UNIFIED_OUTPUT" "$INPUT_JSONL"

echo "Raw output: $RAW_OUTPUT"
echo "Unified output: $UNIFIED_OUTPUT"
