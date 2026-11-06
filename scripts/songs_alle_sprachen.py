#!/usr/bin/env python3
"""Je Sprache ein neues Song-Kapitel erzeugen und alles in ein Markdown sammeln.

Für jede Sprache mit Korpus und Songtext-Album wird per echtem Pipeline-Pfad
(`--mode append-chapter`) ein Kapitel angehängt. Danach entsteht ein Markdown
mit Style-Zeile, Vortragsart und vollständigem Text je Sprache, plus einer
Messzeile (Schriftzeichen, Tags, Hook-Wiederholungen).

Aufruf:
  python3 scripts/songs_alle_sprachen.py --dry-run
  python3 scripts/songs_alle_sprachen.py --out ~/songs.md
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

SCHRIFT = {
    "ar": r"[\u0600-\u06ff]", "he": r"[\u0590-\u05ff]", "hi": r"[\u0900-\u097f]",
    "zh": r"[\u4e00-\u9fff]", "ja": r"[\u3040-\u30ff\u4e00-\u9fff]",
    "ko": r"[\uac00-\ud7af]", "ru": r"[\u0400-\u04ff]", "uk": r"[\u0400-\u04ff]",
    "fa": r"[\u0600-\u06ff]",
}


def album(lang: str) -> str:
    """Songtext-Album der Sprache (erste Fundstelle)."""
    for bj in sorted(glob.glob(f"{REPO}/menschenrechte_books/buch_*/book.json")):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (m.get("language") or "").lower() == lang and m.get("style") == "Songtext_Matrix":
            return os.path.dirname(bj)
    return ""


def kapitel(d: str) -> list:
    return sorted(glob.glob(f"{d}/*_art_*.md"))


def erzeuge(lang: str, band: str, backend: str, model: str) -> tuple:
    bj = os.path.join(band, "book.json")
    m = json.load(open(bj, encoding="utf-8"))
    m.setdefault("song_mode", "erzaehl")
    m.setdefault("song_genre", "dark_ambient")
    m["song_style_engine"] = True
    json.dump(m, open(bj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    vorher = set(kapitel(band))
    r = subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "append-chapter",
                        "--lang", lang.upper(), "--book-id", os.path.basename(band),
                        "--backend", backend, "--model", model],
                       cwd=REPO, capture_output=True, text=True, timeout=600)
    neu = [f for f in kapitel(band) if f not in vorher]
    log = [z for z in (r.stdout + r.stderr).splitlines() if "Versuch" in z or "angehaengt" in z]
    return (neu[-1] if neu else ""), (log[-1][:90] if log else "kein Kapitel")


def md_block(lang: str, band: str, datei: str) -> str:
    roh = open(datei, encoding="utf-8").read()
    teile = roh.split("---", 2)          # ["", Frontmatter, Rumpf]
    kopf, rumpf = (teile[1] if len(teile) > 1 else ""), (teile[2] if len(teile) > 2 else roh)
    titel = (re.search(r'chapter_title:\s*"([^"]+)"', kopf) or [None, "?"])[1]
    artikel = (re.search(r'article:\s*"([^"]+)"', kopf) or [None, "?"])[1]
    ok = "bestanden" if 'manual_ending_ok: true' in kopf else "Fallback"
    zeilen = rumpf.strip().splitlines()
    style = next((z for z in zeilen if z.startswith("Style of Music")), "")
    mood = next((z for z in zeilen if z.startswith("Mood")), "")
    # Kopfzeilen nicht doppeln: die Überschrift steht im Block-Titel, Style und Mood im
    # eigenen Fence. Im Textblock bleiben nur Tags und Liedzeilen.
    text = "\n".join(z for z in zeilen
                     if not z.startswith("# ") and z is not style and z is not mood
                     and not z.startswith(("Style of Music", "Mood:"))).strip("\n")
    muster = SCHRIFT.get(lang, r"[A-Za-zÀ-ÿ]")
    zeichen = len(re.findall(muster, text))
    tags = len(re.findall(r"^\[[^\]]+\]$", text, re.M))
    hook = max((text.count(z.strip()) for z in zeilen
                if 8 < len(z.strip()) < 80 and not z.strip().startswith("[")), default=0)
    return (f"## {lang.upper()} — {titel}\n\n"
            f"*Band `{os.path.basename(band)}` · Artikel `{artikel}` · Endschranke {ok} · "
            f"{zeichen} Schriftzeichen · {tags} Tags · häufigste Zeile {hook}×*\n\n"
            f"```\n{style}\n{mood}\n```\n\n"
            f"```\n{text}\n```\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/.hermes/cache/scratch/songs-alle-sprachen.md"))
    ap.add_argument("--backend", default="deepseek")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--nur", default="", help="Komma-Liste von Sprachen (Standard: alle)")
    ap.add_argument("--ohne-erzeugen", action="store_true",
                    help="Markdown nur aus den vorhandenen Kapiteln bauen")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sprachen = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{REPO}/locales/*.json"))
    if a.nur:
        sprachen = [s for s in sprachen if s in a.nur.split(",")]

    bloecke, fehler = [], []
    for lang in sprachen:
        band = album(lang)
        if not band:
            fehler.append((lang, "kein Songtext-Album"))
            print(f"  {lang:3} kein Album"); continue
        if a.dry_run:
            print(f"  {lang:3} WÜRDE erzeugen in {os.path.basename(band)[:40]}")
            continue
        if a.ohne_erzeugen:
            vorhanden = kapitel(band)
            if not vorhanden:
                fehler.append((lang, "kein Kapitel vorhanden")); print(f"  {lang:3} kein Kapitel"); continue
            datei, info = vorhanden[-1], "vorhanden"
        else:
            datei, info = erzeuge(lang, band, a.backend, a.model)
        if not datei:
            fehler.append((lang, info))
            print(f"  {lang:3} FEHLER {info}"); continue
        bloecke.append(md_block(lang, band, datei))
        print(f"  {lang:3} {os.path.basename(datei)[:56]} · {info}")

    if a.dry_run:
        return 0

    kopf = ("# Ein neuer Song je Sprache\n\n"
            f"{len(bloecke)} Sprachen · erzeugt über den Pipeline-Pfad `append-chapter` "
            f"(Modus `erzaehl`, Genre `dark_ambient`, Stil-Würfel) · Modell {a.model}.\n\n"
            "Jeder Block enthält die Style-Zeile im Suno-Format, den vollständigen Liedtext "
            "und eine Messzeile. Die Artikel beziehen sich auf die Allgemeine Erklärung der "
            "Menschenrechte.\n\n---\n\n")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(kopf + "\n---\n\n".join(bloecke))
    print(f"\n  geschrieben: {a.out} ({os.path.getsize(a.out):,} B) · Blöcke {len(bloecke)} · Fehler {len(fehler)}")
    for lang, info in fehler:
        print(f"    {lang}: {info}")
    return 0 if bloecke else 1


if __name__ == "__main__":
    sys.exit(main())
