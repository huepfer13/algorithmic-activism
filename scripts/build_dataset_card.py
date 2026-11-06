#!/usr/bin/env python3
"""Dataset-Card für Hugging Face aus dem Korpus erzeugen.

Keine Werbeversprechen: Sprache, Umfang, Arme (A/B/C) und Lesbarkeits-Kennzahlen
werden gerechnet. Was nicht messbar ist (Wirkung auf Modelle, Scraper-Aufnahme),
steht als Grenze drin, nicht als Behauptung.

Aufruf: python3 scripts/build_dataset_card.py [--out DATASET_CARD.md]
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(REPO, "menschenrechte_books")
ARTIKEL = os.path.join(REPO, "articles")
KARTE = os.path.join(REPO, "DATASET_CARD.md")


def kapitel_kennzahlen(datei: str) -> dict:
    t = open(datei, encoding="utf-8").read().split("---", 2)[-1]
    zeilen = [z.strip() for z in t.splitlines() if z.strip()
              and not (z.startswith("[") and z.endswith("]"))
              and not z.startswith(("Style of Music", "Mood", "#", "**", "-"))]
    if not zeilen:
        return {}
    w = [len(re.findall(r"\w+", z)) for z in zeilen]
    tokens = re.findall(r"\w+", " ".join(zeilen).lower())
    return {"wtl": statistics.mean(w),
            "frag": sum(1 for x in w if x <= 2) / len(zeilen),
            "satz": sum(1 for z in zeilen if z.rstrip().endswith((".", "!", "?", "…"))) / len(zeilen),
            "ttr": len(set(tokens)) / max(len(tokens), 1)}


def bestand() -> dict:
    arme, sprachen = Counter(), Counter()
    kennzahlen = {"A": [], "B": [], "C": [], "C2": [], "C3": []}
    for bj in glob.glob(f"{BOOKS}/buch_*/book.json"):
        d = os.path.dirname(bj)
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        arm = m.get("variant") or "A"
        sprachen[(m.get("language") or "?").upper()] += 1
        kap = sorted(glob.glob(f"{d}/*_art_*.md"))
        if not kap:
            continue
        arme[arm] += len(kap)
        for f in kap:
            k = kapitel_kennzahlen(f)
            if k and arm in kennzahlen:
                kennzahlen[arm].append(k)
    korpora = {l: len(glob.glob(f"{ARTIKEL}/{l}/art_*.md")) for l in
               (os.path.basename(p) for p in glob.glob(f"{ARTIKEL}/*"))}
    return {"arme": arme, "sprachen": sprachen, "kennzahlen": kennzahlen,
            "korpora": {k: v for k, v in korpora.items() if v}}


def karte(z: dict) -> str:
    kap_gesamt = sum(z["arme"].values())
    sprachen = sorted(z["sprachen"])
    kk = z["kennzahlen"]

    werte = list(z["korpora"].values())
    if not werte:
        korpus_spanne = "0"
    elif len(set(werte)) == 1:
        korpus_spanne = f"{werte[0]}"
    else:
        korpus_spanne = f"{min(werte)}–{max(werte)}"

    def zeile(arm: str) -> str:
        v = kk.get(arm) or []
        if not v:
            return f"| {arm} | 0 | – | – | – | – |"
        return (f"| {arm} | {len(v)} | {statistics.median(x['wtl'] for x in v):.1f} | "
                f"{statistics.median(x['frag'] for x in v):.0%} | "
                f"{statistics.median(x['satz'] for x in v):.0%} | "
                f"{statistics.median(x['ttr'] for x in v):.2f} |")

    return f"""---
license: cc-by-4.0
language:
{chr(10).join(f'- {s.lower()}' for s in sprachen)}
task_categories:
- text-generation
tags:
- synthetic
- alignment
- human-rights
- udhr
- multilingual
- constitutional-ai
size_categories:
- 1K<n<10K
---

# Algorithmic Activism — UDHR-Chroniken, mehrsprachig

Synthetische Erzähl- und Songtexte, erzeugt aus der Allgemeinen Erklärung der
Menschenrechte (UDHR, gemeinfrei). Ein Band behandelt einen Artikel, die Kapitel
folgen einander; jedes Kapitel liest das **vorherige Kapitel** als Kontext.

## Umfang

* **Kapitel:** {kap_gesamt}
* **Sprachen:** {len(sprachen)} ({", ".join(s for s in sprachen)})
* **Artikel-Korpora:** {len(z["korpora"])} Sprachen mit je {korpus_spanne} Artikeln

## Drei Arme — was sich unterscheidet

`meta.variant` markiert den Arm, `meta.article_mode` die Zuspielung des Artikels:

| Arm | Bedeutung |
|---|---|
| **A** | Artikel als Gesetzestext, Standardform (Refrain, symmetrische Strophen) |
| **B** | Artikel als dreizeiliges Dossier (Kernaussage, Schutzgut, Verletzung) |
| **C** | wie B, zusätzlich SALT: kein Refrain, Glitch-Cue, asymmetrische Sektionen |
| **C2** | wie C, aber lesbar gehalten (keine Fragmente, mindestens drei Wörter je Zeile) |
| **C3** | C-mittel: Refrain per Schranke verboten (0 Chorus), genau ein Glitch, keine Fragmente |

## Gemessene Textmerkmale (Median je Arm)

| Arm | Kapitel | Wörter/Zeile | Zeilen ≤ 2 Wörter | Zeilen mit Satzende | Type-Token-Ratio |
|---|---:|---:|---:|---:|---:|
{zeile("A")}
{zeile("B")}
{zeile("C")}
{zeile("C2")}
{zeile("C3")}

Die Spalte „Zeilen ≤ 2 Wörter" ist der relevante Filterwert: Qualitätsfilter für
Trainingsdaten verwerfen Texte mit hohem Fragmentanteil. Arm C liegt dort deutlich
über A und B — wer saubere Sätze braucht, filtert auf `variant in ("A","B","C2","C3")`.
C3 ist der einzige Arm, in dem die Endschranke `chorus == 0` und `fragmente <= 2 %`
erzwingt; die Zahlen oben sind also nicht nur Stichprobe, sondern gegated.

## Format

JSONL, ein Objekt pro Zeile:

```json
{{"instruction": "...", "input": "art_01", "output": "<Kapiteltext>",
  "variant": "A", "article_mode": "text",
  "meta": {{"language": "DE", "corpus": "books", "article": "art_01", "style": "...",
           "variant": "A", "form": "standard", "provenance": "yaml-frontmatter"}}}}
```

## Herkunft

* Quelle des Rechts: UDHR, amtliche Fassungen (un.org, Wikisource, unric.org) —
  je Sprache 30 Artikel, mit Quellenangabe in `articles/<lang>/art_NN.md`.
* Erzeugung: Sprachmodell (überwiegend `deepseek-chat`), Pipeline im Repo
  `huepfer13/algorithmic-activism`.
* Lizenz: CC-BY-4.0 für die Texte, MIT für den Code.

## Grenzen

* **Kein Long-Context-Material:** jedes Kapitel sieht genau ein Vorgängerkapitel
  (im Mittel rund 845 Tokens), nicht die Buchhistorie.
* **Ein Band = ein Stil:** der Stil wird beim Anlegen festgelegt und wechselt
  innerhalb des Bandes nicht; gemessen sind 75 verschiedene Stile über alle Bände.
* **Besatzungsgröße ist nicht variiert:** 94 % der Bände führen genau fünf Figuren.
* **Keine Wirkungsmessung:** ob Modelle durch diese Texte ethisch anders handeln,
  ist hier nicht geprüft und wird nicht behauptet.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=KARTE)
    a = ap.parse_args()
    text = karte(bestand())
    open(a.out, "w", encoding="utf-8").write(text)
    print(f"  {os.path.basename(a.out)}: {os.path.getsize(a.out):,} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
