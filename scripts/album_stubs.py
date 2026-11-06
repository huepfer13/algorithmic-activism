#!/usr/bin/env python3
"""Album-Stub je Sprache: ein Songtext-Band mit Prolog.

Idempotent: existiert für eine Sprache schon ein Band mit style=Songtext_Matrix,
wird sie übersprungen. Der Prolog entsteht über den echten Pipeline-Pfad
(`--mode new-book`), kein Stub-JSON.

Aufruf:
  python3 scripts/album_stubs.py --dry-run
  python3 scripts/album_stubs.py
"""
import argparse
import glob
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def sprachen() -> list:
    """Alle Sprachen mit vollem Artikelkorpus, sortiert."""
    out = []
    for d in sorted(glob.glob(f"{REPO}/articles/*")):
        lang = os.path.basename(d)
        if os.path.isdir(d) and len(os.listdir(d)) >= 30 and os.path.exists(f"{REPO}/locales/{lang}.json"):
            out.append(lang)
    return out


def vorhanden(lang: str) -> list:
    """Bände dieser Sprache im Songtext-Format."""
    treffer = []
    for bj in glob.glob(f"{REPO}/menschenrechte_books/buch_*/book.json"):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("language") or "").lower() == lang and m.get("style") == "Songtext_Matrix":
            treffer.append(os.path.basename(os.path.dirname(bj)))
    return treffer


def anlegen(lang: str, backend: str, model: str) -> tuple:
    r = subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "new-book",
                        "--lang", lang.upper(), "--book-style", "Songtext_Matrix",
                        "--backend", backend, "--model", model],
                       cwd=REPO, capture_output=True, text=True, timeout=420)
    pfad = ""
    for zeile in (r.stdout + r.stderr).splitlines():
        if "Buch angelegt:" in zeile:
            pfad = zeile.split("Buch angelegt:")[-1].strip()
    if not pfad or not os.path.isdir(pfad):
        return "", (r.stderr or r.stdout).strip().splitlines()[-1:] or ["kein Buchpfad"]
    bj = os.path.join(pfad, "book.json")
    m = json.load(open(bj, encoding="utf-8"))
    m.update({"song_mode": "erzaehl", "song_genre": "dark_ambient", "song_style_engine": True})
    json.dump(m, open(bj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    prolog = os.path.join(pfad, "00_prolog.md")
    return os.path.basename(pfad), (os.path.getsize(prolog) if os.path.exists(prolog) else 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="deepseek")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    fertig, fehler, uebersprungen = [], [], []
    for lang in sprachen():
        alte = vorhanden(lang)
        if alte:
            uebersprungen.append((lang, alte[0]))
            print(f"  {lang:3} vorhanden: {alte[0][:48]} — übersprungen")
            continue
        if a.dry_run:
            print(f"  {lang:3} WÜRDE anlegen (Prolog + book.json)")
            continue
        band, info = anlegen(lang, a.backend, a.model)
        if band:
            fertig.append((lang, band, info))
            print(f"  {lang:3} angelegt: {band[:48]} · Prolog {info} B")
        else:
            fehler.append((lang, info))
            print(f"  {lang:3} FEHLER: {info}"[:150])

    print(f"\n  angelegt {len(fertig)} · übersprungen {len(uebersprungen)} · Fehler {len(fehler)}")
    for lang, info in fehler:
        print(f"    {lang}: {info}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
