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
    p.add_argument("--device", default=None,
                   help="SANE device name (e.g., genesys:libusb:001:014). "
                        "If not specified, uses the first available device.")
    p.add_argument("--list-devices", action="store_true",
                   help="List all available SANE scanners and exit.")
    p.add_argument("--mode", choices=["flatbed", "film"],
                   help="Scan mode: flatbed or film (transparency). Required for scanning.")
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
    
    # If listing devices, no other validation needed
    if a.list_devices:
        return a
    
    # Validate mode is provided for scanning
    if a.mode is None:
        p.error("--mode is required for scanning (flatbed or film)")
    
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


DEFAULT_BUFFER_KB = 256


def buffer_kb():
    """scanimage-Eingabepuffer in KB.

    Der Puffer bestimmt, wie lange ein Abbruch braucht: scanimage
    reagiert erst, wenn der laufende sane_read zurückkehrt. Gemessen auf
    dem Durchlichtaufsatz bei 300 dpi, vom SIGTERM bis zum sauberen Ende
    mit geparktem Schlitten: 32 KB 4,2 s · 256 KB 8,3 s · 512 KB 12,8 s ·
    4 MB 37,3 s.

    Früher standen hier 4 MB, wegen weniger USB-Transaktionen. Laut
    DECISIONS.md vom 2026-08-17 bringt die Puffergröße für den Durchsatz
    aber nachweislich nichts. Sie kostete also nur Abbruchzeit. 256 KB
    ist der Kompromiss: achtmal weniger Transaktionen als scanimages
    eigener Standard von 32 KB, Abbruch unter zehn Sekunden. Für
    Messläufe überschreibbar.
    """
    import os
    raw = os.environ.get("JUICESCAN_BUFFER_KB", "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_BUFFER_KB
    return value if value > 0 else DEFAULT_BUFFER_KB


def default_output(a):
    ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[a.format]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"scan_{stamp}.{ext}"


def build_command(a, source_name, device=None):
    # Reihenfolge ist bedeutsam: scanimage wertet Optionen sequenziell
    # aus. Die Quelle muss VOR der Auflösung stehen, sonst wird die
    # Auflösung gegen die Liste der Standardquelle geprüft und still
    # abgerundet (Flachbett kann nur bis 1200, Durchlicht bis 4800).
    # 4-MB-Puffer statt 32 KB Standard: weniger USB-Transaktionen,
    # messbar ruhigerer Durchsatz bei Hochauflösungs-Scans.
    # -p lässt scanimage den Fortschritt auf stderr schreiben. Das ist die
    # einzige Spur, an der sich ein Stocken des Schlittens von einem
    # gleichmäßig langsamen Scan unterscheiden lässt. Der Fortschritt
    # wird einmal pro sane_read gedruckt, die Puffergröße bestimmt also
    # die Auflösung der Messung: mit 4 MB bekommt man bei kleinen Scans
    # nur einen einzigen Messpunkt. Für Messläufe JUICESCAN_BUFFER_KB
    # klein setzen (z.B. 32).
    cmd = [str(SCANIMAGE), "--format=tiff",
           f"--buffer-size={buffer_kb()}", "-p"]
    
    # Add device if specified
    if device:
        cmd += ["-d", device]
    elif getattr(a, "device", None):
        cmd += ["-d", a.device]
    
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


class ScanCancelled(ScanError):
    """Der Anwender hat abgebrochen. Kein Fehler, sondern eine Ansage."""


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


def find_film_source_general(options_text):
    """Find film/transparency source for general SANE scanners."""
    return _pick_source(options_text, r"transparen|film|\bta\b")


# Jedes scanimage -A öffnet das Gerät. Der Warmlauf faellt dabei zwar
# nicht an (gemessen: 0,6 s), aber HDR, Batch und der Crop-Pass haben
# bisher vor jedem einzelnen Pass neu gesondiert. Einmal pro Prozess
# reicht.
_OPTS_CACHE = {}


def clear_options_cache():
    _OPTS_CACHE.clear()


def probe_options(device=None):
    key = device or ""
    if key not in _OPTS_CACHE:
        with stage("probe"):
            _OPTS_CACHE[key] = (_probe_device_options(device) if device
                                else _probe_options())
    return _OPTS_CACHE[key]


def _probe_device_options(device_file, retries=3):
    """Probe options for a specific device."""
    import time
    
    # Wenn device_file angegeben ist, erstmal versuchen
    if device_file:
        for attempt in range(retries):
            probe = scanimage_run([str(SCANIMAGE), "-A", "-d", device_file])
            opts = probe.stdout.decode(errors="replace")
            if probe.returncode == 0 and "--source" in opts:
                return opts
            if attempt < retries - 1:
                time.sleep(3)
        
        # Wenn das spezifische Gerät nicht funktioniert, alle Geräte probieren
        # (USB-Adressen können sich dynamisch ändern)
        try:
            from discovery import ScannerDiscovery
            disc = ScannerDiscovery(str(SCANIMAGE))
            devices = disc.list_devices()
            for dev in devices:
                if dev.device_file == device_file:
                    continue  # schon versucht
                probe = scanimage_run([str(SCANIMAGE), "-A", "-d", dev.device_file])
                opts = probe.stdout.decode(errors="replace")
                if probe.returncode == 0 and "--source" in opts:
                    return opts
        except Exception:
            pass
    
    # Fallback: ohne device_file probieren
    for attempt in range(retries):
        probe = scanimage_run([str(SCANIMAGE), "-A"])
        opts = probe.stdout.decode(errors="replace")
        if probe.returncode == 0 and "--source" in opts:
            return opts
        if attempt < retries - 1:
            time.sleep(3)
    
    raise ScanError(BUSY_HINT + "\nDetails:\n"
                    + probe.stderr.decode(errors="replace"))


def scanimage_run(cmd, **kw):
    import os
    env = dict(os.environ, **SANE_ENV)
    return subprocess.run(cmd, env=env, capture_output=True, **kw)


# --- Diagnose ------------------------------------------------------------
#
# Bis hierher gab es im Projekt keine Zeitmessung und keinen Fortschritt.
# Ein "der Motor stockt" liess sich damit weder belegen noch widerlegen.
# Alles unter diesem Kommentar dient genau dem: messen statt raten.

LAST_LOG_PATH = None


def _rss_bytes():
    """Spitzen-RSS dieses Prozesses. Auf macOS in Bytes, auf Linux in KiB."""
    try:
        import resource
    except ImportError:
        return 0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}"
        n /= 1024.0


def log_path_for(a):
    out = getattr(a, "output", None) or default_output(a)
    return pathlib.Path(out).with_suffix(".scanlog")


def setup_logging(a):
    """Ein Logger: alles in die Datei neben der Ausgabe, Stufenzeiten
    zusätzlich auf stderr. Idempotent, Handler werden ersetzt."""
    global LAST_LOG_PATH
    import logging

    log = logging.getLogger("juicescan")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()

    LAST_LOG_PATH = None
    try:
        path = log_path_for(a)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        log.addHandler(fh)
        LAST_LOG_PATH = path
    except OSError:
        pass

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("juicescan: %(message)s"))
    log.addHandler(sh)
    return log


def get_log():
    import logging
    return logging.getLogger("juicescan")


class stage:
    """Kontextmanager, misst eine Pipeline-Stufe."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        import time
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        import time
        get_log().info("stage %s %.2fs rss=%s", self.name,
                       time.monotonic() - self.t0, _human(_rss_bytes()))
        return False


_PROGRESS = re.compile(r"Progress:\s*([\d.]+)%")


def _pump_stderr(stream, log, t0, sink, on_progress=None):
    """Liest stderr mit, zeitstempelt jede Fortschrittsmeldung und hält
    Progress-Zeilen aus dem Fehlertext heraus."""
    import os
    import time
    buf = ""
    fd = stream.fileno()
    while True:
        # os.read statt stream.read: der gepufferte Reader blockiert, bis
        # 256 Bytes zusammen sind, und liefert die ganze Fortschrittsspur
        # erst am Scanende - mit wertlosen Zeitstempeln.
        try:
            chunk = os.read(fd, 256)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk.decode(errors="replace")
        # scanimage trennt Fortschritt mit \r, Fehler mit \n.
        buf = buf.replace("\r", "\n")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            m = _PROGRESS.search(line)
            if m:
                elapsed = time.monotonic() - t0
                log.debug("t=%.2fs progress=%s%% rss=%s", elapsed, m.group(1),
                          _human(_rss_bytes()))
                if on_progress is not None:
                    try:
                        on_progress(float(m.group(1)), elapsed)
                    except Exception:
                        pass
            elif line.strip():
                sink.append(line)
    if buf.strip() and not _PROGRESS.search(buf):
        sink.append(buf)


# --- Abbruch ------------------------------------------------------------
#
# Bisher gab es keinen. Ein Fenster schliessen liess das laufende
# scanimage als Waise weiterlaufen: es hielt das USB-Geraet, bewegte den
# Schlitten und niemand holte das Ergebnis ab. Der naechste Versuch lief
# dann in "Scanner not found or busy".

import threading as _threading

_RUNNING = {"proc": None, "cancelled": False}
_RUNNING_LOCK = _threading.Lock()


def begin_scan_session():
    with _RUNNING_LOCK:
        _RUNNING["cancelled"] = False


def scan_was_cancelled():
    with _RUNNING_LOCK:
        return _RUNNING["cancelled"]


def _escalate_after(proc, kill_after):
    """Wartet im Hintergrund und tritt nur nach, wenn wirklich nichts
    passiert. Laeuft als eigener Thread, damit weder die Oberflaeche
    noch ein Signalhandler blockiert."""
    import time
    deadline = time.monotonic() + kill_after
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    get_log().info("still running after %.0fs, sending SIGKILL - the "
                   "carriage may be left mid-travel", kill_after)
    try:
        proc.kill()
    except OSError:
        pass


# Der Treiber prueft das Abbruchflag nicht, solange er im
# Lampen-Warmlauf steckt, und der laeuft laut genesys bis zu 65 s
# (WARMUP_TIME). Gemessen: ein Abbruch waehrend des Warmlaufs wurde bei
# 45 s Karenz mit SIGKILL beendet, der Schlitten bleibt dann stehen.
# Ausgerechnet der Warmlauf ist der Moment, in dem man Stop drueckt -
# da sieht es aus, als haenge das Geraet. Deshalb liegt die Karenz
# ueber WARMUP_TIME.
DEFAULT_KILL_AFTER = 75.0


def cancel_scan(kill_after=DEFAULT_KILL_AFTER, wait=True):
    """Bricht den laufenden Pass ab. True, wenn etwas lief.

    Genau EIN SIGTERM. scanimage faengt es ab und ruft sane_cancel, der
    Treiber parkt den Schlitten. Ein zweites Signal laesst es sofort
    aussteigen und der Schlitten bleibt stehen, wo er ist - deshalb wird
    nicht nachgetreten. Erst wenn nach kill_after Sekunden immer noch
    nichts passiert ist, bleibt SIGKILL, und das steht dann im Log.

    Es dauert, weil scanimage erst reagiert, wenn der laufende sane_read
    zurückkehrt: gemessen 8,3 s beim Standardpuffer, 37,3 s bei 4 MB.
    Die Karenz muss über dem schlechtesten Fall liegen, sonst tritt man
    einem Gerät nach, das gerade dabei ist, ordentlich aufzuräumen.
    """
    import time
    with _RUNNING_LOCK:
        _RUNNING["cancelled"] = True
        proc = _RUNNING["proc"]
    if proc is None or proc.poll() is not None:
        return False
    get_log().info("cancel requested, sending SIGTERM to pid %s", proc.pid)
    proc.terminate()
    if not wait:
        # Der Aufrufer ist die Oberflaeche oder ein Signalhandler.
        # Beide duerfen hier nicht stehenbleiben, das Nachtreten
        # uebernimmt ein eigener Thread.
        _threading.Thread(target=_escalate_after, args=(proc, kill_after),
                          daemon=True).start()
        return True
    deadline = time.monotonic() + kill_after
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.1)
    get_log().info("still running after %.0fs, sending SIGKILL - the "
                   "carriage may be left mid-travel", kill_after)
    proc.kill()
    return True


def scan_run(cmd, on_progress=None):
    """Startet scanimage für einen Scanpass und protokolliert dabei die
    Fortschrittsspur. Rückgabe: (returncode, tiff_bytes, stderr_text).

    on_progress(prozent, sekunden) wird aus dem Reader-Thread gerufen,
    sobald scanimage Daten meldet. Bis dahin läuft im Treiber der
    Lampen-Warmlauf: der Schlitten fährt, es kommt aber nichts an.
    """
    import os
    import threading
    import time

    log = get_log()
    env = dict(os.environ, **SANE_ENV)
    t0 = time.monotonic()
    err = []

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    with _RUNNING_LOCK:
        _RUNNING["proc"] = proc
    try:
        pump = threading.Thread(target=_pump_stderr,
                                args=(proc.stderr, log, t0, err, on_progress),
                                daemon=True)
        pump.start()
        payload = proc.stdout.read()
        proc.stdout.close()
        proc.wait()
        pump.join(timeout=5)
    finally:
        with _RUNNING_LOCK:
            _RUNNING["proc"] = None

    log.info("scan pass %.2fs rc=%s %s rss=%s", time.monotonic() - t0,
             proc.returncode, _human(len(payload)), _human(_rss_bytes()))
    return proc.returncode, payload, "\n".join(err)


# --- Optionen gegen das Gerät prüfen -----------------------------------


def _opt_flag(key):
    key = key.lstrip("-")
    return ("-" if len(key) == 1 else "--") + key


def _fmt_num(x):
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def filter_sane_opts(sane_opts, options_text):
    """Verwirft Optionen, die das Gerät nicht kennt, und klemmt Bereiche.

    scanimage steigt bei einer unbekannten Option aus, nachdem es das
    Gerät schon geöffnet hat - der Schlitten fährt an und bleibt stehen,
    ohne dass ein Bild entsteht. Werte außerhalb des Bereichs rundet der
    Treiber still. Beides hier abfangen und benennen.
    """
    import scanoptions

    known = {o.name: o for o in scanoptions.parse(options_text or "")}
    if not known:
        # Ohne verwertbare Optionsliste nicht raten, sondern durchlassen.
        return list(sane_opts or [])

    kept = []
    for raw in sane_opts or []:
        key, sep, val = raw.partition("=")
        flag = _opt_flag(key)
        opt = known.get(flag)
        if opt is None:
            LAST_WARNINGS.append(
                f"{flag.lstrip('-')}: not supported by this scanner, "
                "option ignored")
            get_log().info("dropped unsupported option %s", flag)
            continue
        if opt.kind == "range" and sep and opt.hi > opt.lo:
            try:
                num = float(val)
            except ValueError:
                kept.append(raw)
                continue
            clamped = min(max(num, opt.lo), opt.hi)
            if clamped != num:
                LAST_WARNINGS.append(
                    f"{flag.lstrip('-')}: {_fmt_num(num)} is outside "
                    f"{_fmt_num(opt.lo)}..{_fmt_num(opt.hi)}, "
                    f"clamped to {_fmt_num(clamped)}")
                raw = f"{key}={_fmt_num(clamped)}"
        kept.append(raw)
    return kept


# 70 x 230 mm Durchlichtfenster bei 4800 dpi sind rund 575 Mpx. Das alte
# Limit von 500 Mpx liegt darunter, ein Vollstrip-Scan wäre nach dem
# Scannen an Pillows Bomb-Check gestorben.
MAX_PIXELS = 700_000_000

def _open_pass(payload):
    """PIL-Image aus einem Scanpass. Einzige Stelle, an der das
    Pixel-Limit gesetzt wird."""
    import io

    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    return Image.open(io.BytesIO(payload))


def _run_pass(a, source, device=None, retries=1, tag="scan", on_progress=None):
    rc, payload, err = scan_run(build_command(a, source, device), on_progress)
    if scan_was_cancelled():
        raise ScanCancelled("Scan cancelled.")
    if rc != 0:
        if "no SANE devices" in err:
            raise ScanError(
                "Scanner not found. " + BUSY_HINT
                + "\nDetails:\n" + err)
        if "unrecognized option" in err:
            import re as _re
            m = _re.search(r"unrecognized option [`\'\"]?-*([\w-]+)", err)
            name = m.group(1) if m else "one of the scan options"
            raise ScanError(
                f"This scanner does not support the option '{name}'. "
                "scanimage aborts on an unknown option, which is why the "
                "carriage moves and then stops without producing an image. "
                "Reset that control in the Advanced section and scan again."
                "\nDetails:\n" + err)
        if "Invalid argument" in err and retries > 0:
            # Transient direkt nach vorherigem Scan (Gerät noch busy/homing):
            # kurz warten, einmal neu versuchen.
            # Auch: USB-Adresse könnte sich geändert haben - neues Gerät probieren
            import time
            time.sleep(5)
            
            # Wenn device angegeben war, vielleicht hat es sich geändert
            if device:
                try:
                    from discovery import ScannerDiscovery
                    disc = ScannerDiscovery(str(SCANIMAGE))
                    devices = disc.list_devices()
                    # Versuche, ein funktionierendes Gerät zu finden
                    for dev in devices:
                        if dev.device_file == device:
                            # Gleiches Gerät nochmal versuchen
                            return _run_pass(a, source, device, retries - 1,
                                             tag, on_progress)
                        else:
                            # Neues Gerät probieren
                            new_rc, new_payload, _ = scan_run(
                                build_command(a, source, dev.device_file),
                                on_progress)
                            if new_rc == 0:
                                return new_payload
                except Exception:
                    pass
                # Wenn nichts funktioniert, nochmal mit originalem device
                return _run_pass(a, source, device, retries - 1, tag,
                                 on_progress)
            else:
                return _run_pass(a, source, device, retries - 1, tag,
                                 on_progress)
        raise ScanError(err)
    return payload


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


def _warn_on_narrow_film_window(a, options_text):
    """Auf dem Durchlichtaufsatz ist eine verkuerzte Scanbreite kaputt.

    Der genesys-Treiber legt dann die Shading-Korrektur um einige
    Sensorspalten versetzt an. Das Ergebnis sind senkrechte Streifen,
    unabhaengig von l und t und unabhaengig von der Kalibrierung im
    Cache. Gemessen bei 300 dpi Grau: ganzes Fenster sauber, x=59.44
    kaputt. Senkrecht einschraenken ist harmlos.
    """
    if getattr(a, "mode", None) != "film":
        return
    import scanoptions
    known = {o.name: o for o in scanoptions.parse(options_text or "")}
    full = known.get("-x")
    if full is None or full.hi <= 0:
        return
    for raw in getattr(a, "sane_opt", []) or []:
        key, _, val = raw.partition("=")
        if _opt_flag(key) not in ("-x", "-l"):
            continue
        try:
            num = float(val)
        except ValueError:
            continue
        narrow = (_opt_flag(key) == "-x" and num < full.hi - 0.5) or \
                 (_opt_flag(key) == "-l" and num > 0.5)
        if narrow:
            LAST_WARNINGS.append(
                "Transparency scans narrower than the full window come "
                "back with vertical stripes: the driver applies the "
                "shading correction with a horizontal offset. Scan the "
                "full width and crop afterwards. Restricting the height "
                "is fine.")
            get_log().info("narrow film window requested: %s", raw)
            return


def run_scan(a, on_progress=None):
    LAST_WARNINGS.clear()
    begin_scan_session()
    log = setup_logging(a)
    log.info("run_scan mode=%s dpi=%s gray=%s buffer=%skB",
             getattr(a, "mode", None), getattr(a, "dpi", None),
             getattr(a, "gray", None), buffer_kb())
    if not SCANIMAGE.exists():
        raise ScanError(
            f"Driver not found at {SCANIMAGE}. Install the pkg from the DMG "
            "first (installs to /usr/local/canoscan8600f) or point "
            "SCAN8600_PREFIX at the driver folder.")
    
    # Get device info if not specified
    # Note: We don't set device to a specific address if not provided by user.
    # This avoids USB address changes between detection and scanning.
    # If user didn't specify --device, we let scanimage use the default device.
    device = getattr(a, "device", None)
    
    out = pathlib.Path(a.output or default_output(a))
    source = ir_source = None
    
    # Probe device options to find available sources
    # If device is specified, use it; otherwise probe without device (uses default)
    opts = probe_options(device)

    # Optionen gegen das echte Gerät prüfen, bevor scanimage sie sieht.
    # Eine unbekannte Option lässt scanimage abbrechen, nachdem es das
    # Gerät schon geöffnet hat.
    a.sane_opt = filter_sane_opts(getattr(a, "sane_opt", []) or [], opts)
    _warn_on_narrow_film_window(a, opts)

    if a.mode == "film":
        source = find_film_source(opts)
        if source is None and device:
            # For general SANE scanners, try to find transparency/film source
            source = find_film_source_general(opts)
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
    
    try:
        with stage("scan-visible"):
            tiff_bytes = _run_pass(a, source, device, tag="visible",
                                   on_progress=on_progress)
        cleaned = None
        if ir_source:
            import numpy as np

            import descratch as _ds
            ir_args = argparse.Namespace(**vars(a))
            ir_args.gray = True
            with stage("scan-infrared"):
                ir_bytes = _run_pass(ir_args, ir_source, device, tag="ir",
                                     on_progress=on_progress)
            with stage("decode-descratch"):
                vis = np.array(_open_pass(tiff_bytes).convert("RGB"))
                ir = np.array(_open_pass(ir_bytes).convert("L"))
            skip = _ds.skip_reason(vis, ir)
            if skip:
                LAST_WARNINGS.append(skip)
                get_log().info("descratch skipped: %s", skip.split(":")[1].strip())
            else:
                with stage("descratch"):
                    cleaned = _ds.remove_defects(vis, ir)
        return _finalize(tiff_bytes, cleaned, a, out)
    finally:
        if LAST_LOG_PATH:
            log.info("scan log: %s", LAST_LOG_PATH)


def _save_array(arr, a, path):
    import numpy as np
    from PIL import Image
    
    # For 16-bit arrays, we need to use the correct mode
    if arr.dtype == np.uint16:
        # For TIFF, we can save 16-bit directly
        if a.format == "tiff":
            img = Image.fromarray(arr, mode='I;16')
            img.save(path)
        else:
            # For JPEG/PNG, convert to 8-bit
            arr_8bit = (arr / 256).astype(np.uint8)
            img = Image.fromarray(arr_8bit)
            if a.format == "jpeg":
                img.save(path, quality=95)
            else:
                img.save(path)
    else:
        # 8-bit array
        img = Image.fromarray(arr)
        if a.format == "jpeg":
            img.save(path, quality=95)
        else:
            img.save(path)


def invert_negative(arr):
    import numpy as np
    # Detect if 16-bit (uint16) or 8-bit
    is_16bit = arr.dtype == np.uint16
    max_val = 65535 if is_16bit else 255
    
    if is_16bit:
        inv = (max_val - arr).astype(np.float32)
    else:
        inv = (max_val - arr).astype(np.float32)
    
    if inv.ndim == 3:
        # Grauwelt-Abgleich: Farbstiche der Lampe (kalte Lampe scannt
        # rötlich, invertiert grünlich) auf neutrales Grau ziehen.
        means = inv.reshape(-1, inv.shape[2]).mean(axis=0)
        target = float(means.mean())
        for c in range(inv.shape[2]):
            if means[c] > 1:
                inv[..., c] *= target / means[c]
        inv = np.clip(inv, 0, max_val)
        # Eine gemeinsame Streckung über die Luminanz statt pro Kanal,
        # sonst zerlegt die Streckung den Grauwelt-Abgleich wieder.
        gray = inv.mean(axis=2)
        lo, hi = np.percentile(gray, 1), np.percentile(gray, 99)
        if hi > lo:
            inv = np.clip((inv - lo) * max_val / (hi - lo), 0, max_val)
    
    if is_16bit:
        return inv.astype(np.uint16)
    else:
        return inv.astype(np.uint8)


def denoise(arr, strength=10):
    """Wendet Non-Local Means Denoising auf das Bild an.
    
    Args:
        arr: numpy Array (H x W x 3 für RGB oder H x W für Grayscale)
        strength: Stärke der Denoising (0-100, höher = stärker)
    
    Returns:
        Denoised numpy Array
    """
    import cv2
    import numpy as np
    
    if strength <= 0:
        return arr
    
    # Detect if 16-bit
    is_16bit = arr.dtype == np.uint16
    
    # OpenCV requires 8-bit for denoising, so convert if needed
    if is_16bit:
        # Scale to 8-bit for processing
        arr_8bit = (arr / 256).astype(np.uint8)
    else:
        arr_8bit = arr
    
    if arr_8bit.ndim == 3:
        # Farbe: Konvertiere zu LAB für bessere Denoising-Ergebnisse
        lab = cv2.cvtColor(arr_8bit, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        
        # Denoising auf jeden Kanal anwenden
        h = max(1, strength * 10)
        l = cv2.fastNlMeansDenoising(l.astype(np.uint8), None, h=h, 
                                     templateWindowSize=7, searchWindowSize=21)
        a = cv2.fastNlMeansDenoising(a.astype(np.uint8), None, h=h, 
                                     templateWindowSize=7, searchWindowSize=21)
        b = cv2.fastNlMeansDenoising(b.astype(np.uint8), None, h=h, 
                                     templateWindowSize=7, searchWindowSize=21)
        
        result = cv2.merge((l, a, b))
        result = cv2.cvtColor(result, cv2.COLOR_LAB2RGB)
    else:
        # Grayscale
        result = cv2.fastNlMeansDenoising(arr_8bit.astype(np.uint8), None, 
                                       h=max(1, strength * 10),
                                       templateWindowSize=7, searchWindowSize=21)
    
    # Convert back to 16-bit if needed
    if is_16bit:
        return (result.astype(np.float32) * 256).astype(np.uint16)
    else:
        return result


def _finalize(tiff_bytes, cleaned, a, out):
    plain = a.format == "tiff" and not a.autocrop and not a.negative and not a.depth16
    if cleaned is None and plain:
        with stage("write-plain"):
            out.write_bytes(tiff_bytes)
        return [out]

    import numpy as np

    # For 16-bit mode, load as 16-bit
    use_16bit = getattr(a, "depth16", False)

    if cleaned is None:
        with stage("decode"):
            if use_16bit:
                # Load as 16-bit (PIL will auto-detect the mode from TIFF)
                img = _open_pass(tiff_bytes)
                # If the image is already 16-bit, keep it that way
                if img.mode in ('I;16', 'I;16B', 'I;16L'):
                    arr = np.array(img)
                else:
                    # Convert to 16-bit
                    arr = np.array(img.convert('I;16'))
            else:
                img = _open_pass(tiff_bytes)
                # Ein Graustufen-Scan hat einen Kanal. Ihn auf RGB
                # aufzublasen verdreifacht Datei und Arbeitsspeicher,
                # ohne ein Bit Information hinzuzufügen. Die Quelle
                # entscheidet, nicht eine feste Annahme.
                target = "L" if img.mode in ("L", "1") else "RGB"
                arr = np.array(img.convert(target))
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
                with stage(f"crop-{i}"):
                    if a.negative:
                        crop = invert_negative(crop)
                    # Denoising anwenden
                    denoise_strength = getattr(a, "denoise", 0)
                    if denoise_strength > 0:
                        crop = denoise(crop, denoise_strength)
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
        with stage("invert"):
            arr = invert_negative(arr)
    # Denoising anwenden (für nicht-gesplittete Bilder)
    denoise_strength = getattr(a, "denoise", 0)
    if denoise_strength > 0:
        with stage("denoise"):
            arr = denoise(arr, denoise_strength)
    with stage("save"):
        _save_array(arr, a, out)
    return [out]


def install_signal_handlers():
    """Ctrl-C und SIGTERM sollen den Scanner freigeben, nicht nur uns.

    Ohne das beendet ein Signal nur den Python-Prozess und laesst
    scanimage als Waise zurueck: es haelt weiter das USB-Geraet, bewegt
    weiter den Schlitten, und der naechste Versuch laeuft in "Scanner
    not found or busy". Nur fuer die CLI - die Oberflaeche hat ihren
    Stop-Knopf.
    """
    import signal

    def handler(signum, frame):
        # Nur ausloesen. Das Warten passiert im Hintergrund, und den
        # Abbruch meldet _run_pass, sobald der Pass zurueckkommt.
        get_log().info("signal %s received, cancelling the scan", signum)
        cancel_scan(wait=False)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    install_signal_handlers()
    
    # Handle --list-devices
    if a.list_devices:
        from discovery import ScannerDiscovery
        # Pass the SCANIMAGE path to discovery
        disc = ScannerDiscovery(str(SCANIMAGE))
        devices = disc.list_devices()
        if not devices:
            print("No SANE scanners found.", file=sys.stderr)
            return 1
        print("Available SANE scanners:")
        for i, device in enumerate(devices, 1):
            status = f" [{device.support_status}]" if device.support_status != "untested" else ""
            print(f"  {i}. {device.name} ({device.backend}){status}")
            print(f"     Device: {device.device_file}")
        return 0
    
    try:
        outs = run_scan(a)
    except ScanCancelled:
        # Kein Fehler, sondern eine Ansage. 130 ist die uebliche Antwort
        # auf ein Abbruchsignal.
        print("scan8600: cancelled, the scanner was released cleanly.",
              file=sys.stderr)
        return 130
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
