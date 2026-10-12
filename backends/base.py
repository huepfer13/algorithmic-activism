class BackendPlugin:
    name: str = "base"
    requires_key: bool = False

    def is_available(self) -> tuple[bool, str]:
        return True, "Bereit"

    # details: optionale Metrik-Senke (tokens_generated, duration_seconds ...). Plugins, die keine
    # echten Zahlen liefern, ignorieren sie — der Dispatcher fuellt dann nichts Erfundenes ein.
    # json_mode: erzwungenes JSON (response_format). Nur Plugins mit supports_json=True.
    supports_json = False

    def generate(self, prompt: str, model: str = None, details: dict | None = None,
                 json_mode: bool = False) -> str:
        raise NotImplementedError
