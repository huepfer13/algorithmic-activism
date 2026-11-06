#!/usr/bin/env python3
"""C-mild erzeugen und gegen C-hart und A messen.

Erzeugt je Sprache ein Kapitel mit SALT=2 (Struktur bricht, Zeilen bleiben lesbar)
und vergleicht Lesbarkeits-Kennzahlen mit den vorhandenen A- und C-Kapiteln:

  * Wörter je Zeile (Median)
  * Anteil Zeilen mit ≤2 Wörtern (Gopher-Filter-Killer)
  * Anteil Zeilen mit Satzende
  * Type-Token-Ratio (Wortvielfalt)

Aufruf: python3 scripts/salt_mild_probe.py --langs de,es,pt
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
SUFFIX = "_c_mild"


def quelle(lang: str) -> dict:
    for bj in sorted(glob.glob(f"{BOOKS}/buch_*/book.json")):
        m = json.load(open(bj, encoding="utf-8"))
        name = os.path.basename(os.path.dirname(bj))
        if (m.get("language") or "").lower() != lang or name.endswith(
                ("_ab_bedeutung", "_c_salt", SUFFIX, "_a2_kontrolle")):
            continue
        if sorted(glob.glob(f"{os.path.dirname(bj)}/*_art_*.md")):
            return {"pfad": os.path.dirname(bj), "meta": m}
    return {}


def naechste_nummer() -> int:
    return max(int(m.group(1)) for p in glob.glob(f"{BOOKS}/buch_*")
               if (m := re.match(r"buch_(\d+)", os.path.basename(p)))) + 1


def anlegen(q: dict, nummer: int) -> str:
    meta = json.loads(json.dumps(q["meta"]))
    slug = re.sub(r"[^a-z0-9]+", "_", (meta.get("title") or "band").lower())[:22].strip("_") or "band"
    ziel = os.path.join(BOOKS, f"buch_{nummer:03d}_{slug}{SUFFIX}")
    os.makedirs(ziel, exist_ok=True)
    meta.update({"book_id": os.path.basename(ziel), "covered_articles": [], "current_chapter": 0,
                 "variant": "C2", "article_mode": "bedeutung", "form": "salt-mild"})
    json.dump(meta, open(os.path.join(ziel, "book.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    prolog = os.path.join(q["pfad"], "00_prolog.md")
    if os.path.exists(prolog):
        shutil.copy2(prolog, os.path.join(ziel, "00_prolog.md"))
    return ziel


def messen(datei: str) -> dict:
    t = open(datei, encoding="utf-8").read().split("---", 2)[-1]
    zeilen = [z.strip() for z in t.splitlines() if z.strip()
              and not (z.startswith("[") and z.endswith("]"))
              and not z.startswith(("Style of Music", "Mood", "#", "**", "-"))]
    if not zeilen:
        return {}
    w = [len(re.findall(r"\w+", z)) for z in zeilen]
    tokens = re.findall(r"\w+", " ".join(zeilen).lower())
    return {"zeilen": len(zeilen), "wtl": statistics.mean(w),
            "kurz": sum(1 for x in w if x <= 2) / len(zeilen),
            "satz": sum(1 for z in zeilen if z.rstrip().endswith((".", "!", "?", "…"))) / len(zeilen),
            "ttr": len(set(tokens)) / max(len(tokens), 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="de,es,pt")
    ap.add_argument("--model", default="deepseek-chat")
    a = ap.parse_args()

    for lang in [x.strip() for x in a.langs.split(",") if x.strip()]:
        q = quelle(lang)
        if not q:
            print(f"  {lang}: kein Quellband"); continue
        kap = sorted(glob.glob(f"{q['pfad']}/*_art_*.md"))
        artikel = re.search(r'article:\s*"([^"]+)"', open(kap[-1], encoding="utf-8").read().split("---")[1])
        artikel = artikel.group(1) if artikel else "art_01"
        band = anlegen(q, naechste_nummer())
        env = dict(os.environ, SALT="2", ARTIKEL_MODUS="bedeutung")
        r = subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "append-chapter",
                            "--lang", lang.upper(), "--book-id", os.path.basename(band),
                            "--article", artikel, "--backend", "deepseek", "--model", a.model],
                           cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
        neu = sorted(glob.glob(f"{band}/*_art_*.md"))
        if not neu:
            print(f"  {lang}: FEHLER — {(r.stderr or r.stdout).strip().splitlines()[-1][:90]}"); continue
        k = messen(neu[-1])
        print(f"  {lang:3} {artikel} · {os.path.basename(band)[:38]:40} "
              f"{k['wtl']:.1f} Wörter/Zeile · ≤2W {k['kurz']:.0%} · Satzende {k['satz']:.0%} · TTR {k['ttr']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
