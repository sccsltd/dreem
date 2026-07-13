#!/system/bin/sh
set -eu

SRC=/data/local/tmp/dreem-ble-helper-privileged-module
APK=/data/local/tmp/dreem-ble-helper.apk
MOD=/data/adb/modules/dreemble_priv

echo "uid=$(id)"
ls -ld /data /data/adb /data/adb/modules /data/local/tmp
ls -l "$APK"
find "$SRC" -maxdepth 5 -type f -print

rm -rf "$MOD"
mkdir -p "$MOD"
cp -a "$SRC"/. "$MOD"/
mkdir -p "$MOD"/system/priv-app/DreemBleHelper
mkdir -p "$MOD"/system/etc/permissions
cp "$APK" "$MOD"/system/priv-app/DreemBleHelper/dreem-ble-helper.apk

chmod -R 755 "$MOD"
chmod 644 "$MOD"/module.prop
chmod 644 "$MOD"/system/etc/permissions/privapp-permissions-dreemble.xml
chmod 644 "$MOD"/system/priv-app/DreemBleHelper/dreem-ble-helper.apk
chown -R root:root "$MOD"

echo "installed:"
find "$MOD" -maxdepth 5 -type f -ls
