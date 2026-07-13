#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD="$ROOT/build"
ANDROID_JAR="/usr/lib/android-sdk/platforms/android-23/android.jar"
JAR="$BUILD/dreem-auth-cli.jar"

rm -rf "$BUILD"
mkdir -p "$BUILD/obj" "$BUILD/dex"

find "$ROOT/src" -name '*.java' | sort > "$BUILD/sources.list"
javac --release 8 \
  -classpath "$ANDROID_JAR" \
  -d "$BUILD/obj" \
  @"$BUILD/sources.list"

python3 "$ROOT/../dreem-ble-helper/strip_method_parameters.py" "$BUILD/obj"

d8 --min-api 23 --lib "$ANDROID_JAR" --output "$BUILD/dex" $(find "$BUILD/obj" -name '*.class' | sort)
(cd "$BUILD/dex" && jar cf "$JAR" classes.dex)

echo "$JAR"
