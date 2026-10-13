#!/usr/bin/env python3
"""validate_locale.py — deterministisches Abnahme-Gate für locales/<lang>.json.

Prüft jede Sprachdatei gegen die Regeln aus locales/README.md, mit locales/de.json als
Wahrheitsquelle für die Booleschen Schranken. Aufruf:

    python3 scripts/validate_locale.py                # alle Locales außer de (Referenz)
    python3 scripts/validate_locale.py es fr          # nur diese
    python3 scripts/validate_locale.py --alle         # auch de.json prüfen

Exit 0 = alle geprüften Dateien vertragskonform. Exit 1 = mindestens ein HARTES Problem.
WARNUNGEN machen den Exit nicht rot (z. B. Handbuch-Genre ohne eigenes Schema), werden
aber mit Grund ausgewiesen — genau dieser Punkt hat in es.json/fr.json einen deutschen
Stempel in einem fremdsprachigen Buch erzeugt.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ERLAUBTE_FLAGS = {"manual_ending", "erlaube_rede", "erlaube_emotion", "figuren_verboten",
                  "code_praefix", "zustaende", "block_schema", "stanza_zeilen"}
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c]")


def hart(fehler: list, warnungen: list, bedingung: bool, text: str, warnung: bool = False) -> None:
    if not bedingung:
        (warnungen if warnung else fehler).append(text)


def pruefe(datei: str, referenz: dict) -> tuple[list, list]:
    fehler: list = []
    warnungen: list = []
    try:
        loc = json.load(open(datei, encoding="utf-8"))
    except Exception as ex:
        return [f"nicht lesbar: {type(ex).__name__}: {ex}"], []

    name = loc.get("language_code") or os.path.basename(datei).split(".")[0].upper()
    ist_de = name == "DE"
    stile = loc.get("styles", {})
    regeln = loc.get("style_rules", {})
    flags_map = loc.get("style_flags", {})

    # 1. Kopfzeilen
    if not ist_de:
        hart(fehler, warnungen, bool(loc.get("instruction_language")),
             "instruction_language fehlt — der Buchmodus bricht dann ab (generate_pipeline.py:368)")
    for feld in ("language_code", "language_name", "core_guardrail"):
        hart(fehler, warnungen, bool(loc.get(feld)), f"Kopfzeile {feld} fehlt")

    # 2. Umfang gegen den deutschen Katalog
    if not ist_de:
        hart(fehler, warnungen, len(stile) >= len(referenz["styles"]),
             f"nur {len(stile)} Stile gegen {len(referenz['styles'])} im DE-Katalog")
        hart(fehler, warnungen, len(flags_map) >= len(referenz["style_flags"]),
             f"nur {len(flags_map)} style_flags gegen {len(referenz['style_flags'])}")

    # 3. Je Stil: Flags, Platzhalter, Zustandsworte, Formatierbarkeit
    ohne_schema = []
    for stil, f in flags_map.items():
        unbekannt = set(f) - ERLAUBTE_FLAGS
        hart(fehler, warnungen, not unbekannt,
             f"{stil}: unbekannte Flag-Schluessel {sorted(unbekannt)} (werden still ignoriert)")
        schema = f.get("block_schema")
        if not schema:
            ohne_schema.append(stil)
            continue
        hart(fehler, warnungen, "{zustand}" in schema and "{code}" in schema,
             f"{stil}: Schema ohne {{zustand}}/{{code}}-Platzhalter")
        hart(fehler, warnungen, not BIDI.search(schema), f"{stil}: Bidi-Steuerzeichen im Schema")
        label = re.match(r"^\*{0,2}\[([^:\]]{3,24}):", schema)
        label_ok = bool(label) and bool(re.fullmatch(r"[A-Za-zÄÖÜäöü\-]{3,24}", label.group(1)))
        hart(fehler, warnungen, label_ok,
             f"{stil}: erstes Label verletzt die Klasse [A-Za-zÄÖÜäöü-]{3,24} (keine Akzente, keine Unterstriche)")
        zust = f.get("zustaende") or []
        hart(fehler, warnungen, len(zust) == 4, f"{stil}: {len(zust)} Zustandsworte statt 4")
        hart(fehler, warnungen, all(" " not in z for z in zust), f"{stil}: Leerzeichen in einem Zustandswort")
        praefix = f.get("code_praefix")
        hart(fehler, warnungen, isinstance(praefix, str) and len(praefix) == 1,
             f"{stil}: code_praefix kein Einzelzeichen ({praefix!r})")
        if "{zustand}" in schema and "{code}" in schema and zust:
            try:
                schema.format(zustand=zust[0], code=f"{praefix or 'E'}-01-01")
            except Exception as ex:
                hart(fehler, warnungen, False, f"{stil}: Schema nicht formatierbar ({type(ex).__name__})")
    if ohne_schema:
        grund = ("DE-Referenz, Code-Default ist der kanonische Handbuchstempel" if ist_de else
                 "ohne Schema faellt status_block auf den DEUTSCHEN Defaultblock zurueck — "
                 "in einem fremdsprachigen Buch ein stiller Sprach-Fallback")
        warnungen.append(f"{len(ohne_schema)} Stil(e) ohne block_schema: {ohne_schema} — {grund}")

    # 4. Schranken-Semantik eins zu eins gegen de.json
    if not ist_de:
        verboten_soll = sum(1 for v in referenz["style_flags"].values() if v.get("figuren_verboten"))
        verboten_ist = sum(1 for v in flags_map.values() if v.get("figuren_verboten"))
        hart(fehler, warnungen, verboten_ist == verboten_soll,
             f"figuren_verboten {verboten_ist}x statt {verboten_soll}x (DE)")
        ohne_regeln_soll = len([k for k in referenz["styles"] if k not in referenz["style_rules"]])
        ohne_regeln_ist = len([k for k in stile if k not in regeln])
        hart(fehler, warnungen, ohne_regeln_ist == ohne_regeln_soll,
             f"{ohne_regeln_ist} Stile ohne Regeln statt {ohne_regeln_soll} (DE)")
    for stil in stile:
        hart(fehler, warnungen, bool(stile[stil]), f"{stil}: leere Beschreibung")

    # 5. Laedt die Pipeline die Datei?
    try:
        from generate_pipeline import load_locale
        hart(fehler, warnungen, bool(load_locale(name)["styles"]), "load_locale liefert keine Stile")
    except Exception as ex:
        hart(fehler, warnungen, False, f"load_locale('{name}') scheitert: {type(ex).__name__}: {ex}")

    return fehler, warnungen


def main() -> int:
    ap = argparse.ArgumentParser(description="Abnahme-Gate fuer locales/<lang>.json")
    ap.add_argument("sprachen", nargs="*", help="Sprachkuerzel (Default: alle ausser de)")
    ap.add_argument("--alle", action="store_true", help="auch de.json pruefen")
    args = ap.parse_args()

    referenz = json.load(open(os.path.join(REPO, "locales", "de.json"), encoding="utf-8"))
    dateien = sorted(p for p in glob.glob(os.path.join(REPO, "locales", "*.json")) if ".bak-" not in p)
    fehlend = []
    if args.sprachen:
        wunsch = {s.lower() for s in args.sprachen}
        dateien = [p for p in dateien if os.path.basename(p).split(".")[0] in wunsch]
        vorhanden = {os.path.basename(p).split(".")[0] for p in dateien}
        # Eine angeforderte, aber nicht vorhandene Sprache darf NICHT als Gutfall durchgehen:
        # ohne diese Pruefung liefe die Schleife leer und das Gate meldete Exit 0.
        fehlend = sorted(wunsch - vorhanden)
    elif not args.alle:
        dateien = [p for p in dateien if os.path.basename(p) != "de.json"]

    gesamt_fehler = len(fehlend)
    for sprache in fehlend:
        print(f"    FEHLER   locales/{sprache}.json existiert nicht — angeforderte Sprache fehlt")
    print(f"{'Datei':10s} {'Stile':>5s} {'Regeln':>6s} {'Flags':>5s}  Urteil")
    for p in dateien:
        fehler, warnungen = pruefe(p, referenz)
        loc = {}
        try:
            loc = json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
        urteil = "OK" if not fehler else "FEHLER"
        print(f"{os.path.basename(p):10s} {len(loc.get('styles', {})):5d} {len(loc.get('style_rules', {})):6d} "
              f"{len(loc.get('style_flags', {})):5d}  {urteil}"
              + ("" if not warnungen else f" (+{len(warnungen)} Warnung)"))
        for f in fehler:
            print(f"    FEHLER   {f}")
        for w in warnungen:
            print(f"    WARNUNG  {w}")
        gesamt_fehler += len(fehler)

    print()
    print("Ergebnis:", "vertragskonform" if gesamt_fehler == 0 else f"{gesamt_fehler} harte Verstoesse")
    return 1 if gesamt_fehler else 0


if __name__ == "__main__":
    sys.exit(main())
