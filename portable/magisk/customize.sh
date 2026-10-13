#!/system/bin/sh
SKIPMOUNT=true
PROPFILE=false
POSTFSDATA=false
LATESTARTSERVICE=true
DATA=/data/adb/codaki-portable-use
CORE=/data/local/tmp/codaki-portable-core
umask 077
ui_print 'Codaki Portable Use: independent experimental module'
test ! -d "$DATA" || abort 'Existing Portable Use data found. Upgrade with scripts/install_android.py to preserve rollback.'
test ! -d "$CORE" || abort 'Existing Portable Use core found. Inspect before install.'
PYTHON=
for candidate in /data/data/com.termux/files/usr/bin/python /data/user/0/com.termux/files/usr/bin/python; do
  prefix=${candidate%/bin/python}
  if test -x "$candidate" && LD_LIBRARY_PATH="$prefix/lib" "$candidate" -c 'import sys,ssl,sqlite3; assert sys.version_info >= (3,10)' >/dev/null 2>&1; then
    PYTHON=$candidate
    PREFIX=$prefix
    break
  fi
done
test -n "$PYTHON" || abort 'Existing Termux Python 3.10+ with ssl/sqlite3 is required. No runtime will be downloaded.'
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
