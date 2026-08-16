#!/usr/bin/env bash
# Baut sane-backends (nur genesys) repo-lokal nach ./prefix. Idempotent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/vendor/sane-backends"
PREFIX="$ROOT/prefix"
TAG="1.3.1"

brew list --versions libusb libtiff jpeg-turbo libpng libtool autoconf-archive >/dev/null || \
  brew install libusb libtiff jpeg-turbo libpng libtool autoconf-archive

if [ ! -d "$SRC" ]; then
  git clone --depth 1 --branch "$TAG" \
    https://gitlab.com/sane-project/backends.git "$SRC"
fi

cd "$SRC"
export ACLOCAL_PATH="$(brew --prefix)/share/aclocal:$(brew --prefix libtool)/share/aclocal"
./autogen.sh
PKG_CONFIG_PATH="$(brew --prefix)/lib/pkgconfig" \
  ./configure --prefix="$PREFIX" BACKENDS=genesys
make -j"$(sysctl -n hw.ncpu)"
make install
"$PREFIX/bin/scanimage" --version
