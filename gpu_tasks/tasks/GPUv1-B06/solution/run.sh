#!/usr/bin/env bash
set -euo pipefail
# GPUv1-B06 convenience wrapper. Executes doctor then a single run/resume.
HERE="$(cd "$(dirname "$0")/.." && pwd)"
INPUT="${INPUT:-$HERE/input}"
OUTPUT="${OUTPUT:-$HERE/output}"
ACTION="${ACTION:-run}"
python "$HERE/solution/main.py" doctor --input "$INPUT"
python "$HERE/solution/main.py" "$ACTION" --input "$INPUT" --output "$OUTPUT"
