#!/usr/bin/env bash
# Download all missing video_footage MP4s, then manual English subtitles for gaps.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO_LOG="${ROOT}/catalog/logs/download-video-sections2-6.log"
SUBS_LOG="${ROOT}/catalog/logs/download-subtitles-sections2-6.log"

cd "$ROOT"
mkdir -p "$(dirname "$VIDEO_LOG")"

{
  echo ""
  echo "========== ALL REMAINING VIDEO $(date -u +%Y-%m-%dT%H:%M:%SZ) =========="
  python3 scripts/download_missing_video.py --cookies-from-browser chrome
  echo ""
  echo "========== VIDEO BATCH DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) =========="
} >>"$VIDEO_LOG" 2>&1

{
  echo ""
  echo "========== MISSING SUBTITLES $(date -u +%Y-%m-%dT%H:%M:%SZ) =========="
  python3 scripts/download_missing_subtitles.py --cookies-from-browser chrome
  echo ""
  echo "========== SUBTITLES DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) =========="
} >>"$SUBS_LOG" 2>&1