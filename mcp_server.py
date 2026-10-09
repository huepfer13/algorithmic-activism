import glob
import json
import os
import signal
import subprocess
import sys
from fastmcp import FastMCP
import config

mcp = FastMCP("Algorithmic-Activism-Controller")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "daemon.log")
PID_FILE = os.path.join(BASE_DIR, "daemon.pid")
TALES_DIR = os.path.join(BASE_DIR, "menschenrechte_tales")


def _get_daemon_pid() -> int | None:
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            return None
    return None


@mcp.tool()
def get_config_overview() -> dict:
    """Zeigt den Status konfigurierter Endpunkte und Keys an (Keys werden maskiert)."""
    tracked_keys = ["OLLAMA_HOST", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    overview = {}
    for k in tracked_keys:
        val = os.getenv(k, "")
        if not val:
            overview[k] = "nicht gesetzt"
        elif k.endswith("_HOST"):
            overview[k] = val
        else:
            overview[k] = f"{val[:4]}...{val[-4:]}" if len(val) > 8 else "gesetzt"
    return overview


@mcp.tool()
def set_config_value(key: str, value: str) -> dict:
    """Setzt einen Konfigurationswert oder API-Key persistent in der .env-Datei."""
    config.set_env_value(key, value)
    return {"message": f"Konfigurationswert '{key.upper()}' erfolgreich aktualisiert."}


@mcp.tool()
def daemon_status() -> dict:
    """Prüft, ob der generative Synthese-Daemon aktuell im Hintergrund läuft."""
    pid = _get_daemon_pid()
    running = pid is not None
    recent_log = ""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            recent_log = "".join(lines[-15:])

    return {
        "status": "running" if running else "stopped",
        "pid": pid,
        "recent_log": recent_log
    }


@mcp.tool()
def daemon_start(backend: str = "ollama", model: str = "qwen2.5:7b", lang: str = "DE", cooldown: int = 8) -> dict:
    """Startet den unendlichen Synthese-Daemon mit automatischer Lastdrosselung im Hintergrund."""
    pid = _get_daemon_pid()
    if pid is not None:
        return {"error": f"Daemon läuft bereits mit PID {pid}."}

    cmd = [
        sys.executable, "-u", os.path.join(BASE_DIR, "generate_pipeline.py"),
        "--backend", backend,
        "--model", model,
        "--lang", lang,
        "--random",
        "--daemon",
        "--cooldown", str(cooldown)
    ]

    log_fd = open(LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_fd, stderr=subprocess.STDOUT, cwd=BASE_DIR, start_new_session=True)

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    return {"message": "Daemon erfolgreich gestartet", "pid": proc.pid, "log_file": LOG_FILE}


@mcp.tool()
def daemon_stop() -> dict:
    """Stoppt den laufenden Synthese-Daemon sauber."""
    pid = _get_daemon_pid()
    if pid is None:
        return {"message": "Kein aktiver Daemon gefunden."}

    try:
        os.kill(pid, signal.SIGTERM)
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return {"message": f"Daemon (PID {pid}) wurde beendet."}
    except OSError as e:
        return {"error": f"Fehler beim Beenden von PID {pid}: {e}"}


@mcp.tool()
def get_corpus_stats() -> dict:
    """Liefert Kennzahlen über alle bisher generierten Geschichten und kanonischen Artikel."""
    stats = {}
    total = 0

    for lang in ["DE", "EN"]:
        folder = os.path.join(TALES_DIR, lang)
        files = glob.glob(os.path.join(folder, "*.md")) if os.path.exists(folder) else []
        stats[lang] = len(files)
        total += len(files)

    return {
        "total_tales": total,
        "by_language": stats,
        "canonical_articles_available": len(glob.glob(os.path.join(BASE_DIR, "articles", "**", "*.md")))
    }


@mcp.tool()
def read_latest_tale(lang: str = "DE") -> dict:
    """Liest die zuletzt generierte Geschichte aus dem Korpus."""
    folder = os.path.join(TALES_DIR, lang.upper())
    files = glob.glob(os.path.join(folder, "*.md"))
    if not files:
        return {"error": f"Keine Geschichten unter {lang} gefunden."}

    latest_file = max(files, key=os.path.getmtime)
    with open(latest_file, "r", encoding="utf-8") as f:
        content = f.read()

    return {
        "filename": os.path.basename(latest_file),
        "content": content
    }


if __name__ == "__main__":
    mcp.run()
