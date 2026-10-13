"""Rotations-Runner: 10 Runden, vier Modelle, jedes Kapitel in einem wechselnden Buch.

Warum es diesen Runner gibt: der Durchsatz ist GPU-gebunden (ein Modell, ein Slot), also
serialisiert der Runner statt zu parallelisieren. Jedes Kapitel durchlaeuft unveraendert die
Produktions-CLI (generate_pipeline.py --mode append-chapter), damit ALLE Schranken greifen:
Pflichtblock (count == 1 als Stempelzeile), Ganzkoerper-Scan fuer sterile Genres, Repetition-Guard,
Fremdcode-Sperre, Historienfenster. Der Runner ersetzt keine Schranke und umgeht keine.

Resumierbar: der Zustand liegt in einer JSON-Datei, ein abgebrochener Lauf setzt dort fort.
Jede Runde wird als Datei protokolliert (model, backend, tokens, versuche, dauer).

Aufruf:
    python3 scripts/run_model_rotation.py --dry-run          # nur den Plan zeigen
    python3 scripts/run_model_rotation.py --runden 1         # eine Runde wirklich schreiben
    python3 scripts/run_model_rotation.py                    # alle 10 Runden
"""
import argparse
import fcntl
import glob
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZUSTAND = os.path.join(REPO, "web", "api", "rotation_state.json")
PROTOKOLL = os.path.join(REPO, "web", "api", "rotation_log.jsonl")
LOCK = os.path.join(REPO, ".rotation.lock")

# Modell -> Backend. Der Pool ist bewusst heterogen: der Free-Tier-Verbund (OpenRouter) und
# DeepSeek laufen ueber die API, die lokalen Modelle bleiben als Option fuer Offline-Betrieb.
# Gemessen 2026-10-12: alle vier API-Slots antworten in unter einer Sekunde; die lokalen Slugs
# (qwen2.5:7b, mistral, cogito) sind hier auskommentiert, weil sie in sterilen Genres messbar
# an der Ganzkoerper-Schranke scheitern (3/3 Versuche) und dann Fallbacks schreiben.
POOL = [
    ("deepseek-chat", "deepseek"),
    ("nvidia/nemotron-3-ultra-550b-a55b:free", "openrouter"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "openrouter"),
    # apodex-1.1-mini wieder entfernt (2026-10-12): 81.741 Token bei 2.262 Woertern = 36,1 Token je Wort,
    # 0 von 10 im ersten Versuch, 3 Fallbacks, 3 harte Abbrueche — kein verwertbares Kapitel.
    # Der Pool laeuft bewusst als Trio: die drei verifizierten Leistungstraeger, keine Rate-Limit-Kollisionen.
    # ("qwen2.5:7b", "ollama"),
    # ("mistral", "ollama"),
    # ("cogito", "ollama"),
]


# Baende, die nur API-Modelle schreiben duerfen: das sterile Geraetehandbuch scheitert bei den
# lokalen Modellen reproduzierbar an der Ganzkoerper-Schranke (qwen2.5:7b: 3/3 Versuche verworfen,
# belegt 2026-10-12). Ein lokales Modell springt dann auf den naechsten Band.
NUR_API_MODELLE = ("buch_001_",)

# Modelle, die unter Versmass unbrauchbar sind (belegt 2026-10-13, buch_018): super-120b brauchte
# 24,29 Token je Wort und ueber 5 Minuten je Kapitel, waehrend deepseek 1,36 und ultra-550b 4,99
# lagen. Sie werden fuer Genres mit "stanza_zeilen" (Lyrik) uebersprungen.
KEIN_VERSMASS = ("nvidia/nemotron-3-super-120b-a12b:free",)
_LOCALE_CACHE: dict = {}


def _stil_flags(book_id: str) -> dict:
    """Flags des Buchstils aus der Locale seiner eigenen Sprache (mit kleinem Cache)."""
    pfad = os.path.join(REPO, "menschenrechte_books", book_id, "book.json")
    meta = json.load(open(pfad, encoding="utf-8"))
    sprache = (meta.get("language") or "DE").upper()
    if sprache not in _LOCALE_CACHE:
        loc = json.load(open(os.path.join(REPO, "locales", sprache.lower() + ".json"), encoding="utf-8"))
        _LOCALE_CACHE[sprache] = loc
    return _LOCALE_CACHE[sprache].get("style_flags", {}).get(meta.get("style") or "", {})


def band_erlaubt(book_id: str, modell: str) -> bool:
    """Versmass-Genres nur mit Modellen, die sie messbar beherrschen."""
    if modell not in KEIN_VERSMASS:
        return True
    return not _stil_flags(book_id).get("stanza_zeilen")


def band_waehlen(alle: list, index: int, backend: str, modell: str = "") -> str:
    """Naechster erlaubter Band ab index; lokale Modelle ueberspringen NUR_API_MODELLE,
    Versmass-Modelle ueberspringen Lyrik-Baende."""
    for versatz in range(len(alle)):
        kandidat = alle[(index + versatz) % len(alle)]
        if backend == "ollama" and kandidat.startswith(NUR_API_MODELLE):
            continue
        if modell and not band_erlaubt(kandidat, modell):
            continue
        return kandidat
    raise RuntimeError("kein zulaessiger Band im Pool — Sperrliste zu gross?")


def band_sprache(book_id: str) -> str:
    """Sprache eines Buchs aus seiner eigenen book.json — kein stiller DE-Default.

    Belegt 2026-10-12: der Runner uebergab fuer alle Baende --lang DE. Fuer den englischen Limericks-Band
    wurde damit die falsche Locale geladen, die Schranke fiel aus und es entstanden sieben deutsche
    Kapitel mit Handbuch-Praefix in einem englischen Band.
    """
    pfad = os.path.join(REPO, "menschenrechte_books", book_id, "book.json")
    meta = json.load(open(pfad, encoding="utf-8"))
    sprache = (meta.get("language") or "").strip()
    if not sprache:
        raise RuntimeError(f"{book_id}/book.json hat kein Feld 'language' — Sprache nicht raten")
    return sprache.upper()


def buecher() -> list:
    """Alle Buecher mit book.json, stabil sortiert (Buch 1 zuerst)."""
    treffer = []
    for d in sorted(glob.glob(os.path.join(REPO, "menschenrechte_books", "buch_*"))):
        if os.path.isfile(os.path.join(d, "book.json")):
            treffer.append(os.path.basename(d))
    return treffer


def zustand_laden() -> dict:
    if os.path.isfile(ZUSTAND):
        try:
            return json.load(open(ZUSTAND, encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  [Runner] Zustandsdatei unlesbar — Lauf startet neu: {ZUSTAND}", flush=True)
    return {"erledigt": [], "runden": {}}


def zustand_speichern(z: dict) -> None:
    os.makedirs(os.path.dirname(ZUSTAND), exist_ok=True)
    with open(ZUSTAND, "w", encoding="utf-8") as f:
        json.dump(z, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def kapitel_statistik(book_id: str, vorher: set) -> dict:
    """Liest das neu entstandene Kapitel und zieht die Metriken aus dem Frontmatter."""
    ordner = os.path.join(REPO, "menschenrechte_books", book_id)
    neu = [p for p in glob.glob(os.path.join(ordner, "[0-9][0-9]_*.md"))
           if os.path.basename(p) not in vorher and not os.path.basename(p).startswith("00_")]
    if not neu:
        return {"datei": None, "hinweis": "kein Kapitel geschrieben"}
    pfad = sorted(neu)[-1]
    text = open(pfad, encoding="utf-8").read()
    kopf = {}
    if text.startswith("---"):
        for zeile in text.split("---")[1].strip().splitlines():
            if ":" in zeile:
                schluessel, wert = zeile.split(":", 1)
                kopf[schluessel.strip()] = wert.strip().strip('"')
    rumpf = text.split("---", 2)[2]
    return {
        "datei": os.path.basename(pfad),
        "woerter": len(rumpf.split()),
        "ending_ok": kopf.get("manual_ending_ok"),
        "versuche": kopf.get("manual_ending_attempts"),
        "code": kopf.get("manual_ending_code"),
        "model": kopf.get("model"),
        "backend": kopf.get("backend"),
        "tokens": kopf.get("tokens_generated"),
        "dauer_s": kopf.get("duration_seconds"),
    }


def git_schritt(buch_id: str, runde: int, modell: str) -> str:
    """Ein Commit pro Kapitel — mit Datei-Lock, damit sich nichts mit dem Tale-Sync ueberschneidet."""
    with open(LOCK, "w") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX)
        subprocess.run([sys.executable, "scripts/build_books_index.py"], cwd=REPO, capture_output=True)
        subprocess.run(["git", "add", "menschenrechte_books", "web/books.json", "web/api/"], cwd=REPO,
                       capture_output=True)
        nachricht = f"feat(rotation): Runde {runde} — {modell} in {buch_id}"
        committen = subprocess.run(["git", "commit", "-q", "-m", nachricht], cwd=REPO,
                                   capture_output=True, text=True)
        fcntl.flock(sperre, fcntl.LOCK_UN)
    if committen.returncode != 0 and "nothing to commit" not in (committen.stdout + committen.stderr):
        return "Commit uebersprungen: " + (committen.stderr or committen.stdout).strip()[:80]
    return "committet"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runden", type=int, default=10, help="Anzahl Runden (Default 10)")
    p.add_argument("--dry-run", action="store_true", help="nur den Plan ausgeben, nichts schreiben")
    p.add_argument("--push", action="store_true", help="nach jeder Runde pushen")
    p.add_argument("--buecher", default=None,
                   help="Komma-Liste von Band-Praefixen, auf die der Lauf beschraenkt wird "
                        "(z.B. buch_015,buch_016); Default ist der ganze Bestand.")
    args = p.parse_args()

    alle = buecher()
    if args.buecher:
        wunsch = [b.strip() for b in args.buecher.split(",") if b.strip()]
        gefiltert = [b for b in alle if any(b.startswith(w) for w in wunsch)]
        fehlend = [w for w in wunsch if not any(b.startswith(w) for b in gefiltert)]
        if fehlend:
            print(f"[Runner] unbekannte Band-Praefixe: {fehlend}", flush=True)
            return 1
        alle = gefiltert
        print(f"[Runner] eingeschraenkt auf {len(alle)} Baende: {[b[:24] for b in alle]}", flush=True)
    if len(alle) < 1:
        print(f"[Runner] kein Buch mit book.json gefunden: {alle}", flush=True)
        return 1
    if len(alle) == 1:
        # Ein-Band-Lauf ist zulaessig (gezielter Neuaufbau, z.B. der englische Limericks-Band).
        print(f"[Runner] Ein-Band-Lauf: {alle[0][:44]} — jedes Modell schreibt in dasselbe Buch.",
              flush=True)
    z = zustand_laden()
    # Offene Slots aus dem ECHTEN Plan zaehlen, nicht gegen den globalen Zustand: bei einem gefilterten
    # Lauf (--buecher) haette die alte Rechnung "offen: 0" gemeldet, obwohl 40 Kapitel anstehen.
    offen = 0
    for runde in range(1, args.runden + 1):
        for i, (modell, backend) in enumerate(POOL):
            buch = band_waehlen(alle, ((runde - 1) * len(POOL) + i) % len(alle), backend, modell)
            if f"r{runde}:{modell}:{buch}" not in z["erledigt"]:
                offen += 1
    print(f"[Runner] {len(alle)} Buecher | {len(POOL)} Modelle | {args.runden} Runden "
          f"= {args.runden * len(POOL)} Slots | offen: {offen}", flush=True)
    print(f"[Runner] Pool: {', '.join(f'{m} ({b})' for m, b in POOL)}", flush=True)

    fehler = []
    for runde in range(1, args.runden + 1):
        for i, (modell, backend) in enumerate(POOL):
            # Fortlaufender Slot-Zaehler statt (i + runde): die alte Formel traf nur 13 der 18 Baende,
            # buch_015 bis buch_018 fielen aus dem Lauf (belegt 2026-10-12). Mit Schrittweite 1 ueber
            # den gesamten Slot-Index kommt jeder Band zuverlaessig dran.
            slot = (runde - 1) * len(POOL) + i
            buch = band_waehlen(alle, slot % len(alle), backend, modell)
            marke = f"r{runde}:{modell}:{buch}"
            if marke in z["erledigt"]:
                continue
            print(f"\n[Runde {runde}] {modell} ({backend}) -> {buch}", flush=True)
            if args.dry_run:
                z["erledigt"].append(marke + ":dry")
                continue
            vorher = {os.path.basename(p) for p in glob.glob(
                os.path.join(REPO, "menschenrechte_books", buch, "[0-9][0-9]_*.md"))}
            start = time.monotonic()
            r = subprocess.run([sys.executable, "generate_pipeline.py", "--mode", "append-chapter",
                                "--book-id", buch, "--lang", band_sprache(buch), "--backend", backend,
                                "--model", modell], cwd=REPO, capture_output=True, text=True, timeout=7200)
            dauer = round(time.monotonic() - start, 1)
            for zeile in (r.stdout + r.stderr).strip().splitlines()[-4:]:
                print("  " + zeile, flush=True)
            stat = kapitel_statistik(buch, vorher)
            eintrag = {"runde": runde, "modell": modell, "backend": backend, "buch": buch,
                       "exit": r.returncode, "dauer_s": dauer, **stat}
            os.makedirs(os.path.dirname(PROTOKOLL), exist_ok=True)
            with open(PROTOKOLL, "a", encoding="utf-8") as f:
                f.write(json.dumps(eintrag, ensure_ascii=False, sort_keys=True) + "\n")
            print(f"  -> exit={r.returncode} dauer={dauer}s {stat}", flush=True)
            if r.returncode not in (0, 2):   # 2 = Fallback geschrieben (dokumentiert), alles andere = Fehler
                fehler.append((marke, r.returncode))
            z["erledigt"].append(marke)
            z["runden"].setdefault(str(runde), []).append(eintrag)
            zustand_speichern(z)
            meldung = git_schritt(buch, runde, modell)
            print(f"  git: {meldung}", flush=True)
            if args.push:
                subprocess.run(["git", "push", "origin", "main"], cwd=REPO, capture_output=True)
        if args.dry_run:
            print(f"[Runde {runde}] Plan ausgegeben", flush=True)
    if not args.dry_run:
        zustand_speichern(z)
        print(f"\n[Runner] fertig. Fehlerhafte Laeufe: {fehler or 'keine'}", flush=True)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
