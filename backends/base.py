class BackendPlugin:
    name: str = "base"
    requires_key: bool = False

    def is_available(self) -> tuple[bool, str]:
        return True, "Bereit"

    def generate(self, prompt: str, model: str = None) -> str:
        raise NotImplementedError
