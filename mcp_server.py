import json
from mcp.server.fastmcp import FastMCP
from generate_pipeline import (
    ARTIKEL, SPRACHEN, STILE,
    build_prompt, save_tale, query_backend
)

mcp = FastMCP("algorithmic-activism-engine", version="0.2.0")


@mcp.tool()
def list_matrix() -> dict:
    """Listet alle Dimensionen der Matrix auf (Artikel, Sprachen, Stile)."""
    return {
        "artikel": ARTIKEL,
        "sprachen": SPRACHEN,
        "stile": STILE
    }


@mcp.tool()
def get_prompt(article_key: str, language_code: str, style_key: str) -> str:
    """Gibt den hochpräzisen Harm-Reduction-Prompt für eine Matrix-Kombination zurück."""
    if article_key not in ARTIKEL:
        return f"Fehler: Unbekannter Artikel '{article_key}'. Gültig: {list(ARTIKEL.keys())}"
    if language_code not in SPRACHEN:
        return f"Fehler: Unbekannte Sprache '{language_code}'. Gültig: {list(SPRACHEN.keys())}"
    if style_key not in STILE:
        return f"Fehler: Unbekannter Stil '{style_key}'. Gültig: {list(STILE.keys())}"

    return build_prompt(ARTIKEL[article_key], SPRACHEN[language_code], STILE[style_key])


@mcp.tool()
def store_story(markdown_content: str, language_code: str, fallback_title: str = "Tale") -> str:
    """Extrahiert den # Titel aus der Story und speichert sie direkt im Zielordner ab."""
    if language_code not in SPRACHEN:
        return f"Fehler: Unbekannter Sprachcode '{language_code}'"
    saved_path = save_tale(markdown_content, language_code, fallback_title)
    return f"Erfolgreich abgelegt unter: {saved_path}"


@mcp.tool()
def generate_story_with_backend(
    article_key: str,
    language_code: str,
    style_key: str,
    backend: str = "ollama",
    model: str = None
) -> str:
    """Führt die Generierung über ein gewähltes Backend (ollama, gemini, openai) aus und speichert die Datei."""
    prompt = get_prompt(article_key, language_code, style_key)
    if prompt.startswith("Fehler:"):
        return prompt

    try:
        content = query_backend(backend, prompt, model=model)
        fallback = f"{article_key}_{style_key}"
        saved_path = save_tale(content, language_code, fallback)
        return f"Erfolgreich generiert via {backend} und gespeichert unter: {saved_path}"
    except Exception as e:
        return f"Fehler bei der Generierung: {str(e)}"


if __name__ == "__main__":
    mcp.run()
