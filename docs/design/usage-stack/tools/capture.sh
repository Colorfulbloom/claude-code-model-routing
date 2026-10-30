#!/bin/zsh
# usage: capture.sh <dir> [pattern]   -> <dir>/shots/<name>-<width>.png ; prints "<name> <width> x <height> overflow=<0|1>"
# exits 1 if any page overflowed horizontally (scrollWidth > clientWidth), which the page script reports as data-ox.
# Serve this design folder (the one holding a-usage/ and tools/) first, from the repo root:
#   python3 -m http.server 8732 --bind 127.0.0.1 --directory docs/design/usage-stack
# <dir> is a folder under it, such as a-usage. Override the port with PORT=<n>, Chrome with CHROME=<path>.
CH="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
S="${0:A:h:h}"   # docs/design/usage-stack, found from this script's location
PORT="${PORT:-8732}"
D="${1:A}"; P="${2:-*}"
mkdir -p "$D/shots"
setopt glob_subst
fail=0
probe() { "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=$1 --virtual-time-budget=$2 --dump-dom "$3" 2>/dev/null | grep -o 'data-h="[0-9]*"\|data-ox="[0-9]"' | head -2 | tr '\n' ' '; }
for f in $D/${~P}.html; do
  n=$(basename "$f" .html)
  u="http://127.0.0.1:$PORT/${f#$S/}"
  r=$(probe 1440,900 1500 "$u"); h=$(echo "$r" | grep -o 'data-h="[0-9]*"' | grep -o '[0-9]*'); ox=$(echo "$r" | grep -o 'data-ox="[0-9]"' | grep -o '[0-9]')
  [ -z "$h" ] && h=1200; [ "$h" -gt 8000 ] && h=8000; [ -z "$ox" ] && ox=?
  "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,${h} --virtual-time-budget=1500 --screenshot="$D/shots/${n}-1440.png" "$u" >/dev/null 2>&1
  echo "$n 1440 x $h overflow=$ox"; [ "$ox" = "1" ] && fail=1
  rel="${f#$S/}"; u="http://127.0.0.1:$PORT/tools/host.html?p=/$rel"
  r=$(probe 1001,900 2500 "$u"); h=$(echo "$r" | grep -o 'data-h="[0-9]*"' | grep -o '[0-9]*'); ox=$(echo "$r" | grep -o 'data-ox="[0-9]"' | grep -o '[0-9]')
  [ -z "$h" ] && h=2000; [ "$h" -gt 8000 ] && h=8000; [ -z "$ox" ] && ox=?
  "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=1001,${h} --virtual-time-budget=2500 --screenshot="$D/shots/${n}-375.png" "$u" >/dev/null 2>&1
  sips -c $h 375 "$D/shots/${n}-375.png" >/dev/null 2>&1
  echo "$n 375 x $h overflow=$ox"; [ "$ox" = "1" ] && fail=1
done
[ $fail = 1 ] && echo "FAIL: horizontal overflow" && exit 1
echo "all captured, no overflow"
