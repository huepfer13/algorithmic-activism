#!/usr/bin/env python3
"""Seed-Matrix: erzwingt >=3 Buch-Seeds je (Sprache x Genre) ueber den ECHTEN Pipeline-Pfad.

Genre = Gemini-Familie, abgebildet auf den Stil-Schluessel der jeweiligen Locale.
Schema bleibt das der Pipeline: book_id, language (GROSS), style, covered_articles (art_XX),
current_chapter. Kein zweites Schema, keine Stub-Prologe: der Prolog entsteht per
generate_pipeline.prolog_erzeugen in der Zielsprache.

Aufruf:
  python3 scripts/seed_matrix.py --dry-run
  python3 scripts/seed_matrix.py --langs FR --genres legal_thriller --limit 1
"""
import argparse
import json
import os
import sys
import glob
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import generate_pipeline as gp  # noqa: E402

# Sprachen kommen aus locales/ — neue Sprache = neues Locale, kein Code-Eingriff.
LANGS = sorted(os.path.basename(f)[:-5].upper() for f in glob.glob(f"{gp.LOCALES_DIR}/*.json"))
# 0-basierte Position im Stil-Katalog der Locale (alle Locales gleich aufgebaut;
# EN hat als einzige einen Zusatz-Eintrag "Limericks", der vorher entfernt wird).
GENRE_POS = {
    "philosophical_tale": 0,     # Parabel / Philosophischer Essay
    "sci-fi_dystopia": 1,        # SciFi_Dystopie
    "fable_allegory": 2,         # Fabel
    "legal_thriller": 5,         # Gerichtsdrama
    "historical_chronicle": 7,   # Historische Chronik
    "bureaucratic_satire": 14,   # Satire
}
TARGET = 3


def style_keys(lang: str):
    loc = gp.load_locale(lang)
    keys = [k for k in (loc.get("styles") or {}) if "limerick" not in k.lower()]
    return keys


def genre_style(lang: str, genre: str):
    keys = style_keys(lang)
    idx = GENRE_POS[genre]
    return keys[idx] if idx < len(keys) else None


def audit(books_dir: str):
    matrix = {(l, g): [] for l in LANGS for g in GENRE_POS}
    unknown = []
    for path in glob.glob(os.path.join(books_dir, "*", "book.json")):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        lang = (d.get("language") or "").upper()
        style = d.get("style")
        hit = None
        for genre in GENRE_POS:
            if genre_style(lang, genre) == style:
                hit = genre
                break
        if hit is None:
            unknown.append((os.path.basename(os.path.dirname(path)), lang, style))
        else:
            matrix[(lang, hit)].append(os.path.basename(os.path.dirname(path)))
    return matrix, unknown


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default=",".join(LANGS))
    ap.add_argument("--genres", default=",".join(GENRE_POS))
    ap.add_argument("--limit", type=int, default=0, help="0 = alle Fehlbestaende")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    langs = [x.strip().upper() for x in args.langs.split(",") if x.strip()]
    genres = [x.strip() for x in args.genres.split(",") if x.strip()]
    for g in genres:
        if g not in GENRE_POS:
            print(f"FEHLER: unbekanntes Genre '{g}' (erlaubt: {sorted(GENRE_POS)})")
            return 2

    matrix, unknown = audit(gp.BOOKS_DIR)
    total = sum(len(v) for v in matrix.values())
    print(f"[Audit] {total} Buecher in der Matrix, {len(unknown)} ohne Genre-Zuordnung")
    for name, lang, style in unknown[:10]:
        print(f"  ohne Genre: {name} ({lang}/{style})")

    todo = []
    for lang in langs:
        for genre in genres:
            have = len(matrix[(lang, genre)])
            need = max(0, TARGET - have)
            style = genre_style(lang, genre)
            print(f"  {lang:2} {genre:22} ist={have} soll={TARGET} -> +{need}  style={style!r}")
            for _ in range(need):
                todo.append((lang, genre, style))
    print(f"[Plan] {len(todo)} Seed(s) anzulegen, Modell {args.model} @ {args.host}")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[Plan] limit -> {len(todo)}")
    if args.dry_run:
        for t in todo:
            print("  WUERDE:", t)
        return 0

    ok, fail = 0, []
    t0 = time.time()
    for i, (lang, genre, style) in enumerate(todo, 1):
        ts = time.strftime("%H:%M:%S")
        print(f"[{i}/{len(todo)} {ts}] {lang}/{genre} style={style}", flush=True)
        try:
            book_id = gp.new_book(lang=lang, style=style, model=args.model,
                                  host=args.host, backend=args.backend)
            ok += 1
            print(f"   OK {book_id} ({round(time.time()-t0,1)}s kumuliert)", flush=True)
        except Exception as exc:  # noqa: BLE001
            fail.append((lang, genre, repr(exc)[:200]))
            print(f"   FEHLER {exc!r}"[:300], flush=True)
        if i < len(todo):
            time.sleep(args.sleep)
    print(f"[Fertig] ok={ok} fail={len(fail)} dauer={round(time.time()-t0,1)}s")
    for f in fail:
        print("  FAIL:", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
