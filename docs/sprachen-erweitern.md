# Eine Sprache zur Buch-Pipeline hinzufügen

Eine Sprache besteht aus **zwei** Teilen. Fehlt einer, entstehen Bände ohne Kapitel.

| Teil | Pfad | Umfang | Erzeugt von |
|---|---|---|---|
| Artikelkorpus | `articles/<lang>/art_01.md … art_30.md` | genau 30 | `scripts/erweitere_sprachen.py` |
| Locale | `locales/<lang>.json` | 23 Stile, 21 Regeln, 23 Flags, `core_guardrail`, `instruction_language` | dito |

Dazu zwei Registrierungen, die **Handarbeit** bleiben: `LANGUAGE_NAMES_DE` in
`generate_pipeline.py` (deutscher Sprachname für die Prompt-Zeile) und — nur falls
die Sprache in die Matrix soll — nichts weiter: `seed_matrix.py` und `album_stubs.py`
lesen die Sprachliste inzwischen aus `locales/*.json`.

---

## 1. Korpus beschaffen

```bash
python3 scripts/erweitere_sprachen.py --langs nl --apply
```

Das Skript holt die Allgemeine Erklärung der Menschenrechte, teilt sie in 30 Artikel
und schreibt sie nach `articles/<lang>/`. Danach erzeugt es die Locale per LLM aus
`locales/de.json` und prüft beide Ergebnisse gegen ein Gate (siehe unten).

**Quellenlage** (gemessen 2026-11-06):

| Quelle | Nutzbar für | Anmerkung |
|---|---|---|
| `un.org/<lang>/…` | ar, en, es, fr, ru, zh | nur die sechs UN-Sprachen |
| `<lang>.wikisource.org` | it, uk, he, nl, sv, ja, ko, fa, id | zuverlässig; **429** bei Abrufen < 1,5 s Abstand |
| `<lang>.wikipedia.org` | hi | wenn Wikisource den Titel nicht kennt |
| `unric.org` | it, pt | — |
| `ohchr.org/…/translations/*` | **nichts** | HTTP 403; im Browser Imperva-Botwall („Sicherheitsüberprüfung") |
| OHCHR-PDFs | **nichts** | zweispaltig extrahiert, Artikelreihenfolge zerstört |

## 2. Die Artikelnummer ist der Fallstrick

Nicht jede Sprache schreibt `Artikel 1`. Erst nachsehen, dann Splitter bauen:

| Sprache | Marker | Falle |
|---|---|---|
| es, it, pt, nl, sv, id | `Artículo/Articolo/Artigo/Artikel/Pasal N` | Inhaltsverzeichnis zitiert Artikel klein weiter („de la Declaración…") — der **erste echte Anfang** gewinnt, nicht der längste Treffer |
| zh | `第N条` mit chinesischen Zahlwörtern | 一…十, 二十一, 三十 |
| ja | `第N条` mit **Kanji**-Zahlwörtern | eigener Konverter, sonst 0 Treffer |
| ko | `제N조` | arabische Ziffern |
| he | `סעיף א` … `סעיף ל` | **hebräische Buchstaben**: א=1, י=10, יא=11, טו=15, כ=20, ל=30 |
| fa | `مادهٔ اول` … `مادهٔ سی‌ام` | **persische Ordnungszahlen**, teils mit Leerzeichen („بیست و یکم"), teils mit ZWNJ |
| hi | `अनुच्छेद N` | Devanagari-Label, arabische Ziffer |
| ru, uk | `Статья N` / `Стаття N` | — |

## 3. Mindestlänge ist sprachabhängig

Ein Artikel ist nicht immer lang. Gemessen: Hebräisch Artikel 9 = 45 Zeichen,
Japanisch Artikel 13 = 28 Zeichen. Eine Schwelle von 50 Zeichen verschluckt echte
Artikel — das Gate steht deshalb auf 25 Zeichen.

## 4. Editlink-Reste

Wikisource und Wikipedia hängen Redaktionslinks in den Text (`[ redigera ]`,
`[ sunting ]`, `[ ред. ]`, `[ 編集 ]`). Bleiben sie stehen, beginnt Artikel 1 mit
Müll. Der Filter in `erweitere_sprachen.py` kennt zehn Schreibweisen; eine neue
Sprache kann eine elfte mitbringen — dann prüfen, ob `art_01` mit Text beginnt.

## 5. Locale: `instruction_language` nicht vergessen

Ohne dieses Feld (Eigenname der Sprache, z. B. `日本語`) bricht
`generate_pipeline.py --mode new-book` ab:

```
Keine Anweisungssprache fuer den Buchmodus in 'JA': kein 'instruction_language'
```

`de` braucht es nicht (Ausgangssprache). Der Generator setzt es per `setdefault`;
bereits geschriebene Locales müssen nachgezogen werden.

**Reihenfolge der Stil-Schlüssel erhalten:** `seed_matrix.GENRE_POS` mappt Genres über
die **Position** im Stil-Katalog, nicht über den Namen.

## 6. Gate vor dem Schreiben

Nichts wird geschrieben, was diese Prüfungen nicht besteht:

- 30 Artikel, lückenlos 1…30
- Body über sprachabhängiger Mindestlänge
- Schrift-Gate (CJK, Kyrillisch, Arabisch, Hebräisch, Devanagari)
- Sprachmarker in ≥ 60 % der Artikel
- Locale: gleiche Anzahl Stile/Regeln/Flags wie `de.json`, keine leeren Einträge, `language_code` korrekt

## 7. Sprache im Buch prüfen (nicht nur im Korpus)

`generate_pipeline.audit_manual_ending` prüft die Sprache **je Sektion**, nicht nur als
Gesamtquote: ein deutsches `[INTRO]` in einem chinesischen Lied fiel durch die
Gesamtquote (662 CJK-Zeichen im Rest), wird jetzt aber abgelehnt. Produktions-Cues in
Klammern (`(Sub-bass drops in, snare rolls)`) sind absichtlich englisch und
ausgenommen.

`textsprache()` kennt zehn lateinische Sprachen. Fehlt eine, wird ihr Text als `EN`
verurteilt und das Kapitel abgelehnt — genau das passierte mit Portugiesisch, bevor
`SPRACH_SETS` erweitert wurde.

## 8. Album-Stub je Sprache

```bash
python3 scripts/album_stubs.py --dry-run   # zeigt, was fehlt
python3 scripts/album_stubs.py             # legt an, idempotent
```

Ein Band pro Sprache mit `style=Songtext_Matrix`, `song_mode=erzaehl`,
`song_genre=dark_ambient` und echtem Prolog aus dem Pipeline-Pfad
(kein Stub-JSON). Vorhandene Bände werden übersprungen.

## 9. Fertige Songs dem richtigen Kapitel zuordnen

Der Dateiname hilft nicht: bei einem Band mit zwei Kapiteln heißt die MP3 oft nur wie
das Album. Suno schreibt die verwendeten Lyrics in den ID3-Tag `lyrics-eng` — der ist
die Wahrheit.

```bash
ffprobe -v error -show_entries format_tags -of json "song.mp3"
```

Wortmengen (Jaccard auf `\w+`) gegen jedes Kapitel rechnen, bester Treffer gewinnt.
Gemessen: Swahili-Band mit zwei Kapiteln ergab 83 % gegen Kapitel 1 und 54 % gegen
Kapitel 2. Ablage: `<band>/audio/<kapiteldatei>.mp3`, danach `sha256sum` Quelle ↔ Ziel.

## 10. Was der Runner von selbst tut

`scripts/run_model_rotation.py` schließt Bände aus, deren Sprache **keinen** Korpus hat.
Ohne diesen Filter melden sie „Alle Artikel verhandelt" (Grenze 0), schreiben nie ein
Kapitel und verbrennen jede Runde einen Slot — betraf 90 Bände in AR/ES/IT/PT/UK.
Der Runner committet nur `menschenrechte_books`, `web/books.json` und `web/api/`;
Code und Korpora müssen separat committet werden.
