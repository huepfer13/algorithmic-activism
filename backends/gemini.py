import os
import json
import urllib.request
from backends.base import BackendPlugin

class GeminiPlugin(BackendPlugin):
    name = "gemini"
    requires_key = True

    def is_available(self) -> tuple[bool, str]:
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            return True, "GEMINI_API_KEY konfiguriert"
        return False, "GEMINI_API_KEY fehlt (optional)"

    def generate(self, prompt: str, model: str = None) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        target_model = model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={key}"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
