# Algorithmic Activism

Ein modulares, autonomes und sich selbst verifizierendes System zur kontinuierlichen Synthese ethischer Narrative auf Basis der Allgemeinen Erklärung der Menschenrechte (UDHR).

## Kernprinzipien

- **Zero-Dependency Core:** Ausführbar mit reinem Python 3.10+ ohne zwingende Drittbibliotheken.
- **Kanonischer Korpus (`articles/`):** Vollständige Entkopplung der UN-Originaltexte mit Provenienz-Metadaten und Revisionssicherheit (`sync_udhr.py`).
- **Harm Reduction Guardrail:** Organische Verankerung des Schutzes vor tödlichen Gefahrenquellen (Zero-Home-Storage) ohne wörtliche Floskeln oder aufgesetzte Moralschlüsse.
- **Autonomer Daemon:** Kontinuierliche Synthese mit dynamischer CPU-Lastüberwachung (`check_system_load`) und Cooldown-Schutz.
- **MCP-Orchestrierung:** Integrierter Zero-Dependency JSON-RPC MCP Server (`mcp_server.py`) zur Prozesssteuerung und Korpusanalyse durch autonome Agenten.

---

## Für AI-Forscher, Entwickler & Compute-Sponsoren

Dieses Repository generiert einen **qualitativ kuratierten, synthetischen Datensatz** für Alignment, Constitutional AI und Fine-Tuning:

- **Ethisches Grounding:** Jedes Narrativ ist strikt an einen kanonischen UN-Artikel gekoppelt und durchläuft ein harm-reduction Audit.
- **Provenienz je Dokument:** striktes YAML-Frontmatter mit `article`, `style`, `language`, `model`, `created_at`, `approx_words` und `guardrail_audit` (passed/status) — maschinell filterbar.
- **DPO / RLHF:** abgelehnte Texte wandern nach `quarantine/` statt in den Korpus (chosen = `guardrail_audit.passed: true`, rejected = Quarantäne-Eintrag). **Ehrlich dazu:** der Rejected-Ast ist implementiert, aber derzeit **leer** (0 verworfene Texte) — es werden hier keine Präferenzpaare behauptet, die es noch nicht gibt. Mit dem Harm-Reduction-Audit als heuristischem Filter ist das ein wachsender, kein fertiger Bestand.
- **Dataset Export:** Export in standardisiertes JSONL (Alpaca / Hugging-Face-Format) ohne Abhängigkeiten:

  ```bash
  python3 export_dataset.py        # schreibt dataset.jsonl (ein JSON-Objekt pro Zeile)
  ```

  Felder je Zeile: `instruction`, `input` (Artikel-ID), `output` (Erzähltext), `meta` (vollständiges Frontmatter).
- **Snapshot im Repo:** `datasets/` enthält datierte Exporte (z. B. `datasets/corpus-2026-10-09.jsonl`) für alle, die keinen laufenden Daemon haben.
- **Lizenzierung:** Code unter **MIT** (siehe `LICENSE`), die generierten Texte und der Korpus unter **CC-BY 4.0** (siehe `datasets/LICENSE`) - Namensnennung genuegt, kommerzielle Nutzung (auch Modelltraining/Fine-Tuning) ausdruecklich erlaubt.

### 🤝 Call for Compute & Sponsorship

Um den Korpus über alle 30 UN-Artikel, mehrere Sprachräume und Erzählstile hinweg im größeren Maßstab zu synthetisieren, sind Rechenzeit- und API-Beiträge willkommen:

- **Lokale / dezentrale Nodes:** Betreiber von vLLM- oder Ollama-Endpunkten.
- **Cloud Grants / Tokens:** Inferenz-Kapazitäten (Gemini, Claude, OpenAI oder Open-Weight-Inferenz).
- **Kontakt:** Issues oder PRs im Repository.

---

## Architektur

```text
├── articles/             # Kanonischer Korpus nach UN OHCHR (DE / EN)
├── backends/             # Plugin-System (offline, ollama, gemini)
├── locales/              # Sprach- & Stil-Definitionen (DE, EN)
├── menschenrechte_tales/ # Validierte Narrative mit YAML-Frontmatter
├── quarantine/           # Durch Audit abgelehnte Texte (DPO-Basis)
├── datasets/             # Datierte dataset.jsonl-Snapshots
├── config.py             # Zero-Dependency .env Loader & Setter
├── generate_pipeline.py  # Haupt-Pipeline mit Daemon, Lastwächter & Audit
├── export_dataset.py     # JSONL-Dataset Exporter
├── mcp_server.py         # Zero-Dependency MCP Server für Agenten
└── sync_udhr.py          # Validierungs- & Verifikationstool
```

## Nutzung (CLI)

1. Kanonischen Korpus prüfen

   ```bash
   python3 sync_udhr.py
   ```

2. Gezielte oder zufällige Generierung

   ```bash
   # Zufällige Kombination aus Artikel und Stil
   python3 generate_pipeline.py --backend ollama --random --limit 1 --lang DE

   # Spezifischer Artikel und Stil
   python3 generate_pipeline.py --backend ollama --article art_12 --style Cyberpunk_Noir --lang DE
   ```

3. Autonomer Daemon (Hintergrunddienst mit Lastwächter)

   ```bash
   nohup python3 -u generate_pipeline.py \
     --backend ollama \
     --random \
     --daemon \
     --cooldown 8 \
     --lang DE > daemon.log 2>&1 &
   ```

## MCP-Integration (Agenten)

Der Server implementiert die JSON-RPC 2.0 MCP-Spezifikation rein über die Standardbibliothek (kein pip, kein venv erforderlich) mit den Werkzeugen `daemon_status`, `daemon_start`, `daemon_stop`, `get_corpus_stats`, `read_latest_tale`, `get_config_overview`, `set_config_value`.

```json
{
  "mcpServers": {
    "algorithmic-activism": {
      "command": "python3",
      "args": ["/path/to/algorithmic-activism/mcp_server.py"]
    }
  }
}
```
