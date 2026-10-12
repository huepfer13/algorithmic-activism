# Algorithmic Activism

> **Live-Reader:** https://huepfer13.github.io/algorithmic-activism/  ·  **Dataset:** https://huggingface.co/datasets/hardtoneselector/algorithmic-activism-corpus
>
> [![Deploy Reader](https://github.com/huepfer13/algorithmic-activism/actions/workflows/pages.yml/badge.svg)](https://github.com/huepfer13/algorithmic-activism/actions/workflows/pages.yml) ![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg) ![Data: CC-BY 4.0](https://img.shields.io/badge/data-CC--BY%204.0-lightgrey.svg) ![HF Dataset](https://img.shields.io/badge/HuggingFace-dataset-yellow.svg)


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
├── menschenrechte_books/ # Fortlaufende Bände (book.json + Kapitel)
├── quarantine/           # Durch Audit abgelehnte Texte (DPO-Basis)
├── datasets/             # Datierte dataset.jsonl-Snapshots
├── config.py             # Zero-Dependency .env Loader & Setter
├── generate_pipeline.py  # Haupt-Pipeline mit Daemon, Lastwächter & Audit
├── export_dataset.py     # JSONL-Dataset Exporter
├── scripts/              # sync_corpus.sh (kontrollierter Batch-Push), build_books_index.py (Index/API)
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

## Bücher & Bände (serielle Pipeline)

Neben den Einzelgeschichten erzeugt die Pipeline **fortlaufende Bände**: ein Prolog friert Setting,
Figuren und Perspektive in `book.json` ein, jedes weitere Kapitel verhandelt einen noch unbehandelten
Artikel der UDHR im selben Rahmen — angeschlossen an das Vorgängerkapitel (Markov-Kette über Volltexte,
kein Summarizing-Zwischenschritt).

```bash
# Band anlegen (Prolog + book.json)
python3 generate_pipeline.py --mode new-book --lang DE --book-style Gerätehandbuch

# Nächstes Kapitel anhängen (ohne --book-id: jüngstes Buch nach mtime)
python3 generate_pipeline.py --mode append-chapter --lang DE
python3 generate_pipeline.py --mode append-chapter --lang DE --book-id buch_001_das_büro_der_unendlichkeit
```

**Mechanische Endschranke (`audit_manual_ending`):** Der Schlussabsatz muss einen harten Marker
(`Fehlercode`, `Wartung`, `Intervall`, `Diagnose`, `Prüfung`, `Protokoll`, `Abschnitt`) oder einen
Sicherheitsblock (`[GEFAHR]` / `[WARNUNG]` / `[HINWEIS]`) tragen; wörtliche Rede und Emotionsverben
sind ausgeschlossen. Es gibt bis zu drei Versuche, danach wird das Kapitel **mit Vermerk** geschrieben
(kein stiller Durchlauf, kein Totalverlust). Jedes Kapitel trägt im Frontmatter `manual_ending_ok`,
`manual_ending_attempts` und `manual_ending_note`; die CLI beendet einen Fallback mit **Exit-Code 2**
(Exit 1 = Abbruch ohne Datei).

**Index & Entwickler-Endpunkte** (deterministisch, atomar geschrieben):

```bash
python3 scripts/build_books_index.py
```

| Datei | Inhalt |
|---|---|
| `web/books.json` | Katalog aller Bände: Metadaten, Kapitel-Inhaltsverzeichnis, Wortzahlen, verhandelte Artikel, Audit-Flags |
| `web/api/random.json` | Beispielkapitel im Volltext — **statisch**: GitHub Pages würfelt nicht pro Anfrage |
| `web/api/ipsum.json` | Platzhaltertext aus dem Korpus für Layout-/Testzwecke |

Der Reader (`web/index.html`) hat dafür den Tab **[ Geschichten ] | [ Bücher & Bände ]** mit Kachel-Ansicht
(Genre-Badge, Fortschritt „*n* von 30 Artikeln verhandelt"), Inhaltsverzeichnis, Kapitel-Navigation und
Feedback-Leiste am Kapitelende: ▲/▼ werden **nur lokal** im Browser gespeichert, 🚩 *Melden* öffnet ein
vorausgefülltes GitHub-Issue mit Buch, Kapitelpfad und Audit-Status.

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
