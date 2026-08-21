"""Parst 'scanimage -A'-Ausgabe in strukturierte Optionsbeschreibungen.

Nur stdlib — das Modul wird auch vom GIMP-Plugin (eigener Python-
Interpreter ohne unsere venv) importiert.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Option:
    name: str
    kind: str                      # "choice" | "range" | "bool"
    default: str = ""
    unit: str = ""
    choices: list = field(default_factory=list)
    lo: float = 0.0
    hi: float = 0.0

_LINE = re.compile(r"^\s+(-{1,2}[\w-]+)(\[=\(yes\|no\)\])?\s+(.*?)\s*"
                   r"(?:\[([^\]]*)\])?\s*$")
# scanimage hängt bei quantisierten Bereichen ein "(in steps of N)" an,
# z.B. "--brightness -100..100 (in steps of 1)". Ohne diesen Zusatz im
# Muster fällt die Option komplett aus der Liste - und wer sie gegen
# die Liste prüft, hält sie fälschlich für nicht unterstützt.
_RANGE = re.compile(r"^(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)"
                    r"([a-z%]*)(?:\s*\(in steps of\s*[\d.]+\))?$")
_UNIT = re.compile(r"(dpi|mm|%)$")


def parse(text):
    opts = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        name, boolflag, spec, default = m.groups()
        default = (default or "").strip()
        if boolflag or spec in ("(yes|no)", ""):
            opts.append(Option(name, "bool", default or "no"))
            continue
        r = _RANGE.match(spec)
        if r:
            lo, hi, unit = r.groups()
            opts.append(Option(name, "range", default, unit,
                               lo=float(lo), hi=float(hi)))
            continue
        if "|" in spec:
            unit = ""
            um = _UNIT.search(spec)
            if um and not spec.endswith(um.group(1) + "|"):
                unit = um.group(1)
                spec = spec[: -len(unit)]
            choices = [c.strip() for c in spec.split("|") if c.strip()]
            opts.append(Option(name, "choice", default, unit, choices))
    return opts
