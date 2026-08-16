#!/usr/bin/env python3
"""scan8600 - Flachbett- und Durchlicht-Scans mit dem CanoScan 8600F."""
import argparse
import datetime
import pathlib
import re
import subprocess
import sys

def _default_prefix():
    import os
    if os.environ.get("SCAN8600_PREFIX"):
        return pathlib.Path(os.environ["SCAN8600_PREFIX"])
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            return pathlib.Path(sys.executable).resolve().parent / "prefix"
        # DMG-Install: fester Pfad, identisch mit dem configure-prefix
        # des Dist-Builds (scripts/package_dmg.sh).
        return pathlib.Path("/usr/local/canoscan8600f")
    return pathlib.Path(__file__).resolve().parent / "prefix"


PREFIX = _default_prefix()
_EXE = "scanimage.exe" if sys.platform == "win32" else "scanimage"
SCANIMAGE = PREFIX / "bin" / _EXE
SANE_ENV = {"SANE_CONFIG_DIR": str(PREFIX / "etc" / "sane.d")}
DEFAULT_DPI = {"flatbed": 300, "film": 2400}


def parse_args(argv):
    p = argparse.ArgumentParser(prog="scan8600")
    p.add_argument("--mode", required=True, choices=["flatbed", "film"])
    p.add_argument("--dpi", type=int)
    p.add_argument("--format", choices=["tiff", "png", "jpeg"], default="tiff")
    p.add_argument("--output")
    p.add_argument("--gray", action="store_true")
    p.add_argument("--descratch", action="store_true",
                   help="infrared-based scratch removal (film mode only)")
    p.add_argument("--autocrop", action="store_true",
                   help="crop to detected photos/documents")
    p.add_argument("--split", action="store_true",
                   help="save each detected photo as its own file "
                        "(requires --autocrop)")
    p.add_argument("--frames", type=int, default=0,
                   help="number of frames in the film holder, splits the "
                        "strip evenly (0 = automatic via base gaps)")
    p.add_argument("--depth16", action="store_true",
                   help="16 bits per channel, plain TIFF without "
                        "post-processing only")
    p.add_argument("--negative", action="store_true",
                   help="invert negative (inversion plus per-channel "
                        "stretch against the orange mask)")
    p.add_argument("--sane-opt", action="append", default=[],
                   metavar="OPT=WERT",
                   help="pass any scanimage option without leading dashes, "
                        "e.g. --sane-opt brightness=10 (repeatable)")
    a = p.parse_args(argv)
    if a.dpi is None:
        a.dpi = DEFAULT_DPI[a.mode]
    if a.descratch and a.mode != "film":
        p.error("--descratch requires --mode film")
    if a.split and not a.autocrop:
        p.error("--split requires --autocrop")
    if a.depth16 and (a.descratch or a.negative or a.autocrop
                      or a.format != "tiff"):
        p.error("--depth16 only works with plain TIFF, no post-processing")
    return a


def default_output(a):
    ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[a.format]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"scan_{stamp}.{ext}"


def build_command(a, source_name):
    # Reihenfolge ist bedeutsam: scanimage wertet Optionen sequenziell
    # aus. Die Quelle muss VOR der Auflösung stehen, sonst wird die
    # Auflösung gegen die Liste der Standardquelle geprüft und still
    # abgerundet (Flachbett kann nur bis 1200, Durchlicht bis 4800).
    # 4-MB-Puffer statt 32 KB Standard: weniger USB-Transaktionen,
    # messbar ruhigerer Durchsatz bei Hochauflösungs-Scans.
    cmd = [str(SCANIMAGE), "--format=tiff", "--buffer-size=4096"]
    if source_name:
        cmd += ["--source", source_name]
    cmd += ["--resolution", str(a.dpi),
            "--mode", "Gray" if a.gray else "Color",
            # Kalibrier-Cache nie verfallen lassen, sonst verwirft
            # genesys die Kalibrierung nach 60 Minuten.
            "--expiration-time", "-1"]
    if getattr(a, "depth16", False):
        cmd += ["--depth", "16"]
    for raw in getattr(a, "sane_opt", []) or []:
        key, _, val = raw.partition("=")
        key = key.lstrip("-")
        key = ("-" if len(key) == 1 else "--") + key
        cmd += [key, val] if val else [key]
    return cmd


LAST_WARNINGS = []


class ScanError(Exception):
    pass


def _pick_source(options_text, pattern):
    m = re.search(r"--source\s+(\S[^\[\n]*)", options_text)
    if not m:
        return None
    for cand in m.group(1).split("|"):
        cand = cand.strip()
        if re.search(pattern, cand, re.IGNORECASE):
            return cand
    return None


def find_film_source(options_text):
    # IR-Quelle heisst auch "Transparency ..." — für den Normalpass explizit
    # die Nicht-IR-Variante wählen.
    m = re.search(r"--source\s+(\S[^\[\n]*)", options_text)
    if not m:
        return None
    for cand in m.group(1).split("|"):
        cand = cand.strip()
        if (re.search(r"transparen|film|\bta\b", cand, re.IGNORECASE)
                and not re.search(r"infrared|\bir\b", cand, re.IGNORECASE)):
            return cand
    return None


def find_ir_source(options_text):
    return _pick_source(options_text, r"infrared|\bir\b")


def scanimage_run(cmd, **kw):
    import os
    env = dict(os.environ, **SANE_ENV)
    return subprocess.run(cmd, env=env, capture_output=True, **kw)


def _run_pass(a, source, retries=1):
    r = scanimage_run(build_command(a, source))
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace")
        if "no SANE devices" in err:
            raise ScanError(
                "Scanner not found. " + BUSY_HINT
                + "\nDetails:\n" + err)
        if "Invalid argument" in err and retries > 0:
            # Transient direkt nach vorherigem Scan (Gerät noch busy/homing):
            # kurz warten, einmal neu versuchen.
            import time
            time.sleep(5)
            return _run_pass(a, source, retries - 1)
        raise ScanError(err)
    return r.stdout


BUSY_HINT = (
    "Scanner not found or busy. Most common cause: another application "
    "is holding the device (Image Capture, System Settings "
    "'Printers & Scanners', VueScan). Close those windows and retry. "
    "Then check USB cable and power switch: "
    "ioreg -p IOUSB | grep -i CanoScan")


def _probe_options(retries=3):
    import time
    for attempt in range(retries):
        probe = scanimage_run([str(SCANIMAGE), "-A"])
        opts = probe.stdout.decode(errors="replace")
        if probe.returncode == 0 and "--source" in opts:
            return opts
        if attempt < retries - 1:
            time.sleep(3)
    raise ScanError(BUSY_HINT + "\nDetails:\n"
                    + probe.stderr.decode(errors="replace"))


def run_scan(a):
    LAST_WARNINGS.clear()
    if not SCANIMAGE.exists():
        raise ScanError(
            f"Driver not found at {SCANIMAGE}. Install the pkg from the DMG "
            "first (installs to /usr/local/canoscan8600f) or point "
            "SCAN8600_PREFIX at the driver folder.")
    out = pathlib.Path(a.output or default_output(a))
    source = ir_source = None
    if a.mode == "film":
        opts = _probe_options()
        source = find_film_source(opts)
        if source is None:
            raise ScanError(
                "No transparency source found. Available options:\n"
                + opts)
        if a.descratch:
            ir_source = find_ir_source(opts)
            if ir_source is None:
                raise ScanError(
                    "No infrared source found for --descratch. "
                    "Available options:\n" + opts)
    tiff_bytes = _run_pass(a, source)
    cleaned = None
    if ir_source:
        import io

        import numpy as np
        from PIL import Image

        import descratch as _ds
        ir_args = argparse.Namespace(**vars(a))
        ir_args.gray = True
        ir_bytes = _run_pass(ir_args, ir_source)
        vis = np.array(Image.open(io.BytesIO(tiff_bytes)).convert("RGB"))
        ir = np.array(Image.open(io.BytesIO(ir_bytes)).convert("L"))
        if _ds.is_silver_film(vis, ir):
            LAST_WARNINGS.append(
                "Infrared scratch removal skipped: this looks like "
                "silver-based B/W film. Silver blocks infrared just like "
                "dust does, so inpainting would destroy image content. "
                "This is a physical limit, not a bug.")
        else:
            cleaned = _ds.remove_defects(vis, ir)
    return _finalize(tiff_bytes, cleaned, a, out)


def _save_array(arr, a, path):
    from PIL import Image
    img = Image.fromarray(arr)
    if a.format == "jpeg":
        img.save(path, quality=95)
    else:
        img.save(path)


def invert_negative(arr):
    import numpy as np
    inv = 255 - arr
    if inv.ndim == 3:
        for c in range(inv.shape[2]):
            ch = inv[..., c].astype(np.float32)
            lo, hi = np.percentile(ch, 1), np.percentile(ch, 99)
            if hi > lo:
                inv[..., c] = np.clip(
                    (ch - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    return inv


def _finalize(tiff_bytes, cleaned, a, out):
    plain = a.format == "tiff" and not a.autocrop and not a.negative
    if cleaned is None and plain:
        out.write_bytes(tiff_bytes)
        return [out]
    import io

    import numpy as np
    from PIL import Image
    if cleaned is None:
        arr = np.array(Image.open(io.BytesIO(tiff_bytes)).convert("RGB"))
    else:
        arr = cleaned
    # Reihenfolge: erst zuschneiden, dann invertieren. Bei Film erkennt
    # die Rahmensuche auf dem Rohscan (helle Filmbasis), und jedes Frame
    # bekommt seine eigene Tonwert-Streckung.
    film = a.mode == "film"
    if a.autocrop:
        import autocrop as _ac
        if a.split:
            expected = getattr(a, "frames", 0)
            crops = (_ac.split_film_frames(arr, expected) if film
                     else _ac.split_regions(arr)) or [arr]
            outs = []
            for i, crop in enumerate(crops, 1):
                if a.negative:
                    crop = invert_negative(crop)
                p = (out.with_stem(f"{out.stem}_{i}")
                     if len(crops) > 1 else out)
                _save_array(crop, a, p)
                outs.append(p)
            return outs
        if film:
            frames = _ac.detect_film_frames(arr)
            if frames:
                x0 = min(f[0] for f in frames)
                y0 = min(f[1] for f in frames)
                x1 = max(f[0] + f[2] for f in frames)
                y1 = max(f[1] + f[3] for f in frames)
                arr = arr[y0:y1, x0:x1]
        else:
            arr = _ac.crop_to_content(arr)
    if a.negative:
        arr = invert_negative(arr)
    _save_array(arr, a, out)
    return [out]


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        outs = run_scan(a)
    except ScanError as e:
        print(f"scan8600: {e}", file=sys.stderr)
        return 1
    for w in LAST_WARNINGS:
        print(f"scan8600: warning: {w}", file=sys.stderr)
    for out in outs:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
