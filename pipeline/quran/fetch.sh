#!/usr/bin/env bash
# Downloads the Qur'an text that check.py uses to verify verse references (one-time, ~1.3 MB).
# Source: Tanzil Quran Text (https://tanzil.net), "Simple Clean", one verse per line as sura|aya|text.
# License: Creative Commons Attribution 3.0; verbatim copies only, keep the license notes at the end of the file.
set -euo pipefail
cd "$(dirname "$0")"
URL='https://tanzil.net/pub/download/index.php?quranType=simple-clean&outType=txt-2&agree=true'
curl -fsSL "$URL" -o quran-simple-clean.txt.part
verses=$(grep -c '^[0-9]*|[0-9]*|' quran-simple-clean.txt.part || true)
if [ "$verses" != 6236 ]; then
  echo "unexpected download: $verses verses instead of 6236; nothing installed" >&2
  rm -f quran-simple-clean.txt.part
  exit 1
fi
mv quran-simple-clean.txt.part quran-simple-clean.txt
echo "installed $(pwd)/quran-simple-clean.txt (6236 verses)"
