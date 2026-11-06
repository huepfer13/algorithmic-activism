# Suno-Steuercodes (Sektionstags)

Referenz für den `Songtext_Matrix`-Stil. Suno liest Tags in eckigen Klammern nicht als Text vor,
sondern als Regieanweisung: sie ändern Arrangement, Gesangsstil oder Energie.

Im Prompt steht davon nur ein **kurzes Vokabular** (`tag_vokabular` in `build_chapter_prompt`) —
Platz im Prompt ist teuer, und das Modell braucht die Auswahl, nicht die Enzyklopädie. Diese Datei
ist die Langfassung für Menschen und Agenten.

## 1. Struktur

| Tag | Funktion | typisch für |
|---|---|---|
| `[Intro]` / `[Opening]` | eröffnet, oft instrumental oder gesprochen | alle |
| `[Verse]` / `[Verse 1]` / `[Verse 2]` | Strophe, Arrangement ausgedünnt für den Vortrag | alle textbasierten |
| `[Pre-Chorus]` / `[Build]` / `[Rise]` | Spannung vor dem Refrain (Drums, Akkordwechsel) | Pop, Eurodance, Hyperpop, Metalcore, R&B |
| `[Chorus]` / `[Refrain]` / `[Hook]` | Höhepunkt, volles Arrangement, oft mehrstimmig | Pop, Country, Rock, Punk, Hip-Hop |
| `[Bridge]` / `[Middle 8]` | bricht das Muster (neue Akkorde, Tonartwechsel, Tempo runter) | Pop, Country, Metalcore, R&B |
| `[Outro]` / `[Coda]` / `[Ending]` | leitet das Ende ein, Fade oder Schlussakkord | alle |

## 2. Energie

| Tag | Funktion | typisch für |
|---|---|---|
| `[Build-up]` | Snare-Rolls, Pitch-Bends, Energiekompression | Eurodance, Hyperpop, Glitch-Hop, EDM |
| `[Drop]` | Entladung nach dem Build-up, Bass und Synth maximal | Eurodance, Hyperpop, Deep House, Dubstep |
| `[Breakdown]` | Frequenzen/Instrumente fallen weg, tiefe Riffs | Metalcore, Mathcore, Dubstep, Techno |
| `[Stop]` / `[Abrupt Silence]` | Pause aller Instrumente, meist ein Takt | Deutschpunk, Hardcore, Mathcore, Drill |
| `[Crescendo]` | kontinuierliche Steigerung über einen längeren Block | Post-Rock, Dark Ambient, Math Rock |

## 3. Stimme

| Tag | Funktion | typisch für |
|---|---|---|
| `[Spoken Word]` / `[Spoken Intro]` | verlässt die Melodie, spricht im Rhythmus | Post-Rock, Dark Ambient, Emo, Boom-Bap-Intro |
| `[Group Shout]` / `[All Voices]` | Chor- oder Gang-Vocals statt Solostimme | Deutschpunk, Hardcore, Irish Folk |
| `[Falsetto]` / `[Vocal Runs]` | Kopfstimme, gedehnte Verzierungen | R&B, Neo-Soul, Synthpop |
| `[Scream]` / `[Guttural Vocals]` | aggressiver, verzerrter Gesang | Metalcore, Mathcore, Grindcore |
| `[Whispered Vocals]` | Flüstern nah am Mikrofon | Dark Ambient, Bossa Nova, Trip-Hop |
| `[Vocal Chop Intro]` / `[Bitcrushed Vocal Chop]` | Text als rhythmisches Sample-Fragment | Deep House, Glitch-Hop, Hyperpop |

## 4. Instrument

| Tag | Funktion | typisch für |
|---|---|---|
| `[Guitar Solo]` / `[Nylon Guitar Solo]` / `[Slide Guitar Solo]` | Gitarrensolo, Zusatz bestimmt den Bautyp | Metalcore, Bossa Nova, Delta Blues, Country |
| `[Bass Solo]` / `[Slap Bass Interlude]` | Bass im Vordergrund | Deutschpunk, Funk, Post-Punk |
| `[Scratch-Interlude]` / `[Turntable Scratch]` | Plattenscratches über dem Beat | Boom-Bap, Nu-Metal |
| `[Instrumental Chorus]` / `[Instrumental Break]` | Refrain ohne Gesang | Synthwave, Deep House, Post-Punk |
| `[Pedal Steel Solo]` | das gleitende Saiteninstrument des Country | Country, Americana |
| `[Turnaround]` | kurze Überleitung am Ende eines Blues-Schemas | Delta Blues, Jazz |

## 5. Produktion

| Tag | Funktion | typisch für |
|---|---|---|
| `[Vinyl Crackle]` / `[Lo-Fi Filter]` | Plattenknistern, Telefonfilter | Boom-Bap, Lo-Fi, Delta Blues |
| `[Dub Outro]` / `[Heavy Delay]` / `[Space Echo]` | extreme rhythmische Echos | Reggae/Dub, Post-Punk, Dark Ambient |
| `[Key Change]` / `[Modulation to Major Key]` | Tonartwechsel, oft Moll nach Dur | J-Rock, Eurodance, Power-Pop |

## 6. Kombination

Sektion + Deskriptor mit Gedankenstrich — so steuert man Energie und Klang in einem Tag:

```
[Bridge — stripped, vocal-forward, falsetto]
[Chorus — All Voices / Ensemble]
[Breakdown — heavy down-tuned guitars]
```

Im Prompt steht die Regel: **höchstens zwei Deskriptoren pro Tag**, sonst zerfällt die Anweisung.

## Belegstatus

Die Tag-Wirkung ist **nicht gemessen** — sie stammt aus der Vorlage des Betreibers und aus der
Suno-Prompting-Literatur. Gemessen ist dagegen, wie stark das Vorkapitel die Ausgabe dominiert
(siehe `docs/suno-prompt-and-music-theory.md`): Tags und Regeln verlieren gegen den Kontext.
