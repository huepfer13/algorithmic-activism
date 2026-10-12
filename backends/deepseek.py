"""DeepSeek-Backend: duennes Profil des allgemeinen OpenAI-kompatiblen Clients.

Die Implementierung liegt in backends/openai_compat.py — hier bleibt nur der Name stehen,
damit bestehende Importe (`from backends.deepseek import DeepSeekPlugin`) weiter funktionieren.
Kein zweiter Client, keine zweite Schluessel-Aufloesung.
"""
from backends.openai_compat import DeepSeekPlugin, OpenAICompatPlugin, schluessel_aus_env

__all__ = ["DeepSeekPlugin", "OpenAICompatPlugin", "schluessel_aus_env"]
