#!/usr/bin/env python3
"""Semantisches Dossier je Artikel: Bedeutung statt Wortlaut.

Für die Messreihe „Song aus Bedeutung statt Klartext": aus jedem Artikel wird
EINMALIG ein Dossier destilliert (Kernaussage, Schutzgut, typische Verletzung)
und auf Zielsprache geschrieben. Der Song-Generator sieht danach nur noch dieses
Dossier — nicht den Gesetzestext.

Ablage: articles/<lang>/bedeutung/art_NN.md
Aufruf: python3 scripts/bedeutungsdossier.py --langs es,ja,pt --apply
"""
import argparse
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import generate_pipeline as gp                                          # noqa: E402

FELDER = ("KERNAUSSAGE", "SCHUTZGUT", "VERLETZUNG")
# Das Modell weicht gelegentlich auf Synonyme aus ("VERLETZT:", "SCHADEN:").
ALIASE = {"KERNAUSSAGE": ("KERNAUSSAGE", "KERN", "AUSSAGE"),
          "SCHUTZGUT": ("SCHUTZGUT", "GESCHUETZT", "SCHUTZ"),
          "VERLETZUNG": ("VERLETZUNG", "VERLETZT", "SCHADEN", "VERSTOSS")}
SCHRIFT = {"ar": r"[\u0600-\u06ff]", "he": r"[\u0590-\u05ff]", "hi": r"[\u0900-\u097f]",
           "zh": r"[\u4e00-\u9fff]", "ja": r"[\u3040-\u30ff\u4e00-\u9fff]",
           "ko": r"[\uac00-\ud7af]", "ru": r"[\u0400-\u04ff]", "uk": r"[\u0400-\u04ff]",
           "fa": r"[\u0600-\u06ff]"}


def prompt(text: str, lang_name: str) -> str:
    return f"""Du destillierst die BEDEUTUNG eines Menschenrechts-Artikels. Der Wortlaut wird
danach weggeworfen — nur deine drei Zeilen bleiben.

Schreibe auf {lang_name}. Genau drei Zeilen, jede beginnt mit dem Schluesselwort:

KERNAUSSAGE: <was der Artikel als Anspruch festhaelt, ein Satz, kein Zitat>
SCHUTZGUT: <was konkret geschuetzt wird, eine Sache oder ein Zustand>
VERLETZUNG: <wie dieser Anspruch im Alltag typischerweise verletzt wird, ein konkretes Bild>

Regeln: kein Gesetzesdeutsch, keine Aufzaehlungen, keine Artikelnummer, hoechstens 200 Zeichen
je Zeile, keine Anfuehrungszeichen.

ARTIKEL (nur als Quelle, nicht zitieren):
{text}"""


def destilliere(lang: str, artikel: str, backend: str, model: str) -> str:
    art = gp.load_article(artikel, lang)
    loc = gp.load_locale(lang)
    roh = gp.erzeuge_text(prompt(art["body"], loc.get("language_name") or lang),
                          model, "https://api.deepseek.com", backend)
    zeilen = {}
    for z in roh.splitlines():
        oben = z.strip().upper()
        for feld in FELDER:
            alias = next((a for a in ALIASE[feld] if oben.startswith(a)), None)
            if alias:
                zeilen[feld] = re.sub(rf"^{alias}\s*:?\s*", "", z.strip(), flags=re.I)
    return "\n".join(f"{f}: {zeilen.get(f, '').strip()}" for f in FELDER)


def gate(lang: str, dossier: str) -> list:
    fehler = []
    # Schriftdichte: 100 chinesische Zeichen tragen mehr als 120 lateinische
    # (gemessen 2026-11-06: ein korrektes zh-Dossier fiel mit "Länge 101" durch).
    dicht = lang in ("zh", "ja", "ko", "ar", "he", "hi", "fa")
    gesamt_min, feld_min = (60, 12) if dicht else (120, 25)
    if len(dossier) < gesamt_min or len(dossier) > 900:
        fehler.append(f"Länge {len(dossier)}")
    for feld in FELDER:
        # Wortgrenze + Doppelpunkt: sonst gilt "SCHUTZGUTX: ..." als vorhandenes Feld
        treffer = re.search(rf"^\s*{feld}\s*:\s*(.+)$", dossier, re.M)
        if not treffer or len(treffer.group(1).strip()) < feld_min:
            fehler.append(f"{feld} fehlt/kurz")
    muster = SCHRIFT.get(lang)
    if muster and len(re.findall(muster, dossier)) < 20:
        fehler.append("falsche Schrift")
    # Sprache über den Detektor prüfen, nicht über eine deutsche Wortliste: "die" ist auch
    # ein englisches Wort und hat zwei korrekte EN-Dossiers abgelehnt (Messung 2026-11-06).
    if lang in ("es", "en", "fr", "it", "pt", "nl", "sv", "id", "sw", "de"):
        erkannt, _, _, sicher = gp.textsprache(dossier)
        if erkannt != lang.upper() and sicher >= 0.5:
            fehler.append(f"Sprache {erkannt} statt {lang.upper()}")
    return fehler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="")
    ap.add_argument("--backend", default="deepseek")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    paare = []
    for bj in glob.glob(f"{REPO}/menschenrechte_books/buch_*/book.json"):
        try:
            m = json.load(open(bj, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("style") != "Songtext_Matrix":
            continue
        lang = (m.get("language") or "").lower()
        if a.langs and lang not in a.langs.split(","):
            continue
        for f in sorted(glob.glob(f"{os.path.dirname(bj)}/*_art_*.md")):
            head = open(f, encoding="utf-8").read().split("---")
            treffer = re.search(r'article:\s*"([^"]+)"', head[1] if len(head) > 1 else "")
            if treffer:
                paare.append((lang, treffer.group(1)))
    paare = sorted(set(paare))

    ok, fehler = 0, []
    for lang, artikel in paare:
        ziel_dir = os.path.join(gp.ARTICLES_DIR, lang, "bedeutung")
        ziel = os.path.join(ziel_dir, f"{artikel}.md")
        if os.path.exists(ziel):
            print(f"  {lang}/{artikel}: vorhanden"); ok += 1; continue
        try:
            dossier = destilliere(lang, artikel, a.backend, a.model)
        except Exception as e:                                          # noqa: BLE001
            fehler.append((lang, artikel, repr(e)[:60])); continue
        problem = gate(lang, dossier)
        if problem:
            fehler.append((lang, artikel, str(problem[:2])))
            print(f"  {lang}/{artikel}: GATE {problem[:2]}")
            continue
        if a.apply:
            os.makedirs(ziel_dir, exist_ok=True)
            open(ziel, "w", encoding="utf-8").write(dossier + "\n")
        print(f"  {lang}/{artikel}: {len(dossier)} Zeichen · {dossier.splitlines()[0][:60]}")
        ok += 1
    print(f"\n  Dossiers: {ok} · Fehler {len(fehler)}")
    for f in fehler:
        print(f"    {f}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
