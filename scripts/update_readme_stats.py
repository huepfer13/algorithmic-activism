#!/usr/bin/env python3
"""Live-Kennzahlen in die README schreiben (zwischen zwei Markern).

Alles wird aus dem Bestand gerechnet, nichts geschätzt:
  * Abdeckung je Sprache: Kapitel und verhandelte Artikel von 30
  * A/B/C-Verteilung der Bände
  * Diversitäts-Maße: häufigste Stil-Phrase, Anteil Bände mit genau 5 Figuren
  * Umfang: Kapitel, Zeichen

Aufruf:
  python3 scripts/update_readme_stats.py --dry-run
  python3 scripts/update_readme_stats.py            # schreibt README.md
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(REPO, "menschenrechte_books")
README = os.path.join(REPO, "README.md")
START = "<!-- START_DYNAMIC_STATS -->"
ENDE = "<!-- END_DYNAMIC_STATS -->"
ZIEL = 30


def bestand() -> dict:
    """Kennzahlen aus book.json und den Kapiteldateien."""
    sprachen = defaultdict(lambda: {"kapitel": 0, "artikel": set(), "baende": 0})
    varianten = Counter()
    figuren = []
    zonen = Counter()
    zeichen = 0

    for bj in sorted(glob.glob(f"{BOOKS}/buch_*/book.json")):
        d = os.path.dirname(bj)
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        lang = (m.get("language") or "?").upper()
        kap = sorted(glob.glob(f"{d}/*_art_*.md"))
        sprachen[lang]["baende"] += 1
        sprachen[lang]["kapitel"] += len(kap)
        sprachen[lang]["artikel"].update(m.get("covered_articles") or [])
        varianten[m.get("variant") or "A"] += 1
        if m.get("characters"):
            figuren.append(len(m["characters"]))
        for f in kap:
            t = open(f, encoding="utf-8").read()
            zeichen += len(t)
            for treffer in re.findall(r"(?:low end|mid|wide): ([^·\n]+)", t):
                zonen[treffer.strip()] += 1

    return {"sprachen": sprachen, "varianten": varianten, "figuren": figuren,
            "zonen": zonen, "zeichen": zeichen}


def block(z: dict) -> str:
    gesamt_kap = sum(v["kapitel"] for v in z["sprachen"].values())
    gesamt_art = sum(len(v["artikel"]) for v in z["sprachen"].values())
    varianten = z["varianten"]
    b_gesamt = sum(varianten.values()) or 1
    fig5 = sum(1 for n in z["figuren"] if n == 5)
    zonen_top = z["zonen"].most_common(1)
    zonen_gesamt = sum(z["zonen"].values()) or 1

    zeilen = [START,
              "### Live-Kennzahlen des Korpus",
              "",
              f"*Generiert aus dem Bestand, nicht geschätzt — zuletzt: {__import__('datetime').date.today().isoformat()}*",
              "",
              f"| | |",
              f"|---|---:|",
              f"| Bände | {sum(v['baende'] for v in z['sprachen'].values())} |",
              f"| Kapitel | {gesamt_kap} |",
              f"| Artikel-Abdeckung (Summe über Sprachen) | {gesamt_art} / {ZIEL * len(z['sprachen'])} |",
              f"| Sprachen | {len(z['sprachen'])} |",
              f"| Zeichen im Korpus | {z['zeichen']:,} |".replace(",", "."),
              "",
              "**Abdeckung je Sprache** (Kapitel / Artikel von 30)",
              "",
              "| Sprache | Bände | Kapitel | Artikel |",
              "|---|---:|---:|---:|"]
    for lang in sorted(z["sprachen"]):
        v = z["sprachen"][lang]
        zeilen.append(f"| {lang} | {v['baende']} | {v['kapitel']} | {len(v['artikel'])} / {ZIEL} |")
    zeilen += ["",
               "**Varianten (A = Wortlaut, B = Bedeutung, C = SALT)**",
               "",
               "| Variante | Bände | Anteil |",
               "|---|---:|---:|"]
    for var, n in sorted(varianten.items()):
        zeilen.append(f"| {var} | {n} | {n / b_gesamt:.0%} |")
    zeilen += ["",
               "**Diversität** (je niedriger der erste Wert, desto weniger Schablone)",
               "",
               f"* Häufigste Stil-Phrase: `{zonen_top[0][0]}` in {zonen_top[0][1] / zonen_gesamt:.0%} der Zuordnungen"
               if zonen_top else "* Häufigste Stil-Phrase: keine Daten",
               f"* Bände mit genau 5 Figuren: {fig5} von {len(z['figuren'])} "
               f"({fig5 / max(len(z['figuren']), 1):.0%})",
               "", ENDE]
    return "\n".join(zeilen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--readme", default=README, help="Zieldatei (für Probeläufe auf einer Kopie)")
    a = ap.parse_args()

    neu = block(bestand())
    if a.dry_run:
        print(neu)
        return 0

    text = open(a.readme, encoding="utf-8").read()
    if START in text and ENDE in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(ENDE), neu, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + neu + "\n"
    open(a.readme, "w", encoding="utf-8").write(text)
    print(f"  {os.path.basename(a.readme)} aktualisiert ({os.path.getsize(a.readme):,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
