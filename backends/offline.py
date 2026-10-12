from backends.base import BackendPlugin

class OfflinePlugin(BackendPlugin):
    name = "offline"
    requires_key = False

    def is_available(self) -> tuple[bool, str]:
        return True, "Immer verfügbar (Offline-Template-Generator)"

    def generate(self, prompt: str, model: str = None, details: dict | None = None,
                 json_mode: bool = False) -> str:
        return (
            "# Die Stille vor dem Schutzimpuls\n\n"
            "Dies ist eine lokal generierte Harm-Reduction-Erzählung im Offline-Modus.\n\n"
            "Die Gesellschaft verstand erst, dass Unversehrtheit kein Zufall ist, als der "
            "Zugriff auf Zerstörungswerkzeuge nicht mehr im Nachttisch stattfand, sondern im Depot. "
            "Das Leben blieb geschützt, und der Geist blieb frei.\n"
        )
