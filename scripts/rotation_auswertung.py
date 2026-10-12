"""Auswertung des Rotationslaufs nach dem festen Raster des Betreibers.

Liest web/api/rotation_log.jsonl (ein Eintrag je Kapitel) und web/api/rotation_state.json
und gibt fuenf Bloecke aus:

1. Durchsatz & Latenz   — gesamt, Mittel, Min/Max, Cloud/Free-Tier gegen lokale GPU
2. Token-Oekonomie      — Completion-Token je Modell, Token je Wort (Verbositätsfaktor)
3. Schranken-Trefferquote — Versuch 1 gegen Rejekte (2/3) gegen Fallbacks
4. Stil- und Schranken-Audit — versuche > 0 gegen versuche == 0 (ungeschuetzte Altgenres)
5. Sterile Genres       — Verhalten bei Handbuch, Manifest, Kochbuch, Lebensweisheiten

Nicht enthalten: Prompt-Token je Kapitel. Sie fallen im Adapter an (details["tokens_prompt"]),
werden aber nicht ins Frontmatter geschrieben — das steht als Luecke im Bericht, statt geschaetzt
zu werden.
"""
import json
import os
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(REPO, "web", "api", "rotation_log.jsonl")
STATE = os.path.join(REPO, "web", "api", "rotation_state.json")

LOKAL = {"qwen2.5:7b", "mistral", "cogito"}
STERILE_BAENDE = ("buch_001_", "buch_012_", "buch_015_", "buch_016_", "buch_017_")


def zahl(wert, standard=0.0) -> float:
    """Frontmatter-Werte kommen als String oder None — nie blind addieren."""
    try:
        return float(wert)
    except (TypeError, ValueError):
        return standard


def laden():
    if not os.path.isfile(LOG):
        print(f"[Auswertung] kein Protokoll unter {LOG}")
        return []
    eintraege = []
    for zeile in open(LOG, encoding="utf-8"):
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            eintraege.append(json.loads(zeile))
        except json.JSONDecodeError as e:
            print(f"[Auswertung] unlesbare Zeile uebersprungen: {e}")
    return eintraege


def kopf(titel: str) -> None:
    print(f"\n=== {titel} ===")


def main() -> int:
    e = laden()
    if not e:
        return 1
    gesamt = len(e)
    erledigt = 0
    if os.path.isfile(STATE):
        z = json.load(open(STATE, encoding="utf-8"))
        erledigt = len([m for m in z.get("erledigt", []) if not m.endswith(":dry")])
    print(f"[Auswertung] {gesamt} Kapitel im Protokoll, {erledigt} im Zustand vermerkt")

    kopf("1. Durchsatz und Latenz")
    zeiten = [zahl(x.get("dauer_s")) for x in e if zahl(x.get("dauer_s")) > 0]
    if zeiten:
        print(f"  Kapitel: {len(zeiten)} | Gesamt: {sum(zeiten)/60:.1f} min | "
              f"Mittel: {sum(zeiten)/len(zeiten):.1f} s | Min: {min(zeiten):.1f} s | Max: {max(zeiten):.1f} s")
        for gruppe, name in ((LOKAL, "lokale GPU"), (set(x["modell"] for x in e) - LOKAL, "Cloud/Free-Tier")):
            g = [zahl(x.get("dauer_s")) for x in e if x["modell"] in gruppe and zahl(x.get("dauer_s")) > 0]
            if g:
                print(f"  {name:16} {len(g):2} Kapitel | Mittel {sum(g)/len(g):6.1f} s | "
                      f"Min {min(g):5.1f} | Max {max(g):6.1f}")

    kopf("2. Token-Oekonomie (Completion-Token; Prompt-Token werden nicht protokolliert)")
    print("  %-46s %5s %9s %8s %10s %8s" % ("Modell", "Kap.", "Token", "Ø Token", "Woerter", "Token/Wort"))
    je_modell = defaultdict(list)
    for x in e:
        je_modell[x["modell"]].append(x)
    for modell, liste in sorted(je_modell.items(), key=lambda kv: -sum(zahl(v.get("tokens")) for v in kv[1])):
        tok = [zahl(v.get("tokens")) for v in liste]
        woerter = [zahl(v.get("woerter")) for v in liste if zahl(v.get("woerter")) > 0]
        verhaeltnis = (sum(tok) / sum(woerter)) if woerter and sum(woerter) else 0
        print("  %-46s %5d %9.0f %8.0f %10.0f %8.2f" % (
            modell[:46], len(liste), sum(tok), sum(tok)/len(tok), sum(woerter), verhaeltnis))

    kopf("3. Schranken-Trefferquote")
    print("  %-46s %4s %6s %6s %6s %9s" % ("Modell", "Kap.", "V1", "V2", "V3", "Fallback"))
    for modell, liste in sorted(je_modell.items()):
        zaehler = Counter()
        for v in liste:
            n = int(zahl(v.get("versuche"), -1))
            gut = str(v.get("ending_ok")).lower() == "true"
            if not gut:
                zaehler["Fallback"] += 1
            elif n == 1:
                zaehler["V1"] += 1
            elif n == 2:
                zaehler["V2"] += 1
            elif n == 3:
                zaehler["V3"] += 1
            else:
                zaehler["ohne Pruefung"] += 1
        print("  %-46s %4d %6d %6d %6d %9d" % (modell[:46], len(liste), zaehler["V1"], zaehler["V2"],
                                               zaehler["V3"], zaehler["Fallback"]))
    geprueft = sum(1 for x in e if zahl(x.get("versuche"), 0) > 0)
    print(f"\n  mit Schranke geprueft: {geprueft}/{gesamt} | ohne Pruefung: {gesamt - geprueft}")

    kopf("4. Stil- und Schranken-Audit (ungeschuetzte Baende)")
    # Ein hartes Scheitern (exit weder 0 noch 2) ist KEIN ungeschuetzter Stil, sondern ein Fehlerlauf.
    ungeschuetzt = [(x["buch"], x["modell"]) for x in e
                    if zahl(x.get("versuche"), 0) == 0 and x.get("exit") in (0, 2)]
    hart = [(x["buch"], x["modell"], x.get("exit")) for x in e if x.get("exit") not in (0, 2)]
    for buch, modell, code in hart:
        print(f"  {buch[:40]:42} {modell[:44]:46} -> exit {code} (harter Fehler, nicht ungeschuetzt)")
    for buch, gruppe in sorted(set(ungeschuetzt)):
        print(f"  {buch[:40]:42} {gruppe[:44]} -> versuche: 0 (Stil ohne style_flags)")
    if not ungeschuetzt:
        print("  kein Kapitel ohne Pruefung")

    kopf("5. Sterile Genres")
    steril = [x for x in e if str(x["buch"]).startswith(STERILE_BAENDE)]
    if not steril:
        print("  noch kein steriles Genre im Lauf")
    for x in sorted(steril, key=lambda y: y["runde"]):
        print("  R%-2s %-34s %-44s exit=%s V%s ok=%s" % (
            x["runde"], str(x["buch"])[:34], str(x["modell"])[:44], x["exit"],
            x.get("versuche"), x.get("ending_ok")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
