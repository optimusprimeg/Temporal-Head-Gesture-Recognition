#!/bin/bash
# Builds the iPhone app (iOS 16+) as an UNSIGNED GestureCollector-iOS.ipa next to this script. Same sources as the
# Mac app. Needs a Mac with Xcode (the GitHub build does this). To install it on an iPhone, sign it with your own
# Apple ID: Sideloadly (Windows or Mac) or Xcode; see PILOT_GUIDE.md. A free Apple ID install lasts 7 days.
set -euo pipefail
cd "$(dirname "$0")"

SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
APP="build_ios/Payload/GestureCollector.app"
rm -rf build_ios GestureCollector-iOS.ipa
mkdir -p "$APP"
xcrun --sdk iphoneos swiftc -O -parse-as-library -target arm64-apple-ios16.0 -sdk "$SDK" \
    Sources/*.swift -o "$APP/GestureCollector"
cp Info-iOS.plist "$APP/Info.plist"
cp live_model.json "$APP/live_model.json"      # built-in live recogniser model
[ -f forest_model.json ] && cp forest_model.json "$APP/forest_model.json"   # built-in Forest mode model
mkdir -p "$APP/experiments/media"               # v3.4: shipped experiments + demo clips
cp ../experiments/*.json "$APP/experiments/"
cp ../experiments/media/*.gif "$APP/experiments/media/"
printf 'APPL????' > "$APP/PkgInfo"
(cd build_ios && zip -qry ../GestureCollector-iOS.ipa Payload)
rm -rf build_ios
echo "Built GestureCollector-iOS.ipa (unsigned)"
