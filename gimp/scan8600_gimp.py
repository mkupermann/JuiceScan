#!/usr/bin/env python3
"""GIMP-3-Plugin: Scannen mit dem Canon CanoScan 8600F.

Erkennt den Scanner über den mitgelieferten Treiber-Stack, zeigt alle
Treiberoptionen dynamisch an (aus 'scanimage -A' geparst) und lädt das
Ergebnis als neues Bild in GIMP. Kratzerentfernung und Größenerkennung
laufen über die scan8600-CLI aus demselben Paket.

Installation: siehe gimp/INSTALL.md. Das Plugin braucht den installierten
Stack (macOS: /usr/local/canoscan8600f, sonst SCAN8600_PREFIX setzen).
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gimp, GimpUi, Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanoptions  # noqa: E402

# Diese Optionen bildet die Standard-Seite ab, die Erweitert-Seite
# zeigt alle übrigen.
STANDARD = {"--source", "--resolution", "--mode"}
PROC_NAME = "plug-in-scan8600"


def _prefix():
    env = os.environ.get("SCAN8600_PREFIX")
    if env:
        return pathlib.Path(env)
    if sys.platform == "win32":
        return pathlib.Path.home() / "canoscan" / "prefix"
    return pathlib.Path("/usr/local/canoscan8600f")


def _bin(name):
    exe = name + (".exe" if sys.platform == "win32" else "")
    return _prefix() / "bin" / exe


def _env():
    env = dict(os.environ)
    env["SANE_CONFIG_DIR"] = str(_prefix() / "etc" / "sane.d")
    env["SCAN8600_PREFIX"] = str(_prefix())
    return env


def _run(cmd):
    return subprocess.run(cmd, env=_env(), capture_output=True)


class Scan8600(Gimp.PlugIn):
    def do_query_procedures(self):
        return [PROC_NAME]

    def do_create_procedure(self, name):
        proc = Gimp.Procedure.new(self, name, Gimp.PDBProcType.PLUGIN,
                                  self.run, None)
        proc.set_menu_label("CanoScan 8600F…")
        proc.add_menu_path("<Image>/File/Create")
        proc.set_documentation(
            "Scannen mit dem Canon CanoScan 8600F",
            "Flachbett und Durchlicht, alle Treiberoptionen, "
            "Kratzerentfernung per Infrarot, Größenerkennung.",
            name)
        proc.set_attribution("Michael Kupermann", "Michael Kupermann", "2026")
        return proc

    # --- Dialog -----------------------------------------------------------
    def _error(self, text):
        d = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.OK, text=text)
        d.run()
        d.destroy()

    def _build_dialog(self, options):
        GimpUi.init(PROC_NAME)
        dlg = Gtk.Dialog(title="CanoScan 8600F")
        dlg.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        dlg.add_button("Scannen", Gtk.ResponseType.OK)
        nb = Gtk.Notebook()
        dlg.get_content_area().pack_start(nb, True, True, 8)
        widgets = {}

        def grid():
            g = Gtk.Grid(column_spacing=8, row_spacing=6,
                         margin_top=10, margin_bottom=10,
                         margin_start=10, margin_end=10)
            return g

        def add_row(g, row, label, widget):
            g.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            g.attach(widget, 1, row, 1, 1)

        def widget_for(opt):
            if opt.kind == "choice":
                w = Gtk.ComboBoxText()
                for c in opt.choices:
                    w.append_text(c)
                if opt.default in opt.choices:
                    w.set_active(opt.choices.index(opt.default))
                else:
                    w.set_active(0)
                return w
            if opt.kind == "range":
                adj = Gtk.Adjustment(lower=opt.lo, upper=opt.hi,
                                     step_increment=1)
                w = Gtk.SpinButton(adjustment=adj, digits=0)
                try:
                    w.set_value(float(opt.default))
                except ValueError:
                    w.set_value(opt.lo)
                return w
            w = Gtk.CheckButton()
            w.set_active(opt.default == "yes")
            return w

        std = grid()
        row = 0
        for opt in options:
            if opt.name in STANDARD:
                w = widget_for(opt)
                widgets[opt.name] = (opt, w)
                title = {"--source": "Quelle", "--resolution":
                         "Auflösung (dpi)", "--mode": "Farbe"}[opt.name]
                add_row(std, row, title, w)
                row += 1
        ck_descratch = Gtk.CheckButton(label="Kratzer entfernen (Infrarot)")
        ck_autocrop = Gtk.CheckButton(label="Größe automatisch erkennen")
        ck_split = Gtk.CheckButton(label="Fotos einzeln speichern")
        for w in (ck_descratch, ck_autocrop, ck_split):
            std.attach(w, 0, row, 2, 1)
            row += 1
        nb.append_page(std, Gtk.Label(label="Standard"))

        adv = grid()
        row = 0
        for opt in options:
            if opt.name in STANDARD:
                continue
            w = widget_for(opt)
            widgets[opt.name] = (opt, w)
            add_row(adv, row, opt.name.lstrip("-"), w)
            row += 1
        sc = Gtk.ScrolledWindow()
        sc.set_min_content_height(360)
        sc.add(adv)
        nb.append_page(sc, Gtk.Label(label="Erweitert"))

        dlg.show_all()
        return dlg, widgets, ck_descratch, ck_autocrop, ck_split

    @staticmethod
    def _value(opt, w):
        if opt.kind == "choice":
            return w.get_active_text()
        if opt.kind == "range":
            return str(int(w.get_value()))
        return "yes" if w.get_active() else "no"

    # --- Ablauf -----------------------------------------------------------
    def run(self, procedure, args, run_data):
        scanimage = _bin("scanimage")
        cli = _bin("scan8600")
        if not scanimage.exists() or not cli.exists():
            self._error("Treiber-Stack nicht gefunden unter "
                        f"{_prefix()}. Erst install.sh aus der DMG "
                        "ausführen oder SCAN8600_PREFIX setzen.")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

        probe = _run([str(scanimage), "-L"])
        if b"genesys" not in probe.stdout:
            self._error("Kein CanoScan 8600F gefunden. USB prüfen.")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

        opts_out = _run([str(scanimage), "-A"])
        options = scanoptions.parse(opts_out.stdout.decode(errors="replace"))

        dlg, widgets, ck_descratch, ck_autocrop, ck_split = \
            self._build_dialog(options)
        response = dlg.run()
        if response != Gtk.ResponseType.OK:
            dlg.destroy()
            return procedure.new_return_values(
                Gimp.PDBStatusType.CANCEL, GLib.Error())

        source_opt, source_w = widgets["--source"]
        source = self._value(source_opt, source_w) or "Flatbed"
        mode_opt, mode_w = widgets["--mode"]
        res_opt, res_w = widgets["--resolution"]
        out = pathlib.Path(tempfile.mkdtemp()) / "scan.tiff"
        cmd = [str(cli),
               "--mode", "film" if "Transparency" in source else "flatbed",
               "--dpi", self._value(res_opt, res_w),
               "--format", "tiff", "--output", str(out)]
        if self._value(mode_opt, mode_w) == "Gray":
            cmd.append("--gray")
        if ck_descratch.get_active() and "Transparency" in source:
            cmd.append("--descratch")
        if ck_autocrop.get_active():
            cmd.append("--autocrop")
            if ck_split.get_active():
                cmd.append("--split")
        for name, (opt, w) in widgets.items():
            if name in STANDARD:
                continue
            val = self._value(opt, w)
            if val != opt.default:
                cmd += ["--sane-opt", f"{name.lstrip('-')}={val}"]
        dlg.destroy()

        r = _run(cmd)
        if r.returncode != 0:
            self._error("Scan fehlgeschlagen:\n"
                        + r.stderr.decode(errors="replace"))
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

        for line in r.stdout.decode().splitlines():
            p = line.strip()
            if p and pathlib.Path(p).exists():
                image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,
                                       Gio.File.new_for_path(p))
                Gimp.Display.new(image)
        Gimp.displays_flush()
        return procedure.new_return_values(
            Gimp.PDBStatusType.SUCCESS, GLib.Error())


Gimp.main(Scan8600.__gtype__, sys.argv)
