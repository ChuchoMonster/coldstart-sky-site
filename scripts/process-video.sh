#!/usr/bin/env bash
# Make each raw Seedance sky loop seamless, encode mp4+webm within budget,
# and extract a poster frame. Raw 10s input -> ~8.5s seamless loop:
# the final 1.5s is crossfaded onto the head, so end frame == start frame.
#
# Budgets: mp4 <=2.5MB, webm <=1.6MB, poster <=80KB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/assets-src/raw"
OUT="$ROOT/site/assets/sky"
mkdir -p "$OUT"

XFADE=1.5

for raw in "$RAW"/*.mp4; do
  id="$(basename "$raw" .mp4)"
  [[ "$id" == *-ref ]] && continue

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$raw")
  main_end=$(python3 -c "print(round($dur - $XFADE, 3))")
  loop="/tmp/${id}-loop.mp4"

  echo "[$id] crossfade-loop (${dur}s -> ${main_end}s seamless)"
  ffmpeg -y -v error -i "$raw" -filter_complex \
    "[0:v]split[a][b];\
     [a]trim=0:${main_end},setpts=PTS-STARTPTS[main];\
     [b]trim=${main_end}:${dur},setpts=PTS-STARTPTS[tail];\
     [tail][main]xfade=transition=fade:duration=${XFADE}:offset=0[v]" \
    -map "[v]" -an -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p "$loop"

  echo "[$id] encode mp4"
  ffmpeg -y -v error -i "$loop" -an -c:v libx264 -preset slow -crf 24 \
    -maxrate 2.5M -bufsize 5M -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080" \
    -pix_fmt yuv420p -movflags +faststart "$OUT/${id}.mp4"

  echo "[$id] encode webm"
  ffmpeg -y -v error -i "$loop" -an -c:v libvpx-vp9 -crf 36 -b:v 0 -row-mt 1 \
    -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080" "$OUT/${id}.webm"

  echo "[$id] poster"
  ffmpeg -y -v error -ss 4 -i "$loop" -frames:v 1 \
    -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080" -q:v 6 "$OUT/${id}.jpg"

  mp4_kb=$(du -k "$OUT/${id}.mp4" | cut -f1)
  webm_kb=$(du -k "$OUT/${id}.webm" | cut -f1)
  jpg_kb=$(du -k "$OUT/${id}.jpg" | cut -f1)
  echo "[$id] mp4=${mp4_kb}KB webm=${webm_kb}KB poster=${jpg_kb}KB"
  (( mp4_kb > 2560 )) && echo "  WARN: mp4 over 2.5MB budget"
  (( webm_kb > 1638 )) && echo "  WARN: webm over 1.6MB budget"
  (( jpg_kb > 80 )) && echo "  WARN: poster over 80KB budget"
done

echo "All bands processed into $OUT"
