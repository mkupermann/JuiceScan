# JuiceScan

Canon stopped shipping drivers for the CanoScan 8600F years ago. No
current macOS support, no Windows 11 support. The scanner itself is
still a fine piece of hardware, with a transparency unit and an
infrared lamp for dust detection. This repo keeps it alive.

The stack has three parts. A self-compiled SANE genesys backend as the
driver. A CLI and a GUI for scanning. A GIMP 3 plugin that exposes
every driver option inside GIMP. Runs on macOS (Apple Silicon) and
Windows 11.

## What it does

- Flatbed at 300 to 1200 dpi, transparency (film and slides) at
  300 to 4800 dpi
- Two-stage film workflow: fast 300 dpi preview, draw or adjust frames
  in the built-in editor, then the scanner only scans those frame
  areas at full resolution
- Color or grayscale, TIFF, PNG and JPEG
- Dust and scratch removal via the infrared channel, same principle
  as SilverFast iSRD. Detects silver-based B/W film automatically and
  skips inpainting there, because silver blocks infrared like dust does
- Negative inversion with per-channel stretch against the orange mask
- 16-bit archival TIFF
- Automatic detection of photos and documents on the flatbed, cropped
  to their actual size
- Several photos in one pass, each saved as its own file
- Calibration runs once per resolution and stays cached, not on every
  scan
- Scanner device selection with discovery, ready for multiple scanners
- Batch scan mode for sequential frames with automatic numbering
- HDR multi-exposure: two passes at different exposure, merged for
  dense negatives (new, not yet verified on hardware)
- Lamp warm-up guard: optional delay before color film scans so the
  cold lamp cannot tint the image (new, not yet verified on hardware)
- Settings and presets persist between sessions

## Install on macOS

Prebuilt: grab `JuiceScan.dmg` from the latest release, mount it,
double-click `JuiceScan.pkg`. Self-contained, no Homebrew needed.
It installs the driver to
`/usr/local/canoscan8600f`, the app to `/Applications` and the
`scan8600` CLI symlink.

From source:

    ./build_sane.sh
    python3 -m venv .venv
    .venv/bin/pip install pytest pillow numpy opencv-python PySide6

## Install on Windows 11

Grab `JuiceScan-windows.zip` from the latest release, unpack it,
follow the Zadig driver binding steps in `docs/WINDOWS.md`, then run
`JuiceScan.exe`. Tested on real Windows 11 hardware. The CI
workflow `windows-exe.yml` rebuilds the whole package on a Windows
runner, including the MinGW-patched driver build.

## Scanning

GUI:

    .venv/bin/python gui.py

Film in the GUI is two-stage. Scan runs a quick 300 dpi preview of the
whole strip. The suggested frames appear as rectangles, draw your own
with the mouse, drag to move, Backspace deletes. Save crops then scans
only those areas, inverts each frame on its own and writes numbered
files.

CLI:

    .venv/bin/python scan8600.py --mode flatbed
    .venv/bin/python scan8600.py --mode film --dpi 2400 --descratch --negative
    .venv/bin/python scan8600.py --mode flatbed --autocrop --split

The options that matter:

    --dpi N                  resolution, default 300 flatbed, 2400 film
    --gray                   grayscale instead of color
    --format tiff|png|jpeg   output format, default tiff
    --output PATH            target file
    --descratch              infrared pass plus inpainting, film only
    --negative               invert negatives, orange mask compensated
    --depth16                16-bit archival TIFF, plain scans only
    --autocrop               detect content and crop to size
    --split                  save each detected photo as its own file
    --frames N               number of frames in the film holder; splits
                             the strip evenly (0 = auto via base gaps)
    --sane-opt OPT=VALUE     pass any further driver option through

The first scan at a new resolution calibrates the scanner and takes
longer. After that the calibration is cached for good in `~/.sane`,
scans start right away.

## GIMP plugin

Lives in `gimp/`, install steps in `gimp/INSTALL.md`. The plugin reads
the available options from the driver at runtime. Whatever the driver
can do, the plugin shows. The plugin itself has not been smoke-tested
inside GIMP yet, its option logic is covered by unit tests.

## Honest limits

- White documents on the white lid confuse the autocrop. A high
  contrast backing helps, black paper works.
- Automatic film frame detection relies on bright film-base gaps
  between frames. Dense image areas (a bright sky in the negative)
  look just like a separator bar, so when frames touch, set the frame
  count yourself with `--frames N` or the GUI field. That is the same
  reason SilverFast shows you a frame overview to correct.
- Scanning B/W film? Set Color to Grayscale. A cold lamp shifts its
  color during the first scans, which puts density-dependent casts into
  color scans (pink sky, green shadows). Grayscale is immune, faster,
  and what silver film deserves anyway. Color mode with gray-world
  balancing is for color negatives and slides.
- If transparency scans come out as colored vertical stripes, the
  narrow calibration slot at the top of the transparency window is
  obstructed, usually by the film holder or the white mat. High
  resolutions calibrate through a finer window and fail first, 300 dpi
  survives longer, which makes it look like a driver bug. Clear the
  slot and power-cycle the scanner. We lost an evening to this one.
- Infrared dust removal cannot work on silver-based B/W film or
  Kodachrome. Silver blocks infrared. That is physics, not a bug. The
  app detects this case by comparing the infrared image with the
  visible one and skips inpainting with a warning instead of smearing
  dense image areas.

## Tests

    .venv/bin/python -m pytest tests/ -q

46 tests, plus hardware runs for detection, flatbed, transparency
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
