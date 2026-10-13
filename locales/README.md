# Locale-Vertrag (für Autor:innen neuer Sprachen)

Diese Datei hält fest, was eine `locales/<lang>.json` erfüllen muss, damit die Pipeline sie
ohne stille Ausfälle benutzt. Alle Regeln sind am Code gemessen, nicht abgeleitet.

## 1. Pflichtfelder im Kopf

| Feld | Pflicht | Warum |
|---|---|---|
| `language_code` | ja | z. B. `ES` |
| `language_name` | ja | Eigenname der Sprache (`Español`) |
| `instruction_language` | **ja** für alles außer DE | `generate_pipeline.py:368` (`book_language_directive`). Fehlt es, bricht der Buchmodus ab — das ist gewollt (eine deutsche Anweisung mit bloßem Sprachwunsch erzeugte für AR gemischte Schrift, Messung 2026-10-12) |
| `core_guardrail`, `guardrail_prompt` | ja | übersetzte Guardrail-Texte (Vorlage: `en.json`) |

Struktur-Vorlage ist **`en.json`** (Kopfzeilen), Inhalts- und Wahrheitsquelle bleibt **`de.json`**
(Stile, Regeln, Boolesche Schranken).

## 2. Die sieben Flag-Schlüssel

Erlaubt sind genau: `manual_ending`, `erlaube_rede`, `erlaube_emotion`, `figuren_verboten`,
`code_praefix`, `zustaende`, `block_schema` — plus `stanza_zeilen` für Versgenres.

**Unbekannte Schlüssel werden still ignoriert.** Ein Katalog mit erfundenen Namen (etwa
`is_verse`, `min_words`) baut fehlerfrei und hat trotzdem keine einzige Schranke. Nicht
übersetzen: die **Booleschen Werte** werden eins zu eins aus `de.json` übernommen — die Semantik
einer Schranke darf sich mit der Sprache nicht ändern.

## 3. Das Blockschema

* Platzhalter heißen **immer** `{zustand}` und `{code}`, auch in einer fremdsprachigen Datei
  (`generate_pipeline.py:850` ruft `schema.format(zustand=…, code=…)`). `{state}`, `{estado}` oder
  `{statut}` sind beim Erzeugen ein `KeyError`. Übersetzt werden nur die **Beschriftungen** und die
  vier **Zustandsworte**.
* `zustaende`: genau vier Wörter, in der Zielsprache, ohne Leerzeichen.
* `code_praefix`: ein Zeichen, **identisch mit `de.json`** für dasselbe Genre. Sonst tragen zwei
  Genres denselben Buchstaben quer durch die Sprachen (`scripts/check_prefixes.py` prüft das).
* **Erstes Label nur ASCII** plus ÄÖÜäöü und Bindestrich, 3–24 Zeichen — die Labelklasse in
  `pflichtblock_muster` lässt keine Akzente und keine Unterstriche zu. Also `CRONICA`,
  `LIBRO-INFANTIL`, nicht `CRÓNICA` oder `LIBRO_INFANTIL`. Die **Zustandsworte** hinter dem
  Doppelpunkt sind frei (auch nicht-lateinische Schrift).
* **Bidi-Steuerzeichen** (U+200E/200F, U+202A–202E, U+2066–2069, U+061C) werden vor dem Vergleich
  entfernt; sie dürfen trotzdem nicht ins Schema geschrieben werden.

## 4. Der Sonderfall Handbuch

`de.json` führt für `Gerätehandbuch` **kein** `block_schema`. Der Stempel kommt dann aus dem
Code-Default (`generate_pipeline.py:852`) und lautet:

```
[STATUS: DEGRADED | SUB-SYS: SEKTOR-18 | CODE: E-06-11 | INTERVALL: 144h]
```

Das ist der kanonische Stempel der veröffentlichten Kapitel 1–11 und bleibt für DE so.

Die **fremdsprachigen** Kataloge tragen für dieses Genre ein eigenes, übersetztes Schema
(`en.json`: `**[STATUS: {zustand} | SUB-SYS: {code}]**`, `es.json`: `**[ESTADO: … | ARCHIVO: …]**`,
`fr.json`: `**[ÉTAT: … | DOSSIER: …]**`). Grund: ohne Schema stünde ein **deutscher** Stempel in
einem spanischen oder französischen Buch — ein stiller Sprach-Fallback, den das Projekt sonst
überall verbietet. Das ist eine bewusste Abweichung von `de.json`, keine Nachlässigkeit.

## 5. Abnahme (unabhängig, nicht Selbstauskunft)

1. `json.load` ohne Fehler; Zählung gegen `de.json`: 22 Stile / 20 Regeln / 22 Flags
   (zwei Stile führen bewusst keine Regeln: SciFi-Dystopie und Philosophischer Essay).
2. Für **jeden** Stil: `block_schema.format(zustand=zustaende[0], code="X-01-01")` läuft durch
   (Ausnahme: Handbuch-Genre, siehe 4).
3. Boolesche Schranken und Regelanzahl je Stil gegen `de.json`; `figuren_verboten` genau 4×.
4. `load_locale("<LANG>")` lädt und liefert alle Stile.
5. `scripts/check_prefixes.py` läuft ohne neue Doppelbelegung.
