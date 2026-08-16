# canoscan

Canon liefert für den CanoScan 8600F keine Treiber mehr. Weder für
aktuelles macOS noch für Windows 11. Der Scanner selbst ist aber ein
gutes Stück Hardware, mit Durchlichteinheit und Infrarot-Lampe für die
Kratzererkennung. Dieses Repo hält ihn am Leben.

Der Stack besteht aus drei Teilen. Ein selbst kompiliertes
SANE-genesys-Backend als Treiber. Eine CLI und eine GUI zum Scannen.
Ein GIMP-3-Plugin, das alle Treiberoptionen direkt in GIMP anbietet.
Läuft auf macOS (Apple Silicon) und Windows 11.

## Was es kann

- Flachbett und Durchlicht (Film und Dia), 300 bis 4800 dpi
- Farbe oder Graustufen, TIFF, PNG und JPEG
- Kratzer- und Staubentfernung über den Infrarot-Kanal, nach dem
  gleichen Prinzip wie SilverFast iSRD
- Automatische Erkennung von Fotos und Dokumenten auf dem Flachbett,
  mit Zuschnitt auf die tatsächliche Größe
- Mehrere aufgelegte Fotos in einem Durchgang, jedes als eigene Datei

## Installation macOS

Fertiges Paket: `./scripts/package_dmg.sh` baut die DMG nach
`build/CanoScan8600F.dmg`. In der DMG liegt ein `install.sh`, das
Treiber, CLI und App nach `/usr/local/canoscan8600f` und `/Applications`
installiert.

Aus dem Quellcode:

    ./build_sane.sh
    python3 -m venv .venv
    .venv/bin/pip install pytest pillow numpy opencv-python PySide6

## Installation Windows 11

Der GitHub-Actions-Workflow `windows-exe.yml` baut das komplette Paket
auf einem Windows-Runner. Details und die Zadig-Treiberbindung stehen in
`docs/WINDOWS.md`. Auf echter Windows-Hardware ist das Paket noch
ungetestet.

## Scannen

GUI:

    .venv/bin/python gui.py

CLI:

    .venv/bin/python scan8600.py --mode flatbed
    .venv/bin/python scan8600.py --mode film --dpi 2400 --descratch
    .venv/bin/python scan8600.py --mode flatbed --autocrop --split

Die wichtigsten Optionen:

    --dpi N                  Auflösung, Standard 300 Flachbett, 1200 Film
    --gray                   Graustufen statt Farbe
    --format tiff|png|jpeg   Ausgabeformat, Standard tiff
    --output PATH            Zieldatei
    --descratch              Infrarot-Pass plus Inpainting, nur Film
    --autocrop               Größe automatisch erkennen und zuschneiden
    --split                  jedes erkannte Foto als eigene Datei
    --sane-opt OPT=WERT      jede weitere Treiberoption durchreichen

## GIMP-Plugin

Liegt unter `gimp/`, Installation steht in `gimp/INSTALL.md`. Das Plugin
liest die Optionen zur Laufzeit aus dem Treiber aus. Was der Treiber
kann, zeigt das Plugin an. Mangels GIMP auf dem Entwicklungsrechner ist
es ungetestet, die Options-Logik dahinter ist über Unit-Tests abgedeckt.

## Grenzen, ehrlich benannt

- Weißes Dokument auf weißem Deckel erkennt der Autocrop schlecht.
  Kontrastreiche Auflage hilft, etwa schwarzes Tonpapier.
- Die Durchlichtqualität des genesys-Backends liegt unter VueScan-Niveau.
  Dafür gehört hier der komplette Stack Dir.
- Der erste Scan kalibriert und dauert deshalb länger.

## Tests

    .venv/bin/python -m pytest tests/ -q

30 Tests, dazu Hardware-Tests für Erkennung, Flachbett und Durchlicht
mit Kratzerentfernung.

## Lizenz

Eigener Code steht unter MIT. sane-backends wird beim Build von
gitlab.com/sane-project geladen und steht unter der GPL. Wer die
fertige DMG oder das Windows-Paket weitergibt, gibt damit auch
GPL-Binaries weiter und muss deren Quellcode zugänglich machen.

## Doku

- Spec: `docs/superpowers/specs/2026-08-16-canoscan-8600f-design.md`
- Plan: `docs/superpowers/plans/2026-08-16-canoscan-8600f.md`
- Windows: `docs/WINDOWS.md`

Alte Hardware stirbt nicht am Gerät, sie stirbt am fehlenden Treiber.
