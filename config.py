import os

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def load_env():
    """Lädt Variablen aus .env in os.environ, ohne bestehende Shell-Variablen zu überschreiben."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

def set_env_value(key: str, value: str):
    """Setzt oder aktualisiert einen Wert in .env und os.environ."""
    lines = []
    found = False
    key = key.strip().upper()
    value = value.strip()

    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            if k.strip() == key:
                new_lines.append(f"{key}={value}\n")
                found = True
                continue
        new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value

load_env()
