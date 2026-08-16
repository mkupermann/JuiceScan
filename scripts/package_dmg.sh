#!/usr/bin/env bash
# Baut die macOS-DMG mit nativem .pkg-Installer: Doppelklick installiert
# Treiber (/usr/local/canoscan8600f), App (/Applications) und CLI-Symlink.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_PREFIX=/usr/local/canoscan8600f
STAGE="$ROOT/build/dmg"
SRC="$ROOT/vendor/sane-backends"
VERSION="1.1"

rm -rf "$STAGE"
mkdir -p "$STAGE/payload"
# Altes Dev-Prefix kann veraltete Ladepfade tragen und ueber libtool in
# den Dist-Build einsickern. Weg damit, Schritt 5 baut es frisch.
rm -rf "$ROOT/prefix"

# 1) Treiber mit Dist-Prefix bauen und nach Staging installieren
cd "$SRC"
PKG_CONFIG_PATH="$(brew --prefix)/lib/pkgconfig" \
  ./configure --prefix="$DIST_PREFIX" BACKENDS=genesys >/dev/null
# Ohne make clean behalten Bibliotheken aus dem Dev-Build ihre alten
# Ladepfade und die installierte App bricht, sobald der Dev-Ordner
# fehlt oder umzieht. Deshalb pro Prefix immer sauber neu bauen.
make clean >/dev/null
make -j"$(sysctl -n hw.ncpu)" >/dev/null
make install DESTDIR="$STAGE/root" >/dev/null

# Ladepfade hart normalisieren. libtools Relink ist unzuverlaessig,
# install_name_tool macht sie deterministisch, danach neu signieren.
install_name_tool -id "$DIST_PREFIX/lib/libsane.1.dylib" \
  "$STAGE/root$DIST_PREFIX/lib/libsane.1.dylib"
codesign --force --sign - "$STAGE/root$DIST_PREFIX/lib/libsane.1.dylib"
for bin in "$STAGE/root$DIST_PREFIX"/bin/* "$STAGE/root$DIST_PREFIX"/sbin/*; do
  [ -f "$bin" ] && file "$bin" | grep -q Mach-O || continue
  otool -L "$bin" | awk 'NR>1 {print $1}' | grep 'libsane' | \
    while read -r dep; do
      install_name_tool -change "$dep" \
        "$DIST_PREFIX/lib/libsane.1.dylib" "$bin"
    done
  codesign --force --sign - "$bin"
done

if otool -L "$STAGE/root$DIST_PREFIX/bin/scanimage" | grep -qE "$ROOT|GitHub/canoscan"; then
  echo "FEHLER: scanimage referenziert Dev-Pfade" >&2
  otool -L "$STAGE/root$DIST_PREFIX/bin/scanimage" >&2
  exit 1
fi

# 2) CLI und GUI mit PyInstaller
"$ROOT/.venv/bin/pip" -q install pyinstaller
cd "$ROOT"
"$ROOT/.venv/bin/pyinstaller" --onefile --name scan8600 \
  --distpath "$STAGE/pybin" --workpath "$STAGE/pywork" \
  --specpath "$STAGE" "$ROOT/scan8600.py" >/dev/null 2>&1
"$ROOT/.venv/bin/pyinstaller" --windowed --name "JuiceScan" \
  --distpath "$STAGE/pyapp" --workpath "$STAGE/pywork-gui" \
  --specpath "$STAGE" "$ROOT/gui.py" >/dev/null 2>&1

# 3) pkg-Root zusammensetzen
PKGROOT="$STAGE/pkgroot"
mkdir -p "$PKGROOT/usr/local" "$PKGROOT/Applications"
cp -R "$STAGE/root$DIST_PREFIX" "$PKGROOT$DIST_PREFIX"
cp "$STAGE/pybin/scan8600" "$PKGROOT$DIST_PREFIX/bin/scan8600"
mkdir -p "$PKGROOT$DIST_PREFIX/gimp-plugin"
cp "$ROOT/gimp/scan8600_gimp.py" "$ROOT/scanoptions.py" \
   "$ROOT/gimp/INSTALL.md" "$PKGROOT$DIST_PREFIX/gimp-plugin/"
cp -R "$STAGE/pyapp/JuiceScan.app" "$PKGROOT/Applications/"

mkdir -p "$STAGE/pkgscripts"
cat > "$STAGE/pkgscripts/postinstall" <<'EOF'
#!/bin/bash
mkdir -p /usr/local/bin
ln -sf /usr/local/canoscan8600f/bin/scan8600 /usr/local/bin/scan8600
exit 0
EOF
chmod +x "$STAGE/pkgscripts/postinstall"

# 4) pkg bauen, in DMG verpacken. BundleIsRelocatable aus, sonst
# "aktualisiert" der Installer eine anderswo gefundene Kopie der App
# statt nach /Applications zu installieren.
pkgbuild --analyze --root "$PKGROOT" "$STAGE/components.plist" >/dev/null
/usr/libexec/PlistBuddy -c "Set :0:BundleIsRelocatable false" \
  "$STAGE/components.plist"
pkgbuild --root "$PKGROOT" \
  --component-plist "$STAGE/components.plist" \
  --identifier com.kupermann.juicescan \
  --version "$VERSION" \
  --scripts "$STAGE/pkgscripts" \
  --install-location / \
  "$STAGE/payload/JuiceScan.pkg" >/dev/null

(cd "$STAGE/pkgroot$DIST_PREFIX" && zip -qr \
  "$ROOT/build/scan8600-gimp-plugin.zip" gimp-plugin)

mkdir -p "$ROOT/build"
hdiutil create -volname "JuiceScan" -srcfolder "$STAGE/payload" \
  -ov -format UDZO "$ROOT/build/JuiceScan.dmg" >/dev/null
echo "DMG: $ROOT/build/JuiceScan.dmg (enthält JuiceScan.pkg)"

# 5) Dev-Build im Repo wiederherstellen (ebenfalls sauber)
cd "$SRC"
PKG_CONFIG_PATH="$(brew --prefix)/lib/pkgconfig" \
  ./configure --prefix="$ROOT/prefix" BACKENDS=genesys >/dev/null
make clean >/dev/null
make -j"$(sysctl -n hw.ncpu)" >/dev/null
make install >/dev/null
