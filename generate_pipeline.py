import os
import re
from itertools import product

ARTIKEL = {
    "Art_3_Leben": "Artikel 3: Recht auf Leben, Freiheit und Sicherheit der Person.",
    "Art_1_Wuerde": "Artikel 1: Alle Menschen sind frei und gleich an Würde und Rechten geboren.",
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

OUTPUT_DIR = "menschenrechte_tales"


def setup_repository():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for lang_code in SPRACHEN.keys():
        os.makedirs(os.path.join(OUTPUT_DIR, lang_code), exist_ok=True)


def generate_prompt(artikel_text: str, sprache_name: str, stil_beschreibung: str) -> str:
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
    """Extrahiert den H1-Titel (# Titel) und macht daraus einen sauberen Dateinamen."""
    match = re.search(r"^#\s+(.+)$", markdown_text, flags=re.MULTILINE)
    if match:
        raw_title = match.group(1).strip()
        # Ersetze Sonderzeichen/Satzzeichen durch Unterstriche
        clean = re.sub(r"[^\w\s-]", "", raw_title)
        slug = re.sub(r"[\s-]+", "_", clean).strip("_")
        if slug:
            return slug[:80]
    return fallback_name


def save_story(markdown_text: str, lang_code: str, fallback_base: str):
    """Speichert eine Geschichte unter ihrem echten Titel im Sprachordner."""
    lang_dir = os.path.join(OUTPUT_DIR, lang_code)
    title_slug = slugify_title(markdown_text, fallback_base)
    filename = f"{title_slug}.md"
    filepath = os.path.join(lang_dir, filename)

    # Kollisionsschutz: Falls zwei verschiedene Geschichten denselben Titel tragen
    counter = 1
    while os.path.exists(filepath):
        # Wenn der Inhalt identisch ist, nichts tun
        with open(filepath, "r", encoding="utf-8") as f:
            if f.read().strip() == markdown_text.strip():
                return filepath
        filename = f"{title_slug}_{counter}.md"
        filepath = os.path.join(lang_dir, filename)
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    print(f"📖 Gespeichert: {filepath}")
    return filepath


if __name__ == "__main__":
    setup_repository()
    print("Pipeline bereit. Geschichten werden ab jetzt unter ihrem tatsächlichen Titel gespeichert.")
