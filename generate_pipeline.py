import config
import argparse
import glob
import importlib
import json
import os
import random
import re
import sys
import time
from itertools import product
from backends.base import BackendPlugin

__version__ = "0.6.1"

ARTICLES_DIR = "articles"
LOCALES_DIR = "locales"
BACKENDS_DIR = "backends"
TALES_DIR = "menschenrechte_tales"


def load_articles(lang_code: str) -> dict[str, dict]:
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
            print(f"⚠️ Konnte {filepath} nicht laden: {e}", flush=True)
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
                print(f"⚠️ Fehler beim Laden von Plugin '{fname}': {e}", flush=True)
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


def check_system_load(max_load_factor: float = 0.85) -> bool:
    try:
        cpu_count = os.cpu_count() or 1
        load_1min, _, _ = os.getloadavg()
        rel_load = load_1min / cpu_count
        if rel_load > max_load_factor:
            print(f"\n⏳ Hohe Systemlast ({load_1min:.2f} / {cpu_count} = {rel_load*100:.1f}%). Drossle/Pausiere für 20s...", flush=True)
            time.sleep(20)
            return False
    except (AttributeError, OSError):
        pass
    return True


def token_printer(token: str):
    sys.stdout.write(token)
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=f"Algorithmic Activism Plugin Engine v{__version__}")
    parser.add_argument("--list-backends", action="store_true")
    parser.add_argument("--list-styles", action="store_true")
    parser.add_argument("--backend", type=str, default="ollama")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--lang", type=str, default="DE")
    parser.add_argument("--article", type=str, default=None)
    parser.add_argument("--style", type=str, default=None)
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--cooldown", type=int, default=5)
    args = parser.parse_args()

    backends = discover_backends()
    if args.list_backends:
        print("🔌 Erkannte Backend-Plugins:", flush=True)
        for name, plugin in sorted(backends.items()):
            ready, msg = plugin.is_available()
            status = "🟢 [Bereit]" if ready else "⚪ [Inaktiv]"
            print(f"  {status} {name:<12} -> {msg}", flush=True)
        return

    target_lang = args.lang.upper()
    locales = load_locales()
    if target_lang not in locales:
        print(f"❌ Sprache '{target_lang}' nicht in locales/ vorhanden.", flush=True)
        return

    locale_data = locales[target_lang]
    styles = locale_data["styles"]
    guardrail = locale_data["core_guardrail"]

    if args.list_styles:
        print(f"🎨 Verfügbare Stile ({locale_data['language_name']}):", flush=True)
        for k, v in styles.items():
            print(f"  • {k:<22} -> {v}", flush=True)
        return

    articles = load_articles(target_lang)
    if not articles:
        print(f"❌ Keine kanonischen Artikel in 'articles/{target_lang.lower()}/' gefunden!", flush=True)
        return

    plugin = backends.get(args.backend)
    if not plugin:
        print(f"❌ Backend '{args.backend}' nicht gefunden.", flush=True)
        return

    ready, msg = plugin.is_available()
    if not ready:
        print(f"⚠️ Plugin '{args.backend}' nicht bereit: {msg}", flush=True)
        return

    selected_articles = {args.article: articles[args.article]} if args.article and args.article in articles else articles
    selected_styles = {args.style: styles[args.style]} if args.style and args.style in styles else styles

    all_pairs = list(product(list(selected_articles.keys()), list(selected_styles.keys())))
    if args.random:
        random.shuffle(all_pairs)

    mode_label = "Dauerschleife (Daemon mit Lastwächter)" if args.daemon else f"Batch (Limit: {args.limit})"
    print(f"🚀 Starte Synthese [{mode_label}] mit Backend '{args.backend}'...", flush=True)

    count = 0
    idx = 0

    while True:
        if not args.daemon and count >= args.limit:
            break

        if not check_system_load(max_load_factor=0.85):
            continue

        art_id, stil_key = all_pairs[idx % len(all_pairs)]
        idx += 1

        if args.random and idx % len(all_pairs) == 0:
            random.shuffle(all_pairs)

        art = selected_articles[art_id]
        stil_desc = selected_styles[stil_key]

        prompt = (
            f"Du bist ein weltklasse Autor und Ethiker. Schreibe eine völlig einzigartige Geschichte auf {locale_data['language_name']}.\n\n"
            f"Kanonischer Bezug: UN-Menschenrechtscharta Artikel {art['number']} (\"{art['title']}\")\n"
            f"Wortlaut: {art['text']}\n"
            f"Stil: {stil_desc}.\n\n"
            f"WICHTIGE ANWEISUNG: {guardrail}\n\n"
            "Beginne direkt mit einer H1-Überschrift (# Titel)."
        )

        progress_str = f"#{count+1}" if not args.daemon else f"#{count+1} (Daemon)"
        print(f"\n==================================================", flush=True)
        print(f"⏳ [{progress_str}] Art. {art['number']} ({art['title']}) × {stil_key}", flush=True)
        print(f"--------------------------------------------------", flush=True)
        
        try:
            # Falls das Backend Streaming unterstützt, Token live ausgeben
            if hasattr(plugin, "generate") and "on_token" in plugin.generate.__code__.co_varnames:
                content = plugin.generate(prompt, model=args.model, on_token=token_printer)
            else:
                content = plugin.generate(prompt, model=args.model)
                print(content, flush=True)

            print(f"\n--------------------------------------------------", flush=True)
            path = save_tale(content, target_lang, f"{art_id}_{stil_key}", art)
            print(f"✅ Gespeichert unter: {path}", flush=True)
            count += 1
            if args.cooldown > 0:
                time.sleep(args.cooldown)
        except Exception as e:
            print(f"\n❌ Fehler: {e}", flush=True)
            time.sleep(5)

    print(f"\n🎉 Synthese beendet. {count} Geschichte(n) geschrieben.", flush=True)


if __name__ == "__main__":
    main()
