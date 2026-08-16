#!/usr/bin/env bash
# In der MSYS2-MINGW64-Shell auf Windows 11 ausführen. Baut sane-backends
# (nur genesys) repo-lokal nach ./prefix — Gegenstück zu build_sane.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/vendor/sane-backends"
PREFIX="$ROOT/prefix"
TAG="1.3.1"

pacman -S --needed --noconfirm base-devel git autoconf automake libtool \
  autoconf-archive gettext gettext-devel \
  mingw-w64-x86_64-toolchain mingw-w64-x86_64-libusb \
  mingw-w64-x86_64-libtiff mingw-w64-x86_64-libjpeg-turbo \
  mingw-w64-x86_64-libpng mingw-w64-x86_64-pkgconf

[ -d "$SRC" ] || git clone --depth 1 --branch "$TAG" \
  https://gitlab.com/sane-project/backends.git "$SRC"

cd "$SRC"
autoreconf -f -i
./configure --prefix="$PREFIX" BACKENDS=genesys
make -j"$(nproc)"
make install
"$PREFIX/bin/scanimage" --version
