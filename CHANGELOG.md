# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)
und dieses Projekt hält sich an [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Automatisierte CI/CD-Pipelines via GitHub Actions für periodische Matrix-Synthese.
- Erweiterung des Korpus um UN-Charta Artikel 5 (Verbot von Folter) und Artikel 12 (Privatsphäre).
- Anbindung zusätzlicher lokaler Runner (llama.cpp, text-generation-webui).

---

## [0.2.0] - 2026-10-09

### Added
- **Multi-Backend-Architektur** in `generate_pipeline.py`:
  - Lokale Inferenz via `ollama` (Zero-Cost / Offline).
  - Cloud-Inferenz via `gemini` (`gemini-2.5-flash`).
  - Universelle `openai`-kompatible API-Unterstützung (vLLM, LocalAI, LM-Studio).
  - `catalog-only` Modus für reine Prompt-Vorbereitung ohne Modellaufruf.
- **Git-Automation (`--git-push` & `--create-pr`)**: Automatisches Staging, Committen und Pushen neu erzeugter Erzählungen sowie automatische PR-Erstellung gegen Upstream.
- **FastMCP-Integration (`mcp_server.py`)**: Bereitstellung von MCP-Tools (`list_matrix`, `get_prompt`, `store_story`, `generate_story_with_backend`) für autonome KI-Agenten.
- **Agent Skill Spezifikation**: Definition des Skills `human-rights-tale-generator` für Agent-Frameworks.
- **Titel-Extraktion & Kollisionsschutz**: Geschichten werden automatisch nach ihrer H1-Überschrift (`# Titel`) benannt; Kollisionsschutz durch inkrementelle Suffixe.
- **Strukturierter Prompt-Katalog (`prompts/`)**: Dedizierter Ordner für standardisierte Prompt-Rezepte über alle 5 Sprachräume hinweg.

### Changed
- `README.md` grundlegend überarbeitet: Vollständige Dokumentation von CLI-Workflows, Multi-Backend-Parametern, MCP-Tools und Skill-Spezifikationen.
- Geschichten-Ablage entkoppelt: Keine leeren Platzhalter mehr im Korpus; in `menschenrechte_tales/` verbleiben ausschließlich fertige narrative Artefakte.

---

## [0.1.0] - 2026-10-09

### Added
- Initialer Release des Repositories `huepfer13/algorithmic-activism`.
- 4-Säulen-Manifest für Algorithmic Activism und Harm Reduction.
- 3D-Matrix-Pipeline (Artikel 1, 3, 19 × DE, EN, FR, ES, SW × Parabel, SciFi, Fabel, Essay).
- Erste kanonische Erzählungen im Korpus:
  - `Der_Resonanz_Tresor.md` (Art. 19 Meinung / SciFi-Dystopie, DE).
  - `Die_Unantastbarkeit_als_Schwerkraft.md` (Art. 1 Würde / Philosophischer Essay, DE).
