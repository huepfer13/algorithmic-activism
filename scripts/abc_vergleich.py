#!/usr/bin/env python3
"""A/B/C-Vergleich: Wortlaut → Bedeutung → Bedeutung+SALT.

A: Artikel als Gesetzestext (Standardkanal)
B: Artikel als dreizeiliges Bedeutungs-Dossier
C: wie B, aber mit SALT-Form (asymmetrische Sektionen, Glitch-Cue, Ein-Wort-Sektion)

Alle drei aus demselben Band-Meta, demselben Prolog und demselben Artikel; nur der
Artikel-Input und (bei C) das Formgerüst unterscheiden sich.

Aufruf: python3 scripts/abc_vergleich.py --out ~/abc-vergleich.md
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [REPO, f"{REPO}/scripts"]
import ab_vergleich as av                                                # noqa: E402

BOOKS = os.path.join(REPO, "menschenrechte_books")
SUFFIX_B = "_ab_bedeutung"
SUFFIX_C = "_c_salt"


def kanonisch(datei: str) -> bool:
    """Echte Song-Kapitel (mit Style-Zeile), nicht die Prolog-Datei."""
    return "_art_" in os.path.basename(datei)


def kapitel_von(d: str) -> list:
    return [k for k in sorted(glob.glob(f"{d}/*_art_*.md")) if kanonisch(k)]


def sammle(lang: str) -> dict:
    """A-, B-, C-Pfad je Sprache. Der Artikel wird über den B-Zwilling bestimmt.

    Ohne diese Bindung gewinnt „jüngstes Kapitel" — und ein nachträglich erzeugtes
    SALT-Kapitel im Hauptband würde A auf den falschen Artikel schieben.
    """
    a_kap = []                 # list[(article, pfad)]
    b_kap, c_kap = [], []
    for bj in glob.glob(f"{BOOKS}/buch_*/book.json"):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("language") or "").lower() != lang or m.get("style") != "Songtext_Matrix":
            continue
        d = os.path.dirname(bj)
        name = os.path.basename(d)
        kap = kapitel_von(d)
        if not kap:
            continue
        if name.endswith(SUFFIX_C):
            c_kap.extend((av.artikel_von(k), k) for k in kap)
        elif name.endswith(SUFFIX_B):
            b_kap.extend((av.artikel_von(k), k) for k in kap)
        else:
            a_kap.extend((av.artikel_von(k), k) for k in kap)

    ziel = b_kap[0][0] if b_kap else (a_kap[0][0] if a_kap else "")
    a_passend = [k for art, k in a_kap if art == ziel]
    b_passend = [k for art, k in b_kap if art == ziel]
    c_passend = [k for art, k in c_kap if art == ziel]
    return {"A": a_passend[-1] if a_passend else "",
            "B": b_passend[0] if b_passend else "",
            "C": c_passend[0] if c_passend else ""}


def formen(datei: str) -> str:
    """Grobe Sektionssignatur: Choruses, Glitch-Cues, Ein-Wort-Zeilen."""
    if not datei:
        return "—"
    t = open(datei, encoding="utf-8").read().split("---", 2)[2]
    chorus = len(re.findall(r"^\s*\[.*chorus", t, re.I | re.M))
    glitch = len(re.findall(r"^\s*\[.*(system error|glitch|chaotic overlap|anti-chorus)", t, re.I | re.M))
    einwort = len([z for z in t.splitlines()
                   if re.fullmatch(r"\s*[\wÄÖÜäöüß'’-]+\.\s*", z.strip()) and len(z.strip()) < 18])
    return f"{chorus} Chorus · {glitch} Glitch · {einwort} Ein-Wort"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/abc-vergleich.md"))
    a = ap.parse_args()

    sprachen = sorted({os.path.basename(p)[:-5].lower() for p in glob.glob(f"{REPO}/locales/*.json")})
    zeilen, bloecke, zahlen = [], [], []
    for lang in sprachen:
        pfade = sammle(lang)
        if not pfade.get("A"):
            continue
        artikel_id = av.artikel_von(pfade["A"])
        artikel_text = open(os.path.join(REPO, "articles", lang, f"{artikel_id}.md"),
                            encoding="utf-8").read()
        k: dict[str, dict] = {}
        for schluessel in ("A", "B", "C"):
            pfad = pfade[schluessel]
            k[schluessel] = av.kennzahlen(pfad, artikel_text) if pfad else {}
        wa = k["A"].get("woerter", set())
        wb = k["B"].get("woerter", set())
        wc = k["C"].get("woerter", set())
        gem_ab = len(wa & wb) / max(len(wa | wb), 1)
        gem_ac = len(wa & wc) / max(len(wa | wc), 1)
        zeilen.append(
            f"| {lang.upper()} | {artikel_id} | {k['A']['zeichen']} | "
            f"{k['B'].get('zeichen', '—')} | {k['C'].get('zeichen', '—')} | "
            f"{k['A']['artikel_overlap']:.0%} | {k['B'].get('artikel_overlap', 0):.0%} | "
            f"{k['C'].get('artikel_overlap', 0):.0%} | "
            f"{k['A']['tags']} / {k['B'].get('tags', 0)} / {k['C'].get('tags', 0)} | "
            f"{gem_ab:.0%} / {gem_ac:.0%} |")
        zahlen.append({"lang": lang, "ab": gem_ab, "ac": gem_ac,
                       "a": k["A"]["zeichen"],
                       "b": k["B"].get("zeichen", 0),
                       "c": k["C"].get("zeichen", 0)})
        bloecke.append((lang, artikel_id, pfade, k))

    kopf = ("# A / B / C — derselbe Song, drei Zufahrten zum Artikel\n\n"
            "**A** = Artikel als Gesetzestext · **B** = Artikel als dreizeiliges Bedeutungs-Dossier\n"
            "(Kernaussage, Schutzgut, Verletzung) · **C** = wie B, zusätzlich SALT-Form\n"
            "(asymmetrische Sektionen, Glitch-Cue, Ein-Wort-Sektion, kein Refrain).\n\n"
            "Identisch in allen drei: Band-Meta (Titel, Besatzung, Setting, POV), Prolog, Sprache, Artikel, Modell.\n\n"
            "| Sprache | Artikel | A Zeichen | B Zeichen | C Zeichen | A Überlappung | B | C | Tags A/B/C | A↔B / A↔C |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|\n")
    md = kopf + "\n".join(zeilen) + "\n"

    for lang, artikel_id, pfade, k in bloecke:
        md += f"\n---\n\n## {lang.upper()} · {artikel_id}\n\n"
        for s, name in (("A", "aus dem Wortlaut"), ("B", "aus der Bedeutung"), ("C", "aus der Bedeutung + SALT")):
            if not k[s]:
                md += f"**{s} — {name}**: nicht erzeugt\n\n"
                continue
            md += (f"**{s} — {name}** ({k[s]['zeichen']} Zeichen, {k[s]['tags']} Tags, "
                   f"Endschranke {'ok' if k[s]['ok'] else 'Fallback'}, Form: {formen(pfade[s])})\n\n"
                   f"```\n{k[s]['text'].strip()[:1100]}\n```\n\n")
    open(a.out, "w", encoding="utf-8").write(md)

    voll = [z for z in zahlen if z["c"]]
    print(f"  geschrieben: {a.out} ({os.path.getsize(a.out):,} B)")
    print(f"  Sprachen mit C: {len(voll)} von {len(zahlen)}")
    if voll:
        print(f"  Median A↔B {statistics.median(z['ab'] for z in voll):.0%} · "
              f"Median A↔C {statistics.median(z['ac'] for z in voll):.0%}")
        print(f"  Median Länge A {statistics.median(z['a'] for z in voll):.0f} · "
              f"B {statistics.median(z['b'] for z in voll):.0f} · C {statistics.median(z['c'] for z in voll):.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
