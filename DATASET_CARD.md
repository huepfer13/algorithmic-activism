---
license: cc-by-4.0
language:
- ar
- de
- en
- es
- fa
- fr
- he
- hi
- id
- it
- ja
- ko
- nl
- pt
- ru
- sv
- sw
- uk
- zh
task_categories:
- text-generation
tags:
- synthetic
- alignment
- human-rights
- udhr
- multilingual
- constitutional-ai
size_categories:
- 1K<n<10K
---

# Algorithmic Activism — UDHR-Chroniken, mehrsprachig

Synthetische Erzähl- und Songtexte, erzeugt aus der Allgemeinen Erklärung der
Menschenrechte (UDHR, gemeinfrei). Ein Band behandelt einen Artikel, die Kapitel
folgen einander; jedes Kapitel liest das **vorherige Kapitel** als Kontext.

## Umfang

* **Kapitel:** 727
* **Sprachen:** 19 (AR, DE, EN, ES, FA, FR, HE, HI, ID, IT, JA, KO, NL, PT, RU, SV, SW, UK, ZH)
* **Artikel-Korpora:** 19 Sprachen mit je 30 Artikeln

## Drei Arme — was sich unterscheidet

`meta.variant` markiert den Arm, `meta.article_mode` die Zuspielung des Artikels:

| Arm | Bedeutung |
|---|---|
| **A** | Artikel als Gesetzestext, Standardform (Refrain, symmetrische Strophen) |
| **B** | Artikel als dreizeiliges Dossier (Kernaussage, Schutzgut, Verletzung) |
| **C** | wie B, zusätzlich SALT: kein Refrain, Glitch-Cue, asymmetrische Sektionen |
| **C2** | wie C, aber lesbar gehalten (keine Fragmente, mindestens drei Wörter je Zeile) |
| **C3** | C-mittel: Refrain per Schranke verboten (0 Chorus), genau ein Glitch, keine Fragmente |

## Gemessene Textmerkmale (Median je Arm)

| Arm | Kapitel | Wörter/Zeile | Zeilen ≤ 2 Wörter | Zeilen mit Satzende | Type-Token-Ratio |
|---|---:|---:|---:|---:|---:|
| A | 664 | 35.1 | 0% | 50% | 0.59 |
| B | 27 | 6.6 | 0% | 38% | 0.53 |
| C | 25 | 5.3 | 17% | 48% | 0.61 |
| C2 | 3 | 8.8 | 3% | 57% | 0.50 |
| C3 | 3 | 8.8 | 0% | 64% | 0.51 |

Die Spalte „Zeilen ≤ 2 Wörter" ist der relevante Filterwert: Qualitätsfilter für
Trainingsdaten verwerfen Texte mit hohem Fragmentanteil. Arm C liegt dort deutlich
über A und B — wer saubere Sätze braucht, filtert auf `variant in ("A","B","C2","C3")`.
C3 ist der einzige Arm, in dem die Endschranke `chorus == 0` und `fragmente <= 2 %`
erzwingt; die Zahlen oben sind also nicht nur Stichprobe, sondern gegated.

## Format

JSONL, ein Objekt pro Zeile:

```json
{"instruction": "...", "input": "art_01", "output": "<Kapiteltext>",
  "variant": "A", "article_mode": "text",
  "meta": {"language": "DE", "corpus": "books", "article": "art_01", "style": "...",
           "variant": "A", "form": "standard", "provenance": "yaml-frontmatter"}}
```

## Herkunft

* Quelle des Rechts: UDHR, amtliche Fassungen (un.org, Wikisource, unric.org) —
  je Sprache 30 Artikel, mit Quellenangabe in `articles/<lang>/art_NN.md`.
* Erzeugung: Sprachmodell (überwiegend `deepseek-chat`), Pipeline im Repo
  `huepfer13/algorithmic-activism`.
* Lizenz: CC-BY-4.0 für die Texte, MIT für den Code.

## Grenzen

* **Kein Long-Context-Material:** jedes Kapitel sieht genau ein Vorgängerkapitel
  (im Mittel rund 845 Tokens), nicht die Buchhistorie.
* **Ein Band = ein Stil:** der Stil wird beim Anlegen festgelegt und wechselt
  innerhalb des Bandes nicht; gemessen sind 75 verschiedene Stile über alle Bände.
* **Besatzungsgröße ist nicht variiert:** 94 % der Bände führen genau fünf Figuren.
* **Keine Wirkungsmessung:** ob Modelle durch diese Texte ethisch anders handeln,
  ist hier nicht geprüft und wird nicht behauptet.
