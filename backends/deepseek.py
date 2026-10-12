"""DeepSeek-Backend (OpenAI-kompatibler Endpunkt, https://api.deepseek.com/v1).

Schluessel-Aufloesung in dieser Reihenfolge:
1. Environment-Variable DEEPSEEK_API_KEY
2. ~/.hermes/.env (dieselbe Datei, aus der der Gateway seine Provider-Keys zieht)
3. sonst Abbruch

Der Wert wird NIE geloggt oder ausgegeben — nur Herkunft und Byte-Laenge.
"""
import json
import os
import re
import time
import urllib.request

from backends.base import BackendPlugin

ENV_DATEI = "~/.hermes/.env"


def schluessel_aus_env(datei: str, name: str) -> str | None:
    """Liest einen Schluessel aus dem Environment oder aus einer .env-Datei."""
    wert = os.environ.get(name)
    if wert:
        return wert.strip()
    pfad = os.path.expanduser(datei)
    if os.path.isfile(pfad):
        muster = re.compile(r"\s*(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.+)$")
        for zeile in open(pfad, encoding="utf-8", errors="replace"):
            treffer = muster.match(zeile)
            if treffer:
                return treffer.group(1).strip().strip('"').strip("'")
    return None


class DeepSeekPlugin(BackendPlugin):
    name = "deepseek"
    requires_key = True
    supports_json = True   # response_format json_object

    def __init__(self, base_url: str = "https://api.deepseek.com/v1"):
        self.base_url = base_url.rstrip("/")
        self.key = schluessel_aus_env(ENV_DATEI, "DEEPSEEK_API_KEY")

    def is_available(self) -> tuple[bool, str]:
        if self.key:
            return True, f"DEEPSEEK_API_KEY geladen ({len(self.key)} Byte)"
        return False, "DEEPSEEK_API_KEY weder im Environment noch in ~/.hermes/.env"

    def generate(self, prompt: str, model: str | None = None, details: dict | None = None,
                 json_mode: bool = False) -> str:
        if not self.key:
            raise RuntimeError("DeepSeek ohne Schluessel — kein stiller Ausweichpfad")
        ziel = model or "deepseek-chat"
        rumpf = {"model": ziel, "messages": [{"role": "user", "content": prompt}],
                 "stream": False, "temperature": 0.7}
        if json_mode:
            # DeepSeek verlangt fuer json_object zusaetzlich das Wort "json" im Prompt
            # (der Metadaten-Prompt tut das bereits).
            rumpf["response_format"] = {"type": "json_object"}
        anfrage = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(rumpf).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        start = time.monotonic()
        with urllib.request.urlopen(anfrage, timeout=600) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
        dauer = round(time.monotonic() - start, 1)
        if details is not None:
            # Echte API-Zahlen statt Wort-Proxies (Gegenstueck zu Ollamas eval_count).
            nutzung = daten.get("usage") or {}
            if nutzung.get("completion_tokens") is not None:
                details["tokens_generated"] = int(nutzung["completion_tokens"])
            if nutzung.get("prompt_tokens") is not None:
                details["tokens_prompt"] = int(nutzung["prompt_tokens"])
            details["duration_seconds"] = dauer
        wahl = daten.get("choices") or []
        if not wahl:
            raise RuntimeError(f"DeepSeek lieferte keine choices: {list(daten)[:5]}")
        text = (wahl[0].get("message") or {}).get("content") or ""
        if not text.strip():
            raise RuntimeError("DeepSeek lieferte leeren Text — Abbruch statt Leerkapitel")
        return text
