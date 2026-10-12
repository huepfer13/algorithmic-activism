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
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
PID_FILE = os.path.join(BASE_DIR, "daemon.pid")

# Sprachdirektive je Korpus-Code. OHNE Direktive antwortet das Modell deutsch, egal was
# --lang sagt (gemessen 2026-10-12: 8 von 8 Nicht-DE-Laeufen lieferten deutschen Text).
LANGUAGE_NAMES_DE = {
    "DE": "Deutsch", "EN": "Englisch", "ES": "Spanisch", "FR": "Französisch",
    "SW": "Swahili", "PT": "Portugiesisch", "RU": "Russisch", "AR": "Arabisch",
    "ZH": "Chinesisch", "HI": "Hindi",
}

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
        raise FileNotFoundError(
            f"Locale nicht gefunden: {path} — ohne Locale gibt es keine Stilvorgaben und "
            f"keine Sprachdirektive; es wird absichtlich nichts generiert."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_catalog_prompt(lang: str, article_id: str, style_name: str) -> str | None:
    """Scaffold aus dem kuratierten Katalog `prompts/<LANG>/Art_<n>_<Thema>_<Stil>.md`.

    Reihenfolge: (a) gleicher Artikel UND Stil, (b) gleicher Artikel beliebiger Stil,
    (c) beliebige Vorlage derselben Sprache. Der Katalog liefert Persona, Sprachdirektive,
    Ethik- und Formatregeln; Stil- und Artikelbezug werden beim Zusammensetzen ersetzt,
    damit die Vorlage weder den falschen Stil noch einen fremden Artikeltext vorgibt.
    """
    d = os.path.join(PROMPTS_DIR, lang.upper())
    if not os.path.isdir(d):
        return None
    files = sorted(glob.glob(os.path.join(d, "Art_*.md")))
    if not files:
        return None
    num = str(int(re.sub(r"\D", "", article_id) or 0))
    picks = ([p for p in files if re.search(rf"Art_{num}_", p) and p.endswith(f"_{style_name}.md")]
             or [p for p in files if re.search(rf"Art_{num}_", p)]
             or [p for p in files if p.endswith(f"_{style_name}.md")]
             or files)
    for p in picks:
        with open(p, "r", encoding="utf-8") as f:
            m = re.search(r"```text\s*\n(.*?)```", f.read(), re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def build_prompt(article_data: dict, style_name: str, locale: dict, lang: str = "DE") -> str:
    """Baut den Synthese-Prompt.

    Anweisungssprache kommt aus dem Katalog (`prompts/<LANG>/`) oder aus einer
    Sprachdirektive. Ist beides nicht bestimmbar, wird ABGEBROCHEN — frueher wurde in
    diesem Fall still deutscher Text erzeugt (Messung 2026-10-12).
    """
    styles = locale.get("styles", {})
    style_desc = styles.get(style_name, f"Erzählung im Stil: {style_name}")
    core_rule = locale.get("guardrail_prompt", (
        "Die Unversehrtheit des menschlichen Lebens hat absolute Priorität über Tradition, Hobby oder Bequemlichkeit. "
        "Strukturelle Schadensminimierung, Verzögerung von Impulsen und regulierter Zugang zu tödlichen Gefahrenquellen "
        "sind das ethische Fundament – ohne plumpe Moralschlüsse."
    ))
    title = article_data["meta"].get("title", article_data["id"])
    # Die Sprachdirektive kommt NUR aus dem Katalog oder aus einer kuratierten Locale-Angabe.
    # Eine bloss erfundene Tabelle reicht nicht: eine deutsche Anweisung mit Sprachwunsch lieferte
    # am 2026-10-12 fuer AR gemischte Schrift (ARABIC 361 + HAN 430) — deshalb ist der
    # Skelett-Pfad ohne kuratierte Direktive gesperrt.
    lang_name = locale.get("instruction_language")
    erwartet = None

    katalog = load_catalog_prompt(lang, article_data["id"], style_name)
    if katalog:
        zeilen = []
        for line in katalog.splitlines():
            if line.startswith("Fokus:"):
                zeilen.append(f"Fokus: UN-Artikel {title}:")
                zeilen.append(article_data["body"])
            elif line.startswith("Stil:"):
                zeilen.append(f"Stil: {style_name}: {style_desc}")
            else:
                zeilen.append(line)
        prompt = "\n".join(zeilen)
        erwartet = LANGUAGE_NAMES_DE.get(lang.upper()) or lang_name
    else:
        if not lang_name:
            raise ValueError(
                f"Keine Anweisungssprache für '{lang}': kein Katalog unter prompts/{lang.upper()}/ und "
                f"kein 'instruction_language' in locales/{lang.lower()}.json. Abbruch statt deutscher "
                f"Ausgabe — eine deutsche Anweisung mit blossem Sprachwunsch erzeugte für AR gemischte "
                f"Schrift (Messung 2026-10-12)."
            )
        prompt = f"""Du bist ein weltklasse Autor und Ethiker. Schreibe eine völlig einzigartige, packende Geschichte auf {lang_name}.

Fokus: UN-Artikel {title}:
{article_data['body']}

Stil: {style_name}: {style_desc}

WICHTIGE ANWEISUNG (HARM REDUCTION):
{core_rule}

FORMATVORGABE:
- Gib als erste Zeile genau eine Hauptüberschrift an: # [Titel der Geschichte]
- Starte direkt mit dem Titel, ohne Einleitungssätze oder Meta-Kommentare.
- Reine Erzählung in lebendigem, dichterischem oder analytischem Ton.
"""
        erwartet = lang_name

    # Sicherung gegen die Ursache des Fehlers von heute: k e i n Prompt ohne Sprachdirektive.
    if not erwartet or erwartet.lower() not in prompt.lower():
        raise ValueError(
            f"Prompt enthält keine Sprachdirektive für {lang} ({erwartet or 'unbekannt'}) — Abbruch."
        )
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


def write_new_file(path: str, content: str) -> str:
    """Legt die Datei AN, statt zu ueberschreiben. Existiert der Name, wird _2, _3 ... angehaengt.

    Ursache: der Dateiname kommt aus dem vom Modell erzeugten Titel. Wiederkehrende Titel
    (z. B. 'Der Spiegel des Schweigens') haben am 2026-10-12 elf bestehende Korpus-Dateien
    still ersetzt. `open(..., 'x')` schliesst auch Wettlaeufe aus.
    """
    kandidat, i = path, 2
    while True:
        try:
            with open(kandidat, "x", encoding="utf-8") as f:
                f.write(content)
            return kandidat
        except FileExistsError:
            stem, ext = os.path.splitext(path)
            kandidat = f"{stem}_{i}{ext}"
            i += 1


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

    target_path = write_new_file(target_path, full_content)

    return target_path, passed


def synthesize_one(article_id: str, style: str, lang: str, model: str, host: str):
    art = load_article(article_id, lang)
    loc = load_locale(lang)
    prompt = build_prompt(art, style, loc, lang)
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Synthese: {article_id} | Stil: {style} | Lang: {lang}...", flush=True)

    output = run_ollama_stream(prompt, model=model, host=host)
    if not output:
        print("  -> Leere Antwort vom Modell erhalten.", flush=True)
        return

    path, passed = save_tale(output, article_id, style, lang, model)
    state_str = "GESPEICHERT" if passed else "QUARANTÄNE"
    print(f"  -> [{state_str}] {os.path.basename(path)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Algorithmic Activism Synthesis Pipeline")
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--lang", default="DE",
                        help="Zielsprache. Die Anweisungssprache kommt aus prompts/<LANG>/ "
                             "bzw. aus instruction_language der Locale; ohne Direktive bricht der Lauf ab.")
    parser.add_argument("--article", default=None)
    parser.add_argument("--style", default=None)
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--cooldown", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
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
