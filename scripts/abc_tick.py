#!/usr/bin/env python3
"""Ein A/B/C-Triple pro Aufruf — für den stündlichen Timer.

Wählt die Sprache mit den meisten offenen Artikeln (round-robin über eine
Zustandsdatei), damit alle Sprachen gleichmäßig wachsen, und ruft abc_lauf.py.

Aufruf: python3 scripts/abc_tick.py [--dry-run]
Zustand: ~/.hermes/cache/abc_tick_state.json
"""
import argparse
import glob
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(REPO, "menschenrechte_books")
STATE = os.path.expanduser("~/.hermes/cache/abc_tick_state.json")


def offene(lang: str) -> int:
    """Wie viele Artikel hat die Sprache insgesamt noch offen (alle A-Bände zusammen)?"""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import abc_lauf
    return max(0, 30 - len(abc_lauf.verhandelt(lang)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sprachen = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{REPO}/locales/*.json"))
    zustand = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    kandidaten = [(offene(s), s) for s in sprachen]
    kandidaten = [k for k in kandidaten if k[0] > 0]
    if not kandidaten:
        print("  alle Sprachen vollständig — nichts zu tun"); return 0
    # Sprache mit den meisten offenen Artikeln; bei Gleichstand rotieren
    max_offen = max(k[0] for k in kandidaten)
    gleich = sorted(s for n, s in kandidaten if n == max_offen)
    letzte = zustand.get("zuletzt", "")
    lang = next((s for s in gleich if s > letzte), gleich[0])
    print(f"  Sprache: {lang} ({max_offen} Artikel offen) · Kandidaten {len(kandidaten)}")

    if a.dry_run:
        subprocess.run([sys.executable, "scripts/abc_lauf.py", "--lang", lang, "--dry-run"], cwd=REPO)
        return 0

    # Gleiche Sperre wie run_model_rotation.py: ohne sie legen beide Prozesse Bände mit
    # derselben Nummer an (die Nummer wird vor dem Schreiben gelesen).
    import fcntl
    import time
    sperre = open(os.path.join(REPO, ".rotation.lock"), "w")
    ende = time.monotonic() + 900
    while True:
        try:
            fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() > ende:
                print("  Sperre .rotation.lock seit 15 min belegt — Abbruch"); return 3
            time.sleep(15)

    r = subprocess.run([sys.executable, "scripts/abc_lauf.py", "--lang", lang],
                       cwd=REPO, capture_output=True, text=True, timeout=3000)
    fcntl.flock(sperre, fcntl.LOCK_UN)
    print(r.stdout.strip()[-800:])
    if r.returncode != 0:
        print("  FEHLER:", (r.stderr or r.stdout).strip()[-300:])
        return r.returncode
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"zuletzt": lang, "zeit": __import__("datetime").datetime.now().isoformat(timespec="seconds")},
              open(STATE, "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
