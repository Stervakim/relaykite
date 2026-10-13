#!/system/bin/sh
DATA=/data/adb/codaki-portable-use
CORE=/data/local/tmp/codaki-portable-core
MODULE=/data/adb/modules/codaki_portable_use
umask 077
if test -f "$DATA/service.pid"; then
  prior=$(cat "$DATA/service.pid")
  case "$prior" in ''|*[!0-9]*) exit 1;; esac
  if test -r "/proc/$prior/cmdline"; then
    cmd=$(tr '\000' ' ' < "/proc/$prior/cmdline")
    case "$cmd" in *'/data/adb/modules/codaki_portable_use/service.sh'*) exit 0;; esac
  fi
fi
if test "$1" != --foreground; then
  nohup /system/bin/sh "$MODULE/service.sh" --foreground >/dev/null 2>&1 </dev/null &
  exit 0
fi
test -f "$DATA/runtime.env" || exit 0
test ! -f "$MODULE/disable" || exit 0
test ! -f "$DATA/stopped" || exit 0
. "$DATA/runtime.env"
export PATH="$PREFIX/bin:/system/bin:/system/xbin"
export LD_LIBRARY_PATH="$PREFIX/lib"
export HOME="$DATA" TMPDIR="$CORE" PYTHONPATH="$DATA/app" PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
mkdir -p "$DATA/state" "$CORE"
echo $$ > "$DATA/service.pid"
child=
finish() {
  test -z "$child" || kill -TERM "$child" 2>/dev/null
  test -z "$child" || wait "$child" 2>/dev/null
  rm -f "$DATA/service.pid"
  exit 0
}
trap finish TERM INT
while test ! -f "$MODULE/disable" && test ! -f "$MODULE/remove" && test ! -f "$DATA/stopped"; do
  cd "$DATA/app" || exit 1
  # Bound logs between starts. Local state intentionally survives upgrades.
  test ! -f "$DATA/agent.log" || mv "$DATA/agent.log" "$DATA/agent.previous.log"
  if test -f "$DATA/agent.json"; then
    "$PYTHON" -m portable agent --platform android --config "$DATA/agent.json" --state "$DATA/state" --local-ipc >> "$DATA/agent.log" 2>&1 &
  else
    "$PYTHON" -m portable local --platform android --state "$DATA/state" --local-ipc >> "$DATA/agent.log" 2>&1 &
  fi
  child=$!
  echo "$child" > "$DATA/agent.pid"
  wait "$child"
  child=
  rm -f "$DATA/agent.pid"
  sleep 5 &
  child=$!
  wait "$child"
  child=
done
finish
