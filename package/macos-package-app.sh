#!/usr/bin/env bash
# Inspired by https://github.com/metabrainz/picard/blob/master/scripts/package/macos-notarize-app.sh
#
# Signs and packages Vorta.app. A Developer ID certificate is used when one is
# available (CERTIFICATE_NAME set to an identity present in the keychain), and
# the DMG is notarized when Apple ID credentials are provided as well. Without a
# certificate the app is ad-hoc signed, which is enough to run locally once the
# quarantine attribute is removed:
#   xattr -dr com.apple.quarantine /Applications/Vorta.app

set -eux

APP_BUNDLE="Vorta"

SIGN_IDENTITY="-"
NOTARIZE=0

if [ -n "${CERTIFICATE_NAME:-}" ] &&
    security find-identity -v -p codesigning | grep -qF "$CERTIFICATE_NAME"; then
    SIGN_IDENTITY="$CERTIFICATE_NAME"
    if [ -n "${APPLE_ID_USER:-}" ] && [ -n "${APPLE_ID_PASSWORD:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ]; then
        NOTARIZE=1
    fi
    echo "Signing with '$CERTIFICATE_NAME' (notarize=$NOTARIZE)"
else
    echo "No code signing certificate available; using ad-hoc signing."
fi

# Ad-hoc signatures cannot carry a secure timestamp, so only add --timestamp
# when signing with a real identity.
codesign_cmd() {
    if [ "$SIGN_IDENTITY" = "-" ]; then
        codesign "$@"
    else
        codesign --timestamp "$@"
    fi
}

# Sign app bundle, Sparkle and Borg
codesign_cmd --verbose --force --sign "$SIGN_IDENTITY" --deep --options runtime \
    "$APP_BUNDLE.app/Contents/Frameworks/Sparkle.framework"

find "$APP_BUNDLE.app/Contents/Resources/borg-dir" \
    -type f \( -name \*.so -or -name \*.dylib -or -name borg.exe -or -name Python \) |
    while IFS= read -r file; do
        codesign_cmd --verbose --force --deep --sign "$SIGN_IDENTITY" \
            --entitlements ../package/entitlements.plist --options runtime "$file"
    done

codesign_cmd --verify --force --verbose --deep \
        --options runtime \
        --entitlements ../package/entitlements.plist \
        --sign "$SIGN_IDENTITY" "$APP_BUNDLE.app"


# Create DMG
rm -rf "$APP_BUNDLE.dmg"
create-dmg \
  --volname "Vorta Installer" \
  --filesystem APFS \
  --window-size 410 300 \
  --icon-size 100 \
  --icon "Vorta.app" 70 150 \
  --hide-extension "Vorta.app" \
  --app-drop-link 240 150 \
  "Vorta.dmg" \
  "Vorta.app"

# Notarize and staple only when a Developer ID identity and Apple ID credentials
# are available.
if [ "$NOTARIZE" = "1" ]; then
    xcrun notarytool submit \
        --output-format plist --wait --timeout 10m \
        --apple-id "$APPLE_ID_USER" \
        --password "$APPLE_ID_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        "$APP_BUNDLE.dmg"

    xcrun stapler staple "$APP_BUNDLE.dmg"
    xcrun stapler staple "$APP_BUNDLE.app"
    xcrun stapler validate "$APP_BUNDLE.dmg"
fi
