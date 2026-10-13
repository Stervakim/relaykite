#!/system/bin/sh
# Installed package bytes must match the release's signed-APK digest. Bootstrap
# uses PackageManager's nativeLibDir and Android unzip, with no Termux runtime.
set -eu
unset LD_LIBRARY_PATH LD_PRELOAD
MODDIR=${1:-${0%/*}}
BASE=/data/adb/relaykite-runtime
APK=$(/system/bin/pm path org.relaykite.runtime | /system/bin/head -n 1)
APK=${APK#package:}
[ -f "$APK" ] || { echo 'Install the matching RelayKite APK first.'; exit 1; }
expected=$(cat "$MODDIR/agent/runtime-apk.sha256")
case "$expected" in ''|*[!0-9a-f]*) echo 'Invalid pinned APK digest.'; exit 1;; esac
[ "${#expected}" = 64 ] || exit 1
sum=$(/system/bin/sha256sum "$APK")
actual=${sum%% *}
[ "$actual" = "$expected" ] || { echo 'Installed APK does not match this root component.'; exit 1; }
native=${APK%/*}/lib/arm64
[ -x "$native/librelaykite_python.so" ] || { echo 'Android arm64 native runtime is unavailable.'; exit 1; }
for path in /data/adb "$BASE" "$BASE/versions"; do [ ! -L "$path" ] || exit 1; done
mkdir -p "$BASE/versions"
chmod 0700 "$BASE" "$BASE/versions"
temp=$(/system/bin/mktemp -d "$BASE/bootstrap-XXXXXXXX")
cleanup() {
  case "$temp" in "$BASE"/bootstrap-????????)
    [ ! -L "$temp" ] && [ -d "$temp" ] || return 0
    # Default find does not follow module symlinks into nativeLibraryDir.
    /system/bin/find "$temp" -xdev -depth -delete >/dev/null
  ;; *) return 1;; esac
}
trap cleanup EXIT
# temp is a verified root-owned mktemp child of the fixed installation root.
/system/bin/unzip -p "$APK" assets/runtime.zip > "$temp/runtime.zip"
mkdir "$temp/prefix"
/system/bin/unzip -q "$temp/runtime.zip" -d "$temp/prefix"
export PYTHONHOME="$temp/prefix" LD_LIBRARY_PATH="$native" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=
unset LD_PRELOAD
"$native/librelaykite_python.so" "$MODDIR/agent/bootstrap_native.py" "$temp/prefix" "$native"
"$native/librelaykite_python.so" "$MODDIR/agent/install_embedded_runtime.py" --apk "$APK" --expected-sha256 "$expected" --base "$BASE/versions"
next="$BASE/.current-$$"
[ ! -e "$next" ] && [ ! -L "$next" ] || exit 1
/system/bin/ln -s "versions/$expected" "$next"
"$native/librelaykite_python.so" "$MODDIR/agent/bootstrap_native.py" --activate "$next" "$BASE/current"
echo 'Verified embedded root runtime installed.'
