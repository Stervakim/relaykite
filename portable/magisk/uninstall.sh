#!/system/bin/sh
/system/bin/sh /data/adb/modules/codaki_portable_use/stop.sh
# Keep configuration, journal and outbox for recovery. Only Magisk removes its module.
# To erase these private files, the owner must explicitly choose that separate operation.
