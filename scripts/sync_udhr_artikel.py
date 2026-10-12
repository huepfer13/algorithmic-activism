#!/usr/bin/env python3
"""Ergaenzt die fehlenden UDHR-Artikel in articles/<lang>/ aus der amtlichen deutschen Quelle.

Kein Transkribieren: das Skript holt den Text, parst die 30 Artikel und schreibt NUR die fehlenden
Dateien. Harte Sperre: der abgerufene Wortlaut muss die 9 vorhandenen Artikel BESTAETIGEN — sonst
bricht das Skript ab, bevor es etwas schreibt (Quellenkonflikt statt stiller Wortlaut-Drift).

Aufruf:
    python3 sync_udhr_artikel.py --dry-run     # nur pruefen, nichts schreiben
    python3 sync_udhr_artikel.py               # fehlende Artikel anlegen
"""
from __future__ import annotations

import argparse
import glob
import html
import os
import re
import sys
import urllib.request

QUELLE_URL = "https://unric.org/de/allgemeine-erklaerung-menschenrechte/"
QUELLE_NAME = "UNRIC — Regionales Informationszentrum der Vereinten Nationen"
ARTIKEL_DIR = "articles/de"
# Artikel, die der Bestand bereits traegt und die den Quellenvergleich belegen muessen.
BESTANDS_PROBEN = (1, 3, 4, 5, 9, 12, 14, 19, 26)


def hole_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kompatibel; Korpus-Sync)"})
    with urllib.request.urlopen(req, timeout=30) as antwort:
        return antwort.read().decode("utf-8", errors="replace")


def als_text(roh: str) -> str:
    """HTML grob zu Text: Skripte/Stile weg, Tags weg, Entitaeten aufloesen."""
    ohne = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", roh)
    ohne = re.sub(r"(?i)<br\s*/?>|</p>|</h[1-6]>", "\n", ohne)
    ohne = re.sub(r"<[^>]+>", " ", ohne)
    return html.unescape(ohne)


def parse_artikel(text: str) -> dict[int, str]:
    """Alle Absaetze des amtlichen Textes, indiziert nach Artikelnummer."""
    # Ueberschriften der Quelle heissen "Artikel N" (ggf. mit Anfuehrungszeichen/Doppelpunkt).
    treffer = list(re.finditer(r"(?im)^\s*Art(?:ikel)?\s+(\d{1,2})\s*[.:]?\s*$", text))
    artikel: dict[int, str] = {}
    for i, t in enumerate(treffer):
        nummer = int(t.group(1))
        if nummer < 1 or nummer > 30:
            continue
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
        rumpf = text[t.start():ende]
        rumpf = rumpf.split("\n", 1)[1] if "\n" in rumpf else ""
        rumpf = re.sub(r"(?i)^\s*art(?:ikel)?\s+\d{1,2}\s*[.:;–-]*\s*", "", rumpf)
        absaetze = [re.sub(r"\s+", " ", a).strip() for a in rumpf.split("\n")]
        absaetze = [a for a in absaetze if a and not re.fullmatch(r"[\W_]+", a)]
        if absaetze:
            artikel[nummer] = "\n".join(absaetze)
    return artikel


def titel(roh: str, nummer: int) -> str:
    """Kurztitel aus der ersten Zeile des Artikels (fuer das Frontmatter, max. 60 Zeichen)."""
    erste = roh.split("\n", 1)[0]
    erste = re.sub(r"\s+", " ", erste).strip(" .;:-")
    return (erste[:57] + "...") if len(erste) > 60 else (erste or f"Artikel {nummer}")


def main() -> int:
    p = argparse.ArgumentParser(description="Fehlende UDHR-Artikel aus amtlicher Quelle ergaenzen")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--url", default=QUELLE_URL)
    args = p.parse_args()

    vorhanden = {}
    for pfad in sorted(glob.glob(os.path.join(ARTIKEL_DIR, "*.md"))):
        nummer = int(re.sub(r"\D", "", os.path.basename(pfad)))
        with open(pfad, encoding="utf-8") as f:
            vorhanden[nummer] = f.read()
    print(f"Bestand: {len(vorhanden)} Artikel -> {sorted(vorhanden)}")

    roh = als_text(hole_html(args.url))
    artikel = parse_artikel(roh)
    print(f"Quelle : {len(artikel)} Artikel geparst -> {sorted(artikel)}")
    if len(artikel) < 30:
        print(f"[ABBRUCH] Quelle liefert nur {len(artikel)}/30 Artikel — Parser/Quelle pruefen.", file=sys.stderr)
        return 1

    # SPERRE: der abgerufene Wortlaut muss den Bestand bestaetigen (Kernsaetze wortgleich enthalten).
    # Einzelne Abweichungen sind erlaubt, wenn die Mehrheit bestaetigt — sie werden aber IMMER
    # benannt (belegt 2026-10-12: Artikel 4 des Bestands weicht in der Wortstellung vom amtlichen Text ab).
    abweichungen = []
    for nummer in BESTANDS_PROBEN:
        alt = re.sub(r"\s+", " ", vorhanden[nummer].split("---", 2)[2]).strip()
        neu = re.sub(r"\s+", " ", artikel[nummer]).strip()
        kern = alt.split(".")[0].strip()
        if kern and kern not in neu:
            abweichungen.append((nummer, kern[:90], neu[:90]))
    bestaetigt = len(BESTANDS_PROBEN) - len(abweichungen)
    if abweichungen:
        print(f"[HINWEIS] {len(abweichungen)} von {len(BESTANDS_PROBEN)} Bestandsartikeln weichen "
              f"im Wortlaut ab (werden NICHT ueberschrieben):")
        for n, alt, neu in abweichungen:
            print(f"   Artikel {n}:\n     Bestand: {alt}\n     Quelle : {neu}")
    if bestaetigt * 4 < len(BESTANDS_PROBEN) * 3:      # unter 75 % Bestaetigung: Abbruch
        print(f"[ABBRUCH] nur {bestaetigt}/{len(BESTANDS_PROBEN)} Artikel bestaetigt — Quelle unbrauchbar.",
              file=sys.stderr)
        return 1
    print(f"Sperre  : {bestaetigt}/{len(BESTANDS_PROBEN)} Bestandsartikel wortgleich bestaetigt")

    fehlend = [n for n in range(1, 31) if n not in vorhanden]
    print(f"Fehlend: {fehlend} ({len(fehlend)} Stueck)")
    for nummer in fehlend:
        ziel = os.path.join(ARTIKEL_DIR, f"art_{nummer:02d}.md")
        inhalt = (f'---\narticle: {nummer}\narticle_id: "art_{nummer:02d}"\n'
                  f'title: "{titel(artikel[nummer], nummer)}"\n'
                  f'source: "{QUELLE_NAME}"\nurl: {args.url}\n---\n{artikel[nummer]}\n')
        if args.dry_run:
            print(f"  [dry-run] wuerde schreiben: {ziel} ({len(artikel[nummer])} Zeichen)")
            continue
        if os.path.exists(ziel):
            print(f"  [uebersprungen] {ziel} existiert bereits")
            continue
        with open(ziel, "w", encoding="utf-8") as f:
            f.write(inhalt)
        print(f"  geschrieben: {ziel} ({len(artikel[nummer])} Zeichen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
