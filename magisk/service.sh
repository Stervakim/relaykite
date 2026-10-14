#!/system/bin/sh
MODDIR=${0%/*}
BASE=/data/adb/mini-codex
PREFIX=/data/data/com.termux/files/usr
# Embedded runtime takes priority once the original private memory migration
# has committed, or on a fresh APK-first installation. Legacy upgrades keep
# their old worker until the verified migration has supplied memory-node.json.
RUNTIME=$(/system/bin/readlink -f /data/adb/relaykite-runtime/current 2>/dev/null)
APP=/data/data/org.relaykite.runtime/files/owner
if [ -x "$RUNTIME/native/librelaykite_python.so" ] && { [ -f "$BASE/memory-node.json" ] || [ ! -f "$BASE/config.json" ]; }; then
  (
    while [ "$(/system/bin/getprop sys.boot_completed)" != 1 ]; do
      [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
      sleep 2
    done
    while [ ! -f "$BASE/enabled" ]; do
      [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
      if [ -f "$APP/enabled" ] && [ -f "$APP/config.json" ]; then
        mkdir -p "$BASE/state"; chmod 0700 "$BASE" "$BASE/state"; touch "$BASE/enabled"; chmod 0600 "$BASE/enabled"; break
      fi
      sleep 5
    done
    export PYTHONHOME="$RUNTIME" LD_LIBRARY_PATH="$RUNTIME/native" PYTHONPATH="$RUNTIME/agent" RELAYKITE_NATIVE="$RUNTIME/native"
    export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 RELAYKITE_BASE="$BASE" RELAYKITE_MODULE="$MODDIR" RELAYKITE_MODE=root
    export SSL_CERT_FILE="$RUNTIME/etc/tls/cert.pem" HOME="$BASE" TMPDIR="$BASE/state" PATH=/system/bin:/system/xbin
    unset LD_PRELOAD
    umask 077
    while [ -f "$BASE/enabled" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ]; do
      if [ -f "$BASE/state/runtime-supervisor.log" ] && [ "$(/system/bin/stat -c %s "$BASE/state/runtime-supervisor.log")" -gt 1048576 ]; then
        /system/bin/mv -f "$BASE/state/runtime-supervisor.log" "$BASE/state/runtime-supervisor.previous.log"
      fi
      "$RUNTIME/native/librelaykite_python.so" "$RUNTIME/agent/root_supervisor.py" </dev/null >>"$BASE/state/runtime-supervisor.log" 2>&1
      sleep 5
    done
  ) &
  exit 0
fi
# Magisk late_start service: no PC, no second runtime, no public root listener.
# Start a background supervisor without blocking Android startup.
(
  attempts=0
  while [ "$(/system/bin/getprop sys.boot_completed)" != 1 ] || [ ! -x "$PREFIX/bin/python" ]; do
    [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    attempts=$((attempts + 1))
    [ "$attempts" -lt 180 ] || exit 0
    sleep 2
  done
  export PREFIX PATH="$PREFIX/bin:/system/bin:/system/xbin" LD_LIBRARY_PATH="$PREFIX/lib"
  if [ -f "$PREFIX/etc/tls/cert.pem" ]; then export SSL_CERT_FILE="$PREFIX/etc/tls/cert.pem"; fi
  export PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 HOME="$BASE"
  umask 077
  # Legacy installations may have credentials but no enabled marker.
  # Do not auto-enable here: explicit migration is needed to preserve consent.
  [ -f "$BASE/enabled" ] || exit 0
  # Validate before running and retain original owner credentials/memory/journal.
  "$PREFIX/bin/python" "$MODDIR/agent/configure.py" --validate >/dev/null 2>&1 || exit 0
  "$PREFIX/bin/python" "$MODDIR/agent/support_runtime.py" refresh >/dev/null 2>&1 || :
  memory_child=
  start_memory() {
    if [ -f "$BASE/memory-service.json" ] && { [ -z "$memory_child" ] || ! kill -0 "$memory_child" 2>/dev/null; }; then
      [ -z "$memory_child" ] || wait "$memory_child" 2>/dev/null || :
      "$PREFIX/bin/python" "$MODDIR/agent/memory_service.py" </dev/null >/dev/null 2>&1 &
      memory_child=$!
    fi
  }
  while [ -f "$BASE/enabled" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ]; do
    start_memory
    memory_tick=0
    # The Python worker holds a nonblocking flock; concurrent supervisors
    # cannot execute a second job worker or duplicate root actions.
    "$PREFIX/bin/python" "$MODDIR/agent/phone_agent.py" --config "$BASE/config.json" >"$BASE/startup.log" 2>&1 &
    child=$!
    while kill -0 "$child" 2>/dev/null; do
      if [ ! -f "$BASE/enabled" ] || [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; then
        kill -TERM "$child" 2>/dev/null
        wait "$child" 2>/dev/null
        exit 0
      fi
      memory_tick=$((memory_tick + 1))
      if [ "$memory_tick" -ge 5 ]; then start_memory; memory_tick=0; fi
      sleep 3
    done
    wait "$child" 2>/dev/null || :
    # Crash recovery (including transient Termux/network faults), bounded
    # backoff. No phone UI, VPN routing or VLESS subscriptions are modified.
    [ -f "$BASE/enabled" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    sleep 15
  done
) &
