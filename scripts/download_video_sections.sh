#!/usr/bin/env bash
# Download section video footage; continues through all sections even if one fails.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${ROOT}/catalog/logs/download-video-section1.log"
SECTIONS=(1A 1B 1C 1D 1E)

cd "$ROOT"
mkdir -p "$(dirname "$LOG")"

for sec in "${SECTIONS[@]}"; do
  {
    echo ""
    echo "========== Section ${sec} $(date -u +%Y-%m-%dT%H:%M:%SZ) =========="
    python3 scripts/download_section.py "${sec}" --video --no-subs --cookies-from-browser chrome
  } >>"$LOG" 2>&1 || true
done

{
  echo ""
  echo "========== Batch done $(date -u +%Y-%m-%dT%H:%M:%SZ) =========="
} >>"$LOG" 2>&1