import os
import hashlib
import time
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
PLACEHOLDER_MARKER = "[Warten auf API-Einspeisung"


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


def resolve_target_filepath(directory: str, base_name: str) -> str:
    """
    Sichert bestehende Arbeiten ab:
    - Wenn Datei nicht existiert: Standardpfad nutzen.
    - Wenn Datei existiert und noch ein Template ist: Standardpfad überschreiben/nutzen.
    - Wenn Datei existiert und bereits eine fertige Story enthält: Eindeutige Variante mit Hash anlegen.
    """
    primary_path = os.path.join(directory, f"{base_name}.md")
    
    if not os.path.exists(primary_path):
        return primary_path

    try:
        with open(primary_path, "r", encoding="utf-8") as f:
            content = f.read()
            if PLACEHOLDER_MARKER in content:
                return primary_path
    except OSError:
        pass

    # Datei enthält bereits fertige Story -> Neue Variante erzeugen
    unique_seed = f"{base_name}_{time.time_ns()}"
    nonce = hashlib.sha256(unique_seed.encode("utf-8")).hexdigest()[:6]
    variant_name = f"{base_name}_var_{nonce}.md"
    return os.path.join(directory, variant_name)


def run_pipeline():
    setup_repository()
    kombinationen = list(product(ARTIKEL.keys(), SPRACHEN.keys(), STILE.keys()))
    print(f"🚀 Starte Pipeline. Prüfe/Generiere Matrix aus {len(kombinationen)} Kombinationen...")

    created_count = 0
    skipped_count = 0

    for art_key, lang_code, stil_key in kombinationen:
        artikel_text = ARTIKEL[art_key]
        sprache_name = SPRACHEN[lang_code]
        stil_beschreibung = STILE[stil_key]

        base_name = f"{art_key}_{stil_key}"
        lang_dir = os.path.join(OUTPUT_DIR, lang_code)
        filepath = resolve_target_filepath(lang_dir, base_name)

        # Wenn der ermittelte Pfad bereits existiert und kein Template mehr ist, überspringen
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                if PLACEHOLDER_MARKER not in f.read():
                    skipped_count += 1
                    continue

        prompt_text = generate_prompt(artikel_text, sprache_name, stil_beschreibung)
        title_art = art_key.replace('_', ' ')
        title_stil = stil_key.replace('_', ' ')

        markdown_content = (
            f"# {title_art} - {title_stil} ({lang_code})\n\n"
            "*Dieses Dokument wurde automatisch von der Algorithmic-Activism-Pipeline vorbereitet.*\n\n"
            "## Generierungs-Prompt:\n"
            "```text\n"
            f"{prompt_text}\n"
            "```\n\n"
            "## Status:\n"
            f"{PLACEHOLDER_MARKER}. Der Text wird hier nach dem nächsten Lauf im Folgemodell verankert.]\n"
        )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        created_count += 1

    print(f"✅ Pipeline abgeschlossen. {created_count} Vorlagen synchronisiert/angelegt, {skipped_count} bestehende Geschichten geschützt.")


if __name__ == "__main__":
    run_pipeline()
