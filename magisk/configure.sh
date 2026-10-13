#!/system/bin/sh
MODDIR=${0%/*}
PREFIX=/data/data/com.termux/files/usr
RUNTIME=$(/system/bin/readlink -f /data/adb/relaykite-runtime/current 2>/dev/null)
if [ -x "$RUNTIME/native/librelaykite_python.so" ]; then
  [ -f /data/adb/mini-codex/memory-node.json ] || { echo 'Import your connection in the RelayKite APK first, then select a root mode there.'; exit 1; }
  export PYTHONHOME="$RUNTIME" PYTHONPATH="$RUNTIME/agent" LD_LIBRARY_PATH="$RUNTIME/native" RELAYKITE_NATIVE="$RUNTIME/native"
  export RELAYKITE_BASE=/data/adb/mini-codex RELAYKITE_MODULE="$MODDIR" RELAYKITE_MODE=root PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
  export SSL_CERT_FILE="$RUNTIME/etc/tls/cert.pem" PATH=/system/bin:/system/xbin
  unset LD_PRELOAD
  exec "$RUNTIME/native/librelaykite_python.so" "$RUNTIME/agent/configure.py" "$@"
fi
[ -x "$PREFIX/bin/python" ] || { echo 'Install official Termux Python first.'; exit 1; }
export PREFIX
export PATH="$PREFIX/bin:/system/bin:/system/xbin"
export LD_LIBRARY_PATH="$PREFIX/lib"
if [ -f "$PREFIX/etc/tls/cert.pem" ]; then export SSL_CERT_FILE="$PREFIX/etc/tls/cert.pem"; fi
# Python getpass reads secrets from the terminal with echo disabled, never argv.
exec "$PREFIX/bin/python" "$MODDIR/agent/configure.py" "$@"
