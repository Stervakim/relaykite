#!/system/bin/sh
SKIPMOUNT=true
PROPFILE=false
POSTFSDATA=false
LATESTARTSERVICE=true
DATA=/data/adb/codaki-portable-use
CORE=/data/local/tmp/codaki-portable-core
umask 077
ui_print 'Codaki Portable Use: independent experimental module'
test ! -d "$DATA" || abort 'Existing Portable Use data found. Follow CODEX_INSTALL.md for a reviewed idle upgrade with backup; do not erase owner state.'
test ! -d "$CORE" || abort 'Existing Portable Use core found. Inspect before install.'
PYTHON=
PREFIX=
NATIVE=$(/system/bin/readlink -f /data/adb/relaykite-runtime/current 2>/dev/null)
if test -x "$NATIVE/native/librelaykite_python.so" && PYTHONHOME="$NATIVE" LD_LIBRARY_PATH="$NATIVE/native" "$NATIVE/native/librelaykite_python.so" -c 'import ssl,sqlite3' >/dev/null 2>&1; then
  PYTHON="$NATIVE/native/librelaykite_python.so"
fi
for candidate in /data/data/com.termux/files/usr/bin/python /data/user/0/com.termux/files/usr/bin/python; do
  test -z "$PYTHON" || break
  prefix=${candidate%/bin/python}
  if test -x "$candidate" && LD_LIBRARY_PATH="$prefix/lib" "$candidate" -c 'import sys,ssl,sqlite3; assert sys.version_info >= (3,10)' >/dev/null 2>&1; then
    PYTHON=$candidate
    PREFIX=$prefix
    break
  fi
done
test -n "$PYTHON" || abort 'Install the signed RelayKite runtime APK/root component or supply existing Termux Python. No runtime will be downloaded.'
mkdir -p "$DATA" "$CORE"
mv "$MODPATH/runtime" "$DATA/app" || abort 'Runtime extraction failed'
cp "$MODPATH/core/"*.jar "$CORE/" || abort 'Dex extraction failed'
printf "PYTHON='%s'\nPREFIX='%s'\n" "$PYTHON" "$PREFIX" > "$DATA/runtime.env"
cp "$MODPATH/agent.example.json" "$DATA/agent.example.json"
touch "$DATA/stopped"
set_perm_recursive "$DATA" 0 0 0700 0600
set_perm_recursive "$CORE" 0 0 0700 0600
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/stop.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755
ui_print 'Installed stopped. Configure private agent.json, then explicitly start.'
