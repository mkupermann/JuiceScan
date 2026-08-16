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
DEFAULT_DPI = {"flatbed": 300, "film": 1200}


def parse_args(argv):
    p = argparse.ArgumentParser(prog="scan8600")
    p.add_argument("--mode", required=True, choices=["flatbed", "film"])
    p.add_argument("--dpi", type=int)
    p.add_argument("--format", choices=["tiff", "png", "jpeg"], default="tiff")
    p.add_argument("--output")
    p.add_argument("--gray", action="store_true")
    p.add_argument("--descratch", action="store_true",
                   help="IR-basierte Kratzerentfernung (nur --mode film)")
    p.add_argument("--autocrop", action="store_true",
                   help="auf erkannte Fotos/Dokumente zuschneiden")
    p.add_argument("--split", action="store_true",
                   help="jedes erkannte Foto als eigene Datei "
                        "(erfordert --autocrop)")
    p.add_argument("--depth16", action="store_true",
                   help="16 Bit pro Kanal, nur reines TIFF ohne "
                        "Nachbearbeitung")
    p.add_argument("--negative", action="store_true",
                   help="Negativ umkehren (Invertierung plus "
                        "Kanal-Streckung gegen die Orangemaske)")
    p.add_argument("--sane-opt", action="append", default=[],
                   metavar="OPT=WERT",
                   help="beliebige scanimage-Option ohne führende Striche "
                        "durchreichen, z. B. --sane-opt brightness=10 "
                        "(wiederholbar)")
    a = p.parse_args(argv)
    if a.dpi is None:
        a.dpi = DEFAULT_DPI[a.mode]
    if a.descratch and a.mode != "film":
        p.error("--descratch erfordert --mode film")
    if a.split and not a.autocrop:
        p.error("--split erfordert --autocrop")
    if a.depth16 and (a.descratch or a.negative or a.autocrop
                      or a.format != "tiff"):
        p.error("--depth16 geht nur mit reinem TIFF ohne Nachbearbeitung")
    return a


def default_output(a):
    ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[a.format]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"scan_{stamp}.{ext}"


def build_command(a, source_name):
    cmd = [str(SCANIMAGE), "--format=tiff",
           "--resolution", str(a.dpi),
           "--mode", "Gray" if a.gray else "Color"]
    if getattr(a, "depth16", False):
        cmd += ["--depth", "16"]
    if source_name:
        cmd += ["--source", source_name]
    for raw in getattr(a, "sane_opt", []) or []:
        key, _, val = raw.partition("=")
        key = key.lstrip("-")
        key = ("-" if len(key) == 1 else "--") + key
        cmd += [key, val] if val else [key]
    return cmd


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
                "Scanner nicht gefunden. " + BUSY_HINT
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
    "Der Scanner wurde nicht gefunden oder ist belegt. Häufigste Ursache: "
    "ein anderes Programm hält das Gerät (Digitale Bilder, "
    "Systemeinstellungen 'Drucker & Scanner', VueScan). Diese Fenster "
    "schließen und erneut versuchen. Danach USB-Kabel und Netzschalter "
    "prüfen: ioreg -p IOUSB | grep -i CanoScan")


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
    out = pathlib.Path(a.output or default_output(a))
    source = ir_source = None
    if a.mode == "film":
        opts = _probe_options()
        source = find_film_source(opts)
        if source is None:
            raise ScanError(
                "Keine Durchlicht-Quelle gefunden. Verfügbare Optionen:\n"
                + opts)
        if a.descratch:
            ir_source = find_ir_source(opts)
            if ir_source is None:
                raise ScanError(
                    "Keine Infrarot-Quelle für --descratch gefunden. "
                    "Verfügbare Optionen:\n" + opts)
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
    if a.negative:
        arr = invert_negative(arr)
    if a.autocrop:
        import autocrop as _ac
        if a.split:
            crops = _ac.split_regions(arr) or [arr]
            outs = []
            for i, crop in enumerate(crops, 1):
                p = (out.with_stem(f"{out.stem}_{i}")
                     if len(crops) > 1 else out)
                _save_array(crop, a, p)
                outs.append(p)
            return outs
        arr = _ac.crop_to_content(arr)
    _save_array(arr, a, out)
    return [out]


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        outs = run_scan(a)
    except ScanError as e:
        print(f"scan8600: {e}", file=sys.stderr)
        return 1
    for out in outs:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
