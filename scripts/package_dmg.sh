#!/usr/bin/env bash
# Baut die macOS-DMG: sane-backends mit Dist-Prefix /usr/local/canoscan8600f,
# PyInstaller-Binary der CLI, install.sh, hdiutil-Image nach build/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_PREFIX=/usr/local/canoscan8600f
STAGE="$ROOT/build/dmg"
SRC="$ROOT/vendor/sane-backends"

rm -rf "$STAGE"
mkdir -p "$STAGE/payload"

cd "$SRC"
PKG_CONFIG_PATH="$(brew --prefix)/lib/pkgconfig" \
  ./configure --prefix="$DIST_PREFIX" BACKENDS=genesys >/dev/null
make -j"$(sysctl -n hw.ncpu)" >/dev/null
make install DESTDIR="$STAGE/root" >/dev/null
cp -R "$STAGE/root$DIST_PREFIX" "$STAGE/payload/canoscan8600f"

"$ROOT/.venv/bin/pip" -q install pyinstaller
cd "$ROOT"
"$ROOT/.venv/bin/pyinstaller" --onefile --name scan8600 \
  --distpath "$STAGE/pybin" --workpath "$STAGE/pywork" \
  --specpath "$STAGE" "$ROOT/scan8600.py" >/dev/null 2>&1
cp "$STAGE/pybin/scan8600" "$STAGE/payload/canoscan8600f/bin/scan8600"

"$ROOT/.venv/bin/pyinstaller" --windowed --name "CanoScan 8600F" \
  --distpath "$STAGE/pyapp" --workpath "$STAGE/pywork-gui" \
  --specpath "$STAGE" "$ROOT/gui.py" >/dev/null 2>&1
cp -R "$STAGE/pyapp/CanoScan 8600F.app" "$STAGE/payload/"

mkdir -p "$STAGE/payload/gimp-plugin"
cp "$ROOT/gimp/scan8600_gimp.py" "$ROOT/scanoptions.py" \
   "$ROOT/gimp/INSTALL.md" "$STAGE/payload/gimp-plugin/"
(cd "$STAGE/payload" && zip -qr "$ROOT/build/scan8600-gimp-plugin.zip" \
   gimp-plugin)

cat > "$STAGE/payload/install.sh" <<'EOF'
#!/bin/bash
# Installiert den CanoScan-8600F-Stack (Treiber + CLI + GUI-App).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
sudo mkdir -p /usr/local/canoscan8600f /usr/local/bin
sudo cp -R "$HERE/canoscan8600f/." /usr/local/canoscan8600f/
sudo ln -sf /usr/local/canoscan8600f/bin/scan8600 /usr/local/bin/scan8600
cp -R "$HERE/CanoScan 8600F.app" /Applications/
echo "Installiert: /Applications/CanoScan 8600F.app und CLI 'scan8600'."
EOF
chmod +x "$STAGE/payload/install.sh"

mkdir -p "$ROOT/build"
hdiutil create -volname "CanoScan 8600F" -srcfolder "$STAGE/payload" \
  -ov -format UDZO "$ROOT/build/CanoScan8600F.dmg" >/dev/null
echo "DMG: $ROOT/build/CanoScan8600F.dmg"

# Dev-Build im Repo wiederherstellen (configure-prefix zurückdrehen),
# damit ./prefix und die Tests weiter funktionieren.
cd "$SRC"
PKG_CONFIG_PATH="$(brew --prefix)/lib/pkgconfig" \
  ./configure --prefix="$ROOT/prefix" BACKENDS=genesys >/dev/null
