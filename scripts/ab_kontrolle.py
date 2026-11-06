#!/usr/bin/env python3
"""Kontrolle für den A/B-Streit: ist der Unterschied größer als das Rauschen?

Die Frage „unterscheiden sich A und B?" ist ohne Rauschboden nicht beantwortbar.
Dieses Skript erzeugt deshalb eine ZWEITE A-Variante (A2) mit identischem Meta,
identischem Prolog, identischem Artikel und identischem Kanal — nur ein anderer
Sampling-Lauf. Dann:

  A ↔ A2   = Rauschen (zweimal derselbe Input)
  A ↔ B    = Effekt des Dossiers

Ist A↔B ähnlich zu A↔A2, hat das Dossier nichts bewirkt. Liegt A↔B deutlich
darunter, verschiebt es den Text.

Zusätzlich: Anteil der Dossier-Inhaltswörter, die im Kapitel wieder auftauchen
(B vs A) — das misst, ob die Bedeutung ankommt, nicht nur ob Wörter abweichen.

Aufruf: python3 scripts/ab_kontrolle.py --nur de,es,pt,ja,hi
"""
import argparse
import glob
import json
import os
import re
import shutil
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [REPO, f"{REPO}/scripts"]
BOOKS = os.path.join(REPO, "menschenrechte_books")
SUFFIX_A2 = "_a2_kontrolle"

STOPP = set("""der die das und oder aber nicht ist sind war ware ein eine einen einem einer
des dem den sich mit fuer für von zu im in am auf aus bei nach ueber über unter vor
ich du er sie es wir ihr man mein meine dein deine sein seine ihr ihre unser unsere
the and or but not is are was were a an of to in on at for with from by this that
these those it its his her their our your my i you he she we they""".split())


def woerter(text: str) -> set:
    return {w for w in re.findall(r"\w{4,}", text.lower()) if w not in STOPP}


def kapitel(d: str) -> list:
    return sorted(glob.glob(f"{d}/*_art_*.md"))


def finde(lang: str) -> dict:
    """A-, B- und A2-Band einer Sprache."""
    a = b = a2 = ""
    for bj in glob.glob(f"{BOOKS}/buch_*/book.json"):
        d = os.path.dirname(bj)
        name = os.path.basename(d)
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("language") or "").lower() != lang or m.get("style") != "Songtext_Matrix":
            continue
        kap = kapitel(d)
        if not kap:
            continue
        if name.endswith(SUFFIX_A2):
            a2 = kap[-1]
        elif name.endswith("_ab_bedeutung"):
            b = kap[-1] if not b else b
        elif not name.endswith("_c_salt"):
            a = kap[-1] if not a else a
    return {"A": a, "B": b, "A2": a2}


def naechste_nummer() -> int:
    nummern = [int(m.group(1)) for p in glob.glob(f"{BOOKS}/buch_*")
               if (m := re.match(r"buch_(\d+)", os.path.basename(p)))]
    return (max(nummern) + 1) if nummern else 1


def klone_a(quelldatei: str, nummer: int) -> str:
    d = os.path.dirname(quelldatei)
    meta = json.load(open(os.path.join(d, "book.json"), encoding="utf-8"))
    slug = re.sub(r"[^a-z0-9]+", "_", (meta.get("title") or "band").lower())[:24].strip("_")
    slug = slug or (meta.get("language") or "band").lower()
    neu_id = f"buch_{nummer:03d}_{slug}{SUFFIX_A2}"
    ziel = os.path.join(BOOKS, neu_id)
    os.makedirs(ziel, exist_ok=True)
    meta.update({"book_id": neu_id, "covered_articles": [], "current_chapter": 0,
                 "variant": "A2", "article_mode": "text", "form": "standard"})
    json.dump(meta, open(os.path.join(ziel, "book.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    prolog = os.path.join(d, "00_prolog.md")
    if os.path.exists(prolog):
        shutil.copy2(prolog, os.path.join(ziel, "00_prolog.md"))
    return ziel


def erzeuge(lang: str, band: str, artikel: str, backend: str, model: str) -> str:
    subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "append-chapter",
                    "--lang", lang.upper(), "--book-id", os.path.basename(band),
                    "--article", artikel, "--backend", backend, "--model", model],
                   cwd=REPO, capture_output=True, text=True, timeout=900)
    kap = kapitel(band)
    return kap[-1] if kap else ""


def artikel_von(pfad: str) -> str:
    teile = open(pfad, encoding="utf-8").read().split("---")
    treffer = re.search(r'article:\s*"([^"]+)"', teile[1] if len(teile) > 1 else "")
    return treffer.group(1) if treffer else ""


def jaccard(x: set, y: set) -> float:
    return len(x & y) / max(len(x | y), 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nur", default="de,es,pt,ja,hi")
    ap.add_argument("--backend", default="deepseek")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--ohne-erzeugen", action="store_true")
    a = ap.parse_args()

    sprachen = [s.strip() for s in a.nur.split(",") if s.strip()]
    zeilen, rausch, effekt = [], [], []
    for lang in sprachen:
        pf = finde(lang)
        if not (pf["A"] and pf["B"]):
            print(f"  {lang}: A oder B fehlt"); continue
        artikel = artikel_von(pf["B"])
        if not pf["A2"] and not a.ohne_erzeugen:
            band = klone_a(pf["B"], naechste_nummer())
            pf["A2"] = erzeuge(lang, band, artikel, a.backend, a.model)
        if not pf["A2"]:
            print(f"  {lang}: A2 fehlt"); continue

        w_a, w_b, w_a2 = (woerter(open(pf[k], encoding="utf-8").read().split("---", 2)[2])
                          for k in ("A", "B", "A2"))
        j_aa = jaccard(w_a, w_a2)
        j_ab = jaccard(w_a, w_b)

        dossier = os.path.join(REPO, "articles", lang, "bedeutung", f"{artikel}.md")
        dw = woerter(open(dossier, encoding="utf-8").read()) if os.path.exists(dossier) else set()
        treffer_b = len(dw & w_b) / max(len(dw), 1)
        treffer_a = len(dw & w_a) / max(len(dw), 1)

        rausch.append(j_aa); effekt.append(j_ab)
        zeilen.append((lang, artikel, len(w_a), len(w_b), len(w_a2), j_aa, j_ab, treffer_a, treffer_b))
        print(f"  {lang:3} {artikel} · A↔A2 {j_aa:.0%} · A↔B {j_ab:.0%} · "
              f"Dossier-Wörter in A {treffer_a:.0%} / B {treffer_b:.0%}")

    if not zeilen:
        print("  keine Paare"); return 1
    print(f"\n  Median A↔A2 (Rauschen): {statistics.median(rausch):.0%}")
    print(f"  Median A↔B  (Effekt)  : {statistics.median(effekt):.0%}")
    differenz = statistics.median(rausch) - statistics.median(effekt)
    print(f"  Differenz             : {differenz:+.0%} Punkte "
          f"({'Dossier wirkt' if differenz > 0.05 else 'Dossier wirkt nicht über das Rauschen hinaus'})")
    json.dump([{"lang": z[0], "artikel": z[1], "j_aa": round(z[5], 4), "j_ab": round(z[6], 4),
                "dossier_a": round(z[7], 4), "dossier_b": round(z[8], 4)} for z in zeilen],
              open(os.path.expanduser("~/ab-kontrolle.json"), "w", encoding="utf-8"), indent=2)
    print(f"  Zahlen: ~/ab-kontrolle.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
