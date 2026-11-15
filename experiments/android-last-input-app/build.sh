#!/bin/bash
set -e
cd "$(dirname "$0")"
J=/usr/lib/android-sdk/platforms/android-23/android.jar
rm -rf out lastinput.apk && mkdir -p out/classes
javac --release 8 -nowarn -cp $J -d out/classes src/local/lastinput/*.java 2>&1 | grep -v warning || true
dalvik-exchange --dex --output=out/classes.dex out/classes
aapt package -f -M AndroidManifest.xml -S res -I $J -F out/unsigned.apk
(cd out && aapt add unsigned.apk classes.dex >/dev/null)
apksigner sign --ks ../../ks.jks --ks-pass pass:lastinput --out lastinput.apk out/unsigned.apk
