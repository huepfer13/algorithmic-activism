"""Prueft, dass innerhalb JEDER Locale jedes code_praefix genau einmal belegt ist.

Warum: Prompt-Schema, Regex und Leck-Suche haengen am Praefix. Zwei Genres mit demselben
Praefix sind maschinell meist noch unterscheidbar (der Blockname differiert), in Logs und
Berichten aber mehrdeutig. Belegt 2026-10-12 (W, K, R) und erneut 2026-10-13, als Solarpunk
im englischen Katalog versehentlich P statt U trug und damit mit Philosophical_Essay
kollidierte.

Abgrenzung (2026-10-13): Ueber mehrere Sprachen hinweg SOLL dasselbe Genre denselben
Buchstaben tragen — das ist der Vertrag (locales/README.md), nicht ein Fehler. Die
frueheren Fassung dieses Skripts aggregierte ueber alle Kataloge und meldete deshalb bei
jeder weiteren Sprache Exit 1; als Gate war sie damit unbrauchbar. Die sprachuebergreifende
Sicht wird hier nur noch als Uebersicht gedruckt, nicht bewertet. Die Gegenrichtung
(kein deutsches Genre darf seinen Buchstaben verlieren) prueft scripts/validate_locale.py.

Exit 0 = kein Buchstabe innerhalb einer Sprache doppelt. Exit 1 = Kollision.
"""
import collections
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pro_sprache: dict = {}
uebersicht: dict = collections.defaultdict(set)
kollisionen: dict = {}

for pfad in sorted(glob.glob(os.path.join(REPO, "locales", "*.json"))):
    if ".bak-" in os.path.basename(pfad):
        continue
    sprache = os.path.basename(pfad)[:-5]
    try:
        d = json.load(open(pfad, encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[Praefixe] {sprache}: unlesbar — {e}")
        sys.exit(1)
    zaehler = collections.Counter()
    for stil, flags in (d.get("style_flags") or {}).items():
        praefix = flags.get("code_praefix")
        if not praefix:
            continue
        zaehler[praefix] += 1
        uebersicht[praefix].add(sprache)
    pro_sprache[sprache] = zaehler
    doppelt = {k: v for k, v in zaehler.items() if v > 1}
    if doppelt:
        kollisionen[sprache] = doppelt

print("  Praefix-Uebersicht (Genre-Zahl je Sprache; dieselbe Zahl je Buchstabe = Vertrag erfuellt):")
for praefix in sorted(uebersicht):
    zahlen = ", ".join(f"{sp}:{pro_sprache[sp][praefix]}" for sp in sorted(uebersicht[praefix]))
    print(f"    {praefix}: {zahlen}")

if kollisionen:
    print()
    for sprache, doppelt in sorted(kollisionen.items()):
        print(f"[Praefixe] KOLLISION in {sprache}: {doppelt}")
    sys.exit(1)
print(f"\n[Praefixe] {len(pro_sprache)} Kataloge, in keinem ein Buchstabe doppelt belegt")
