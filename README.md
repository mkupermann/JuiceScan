<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/juicescan-logo.png">
  <img alt="JuiceScan" src="assets/juicescan-logo-light.png" width="560">
</picture>

# JuiceScan

Old scanners do not die from broken hardware. They die from missing
drivers. I was not ready to accept that for my CanoScan 8600F, so this
project exists.

JuiceScan brings old scanners back to life on current macOS and
Windows 11. The app finds any SANE-compatible scanner, you pick it,
and the options come straight from the driver. The bundled driver
stack ships the SANE genesys backend today. That covers the Canon
CanoScan and LiDE families and related GL-chipset scanners from
Plustek, Medion and Visioneer. I have tested exactly one machine on
real hardware, my own CanoScan 8600F. Every other model runs on the
word of the driver database and stays marked untested until someone
scans with it. I would rather tell you that than pretend.

Three parts. A self-compiled SANE driver backend. A CLI and a GUI. A
GIMP 3 plugin that shows every option the driver has. macOS on Apple
Silicon and Windows 11.

<img width="3398" height="2122" alt="image" src="https://github.com/user-attachments/assets/6c57a956-7c01-4159-8a9c-d1687124ea88" />

<img width="273" height="480" alt="image" src="https://github.com/user-attachments/assets/827ddc46-ad16-49b2-8d65-ac5db971f6d1" />


## What it does

- Flatbed at 300 to 1200 dpi, transparency at 300 to 4800 dpi
- Two-stage film workflow. Fast preview, draw your frames in the
  editor, then the scanner only scans those areas at full resolution
- Scanner selection with discovery, handles USB re-numbering
- Batch mode, presets, persistent settings, custom scan areas
- Controls are built from your scanner. A slider the driver does not
  offer is switched off instead of sent, and a value out of range is
  clamped and named. Before, one unsupported option aborted the scan
  after the carriage had already moved
- Every scan writes a log beside the image: progress with timestamps,
  and how long each stage took. When something is slow you can see
  where, instead of guessing
- HDR multi-exposure for dense negatives, two passes merged (new, not
  yet verified on hardware)
- The lamp warm-up is shown for what it is. The driver scans one line
  over and over until the brightness is stable, up to twenty seconds
  with the carriage moving and no image coming out. The window says so,
  with a second count, instead of claiming to be scanning
- Dust and scratch removal over the infrared channel, the same
  principle SilverFast calls iSRD. On silver B/W film the app detects
  that infrared cannot work there and says so instead of ruining the
  image
- Negative inversion with gray-world balance against the orange mask
- 16-bit archival TIFF
- Automatic size detection for photos on the flatbed, several photos
  in one pass, each saved as its own file
- Calibration runs once per resolution and mode, then it is cached

## Install on macOS

Take `JuiceScan.dmg` from the latest release, mount it, double-click
`JuiceScan.pkg`. Self-contained, no Homebrew needed. Driver goes to
`/usr/local/canoscan8600f`, the app to `/Applications`, the `scan8600`
CLI gets a symlink.

From source:

    ./build_sane.sh
    python3 -m venv .venv
    .venv/bin/pip install pytest pillow numpy opencv-python PySide6

## Install on Windows 11

Take `JuiceScan-windows.zip` from the latest release, unpack it, bind
the scanner to WinUSB with Zadig as described in `docs/WINDOWS.md`,
run `JuiceScan.exe`. Tested on real Windows 11 hardware. The CI
workflow rebuilds the whole package on a Windows runner, including the
MinGW-patched driver build.

## Scanning

GUI:

    .venv/bin/python gui.py

Film is two-stage. Scan makes a quick preview of the whole strip. The
suggested frames appear as rectangles. Draw your own with the mouse,
drag to move, Backspace deletes. Save crops scans only those areas,
inverts each frame on its own and writes numbered files. That is why a
single 6x6 frame takes a fraction of a full-strip scan.

CLI:

    scan8600 --list-devices
    scan8600 --mode flatbed
    scan8600 --mode film --dpi 2400 --descratch --negative
    scan8600 --mode flatbed --autocrop --split

The options that matter:

    --device NAME            pick a scanner, default is the first found
    --dpi N                  resolution, default 300 flatbed, 2400 film
    --gray                   grayscale instead of color
    --format tiff|png|jpeg   output format, default tiff
    --output PATH            target file
    --descratch              infrared pass plus inpainting, film only
    --negative               invert negatives, orange mask compensated
    --depth16                16-bit archival TIFF, plain scans only
    --autocrop               detect content and crop to size
    --split                  each detected photo as its own file
    --frames N               frames in the film holder, 0 is automatic
    --sane-opt OPT=VALUE     pass any further driver option through

The first scan at a new resolution or mode calibrates once and takes
longer. After that the calibration is cached for good in `~/.sane` and
scans start right away.

## GIMP plugin

Lives in `gimp/`, install steps in `gimp/INSTALL.md`. The plugin reads
the options from the driver at runtime. What the driver can do, the
plugin shows. Not yet smoke-tested inside a running GIMP, the logic
behind it is covered by unit tests.

## Honest limits

- Scanning B/W film? Set Color to Grayscale. A cold lamp shifts its
  color during the first scans and puts density-dependent casts into
  color scans, pink sky, green shadows. Grayscale is immune, faster,
  a third of the file size, and what silver film deserves anyway.
- If transparency scans come out as colored vertical stripes, the
  narrow calibration slot at the top of the transparency window is
  blocked, usually by the film holder or the white mat. High
  resolutions fail first, 300 dpi survives longest, which makes it
  look like a driver bug. It is not. Clear the slot, power-cycle the
  scanner. This one cost us an evening.
- Automatic frame detection needs bright film-base gaps between
  frames. Dense image areas look just like separators. When frames
  touch, set the frame count yourself or draw the frames in the
  editor. SilverFast shows you a frame overview for the same reason.
- Infrared dust removal cannot work on silver-based B/W film or
  Kodachrome. Silver blocks infrared. That is physics, not a bug. The
  app detects the case and skips inpainting with a warning.
- Scan speed is honest genesys speed. About two minutes for a 6x6
  frame at 2400 dpi. VueScan is faster because Hamrick spent twenty
  years tuning motor profiles per device. We measured where our time
  goes, took the safe gains, and left the risky motor tricks alone.
- The first scan after a break is slow and the carriage moves without
  producing anything. That is the driver warming the lamp: it scans one
  line over and over until the brightness stops drifting. Measured on
  a 40x40 mm flatbed scan: 36.7 of 39.5 seconds passed before the first
  byte arrived. Scan again right away and it is 10.6 of 12.6. Nothing
  in this app can shorten it, so the window says what is happening
  instead of pretending to scan.
- White documents on the white lid confuse the flatbed autocrop. A
  black sheet of paper behind the document fixes it.
- Switching between JuiceScan and VueScan can leave the scanner in a
  state the other driver cannot open. One power-cycle fixes it.

## When a scan is slow

Every scan writes a `.scanlog` next to the output file. It carries the
progress reports from the driver with timestamps, and the duration of
each stage:

    stage probe 0.57s
    t=10.61s progress=4.9% rss=27.8MB
    t=12.31s progress=100.0% rss=27.8MB
    scan pass 12.63s rc=0 652.9KB
    stage decode 0.06s
    stage save 0.00s

A flat stretch before the first `progress` line is the lamp warm-up. A
plateau in the middle would be something else, and worth reporting.

The progress is printed once per driver read, so the buffer size sets
how finely you can see. For a close look set `JUICESCAN_BUFFER_KB=32`;
the default of 4096 gives one data point on a small scan.

## Tests

    .venv/bin/python -m pytest tests/ -q

77 tests, plus hardware runs for detection, flatbed, transparency with
scratch removal, negative inversion, 16-bit output, and a 6x6 black
and white strip through the whole film path. Only what ran on the real
machine counts as verified. The rest is listed as what it is.

## License

Own code is MIT. sane-backends is fetched at build time from
gitlab.com/sane-project and is GPL licensed. If you redistribute the
DMG or the Windows package you ship GPL binaries and must provide
access to their source.

## Docs

- Windows setup: `docs/WINDOWS.md`
- Design and plans: `docs/superpowers/`
- Decisions and verdicts: `DECISIONS.md`

Not everything that can be automated should be automated. But a good
scanner should never die of a missing driver.
