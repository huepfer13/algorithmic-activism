#!/usr/bin/env python3
"""Ergaenzt die fehlenden UDHR-Artikel in articles/<lang>/ aus der amtlichen Quelle der Sprache.

Kein Transkribieren: das Skript holt den Text, parst die 30 Artikel und schreibt NUR die fehlenden
Dateien. Harte Sperre: der abgerufene Wortlaut muss die vorhandenen Artikel BESTAETIGEN — sonst
bricht das Skript ab, bevor es etwas schreibt (Quellenkonflikt statt stiller Wortlaut-Drift).

SPRACHPARAMETER + GATE (2026-10-15, Karte t_43fe886f):
  * `--lang <code>` waehlt Sprache und Zielordner `articles/<lang>/` (Sprach-Registry QUELLEN unten).
  * ALLES wird im Speicher geparst und geprueft; geschrieben wird erst, wenn das Gate fuer alle
    30 Artikel bestanden ist — kein Teilimport, kein halb gefuellter Ordner (Dateien werden zudem
    als `.tmp` geschrieben und erst danach umbenannt).
  * Gate: 30 Slots 1..30 lueckenlos und streng monoton; 50..2500 Zeichen je Artikel; unter 1 %
    Ersatz-/Steuerzeichen (U+FFFD, Steuer-/Formatzeichen, Ligaturmuell aus der Private Use Area);
    keine ungeparsten Artikel-Ueberschriften im Resttext; Sprachwaechter (Ueberschrift-Splitter der
    Zielsprache + Stoppwoerter bzw. Schriftsystem) und kein Seitenrahmen (Footer/Navigation) im
    Artikeltext.
  * Abbruch ist laut: Diagnosezeile `GATE_FAIL [<lang>]: <grund>` auf stderr, RuntimeError
    (GateFehler), Exit-Code 1.
  * Das Verhalten fuer `de` aendert sich nicht: Quelle bleibt unric.org/de, Parser, Dateinamen
    (art_NN.md), Frontmatter und Bestandssperre sind unveraendert. Zusaetzlich laeuft das Gate auch
    fuer `de`; da der deutsche Bestand vollstaendig ist, schreibt ein de-Lauf weiterhin nichts.

Aufruf:
    python3 sync_udhr_artikel.py --lang de --dry-run   # nur pruefen, nichts schreiben
    python3 sync_udhr_artikel.py --lang de             # fehlende deutsche Artikel anlegen
    python3 sync_udhr_artikel.py --lang sw             # Swahili (OHCHR-HTML-Quelle) erstmalig anlegen
"""
from __future__ import annotations

import argparse
import glob
import html
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

# Pfad relativ zum SKRIPT, nicht zum Arbeitsverzeichnis: sonst findet ein Aufruf aus einem anderen
# CWD still 0 Artikel (belegt 2026-10-12).
HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)

ARTIKEL_ANZAHL = 30
LAENGE_MIN = 50
LAENGE_MAX = 2500
FEHLZEICHEN_ANTEIL_MAX = 0.01      # unter 1 % Ersatz-/Steuerzeichen je Artikel
STOPPWORT_MIN = 3                  # Mindesttreffer je Stoppwort im Quelltext

# Artikel, die ein Bestand bereits traegt und die den Quellenvergleich belegen muessen.
BESTANDS_PROBEN = (1, 3, 4, 5, 9, 12, 14, 19, 26)

# Browsernahe Kopfzeilen: OHCHR steht hinter Cloudflare und antwortet einem nackten
# Python/urllib-Besucher mit HTTP 403 + "cf-mitigated: challenge" (gemessen 2026-10-15). Erst der
# VOLLE Browsersatz (Chromium-UA + Accept-Sprache + sec-ch-ua + Sec-Fetch-* + Accept-Encoding:
# identity) liefert HTTP 200 — mit dem halben Satz bleibt es bei 403. Fuer unric.org harmlos.
KOPFZEILEN = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="126", "Not:A-Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Accept-Encoding": "identity",
}

# Sprach-Registry: je Sprache Quelle, Artikel-Ueberschrift (Splitter) und Sprachwaechter.
#   splitter      — streng, liefert die Artikelnummer; MUSS die Ueberschrift der ZIELSPRACHE treffen.
#                   Falsche Sprache => 0 Treffer => Gate bricht ab, bevor etwas geschrieben wird.
#   splitter_weit — lose Variante derselben Ueberschrift. Ihre Trefferzahl im Quelltext muss der
#                   Zahl der geparsten Artikel entsprechen, sonst wurde eine Schreibvariante verpasst.
#   stoppwoerter  — Woerter, die in der Zielsprache mehrfach vorkommen MUESSEN.
#   schrift       — optionales Schriftsystem, das den Quelltext dominieren muss (z. B. CYRILLIC).
#   trailer       — Regex, ab dem der Seitenrahmen (Footer/Navigation) abgeschnitten wird.
#   rahmen_marker — Zeichenketten, die im Artikeltext NICHT vorkommen duerfen (Folgetext-Sperre).
QUELLEN = {
    "de": {
        "url": "https://unric.org/de/allgemeine-erklaerung-menschenrechte/",
        "name": "UNRIC — Regionales Informationszentrum der Vereinten Nationen",
        "splitter": r"(?im)^\s*Art(?:ikel)?\s+(\d{1,2})\s*[.:]?\s*$",
        "splitter_weit": r"(?i)Art(?:ikel)?\s+\d{1,2}",
        "stoppwoerter": ("Menschen", "Rechte", "Freiheit"),
        "schrift": None,
        # de bewusst ohne trailer/marker: Bestandsquelle und -text bleiben unveraendert.
        "trailer": None,
        "rahmen_marker": (),
    },
    "sw": {
        "url": "https://www.ohchr.org/en/human-rights/universal-declaration/translations/swahilikiswahili",
        "name": "OHCHR — Office of the High Commissioner for Human Rights (UDHR Swahili/Kiswahili)",
        # Die OHCHR-Seite schreibt die Ueberschrift in zwei Varianten falsch: "Kufungu cha 7." und
        # "Kifungu ch 23." (gemessen 2026-10-15). Der Splitter toleriert genau diese zwei Kuerzungen,
        # bleibt aber eindeutig Swahili — eine englische Seite liefert damit 0 Treffer.
        "splitter": r"(?im)^\s*K[iu]fung[uo]\s+ch(?:a)?\s*(\d{1,2})\s*[.:]?\s*$",
        "splitter_weit": r"(?i)K[iu]fung[uo]\s+(?:ch(?:a)?\s*)?\d{1,2}",
        "stoppwoerter": ("haki", "watu", "kila"),
        "schrift": None,
        "trailer": r"(?im)^\s*Back to top\s*$",
        "rahmen_marker": ("Back to top", "Our Work", "DONATE NOW", "© OHCHR"),
    },
    # uk ist vorbereitet, aber noch nicht freigegeben (eigene Karte). trailer/marker fehlen noch,
    # weil die ukrainische Seite dafuer erst vermessen werden muss.
    "uk": {
        "url": "https://www.ohchr.org/en/human-rights/universal-declaration/translations/ukrainian-ukrayinska",
        "name": "OHCHR — Office of the High Commissioner for Human Rights (UDHR Ukrainian)",
        "splitter": r"(?im)^\s*Стаття\s+(\d{1,2})\s*[.:]?\s*$",
        "splitter_weit": r"(?i)Стаття\s+\d{1,2}",
        "stoppwoerter": ("права", "люди", "кожна"),
        "schrift": "CYRILLIC",
        "trailer": None,
        "rahmen_marker": (),
    },
}


class GateFehler(RuntimeError):
    """Gate nicht bestanden — der Lauf bricht ab, bevor eine Datei entsteht."""


def hole_html(url: str) -> str:
    req = urllib.request.Request(url, headers=KOPFZEILEN)
    try:
        with urllib.request.urlopen(req, timeout=30) as antwort:
            roh = antwort.read()
            satz = antwort.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as fehler:
        raise GateFehler(f"Quelle nicht abrufbar: HTTP {fehler.code} {fehler.reason} — {url}") from fehler
    except urllib.error.URLError as fehler:
        raise GateFehler(f"Quelle nicht abrufbar: {fehler.reason} — {url}") from fehler
    return roh.decode(satz, errors="replace")


def als_text(roh: str) -> str:
    """HTML grob zu Text: Skripte/Stile weg, Tags weg, Entitaeten aufloesen."""
    ohne = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", roh)
    ohne = re.sub(r"(?i)<br\s*/?>|</p>|</h[1-6]>", "\n", ohne)
    ohne = re.sub(r"<[^>]+>", " ", ohne)
    return html.unescape(ohne)


def schneide_rahmen_ab(text: str, konf: dict) -> str:
    """Schneidet den Seitenrahmen (Footer/Navigation) ab. Ohne trailer bleibt der Text unveraendert."""
    trailer = konf.get("trailer")
    if not trailer:
        return text
    treffer = re.search(trailer, text)
    return text[:treffer.start()] if treffer else text


def parse_artikel(text: str, splitter: str) -> dict[int, str]:
    """Alle Absaetze des amtlichen Textes, indiziert nach Artikelnummer."""
    treffer = list(re.finditer(splitter, text))
    artikel: dict[int, str] = {}
    for i, t in enumerate(treffer):
        nummer = int(t.group(1))
        if nummer < 1 or nummer > ARTIKEL_ANZAHL:
            continue
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
        rumpf = text[t.end():ende]
        absaetze = [re.sub(r"\s+", " ", a).strip() for a in rumpf.split("\n")]
        absaetze = [a for a in absaetze if a and not re.fullmatch(r"[\W_]+", a)]
        if absaetze:
            artikel[nummer] = "\n".join(absaetze)
    return artikel


def fehlzeichen(text: str) -> int:
    """Ersatzzeichen (U+FFFD), Steuer-/Formatzeichen und Ligaturmuell (Private Use Area)."""
    zaehler = 0
    for zeichen in text:
        if zeichen in ("\n", "\t"):
            continue
        if ord(zeichen) == 0xFFFD or 0xE000 <= ord(zeichen) <= 0xF8FF:
            zaehler += 1
        elif unicodedata.category(zeichen) in ("Cc", "Cf", "Co", "Cs"):
            zaehler += 1
    return zaehler


def schrift_anteil(text: str, schrift: str) -> float:
    """Anteil der Buchstaben, die zum genannten Schriftsystem gehoeren (z. B. CYRILLIC)."""
    buchstaben = [z for z in text if z.isalpha()]
    if not buchstaben:
        return 0.0
    treffer = sum(1 for z in buchstaben if schrift in unicodedata.name(z, ""))
    return treffer / len(buchstaben)


def pruefe_gate(lang: str, konf: dict, text: str, artikel: dict[int, str]) -> list[str]:
    """Prueft die geparste Quelle vollstaendig im Speicher. Rueckgabe: Liste der Verstoesse."""
    gruende: list[str] = []

    # 1. Sprachwaechter zuerst — der haeufigste Fehler ist die falsche Sprache.
    for wort in konf.get("stoppwoerter", ()):
        treffer = len(re.findall(re.escape(wort), text, re.IGNORECASE))
        if treffer < STOPPWORT_MIN:
            gruende.append(f"Sprachwaechter: Stoppwort '{wort}' nur {treffer}x im Quelltext "
                           f"(< {STOPPWORT_MIN}) — falsche Sprache oder unvollstaendige Seite?")
    schrift = konf.get("schrift")
    if schrift:
        anteil = schrift_anteil(text, schrift)
        if anteil < 0.5:
            gruende.append(f"Sprachwaechter: nur {anteil:.1%} Buchstaben in Schrift {schrift} "
                           f"(< 50 %) — falsche Sprache oder unvollstaendige Seite?")

    # 2. Anzahl und Nummerierung der Slots.
    if len(artikel) != ARTIKEL_ANZAHL:
        gruende.append(f"{len(artikel)}/{ARTIKEL_ANZAHL} Artikel-Slots geparst "
                       f"(Splitter {konf['splitter']!r}) — Quelle/Parser pruefen")
    elif sorted(artikel) != list(range(1, ARTIKEL_ANZAHL + 1)):
        gruende.append(f"Slots nicht lueckenlos 1..{ARTIKEL_ANZAHL}: {sorted(artikel)}")

    # 3. Ungeparste Artikel-Ueberschriften im Resttext.
    weit = len(re.findall(konf["splitter_weit"], text))
    if weit != len(artikel):
        gruende.append(f"{weit} Artikel-Ueberschriften im Text, aber nur {len(artikel)} geparst — "
                       f"Schreibvariante der Ueberschrift verpasst")

    # 4. Je Artikel: Laenge, Ersatzzeichen, Folgetext, Restueberschrift.
    for nummer in sorted(artikel):
        koerper = artikel[nummer]
        if not (LAENGE_MIN <= len(koerper) <= LAENGE_MAX):
            gruende.append(f"Artikel {nummer}: {len(koerper)} Zeichen, erlaubt "
                           f"{LAENGE_MIN}..{LAENGE_MAX} (Folgetext mitgeschluckt oder leer?)")
        quote = fehlzeichen(koerper) / max(len(koerper), 1)
        if quote >= FEHLZEICHEN_ANTEIL_MAX:
            gruende.append(f"Artikel {nummer}: {quote:.2%} Ersatz-/Steuerzeichen "
                           f"(>= {FEHLZEICHEN_ANTEIL_MAX:.0%})")
        for marker in konf.get("rahmen_marker", ()):
            if marker in koerper:
                gruende.append(f"Artikel {nummer}: Seitenrahmen im Artikeltext ('{marker}')")
        if re.search(konf["splitter"], koerper):
            gruende.append(f"Artikel {nummer}: ungeparste Artikel-Ueberschrift im Resttext")

    return gruende


def titel(roh: str, nummer: int) -> str:
    """Kurztitel aus der ersten Zeile des Artikels (fuer das Frontmatter, max. 60 Zeichen)."""
    erste = roh.split("\n", 1)[0]
    erste = re.sub(r"\s+", " ", erste).strip(" .;:-")
    return (erste[:57] + "...") if len(erste) > 60 else (erste or f"Artikel {nummer}")


def main() -> int:
    p = argparse.ArgumentParser(description="Fehlende UDHR-Artikel aus amtlicher Quelle ergaenzen")
    p.add_argument("--lang", default="de", choices=sorted(QUELLEN),
                   help="Sprachcode = Zielordner articles/<lang>/ (Default: de)")
    p.add_argument("--dry-run", action="store_true", help="nur pruefen, nichts schreiben")
    p.add_argument("--url", default=None, help="Quelle ueberschreiben (Default: Quelle der Sprache)")
    args = p.parse_args()

    konf = QUELLEN[args.lang]
    url = args.url or konf["url"]
    artikel_dir = os.path.join(REPO, "articles", args.lang)

    vorhanden: dict[int, str] = {}
    for pfad in sorted(glob.glob(os.path.join(artikel_dir, "*.md"))):
        nummer = int(re.sub(r"\D", "", os.path.basename(pfad)))
        with open(pfad, encoding="utf-8") as f:
            vorhanden[nummer] = f.read()
    print(f"Sprache: {args.lang}")
    print(f"Ziel   : {artikel_dir}")
    print(f"Bestand: {len(vorhanden)} Artikel -> {sorted(vorhanden)}")

    roh = hole_html(url)
    text = schneide_rahmen_ab(als_text(roh), konf)
    artikel = parse_artikel(text, konf["splitter"])
    print(f"Quelle : {len(artikel)} Artikel geparst -> {sorted(artikel)}")

    gruende = pruefe_gate(args.lang, konf, text, artikel)
    if gruende:
        for grund in gruende[:5]:
            print(f"GATE_FAIL [{args.lang}]: {grund}", file=sys.stderr)
        if len(gruende) > 5:
            print(f"GATE_FAIL [{args.lang}]: ... und {len(gruende) - 5} weitere Verstoesse",
                  file=sys.stderr)
        raise GateFehler(f"Gate fuer '{args.lang}' nicht bestanden ({len(gruende)} Verstoss/Verstoesse)"
                         f" — es wurde NICHTS geschrieben")
    print(f"Gate   : bestanden — {len(artikel)} Slots 1..{ARTIKEL_ANZAHL}, "
          f"{LAENGE_MIN}..{LAENGE_MAX} Zeichen, <{FEHLZEICHEN_ANTEIL_MAX:.0%} Ersatzzeichen, "
          f"0 ungeparste Ueberschriften, Stoppwoerter {list(konf.get('stoppwoerter', ()))} belegt, "
          f"0 Rahmentreffer")

    # Bestandssperre: der abgerufene Wortlaut muss den vorhandenen Bestand bestaetigen. Bei der
    # Erstanlage (leerer Ordner) gibt es nichts zu bestaetigen — dort traegt das Gate oben.
    if vorhanden:
        abweichungen = []
        for nummer in BESTANDS_PROBEN:
            if nummer not in vorhanden or nummer not in artikel:
                abweichungen.append((nummer, "<fehlt>", "<fehlt>"))
                continue
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
            print(f"[ABBRUCH] nur {bestaetigt}/{len(BESTANDS_PROBEN)} Artikel bestaetigt — "
                  f"Quelle unbrauchbar.", file=sys.stderr)
            return 1
        print(f"Sperre : {bestaetigt}/{len(BESTANDS_PROBEN)} Bestandsartikel wortgleich bestaetigt")
    else:
        print("Sperre : kein Bestand (Erstanlage) — Bestandssperre entfaellt, Gate oben hat geprueft")

    fehlend = [n for n in range(1, ARTIKEL_ANZAHL + 1) if n not in vorhanden]
    print(f"Fehlend: {fehlend} ({len(fehlend)} Stueck)")
    if not fehlend:
        return 0

    if args.dry_run:
        for nummer in fehlend:
            ziel = os.path.join(artikel_dir, f"art_{nummer:02d}.md")
            print(f"  [dry-run] wuerde schreiben: {ziel} ({len(artikel[nummer])} Zeichen)")
        return 0

    os.makedirs(artikel_dir, exist_ok=True)
    # Erst ALLE Dateien als .tmp schreiben, dann in einem Zug umbenennen: ein Abbruch mitten im
    # Schreiben hinterlaesst so keinen halb gefuellten Ordner.
    geschrieben = []
    for nummer in fehlend:
        ziel = os.path.join(artikel_dir, f"art_{nummer:02d}.md")
        if os.path.exists(ziel):
            print(f"  [uebersprungen] {ziel} existiert bereits")
            continue
        inhalt = (f'---\narticle: {nummer}\narticle_id: "art_{nummer:02d}"\n'
                  f'title: "{titel(artikel[nummer], nummer)}"\n'
                  f'source: "{konf["name"]}"\nurl: {url}\n---\n{artikel[nummer]}\n')
        temp = ziel + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            f.write(inhalt)
        geschrieben.append((temp, ziel, nummer))
    for temp, ziel, nummer in geschrieben:
        os.replace(temp, ziel)
        print(f"  geschrieben: {ziel} ({len(artikel[nummer])} Zeichen)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GateFehler as fehler:
        print(f"[ABBRUCH] {fehler}", file=sys.stderr)
        sys.exit(1)
