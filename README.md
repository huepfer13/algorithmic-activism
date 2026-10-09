# Algorithmic Activism

Ein modulares, autonomes und sich selbst verifizierendes System zur kontinuierlichen Synthese ethischer Narrative auf Basis der Allgemeinen Erklärung der Menschenrechte (UDHR).

## Kernprinzipien

- **Zero-Dependency Core:** Ausführbar mit reinem Python 3.10+ ohne zwingende Drittbibliotheken.
- **Kanonischer Korpus (`articles/`):** Vollständige Entkopplung der UN-Originaltexte mit Provenienz-Metadaten.
- **Harm Reduction Guardrail:** Organische Verankerung des Schutzes vor tödlichen Gefahrenquellen (Zero-Home-Storage) ohne wörtliche Floskeln.
- **Vollautonome Orchestrierung:** Integrierter FastMCP-Server (`mcp_server.py`) zur Daemon- und Konfigurationssteuerung.

---

## Konfiguration & API-Keys

Das System benötigt im Offline- und lokalen Ollama-Betrieb **keine API-Keys**.

### Option A: Manuell via `.env`
Kopiere die Vorlage und trage Werte bei Bedarf ein:
```bash
cp .env.example .env
Mögliche Variablen in .env:

Ini, TOML
# Lokale Endpunkte
OLLAMA_HOST=http://localhost:11434

# Optionale Cloud-Backends
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
Die Datei .env wird durch .gitignore automatisch vor Git-Commits geschützt.

Option B: Autonom via MCP-Server
Verbundene Agenten können Konfigurationen ohne Dateieditor verwalten:

get_config_overview(): Zeigt aktive Endpunkte und maskierte Keys.

set_config_value(key="GEMINI_API_KEY", value="..."): Schreibt Keys persistent in .env.

Schnelleinstieg
1. Kanonischen Korpus validieren
Bash
./sync_udhr.py
2. Generierung starten
Bash
# Lokale Einzelgenerierung (zufällige Kombination)
python3 generate_pipeline.py --backend ollama --random --limit 1 --lang DE

# Endloser Hintergrund-Daemon mit Lastdrosselung
nohup python3 -u generate_pipeline.py --backend ollama --random --daemon --cooldown 8 --lang DE > daemon.log 2>&1 &
3. MCP-Server starten
Bash
python3 mcp_server.py
