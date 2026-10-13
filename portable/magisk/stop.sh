#!/system/bin/sh
DATA=/data/adb/codaki-portable-use
umask 077
mkdir -p "$DATA"
touch "$DATA/stopped"
for record in service agent; do
  test -f "$DATA/$record.pid" || continue
  pid=$(cat "$DATA/$record.pid")
  case "$pid" in ''|*[!0-9]*) echo 'Invalid owned PID record' >&2; exit 1;; esac
  test -r "/proc/$pid/cmdline" || continue
  cmd=$(tr '\000' ' ' < "/proc/$pid/cmdline")
  case "$record:$cmd" in
    service:*'/data/adb/modules/codaki_portable_use/service.sh'*) kill -TERM "$pid";;
    agent:*' -m portable agent '*'--state /data/adb/codaki-portable-use/state'*) kill -TERM "$pid";;
    agent:*' -m portable local '*'--state /data/adb/codaki-portable-use/state'*) kill -TERM "$pid";;
    *) echo 'PID ownership could not be verified; refusing signal' >&2; exit 1;;
  esac
done
# A graceful agent exit closes its display. Java independently enforces the lease.
