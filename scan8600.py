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
