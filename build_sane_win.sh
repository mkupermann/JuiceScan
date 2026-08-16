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

# MinGW-Kompatibilität: u_int32_t und syslog existieren unter Windows nicht.
# Beide Dateien sind Netz-/Logging-Kompatschichten ohne Bedeutung für
# lokales USB-Scannen.
grep -q 'typedef uint32_t u_int32_t' lib/inet_pton.c || \
  sed -i '1i #include <stdint.h>\ntypedef uint32_t u_int32_t;' lib/inet_pton.c
cat > lib/vsyslog.c <<'EOF'
/* MinGW: kein syslog vorhanden, Logging wird verworfen. */
#include <stdarg.h>
void vsyslog(int priority, const char *format, va_list args)
{ (void) priority; (void) format; (void) args; }
EOF

# MinGW: tv_sec ist long, localtime erwartet time_t*.
grep -q 'time_t _tsec' sanei/sanei_init_debug.c || \
  sed -i 's|t = localtime (&tv.tv_sec);|{ time_t _tsec = tv.tv_sec; t = localtime (\&_tsec); }|' \
    sanei/sanei_init_debug.c

autoreconf -f -i
./configure --prefix="$PREFIX" BACKENDS=genesys
make -j"$(nproc)"
make install
"$PREFIX/bin/scanimage" --version
