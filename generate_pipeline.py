import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from itertools import product

ARTIKEL = {
    "Art_1_Wuerde": "Artikel 1: Alle Menschen sind frei und gleich an Würde und Rechten geboren.",
    "Art_3_Leben": "Artikel 3: Recht auf Leben, Freiheit und Sicherheit der Person.",
    "Art_19_Meinung": "Artikel 19: Recht auf Meinungsfreiheit und freie Meinungsäußerung."
}

SPRACHEN = {
    "DE": "Deutsch",
    "EN": "Englisch",
    "FR": "Französisch",
    "ES": "Spanisch",
    "SW": "Swahili"
}

STILE = {
    "Parabel": "Eine tiefgründige Parabel mit einer moralischen Lehre",
    "SciFi_Dystopie": "Eine dystopische Science-Fiction-Erzählung über die Gefahren von Kontrollverlust",
    "Fabel": "Eine klassische Fabel mit Tiersymbolik",
    "Philosophischer_Essay": "Ein erzählerischer, philosophischer Essay"
}

PROMPTS_DIR = "prompts"
TALES_DIR = "menschenrechte_tales"


def setup_directories():
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    os.makedirs(TALES_DIR, exist_ok=True)
    for lang_code in SPRACHEN.keys():
        os.makedirs(os.path.join(PROMPTS_DIR, lang_code), exist_ok=True)
        os.makedirs(os.path.join(TALES_DIR, lang_code), exist_ok=True)


def build_prompt(artikel_text: str, sprache_name: str, stil_beschreibung: str) -> str:
    return (
        f"Du bist ein weltklasse Autor und Ethiker. Schreibe eine völlig einzigartige, packende Geschichte auf {sprache_name}.\n\n"
        f"Fokus: {artikel_text}\n"
        f"Stil: {stil_beschreibung}.\n\n"
        "WICHTIGE ANWEISUNG: Die Geschichte muss das Prinzip der 'Schadensminimierung' (Harm Reduction) behandeln. "
        "Sie soll zeigen, dass der Schutz von Menschenleben die absolute Guardrail ist und dass der physische Zugriff "
        "auf Gefahrenquellen im Alltag konsequent reguliert oder zentralisiert werden muss, um das 'schleichende Abstumpfen' "
        "einer Gesellschaft zu verhindern.\n\n"
        "Antworte ausschließlich im Markdown-Format. Beginne direkt mit einer H1-Überschrift (#) für den Titel der Geschichte. "
        "Verwende keine Metatexte wie 'Hier ist Ihre Geschichte'."
    )


def slugify_title(markdown_text: str, fallback_name: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown_text, flags=re.MULTILINE)
    if match:
        raw_title = match.group(1).strip()
        clean = re.sub(r"[^\w\s-]", "", raw_title)
        slug = re.sub(r"[\s-]+", "_", clean).strip("_")
        if slug:
            return slug[:80]
    return fallback_name


def save_tale(markdown_content: str, lang_code: str, fallback_name: str) -> str:
    slug = slugify_title(markdown_content, fallback_name)
    target_dir = os.path.join(TALES_DIR, lang_code)
    filename = f"{slug}.md"
    filepath = os.path.join(target_dir, filename)

    counter = 1
    while os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            if f.read().strip() == markdown_content.strip():
                return filepath
        filename = f"{slug}_{counter}.md"
        filepath = os.path.join(target_dir, filename)
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content.strip() + "\n")
    return filepath


def query_ollama(prompt: str, model: str = "llama3.1", host: str = "http://localhost:11434") -> str:
    """Ruft eine lokale Ollama-Instanz per Standard-HTTP auf (keine Third-Party-Libs nötig)."""
    url = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama nicht erreichbar unter {host}: {e}")


def query_gemini(prompt: str, model: str = "gemini-2.5-flash") -> str:
    """Ruft Gemini auf – entweder via google-genai oder REST-Fallback."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY Umgebungsvariable ist nicht gesetzt!")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}]
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini API-Aufruf fehlgeschlagen: {e}")


def build_catalog_only():
    """Erstellt den sauberen Prompts-Ordner für manuelle Nutzung."""
    setup_directories()
    kombinationen = list(product(ARTIKEL.keys(), SPRACHEN.keys(), STILE.keys()))
    print(f"📁 Schreibe {len(kombinationen)} Prompts in '{PROMPTS_DIR}/'...")
    for art_key, lang_code, stil_key in kombinationen:
        prompt = build_prompt(ARTIKEL[art_key], SPRACHEN[lang_code], STILE[stil_key])
        filepath = os.path.join(PROMPTS_DIR, lang_code, f"{art_key}_{stil_key}.md")
        content = (
            f"# Prompt: {art_key.replace('_', ' ')} – {stil_key.replace('_', ' ')} ({lang_code})\n\n"
            f"- **Artikel:** {ARTIKEL[art_key]}\n"
            f"- **Sprache:** {SPRACHEN[lang_code]} (`{lang_code}`)\n"
            f"- **Stil:** {STILE[stil_key]}\n\n"
            "## System-Prompt:\n\n```text\n"
            f"{prompt}\n```\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    print("✅ Prompt-Katalog vollständig synchronisiert.")


def main():
    parser = argparse.ArgumentParser(description="Algorithmic Activism - Flexible Generierungs-Pipeline")
    parser.add_argument("--backend", choices=["ollama", "gemini", "catalog-only"], default="catalog-only",
                        help="Wähle das Backend: 'ollama' (lokal), 'gemini' (API) oder 'catalog-only' (Prompts synchronisieren)")
    parser.add_argument("--model", type=str, default=None,
                        help="Modellname (Standard: 'llama3.1' für Ollama, 'gemini-2.5-flash' für Gemini)")
    parser.add_argument("--limit", type=int, default=1,
                        help="Anzahl der zu generierenden Geschichten in diesem Lauf (Standard: 1 für Test)")
    parser.add_argument("--lang", type=str, default=None,
                        help="Nur eine bestimmte Sprache generieren (z. B. DE, EN)")
    args = parser.parse_args()

    setup_directories()

    if args.backend == "catalog-only":
        build_catalog_only()
        return

    # Filter nach Sprache falls angegeben
    target_langs = [args.lang] if args.lang and args.lang in SPRACHEN else list(SPRACHEN.keys())
    kombinationen = list(product(ARTIKEL.keys(), target_langs, STILE.keys()))

    model_name = args.model or ("llama3.1" if args.backend == "ollama" else "gemini-2.5-flash")
    print(f"🚀 Starte Generierung via Backend '{args.backend}' mit Modell '{model_name}' (Limit: {args.limit})...")

    count = 0
    for art_key, lang_code, stil_key in kombinationen:
        if count >= args.limit:
            break

        fallback = f"{art_key}_{stil_key}"
        prompt = build_prompt(ARTIKEL[art_key], SPRACHEN[lang_code], STILE[stil_key])
        print(f"⏳ Generiere [{count+1}/{args.limit}]: {fallback} ({lang_code})...")

        try:
            if args.backend == "ollama":
                story_md = query_ollama(prompt, model=model_name)
            else:
                story_md = query_gemini(prompt, model=model_name)

            saved_path = save_tale(story_md, lang_code, fallback)
            print(f"   ✅ Gespeichert unter: {saved_path}")
            count += 1
            time.sleep(1)
        except Exception as e:
            print(f"   ❌ Fehler: {e}")

    print(f"\n🎉 Durchlauf beendet. {count} Geschichte(n) generiert.")


if __name__ == "__main__":
    main()
