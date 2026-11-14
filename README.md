# Algorithmic Activism

> **Live reader:** https://huepfer13.github.io/algorithmic-activism/  ·  **Dataset:** https://huggingface.co/datasets/hardtoneselector/algorithmic-activism-corpus
>
> [![Deploy Reader](https://github.com/huepfer13/algorithmic-activism/actions/workflows/pages.yml/badge.svg)](https://github.com/huepfer13/algorithmic-activism/actions/workflows/pages.yml) ![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg) ![Data: CC-BY 4.0](https://img.shields.io/badge/data-CC--BY%204.0-lightgrey.svg) ![HF Dataset](https://img.shields.io/badge/HuggingFace-dataset-yellow.svg)
>
> **Languages:** English (this file) · [Deutsch](README.de.md)

A modular, autonomous, self-verifying system for the continuous synthesis of ethical narratives grounded in the Universal Declaration of Human Rights (UDHR).

## Core principles

- **Zero-dependency core:** runs on plain Python 3.10+ with no mandatory third-party packages.
- **Canonical corpus (`articles/`):** UN source texts fully decoupled from generation, with provenance metadata and revision safety (`sync_udhr.py`).
- **Harm-reduction guardrail:** protection against lethal hazards is embedded organically (zero home storage) — no boilerplate phrases, no appended moral conclusions.
- **Autonomous daemon:** continuous synthesis with live CPU load monitoring (`check_system_load`) and cooldown protection.
- **MCP orchestration:** a built-in zero-dependency JSON-RPC MCP server (`mcp_server.py`) for process control and corpus analysis by autonomous agents.

---

## For AI researchers, developers and compute sponsors

This repository generates a **curated synthetic dataset** for alignment, constitutional AI and fine-tuning:

- **Ethical grounding:** every narrative is strictly bound to one canonical UN article and passes a harm-reduction audit.
- **Per-document provenance:** strict YAML front matter with `article`, `style`, `language`, `model`, `created_at`, `approx_words` and `guardrail_audit` (passed/status) — machine filterable.
- **DPO / RLHF:** rejected texts go to `quarantine/` instead of the corpus (chosen = `guardrail_audit.passed: true`, rejected = quarantine entry). **Stated honestly:** the rejected branch is implemented but currently **empty** (0 rejected texts) — no preference pairs are claimed that do not exist yet. With the harm-reduction audit as a heuristic filter this is a growing, not a finished, asset.
- **Dataset export:** export to standardised JSONL (Alpaca / Hugging Face format) without dependencies:

  ```bash
  python3 export_dataset.py        # writes dataset.jsonl (one JSON object per line)
  ```

  Fields per line: `instruction`, `input` (article ID), `output` (narrative text), `meta` (full front matter).
- **Snapshots in the repo:** `datasets/` holds dated exports (e.g. `datasets/corpus-2026-10-09.jsonl`) for anyone without a running daemon.
- **Licensing:** code under **MIT** (see `LICENSE`), generated texts and the corpus under **CC-BY 4.0** (see `datasets/LICENSE`) — attribution is sufficient, commercial use (including model training and fine-tuning) is explicitly permitted.

### 🤝 Call for compute & sponsorship

Synthesising the corpus across all 30 UN articles, several language spaces and narrative styles at scale requires compute and API contributions:

- **Local / decentralised nodes:** operators of vLLM or Ollama endpoints.
- **Cloud grants / tokens:** inference capacity (Gemini, Claude, OpenAI or open-weight inference).
- **Contact:** issues or pull requests in this repository.

---

## Architecture

```text
├── articles/             # Canonical corpus per UN OHCHR (de 30 · fr 30 · sw 30 · en 9)
├── backends/             # Plugin system (offline, ollama, gemini, deepseek, openai-compatible)
├── locales/              # Language & style definitions (13 locales)
├── menschenrechte_tales/ # Validated narratives with YAML front matter
├── menschenrechte_books/ # Serial volumes (book.json + chapters)
├── quarantine/           # Texts rejected by the audit (DPO base)
├── datasets/             # Dated dataset.jsonl snapshots
├── config.py             # Zero-dependency .env loader & setter
├── generate_pipeline.py  # Main pipeline with daemon, load watchdog & audit
├── export_dataset.py     # JSONL dataset exporter
├── scripts/              # run_model_rotation.py (hourly rotation), seed_matrix.py (language×genre seeds),
│                         # build_books_index.py (index/API), sync_corpus.sh (controlled batch push)
├── mcp_server.py         # Zero-dependency MCP server for agents
└── sync_udhr.py          # Validation & verification tool
```

## Usage (CLI)

1. Verify the canonical corpus

   ```bash
   python3 sync_udhr.py
   ```

2. Targeted or random generation

   ```bash
   # Random article/style combination
   python3 generate_pipeline.py --backend ollama --random --limit 1 --lang DE

   # Specific article and style
   python3 generate_pipeline.py --backend ollama --article art_12 --style Cyberpunk_Noir --lang DE
   ```

3. Autonomous daemon (background service with load watchdog)

   ```bash
   nohup python3 -u generate_pipeline.py \
     --backend ollama \
     --random \
     --daemon \
     --cooldown 8 \
     --lang DE > daemon.log 2>&1 &
   ```

## Books & volumes (serial pipeline)

Alongside single stories the pipeline produces **serial volumes**: a prologue freezes setting,
characters and point of view in `book.json`; each further chapter negotiates a not-yet-covered UDHR
article within the same frame, chained to the previous chapter (Markov chain over full texts — no
summarising step in between).

```bash
# Create a volume (prologue + book.json)
python3 generate_pipeline.py --mode new-book --lang DE --book-style Gerätehandbuch

# Append the next chapter (without --book-id: youngest book by mtime)
python3 generate_pipeline.py --mode append-chapter --lang DE
python3 generate_pipeline.py --mode append-chapter --lang DE --book-id buch_001_das_büro_der_unendlichkeit
```

**A volume is bounded by its language corpus, not by a fixed 30.** `naechster_artikel()` takes the
unused articles from `articles/<lang>/`, so a volume is complete when its corpus is exhausted
(currently 9 chapters for English, 30 for German/French/Swahili).

**Mechanical closing guard (`audit_manual_ending`):** the closing paragraph must carry a hard marker
(`Fehlercode`, `Wartung`, `Intervall`, `Diagnose`, `Prüfung`, `Protokoll`, `Abschnitt`) or a safety
block (`[GEFAHR]` / `[WARNUNG]` / `[HINWEIS]`); direct speech and emotion verbs are excluded. Up to
three attempts are made; afterwards the chapter is written **with a note** (no silent pass, no total
loss). Each chapter records `manual_ending_ok`, `manual_ending_attempts` and `manual_ending_note` in
its front matter; the CLI exits with **code 2** on a fallback (exit 1 = abort without a file).

**Rotation runner (`scripts/run_model_rotation.py`):** the hourly service walks the volume pool with
a model pool and writes one chapter per slot. Volumes whose corpus is fully negotiated are removed
from the pool *before* a slot is spent, so a round is never consumed by a volume that cannot accept
another chapter.

**Index & developer endpoints** (written deterministically and atomically):

```bash
python3 scripts/build_books_index.py
```

| File | Content |
|---|---|
| `web/books.json` | Catalogue of all volumes: metadata, chapter table of contents, word counts, covered articles, audit flags |
| `web/api/random.json` | Sample chapter in full text — **static**: GitHub Pages does not shuffle per request |
| `web/api/ipsum.json` | Placeholder text from the corpus for layout and testing |

The reader (`web/index.html`) exposes the tabs **[ Stories ] | [ Books & Volumes ]** with a tile view
(genre badge, progress "*n* of 30 articles negotiated"), table of contents, chapter navigation and a
feedback bar at the end of each chapter: ▲/▼ are stored **locally in the browser only**, 🚩 *Report*
opens a pre-filled GitHub issue with volume, chapter path and audit status.

## Language matrix (seeds)

`scripts/seed_matrix.py` enforces **≥ 3 volumes per (language × genre)** across 10 languages and
6 genres (target: 180 seeds), and goes through the real pipeline path (`prologue generation`), not
stub files:

```bash
python3 scripts/seed_matrix.py --dry-run          # report the gap per combination
python3 scripts/seed_matrix.py --langs FR --genres legal_thriller --limit 1
```

## MCP integration (agents)

The server implements the JSON-RPC 2.0 MCP specification using only the standard library (no pip, no
venv required) with the tools `daemon_status`, `daemon_start`, `daemon_stop`, `get_corpus_stats`,
`read_latest_tale`, `get_config_overview`, `set_config_value`.

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

<!-- START_DYNAMIC_STATS -->
### Live-Kennzahlen des Korpus

*Generiert aus dem Bestand, nicht geschätzt — zuletzt: 2026-11-14*

| Kennzahl | Wert |
|---|---:|
| Bände | 516 |
| Kapitel | 931 |
| Artikel-Abdeckung (Summe über Sprachen) | 107 / 570 |
| Sprachen | 19 |
| Zeichen im Korpus | 2.968.893 |

**Abdeckung je Sprache** (Kapitel / Artikel von 30)

| Sprache | Bände | Kapitel | Artikel |
|---|---:|---:|---:|
| AR | 23 | 7 | 4 / 30 |
| DE | 52 | 507 | 30 / 30 |
| EN | 39 | 131 | 10 / 30 |
| ES | 31 | 13 | 4 / 30 |
| FA | 8 | 8 | 4 / 30 |
| FR | 23 | 6 | 4 / 30 |
| HE | 5 | 6 | 4 / 30 |
| HI | 6 | 7 | 4 / 30 |
| ID | 8 | 8 | 4 / 30 |
| IT | 26 | 9 | 4 / 30 |
| JA | 53 | 51 | 3 / 30 |
| KO | 49 | 49 | 3 / 30 |
| NL | 50 | 49 | 4 / 30 |
| PT | 24 | 8 | 5 / 30 |
| RU | 3 | 4 | 4 / 30 |
| SV | 49 | 49 | 4 / 30 |
| SW | 22 | 8 | 4 / 30 |
| UK | 23 | 6 | 4 / 30 |
| ZH | 22 | 5 | 4 / 30 |

**Varianten (A = Wortlaut, B = Bedeutung, C = SALT)**

| Variante | Bände | Anteil |
|---|---:|---:|
| A | 248 | 48% |
| A2 | 5 | 1% |
| B | 25 | 5% |
| C | 25 | 5% |
| C2 | 3 | 1% |
| C3 | 210 | 41% |

**Stil-Verteilung** (Stil ist je Band fest; innerhalb eines Bandes wechselt er nicht)

| Stil | Bände |
|---|---:|
| Songtext_Matrix | 281 |
| Satire | 9 |
| Fable | 8 |
| Distopia_SciFi | 8 |
| Parabel | 6 |
| Fábula | 6 |
| Sátira | 6 |
| Crónica_Histórica | 6 |
| Parábola | 6 |
| Drama_Judicial | 6 |

* 77 verschiedene Stile im Bestand · 26 Bände mit mindestens 10 Kapiteln

**Ketten-Tiefe** (jedes Kapitel liest genau das VORHERIGE Kapitel, nicht die ganze Historie)

* Kapitel je Band: Median 1 · Maximum 28
* Kontext je Kapitel: ein Vorgängerkapitel, im Mittel 3189 Zeichen (~797 Tokens)

**Diversität** (je niedriger der erste Wert, desto weniger Schablone)

* Häufigste Stil-Phrase: `filtered reese bass` in 22% der Zuordnungen
* Bände mit genau 5 Figuren: 488 von 506 (96%)

<!-- END_DYNAMIC_STATS -->
