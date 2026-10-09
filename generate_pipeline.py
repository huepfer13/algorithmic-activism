import argparse
import json
import os
import re
import subprocess
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
    setup_directories()
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


# ==================== BACKENDS ====================

def query_ollama(prompt: str, model: str = "llama3.1", host: str = "http://localhost:11434") -> str:
    url = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8")).get("response", "")


def query_gemini(prompt: str, model: str = "gemini-2.5-flash") -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY Umgebungsvariable ist nicht gesetzt!")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]


def query_openai_compat(prompt: str, model: str = "gpt-4o-mini", base_url: str = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "dummy-local-key")
    url = f"{base_url.rstrip('/') if base_url else 'https://api.openai.com/v1'}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def query_backend(backend: str, prompt: str, model: str = None) -> str:
    b = backend.lower()
    if b == "ollama":
        return query_ollama(prompt, model=model or "llama3.1")
    elif b == "gemini":
        return query_gemini(prompt, model=model or "gemini-2.5-flash")
    elif b in ["openai", "vllm", "localai"]:
        base_url = os.environ.get("OPENAI_BASE_URL")
        return query_openai_compat(prompt, model=model or "gpt-4o-mini", base_url=base_url)
    else:
        raise ValueError(f"Unbekanntes Backend: {backend}. Wähle 'ollama', 'gemini' oder 'openai'.")


# ==================== GIT AUTOMATION ====================

def run_cmd(cmd: list) -> str:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Befehl {' '.join(cmd)} fehlgeschlagen: {res.stderr.strip()}")
    return res.stdout.strip()


def sync_git(generated_files: list, create_pr: bool = False):
    """Fügt generierte Geschichten zu Git hinzu, committet und pusht sie."""
    if not generated_files:
        print("ℹ️ Keine neuen Dateien zum Pushen vorhanden.")
        return

    print("\n📦 Starte Git-Synchronisation...")
    try:
        # 1. Änderungen stagen
        for f in generated_files:
            run_cmd(["git", "add", f])

        # Status prüfen
        status = run_cmd(["git", "status", "--porcelain"])
        if not status:
            print("ℹ️ Keine Änderungen im Working Tree.")
            return

        # 2. Commit erstellen
        msg = f"feat(tales): auto-generate {len(generated_files)} human rights stories"
        run_cmd(["git", "commit", "-m", msg])
        print(f"✅ Commit erstellt: '{msg}'")

        # 3. Branch und Remote ermitteln
        branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        run_cmd(["git", "push", "origin", branch])
        print(f"🚀 Erfolgreich nach 'origin/{branch}' gepusht!")

        # 4. Optional: Automatischen Pull Request erstellen (für Forks)
        if create_pr:
            print("🔀 Erstelle Pull Request via GitHub CLI...")
            pr_title = f"feat(matrix): add {len(generated_files)} synthesized tales"
            pr_body = (
                "Automatisierter PR der Algorithmic-Activism-Pipeline.\n\n"
                f"Generierte Dateien:\n" + "\n".join([f"- `{f}`" for f in generated_files])
            )
            pr_cmd = ["gh", "pr", "create", "--title", pr_title, "--body", pr_body]
            pr_url = run_cmd(pr_cmd)
            print(f"🎉 Pull Request erfolgreich eröffnet: {pr_url}")

    except Exception as e:
        print(f"⚠️ Git-Push fehlgeschlagen: {e}")


# ==================== MAIN ====================

def build_catalog_only():
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
    parser = argparse.ArgumentParser(description="Algorithmic Activism Engine with Git Automation")
    parser.add_argument("--backend", choices=["ollama", "gemini", "openai", "catalog-only"], default="catalog-only")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--git-push", action="store_true", help="Automatisch committen und zu origin pushen")
    parser.add_argument("--create-pr", action="store_true", help="Erstellt nach dem Push automatisch einen PR via 'gh'")
    args = parser.parse_args()

    if args.backend == "catalog-only":
        build_catalog_only()
        if args.git-push:
            sync_git([PROMPTS_DIR])
        return

    setup_directories()
    target_langs = [args.lang] if args.lang and args.lang in SPRACHEN else list(SPRACHEN.keys())
    kombinationen = list(product(ARTIKEL.keys(), target_langs, STILE.keys()))

    print(f"🚀 Starte Generierung via Backend '{args.backend}' (Limit: {args.limit})...")
    generated_files = []

    for art_key, lang_code, stil_key in kombinationen:
        if len(generated_files) >= args.limit:
            break
        fallback = f"{art_key}_{stil_key}"
        prompt = build_prompt(ARTIKEL[art_key], SPRACHEN[lang_code], STILE[stil_key])
        print(f"⏳ Generiere [{len(generated_files)+1}/{args.limit}]: {fallback} ({lang_code})...")
        try:
            story_md = query_backend(args.backend, prompt, model=args.model)
            saved = save_tale(story_md, lang_code, fallback)
            print(f"   ✅ Gespeichert unter: {saved}")
            generated_files.append(saved)
            time.sleep(1)
        except Exception as e:
            print(f"   ❌ Fehler: {e}")

    print(f"\n🎉 Durchlauf beendet. {len(generated_files)} Geschichte(n) generiert.")

    if args.git_push:
        sync_git(generated_files, create_pr=args.create_pr)


if __name__ == "__main__":
    main()
