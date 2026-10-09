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


def main():
    parser = argparse.ArgumentParser(description="Algorithmic Activism Synthesis Pipeline")
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--lang", default="DE")
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
