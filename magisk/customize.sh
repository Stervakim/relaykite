#!/system/bin/sh
# Sourced by Magisk's module installer on a running Android system.
[ "$BOOTMODE" = true ] || abort 'Install on booted Android with the Magisk app or supported CLI, not recovery.'
BASE=/data/adb/mini-codex
for path in /data /data/adb "$BASE" "$BASE/config.json" "$BASE/enabled" "$BASE/state" "$BASE/memory"; do
  [ ! -L "$path" ] || abort 'Private storage must not contain symbolic links.'
done
[ ! -e "$BASE" ] || [ -d "$BASE" ] || abort 'Private storage is not a directory.'
mkdir -p "$BASE" || abort 'Cannot create private storage.'
chmod 0700 "$BASE"
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in service.sh stop.sh uninstall.sh configure.sh install-runtime.sh; do
  set_perm "$MODPATH/$script" 0 0 0755
done
"/system/bin/sh" "$MODPATH/install-runtime.sh" "$MODPATH" || abort 'Install the matching signed RelayKite APK before installing this root component.'
# Existing config, enabled marker, memory and journal remain intact on upgrades.
# No credentials or enabled marker are supplied by this ZIP.
ui_print 'RelayKite installed. Import your OWN connection in the matching APK and select a mode.'
ui_print 'Existing Termux installations require the verified private migration before switching.'
