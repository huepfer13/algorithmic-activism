#!/usr/bin/env python3
"""Baut den Buch-Index fuer den Web-Reader und die Entwickler-Endpunkte.

Erzeugt (alle deterministisch, ohne Zeitstempel — sonst erzeugt jeder CI-Lauf einen Diff):
  web/books.json        — Katalog aller Buecher samt Kapitel-Metadaten fuer den Reader
  web/api/random.json   — ein Beispielkapitel im Volltext (statisch, siehe Hinweis unten)
  web/api/ipsum.json    — Textfutter aus dem Korpus fuer Platzhalter

Hinweis zu "random": GitHub Pages liefert statische Dateien. Es gibt keinen Server, der pro
Anfrage wuerfeln koennte — die Datei enthaelt deshalb ein deterministisch gewaehltes Kapitel.
Echte Zufallsauslieferung braucht einen Worker oder einen Caddy-Rewrite, nicht diese Datei.

Aufruf:
  python3 scripts/build_books_index.py [--dry-run] [--books-dir PFAD] [--web-dir PFAD]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

WORDS_PER_MINUTE = 200          # Lesetempo-Annahme, bewusst als Konstante
IPSUM_WOERTER = 200             # Umfang des Platzhaltertexts

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)
KAPITEL_RE = re.compile(r"^(\d{2,})_.*\.md$")


def lies_frontmatter(pfad: str) -> tuple[dict, str]:
    """Liest den YAML-Kopf (nur einfache `schluessel: wert`-Zeilen) und gibt (kopf, rumpf) zurueck."""
    with open(pfad, encoding="utf-8") as f:
        roh = f.read()
    kopf: dict[str, str] = {}
    rumpf = roh
    if roh.startswith("---"):
        teile = roh.split("---", 2)
        if len(teile) >= 3:
            for zeile in teile[1].splitlines():
                if ":" in zeile and not zeile.startswith((" ", "\t", "#")):
                    schluessel, wert = zeile.split(":", 1)
                    kopf[schluessel.strip()] = wert.strip().strip('"').strip("'")
            rumpf = teile[2]
    return kopf, rumpf.strip()


def lesezeit(worte: int) -> int:
    """Minuten, mindestens 1 bei nicht leerem Text."""
    if worte <= 0:
        return 0
    return max(1, round(worte / WORDS_PER_MINUTE))


def kapitel_daten(buch_dir: str) -> list[dict]:
    """Alle Kapitel eines Buchs, numerisch nach Dateipraefix sortiert (00_prolog zuerst)."""
    dateien = [f for f in os.listdir(buch_dir) if KAPITEL_RE.match(f)]
    kapitel = []
    for name in sorted(dateien):
        kopf, rumpf = lies_frontmatter(os.path.join(buch_dir, name))
        worte = len(rumpf.split())
        nummer = KAPITEL_RE.match(name)
        index = int(kopf.get("chapter_index") or (nummer.group(1) if nummer else 0))
        kapitel.append({
            "file": name,
            "index": index,
            "title": kopf.get("chapter_title", ""),
            "article": kopf.get("article", ""),
            "ending_ok": kopf.get("manual_ending_ok", ""),
            "attempts": kopf.get("manual_ending_attempts", ""),
            "words": worte,
            "reading_minutes": lesezeit(worte),
        })
    return kapitel


def buch_daten(buch_dir: str) -> dict | None:
    """Metadaten eines Buchordners; None, wenn book.json fehlt oder unlesbar ist."""
    meta_pfad = os.path.join(buch_dir, "book.json")
    if not os.path.isfile(meta_pfad):
        print(f"  [WARNUNG] kein book.json in {os.path.basename(buch_dir)} — uebersprungen")
        return None
    try:
        with open(meta_pfad, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  [WARNUNG] book.json in {os.path.basename(buch_dir)} nicht lesbar ({e}) — uebersprungen")
        return None

    kapitel = kapitel_daten(buch_dir)
    # Verhandelte Artikel aus book.json UND aus den Kapiteldateien (Dateien sind die Wahrheit).
    artikel = [a for a in meta.get("covered_articles", []) if a]
    for k in kapitel:
        if k["article"] and k["article"] not in artikel:
            artikel.append(k["article"])
    worte = sum(k["words"] for k in kapitel)
    cover_relativ = f"menschenrechte_books/{os.path.basename(buch_dir)}/cover.svg"
    cover = cover_relativ if os.path.isfile(os.path.join(buch_dir, "cover.svg")) else None

    return {
        "book_id": meta.get("book_id", os.path.basename(buch_dir)),
        "title": meta.get("title", ""),
        "language": meta.get("language", ""),
        "style": meta.get("style", ""),
        "pov": meta.get("pov", ""),
        "setting_summary": meta.get("setting_summary", ""),
        "characters": meta.get("characters", []),
        "chapter_count": len([k for k in kapitel if k["index"] > 0]),
        "covered_articles": sorted(artikel),
        "words": worte,
        "reading_minutes": lesezeit(worte),
        "cover": cover,
        "chapters": kapitel,
    }


def sammle_buecher(books_dir: str) -> list[dict]:
    if not os.path.isdir(books_dir):
        return []
    buecher = []
    for name in sorted(os.listdir(books_dir)):
        pfad = os.path.join(books_dir, name)
        if os.path.isdir(pfad):
            daten = buch_daten(pfad)
            if daten:
                buecher.append(daten)
    return buecher


def baue_ipsum(buecher: list[dict], books_dir: str) -> dict:
    """Platzhaltertext aus dem Korpus: der Prolog des ersten Buchs, auf N Woerter gekuerzt."""
    for buch in buecher:
        for k in buch["chapters"]:
            if k["index"] == 0:
                _, rumpf = lies_frontmatter(os.path.join(books_dir, buch["book_id"], k["file"]))
                woerter = rumpf.split()[:IPSUM_WOERTER]
                if woerter:
                    return {
                        "note": "Platzhaltertext aus dem Korpus (statisch).",
                        "source": f"{buch['book_id']}/{k['file']}",
                        "words": len(woerter),
                        "text": " ".join(woerter),
                    }
    return {"note": "Noch kein Buch im Korpus.", "source": None, "words": 0, "text": ""}


def baue_random(buecher: list[dict], books_dir: str) -> dict:
    """Ein Beispielkapitel im Volltext (deterministisch: das letzte Kapitel des letzten Buchs)."""
    for buch in reversed(buecher):
        for k in reversed(buch["chapters"]):
            if k["index"] > 0:
                _, rumpf = lies_frontmatter(os.path.join(books_dir, buch["book_id"], k["file"]))
                return {
                    "note": ("Statische Datei: GitHub Pages wuerfelt nicht pro Anfrage. "
                             "Deterministisch gewaehltes Kapitel."),
                    "book_id": buch["book_id"],
                    "title": buch["title"],
                    "style": buch["style"],
                    "language": buch["language"],
                    "chapter": k["file"],
                    "chapter_title": k["title"],
                    "article": k["article"],
                    "words": k["words"],
                    "reading_minutes": k["reading_minutes"],
                    "text": rumpf,
                }
    return {"note": "Noch kein Buchkapitel im Korpus.", "text": ""}


def schreibe(pfad: str, daten: dict, dry_run: bool) -> None:
    text = json.dumps(daten, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if dry_run:
        print(f"  [dry-run] wuerde schreiben: {pfad} ({len(text)} B)")
        return
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    alt = None
    if os.path.isfile(pfad):
        with open(pfad, encoding="utf-8") as f:
            alt = f.read()
    if alt == text:
        print(f"  unveraendert: {pfad}")
        return
    # atomar: erst daneben schreiben, dann ersetzen - ein Abbruch hinterlaesst keine halbe Datei
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, pfad)
    print(f"  geschrieben: {pfad} ({len(text)} B)")


def main() -> int:
    p = argparse.ArgumentParser(description="Buch-Index und Entwickler-Endpunkte bauen")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--books-dir", default=os.path.join(REPO, "menschenrechte_books"))
    p.add_argument("--web-dir", default=os.path.join(REPO, "web"))
    args = p.parse_args()

    buecher = sammle_buecher(args.books_dir)
    print(f"Buecher: {len(buecher)} | Kapitel: {sum(len(b['chapters']) for b in buecher)} "
          f"| Woerter gesamt: {sum(b['words'] for b in buecher)}")
    schreibe(os.path.join(args.web_dir, "books.json"),
             {"schema": 1, "count": len(buecher), "books": buecher}, args.dry_run)
    schreibe(os.path.join(args.web_dir, "api", "random.json"),
             baue_random(buecher, args.books_dir), args.dry_run)
    schreibe(os.path.join(args.web_dir, "api", "ipsum.json"),
             baue_ipsum(buecher, args.books_dir), args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
