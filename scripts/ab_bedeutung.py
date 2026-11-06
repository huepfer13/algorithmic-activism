#!/usr/bin/env python3
"""A/B: derselbe Song, einmal aus dem Gesetzestext, einmal nur aus der Bedeutung.

Klonen: für jedes Songtext-Album entsteht ein Zwilling mit identischem Meta
(Titel, Besatzung, Setting, POV), identischem Prolog und demselben Artikel.
Der einzige Unterschied ist der Artikel-Input: `ARTIKEL_MODUS=bedeutung`
ersetzt den Klartext durch das Dossier aus articles/<lang>/bedeutung/.

Aufruf:
  python3 scripts/ab_bedeutung.py --dry-run
  python3 scripts/ab_bedeutung.py
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(REPO, "menschenrechte_books")
SUFFIX = "_ab_bedeutung"
SUFFIX_C = "_c_salt"


def alben() -> list:
    """(sprache, albumpfad) je Songtext-Album, neuestes Kapitel zuerst relevant."""
    out = []
    for bj in sorted(glob.glob(f"{BOOKS}/buch_*/book.json")):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = os.path.basename(os.path.dirname(bj))
        if m.get("style") == "Songtext_Matrix" and not name.endswith((SUFFIX, SUFFIX_C)):
            out.append(((m.get("language") or "").lower(), os.path.dirname(bj)))
    return out


def letztes_kapitel(d: str):
    ks = sorted(glob.glob(f"{d}/*_art_*.md"))
    if not ks:
        return "", ""
    kopf = open(ks[-1], encoding="utf-8").read().split("---")[1]
    m = re.search(r'article:\s*"([^"]+)"', kopf)
    return ks[-1], (m.group(1) if m else "")


def artikel_des_zwillings(lang: str, quelle: str, suffix: str) -> str:
    """Artikel, den der bereits vorhandene Zwilling verhandelt (sonst der von A).

    Nötig, weil im Hauptband später weitere Kapitel entstehen können: ohne diese
    Bindung erzeugt ein --salt-Lauf einen Zwilling zum falschen Artikel.
    """
    for name in sorted(os.listdir(BOOKS)):
        if not name.endswith(suffix):
            continue
        bj = os.path.join(BOOKS, name, "book.json")
        if not os.path.exists(bj):
            continue
        m = json.load(open(bj, encoding="utf-8"))
        if (m.get("language") or "").lower() != lang:
            continue
        _, artikel = letztes_kapitel(os.path.join(BOOKS, name))
        if artikel:
            return artikel
    _, artikel = letztes_kapitel(quelle)
    return artikel


def naechste_nummer() -> int:
    nummern = [int(m.group(1)) for p in glob.glob(f"{BOOKS}/buch_*")
               if (m := re.match(r"buch_(\d+)", os.path.basename(p)))]
    return (max(nummern) + 1) if nummern else 1


def klone(quelle: str, nummer: int, suffix: str = SUFFIX) -> str:
    meta = json.load(open(os.path.join(quelle, "book.json"), encoding="utf-8"))
    slug = re.sub(r"[^a-z0-9]+", "_", (meta.get("title") or "band").lower())[:28].strip("_")
    if not slug:                       # Titel in CJK/Arabisch/Kyrillisch ergibt keinen ASCII-Slug
        slug = (meta.get("language") or "band").lower()
    neu_id = f"buch_{nummer:03d}_{slug}{suffix}"
    ziel = os.path.join(BOOKS, neu_id)
    os.makedirs(ziel, exist_ok=True)
    meta["book_id"] = neu_id
    meta["covered_articles"] = []
    meta["current_chapter"] = 0
    json.dump(meta, open(os.path.join(ziel, "book.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    prolog = os.path.join(quelle, "00_prolog.md")
    if os.path.exists(prolog):
        shutil.copy2(prolog, os.path.join(ziel, "00_prolog.md"))
    return ziel


def erzeuge(lang: str, band_neu: str, artikel: str, backend: str, model: str,
            salt: bool = False) -> tuple:
    env = dict(os.environ, ARTIKEL_MODUS="bedeutung")
    if salt:
        env["SALT"] = "1"
    r = subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "append-chapter",
                        "--lang", lang.upper(), "--book-id", os.path.basename(band_neu),
                        "--article", artikel, "--backend", backend, "--model", model],
                       cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
    neu = sorted(glob.glob(f"{band_neu}/*_art_*.md"))
    log = [z for z in (r.stdout + r.stderr).splitlines() if "BEDEUTUNG" in z or "Versuch" in z]
    return (neu[-1] if neu else ""), (log[-1][:80] if log else "kein Kapitel")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="deepseek")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--salt", action="store_true",
                    help="dritte Variante C erzeugen: Bedeutung + SALT-Form")
    ap.add_argument("--nur", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # Ein Album je Sprache — das mit dem jüngsten Kapitel (sonst entstehen zwei DE-Zwillinge).
    beste = {}
    for lang, d in alben():
        if a.nur and lang not in a.nur.split(","):
            continue
        kap = sorted(glob.glob(f"{d}/*_art_*.md"))
        if not kap:
            continue
        mtime = os.path.getmtime(kap[-1])
        if lang not in beste or mtime > beste[lang][1]:
            beste[lang] = (d, mtime)
    liste = [(lang, d) for lang, (d, _) in sorted(beste.items())]
    nummer = naechste_nummer()
    fertig, fehler = [], []
    for lang, quelle in liste:
        kap, artikel = letztes_kapitel(quelle)
        if a.salt:
            artikel = artikel_des_zwillings(lang, quelle, SUFFIX) or artikel
        if not artikel:
            fehler.append((lang, "kein Kapitel/Artikel")); continue
        dossier = os.path.join(REPO, "articles", lang, "bedeutung", f"{artikel}.md")
        if not os.path.exists(dossier):
            fehler.append((lang, f"kein Dossier für {artikel}")); continue
        if a.dry_run:
            print(f"  {lang:3} {os.path.basename(quelle)[:36]:38} Artikel {artikel} → "
                  f"buch_{nummer:03d}_…{SUFFIX}")
            nummer += 1
            continue
        band_neu = klone(quelle, nummer, SUFFIX_C if a.salt else SUFFIX)
        nummer += 1
        datei, info = erzeuge(lang, band_neu, artikel, a.backend, a.model, salt=a.salt)
        if datei:
            fertig.append((lang, quelle, band_neu, artikel, datei))
            print(f"  {lang:3} {os.path.basename(band_neu)[:44]:46} {info}")
        else:
            fehler.append((lang, info))
            print(f"  {lang:3} FEHLER {info}")
    if not a.dry_run:
        print(f"\n  Zwillinge erzeugt: {len(fertig)} · Fehler {len(fehler)}")
        for f in fehler:
            print(f"    {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
