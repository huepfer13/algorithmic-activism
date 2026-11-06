#!/usr/bin/env python3
"""Vergleich A (Klartext) gegen B (Bedeutung): Kennzahlen je Sprache.

Misst, was der Unterschied im Artikel-Input bewirkt:
  - Länge, Tags, Sektionszahl
  - Wortüberlappung mit dem Gesetzestext (Jaccard) — B soll deutlich darunter liegen
  - Papier/Relais-Metaphorik
  - Überlappung A ↔ B (wie ähnlich sind sich die beiden Songs überhaupt)
  - Endschranke je Seite

Aufruf: python3 scripts/ab_vergleich.py [--out file.md]
"""
import argparse
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(REPO, "menschenrechte_books")
METAPHER = ("relais", "relay", "rele", "رله", "реле", "纸屑", "パルプ", "काग़ज़",
            "papier", "paper", "papper", "pneumatisch")


def woerter(t: str) -> set:
    return set(re.findall(r"\w+", t.lower()))


def kennzahlen(datei: str, artikel_text: str) -> dict:
    roh = open(datei, encoding="utf-8").read()
    teile = roh.split("---", 2)
    kopf, rumpf = teile[1], teile[2]
    w = woerter(rumpf)
    return {
        "zeichen": len(rumpf),
        "tags": len(re.findall(r"^\[[^\]]+\]$", rumpf, re.M)),
        "sektionen": len({z for z in re.findall(r"^\[([^\]]+)\]$", rumpf, re.M)}),
        "artikel_overlap": round(len(w & woerter(artikel_text)) / max(len(w | woerter(artikel_text)), 1), 3),
        "metapher": sum(len(re.findall(m, rumpf, re.I)) for m in METAPHER),
        "ok": (m.group(1).lower() == "true") if (m := re.search(r"manual_ending_ok:\s*(\w+)", kopf)) else False,
        "woerter": w,
        "text": rumpf,
    }


def artikel_von(datei: str) -> str:
    kopf = open(datei, encoding="utf-8").read().split("---")
    treffer = re.search(r'article:\s*"([^"]+)"', kopf[1] if len(kopf) > 1 else "")
    return treffer.group(1) if treffer else ""


def paar(lang: str) -> tuple:
    """(A-Pfad, B-Pfad) für eine Sprache — der Zwilling zum SELBEN Artikel.

    Nicht einfach das jüngste Kapitel nehmen: im Zwilling können durch Nachläufe
    weitere Kapitel stehen, die nicht zum A-Paar gehören (Messung 2026-11-06).
    """
    a = b = ""
    twins = []
    for bj in glob.glob(f"{BOOKS}/buch_*/book.json"):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("language") or "").lower() != lang or m.get("style") != "Songtext_Matrix":
            continue
        d = os.path.dirname(bj)
        ks = sorted(glob.glob(f"{d}/*_art_*.md"))
        if not ks:
            continue
        if d.endswith("_ab_bedeutung"):
            twins.append((d, ks))
        elif not a or os.path.getmtime(ks[-1]) > os.path.getmtime(a):
            a = ks[-1]
    ziel = artikel_von(a) if a else ""
    for _, ks in twins:
        passend = [k for k in ks if artikel_von(k) == ziel]
        if passend:
            b = passend[0]
            break
    return a, b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/ab-bedeutung.md"))
    a = ap.parse_args()

    sprachen = sorted({os.path.basename(p)[:-5].lower() for p in glob.glob(f"{REPO}/locales/*.json")})
    zeilen, bloecke = [], []
    for lang in sprachen:
        pa, pb = paar(lang)
        if not (pa and pb):
            zeilen.append(f"| {lang.upper()} | — | — | — | — | — | — | — |")
            continue
        kopf_a = open(pa, encoding="utf-8").read().split("---")[1]
        treffer = re.search(r'article:\s*"([^"]+)"', kopf_a)
        artikel_id = treffer.group(1) if treffer else "art_01"
        artikel_text = open(os.path.join(REPO, "articles", lang, f"{artikel_id}.md"), encoding="utf-8").read()
        ka, kb = kennzahlen(pa, artikel_text), kennzahlen(pb, artikel_text)
        gemeinsam = len(ka["woerter"] & kb["woerter"]) / max(len(ka["woerter"] | kb["woerter"]), 1)
        zeilen.append(f"| {lang.upper()} | {artikel_id} | {ka['zeichen']} | {kb['zeichen']} | "
                      f"{ka['artikel_overlap']:.0%} | {kb['artikel_overlap']:.0%} | "
                      f"{ka['metapher']} / {kb['metapher']} | {gemeinsam:.0%} |")
        bloecke.append((lang, artikel_id, ka, kb))

    kopf = ("# A/B: Song aus Gesetzestext gegen Song aus Bedeutung\n\n"
            "Gleicher Band-Meta (Titel, Besatzung, Setting, POV), gleicher Prolog, gleicher Artikel,\n"
            "gleiche Sprache — der **einzige** Unterschied ist der Artikel-Input: links der Wortlaut,\n"
            "rechts ein Dossier aus drei Zeilen (Kernaussage, Schutzgut, Verletzung).\n\n"
            "| Sprache | Artikel | A Zeichen | B Zeichen | A Artikel-Überlappung | B Artikel-Überlappung | Metapher A/B | A↔B Wortgleichheit |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|\n")
    md = kopf + "\n".join(zeilen) + "\n"
    for lang, artikel_id, ka, kb in bloecke:
        md += (f"\n---\n\n## {lang.upper()} · {artikel_id}\n\n"
               f"**A — aus dem Wortlaut** ({ka['zeichen']} Zeichen, {ka['tags']} Tags, "
               f"Endschranke {'ok' if ka['ok'] else 'Fallback'})\n\n```\n{ka['text'].strip()[:1400]}\n```\n\n"
               f"**B — aus der Bedeutung** ({kb['zeichen']} Zeichen, {kb['tags']} Tags, "
               f"Endschranke {'ok' if kb['ok'] else 'Fallback'})\n\n```\n{kb['text'].strip()[:1400]}\n```\n")
    open(a.out, "w", encoding="utf-8").write(md)
    print(f"  geschrieben: {a.out} ({os.path.getsize(a.out):,} B) · Paare {len(bloecke)}/{len(sprachen)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
