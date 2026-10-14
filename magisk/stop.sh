#!/system/bin/sh
MODDIR=${0%/*}
BASE=/data/adb/mini-codex
for path in "$BASE" "$BASE/agent.pid" "$BASE/enabled"; do
  [ ! -L "$path" ] || { echo 'Refusing linked private storage.'; exit 1; }
done
RUNTIME=$(/system/bin/readlink -f /data/adb/relaykite-runtime/current 2>/dev/null)
if [ -x "$RUNTIME/native/librelaykite_python.so" ] && [ -f "$BASE/memory-node.json" ]; then
  export PYTHONHOME="$RUNTIME" PYTHONPATH="$RUNTIME/agent" LD_LIBRARY_PATH="$RUNTIME/native" PATH=/system/bin:/system/xbin
  export RELAYKITE_BASE="$BASE" RELAYKITE_MODULE="$MODDIR" RELAYKITE_MODE=root PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
  unset LD_PRELOAD
  "$RUNTIME/native/librelaykite_python.so" "$MODDIR/agent/runtime_control.py" stop || { echo 'Stop outcome requires inspection; retain the original control request.'; exit 1; }
  rm -f "$BASE/enabled"
  exit 0
fi
# Revocation stops future work even when the process is already offline.
rm -f "$BASE/enabled"
pid=$(cat "$BASE/agent.pid" 2>/dev/null)
case "$pid" in ''|*[!0-9]*) exit 0;; esac
command=$(tr '\000' '\n' <"/proc/$pid/cmdline" 2>/dev/null)
case "$command" in
  *"$MODDIR/agent/phone_agent.py"*"$BASE/config.json"*) kill -TERM "$pid" 2>/dev/null;;
  *) echo 'No matching agent process; no process was killed.';;
esac
