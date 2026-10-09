import json
import urllib.request
from backends.base import BackendPlugin

class OllamaPlugin(BackendPlugin):
    name = "ollama"
    requires_key = False

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host

    def is_available(self) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True, f"Ollama erreichbar unter {self.host}"
        except Exception:
            pass
        return False, f"Ollama nicht unter {self.host} erreichbar (Starte: 'ollama serve')"

    def generate(self, prompt: str, model: str = None) -> str:
        target_model = model or "llama3.1"
        url = f"{self.host}/api/generate"
        payload = json.dumps({"model": target_model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
