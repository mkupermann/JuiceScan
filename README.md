# canoscan

Eigener Treiber-Stack für den Canon CanoScan 8600F (USB 04a9:2229) —
selbst kompiliertes SANE-genesys-Backend plus eigene Scan-CLI mit
IR-Kratzerentfernung. macOS arm64 und Windows 11 (siehe
`docs/WINDOWS.md`).

## Setup (macOS)

    ./build_sane.sh                  # kompiliert sane-backends (genesys) nach ./prefix
    python3 -m venv .venv
    .venv/bin/pip install pytest pillow numpy opencv-python

## Scannen

    .venv/bin/python scan8600.py --mode flatbed                 # 300 dpi, Farbe, TIFF
    .venv/bin/python scan8600.py --mode film                    # Durchlicht, 1200 dpi
    .venv/bin/python scan8600.py --mode film --descratch        # + IR-Kratzerentfernung

Optionen:

    --dpi N              Auflösung (Default 300 flatbed / 1200 film)
    --gray               Graustufen statt Farbe
    --format tiff|png|jpeg   Ausgabeformat (Default tiff)
    --output PATH        Zieldatei (Default scan_<timestamp>.<ext>)
    --descratch          Zweiter Infrarot-Pass, Defektmaske, Inpainting
                         (Prinzip SilverFast iSRD/FARE; nur --mode film)
    --autocrop           Fotos/Dokumente automatisch erkennen und auf die
                         tatsächliche Größe zuschneiden
    --split              jedes erkannte Foto als eigene Datei speichern
                         (scan_x_1.tiff, scan_x_2.tiff, ...; erfordert --autocrop)

Hinweis zu --autocrop: weißes Dokument auf weißem Deckel ist für die
Erkennung unzuverlässig — kontrastreiche Auflage (z. B. schwarzes
Tonpapier hinter dem Dokument) verbessert das Ergebnis deutlich.

Der erste Scan kalibriert den Scanner (dauert länger); Kalibrierdaten
liegen unter `~/.sane`.

## Tests

    .venv/bin/python -m pytest tests/ -q

## Doku

- Spec: `docs/superpowers/specs/2026-08-16-canoscan-8600f-design.md`
- Plan: `docs/superpowers/plans/2026-08-16-canoscan-8600f.md`
- Windows: `docs/WINDOWS.md`
