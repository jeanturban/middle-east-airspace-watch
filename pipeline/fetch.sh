#!/usr/bin/env bash
# Download a day's split tar to disk, resuming broken transfers, and check every part is complete.
#   pipeline/fetch.sh DIR URL [URL...]
# Exits non-zero if any part can't be fetched in full. Streaming straight into process_day.py
# was fragile: when GitHub dropped a connection mid-file, the stream silently lost its middle and
# a partial day was saved as if it were complete.
set -euo pipefail
dir=$1; shift
mkdir -p "$dir"
for url in "$@"; do
  out="$dir/$(basename "$url")"
  size=""
  for attempt in 1 2 3 4 5 6 7 8; do
    if [ -z "$size" ]; then
      size=$(curl -sSfIL --retry 3 --retry-delay 10 "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:"{n=$2} END{print n}') || size=""
    fi
    have=$(stat -c %s "$out" 2>/dev/null || echo 0)
    if [ -n "$size" ] && [ "$have" = "$size" ]; then break; fi
    echo "fetch $(basename "$url"): attempt $attempt, have $have of ${size:-?} bytes" >&2
    # resume from what is on disk; if resuming keeps failing, start the part over
    [ "$attempt" -ge 5 ] && rm -f "$out"
    curl -sSfL -C - --retry 3 --retry-delay 20 -o "$out" "$url" || sleep $((attempt * 30))
  done
  have=$(stat -c %s "$out" 2>/dev/null || echo 0)
  if [ -z "$size" ] || [ "$have" != "$size" ]; then
    echo "fetch $(basename "$url"): incomplete ($have of ${size:-unknown} bytes), giving up" >&2
    exit 1
  fi
  echo "fetch $(basename "$url"): ok, $size bytes" >&2
done
