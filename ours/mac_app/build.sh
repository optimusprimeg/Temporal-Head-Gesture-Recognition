#!/bin/bash
# Builds AirPodsCheck.app next to this script. Needs macOS 14+ and Apple's command line tools
# (run `xcode-select --install` once if `swiftc` is missing).
# UNIVERSAL=1 bash build.sh  -> one app for both Apple Silicon and Intel Macs (used by the GitHub build).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v swiftc >/dev/null 2>&1; then
    echo "swiftc not found. Run:  xcode-select --install   then run this script again."
    exit 1
fi

APP="AirPodsCheck.app"
BIN="$APP/Contents/MacOS/AirPodsCheck"
rm -rf "$APP" build
mkdir -p "$APP/Contents/MacOS" build
if [ "${UNIVERSAL:-0}" = "1" ]; then
    for arch in arm64 x86_64; do
        swiftc -O -parse-as-library -target "$arch-apple-macos14.0" AirPodsCheck.swift -o "build/AirPodsCheck-$arch"
    done
    lipo -create build/AirPodsCheck-arm64 build/AirPodsCheck-x86_64 -output "$BIN"
else
    swiftc -O -parse-as-library -target "$(uname -m)-apple-macos14.0" AirPodsCheck.swift -o "$BIN"
fi
rm -rf build
cp Info.plist "$APP/Contents/Info.plist"
codesign --force --sign - "$APP"   # ad-hoc signature

echo
echo "Built $APP. Start it with:  open $APP"
