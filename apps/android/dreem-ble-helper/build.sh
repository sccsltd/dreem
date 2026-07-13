#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD="$ROOT/build"
ANDROID_JAR="/usr/lib/android-sdk/platforms/android-23/android.jar"
APK="$BUILD/dreem-ble-helper.apk"

rm -rf "$BUILD"
mkdir -p "$BUILD/gen" "$BUILD/obj" "$BUILD/dex"

aapt package -f -m \
  -J "$BUILD/gen" \
  -M "$ROOT/AndroidManifest.xml" \
  -S "$ROOT/res" \
  -I "$ANDROID_JAR"

find "$ROOT/src" "$BUILD/gen" -name '*.java' | sort > "$BUILD/sources.list"
javac --release 8 \
  -classpath "$ANDROID_JAR" \
  -d "$BUILD/obj" \
  @"$BUILD/sources.list"

python3 "$ROOT/strip_method_parameters.py" "$BUILD/obj"
d8 --min-api 23 --lib "$ANDROID_JAR" --output "$BUILD/dex" $(find "$BUILD/obj" -name '*.class' | sort)

aapt package -f \
  -M "$ROOT/AndroidManifest.xml" \
  -S "$ROOT/res" \
  -I "$ANDROID_JAR" \
  -F "$BUILD/unsigned.apk"

(cd "$BUILD/dex" && aapt add "$BUILD/unsigned.apk" classes.dex >/dev/null)
zipalign -f 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk"

if [ ! -f "$ROOT/debug.keystore" ]; then
  keytool -genkeypair \
    -keystore "$ROOT/debug.keystore" \
    -storepass android \
    -keypass android \
    -alias androiddebugkey \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -dname "CN=Android Debug,O=Codex,C=US" >/dev/null
fi

apksigner sign \
  --ks "$ROOT/debug.keystore" \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out "$APK" \
  "$BUILD/aligned.apk"

apksigner verify "$APK"
echo "$APK"
