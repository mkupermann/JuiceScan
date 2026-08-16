#!/usr/bin/env python3
"""scan8600 - Flachbett- und Durchlicht-Scans mit dem CanoScan 8600F."""
import argparse
import datetime
import pathlib
import re
import subprocess
import sys

PREFIX = pathlib.Path(__file__).resolve().parent / "prefix"
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
    a = p.parse_args(argv)
    if a.dpi is None:
        a.dpi = DEFAULT_DPI[a.mode]
    if a.descratch and a.mode != "film":
        p.error("--descratch erfordert --mode film")
    return a


def default_output(a):
    ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[a.format]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"scan_{stamp}.{ext}"


def build_command(a, source_name):
    cmd = [str(SCANIMAGE), "--format=tiff",
           "--resolution", str(a.dpi),
           "--mode", "Gray" if a.gray else "Color"]
    if source_name:
        cmd += ["--source", source_name]
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


def _run_pass(a, source):
    r = scanimage_run(build_command(a, source))
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace")
        if "no SANE devices" in err or "Invalid argument" in err:
            raise ScanError(
                "Scanner nicht gefunden. USB-Kabel prüfen, dann: "
                "ioreg -p IOUSB | grep -i CanoScan. Details:\n" + err)
        raise ScanError(err)
    return r.stdout


def run_scan(a):
    out = pathlib.Path(a.output or default_output(a))
    source = ir_source = None
    if a.mode == "film":
        probe = scanimage_run([str(SCANIMAGE), "-A"])
        opts = probe.stdout.decode(errors="replace")
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
        img = Image.fromarray(cleaned)
        if a.format == "jpeg":
            img.save(out, quality=95)
        else:
            img.save(out)
        return out
    if a.format == "tiff":
        out.write_bytes(tiff_bytes)
    else:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(tiff_bytes))
        img.save(out, quality=95) if a.format == "jpeg" else img.save(out)
    return out


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        out = run_scan(a)
    except ScanError as e:
        print(f"scan8600: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
