# CanoScan 8600F — Eigener Treiber-Stack + Scan-CLI (Design)

Datum: 2026-08-16
Status: freigegeben (VIBE)

## Ziel

Den Canon CanoScan 8600F (USB 04a9:2229, GL841-Chipsatz) auf macOS arm64
(Apple Silicon, Darwin 25) betreiben — ohne Canon-Treiber, ohne VueScan.
Zwei Scan-Modi: Flachbett (Auflicht) und Durchlicht (Film/Dia über die
eingebaute Transparency Unit).

## Ansatz

Kein Protokoll-Reverse-Engineering: das genesys-Backend von sane-backends
unterstützt den 8600F inklusive Durchlichteinheit. "Eigener Treiber" heißt
hier: sane-backends selbst aus dem Quellcode kompilieren, repo-lokal
installiert, plus eine eigene kleine CLI darauf.

## Komponenten

### 1. build_sane.sh — Treiber-Build

- Klont sane-backends (GitLab, stabiler Release-Tag).
- `./configure BACKENDS=genesys --prefix=<repo>/prefix` — nur das
  genesys-Backend, Installation repo-lokal unter `./prefix`. Kein
  System-Install, kein Homebrew-Paket, keine Kollision mit anderer Software.
- Abhängigkeiten: Xcode CLT, autotools (vorhanden), libusb 1.0.30 (Homebrew,
  vorhanden), libtiff/libpng/libjpeg via Homebrew nach Bedarf.
- Ergebnis: `prefix/bin/scanimage`, `prefix/lib/sane/libsane-genesys.*`.
- Idempotent: erneuter Lauf aktualisiert/rebuildet.

### 2. scan8600 — Python-CLI

Python ≥3.13, stdlib + Pillow (nur für Formatkonvertierung). Ruft das
repo-lokale `scanimage` per subprocess.

Flags:
- `--mode flatbed|film` (Pflicht). `film` setzt `--source "Transparency
  Adapter"` (exakter Source-Name wird zur Laufzeit aus `scanimage -A`
  ermittelt, da Backend-Versionen abweichen können).
- `--dpi N` — Default 300 (flatbed) / 1200 (film).
- `--format tiff|png|jpeg` — Default tiff. scanimage liefert TIFF/PNM;
  Konvertierung via Pillow.
- `--output PATH` — Default `scan_YYYYmmdd_HHMMSS.<ext>` im CWD.
- `--gray` — Graustufen statt Farbe.

Fehlerbehandlung:
- Gerät nicht gefunden → klarer Hinweis (USB-Kabel, `ioreg`-Check,
  evtl. von Image Capture belegt).
- Unbekannter Source-Name → Ausgabe der verfügbaren Sources aus
  `scanimage -A`.
- scanimage-Exit ≠ 0 → stderr durchreichen, kein Halbergebnis-Schreiben.

## Datenfluss

scan8600 → subprocess scanimage (lokales prefix, SANE_CONFIG_DIR auf
prefix/etc/sane.d) → TIFF auf stdout → Pillow-Konvertierung falls nötig →
Zieldatei.

## Tests

1. Erkennung: `scanimage -L` listet `genesys:libusb:...`.
2. Flachbett-Testscan (300 dpi, TIFF) — Datei entsteht, plausible Größe.
3. Durchlicht-Testscan (1200 dpi, TIFF) — Lampe der TPU fährt, Datei entsteht.
4. CLI-Unit-Tests (pytest): Argument-Parsing, Default-Ableitung,
   Fehlerpfade mit gemocktem subprocess.

## Risiken

- genesys-Kalibrierung schreibt nach `$HOME/.sane` — beim ersten Scan
  dauert es länger (Kalibrierfahrt), das ist normal.
- macOS kann das Gerät über ICA (Image Capture) belegen; falls libusb
  keinen Zugriff bekommt, Prozess `scanservices`/ICA-Daemon identifizieren
  und Hinweis geben.
- TPU-Scanqualität des genesys-Backends ist unter VueScan-Niveau —
  akzeptiert, Ziel ist ein eigener, offener Stack.

## Nicht-Ziele (YAGNI)

Keine GUI, kein Mehrseiten-/Batch-Management, keine Infrarot-Staubentfernung,
kein System-Install, keine Unterstützung anderer Scanner.
