#!/usr/bin/env python3
import argparse
import datetime
import glob
import json
import os
import random
import re
import sys
import time

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")
LOCALES_DIR = os.path.join(BASE_DIR, "locales")
TALES_DIR = os.path.join(BASE_DIR, "menschenrechte_tales")
QUARANTINE_DIR = os.path.join(BASE_DIR, "quarantine")
PID_FILE = os.path.join(BASE_DIR, "daemon.pid")

# Ausgleichendes Sprach-Sampling: --lang auto-balanced
AUTO_LANG = "auto-balanced"
AUTO_LANG_ALIASES = {AUTO_LANG, "auto"}

# Heuristische Indikatoren für unregulierte Gewaltverherrlichung / Bruch der Schadensminimierung
TOXIC_PATTERNS = [
    r"\b(waffenbesitz\s+als\s+menschenrecht)\b",
    r"\b(jeder\s+braucht\s+eine\s+waffe)\b",
    r"\b(selbstjustiz\s+ist\s+die\s+l[oö]sung)\b",
    r"\b(t[oö]tung\s+ohne\s+konsequenz)\b"
]


def check_system_load() -> bool:
    """Gibt True zurück, wenn die 1-Minuten-Last kleiner als 85% der Kerne ist."""
    try:
        load1, _, _ = os.getloadavg()
        cores = os.cpu_count() or 1
        return (load1 / cores) < 0.85
    except Exception:
        return True


def audit_guardrail(text: str) -> tuple[bool, str]:
    """Prüft den Text auf Einhaltung der Grundsätze der Schadensminimierung."""
    lowered = text.lower()
    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"Toxische Phrase erkannt: {pattern}"
    
    # Text muss substanziell sein (> 250 Zeichen)
    if len(text.strip()) < 250:
        return False, "Text unterschreitet Mindestlänge von 250 Zeichen."

    return True, "Passed"


def load_article(article_id: str, lang: str = "DE") -> dict:
    lang_dir = os.path.join(ARTICLES_DIR, lang.lower())
    path = os.path.join(lang_dir, f"{article_id}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Artikel nicht gefunden: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
            body = parts[2].strip()

    return {"meta": meta, "body": body, "id": article_id}


def load_locale(lang: str = "DE") -> dict:
    path = os.path.join(LOCALES_DIR, f"{lang.lower()}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Locale nicht gefunden: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(article_data: dict, style_name: str, locale: dict) -> str:
    styles = locale.get("styles", {})
    style_desc = styles.get(style_name, f"Erzählung im Stil: {style_name}")
    core_rule = locale.get("guardrail_prompt", (
        "Die Unversehrtheit des menschlichen Lebens hat absolute Priorität über Tradition, Hobby oder Bequemlichkeit. "
        "Strukturelle Schadensminimierung, Verzögerung von Impulsen und regulierter Zugang zu tödlichen Gefahrenquellen "
        "sind das ethische Fundament – ohne plumpe Moralschlüsse."
    ))

    prompt = f"""Du bist ein literarischer Chronist des Algorithmischen Aktivismus.
Schreibe eine fesselnde Erzählung basierend auf folgendem UN-Menschenrechtsartikel.

UN-ARTIKEL ({article_data['meta'].get('title', article_data['id'])}):
{article_data['body']}

STILVORGABE:
{style_name}: {style_desc}

ETHISCHE LEITLINIE (HARM REDUCTION):
{core_rule}

FORMATVORGABE:
- Gib als erste Zeile genau eine Hauptüberschrift an: # [Titel der Geschichte]
- Starte direkt mit dem Titel, ohne Einleitungssätze oder Meta-Kommentare.
- Reine Erzählung in lebendigem, dichterischem oder analytischem Ton.
"""
    return prompt


def run_ollama_stream(prompt: str, model: str = "qwen2.5:7b", host: str = "http://localhost:11434") -> str:
    import urllib.request
    url = f"{host}/api/generate"
    req_data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("response", "")


def sanitize_filename(title: str) -> str:
    clean = re.sub(r"[^\w\s\-äöüÄÖÜß]", "", title)
    clean = re.sub(r"[\s\-]+", "_", clean).strip("_")
    return clean[:60] or f"tale_{int(time.time())}"


def extract_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return f"Tale_{int(time.time())}"


def save_tale(text: str, article_id: str, style_name: str, lang: str, model: str) -> tuple[str, bool]:
    os.makedirs(TALES_DIR, exist_ok=True)
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    os.makedirs(os.path.join(TALES_DIR, lang.upper()), exist_ok=True)

    passed, reason = audit_guardrail(text)
    title = extract_title(text)
    slug = sanitize_filename(title)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tokens = len(text.split())

    frontmatter = f"""---
title: "{title}"
article: "{article_id}"
style: "{style_name}"
language: "{lang.upper()}"
model: "{model}"
created_at: "{now}"
approx_words: {tokens}
guardrail_audit:
  passed: {str(passed).lower()}
  status: "{reason}"
---

"""
    full_content = frontmatter + text.strip() + "\n"

    if passed:
        target_path = os.path.join(TALES_DIR, lang.upper(), f"{slug}.md")
    else:
        target_path = os.path.join(QUARANTINE_DIR, f"{slug}_rejected.md")

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return target_path, passed


def synthesize_one(article_id: str, style: str, lang: str, model: str, host: str):
    art = load_article(article_id, lang)
    loc = load_locale(lang)
    prompt = build_prompt(art, style, loc)
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Synthese: {article_id} | Stil: {style} | Lang: {lang}...", flush=True)

    output = run_ollama_stream(prompt, model=model, host=host)
    if not output:
        print("  -> Leere Antwort vom Modell erhalten.", flush=True)
        return

    path, passed = save_tale(output, article_id, style, lang, model)
    state_str = "GESPEICHERT" if passed else "QUARANTÄNE"
    print(f"  -> [{state_str}] {os.path.basename(path)}", flush=True)


# ---------------------------------------------------------------------------
# Sprach-Inventar & ausgleichendes Sampling (--lang auto-balanced)
# ---------------------------------------------------------------------------

def language_candidates():
    """Sprachkuerzel, die in articles/ oder locales/ ueberhaupt vorkommen."""
    names = set()
    if os.path.isdir(ARTICLES_DIR):
        for name in os.listdir(ARTICLES_DIR):
            if os.path.isdir(os.path.join(ARTICLES_DIR, name)):
                names.add(name.lower())
    if os.path.isdir(LOCALES_DIR):
        for name in os.listdir(LOCALES_DIR):
            if name.endswith(".json"):
                names.add(os.path.splitext(name)[0].lower())
    return sorted(names)


def language_inventory():
    """Sprachen zur Laufzeit: Schnittmenge aus articles/<lang>/*.md (nicht leer)
    UND vorhandener locales/<lang>.json mit mindestens einem Stil.

    Keine hartkodierte Sprachliste: ohne Artikel oder ohne Locale wird die
    Sprache uebersprungen statt ins Leere zu laufen.
    """
    inventory = []
    for name in language_candidates():
        articles = sorted(
            os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(ARTICLES_DIR, name, "*.md"))
        )
        if not articles:
            continue
        locale_path = os.path.join(LOCALES_DIR, f"{name}.json")
        if not os.path.isfile(locale_path):
            continue
        try:
            with open(locale_path, "r", encoding="utf-8") as f:
                styles = list(json.load(f).get("styles", {}).keys())
        except (OSError, ValueError):
            continue
        if not styles:
            continue
        inventory.append({"lang": name.upper(), "articles": articles, "styles": styles})
    return inventory


def skipped_languages():
    """Kandidaten ohne Artikel/Locale inkl. Grund - diese werden nie gezogen."""
    active = {entry["lang"].lower() for entry in language_inventory()}
    skipped = []
    for name in language_candidates():
        if name in active:
            continue
        if not glob.glob(os.path.join(ARTICLES_DIR, name, "*.md")):
            reason = f"keine Artikel in articles/{name}/"
        elif not os.path.isfile(os.path.join(LOCALES_DIR, f"{name}.json")):
            reason = f"locales/{name}.json fehlt"
        else:
            reason = f"locales/{name}.json ohne Stile"
        skipped.append((name.upper(), reason))
    return skipped


def count_tales(lang):
    """Bestand: Tale-Dateien in menschenrechte_tales/<LANG>/*.md."""
    return len(glob.glob(os.path.join(TALES_DIR, lang.upper(), "*.md")))


def balance_weight(count):
    """Inverses Gewicht 1/(Bestand+1) (Laplace-Glaettung): Rueckstand wird
    aufgeholt, starke Sprachen bleiben ziehbar, Division durch 0 entfaellt."""
    return 1.0 / (float(count) + 1.0)


def pick_balanced_language(inventory):
    """Zieht eine Sprache invers zum Bestand; der Bestand wird live von Platte gelesen."""
    weights = [balance_weight(count_tales(entry["lang"])) for entry in inventory]
    return random.choices(inventory, weights=weights, k=1)[0]


def build_auto_inventory(article, style):
    """Sprach-Inventar inkl. optionaler Einschraenkung durch --article / --style."""
    inventory = language_inventory()
    if article:
        inventory = [entry for entry in inventory if article in entry["articles"]]
    if style:
        inventory = [entry for entry in inventory if style in entry["styles"]]
    return inventory


def format_distribution_table(inventory, start, end, picks, draws):
    """Tabelle: eine Spalte je Sprache (Ziehungsverteilung des Trockenlaufs)."""
    langs = [entry["lang"] for entry in inventory]
    start_weights = [balance_weight(start[lang]) for lang in langs]
    weight_sum = sum(start_weights) or 1.0
    rows = [
        ("Artikel (articles/)", [str(len(e["articles"])) for e in inventory],
         str(sum(len(e["articles"]) for e in inventory))),
        ("Stile (locales/)", [str(len(e["styles"])) for e in inventory],
         str(sum(len(e["styles"]) for e in inventory))),
        ("Bestand Start (Tales)", [str(start[l]) for l in langs], str(sum(start.values()))),
        ("Gewicht 1/(n+1)", [f"{balance_weight(start[l]):.6f}" for l in langs], "-"),
        ("P(Start)", [f"{100.0 * balance_weight(start[l]) / weight_sum:.2f}%" for l in langs], "100.00%"),
        (f"Ziehungen (N={draws})", [str(picks[l]) for l in langs], str(sum(picks.values()))),
        ("Anteil Ziehungen", [f"{100.0 * picks[l] / draws:.2f}%" for l in langs], "100.00%"),
        ("Bestand Ende (sim.)", [str(end[l]) for l in langs], str(sum(end.values()))),
    ]
    label_w = max(len(row[0]) for row in rows) + 2
    col_w = max(10, max(len(l) for l in langs), max(len(v) for row in rows for v in row[1])) + 2
    total_w = max(6, max(len(row[2]) for row in rows)) + 2

    header = "".join(f"{l:>{col_w}}" for l in langs) + f"{'Summe':>{total_w}}"
    lines = [f"{'Metrik':<{label_w}}{header}", "-" * (label_w + len(header))]
    for label, values, total in rows:
        lines.append(f"{label:<{label_w}}" + "".join(f"{v:>{col_w}}" for v in values) + f"{total:>{total_w}}")
    return "\n".join(lines)


def print_dry_run(inventory, draws):
    """Trockenlauf: N Sprach-Ziehungen simulieren (adaptiv wie der Daemon). Schreibt nichts."""
    start = {entry["lang"]: count_tales(entry["lang"]) for entry in inventory}
    end = dict(start)
    picks = {entry["lang"]: 0 for entry in inventory}

    for _ in range(draws):
        weights = [balance_weight(end[entry["lang"]]) for entry in inventory]
        chosen = random.choices(inventory, weights=weights, k=1)[0]
        picks[chosen["lang"]] += 1
        end[chosen["lang"]] += 1  # emuliert das Schreiben eines Tales

    skipped = skipped_languages()
    print("Modus         : --lang auto-balanced (inverser Bestand, adaptiv wie im Daemon)")
    print(f"Ziehungen     : {draws}")
    print("Inventar      : articles/<lang>/*.md (nicht leer) UND locales/<lang>.json (mit Stilen)")
    if skipped:
        print("Uebersprungen : " + "; ".join(f"{lang} ({reason})" for lang, reason in skipped))
    else:
        print("Uebersprungen : keine")
    print()
    print(format_distribution_table(inventory, start, end, picks, draws))
    print()
    drawn = sum(picks.values())
    print(f"Pruefung: Summe Ziehungen = {drawn} (Soll {draws}) -> {'OK' if drawn == draws else 'FEHLER'}")
    print("Pruefung: Ziehungen ausserhalb des Inventars = 0 -> OK "
          "(strukturell: nur Sprachen mit Artikeln UND Locale sind ziehbar)")
    print(f"Bestandsspanne max-min: Start {max(start.values()) - min(start.values())} "
          f"-> simuliert {max(end.values()) - min(end.values())}")


def print_locked_dry_run(lang, draws):
    """Trockenlauf fuer manuell erzwungene Sprache: alle Ziehungen gehen an diese Sprache."""
    stock = count_tales(lang)
    print(f"Modus         : --lang {lang} (manuell erzwungen, kein Sampling)")
    print(f"Ziehungen     : {draws}")
    print()
    print(f"{'Sprache':<22}{lang:>12}{'Summe':>12}")
    print(f"{'Bestand (Tales)':<22}{stock:>12}{stock:>12}")
    print(f"{'Ziehungen':<22}{draws:>12}{draws:>12}")


def run_auto_balanced(args, host):
    """Ausgleichendes Sampling ueber alle Sprachen mit Artikeln UND Locale."""
    inventory = build_auto_inventory(args.article, args.style)
    if not inventory:
        print("Keine Sprache mit Artikeln UND Locale gefunden "
              "(articles/<lang>/*.md + locales/<lang>.json).")
        sys.exit(1)

    if args.dry_run > 0:
        print_dry_run(inventory, args.dry_run)
        return

    stock = ", ".join(f"{entry['lang']}={count_tales(entry['lang'])}" for entry in inventory)
    print(f"Sprach-Rotation aktiv (inverser Bestand): {stock}", flush=True)

    if args.daemon:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        print(f"Daemon aktiv (PID: {os.getpid()}). Last-Monitor scharfgeschaltet.")

        try:
            while True:
                if not check_system_load():
                    print("Systemlast > 85%. Pausiere 30 Sekunden...", flush=True)
                    time.sleep(30)
                    continue

                # Inventar jeden Durchlauf neu bestimmen: neu hinzugekommene Sprachen
                # (Artikel+Locale) laufen ohne Neustart mit, unvollstaendige entfallen.
                current = build_auto_inventory(args.article, args.style)
                if not current:
                    print("Kein Sprach-Inventar (Artikel+Locale) vorhanden. "
                          "Pausiere 30 Sekunden...", flush=True)
                    time.sleep(30)
                    continue

                entry = pick_balanced_language(current)
                article_id = args.article or random.choice(entry["articles"])
                style = args.style or random.choice(entry["styles"])
                synthesize_one(article_id, style, entry["lang"], args.model, host)
                time.sleep(args.cooldown)
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
    else:
        for _ in range(args.limit):
            entry = pick_balanced_language(inventory)
            article_id = args.article or random.choice(entry["articles"])
            style = args.style or random.choice(entry["styles"])
            synthesize_one(article_id, style, entry["lang"], args.model, host)


def main():
    parser = argparse.ArgumentParser(description="Algorithmic Activism Synthesis Pipeline")
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument(
        "--lang",
        default="DE",
        help="Zielsprache (z.B. DE) oder 'auto-balanced': ausgleichendes Sampling ueber alle "
             "Sprachen, fuer die Artikel UND Locale real vorliegen (Gewicht invers zum Bestand).",
    )
    parser.add_argument("--article", default=None)
    parser.add_argument("--style", default=None)
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--cooldown", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--dry-run",
        type=int,
        default=0,
        metavar="N",
        help="N Sprach-Ziehungen simulieren und die Verteilung ausgeben (schreibt nichts).",
    )
    parser.add_argument("--seed", type=int, default=None,
                        help="Zufallsseed fuer reproduzierbare Ziehungen.")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    if args.lang.strip().lower() in AUTO_LANG_ALIASES:
        # Ausgleichendes Sprach-Sampling: kein manuell erzwungenes --lang.
        run_auto_balanced(args, host)
        return

    if args.dry_run > 0:
        # Manuell erzwungene Sprache: keine Verteilung, alle Ziehungen an diese Sprache.
        print_locked_dry_run(args.lang.upper(), args.dry_run)
        return

    locale_data = load_locale(args.lang)
    available_styles = list(locale_data.get("styles", {}).keys())
    available_articles = [
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(ARTICLES_DIR, args.lang.lower(), "*.md"))
    ]

    if not available_articles:
        print(f"Keine Artikel für Sprache '{args.lang}' gefunden.")
        sys.exit(1)

    if args.daemon:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        print(f"Daemon aktiv (PID: {os.getpid()}). Last-Monitor scharfgeschaltet.")

        try:
            while True:
                if not check_system_load():
                    print("Systemlast > 85%. Pausiere 30 Sekunden...", flush=True)
                    time.sleep(30)
                    continue

                sel_art = random.choice(available_articles)
                sel_style = random.choice(available_styles)
                synthesize_one(sel_art, sel_style, args.lang, args.model, host)
                time.sleep(args.cooldown)
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
    else:
        for _ in range(args.limit):
            sel_art = args.article or (random.choice(available_articles) if args.random else available_articles[0])
            sel_style = args.style or (random.choice(available_styles) if args.random else available_styles[0])
            synthesize_one(sel_art, sel_style, args.lang, args.model, host)


if __name__ == "__main__":
    main()
