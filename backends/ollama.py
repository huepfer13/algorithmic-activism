import json
import urllib.request
import urllib.error
from backends.base import BackendPlugin

class OllamaPlugin(BackendPlugin):
    name = "ollama"
    requires_key = False

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host

    def get_installed_models(self) -> list[str]:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return [m.get("name") for m in data.get("models", []) if "name" in m]
        except Exception:
            pass
        return []

    def is_available(self) -> tuple[bool, str]:
        models = self.get_installed_models()
        if models:
            return True, f"Ollama aktiv ({len(models)} Modell(e) bereit, nutzt bevorzugt '{models[0]}')"
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return False, "Ollama läuft, aber keine Modelle installiert"
        except Exception:
            pass
        return False, f"Ollama nicht unter {self.host} erreichbar"

    def generate(self, prompt: str, model: str = None, on_token=None) -> str:
        models = self.get_installed_models()
        
        target_model = model
        if not target_model:
            preferred = ["qwen2.5:7b", "mistral:latest", "llama3.2:latest", "llama3:latest", "falcon3:latest"]
            for pref in preferred:
                if pref in models:
                    target_model = pref
                    break
            if not target_model and models:
                target_model = models[0]

        if not target_model:
            raise RuntimeError("Keine Modelle in lokaler Ollama-Instanz gefunden.")

        url = f"{self.host}/api/generate"
        payload = json.dumps({
            "model": target_model,
            "prompt": prompt,
            "stream": True
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        full_text = []

        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    full_text.append(token)
                    if on_token and token:
                        on_token(token)
                except Exception:
                    pass

        return "".join(full_text)
