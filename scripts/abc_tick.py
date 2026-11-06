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
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(REPO, "menschenrechte_books")
STATE = os.path.expanduser("~/.hermes/cache/abc_tick_state.json")


def offene(lang: str) -> int:
    """Wie viele Artikel hat die Sprache insgesamt noch offen (alle A-Bände zusammen)?"""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import abc_lauf
    return max(0, 30 - len(abc_lauf.verhandelt(lang)))


def laufsuffix(variante: str) -> str:
    """Verzeichnis-Suffix eines Arms — eine Quelle: abc_lauf.VARIANTEN."""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import abc_lauf
    return abc_lauf.VARIANTEN.get(variante, {}).get("suffix", "")


def passende_buchart(lang: str, wunsch: str) -> str:
    """Buchart, die für diese Sprache wirklich offene Artikel hat.

    Der Tick wechselt stündlich zwischen Song und Prosa; nicht jede Sprache hat
    beides (Koreanisch hatte nur das Song-Album). Ohne diesen Fallback bricht der
    Lauf mit rc=2 ab und meldet "kein Buch mit offenen Artikeln"
    (gemessen 2026-11-06, 05:30).
    """
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import abc_lauf
    for art in (wunsch, "prosa" if wunsch == "song" else "song"):
        if abc_lauf.quelle(lang, art):
            return art
    return wunsch


def fehlversuche(lang: str, grenze: int = 2) -> int:
    """Wie viele der letzten Läufe dieser Sprache sind an der Schranke gerissen?

    Ohne diese Bremse dreht der Tick ewig dieselbe Sprache: steht die Schranke,
    bleibt der Artikel offen, die Sprache bleibt Kandidat (gemessen 2026-11-06:
    Japanisch dreimal hintereinander, jedes Mal ein neuer Band ohne Kapitel im Repo).
    """
    pfad = os.path.expanduser("~/.hermes/logs/abc_log.jsonl")
    if not os.path.exists(pfad):
        return 0
    laeufe = []
    for zeile in open(pfad, encoding="utf-8"):
        try:
            d = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if (d.get("sprache") or "").lower() == lang.lower():
            laeufe.append(d.get("exit"))
    zahl = 0
    for eintrag in reversed(laeufe):
        if eintrag == 4:
            zahl += 1
        else:
            break
    return zahl


def gerissene_kapitel(varianten: str, seit: float) -> list:
    """Kapitel ohne bestandene Endschranke, die seit `seit` entstanden sind."""
    treffer = []
    for variante in [v.strip() for v in varianten.split(",") if v.strip()]:
        for d in glob.glob(f"{REPO}/menschenrechte_books/buch_*{laufsuffix(variante)}"):
            if os.path.getmtime(d) < seit:
                continue
            for f in glob.glob(f"{d}/*_art_*.md"):
                if "manual_ending_ok: true" not in open(f, encoding="utf-8").read():
                    treffer.append(os.path.basename(f))
    return treffer


def protokollieren(daten: dict) -> None:
    """Eine JSON-Zeile je Lauf in web/api/abc_log.jsonl (Wächter-Quelle)."""
    # NICHT ins Repo: web/api gilt als Korpus-Bereich, corpus-sync bricht sonst mit
    # "das ueberschreibt vorhandene Tales" ab (gemessen 2026-11-06, 06:21).
    pfad = os.path.expanduser("~/.hermes/logs/abc_log.jsonl")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "a", encoding="utf-8") as f:
        f.write(json.dumps(daten, ensure_ascii=False) + "\n")


def committen(nachricht: str) -> str:
    """Bände und Web-Index committen und pushen.

    Ohne diesen Schritt bleibt der Korpus lokal: der Stunden-Tick erzeugte Bände,
    die weder auf GitHub noch bei Hugging Face ankamen (gemessen 2026-11-06:
    17 Bände untracked, HF-Datensatz unverändert). Der alte Kapitel-Runner hat das
    erledigt; der ist abgeschaltet, seit A/B/C allein läuft.
    """
    # Nur vorhandene Pfade stagen: ein fehlendes Pfad-Argument laesst `git add`
    # komplett scheitern, dann wird NICHTS committet (im Prüfrepo aufgefallen, 2026-11-06).
    pfade = [p for p in ("menschenrechte_books", "web/books.json", "web/api")
             if os.path.exists(os.path.join(REPO, p))]
    if pfade:
        subprocess.run(["git", "add", "--", *pfade], cwd=REPO, capture_output=True)
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
    if pu.returncode != 0:
        # Der CI-Lauf schreibt die README selbst zurueck ("[skip ci]"); ohne Rebase
        # scheitert der naechste Push als non-fast-forward (gemessen 2026-11-06).
        subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"],
                       cwd=REPO, capture_output=True, text=True, timeout=240)
        pu = subprocess.run(["git", "push", "origin", "main"], cwd=REPO, capture_output=True,
                            text=True, timeout=240)
    return "committet und gepusht" if pu.returncode == 0 else ("committet, Push fehlgeschlagen: "
                                                             + (pu.stderr or pu.stdout).strip()[-100:])

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--varianten", default="C3",
                    help="Arme je Lauf (Standard C3 = C-mittel mit harter Formschranke)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sprachen = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{REPO}/locales/*.json"))
    zustand = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    kandidaten = [(offene(s), s) for s in sprachen]
    kandidaten = [k for k in kandidaten if k[0] > 0]
    gesperrt = {s for _, s in kandidaten if fehlversuche(s) >= 2}
    if gesperrt:
        rest = [k for k in kandidaten if k[1] not in gesperrt]
        print(f"  Übersprungen (2× Schranke gerissen): {', '.join(sorted(gesperrt))}")
        if rest:
            kandidaten = rest
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
    buchart = passende_buchart(lang, buchart)
    print(f"  Sprache: {lang} ({max_offen} Artikel offen) · Buchart {buchart} · "
          f"Arme {a.varianten} · Kandidaten {len(kandidaten)}")

    if a.dry_run:
        subprocess.run([sys.executable, "scripts/abc_lauf.py", "--lang", lang, "--buchart", buchart,
                        "--varianten", a.varianten, "--dry-run"], cwd=REPO)
        return 0

    # Die Sperre hält abc_lauf selbst (.rotation.lock); hier keine zweite,
    # sonst blockiert der Unterprozess gegen den eigenen Elternprozess.
    start_zeit = time.time()
    bbox = "Triple"
    r = subprocess.run([sys.executable, "scripts/abc_lauf.py", "--lang", lang, "--buchart", buchart,
                        "--varianten", a.varianten],
                       cwd=REPO, capture_output=True, text=True, timeout=3000)
    print(r.stdout.strip()[-800:])
    mm = __import__("re").search(r"Artikel (art_\d+)", r.stdout)
    if mm:
        bbox = mm.group(1)
    if r.returncode != 0:
        print("  FEHLER:", (r.stderr or r.stdout).strip()[-300:])
        return r.returncode
    # Gerissene Schranke ZUERST pruefen: ein Fallback-Kapitel darf nicht in den Korpus.
    gerissen = gerissene_kapitel(a.varianten, start_zeit)
    if gerissen:
        print(f"  SCHRANKE GERISSEN: {len(gerissen)} Kapitel ohne bestandene Pruefung — "
              f"{gerissen[:2]}")
        print("  Nicht committet. Exit 4 loest algorithmic-alert@ aus.")
        protokollieren({"zeit": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                        "sprache": lang, "buchart": buchart, "arme": a.varianten,
                        "artikel": bbox, "exit": 4, "gerissen": gerissen})
        return 4
    ergebnis = committen(f"feat(abc): {lang.upper()} {bbox} — Arm {a.varianten}")
    print(" ", ergebnis)
    protokollieren({"zeit": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                    "sprache": lang, "buchart": buchart, "arme": a.varianten,
                    "artikel": bbox, "exit": 0, "gerissen": [], "commit": ergebnis})

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"zuletzt": lang, "buchart": buchart, "zeit": __import__("datetime").datetime.now().isoformat(timespec="seconds")},
              open(STATE, "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
