"""OpenAI-kompatible Backends unter einem Dach: DeepSeek, OpenRouter (Free-Tier), Nous, DeepInfra.

Ein Client, mehrere Profile: base_url + Schluesselvariable + Default-Modell. Der Client spricht
das OpenAI-Chat-Protokoll (`/chat/completions`), das alle vier Anbieter bedienen.

Schluessel-Aufloesung: Environment zuerst, dann ~/.hermes/.env (dieselbe Quelle wie der Gateway).
Der Wert wird NIE geloggt oder ausgegeben — nur Herkunft und Byte-Laenge.

Aufgenommen sind nur Anbieter, deren Endpunkt gemessen wurde (deepseek, openrouter). Weitere
Profile kommen erst dazu, wenn ihre Erreichbarkeit belegt ist — kein geratener base_url.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

from backends.base import BackendPlugin

ENV_DATEI = "~/.hermes/.env"

PROVIDER = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "key_var": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_var": "OPENROUTER_API_KEY",
        # Gemessen 2026-10-12: 15 kostenlose Slugs, alle text->text. Dies ist der groesste
        # verfuegbare freie Endpunkt (262144 Kontext). Weitere: nemotron-3-ultra-550b-a55b:free,
        # thinkingmachines/inkling:free, google/gemma-4-31b-it:free.
        "default_model": "nvidia/nemotron-3-super-120b-a12b:free",
    },
}


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


class OpenAICompatPlugin(BackendPlugin):
    """Ein Plugin je Anbieterprofil — gleicher Code, andere base_url und Schluessel."""

    requires_key = True
    supports_json = True   # response_format json_object

    def __init__(self, provider: str = "openrouter", base_url: str | None = None,
                 key_var: str | None = None):
        if provider not in PROVIDER:
            raise RuntimeError(f"unbekannter OpenAI-kompatibler Anbieter '{provider}' — "
                               f"bekannt: {sorted(PROVIDER)}")
        profil = PROVIDER[provider]
        self.name = provider
        self.base_url = (base_url or profil["base_url"]).rstrip("/")
        self.key_var = key_var or profil["key_var"]
        self.default_model = profil["default_model"]
        self.key = schluessel_aus_env(ENV_DATEI, self.key_var)

    def is_available(self) -> tuple[bool, str]:
        if self.key:
            return True, f"{self.key_var} geladen ({len(self.key)} Byte, {self.name})"
        return False, f"{self.key_var} weder im Environment noch in {ENV_DATEI}"

    def generate(self, prompt: str, model: str | None = None, details: dict | None = None,
                 json_mode: bool = False) -> str:
        if not self.key:
            raise RuntimeError(f"{self.name} ohne Schluessel — kein stiller Ausweichpfad")
        ziel = model or self.default_model
        rumpf = {"model": ziel, "messages": [{"role": "user", "content": prompt}],
                 "stream": False, "temperature": 0.7}
        if json_mode:
            rumpf["response_format"] = {"type": "json_object"}
        kopf = {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"}
        if self.name == "openrouter":
            # OpenRouter empfiehlt diese beiden Kopfzeilen zur Zuordnung; ohne sie funktioniert es
            # ebenfalls, aber die Ratenzuordnung des Anbieters bleibt unscharf.
            kopf["HTTP-Referer"] = "https://github.com/huepfer13/algorithmic-activism"
            kopf["X-Title"] = "algorithmic-activism"
        anfrage = urllib.request.Request(f"{self.base_url}/chat/completions",
                                         data=json.dumps(rumpf).encode("utf-8"), headers=kopf)
        start = time.monotonic()
        try:
            with urllib.request.urlopen(anfrage, timeout=600) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Fehlertext des Anbieters durchreichen (Rate-Limit 429, Modell offline 404 ...) —
            # ein stiller Retry hier wuerde die Ursache verstecken.
            text = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{self.name} HTTP {e.code}: {text}") from None
        dauer = round(time.monotonic() - start, 1)
        if "error" in daten:
            raise RuntimeError(f"{self.name} meldet Fehler: {str(daten['error'])[:200]}")
        if details is not None:
            nutzung = daten.get("usage") or {}
            if nutzung.get("completion_tokens") is not None:
                details["tokens_generated"] = int(nutzung["completion_tokens"])
            if nutzung.get("prompt_tokens") is not None:
                details["tokens_prompt"] = int(nutzung["prompt_tokens"])
            details["duration_seconds"] = dauer
        wahl = daten.get("choices") or []
        if not wahl:
            raise RuntimeError(f"{self.name} lieferte keine choices: {list(daten)[:5]}")
        text = (wahl[0].get("message") or {}).get("content") or ""
        if not text.strip():
            raise RuntimeError(f"{self.name} lieferte leeren Text — Abbruch statt Leerkapitel")
        return text


class DeepSeekPlugin(OpenAICompatPlugin):
    """Bestandsname: der DeepSeek-Adapter ist ein Profil des allgemeinen Clients."""

    def __init__(self, base_url: str = "https://api.deepseek.com/v1"):
        super().__init__("deepseek", base_url=base_url)
