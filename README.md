# canoscan

Canon stopped shipping drivers for the CanoScan 8600F years ago. No
current macOS support, no Windows 11 support. The scanner itself is
still a fine piece of hardware, with a transparency unit and an
infrared lamp for dust detection. This repo keeps it alive.

The stack has three parts. A self-compiled SANE genesys backend as the
driver. A CLI and a GUI for scanning. A GIMP 3 plugin that exposes
every driver option inside GIMP. Runs on macOS (Apple Silicon) and
Windows 11.

## What it does

- Flatbed and transparency (film and slides), 300 to 4800 dpi
- Color or grayscale, TIFF, PNG and JPEG
- Dust and scratch removal via the infrared channel, same principle
  as SilverFast iSRD
- Negative inversion with per-channel stretch against the orange mask
- 16-bit archival TIFF
- Automatic detection of photos and documents on the flatbed, cropped
  to their actual size
- Several photos in one pass, each saved as its own file

## Install on macOS

Prebuilt: grab `CanoScan8600F.dmg` from the latest release, mount it,
double-click `CanoScan8600F.pkg`. That installs the driver to
`/usr/local/canoscan8600f`, the app to `/Applications` and the
`scan8600` CLI symlink.

From source:

    ./build_sane.sh
    python3 -m venv .venv
    .venv/bin/pip install pytest pillow numpy opencv-python PySide6

## Install on Windows 11

Grab `CanoScan8600F-windows.zip` from the latest release, unpack it,
follow the Zadig driver binding steps in `docs/WINDOWS.md`, then run
`CanoScan8600F.exe`. Tested on real Windows 11 hardware. The CI
workflow `windows-exe.yml` rebuilds the whole package on a Windows
runner, including the MinGW-patched driver build.

## Scanning

GUI:

    .venv/bin/python gui.py

CLI:

    .venv/bin/python scan8600.py --mode flatbed
    .venv/bin/python scan8600.py --mode film --dpi 2400 --descratch --negative
    .venv/bin/python scan8600.py --mode flatbed --autocrop --split

The options that matter:

    --dpi N                  resolution, default 300 flatbed, 1200 film
    --gray                   grayscale instead of color
    --format tiff|png|jpeg   output format, default tiff
    --output PATH            target file
    --descratch              infrared pass plus inpainting, film only
    --negative               invert negatives, orange mask compensated
    --depth16                16-bit archival TIFF, plain scans only
    --autocrop               detect content and crop to size
    --split                  save each detected photo as its own file
    --sane-opt OPT=VALUE     pass any further driver option through

The first scan calibrates the scanner and takes longer. Calibration
data lives in `~/.sane`.

## GIMP plugin

Lives in `gimp/`, install steps in `gimp/INSTALL.md`. The plugin reads
the available options from the driver at runtime. Whatever the driver
can do, the plugin shows. The plugin itself has not been smoke-tested
inside GIMP yet, its option logic is covered by unit tests.

## Honest limits

- White documents on the white lid confuse the autocrop. A high
  contrast backing helps, black paper works.
- Transparency quality of the genesys backend sits below VueScan
  level. In return you own the whole stack.
- Infrared dust removal cannot work on silver-based B/W film or
  Kodachrome. Silver blocks infrared. That is physics, not a bug.

## Tests

    .venv/bin/python -m pytest tests/ -q

35 tests, plus hardware runs for detection, flatbed, transparency
with scratch removal, negative inversion and 16-bit output.

## License

Own code is MIT. sane-backends is fetched at build time from
gitlab.com/sane-project and is GPL licensed. If you redistribute the
DMG or the Windows package you are shipping GPL binaries and must
provide access to their source.

## Docs

- Spec: `docs/superpowers/specs/2026-08-16-canoscan-8600f-design.md`
- Plan: `docs/superpowers/plans/2026-08-16-canoscan-8600f.md`
- Windows: `docs/WINDOWS.md`

Old hardware does not die with the device. It dies with the missing
driver.
