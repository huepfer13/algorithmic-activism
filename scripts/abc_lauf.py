#!/usr/bin/env python3
"""Ein Artikel, drei Varianten — der Standardlauf.

Für eine Sprache und einen Artikel entstehen drei Bände mit identischem Meta und
identischem Prolog:

  A  Wortlaut    — Artikel als Gesetzestext        (variant: "A")
  B  Bedeutung   — Artikel als Dossier (3 Zeilen)  (variant: "B")
  C  SALT        — Dossier + asymmetrische Form    (variant: "C")

`book.json` trägt danach `variant` und `article_mode`, damit der Datensatz-Export
die drei Arme filtern kann, ohne am Ordnernamen zu raten.

Aufruf:
  python3 scripts/abc_lauf.py --lang es                 # nächster freier Artikel
  python3 scripts/abc_lauf.py --lang es --article art_05
  python3 scripts/abc_lauf.py --lang es --dry-run
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
sys.path.insert(0, REPO)
BOOKS = os.path.join(REPO, "menschenrechte_books")

VARIANTEN = {
    "A": {"suffix": "", "env": {}},
    "B": {"suffix": "_ab_bedeutung", "env": {"ARTIKEL_MODUS": "bedeutung"}},
    "C": {"suffix": "_c_salt", "env": {"ARTIKEL_MODUS": "bedeutung", "SALT": "1"}},
    # C3 = C-mittel: Refrain hart verboten (Schranke), Fragmente verboten, Text bleibt lesbar.
    "C3": {"suffix": "_c_mittel", "env": {"ARTIKEL_MODUS": "bedeutung", "SALT": "3"}},
}


def quelle(lang: str, buchart: str = "auto") -> dict:
    """Buch-Meta und Prolog der Sprache — jede Buchart, nicht nur Songtext.

    Gewählt wird das Buch mit den meisten offenen Artikeln; Songs haben Vorrang,
    solange sie offene Artikel haben, weil dort die Struktur (SALT) am stärksten greift.
    """
    treffer = []
    for bj in sorted(glob.glob(f"{BOOKS}/buch_*/book.json")):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = os.path.basename(os.path.dirname(bj))
        if (m.get("language") or "").lower() != lang:
            continue
        if name.endswith(tuple(v["suffix"] for v in VARIANTEN.values() if v["suffix"])):
            continue
        offen = 30 - len(m.get("covered_articles") or [])
        if offen <= 0:
            continue
        ist_song = m.get("style") == "Songtext_Matrix"
        if buchart == "song" and not ist_song:
            continue
        if buchart == "prosa" and ist_song:
            continue
        treffer.append((not ist_song, -offen, name, os.path.dirname(bj), m))
    if not treffer:
        return {}
    treffer.sort()
    _, _, _, pfad, m = treffer[0]
    return {"pfad": pfad, "meta": m}


# Zwillinge aus der Messreihe zaehlen NICHT als verhandelt (sie sind Vergleichsarme).
# Der Produktionsarm C3 zaehlt: er hat ebenfalls ein Suffix, ist aber der laufende Betrieb.
EXPERIMENT = {"A2", "B", "C", "_ab_bedeutung", "_c_salt", "_a2_kontrolle"}


def verhandelt(lang: str) -> set:
    """Artikel, die im Betrieb wirklich behandelt wurden.

    Frueher wurden ALLE Suffix-Baende uebersprungen — auch der Produktionsarm C3.
    Folge: derselbe Artikel blieb ewig offen und wurde 44-46 Mal je Sprache neu
    erzeugt (gemessen 2026-11-13: JA/KO/NL/SV je 44+ Wiederholungen).
    """
    treffer = set()
    for bj in glob.glob(f"{BOOKS}/buch_*/book.json"):
        d = os.path.basename(os.path.dirname(bj))
        if any(d.endswith(sfx) for sfx in EXPERIMENT):
            continue
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("language") or "").lower() != lang:
            continue
        treffer.update(m.get("covered_articles") or [])
    return treffer


def offene_artikel(lang: str, meta: dict) -> str:
    """Nächster Artikel, den die Sprache noch nicht verhandelt hat."""
    covered = verhandelt(lang) | set(meta.get("covered_articles") or [])
    for i in range(1, 31):
        kennung = f"art_{i:02d}"
        if kennung not in covered:
            return kennung
    return ""


def naechste_nummer() -> int:
    nummern = [int(m.group(1)) for p in glob.glob(f"{BOOKS}/buch_*")
               if (m := re.match(r"buch_(\d+)", os.path.basename(p)))]
    return (max(nummern) + 1) if nummern else 1


def band_anlegen(q: dict, variante: str, nummer: int) -> str:
    meta = json.loads(json.dumps(q["meta"]))
    slug = re.sub(r"[^a-z0-9]+", "_", (meta.get("title") or "band").lower())[:24].strip("_")
    slug = slug or (meta.get("language") or "band").lower()
    neu_id = f"buch_{nummer:03d}_{slug}{VARIANTEN[variante]['suffix']}"
    ziel = os.path.join(BOOKS, neu_id)
    os.makedirs(ziel, exist_ok=True)
    meta.update({
        "book_id": neu_id, "covered_articles": [], "current_chapter": 0,
        "variant": variante,
        "article_mode": "bedeutung" if VARIANTEN[variante]["env"].get("ARTIKEL_MODUS") else "text",
        "form": "salt" if variante == "C" else "standard",
    })
    json.dump(meta, open(os.path.join(ziel, "book.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    prolog = os.path.join(q["pfad"], "00_prolog.md")
    if os.path.exists(prolog):
        shutil.copy2(prolog, os.path.join(ziel, "00_prolog.md"))
    return ziel


def erzeuge(lang: str, band: str, artikel: str, variante: str, backend: str, model: str) -> tuple:
    env = dict(os.environ, **VARIANTEN[variante]["env"])
    try:
        r = subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "append-chapter",
                            "--lang", lang.upper(), "--book-id", os.path.basename(band),
                            "--article", artikel, "--backend", backend, "--model", model],
                           cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        # 900 s ohne Ergebnis heisst: Provider haengt. Kein Traceback, sondern Befund.
        return "", "TIMEOUT nach 900 s — Provider antwortet nicht"
    kap = sorted(glob.glob(f"{band}/*_art_*.md"))
    zeilen = [z for z in (r.stdout + r.stderr).splitlines()
              if "Versuch" in z or "Artikel-Input" in z or "angehaengt" in z]
    return (kap[-1] if kap else ""), (zeilen[-1][:70] if zeilen else f"rc={r.returncode}")


def _sperre(warten_s: int = 900):
    """Exklusive Sperre auf .rotation.lock — wie run_model_rotation.py.

    Ohne sie lesen zwei gleichzeitige Läufe dieselbe nächste Bandnummer und legen
    zwei Verzeichnisse mit derselben Zahl an (gemessen 2026-11-06: buch_295 doppelt,
    einmal Prosa-Lauf, einmal Stunden-Tick). Rückgabe: offene Datei oder None.
    """
    import fcntl
    import time
    f = open(os.path.join(REPO, ".rotation.lock"), "w")
    ende = time.monotonic() + warten_s
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            if time.monotonic() > ende:
                f.close()
                return None
            time.sleep(10)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--article", default="")
    ap.add_argument("--varianten", default="A,B,C",
                    help="welche Arme erzeugt werden (A,B,C,C3)")
    ap.add_argument("--buchart", default="auto", choices=("auto", "song", "prosa"),
                    help="auto = Songs bevorzugt, solange sie offene Artikel haben")
    ap.add_argument("--backend", default="deepseek")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    q = quelle(a.lang, a.buchart)
    if not q:
        print(f"  FEHLER: kein Buch mit offenen Artikeln für '{a.lang}' ({a.buchart})"); return 2
    artikel = a.article or offene_artikel(a.lang, q["meta"])
    if not artikel:
        print(f"  {a.lang}: alle 30 Artikel verhandelt"); return 0
    nummer = naechste_nummer()

    griff = None if a.dry_run else _sperre()
    if not a.dry_run and griff is None:
        print("  FEHLER: .rotation.lock seit 15 min belegt — kein paralleles Anlegen"); return 3

    print(f"  {a.lang.upper()} · Band {os.path.basename(q['pfad'])[:36]} · Artikel {artikel}")
    for variante in [v.strip() for v in a.varianten.split(",") if v.strip()]:
        if a.dry_run:
            print(f"   {variante}: würde buch_{nummer:03d}_…{VARIANTEN[variante]['suffix']} anlegen")
            nummer += 1
            continue
        band = band_anlegen(q, variante, nummer); nummer += 1
        datei, info = erzeuge(a.lang, band, artikel, variante, a.backend, a.model)
        print(f"   {variante}: {os.path.basename(band)[:44]:46} {'ok' if datei else 'FEHLER'} · {info}")
    if griff is not None:
        import fcntl
        fcntl.flock(griff, fcntl.LOCK_UN)
        griff.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
