#!/usr/bin/env python3
import fcntl
import hashlib
import argparse
import datetime
import glob
import json
import os
import random
import re
import sys
import time
import unicodedata

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


def run_ollama_stream(prompt: str, model: str = "qwen2.5:7b", host: str = "http://localhost:11434",
                      details: dict | None = None) -> str:
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
        if details is not None:
            # Ollama liefert die echten Zahlen mit — keine Wort-Proxies.
            for schluessel, feld in (("eval_count", "tokens_generated"),
                                     ("eval_duration", "generation_ns"),
                                     ("total_duration", "total_ns")):
                if data.get(schluessel) is not None:
                    details[feld] = data[schluessel]
        return data.get("response", "")


def erzeuge_text(prompt: str, model: str, host: str, backend: str = "ollama",
                 details: dict | None = None, json_mode: bool = False) -> str:
    """Generiert ueber das gewaehlte Backend — unbekannte oder nicht einsatzbereite brechen ab.

    Kein stiller Ollama-Fallback: bis hierher war der --backend-Schalter wirkungslos, jede Angabe
    landete in run_ollama_stream (belegt 2026-10-12). Ein Backend, das nicht liefern kann, muss
    sichtbar scheitern statt heimlich etwas anderes zu tun.
    """
    if backend == "ollama":
        if json_mode:
            return run_ollama_json_raw(prompt, model=model, host=host, details=details)
        return run_ollama_stream(prompt, model=model, host=host, details=details)
    if backend == "offline":
        from backends.offline import OfflinePlugin
        plugin = OfflinePlugin()
    elif backend == "gemini":
        from backends.gemini import GeminiPlugin
        plugin = GeminiPlugin()
    elif backend == "deepseek":
        from backends.deepseek import DeepSeekPlugin
        plugin = DeepSeekPlugin()
    elif backend == "openrouter":
        # Free-Tier-Verbund: nur Anbieter mit gemessenem Endpunkt (siehe backends/openai_compat.py).
        from backends.openai_compat import OpenAICompatPlugin
        plugin = OpenAICompatPlugin("openrouter")
    else:
        raise RuntimeError(f"unbekanntes Backend '{backend}' — erlaubt sind: "
                           "ollama, offline, gemini, deepseek, openrouter")
    if json_mode and not getattr(plugin, "supports_json", False):
        raise RuntimeError(f"Backend '{backend}' unterstuetzt keinen JSON-Modus "
                           "(erzwungenes Format gibt es bei ollama, deepseek und openrouter)")
    bereit, meldung = plugin.is_available()
    if not bereit:
        raise RuntimeError(f"Backend '{backend}' nicht einsatzbereit: {meldung}")
    return plugin.generate(prompt, model=model, details=details, json_mode=json_mode)


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


# --- Buecher ("Unendliche Geschichte") ----------------------------------------------------------
# Ein Buch ist ein Verzeichnis mit EINMAL eingefrorenem Rahmen (book.json) und fortlaufenden
# Kapiteln: 00_prolog.md, 01_art_XX_kapitel_1.md, 02_art_XX_kapitel_2.md ...
# Drift-Schutz (gemessen 2026-10-12): Titel und Erzaehlperspektive werden im Prolog festgelegt und
# danach in jedem Kapitelprompt ZITIERT — ohne das erfindet das Modell einen neuen Titel.
BOOKS_DIR = os.path.join(BASE_DIR, "menschenrechte_books")
POVS = ("first_person", "third_person", "third_person_manual")


def run_ollama_json_raw(prompt: str, model: str = "qwen2.5:7b",
                        host: str = "http://localhost:11434",
                        details: dict | None = None) -> str:
    """Wie run_ollama_stream, aber mit erzwungenem JSON-Format — liefert den ROHEN JSON-Text.

    Fuellt details mit denselben echten Ollama-Zahlen wie run_ollama_stream (kein Wort-Proxy).
    """
    import urllib.request
    req_data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                           "format": "json", "options": {"temperature": 0.7}}).encode("utf-8")
    req = urllib.request.Request(f"{host}/api/generate", data=req_data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        daten = json.loads(resp.read().decode())
    if details is not None:
        if daten.get("eval_count") is not None:
            details["tokens_generated"] = int(daten["eval_count"])
        if daten.get("eval_duration"):
            details["generation_ns"] = int(daten["eval_duration"])
        if daten.get("total_duration"):
            details["total_ns"] = int(daten["total_duration"])
    return daten.get("response", "")


def run_ollama_json(prompt: str, model: str = "qwen2.5:7b",
                    host: str = "http://localhost:11434") -> dict:
    """Erzwungenes JSON-Format, geparst (fuer Buch-Metadaten)."""
    return json.loads(run_ollama_json_raw(prompt, model=model, host=host))


def book_language_directive(lang: str, locale: dict) -> str:
    """Sprachdirektive fuer Buch-Prompts — dieselbe Regel wie in build_prompt():
    kuratierte Angabe aus der Locale, oder DE als Muttersprache der Pipeline. Sonst Abbruch.
    (Eine deutsche Anweisung mit blossem Sprachwunsch lieferte fuer AR gemischte Schrift.)"""
    name = locale.get("instruction_language") or ("Deutsch" if lang.upper() == "DE" else None)
    if not name:
        raise ValueError(
            f"Keine Anweisungssprache fuer den Buchmodus in '{lang}': kein 'instruction_language' "
            f"in locales/{lang.lower()}.json. Der Buchmodus laeuft vorerst nur auf DE."
        )
    return name


def next_book_index() -> int:
    """Naechster freier Buchindex aus dem DATEISYSTEM — kein Zaehler, der driften kann."""
    if not os.path.isdir(BOOKS_DIR):
        return 1
    idx = [int(m.group(1)) for d in os.listdir(BOOKS_DIR)
           if (m := re.match(r"buch_(\d{3})_", d)) and os.path.isdir(os.path.join(BOOKS_DIR, d))]
    return max(idx) + 1 if idx else 1


def build_book_meta_prompt(lang_name: str, style_name: str, style_desc: str) -> str:
    return f"""Du konzipierst einen fortlaufenden Roman im Stil {style_name}, geschrieben auf {lang_name}.

STILVORGABE {style_name}: {style_desc}

Erfinde Setting, Besatzung und eine Konflikt-Praemisse, die sich ueber viele Kapitel tragen kann.

Anforderungen:
- 3 bis 5 Hauptfiguren mit Namen (Eigennamen oder kurze Bezeichner).
- Ein Schauplatz mit eigenem Druckmittel (Zeit, Enge, Ueberwachung, Ressourcen, Hierarchie).
- Die Praemisse muss es erlauben, spaeter einzelne Artikel der Allgemeinen Erklaerung der
  Menschenrechte zu verhandeln (Wuerde, Meinungsfreiheit, Leben, Gleichheit).
- Erzaehlperspektive festlegen: 'first_person', 'third_person' oder — bei Sach-, Handbuch- und
  Dokumentationsgenres — 'third_person_manual'.

Fuer 'characters' gilt STRIKT: ausschliesslich Namen bzw. kurze Bezeichner. KEINE Rollenbezeichnung,
KEIN Doppelpunkt, KEINE Beschreibung, KEINE Nummern-Codes, keine Strings wie "Rolle: Beschreibung".

Antworte AUSSCHLIESSLICH mit JSON in genau dieser Form:
{{"title": "...", "pov": "first_person", "characters": ["Name1", "Name2", "Name3"], "setting_summary": "zwei bis drei Saetze"}}"""


def regelblock(style_name: str, style_rules: list) -> str:
    """Gemeinsamer Regel-Teil fuer Prolog und Kapitel.

    Die stilspezifischen Regeln kommen aus der Locale (Daten, kein Genre-Sonderfall im Code).
    Der Phrasen-Bann ist generisch: er konkretisiert nur den Kern-Guardrail, denn am 2026-10-12
    endete ein Handbuch-Kapitel mit 'Es ist wichtig zu betonen, dass die Wuerde aller Menschen
    unantastbar ist' — ein Bekenntnissatz, der die Satire zerstoert.
    """
    zeilen = []
    if style_rules:
        zeilen.append(f"STILREGELN {style_name} (verbindlich, woertlich umsetzen):")
        zeilen += [f"- {r}" for r in style_rules]
        zeilen.append("")
    zeilen += [
        "VERBOTEN (ein Verstoss macht den Text unbrauchbar):",
        "- Moral- und Bekenntnissaetze, z. B. 'Es ist wichtig zu betonen', 'Zusammenfassend laesst",
        "  sich sagen', 'Die Wuerde des Menschen ist unantastbar', 'Wir muessen bedenken'.",
        "- Ein Schlusssatz, der das Geschriebene moralisch einordnet ('Moral von der Geschicht').",
        "- Der Artikel wird NICHT zitiert und NICHT als Appell erwaehnt.",
    ]
    return "\n".join(zeilen)


def rahmenblock(meta: dict, lang_name: str, style_name: str, style_desc: str, rolle: str) -> str:
    """Kopf jedes Buch-Textes: fester Titel, Stil, Sprache, POV, Setting, Besatzung (DRY)."""
    return (f"{rolle}\n"
            f'"{meta["title"]}" im Stil {style_name} auf {lang_name}. Erzaehlperspektive: {meta["pov"]}.\n\n'
            f"STILVORGABE {style_name}: {style_desc}\n\n"
            f"SETTING (verbindlich): {meta['setting_summary']}\n"
            f"BESATZUNG (verbindlich): {', '.join(meta['characters'])}")


def build_prologue_prompt(meta: dict, lang_name: str, style_name: str, style_desc: str,
                          style_rules: list, core_rule: str) -> str:
    return f"""{rahmenblock(meta, lang_name, style_name, style_desc,
                'Du bist ein weltklasse Autor und Ethiker. Schreibe den Prolog des fortlaufenden Romans')}

{regelblock(style_name, style_rules)}

AUFGABE:
- Etabliere Setting und Besatzung; jede Figur bekommt eine Eigenheit und einen eigenen Konflikt.
- Baue eine konkrete Bedrohung auf, die die folgenden Kapitel tragen kann.
- {core_rule}

FORMAT:
- Erste Zeile: # {meta['title']}
- 300-500 Woerter, reine Erzaehlung, kein Meta-Text."""


def build_chapter_prompt(meta: dict, lang_name: str, style_name: str, style_desc: str, style_rules: list,
                         core_rule: str, chapter_index: int, article_id: str, article_text: str,
                         previous_text: str, previous_label: str) -> str:
    """Markov-Schritt: festes Setting + Volltext des Vorkapitels + naechster UN-Artikel."""
    return f"""{rahmenblock(meta, lang_name, style_name, style_desc,
                f'Du bist ein weltklasse Autor und Ethiker. Du schreibst Kapitel {chapter_index} des fortlaufenden Romans')}

{regelblock(style_name, style_rules)}

VORHERIGES ({previous_label}, Volltext):
{previous_text}

NEUE AUFGABE:
- Fuehre das Dokument nahtlos fort: greife mindestens EINE Figur und EIN konkretes Detail aus dem
  vorherigen Teil auf. Keine Wiederholung der Exposition.
- Verhandle UN-Artikel {article_id} als technischen Parameter, Kalibrierungsvorgabe oder Stoerfall
  ({article_text}) — nicht als Zitat, nicht als Appell.
- {core_rule}
- Ende mit einem Cliffhanger ODER einer technischen Folgeanweisung.

FORMAT:
- Erste Zeile: # Abschnitt {chapter_index}: [Titel des Abschnitts]
- 300-500 Woerter, reine Erzaehlung, kein Meta-Text."""


def pruefe_figuren(figuren) -> None:
    """Figuren muessen Namen bzw. kurze Bezeichner sein — keine Rollen-/Beschreibungsstrings.

    Ursache (gemessen 2026-10-12): das Modell lieferte 'Einzelne2: Biologischer Subsystem-... B-001';
    solche Rollenangaben wandern sonst in jedes Kapitel und in die Figuren-Treue-Pruefung.
    """
    if not isinstance(figuren, list) or not (3 <= len(figuren) <= 5):
        raise ValueError(f"Erwartet 3-5 Figuren als Liste, erhalten {figuren!r}")
    for f in figuren:
        if not isinstance(f, str) or not f.strip():
            raise ValueError(f"Figur ist kein nichtleerer String: {f!r}")
        if ":" in f or "\n" in f:
            raise ValueError(f"Figur enthaelt eine Rollen-/Beschreibungsangabe (Doppelpunkt): {f!r}")
        if len(f.strip()) > 40:
            raise ValueError(f"Figur ist zu lang (>40 Zeichen) — wohl eine Beschreibung: {f[:50]!r}")


def prolog_erzeugen(buch_dir: str, book_id: str, meta: dict, lang: str, lang_name: str,
                    style_name: str, style_desc: str, style_rules: list, core_rule: str,
                    model: str, host: str, backend: str) -> str:
    """Schreibt 00_prolog.md aus einem BESTEHENDEN Rahmen — eine Quelle fuer new-book und --mode prolog.

    Ueberschreibt nie: existiert der Prolog schon, bricht der Aufruf ab (kein stiller Datenverlust).
    Das Buchverzeichnis entsteht erst nach erfolgreicher Generierung, damit ein Backend-Abbruch kein
    leeres Verzeichnis hinterlaesst, das naechstes_buch() als "neuestes Buch" waehlen wuerde.
    """
    pfad = os.path.join(buch_dir, "00_prolog.md")
    if os.path.exists(pfad):
        raise FileExistsError(f"Prolog existiert bereits: {pfad}")
    details: dict = {}
    start = time.monotonic()
    prolog = erzeuge_text(build_prologue_prompt(meta, lang_name, style_name, style_desc,
                                                style_rules, core_rule),
                          model, host, backend=backend, details=details)
    dauer = round(time.monotonic() - start, 1)
    if not prolog.strip():
        raise RuntimeError("Leerer Prolog vom Modell — es wird nichts geschrieben.")
    if not os.path.isdir(buch_dir):
        os.makedirs(buch_dir)
    write_new_file(pfad,
                   f'---\nbook_id: "{book_id}"\nchapter_index: 0\nchapter_title: "Prolog"\n'
                   f'article: ""\nlanguage: "{lang.upper()}"\nstyle: "{style_name}"\n'
                   f'pov: "{meta["pov"]}"\n'
                   + (f'model: "{model}"\ngenre: "{style_name}"\nbackend: "{backend}"\n'
                      f'duration_seconds: {dauer}\n'
                      + (f'tokens_generated: {details["tokens_generated"]}\n'
                         if details.get("tokens_generated") else ""))
                   + '---\n\n' + prolog.strip() + "\n")
    return pfad


def prolog_schreiben(book_id: str, lang: str = "DE", model: str = "deepseek-chat",
                     host: str = "http://localhost:11434", backend: str = "deepseek") -> str:
    """Ergaenzt einen fehlenden Prolog zu einem BESTEHENDEN Buch (book.json bleibt kanonisch)."""
    buch_dir = os.path.join(BOOKS_DIR, book_id)
    meta_pfad = os.path.join(buch_dir, "book.json")
    if not os.path.isfile(meta_pfad):
        raise FileNotFoundError(f"Kein book.json in {buch_dir} — --mode prolog ergaenzt nur Bestand")
    meta = json.load(open(meta_pfad, encoding="utf-8"))
    locale = load_locale(lang)
    style_name = meta.get("style") or ""
    styles = locale.get("styles", {})
    if style_name not in styles:
        raise ValueError(f"Stil '{style_name}' aus {book_id}/book.json fehlt in locales/{lang.lower()}.json")
    core_rule = (locale.get("guardrail_prompt") or locale.get("core_guardrail")
                 or "Schutz von Leben und koerperlicher Unversehrtheit hat Vorrang.")
    lang_name = book_language_directive(lang, locale)
    return prolog_erzeugen(buch_dir, book_id, meta, lang, lang_name, style_name, styles[style_name],
                           locale.get("style_rules", {}).get(style_name, []), core_rule,
                           model, host, backend)


def new_book(lang: str = "DE", style: str | None = None, model: str = "qwen2.5:7b",
             host: str = "http://localhost:11434", backend: str = "ollama",
             book_id: str | None = None, titel: str | None = None) -> str:
    """Stufe 1: neues Buch anlegen. Der Rahmen wird EINMAL eingefroren, danach nur angehaengt."""
    locale = load_locale(lang)
    styles = locale.get("styles", {})
    if not styles:
        raise ValueError(f"locales/{lang.lower()}.json enthaelt keine Stile.")
    style_name = style or random.choice(list(styles.keys()))
    if style_name not in styles:
        raise ValueError(f"Unbekannter Stil '{style_name}'. Verfuegbar: {sorted(styles)}")
    style_desc = styles[style_name]
    style_rules = locale.get("style_rules", {}).get(style_name, [])
    lang_name = book_language_directive(lang, locale)
    # 'guardrail_prompt' ist der Code-Name, 'core_guardrail' der historische Locale-Name:
    # beide lesen, sonst greift der deutsche Fallback.
    core_rule = (locale.get("guardrail_prompt") or locale.get("core_guardrail")
                 or "Schutz von Leben und koerperlicher Unversehrtheit hat Vorrang.")

    # Schritt 1: Metadaten (JSON, deterministisch parsebar)
    meta_details: dict = {}
    t_meta = time.monotonic()
    meta = json.loads(erzeuge_text(build_book_meta_prompt(lang_name, style_name, style_desc),
                                   model, host, backend=backend, details=meta_details,
                                   json_mode=True))
    dauer_meta = round(time.monotonic() - t_meta, 1)
    fehlend = [k for k in ("title", "pov", "characters", "setting_summary") if not meta.get(k)]
    if fehlend:
        raise ValueError(f"Buch-Metadaten unvollstaendig ({fehlend}) in {meta!r}")
    if meta["pov"] not in POVS:
        raise ValueError(f"Unbekannte Perspektive '{meta['pov']}' (erlaubt: {POVS})")
    pruefe_figuren(meta["characters"])

    # Schritt 2: Verzeichnis + Rahmen einfrieren
    if titel:
        meta["title"] = titel
    index = next_book_index()
    if book_id is not None:
        # Explizite ID aus der CLI: Pfadanteile sind tabu, sonst schreibt der Aufruf ausserhalb des Buchordners.
        # Leerstring ist ein FEHLER, kein "nicht angegeben" — stiller Fallback waere hier die falsche Freundlichkeit.
        if not book_id.strip() or ".." in book_id or "/" in book_id:
            raise RuntimeError(f"ungueltige book_id '{book_id}' — kein Pfadanteil, kein Leerstring")
        book_id = book_id.strip()
    else:
        book_id = f"buch_{index:03d}_{sanitize_filename(meta['title']).lower()[:40]}"
    buch_dir = os.path.join(BOOKS_DIR, book_id)
    if os.path.isdir(buch_dir):
        raise FileExistsError(f"Buch existiert bereits: {buch_dir}")

    prolog_erzeugen(buch_dir, book_id, meta, lang, lang_name, style_name, style_desc,
                    style_rules, core_rule, model, host, backend)

    buch_meta = {
        "book_id": book_id, "title": meta["title"], "pov": meta["pov"],
        "language": lang.upper(), "style": style_name,
        "setting_summary": meta["setting_summary"], "characters": meta["characters"],
        "covered_articles": [], "current_chapter": 0,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "_hinweis": "current_chapter ist nur ein Cache — massgeblich ist der Dateibestand im Ordner.",
    }
    write_new_file(os.path.join(buch_dir, "book.json"),
                   json.dumps(buch_meta, ensure_ascii=False, indent=2) + "\n")
    return book_id


# --- Stufe 2: Kapitel anhaengen ("Unendliche Geschichte") ----------------------------------------
DIALOG_ZEICHEN = ('"', '„', '“', '»', '«')
EMOTIONS_VERBEN = ("flüsterte", "lächelte", "sagte", "nickte", "seufzte", "blickte", "lächeln", "flüstern")
# Strukturelle Marker: gelten NUR am Zeilenanfang (nach Aufzaehlung/Fettung). Substring-Treffer
# im Fliesstext zaehlen nicht mehr — "Diagnosetabelle" hat die Schranke sonst passiert (belegt
# 2026-10-12: Kapitel 3 und 4 endeten wortgleich, sha256[:8]=49259407).
# Marker MUESSEN formal sein: Doppelpunkt (bzw. Ziffer bei Abschnitt/Fehlercode). Ohne diese Schaerfe
# rutschte Prosa durch ("Wartung war heute nicht noetig" galt als Abschluss — belegt 2026-10-12).
# Muster in normalisierter Schreibweise (Umlaut-Mapping aus _normalisiere), Treffer auf Kleinschrift.
ABSCHLUSS_MARKER = (
    ("diagnose", r"^diagnose\s*:"),
    ("wartung", r"^wartung\s*:"),
    ("intervall", r"^intervall\s*:"),
    ("pruefung", r"^pruefung\s*:"),
    ("pruefprotokoll", r"^pruefprotokoll\s*:"),
    ("protokoll", r"^protokoll\s*:"),
    ("abschnitt", r"^abschnitt\s+\d+\s*:"),
    ("fehlercode", r"^fehlercode\s+e-?\d+"),
)
SICHERHEITS_BLOECKE = ("[gefahr]", "[warnung]", "[hinweis]", "[status")
_MARKDOWN_PRAEFIX_RE = re.compile(r"^\s*(?:[-*+>]\s+|\d+[.)]\s+|\*\*)+")

# Bidi-Steuerzeichen (RLM/LRM, RLE/LRE/PDF, Isolate) sind fuer den Leser unsichtbar, stehen aber
# im String. Gemessen 2026-10-13: ein RLM direkt vor der Stempelzeile verhindert sowohl das Abstreifen
# des Markdown-Praefixes (der Anker greift am Zeilenanfang) als auch den Mustervergleich — ein korrekt
# geschriebenes hebraeisches oder arabisches Kapitel waere als "ungueltiges Schema" durchgefallen.
BIDI_STEUERZEICHEN = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c]")

# Ein Pflichtblock ist eine ALLEINSTEHENDE Klammerzeile "**[NAME: ... | ...]**".
# Das deckt [STATUS: ...] ebenso ab wie [CHRONIK: ... | SIEGEL: M-06-11] — Forum statt Wortliste.
STEMPEL_RE = re.compile(r"^\*{0,2}\[[A-Za-zÄÖÜäöü\-]{3,24}:[^\]]*\]\*{0,2}$")
SCHWELLE_WIEDERHOLUNG = 0.4
HISTORIE_FENSTER = 10          # Vergleich nur gegen die letzten N prosatragenden Vorgaenger


def _normalisiere(text: str) -> str:
    """Entfernt unsichtbare Bidi-Steuerzeichen, BEVOR verglichen wird (RTL-Sprachen, 2026-10-13)."""
    text = BIDI_STEUERZEICHEN.sub("", text)
    """Erst NFC, dann Umlaut-Vereinheitlichung — sonst faellt Text still durch jede Pruefung.

    Zwei belegte Fallen (2026-10-12): ASCII-Umschrift ("Pruefprotokoll" vs "Prüfprotokoll") und
    NFD-Kodierung ("a" + U+0308 statt U+00E4), die KEIN Muster der Pruefungen trifft.
    """
    text = unicodedata.normalize("NFC", text)
    return (text.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss"))


def rede_oder_emotion(text: str) -> str | None:
    """Erster Treffer aus Dialogzeichen oder Emotionsverben — NFD-fest, fuer alle Pruefungen."""
    geprueft = _normalisiere(text)
    for zeichen in DIALOG_ZEICHEN:
        if _normalisiere(zeichen) in geprueft:
            return zeichen
    for verb in EMOTIONS_VERBEN:
        if re.search(_normalisiere(verb), geprueft, re.I):
            return verb
    return None


STOER_PARAMETER_POOL = (
    {"typ": "SENSORIK_DRIFT", "detail": "Pneumatische Rohrpostleitung blockiert; feiner Papierschliff auf den Relaiskontakten.",
     "anweisung": "Lass die Figur beilaeufig die mechanische Blockade oder den Staub wahrnehmen."},
    {"typ": "AUDIT_DRUCK", "detail": "Unerwartete Revision durch die Zentrale Registratur angekuendigt.",
     "anweisung": "Spuerbare Nervositaet im Sektor; beschleunigtes Abheften von Protokollen."},
    {"typ": "PHYSISCHE_ANOMALIE", "detail": "Flackernde Entladungslampen mit 47 Hz; stechender Ozongeruch an den Schaltschraenken.",
     "anweisung": "Integriere die optische oder geruchliche Stoerung in die Arbeitsumgebung."},
    {"typ": "KLIMATISIERUNG", "detail": "Thermische Drift im Zwischenboden; Kondensat tropft auf die Kabelschaechte.",
     "anweisung": "Erwaehne die feuchte Kaelte oder das rhythmische Tropfen im Hintergrund."},
    {"typ": "SIGNAL_INTERFERENZ", "detail": "Daempfungsfelder erzeugen ein hochfrequentes Fiepen in den Gegensprechanlagen.",
     "anweisung": "Eine akustische Reizung unterbricht kurz die Konzentration."},
)


def stoerparameter(kapitel_index: int) -> dict:
    """Deterministisch rotierende Sektor-Bedingung je Kapitel (Modulo, kein Zufall, kein Zeitstempel)."""
    return STOER_PARAMETER_POOL[(kapitel_index - 1) % len(STOER_PARAMETER_POOL)]


PROSA_VERBOTENE_PRAEFIXE = (
    "[status", "[warnung", "[gefahr", "[hinweis", "warnung", "gefahr", "hinweis", "diagnose",
    "wartung", "intervall", "prüfung", "protokoll", "fehlercode", "abschnitt", "|", "```",
)


def ist_narrative_prosa(absatz: str) -> bool:
    """Nur deskriptiver Fliesstext taugt als Aktennotiz.

    Formalbloecke (auch fett gesetzt), Tabellenreste, Code-Fences und Fehlercode-Zeilen OHNE Nummer
    erzeugen im Prompt nur Rauschen und lenken vom Pflichtblock am Kapitelende ab. Eine Aktennotiz
    zitiert niemanden und traegt keine Emotionsverben — derselbe Maßstab wie an den Schlussabsatz.
    """
    rumpf = _normalisiere(_MARKDOWN_PRAEFIX_RE.sub("", absatz.strip()).strip().strip("*_#")).lower()
    if any(rumpf.startswith(p) for p in PROSA_VERBOTENE_PRAEFIXE):
        return False
    if rede_oder_emotion(absatz):
        return False
    if any(ist_strukturzeile(z) for z in absatz.splitlines()):
        return False
    return len(absatz) > 80


def ist_bausteinabsatz(absatz: str) -> bool:
    """Absatz, dessen erste Zeile formal ist (Marker oder fett gesetzter Block wie **WARNUNG**)."""
    erste = absatz.splitlines()[0]
    rumpf = _normalisiere(_MARKDOWN_PRAEFIX_RE.sub("", erste).strip().strip("*_#")).lower()
    return bool(zeilen_marker(erste)) or rumpf.startswith(("gefahr", "warnung", "hinweis", "status"))


def archiv_artefakt(buch_dir: str, kapitel_index: int, book_id: str) -> str | None:
    """Deterministischer Archiv-Splitter aus einem VORKAPITEL — nie aus dessen Schlussprosa.

    Der Ausschluss des Schlussabsatzes ist kein Detail: er stammt aus der Historie der Endschranke.
    Traegt der Splitter eine bereits abgewiesene Formulierung, setzt das Modell sie als eigenen
    Abschluss ein und die Wiederholungsschranke schlaegt zu (belegt 2026-10-12 an Kapitel 3/4).
    """
    if kapitel_index <= 1:
        return None
    seed = int(hashlib.sha256(f"{book_id}:{kapitel_index}:artefakt".encode("utf-8")).hexdigest(), 16)
    quell_index = (seed % (kapitel_index - 1)) + 1
    dateien = sorted(glob.glob(os.path.join(buch_dir, f"{quell_index:02d}_*.md")))
    if not dateien:
        return None
    roh = open(dateien[0], encoding="utf-8").read()
    rumpf = roh.split("---", 2)[2] if roh.startswith("---") else roh
    tabu = schluss_prosa(rumpf)                       # Schlussprosa des Quellkapitels: tabu
    # Alle bisherigen Schlussprosas: ein Splitter, der einem davon zu aehnlich ist, wuerde das Modell
    # in die Wiederholungsfalle fuehren. Gleiche Funktion und Schwelle wie die Schranke selbst.
    andere_schluesse = []
    for f in sorted(glob.glob(os.path.join(buch_dir, "*.md"))):
        r = open(f, encoding="utf-8").read()
        prosa = schluss_prosa(r.split("---", 2)[2] if r.startswith("---") else r)
        if prosa:
            andere_schluesse.append(prosa)
    kandidaten = []
    for absatz in (a.strip() for a in rumpf.split("\n\n")):
        if not absatz or len(absatz) < 80:
            continue
        if not ist_narrative_prosa(absatz):
            continue
        if tabu and schluss_prosa(absatz) == tabu:
            continue
        if ist_wiederholung(schluss_prosa(absatz), andere_schluesse)[0]:
            continue
        kandidaten.append(absatz)
    if not kandidaten:
        return None
    gewaehlt = kandidaten[seed % len(kandidaten)]
    saetze = re.split(r"(?<=[.!?])\s+", gewaehlt)
    return (f'[ARCHIV-QUERVERWEIS AUS KAPITEL {quell_index:02d}]: "'
            + " ".join(saetze[:2]).strip() + '"')


# Woertliche Instruktionen aus UNSEREN Prompts. Belegt 2026-10-12 (Issue #5): das freie
# nemotron-3.5-lightning kopierte den Schlusssatz des Prompts (generate_pipeline.py, Prompt-Bauer)
# unveraendert ins Kapitel. Die Liste stammt daher aus dem Code, nicht aus geratenen Stichwoertern.
PROMPT_VERBOTE = (
    "Der vorherige Abschnitt ist abgeschlossen",
    "Wiederhole seinen Wortlaut nicht",
    "nenne kein anderes Aktenzeichen",
    "Pflichtblock",
    "Ausgabeformat",
)

# Funktionswoerter fuer die Sprachpruefung. Kalibriert gegen bekannte Kapitel (2026-10-12):
# deutsche Kapitel 91-96 Prozent Sicherheit, das gemeldete englische 92, EN-Prolog 100.
SPRACH_DE = frozenset(("der die das und nicht ist ein eine mit sich dem den des wird werden auch aber "
                       "auf von zu im in wurde sind dass als nach bei").split())
SPRACH_EN = frozenset(("the and of to a is in that it for on with as are this be by not or was were "
                       "his her had from at but they").split())


def textsprache(text: str) -> tuple[str, int, int, float]:
    """Grobe Sprachbestimmung ueber Funktionswoerter: (Code, de, en, Sicherheit).

    Kein Linguistik-Ersatz, aber mechanisch pruefbar und gegen den Bestand kalibriert. Kurze Texte
    (< 20 Treffer) gelten als unsicher und werden nicht bewertet.
    """
    woerter = [w.lower().strip(".,;:!?\"'()[]") for w in text.split()]
    de = sum(1 for w in woerter if w in SPRACH_DE)
    en = sum(1 for w in woerter if w in SPRACH_EN)
    gesamt = de + en
    sicher = (max(de, en) / gesamt) if gesamt else 0.0
    return ("DE" if de > en else "EN"), de, en, sicher


def block_code(block: str) -> str:
    """Der kapitelgebundene Kennbezeichner eines Pflichtblocks — EINZIGE Quelle fuer Muster,
    Trace, Frontmatter und Leck-Pruefung.

    Nicht mehr nach dem Wort "CODE" suchen: das Schluesselwort kommt aus dem block_schema des
    Stils (CODE im Geraetehandbuch, SIEGEL im Maerchen, KAPITEL im Kinderbuch). Die FORM des
    Werts (A-xx-yy) ist in jeder Blockform dieselbe.
    """
    treffer = re.search(r":\s*([A-Za-z]{1,3}-\d{2,}-\d{2,})\s*[|\]]", block)
    return treffer.group(1).strip() if treffer else ""


def pflichtblock_muster(erwarteter_block: str):
    """Regex fuer den Pflichtblock: der CODE ist der Anker (exakt), Zustand/Sektor/Intervall sind Dekoration.

    Belegt 2026-10-12: qwen2.5:7b lieferte den Block vollstaendig (Zustand, Sektor, Code E-12-06),
    wich aber bei einer Ziffer ab (553h statt 552h) und setzte Markdown-Fettung. Byte-Gleichheit war
    damit die falsche Schaerfe — eine narrative Wiederholung verhindert schon der exakte Code.
    """
    # Der kapitelgebundene Code ist der Anker: er traegt in JEDER Blockform Artikel und Kapitel
    # (CODE/SIEGEL/KAPITEL/LOG/ZEUGNIS/...). Form statt Wortliste.
    eigen_code = block_code(erwarteter_block)
    if eigen_code:
        code = _normalisiere(eigen_code).lower()
        return re.compile(r"^\*{0,2}\[[A-Za-zÄÖÜäöü\-]{3,24}:[^\]]*"
                          + re.escape(code) + r"[^\]]*\]\*{0,2}$")
    alt = re.search(r"CODE:\s*([^|\]]+)", erwarteter_block)
    code = _normalisiere((alt.group(1) if alt else "").strip()).lower()
    return re.compile(r"^\[status:\s*\w+\s*\|\s*sub-sys:\s*sektor-\d+\s*\|\s*code:\s*"
                      + re.escape(code) + r"\s*\|\s*intervall:\s*\d+\s*h\]")


def zeilen_marker(zeile: str) -> list:
    """Akzeptierte Marker EINER Zeile — formal (Doppelpunkt/Ziffer), nie als Teilwort."""
    rumpf = _normalisiere(_MARKDOWN_PRAEFIX_RE.sub("", zeile).strip().strip("*_#")).lower()
    blank = _MARKDOWN_PRAEFIX_RE.sub("", zeile).strip()
    return ([name for name, muster in ABSCHLUSS_MARKER if re.match(muster, rumpf)]
            + [b for b in SICHERHEITS_BLOECKE if rumpf.startswith(b)]
            + (["stempel"] if STEMPEL_RE.match(blank) else []))


def status_block(book_id: str, artikel: str, index: int, style_flags: dict | None = None) -> str:
    """Deterministischer Pflichtblock je Kapitel: gleiche Eingaben -> gleicher Block (nachpruefbar).

    Form kommt aus dem STIL, wenn er ein block_schema traegt (z. B. Maerchen -> Chronik-Siegel);
    ohne Schema gilt die Geraetehandbuch-Form. Der CODE traegt Artikel- und Kapitelnummer, deshalb
    kann eine wortgleiche Wiederholung die Schranke nicht passieren — kein Zufall, kein Zeitstempel.
    """
    art = re.sub(r"\D", "", artikel) or "0"
    seed = hashlib.sha256(f"{book_id}|{artikel}|{index}".encode("utf-8")).hexdigest()
    n = int(seed[:12], 16)
    flags = style_flags or {}
    schema = flags.get("block_schema")
    if schema:
        zustaende = tuple(flags.get("zustaende") or ("BESTAETIGT", "GEPRUEFT", "BEREIT", "VERMERKT"))
        return schema.format(zustand=zustaende[n % len(zustaende)],
                             code=f"{flags.get('code_praefix', 'E')}-{int(art):02d}-{index:02d}")
    zustaende = ("NOMINAL", "DEGRADED", "PRUEFLAUF", "WARTUNGSMODUS")
    return (f"[STATUS: {zustaende[n % len(zustaende)]} | SUB-SYS: SEKTOR-{(n >> 4) % 30 + 1:02d} "
            f"| CODE: E-{int(art):02d}-{index:02d} | INTERVALL: {120 + (n >> 8) % 36 * 24}h]")


def pflichtblock_hinweis(block: str) -> str:
    """Prompt-Anhang: verlangt NUR den eigenen Pflichtblock und sperrt den Vorgaenger.

    Bewusst ohne jeden Fremd-Code: ein 7B-Modell zieht Aktenzeichen-Zeichenketten aus dem Prompt in
    den Erzaehltext (belegt 2026-10-12 an Kapitel 7, 8 und 9 — Kapitel 9 Versuch 1 wurde genau
    deshalb von fremdcode_im_text() verworfen: "Fremd-Aktenzeichen im Kapiteltext (E-19-08)").
    """
    return ("\n\nPFLICHT AM ENDE (wird maschinell geprueft): Der letzte Absatz enthaelt in einer "
            "eigenen Zeile genau diesen Systemblock, Zeichen fuer Zeichen:\n" + block
            + "\nDer vorherige Abschnitt ist abgeschlossen. Wiederhole seinen Wortlaut nicht und "
              "nenne kein anderes Aktenzeichen als das oben angegebene.")


def schlussabsatz(text: str) -> str:
    """Letzter nicht leerer Absatz eines Textes."""
    absaetze = [a.strip() for a in text.split("\n\n") if a.strip()]
    return absaetze[-1] if absaetze else ""


def inhaltliche_woerter(text: str) -> set:
    """Woerter ab 4 Zeichen; Fuellwoerter (die, der, und, aber) verwaessern sonst jede Aehnlichkeit."""
    return {w for w in re.findall(r"[^\W\d_]{4,}", text.lower())}


def ist_strukturzeile(zeile: str) -> bool:
    """Zeile, die ein Strukturbaustein ist (Pflichtblock oder Marker am Zeilenanfang)."""
    rumpf = BIDI_STEUERZEICHEN.sub("", _MARKDOWN_PRAEFIX_RE.sub("", BIDI_STEUERZEICHEN.sub("", zeile))).strip().strip("*_#").strip()
    return not rumpf or bool(zeilen_marker(rumpf))


def schluss_prosa(text: str) -> str:
    """Der letzte Absatz, der KEIN Strukturbaustein ist — die Historien-Schranke vergleicht nur Prosa.

    Zwei Fallen waren hier zu umgehen (beide am 2026-10-12 belegt):
    1. Der Pflichtblock darf nicht mitgezaehlt werden, sonst sind alle Kapitel zu 100 % "gleich"
       (status, degraded, sektor, code, intervall) -> Fehlalarm.
    2. Das Modell setzt den Block als EIGENEN Absatz ans Ende. Wird nur der letzte Absatz gefiltert,
       bleibt nichts uebrig und die Schranke wird blind. Daher rueckwaerts den ersten inhaltstragenden
       Absatz nehmen.
    """
    for absatz in reversed([a.strip() for a in text.split("\n\n") if a.strip()]):
        reste = [z.strip() for z in absatz.splitlines() if z.strip() and not ist_strukturzeile(z)]
        if reste:
            return " ".join(reste)
    return ""


def ist_wiederholung(schluss: str, vorgaenger: list, schwelle: float = SCHWELLE_WIEDERHOLUNG):
    """Jaccard-Aehnlichkeit ueber Wortmengen gegen die Schlussabsaetze der Vorkapitel."""
    a = inhaltliche_woerter(schluss)
    if not a:
        return False, 0.0
    bester = 0.0
    for alt_text in vorgaenger:
        b = inhaltliche_woerter(alt_text)
        if not b:
            continue
        bester = max(bester, len(a & b) / len(a | b))
    return (bester >= schwelle), bester
# Weiche Woerter (system, gefahr, hinweis) flogen raus: sie kommen in normaler Prosa vor und
# liessen narrative Schluesse durch (belegt 2026-10-12 an Kapitel 2, dessen Schlusssatz nur
# ueber "System"/"Gefahr" bestand). Ein Sicherheitsblock ist die zweite zulaessige Form.


def audit_manual_ending(text: str, erwarteter_block: str | None = None,
                        style_flags: dict | None = None,
                        sprache: str | None = None,
                        figuren: list | None = None) -> tuple[bool, str]:
    """Mechanische Endschranke fuer Sach-/Handbuchgenres: prueft NUR den letzten Absatz.

    Grund (gemessen 2026-10-12): der Prompt-Bann hielt das Modell von Moral-Bekenntnissen ab — es
    floh danach in narrative Klischees ('"Gut gemacht.", flüsterte sie'). Prosa-Regeln im Prompt
    sind dafuer zu weich, deshalb eine harte Pruefung mit begrenzten Wiederholungen.
    """
    absaetze = [a.strip() for a in text.strip().split("\n\n") if a.strip()]
    if not absaetze:
        return False, "leerer Text"
    letzter = absaetze[-1]
    # Rede- und Emotionssperre kommen aus dem STIL (style_flags). Ohne Flags bleibt der strenge
    # Handbuch-Massstab — der Bestand (Kapitel 1-11) darf sich dadurch nicht veraendern.
    erlaube_rede = bool((style_flags or {}).get("erlaube_rede"))
    erlaube_emotion = bool((style_flags or {}).get("erlaube_emotion"))
    treffer = rede_oder_emotion(letzter)
    if treffer:
        ist_rede = treffer in DIALOG_ZEICHEN
        if not ((erlaube_rede and ist_rede) or (erlaube_emotion and not ist_rede)):
            art = "woertliche Rede" if ist_rede else "Dialog-/Emotionsverb"
            return False, f"{art} im Schlussabsatz ({treffer})"
    # GANZKOERPER-PRUEFUNG — belegt 2026-10-12 an Kapitel 11: die Endschranke sah nur den letzten
    # Absatz, waehrend der Koerper 26 Dialogzeichen, "Wir sind gut," fluestert sie leise. und den
    # STATUS-Block 19x wiederholt enthielt (Artikel-6-Bezug: 0 Treffer). Kapitel 8 und 10 ebenso.
    # Deshalb: das ganze Genre-Gesetz gilt fuer den ganzen Text, nicht nur fuer den Schlusstakt.
    # Pro Regel schalten, nicht pauschal: der Essay verbietet Rede, erlaubt aber Reflexion —
    # eine gemeinsame Bedingung haette den Scan dort komplett abgeschaltet (gemessen 2026-10-12).
    if not erlaube_rede:
        dialog = sum(text.count(z) for z in DIALOG_ZEICHEN)
        if dialog:
            return False, (f"woertliche Rede im Kapitelkoerper ({dialog} Zeichen) — "
                           "dieses Genre verlangt Sachtext, nicht nur einen sachlichen Schluss")
    # Formvorgabe als pruefbare Regel: Genres mit "stanza_zeilen" (z. B. Limericks = 5) muessen im
    # Koerper ausschliesslich Strophen dieser Laenge fuehren. Der REIM selbst ist damit NICHT geprueft —
    # das steht ausdruecklich als Luecke im Bericht, statt als erfuellt zu gelten.
    verse = (style_flags or {}).get("stanza_zeilen")
    if verse:
        bloecke = [b for b in text.split("\n\n") if b.strip() and not b.strip().startswith("**[")]
        falsch = [(len(b.strip().splitlines()), b.strip().splitlines()[0][:40]) for b in bloecke
                  if len(b.strip().splitlines()) != verse and len(b.strip().splitlines()) > 1]
        if falsch:
            return False, (f"Strophenform verletzt: {falsch[0][0]} Zeilen statt {verse} "
                           f"(\"{falsch[0][1]}...\")")
    # Prompt-Leck: unsere eigenen Instruktionen duerfen nicht im Artefakt landen (Issue #5).
    for verboten in PROMPT_VERBOTE:
        if verboten.lower() in text.lower():
            return False, (f"Prompt-Fragment im Kapiteltext (\"{verboten}\") — "
                           "die Anweisung wurde als Erzaehltext uebernommen")
    # Sprache: ein Kapitel muss in der Sprache des Buchs geschrieben sein.
    if sprache:
        erkannt, de, en, sicher = textsprache(text)
        if (de + en) >= 20 and erkannt != sprache.upper() and sicher >= 0.6:
            return False, (f"Sprache verletzt: Kapitel ist {erkannt} ({de} deutsche vs. {en} englische "
                           f"Funktionswoerter, {sicher * 100:.0f}%), erwartet {sprache.upper()}")
    # Figurenverbot — eigenes Flag, NICHT "erlaube_rede: false". Kalibriert 2026-10-12: der
    # Philosophische Essay verbietet Rede, fuehrt aber legitim Figuren (Mira, Halden); ein Filter
    # ueber erlaube_rede haette dort Fehlalarme produziert. Greift nur bei figuren_verboten: true.
    if (style_flags or {}).get("figuren_verboten"):
        for figur in (figuren or []):
            name = str(figur).strip()
            if name and re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                return False, (f"Figur '{name}' im figurenfreien Genre — dieses Genre fuehrt keine Namen")
        # Halluzinierte Spontanfiguren stehen in keiner Liste: Rollenmuster statt Positivliste.
        # Beide Richtungen, weil "Milo nickte" und "sagte Milo" sonst durchrutschen.
        # Zwei Verbfamilien, kalibriert 2026-10-12: die zweite Richtung (Grosswort + Verb) hatte mit
        # "antwortet" einen Fehlalarm auf "Das System antwortet" — im Handbuch voellig normal. Sie laeuft
        # deshalb nur mit rein narrativen Verben; die technisch verwendbaren (sagte, antwortet, fragt,
        # ruft) bleiben auf die erste Richtung beschraenkt, die ein folgendes Grosswort verlangt.
        # BEKANNTE LUECKE, bewusst: "Milo antwortet nicht" (Name + technisches Verb) wird nicht erkannt,
        # weil "antwortet" aus der zweiten Richtung entfernt wurde, um "Das System antwortet" zu retten.
        # Eine Vornamen-Blacklist waere der naechste Hebel — sie ist unvollstaendig per Natur und wurde
        # deshalb noch nicht gebaut. Der deklarierte Figuren-Fall (Buch mit characters) ist abgedeckt.
        # Getrennte Verbfamilien (Betreiber-Vorgabe 2026-10-12): die zweite Richtung darf nur genuin
        # menschlich-narrative Regieverben enthalten. Funktionale Verben (antwortet, meldet, reagiert)
        # sind im Handbuch Standard ("Das System antwortet") und loesten einen Fehlalarm aus.
        STELLE = ("sagte|sagt|antwortete|antwortet|flüsterte|flüstert|dachte|denkt|nickte|nickt|"
                  "blickte|blickt|lächelte|lächelt|seufzte|seufzt|fragte|fragt|rief|ruft")
        NARRATIV = ("sagte|dachte|flüsterte|seufzte|lächelte|nickte|schrie|spürte|blickte|schritt")
        PRONOMEN = {"sie", "er", "es", "wir", "ihr", "der", "die", "das", "man", "ich"}
        for muster in (rf"\b(?:{STELLE})\s+([A-ZÄÖÜ][a-zäöüß]{{2,}})",
                       rf"\b([A-ZÄÖÜ][a-zäöüß]{{2,}})\s+(?:{NARRATIV})"):
            for treffer in re.findall(muster, text):
                if treffer.lower() not in PRONOMEN:
                    return False, (f"personifizierter Akteur '{treffer}' im figurenfreien Genre — "
                                   "Handbuch, Kochbuch, Manifest und Lebensweisheiten fuehren keine Figuren")
    if not erlaube_emotion:
        erzaehlend = [w for w in ("flüster", "lächel", "seufz", "nickt", "kicher", "stöhnt")
                      if w in text.lower()]
        if erzaehlend:
            return False, ("Personenregie im Kapitelkoerper (" + ", ".join(erzaehlend) +
                           ") — Handbuchgenres fuehren keine Figuren")
        # Wiederholungs-Bremse (Repetition Guard): saetze > 2x wortgleich = Degenerations-Schleife.
        # Nur fuer die strengen Genres — im Maerchen ist ein Kehrvers Stilmittel, keine Degeneration.
    saetze = [z.strip() for z in re.split(r"(?<=[.!?])\s+", text) if len(z.strip()) > 30]
    zaehler: dict = {}
    for satz in saetze:
        zaehler[satz] = zaehler.get(satz, 0) + 1
    schleifen = [(z, k) for z, k in zaehler.items() if k > 2]
    if schleifen:
        return False, (f"Wiederholungsschleife: ein Satz {schleifen[0][1]}x wortgleich "
                       f"(\"{schleifen[0][0][:60]}...\")")
    eigen = block_code(erwarteter_block) if erwarteter_block else ""
    if eigen:
        # Nur STEMPELZEILEN zaehlen, nicht jede Nennung: die Handbuch-Regel verlangt ausdruecklich einen
        # Fließtext-Fehlercode ("Fehlercode E-xx-yy: <Stoerung>") — der ist kein Loop. Belegt 2026-10-12:
        # ein DeepSeek-Kapitel fiel 3/3 durch, weil die Regel genau das tat, was der Stil verlangt.
        stempel_zeilen = [z for z in text.splitlines()
                          if eigen in z and STEMPEL_RE.match(_MARKDOWN_PRAEFIX_RE.sub("", z).strip())]
        if len(stempel_zeilen) > 1:
            return False, (f"Pflichtblock {eigen} {len(stempel_zeilen)}x als Stempelzeile "
                           "(Wiederholungsschleife statt Kapitel)")
    if erwarteter_block:
        muster = pflichtblock_muster(erwarteter_block)
        code = block_code(erwarteter_block) or "?"
        for zeile in letzter.splitlines():
            rumpf = BIDI_STEUERZEICHEN.sub("", _MARKDOWN_PRAEFIX_RE.sub("", BIDI_STEUERZEICHEN.sub("", zeile))).strip().strip("*_#").strip()
            if muster.match(_normalisiere(rumpf).lower()):
                return True, "Passed (Pflichtblock " + code + ")"
        return False, ("ungueltiges Schema: keine alleinstehende Klammerzeile mit dem Code "
                       + code + " am Kapitelende")
    treffer = []
    for zeile in letzter.splitlines():
        for t in zeilen_marker(zeile):
            if t not in treffer:
                treffer.append(t)
    if not treffer:
        return False, ("kein struktureller Abschluss am Zeilenanfang (z. B. 'Fehlercode E-01', "
                       "'Wartung:', 'Diagnose:', 'Pruefung:', '[WARNUNG]')")
    return True, "Passed (" + "+".join(treffer) + ")"


def fremdcode_im_text(text: str, erwarteter_block: str) -> str | None:
    """Liefert ein Fremd-Aktenzeichen, wenn der Kapiteltext ein ANDERES als das erwartete nennt.

    Belegt 2026-10-12: der Prompt-Sperrvermerk wurde als Erzaehltext kopiert ("Der vorherige
    Wartungsabschluss lautete: ... E-14-07 ...") — Metatext im veroeffentlichten Artefakt.
    """
    eigen_code = _normalisiere(block_code(erwarteter_block)).lower()
    # Bewusst OHNE Endanker: der belegte Leck-Fall (Kapitel 9) nannte den Fremdcode mitten im Satz,
    # nicht vor einem "|" oder "]". Der eigene Code wird per Gleichheit ausgenommen.
    for treffer in re.finditer(r"[A-Za-z]{1,3}-\d{2,}-\d{2,}", _normalisiere(text)):
        if treffer.group(0).lower() != eigen_code:
            return treffer.group(0)
    return None


def erzeuge_mit_endschranke(prompt: str, model: str, host: str, style_flags: dict,
                            label: str, versuche: int = 3,
                            vorgaenger_schluesse: list | None = None,
                            erwarteter_block: str | None = None,
                            details: dict | None = None,
                            backend: str = "ollama",
                            sprache: str | None = None,
                            figuren: list | None = None) -> tuple[str, bool, str, int]:
    """Generiert und prueft das Ende, solange das Genre es verlangt.

    Rueckgabe (text, ende_ok, grund, gebrauchte_versuche). Nach Ausschoepfung wird der Text MIT Vermerk
    geliefert: kein stiller Durchlauf, aber auch kein Totalverlust.
    """
    if not style_flags.get("manual_ending"):
        # Ehrlichkeit statt Gruen: hier wurde nichts geprueft, also steht das auch so im Artefakt.
        return (erzeuge_text(prompt, model, host, backend, details), False,
                "nicht geprueft (Stil ohne Endschranke) — Flags fehlen oder Genre ohne Schema", 0)
    text, grund = "", ""
    for i in range(1, versuche + 1):
        text = erzeuge_text(prompt, model, host, backend=backend, details=details)
        ok, grund = audit_manual_ending(text, erwarteter_block=erwarteter_block,
                                        style_flags=style_flags, sprache=sprache, figuren=figuren)
        if ok and vorgaenger_schluesse:
            # Nur die Prosa vergleichen: der Pflichtblock ist per Kapitelcode eindeutig und darf
            # nicht als "Wiederholung" gelten.
            # Wanderndes Fenster: nur die letzten HISTORIE_FENSTER prosatragenden Vorgaenger.
            # Sonst waechst mit jedem Kapitel die Trefferwahrscheinlichkeit gegen die Schwelle.
            fenster = [p for p in (schluss_prosa(v) for v in vorgaenger_schluesse) if p][-HISTORIE_FENSTER:]
            wieder, aehnlich = ist_wiederholung(schluss_prosa(text), fenster)
            if details is not None:
                details["jaccard_max"] = round(aehnlich, 3)
            if wieder:
                ok, grund = False, ("Wiederholung des Schlussabsatzes "
                                    f"({aehnlich:.0%} Wortueberlappung mit einem Vorkapitel)")
        if ok and erwarteter_block:
            fremd = fremdcode_im_text(text, erwarteter_block)
            if fremd:
                ok, grund = False, (f"Fremd-Aktenzeichen im Kapiteltext ({fremd}) — "
                                    "Metatext/Prompt-Leck statt Erzaehlung")
            elif details is not None:
                details["leak_free"] = True
        print(f"  [{label}] Versuch {i}/{versuche}: Endschranke "
              f"{'erfuellt' if ok else 'VERFEHLT'} ({grund})", flush=True)
        if not ok:
            schluss = schlussabsatz(text)[-120:].replace(chr(10), " ")
            print(f"  [{label}]   abgelehnter Schluss: " + schluss, flush=True)
            prosa = schluss_prosa(text)[-120:].replace(chr(10), " ")
            if prosa and prosa not in schluss:
                # Bei einer Wiederholungs-Ablehnung liegt der Grund in der Prosa, nicht im Block.
                print(f"  [{label}]   verglichene Prosa: " + prosa, flush=True)
        if ok:
            return text, True, grund, i
    return text, False, grund, versuche


def naechstes_buch() -> str:
    """Neuestes Buchverzeichnis nach mtime — kein Register, das driften kann."""
    if os.path.isdir(BOOKS_DIR):
        buende = [os.path.join(BOOKS_DIR, d) for d in os.listdir(BOOKS_DIR)
                  if d.startswith("buch_") and os.path.isdir(os.path.join(BOOKS_DIR, d))]
        if buende:
            return os.path.basename(max(buende, key=os.path.getmtime))
    raise FileNotFoundError(f"Kein Buch unter {BOOKS_DIR} — erst --mode new-book ausfuehren.")


def buch_kapitel(buch_dir: str) -> list:
    """Kapiteldateien in Reihenfolge (00_prolog.md zuerst), aus dem Dateisystem."""
    return sorted(f for f in os.listdir(buch_dir) if re.match(r"^\d{2,}_.*\.md$", f))


def naechster_artikel(lang: str, covered: list) -> str | None:
    """Erster noch unbenutzter Artikel in kanonischer (sortierter) Reihenfolge — nicht zufaellig."""
    alle = [os.path.splitext(os.path.basename(p))[0]
            for p in sorted(glob.glob(os.path.join(ARTICLES_DIR, lang.lower(), "*.md")))]
    for a in alle:
        if a not in covered:
            return a
    return None


def inject_chapter(book_id: str, datei: str, artikel: str | None = None, fork_from: str | None = None,
                   lang: str = "DE") -> str:
    """Externen Kapiteltext kontrolliert in den Kanon lassen (nur lineare Injektion).

    Reihenfolge: erst pruefen, dann schreiben. Bei jedem Verstoss bleibt das Dateisystem unberuehrt.
    Herkunft wird ausgewiesen (origin/source_file/injected_at) und es werden KEINE Modell-Statistiken
    erfunden: model steht als "external", backend als "manual", tokens_generated auf 0. Der Injektor
    erzeugt auch keinen Abschlussblock — der muss im eingereichten Text stehen, sonst waere die
    Pruefung zirkulaer (wir wuerden unser eigenes Siegel auf einen ungeprueften Text kleben).

    Abweichungen zur Auftragsskizze, bewusst:
    * --fork-from bricht mit Exit 1 ab, nicht mit 2 — 2 heisst hier "Fallback geschrieben".
    * Das Lock ist BOOKS_DIR/.append.lock (global), dieselbe Datei wie beim Anhang, damit sich
      Injektion und Generierung nie ueberholen.
    * Frontmatter bleibt flach (model/backend/tokens_generated), weil der Indexer diese Felder liest;
      ein verschachtelter generation_stats-Block waere fuer ihn unsichtbar.
    """
    if fork_from:
        raise RuntimeError("Verzweigungen (--fork-from) sind in Version 1 nicht freigegeben — nur lineare "
                           "Injektion. Voraussetzung waere KAPITEL_RE auf ^\\d{2,}[a-z]?_ und ein Anker "
                           "in block_code; siehe Epic 'Zweige'.")
    buch_dir = os.path.join(BOOKS_DIR, book_id)
    meta_pfad = os.path.join(buch_dir, "book.json")
    if not os.path.isfile(meta_pfad):
        raise FileNotFoundError(f"Kein book.json in {buch_dir}")
    if not os.path.isfile(datei):
        raise FileNotFoundError(f"Eingabedatei fehlt: {datei}")
    rohtext = open(datei, encoding="utf-8").read()
    if not rohtext.strip():
        raise ValueError(f"Eingabedatei ist leer: {datei}")
    meta = json.load(open(meta_pfad, encoding="utf-8"))
    locale = load_locale(lang)
    stil = meta.get("style") or ""
    if stil not in locale.get("styles", {}):
        raise ValueError(f"Stil '{stil}' des Buchs fehlt in locales/{lang.lower()}.json")
    flags = locale.get("style_flags", {}).get(stil, {})

    os.makedirs(BOOKS_DIR, exist_ok=True)
    sperrpfad = os.path.join(BOOKS_DIR, ".append.lock")
    with open(sperrpfad, "w") as sperre:
        ende = time.monotonic() + 10.0
        while True:
            try:
                fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > ende:
                    raise RuntimeError("Buch ist gesperrt (ein anderer Lauf schreibt) — nach 10 s aufgegeben")
                time.sleep(0.5)
        try:
            return _inject_gesperrt(book_id, buch_dir, meta, meta_pfad, rohtext, datei, artikel, stil, flags, lang)
        finally:
            fcntl.flock(sperre, fcntl.LOCK_UN)


def _inject_gesperrt(book_id: str, buch_dir: str, meta: dict, meta_pfad: str, rohtext: str, datei: str,
                     artikel: str | None, stil: str, flags: dict, lang: str) -> str:
    """Kern der Injektion — laeuft ausschliesslich unter der Sperre."""
    kapitel = buch_kapitel(buch_dir)
    indizes = []
    for name in kapitel:
        if name == "00_prolog.md":
            continue
        treffer = re.match(r"^(\d+)", name)
        if treffer:
            indizes.append(int(treffer.group(1)))
    index = (max(indizes) + 1) if indizes else 1
    covered = list(meta.get("covered_articles", []))
    for name in kapitel:
        if name == "00_prolog.md":
            continue
        t = open(os.path.join(buch_dir, name), encoding="utf-8").read()
        m = re.search(r'article:\s*"([^"]*)"', t)
        if m and m.group(1) and m.group(1) not in covered:
            covered.append(m.group(1))
    if artikel:
        if not re.fullmatch(r"art_\d{2}", artikel):
            raise ValueError(f"ungueltiger Artikel '{artikel}' — erwartet art_NN")
        covered = [c for c in covered if c != artikel]
    artikel = artikel or naechster_artikel(lang, covered)
    if not artikel:
        raise RuntimeError(f"kein offener Artikel fuer {book_id} — alle verhandelt")

    block = status_block(book_id, artikel, index, flags)
    ok, grund = audit_manual_ending(rohtext, erwarteter_block=block if flags.get("manual_ending") else None,
                                    style_flags=flags, sprache=lang,
                                    figuren=meta.get("characters") or [])
    if not ok:
        raise ValueError(f"Schrankenpruefung fehlgeschlagen ({grund}).\n"
                         f"Erwartete Abschlusszeile fuer Index {index}, Artikel {artikel}:\n{block}")

    titel = ""
    for zeile in rohtext.splitlines():
        if zeile.strip().startswith("# "):
            titel = zeile.strip()[2:].strip()
            break
    titel = titel or f"Abschnitt {index}"
    dateiname = f"{index:02d}_{artikel}_{sanitize_filename(titel).lower()[:40]}.md"
    ziel = os.path.join(buch_dir, dateiname)
    if os.path.exists(ziel):
        raise FileExistsError(f"Zieldatei existiert bereits: {ziel}")
    vorgaenger = kapitel[-1] if kapitel else ""
    kopf = (f'---\nbook_id: "{book_id}"\nchapter_index: {index}\nchapter_title: "{titel}"\n'
            f'article: "{artikel}"\nlanguage: "{lang.upper()}"\nstyle: "{stil}"\n'
            f'pov: "{meta.get("pov", "third_person")}"\nprevious_chapter_file: "{vorgaenger}"\n'
            f'origin: "external_injection"\nsource_file: "{os.path.basename(datei)}"\n'
            f'injected_at: "{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}"\n'
            f'model: "external"\nbackend: "manual"\ntokens_generated: 0\n'
            f'manual_ending_ok: true\nmanual_ending_code: "{block_code(block) or artikel}"\n---\n\n')
    write_new_file(ziel, kopf + rohtext.strip() + "\n")
    if artikel not in meta.setdefault("covered_articles", []):
        meta["covered_articles"].append(artikel)
    meta["current_chapter"] = str(index)
    with open(meta_pfad, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[Injektion] externes Kapitel aufgenommen: {os.path.basename(ziel)} "
          f"(Artikel {artikel}, Index {index}, Herkunft {os.path.basename(datei)})", flush=True)
    return ziel


def append_chapter(book_id: str | None = None, lang: str | None = None, model: str = "qwen2.5:7b",
                   host: str = "http://localhost:11434", backend: str = "ollama",
                   artikel: str | None = None) -> str:
    """Stufe 2: naechstes Kapitel anhaengen — mit Sperre gegen gleichzeitige Laeufe.

    Belegt 2026-10-12: zwei Prozesse (Rotationslauf und ein Ersatzlauf) berechneten denselben Index,
    weil die Nummer aus dem Dateibestand abgeleitet wird (Lesen, dann Schreiben) und die Dateinamen
    wegen unterschiedlicher Artikelwahlen differierten — `open(..., "x")` konnte das nicht fangen.
    Deshalb liegt jetzt der GESAMTE Anhang unter einer Sperre: Index, Generierung und Schreiben.
    """
    os.makedirs(BOOKS_DIR, exist_ok=True)
    sperrpfad = os.path.join(BOOKS_DIR, ".append.lock")
    with open(sperrpfad, "w") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX)
        try:
            return _append_chapter_gesperrt(book_id=book_id, lang=lang, model=model, host=host,
                                           backend=backend, artikel=artikel)
        finally:
            fcntl.flock(sperre, fcntl.LOCK_UN)


def _append_chapter_gesperrt(book_id: str | None = None, lang: str | None = None,
                             model: str = "qwen2.5:7b", host: str = "http://localhost:11434",
                             backend: str = "ollama", artikel: str | None = None) -> str:
    """Stufe 2 (Kern): naechstes Kapitel anhaengen — deterministisch, kollisionssicher, mit Endschranke."""
    book_id = book_id or naechstes_buch()
    buch_dir = os.path.join(BOOKS_DIR, book_id)
    if not os.path.isdir(buch_dir):
        raise FileNotFoundError(f"Buch nicht gefunden: {buch_dir}")

    meta = json.load(open(os.path.join(buch_dir, "book.json"), encoding="utf-8"))
    sprache = (lang or meta.get("language", "DE")).upper()
    style_name = meta["style"]
    locale = load_locale(sprache)
    # Belegt 2026-10-12: der Runner uebergab fuer ALLE Buende --lang DE, auch fuer den englischen Band.
    # Die DE-Locale kennt "Limericks" nicht, der Stilname fiel still auf sich selbst zurueck, die Flags
    # fehlten, die Schranke war aus und das Modell schrieb deutsche Handbuchprosa in den EN-Band.
    if style_name not in locale.get("styles", {}):
        raise ValueError(
            f"Stil '{style_name}' fehlt in locales/{sprache.lower()}.json — das Buch deklariert "
            f"language={meta.get('language')!r}. Vermutlich wurde die falsche Locale geladen; "
            "es gibt bewusst keinen stillen Rueckfall auf den Stilnamen.")
    style_desc = locale["styles"][style_name]
    style_rules = locale.get("style_rules", {}).get(style_name, [])
    style_flags = locale.get("style_flags", {}).get(style_name, {})
    lang_name = book_language_directive(sprache, locale)
    core_rule = (locale.get("guardrail_prompt") or locale.get("core_guardrail")
                 or "Schutz von Leben und koerperlicher Unversehrtheit hat Vorrang.")

    kapitel = buch_kapitel(buch_dir)
    if not kapitel:
        raise FileNotFoundError(f"Buch ohne Prolog: {buch_dir}")
    vorherige = kapitel[-1]
    vorgaenger = open(os.path.join(buch_dir, vorherige), encoding="utf-8").read()
    if vorgaenger.startswith("---"):
        vorgaenger = vorgaenger.split("---", 2)[-1].strip()
    # Verhandelte Artikel aus dem DATEISYSTEM ergaenzen (Frontmatter der Kapitel): eine Liste in
    # book.json kann driften, die Dateien nicht. Der Index kommt ohnehin schon von dort.
    covered = list(meta.get("covered_articles", []))
    for k in kapitel:
        if k == "00_prolog.md":
            continue
        txt = open(os.path.join(buch_dir, k), encoding="utf-8").read()
        treffer = re.search(r'^article:\s*"?([A-Za-z0-9_]+)"?\s*$', txt, re.M)
        if treffer and treffer.group(1) not in covered:
            covered.append(treffer.group(1))
    index = len([k for k in kapitel if k != "00_prolog.md"]) + 1

    # Expliziter Artikel schlaegt die Automatik: beim Ersetzen eines Kapitels muss der verhandelte
    # Artikel erhalten bleiben (belegt 2026-10-12, Kapitel 11 rutschte sonst auf art_07).
    if artikel:
        if not re.fullmatch(r"art_\d{2}", artikel):
            raise ValueError(f"ungueltiger Artikel '{artikel}' — erwartet art_NN")
        covered = [c for c in covered if c != artikel]
    artikel = artikel or naechster_artikel(sprache, covered)
    if not artikel:
        raise RuntimeError(f"Alle Artikel in '{book_id}' verhandelt — neues Buch per --mode new-book.")

    art = load_article(artikel, sprache)
    prompt = build_chapter_prompt(meta, lang_name, style_name, style_desc, style_rules, core_rule,
                                  index, artikel, art["body"], vorgaenger, vorherige)
    print(f"[Kapitel {index}] Buch '{book_id}' | Artikel {artikel} | Vorgaenger {vorherige}", flush=True)
    # Schlussabsaetze der Vorkapitel — die Schranke braucht ein Gedaechtnis ueber Kapitel hinweg,
    # sonst passiert derselbe Mustersatz jede Runde erneut (belegt 2026-10-12, Kapitel 3 == 4).
    vorgaenger_schluesse = []
    for k in kapitel:
        roh = open(os.path.join(buch_dir, k), encoding="utf-8").read()
        sa = schlussabsatz(roh.split("---", 2)[2] if roh.startswith("---") else roh)
        if sa:
            vorgaenger_schluesse.append(sa)
    block = status_block(book_id, artikel, index, style_flags)
    prompt += pflichtblock_hinweis(block)
    # Salz: dosierte, deterministische Reibung — Sektor-Bedingung + Aktennotiz aus einem Vorkapitel.
    stoerung = stoerparameter(index)
    artefakt = archiv_artefakt(buch_dir, index, book_id)
    prompt += (f"\n\n### BEHOERDLICHE RAHMENBEDINGUNGEN DIESES ABSCHNITTS:\n"
               f"- Sektor-Bedingung ({stoerung['typ']}): {stoerung['detail']}\n"
               f"  -> Vorgabe: {stoerung['anweisung']} Nimm sie in mindestens einem Satz der Szene auf.")
    if artefakt:
        prompt += (f"\n- Aktennotiz zur Beruecksichtigung:\n  {artefakt}\n"
                   "  -> Vorgabe: Lass dieses Ereignis kurz als Referenz oder Erinnerung einfliessen.")
    t_start = time.monotonic()
    details: dict = {}
    text, ende_ok, grund, versuche = erzeuge_mit_endschranke(
        prompt, model, host, style_flags,
        sprache=sprache, figuren=meta.get("characters") or [],
        label=f"Kapitel {index}", versuche=3,
        vorgaenger_schluesse=vorgaenger_schluesse,
                                                             erwarteter_block=block, details=details,
                                                             backend=backend)
    dauer = round(time.monotonic() - t_start, 1)
    if not text.strip():
        raise RuntimeError("Leere Antwort vom Modell — Kapitel wird nicht geschrieben.")

    titel = extract_title(text)
    # BEIDE Faelle markieren: ein Erfolg ohne Flag ist fuer Downstream-Parser (Index-Builder,
    # Monitoring) nicht von "nie geprueft" zu unterscheiden.
    # Erzeugungs-Metriken ins Artefakt: Modell, Genre, Dauer, Aehnlichkeitswert, Leck-Freiheit.
    # "backend" ist bewusst der EFFEKTIVE Wert — der Buchpfad generiert heute ueber Ollama;
    # der --backend-Schalter ist noch nicht verdrahtet (belegt 2026-10-12).
    stats = ""
    if details:
        stats = (f'model: "{model}"\n'
                 f'genre: "{meta.get("style", "")}"\n'
                 f'backend: "{backend}"\n'
                 f'duration_seconds: {dauer}\n'
                 f'jaccard_max: {details.get("jaccard_max", 0.0)}\n'
                 + (f'tokens_generated: {details["tokens_generated"]}\n'
                    if details.get("tokens_generated") else "")
                 + ('leak_free: true\n' if details.get("leak_free") else ""))
    code_fuer_frontmatter = block_code(block)
    marke = (f'manual_ending_ok: {"true" if ende_ok else "false"}\n'
             f'manual_ending_attempts: {versuche}\n'
             f'manual_ending_code: "{code_fuer_frontmatter}"\n'
             f'scene_condition: "{stoerung["typ"]}"\n'
             f'archive_note: "{("KAPITEL " + artefakt.split("KAPITEL ")[1][:2]) if artefakt else ""}"\n'
             + stats
             + f'manual_ending_note: "{grund}"\n')
    datei = f"{index:02d}_{artikel}_{sanitize_filename(titel).lower()[:40]}.md"
    pfad = write_new_file(os.path.join(buch_dir, datei),
                          f'---\nbook_id: "{book_id}"\nchapter_index: {index}\n'
                          f'chapter_title: "{titel}"\narticle: "{artikel}"\nlanguage: "{sprache}"\n'
                          f'style: "{style_name}"\npov: "{meta["pov"]}"\n'
                          f'previous_chapter_file: "{vorherige}"\n{marke}---\n\n' + text.strip() + "\n")

    # book.json ATOMAR aktualisieren (temp + os.replace) — kein halber Zustand
    meta["covered_articles"] = covered + [artikel]
    meta["current_chapter"] = index
    tmp = os.path.join(buch_dir, "book.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, os.path.join(buch_dir, "book.json"))
    return pfad


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
    parser.add_argument("--file", default=None, help="Eingabedatei fuer inject-chapter.")
    parser.add_argument("--fork-from", default=None,
                        help="Verzweigung (nicht freigegeben) — inject-chapter lehnt das ab.")
    parser.add_argument("--mode", choices=("tales", "new-book", "append-chapter", "prolog",
                                           "inject-chapter"), default="tales",
                        help="tales = Einzelgeschichten (Default, unveraendert); new-book = Buchrahmen "
                             "anlegen; append-chapter = naechstes Kapitel anhaengen; prolog = fehlenden "
                             "Prolog zu einem bestehenden Buch ergaenzen (book.json bleibt kanonisch).")
    parser.add_argument("--book-style", default=None,
                        help="Stil fuer den Buchmodus; Default ist ein zufaelliger Stil der Locale.")
    parser.add_argument("--book-title", default=None,
                        help="Titel fuer new-book; uebersteuert den Titel aus dem Modell.")
    parser.add_argument("--book-id", default=None,
                        help="Buch-ID fuer new-book/append-chapter; Default ist das neueste Buch (mtime).")
    parser.add_argument("--article", default=None)
    parser.add_argument("--style", default=None)
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--cooldown", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    if args.mode in ("new-book", "append-chapter", "prolog", "inject-chapter"):
        try:
            if args.mode == "new-book":
                book_id = new_book(lang=args.lang, style=args.book_style, model=args.model,
                                   host=host, backend=args.backend,
                                   book_id=args.book_id, titel=args.book_title)
                print(f"[Buchmodus] Buch angelegt: {os.path.join(BOOKS_DIR, book_id)}", flush=True)
            elif args.mode == "inject-chapter":
                if not args.book_id or not args.file:
                    raise RuntimeError("inject-chapter braucht --book-id und --file")
                pfad = inject_chapter(book_id=args.book_id, datei=args.file, artikel=args.article,
                                      fork_from=args.fork_from, lang=args.lang)
            elif args.mode == "prolog":
                if not args.book_id:
                    raise RuntimeError("--mode prolog braucht --book-id (book.json bleibt kanonisch)")
                pfad = prolog_schreiben(book_id=args.book_id, lang=args.lang, model=args.model,
                                        host=host, backend=args.backend)
                print(f"[Buchmodus] Prolog ergaenzt: {pfad}", flush=True)
            else:
                pfad = append_chapter(book_id=args.book_id, lang=args.lang, model=args.model,
                                      host=host, backend=args.backend, artikel=args.article)
                print(f"[Buchmodus] Kapitel angehaengt: {pfad}", flush=True)
                # Monitoring: ein Kapitel, das die Endschranke NICHT passiert hat, ist ein Fallback.
                # Ohne eigenen Exit-Code bleibt das in CI/Langfuse unsichtbar (Exit 1 = Abbruch ohne Datei).
                if "manual_ending_ok: false" in open(pfad, encoding="utf-8").read(400):
                    print("[Buchmodus] WARNUNG: Fallback-Kapitel (Endschranke nicht erfuellt) "
                          "— Exit-Code 2", flush=True)
                    sys.exit(2)
        except (ValueError, FileExistsError, FileNotFoundError, RuntimeError) as e:
            print(f"[Buchmodus] Abbruch: {e}", flush=True)
            sys.exit(1)
        sys.exit(0)

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
