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

# MinGW: Parallelport und SCSI gibt es hier nicht, USB reicht.
# Stubs mit den offiziellen Signaturen, damit sane-find-scanner linkt.
cat > sanei/sanei_pio.c <<'EOF'
/* MinGW-Stub: kein Parallelport unter Windows. */
#include "../include/sane/config.h"
#include "../include/sane/sane.h"
#include "../include/sane/sanei_pio.h"
SANE_Status sanei_pio_open (const char *dev, int *fd)
{ (void) dev; (void) fd; return SANE_STATUS_UNSUPPORTED; }
void sanei_pio_close (int fd) { (void) fd; }
int sanei_pio_read (int fd, u_char *buf, int n)
{ (void) fd; (void) buf; (void) n; return -1; }
int sanei_pio_write (int fd, const u_char *buf, int n)
{ (void) fd; (void) buf; (void) n; return -1; }
EOF
cat > sanei/sanei_scsi.c <<'EOF'
/* MinGW-Stub: kein SCSI-Pfad, der 8600F läuft über USB. */
#include "../include/sane/config.h"
#include "../include/sane/sane.h"
#include "../include/sane/sanei_scsi.h"
int sanei_scsi_max_request_size = 0;
void sanei_scsi_find_devices (const char *vendor, const char *model,
                              const char *type, int bus, int channel,
                              int id, int lun,
                              SANE_Status (*attach) (const char *dev))
{ (void) vendor; (void) model; (void) type; (void) bus; (void) channel;
  (void) id; (void) lun; (void) attach; }
SANE_Status sanei_scsi_open (const char *device_name, int *fd,
                             SANEI_SCSI_Sense_Handler handler,
                             void *handler_arg)
{ (void) device_name; (void) fd; (void) handler; (void) handler_arg;
  return SANE_STATUS_UNSUPPORTED; }
SANE_Status sanei_scsi_open_extended (const char *device_name, int *fd,
                                      SANEI_SCSI_Sense_Handler handler,
                                      void *handler_arg, int *buffersize)
{ (void) device_name; (void) fd; (void) handler; (void) handler_arg;
  (void) buffersize; return SANE_STATUS_UNSUPPORTED; }
SANE_Status sanei_scsi_req_enter (int fd, const void *src, size_t src_size,
                                  void *dst, size_t *dst_size, void **idp)
{ (void) fd; (void) src; (void) src_size; (void) dst; (void) dst_size;
  (void) idp; return SANE_STATUS_UNSUPPORTED; }
SANE_Status sanei_scsi_req_enter2 (int fd, const void *cmd, size_t cmd_size,
                                   const void *src, size_t src_size,
                                   void *dst, size_t *dst_size, void **idp)
{ (void) fd; (void) cmd; (void) cmd_size; (void) src; (void) src_size;
  (void) dst; (void) dst_size; (void) idp;
  return SANE_STATUS_UNSUPPORTED; }
SANE_Status sanei_scsi_req_wait (void *id)
{ (void) id; return SANE_STATUS_UNSUPPORTED; }
SANE_Status sanei_scsi_cmd (int fd, const void *src, size_t src_size,
                            void *dst, size_t *dst_size)
{ (void) fd; (void) src; (void) src_size; (void) dst; (void) dst_size;
  return SANE_STATUS_UNSUPPORTED; }
SANE_Status sanei_scsi_cmd2 (int fd, const void *cmd, size_t cmd_size,
                             const void *src, size_t src_size,
                             void *dst, size_t *dst_size)
{ (void) fd; (void) cmd; (void) cmd_size; (void) src; (void) src_size;
  (void) dst; (void) dst_size; return SANE_STATUS_UNSUPPORTED; }
void sanei_scsi_req_flush_all (void) { }
void sanei_scsi_req_flush_all_extended (int fd) { (void) fd; }
void sanei_scsi_close (int fd) { (void) fd; }
EOF

# MinGW: kill() existiert nicht. Lock-Datei-Prüfung meldet dann
# konservativ, dass der andere Prozess noch lebt.
grep -q 'define kill' sanei/sanei_access.c || \
  sed -i 's|#include "../include/sane/sanei_access.h"|#include "../include/sane/sanei_access.h"\n#ifdef __MINGW32__\n#define kill(pid, sig) 0\n#endif|' \
    sanei/sanei_access.c

# MinGW: tv_sec ist long, localtime erwartet time_t*.
grep -q 'time_t _tsec' sanei/sanei_init_debug.c || \
  sed -i 's|t = localtime (&tv.tv_sec);|{ time_t _tsec = tv.tv_sec; t = localtime (\&_tsec); }|' \
    sanei/sanei_init_debug.c

# MinGW: mkdir nimmt nur ein Argument.
grep -q 'mkdir(ret.c_str())' backend/genesys/genesys.cpp || \
  sed -i 's|mkdir(ret.c_str(), 0700);|#ifdef __MINGW32__\n        mkdir(ret.c_str());\n#else\n        mkdir(ret.c_str(), 0700);\n#endif|' \
    backend/genesys/genesys.cpp

# MinGW: localtime_r existiert nicht, Wrapper über localtime.
grep -q 'mingw_localtime_r' frontend/jpegtopdf.c || \
  sed -i 's|#include "jpegtopdf.h"|#include "jpegtopdf.h"\n#ifdef __MINGW32__\nstatic struct tm *mingw_localtime_r(const time_t *t, struct tm *r)\n{ struct tm *p = localtime(t); if (p) *r = *p; return p ? r : 0; }\n#define localtime_r mingw_localtime_r\n#endif|' \
    frontend/jpegtopdf.c

autoreconf -f -i

# C++-verträglich: Parametername 'new' im sigprocmask-Fallback-Prototyp.
# config.h.in existiert erst nach autoreconf.
sed -i 's|int sigprocmask (int how, int \*new, int \*old);|int sigprocmask (int how, int *nset, int *oset);|' \
  include/sane/config.h.in

CFLAGS="-O2 -Wno-incompatible-pointer-types -Wno-implicit-function-declaration" \
  LIBS="-lws2_32 -lstdc++" \
  LDFLAGS="-Wl,--allow-multiple-definition" \
  ./configure --prefix="$PREFIX" BACKENDS=genesys
make -j"$(nproc)"
make install
"$PREFIX/bin/scanimage" --version
