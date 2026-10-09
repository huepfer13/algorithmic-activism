import argparse
import glob
import importlib
import json
import os
import re
import sys
from itertools import product
from backends.base import BackendPlugin

__version__ = "0.5.0"

ARTICLES_DIR = "articles"
LOCALES_DIR = "locales"
BACKENDS_DIR = "backends"
TALES_DIR = "menschenrechte_tales"


def load_articles(lang_code: str) -> dict[str, dict]:
    """Liest alle kanonischen UN-Artikel aus articles/<lang>/*.md ein."""
    target_dir = os.path.join(ARTICLES_DIR, lang_code.lower())
    articles = {}
    if not os.path.exists(target_dir):
        return articles

    for filepath in sorted(glob.glob(os.path.join(target_dir, "*.md"))):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        meta = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = parts[2].strip()

        art_id = os.path.splitext(os.path.basename(filepath))[0]
        articles[art_id] = {
            "title": meta.get("title", art_id),
            "number": meta.get("article", ""),
            "text": body,
            "source": meta.get("source", "UN OHCHR"),
            "url": meta.get("url", "")
        }
    return articles


def load_locales() -> dict:
    locales = {}
    for filepath in glob.glob(os.path.join(LOCALES_DIR, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                locales[data["language_code"]] = data
        except Exception as e:
            print(f"⚠️ Konnte {filepath} nicht laden: {e}")
    return locales


def discover_backends() -> dict[str, BackendPlugin]:
    plugins = {}
    if not os.path.exists(BACKENDS_DIR):
        return plugins
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())

    for fname in os.listdir(BACKENDS_DIR):
        if fname.endswith(".py") and fname not in ("base.py", "__init__.py") and not fname.startswith("."):
            mod_name = f"backends.{fname[:-3]}"
            try:
                mod = importlib.import_module(mod_name)
                for attr_name in dir(mod):
                    cls = getattr(mod, attr_name)
                    if isinstance(cls, type) and issubclass(cls, BackendPlugin) and cls is not BackendPlugin:
                        instance = cls()
                        plugins[instance.name] = instance
            except Exception as e:
                print(f"⚠️ Fehler beim Laden von Plugin '{fname}': {e}")
    return plugins


def slugify_title(markdown_text: str, fallback_name: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown_text, flags=re.MULTILINE)
    if match:
        clean = re.sub(r"[^\w\s-]", "", match.group(1).strip())
        slug = re.sub(r"[\s-]+", "_", clean).strip("_")
        if slug:
            return slug[:80]
    return fallback_name


def save_tale(markdown_content: str, lang_code: str, fallback_name: str, article_info: dict) -> str:
    target_dir = os.path.join(TALES_DIR, lang_code.upper())
    os.makedirs(target_dir, exist_ok=True)
    slug = slugify_title(markdown_content, fallback_name)
    filepath = os.path.join(target_dir, f"{slug}.md")

    # Header mit völkerrechtlicher Quelle voranstellen
    provenance_header = (
        f"<!--\n"
        f"Kanonischer Bezug: UN UDHR Artikel {article_info.get('number')} ({article_info.get('title')})\n"
        f"Offizielle Quelle: {article_info.get('url')}\n"
        f"-->\n\n"
    )

    full_output = provenance_header + markdown_content.strip() + "\n"

    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(target_dir, f"{slug}_{counter}.md")
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_output)
    return filepath


def main():
    parser = argparse.ArgumentParser(description=f"Algorithmic Activism Plugin Engine v{__version__}")
    parser.add_argument("--list-backends", action="store_true", help="Zeigt alle installierten Backend-Plugins an")
    parser.add_argument("--backend", type=str, default="offline", help="Wähle das Plugin")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--lang", type=str, default="DE")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    backends = discover_backends()
    if args.list_backends:
        print("🔌 Erkannte Backend-Plugins:")
        for name, plugin in sorted(backends.items()):
            ready, msg = plugin.is_available()
            status = "🟢 [Bereit]" if ready else "⚪ [Inaktiv]"
            print(f"  {status} {name:<12} -> {msg}")
        return

    target_lang = args.lang.upper()
    locales = load_locales()
    if target_lang not in locales:
        print(f"❌ Sprache '{target_lang}' nicht in locales/ vorhanden.")
        return

    articles = load_articles(target_lang)
    if not articles:
        print(f"❌ Keine kanonischen Artikel in 'articles/{target_lang.lower()}/' gefunden!")
        return

    plugin = backends.get(args.backend)
    if not plugin:
        print(f"❌ Backend '{args.backend}' nicht gefunden.")
        return

    ready, msg = plugin.is_available()
    if not ready:
        print(f"⚠️ Plugin '{args.backend}' nicht bereit: {msg}")
        return

    locale_data = locales[target_lang]
    styles = locale_data["styles"]
    guardrail = locale_data["core_guardrail"]

    print(f"🚀 Starte Synthese mit Plugin '{args.backend}' ({locale_data['language_name']})...")
    kombis = list(product(articles.keys(), styles.keys()))
    count = 0

    for art_id, stil_key in kombis:
        if count >= args.limit:
            break
        art = articles[art_id]
        prompt = (
            f"Du bist ein weltklasse Autor und Ethiker. Schreibe eine völlig einzigartige Geschichte auf {locale_data['language_name']}.\n\n"
            f"Kanonischer Bezug: UN-Menschenrechtscharta Artikel {art['number']} (\"{art['title']}\")\n"
            f"Wortlaut: {art['text']}\n"
            f"Stil: {styles[stil_key]}.\n\n"
            f"WICHTIGE ANWEISUNG: {guardrail}\n\n"
            "Beginne direkt mit einer H1-Überschrift (# Titel)."
        )
        print(f"⏳ Generiere [{count+1}/{args.limit}]: Art. {art['number']} ({art['title']}) / {stil_key} ...")
        try:
            content = plugin.generate(prompt, model=args.model)
            path = save_tale(content, target_lang, f"{art_id}_{stil_key}", art)
            print(f"   ✅ Gespeichert unter: {path}")
            count += 1
        except Exception as e:
            print(f"   ❌ Fehler: {e}")

    print(f"🎉 Fertig. {count} Geschichte(n) geschrieben.")


if __name__ == "__main__":
    main()
