"""Prueft, dass jedes code_praefix in den Locales genau einmal belegt ist.

Warum: Prompt-Schema, Regex und Leck-Suche haengen am Praefix. Zwei Genres mit demselben
Praefix sind maschinell meist noch unterscheidbar (der Blockname differiert), in Logs und
Berichten aber mehrdeutig. Belegt 2026-10-12: W (Gothic/Witzebuch) und K (Kinderbuch/Limericks),
danach R (Manifest/Limericks) — jedes Mal beim Anlegen eines neuen Genres.
"""
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
belegt: dict = {}
for pfad in sorted(glob.glob(os.path.join(REPO, "locales", "*.json"))):
    sprache = os.path.basename(pfad)[:-5]
    try:
        d = json.load(open(pfad, encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[Praefixe] {sprache}: unlesbar — {e}")
        continue
    for stil, flags in (d.get("style_flags") or {}).items():
        praefix = flags.get("code_praefix")
        if praefix:
            belegt.setdefault(praefix, []).append(f"{stil}({sprache})")

doppel = {k: v for k, v in sorted(belegt.items()) if len(v) > 1}
for k, v in sorted(belegt.items()):
    print(f"  {k} -> {', '.join(v)}")
if doppel:
    print(f"\n[Praefixe] DOPPELBELEGUNG: {doppel}")
    sys.exit(1)
print(f"\n[Praefixe] {len(belegt)} Praefixe, alle eindeutig")
