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


def committen(nachricht: str) -> str:
    """Bände und Web-Index committen und pushen.

    Ohne diesen Schritt bleibt der Korpus lokal: der Stunden-Tick erzeugte Bände,
    die weder auf GitHub noch bei Hugging Face ankamen (gemessen 2026-11-06:
    17 Bände untracked, HF-Datensatz unverändert). Der alte Kapitel-Runner hat das
    erledigt; der ist abgeschaltet, seit A/B/C allein läuft.
    """
    pfade = ["menschenrechte_books", "web/books.json", "web/api"]
    subprocess.run(["git", "add", *pfade], cwd=REPO, capture_output=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True)
    if not status.stdout.strip():
        return "nichts zu committen"
    c = subprocess.run(["git", "-c", "user.name=agent-runner-xomni",
                        "-c", "user.email=agent@xomni.local", "commit", "-q", "-m", nachricht],
                       cwd=REPO, capture_output=True, text=True)
    if c.returncode != 0:
        return "Commit fehlgeschlagen: " + (c.stderr or c.stdout).strip()[:80]
    pu = subprocess.run(["git", "push", "origin", "main"], cwd=REPO, capture_output=True, text=True,
                        timeout=240)
    return "committet und gepusht" if pu.returncode == 0 else ("committet, Push fehlgeschlagen: "
                                                             + (pu.stderr or pu.stdout).strip()[-80:])

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
    # Abwechselnd Song- und Prosaband: das Konzept gilt für alle Bücher, Songs haben
    # nur Vorrang, weil dort die Struktur (SALT) am stärksten greift.
    buchart = "prosa" if zustand.get("buchart") == "song" else "song"
    print(f"  Sprache: {lang} ({max_offen} Artikel offen) · Buchart {buchart} · Kandidaten {len(kandidaten)}")

    if a.dry_run:
        subprocess.run([sys.executable, "scripts/abc_lauf.py", "--lang", lang, "--buchart", buchart,
                        "--dry-run"], cwd=REPO)
        return 0

    # Die Sperre hält abc_lauf selbst (.rotation.lock); hier keine zweite,
    # sonst blockiert der Unterprozess gegen den eigenen Elternprozess.
    bbox = "Triple"
    r = subprocess.run([sys.executable, "scripts/abc_lauf.py", "--lang", lang, "--buchart", buchart],
                       cwd=REPO, capture_output=True, text=True, timeout=3000)
    print(r.stdout.strip()[-800:])
    mm = __import__("re").search(r"Artikel (art_\d+)", r.stdout)
    if mm:
        bbox = mm.group(1)
    if r.returncode != 0:
        print("  FEHLER:", (r.stderr or r.stdout).strip()[-300:])
        return r.returncode
    print(" ", committen(f"feat(abc): {lang.upper()} {bbox} — A/B/C-Triple"))

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"zuletzt": lang, "buchart": buchart, "zeit": __import__("datetime").datetime.now().isoformat(timespec="seconds")},
              open(STATE, "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
