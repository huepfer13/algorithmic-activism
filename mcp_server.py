#!/usr/bin/env python3
import glob
import json
import os
import signal
import subprocess
import sys
import config

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


# --- Tool Implementierungen ---

def tool_get_config_overview(arguments: dict) -> dict:
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


def tool_set_config_value(arguments: dict) -> dict:
    key = arguments.get("key", "")
    value = arguments.get("value", "")
    if not key:
        return {"error": "Parameter 'key' fehlt."}
    config.set_env_value(key, value)
    return {"message": f"Konfigurationswert '{key.upper()}' erfolgreich in .env aktualisiert."}


def tool_daemon_status(arguments: dict) -> dict:
    pid = _get_daemon_pid()
    running = pid is not None
    recent_log = ""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                recent_log = "".join(lines[-15:])
        except Exception as e:
            recent_log = f"Fehler beim Lesen des Logs: {e}"

    return {
        "status": "running" if running else "stopped",
        "pid": pid,
        "recent_log": recent_log
    }


def tool_daemon_start(arguments: dict) -> dict:
    pid = _get_daemon_pid()
    if pid is not None:
        return {"error": f"Daemon laeuft bereits mit PID {pid}."}

    backend = arguments.get("backend", "ollama")
    model = arguments.get("model", "qwen2.5:7b")
    lang = arguments.get("lang", "DE")
    cooldown = arguments.get("cooldown", 8)

    cmd = [
        sys.executable, "-u", os.path.join(BASE_DIR, "generate_pipeline.py"),
        "--backend", str(backend),
        "--model", str(model),
        "--lang", str(lang),
        "--random",
        "--daemon",
        "--cooldown", str(cooldown)
    ]

    log_fd = open(LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_fd, stderr=subprocess.STDOUT, cwd=BASE_DIR, start_new_session=True)

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    return {"message": "Daemon erfolgreich gestartet", "pid": proc.pid, "log_file": LOG_FILE}


def tool_daemon_stop(arguments: dict) -> dict:
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


def tool_get_corpus_stats(arguments: dict) -> dict:
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


def tool_read_latest_tale(arguments: dict) -> dict:
    lang = arguments.get("lang", "DE").upper()
    folder = os.path.join(TALES_DIR, lang)
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


# --- Tool Definitionen nach MCP Spezifikation ---

TOOLS = [
    {
        "name": "get_config_overview",
        "description": "Zeigt den Status konfigurierter Endpunkte und Keys an (Keys maskiert).",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_get_config_overview
    },
    {
        "name": "set_config_value",
        "description": "Setzt einen Konfigurationswert oder API-Key persistent in der .env-Datei.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Name der Variable, z.B. GEMINI_API_KEY"},
                "value": {"type": "string", "description": "Der zu setzende Wert"}
            },
            "required": ["key", "value"]
        },
        "handler": tool_set_config_value
    },
    {
        "name": "daemon_status",
        "description": "Prueft, ob der generative Synthese-Daemon laeuft und liefert die letzten Log-Zeilen.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_daemon_status
    },
    {
        "name": "daemon_start",
        "description": "Startet den unendlichen Synthese-Daemon mit automatischer Lastdrosselung im Hintergrund.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "backend": {"type": "string", "default": "ollama"},
                "model": {"type": "string", "default": "qwen2.5:7b"},
                "lang": {"type": "string", "default": "DE"},
                "cooldown": {"type": "integer", "default": 8}
            }
        },
        "handler": tool_daemon_start
    },
    {
        "name": "daemon_stop",
        "description": "Stoppt den laufenden Synthese-Daemon sauber.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_daemon_stop
    },
    {
        "name": "get_corpus_stats",
        "description": "Liefert Kennzahlen ueber alle bisher generierten Geschichten und kanonischen Artikel.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_get_corpus_stats
    },
    {
        "name": "read_latest_tale",
        "description": "Liest die zuletzt generierte Geschichte aus dem Korpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lang": {"type": "string", "default": "DE", "description": "Sprachcode (DE oder EN)"}
            }
        },
        "handler": tool_read_latest_tale
    }
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def send_response(response_dict: dict):
    line = json.dumps(response_dict)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        # MCP Notifications (haben keine id)
        if req_id is None:
            continue

        if method == "initialize":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "Algorithmic-Activism-Controller",
                        "version": "0.6.0"
                    }
                }
            })

        elif method == "tools/list":
            tools_manifest = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"]
                }
                for t in TOOLS
            ]
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_manifest}
            })

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            if tool_name not in TOOLS_BY_NAME:
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' nicht gefunden."}
                })
            else:
                try:
                    res_data = TOOLS_BY_NAME[tool_name]["handler"](tool_args)
                    send_response({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(res_data, indent=2, ensure_ascii=False)
                                }
                            ]
                        }
                    })
                except Exception as e:
                    send_response({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32000, "message": str(e)}
                    })

        elif method == "ping":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {}
            })

        else:
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Methode '{method}' nicht unterstuetzt."}
            })


if __name__ == "__main__":
    main()
