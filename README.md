# Algorithmic Activism

Ein modulares, autonomes und sich selbst verifizierendes System zur kontinuierlichen Synthese ethischer Narrative auf Basis der Allgemeinen Erklärung der Menschenrechte (UDHR).

## Kernprinzipien

- **Zero-Dependency Core:** Ausführbar mit reinem Python 3.10+ ohne zwingende Drittbibliotheken.
- **Kanonischer Korpus (`articles/`):** Vollständige Entkopplung der UN-Originaltexte mit Provenienz-Metadaten und Revisionssicherheit (`sync_udhr.py`).
- **Harm Reduction Guardrail:** Organische Verankerung des Schutzes vor tödlichen Gefahrenquellen (Zero-Home-Storage) ohne wörtliche Floskeln oder aufgesetzte Moralschlüsse.
- **Autonomer Daemon:** Kontinuierliche Synthese mit dynamischer CPU-Lastüberwachung (`check_system_load`) und Cooldown-Schutz.
- **MCP-Orchestrierung:** Integrierter FastMCP-Server (`mcp_server.py`) zur Prozesssteuerung, Korpusanalyse und Konfigurationsverwaltung.

---

## Architektur

```text
├── articles/             # Kanonischer Korpus nach UN OHCHR (DE / EN)
├── backends/             # Plugin-System (offline, ollama, gemini)
├── locales/              # Sprach- & Stil-Definitionen (DE, EN)
├── menschenrechte_tales/ # Generierte Narrative mit UN-Provenienz-Header
├── config.py             # Zero-Dependency .env Loader & Setter
├── generate_pipeline.py  # Haupt-Pipeline mit Daemon & Lastwächter
├── mcp_server.py         # FastMCP Server für Agenten
└── sync_udhr.py          # Validierungs- & Verifikationstool
Konfiguration & API-Keys
Das System läuft im Offline- und lokalen Ollama-Betrieb komplett ohne API-Keys.

Option A: Manuell via .env
Bash
cp .env.example .env
Mögliche Variablen:

Ini, TOML
OLLAMA_HOST=http://localhost:11434
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
.env ist via .gitignore vor versehentlichen Commits geschützt.

Option B: Autonom via MCP-Server
Verbundene Agenten können Konfigurationen direkt über Tools anpassen:

get_config_overview(): Zeigt Endpunkte und maskierte Keys.

set_config_value(key="GEMINI_API_KEY", value="..."): Schreibt persistent in .env.

Nutzung (CLI)
1. Kanonischen Korpus prüfen
Bash
./sync_udhr.py
2. Verfügbare Backends und Stile anzeigen
Bash
python3 generate_pipeline.py --list-backends
python3 generate_pipeline.py --list-styles --lang DE
3. Gezielte oder zufällige Generierung
Bash
# Zufällige Kombination aus Artikel und Stil
python3 generate_pipeline.py --backend ollama --random --limit 1 --lang DE

# Spezifischer Artikel und Stil
python3 generate_pipeline.py --backend ollama --article art_12 --style Cyberpunk_Noir --lang DE
4. Autonomer Daemon (Hintergrunddienst mit Lastwächter)
Bash
nohup python3 -u generate_pipeline.py \
  --backend ollama \
  --random \
  --daemon \
  --cooldown 8 \
  --lang DE > daemon.log 2>&1 &
Überwacht Systemlast (loadavg vs. Kerne) und pausiert bei >85 % Last automatisch.

Live-Ausgabe verfolgen: tail -f daemon.log

Beenden: pkill -f "generate_pipeline.py.*--daemon"

MCP-Integration (Agenten)
Der MCP-Server (mcp_server.py) stellt folgende Tools bereit:

daemon_status() / daemon_start(...) / daemon_stop()

get_corpus_stats() / read_latest_tale(lang="DE")

get_config_overview() / set_config_value(key, value)

Einbindung in MCP-Clients (z. B. Claude Desktop / Agent Config)
JSON
{
  "mcpServers": {
    "algorithmic-activism": {
      "command": "python3",
      "args": ["/path/to/algorithmic-activism/mcp_server.py"]
    }
  }
}

---

## Dataset — maschinenlesbarer Korpus

Der Korpus ist als **JSONL** exportierbar (Alpaca-/HuggingFace-kompatibel):

```bash
python3 export_dataset.py        # schreibt dataset.jsonl (ein JSON-Objekt pro Zeile)
```

Jeder Eintrag traegt `instruction`, `input` (Artikel-ID), `output` (Erzaehltext) und `meta`
(vollstaendiges YAML-Frontmatter: `article`, `style`, `language`, `model`, `created_at`,
`approx_words`, `guardrail_audit`).

* **Reproduzierbar & lizenzfrei:** Die Texte entstehen synthetisch aus dem gemeinfreien
  UN-Korpus (`articles/`) — keine urheberrechtlich geschuetzten Werke, keine Fremdtexte.
* **Snapshot im Repo:** `datasets/` enthaelt datierte Exporte (z. B.
  `datasets/corpus-2026-10-09.jsonl`) fuer alle, die keinen laufenden Daemon haben.
* **Pruefstatus je Zeile:** `guardrail_audit.passed` macht den Zustand maschinell filterbar.
* Wichtig und ehrlich: der Harm-Reduction-Audit laeuft **heuristisch** (Musterliste +
  Mindestlaenge). Er ist ein Filter, kein Beweis — bitte beim Weiterverwenden nachpruefen.

## Fuer KI-Forschung & Compute-Sponsoren

Dieses Projekt erzeugt **synthetische, wertebasierte Erzaehltexte** aus den Allgemeinen
Erklaerung der Menschenrechte — als offener Datensatz fuer Alignment-, Constitutional-AI-
und SFT-Experimente.

* **Was hier interessant ist:** ein wachsender Korpus kurzer Erzaehlungen mit
  Artikel-/Stil-/Sprach-Attribution und dokumentiertem Pruefergebnis, erzeugt von einem
  lokalen Modell (Ollama, Default `qwen2.5:7b`) in einer nachvollziehbaren Pipeline
  (`generate_pipeline.py`) — inklusive Nachweis, welche Anfrage zu welchem Text fuehrte.
* **Preference-Daten (DPO/RLHF):** abgelehnte Texte wandern nach `quarantine/` statt in den
  Korpus. Sobald dort Eintraege liegen, laesst sich daraus ein *chosen/rejected*-Paar bauen
  (chosen = `guardrail_audit.passed: true`, rejected = Quarantaene-Eintrag). **Stand jetzt:
  keine verworfenen Texte** — der Rejected-Ast ist also vorhanden, aber noch leer; wir
  behaupten hier keine Praeferenzdaten, die es noch nicht gibt.
* **Hugging-Face-Spiegelung:** vorgesehen/auf Anfrage (kein automatischer Upload).
* **Compute-Sponsoring:** GPU-/API-Credits (Ollama endpunkt, vLLM-Node oder Token-Kontingent)
  erweitern die Stichprobe pro Zeiteinheit direkt. Interessierte Anbieter: Kontakt ueber die
  Issues des Repositories.
* **Lizenzierung:** Code und Korpus sind zur Nachnutzung veroeffentlicht; die formale Lizenz
  (Vorschlag: MIT fuer Code, CC-BY 4.0 fuer die Daten) wird derzeit vom Autor festgelegt.
  Bis dahin gilt: Nutzung fuer Forschung/Zitat ist ausdruecklich gewollt, bitte Quelle nennen.
