# Songwriting reference: Suno prompting & music theory

Reference for the `Songtext_Matrix` style. Two sources:

1. **[suno-prompt-engineering-guide](https://github.com/suno-ai-farm/suno-prompt-engineering-guide)** (MIT, suno-ai-farm) — prompt anatomy and the hard limits of text-to-music.
2. **Music-theory skill libraries** — for the parts of composition that a language model otherwise guesses.

Nothing here is loaded at runtime: the generation prompt is assembled from `locales/<lang>.json`
(`styles`, `style_rules`, `style_flags`). This file is the human/agent reference those rules were
derived from — if you change the rules, change them here too.

---

## 1. The seven prompt elements

| # | Element | Example | Purpose |
|---|---|---|---|
| 1 | Genre | `synth-pop`, `trap`, `arena-rock` | overall style |
| 2 | Mood | `melancholic`, `defiant` | emotional character |
| 3 | Instrumentation | `jangly guitar, 808 bass, rhodes` | sound palette |
| 4 | Vocal style | `breathy vocals, powerhouse vocals` | voice character |
| 5 | Production | `tape saturation, stadium reverb` | sonic aesthetic |
| 6 | Technical specs | `BPM: 128, Key: C Major` | locks tempo and key |
| 7 | Structure | `intro -> verse -> chorus -> bridge` | song flow |

**Hard limit: keep the style prompt under 950 characters.** Suno truncates the rest — and the
truncated part is usually exactly where instrumentation and production sit.

In our pipeline this maps to the two control lines at the top of every track:

```
Style of Music: <era + genre + mood + 3-4 instruments + production + vocal style + BPM + key>
Mood: <short emotional descriptor>
```

## 2. Templates worth using

**Era + Mood + Production**
```
80s-synth, synth-pop, nostalgic, analog synths, gated reverb drums,
warm pads, breathy vocals, 118 BPM, A minor
```

**Genre fusion with an explicit ratio** (better than stacking genre names)
```
70% country storytelling + 20% trap 808s + 10% rock guitar riffs =
modern country-rap fusion, 95 BPM, G major
```

**Mood evolution / energy arc** — the far more useful form for a 30-track album
```
melancholic piano intro -> tension with strings -> explosive chorus ->
stripped-back bridge -> massive final chorus, 130 BPM, E minor
```

**Layering** (depth without vagueness)
```
[Foundation] punchy kick, deep 808
[Rhythm] syncopated hi-hats, snappy snare
[Melody] lush pad chords, arpeggiated lead
[Vocals] layered harmonies, ad-libs
```

**Vocal effects per section**
```
[Verse] clean dry vocals, intimate
[Chorus] heavy reverb, doubled, layered harmonies
[Bridge] distorted megaphone, raw
```

## 3. Common mistakes

| Mistake | Fix |
|---|---|
| Too vague (`make a pop song`) | name genre, mood, 2–3 instruments, vocal type, BPM, key |
| Contradictory elements (`lo-fi … with stadium reverb`) | pick one production world |
| Over 950 characters | cut to the elements that matter |
| Naming artists | describe the sonic DNA instead (`dark production, minimalist beat, whispered vocals`) |
| No BPM / no key | always give both; without them the harmonic content is a lottery |

Genre BPM ranges (from the guide): pop 100–128 · rock 120–160 · hip-hop 70–90 · EDM 120–140 ·
country 90–120.

## 4. Music-theory libraries and what we take from them

| Library | What it offers | What we actually use |
|---|---|---|
| [SJY051/music-composition](https://github.com/SJY051/music-composition) (105★, CC BY 4.0 docs + MIT code) | 117 files: harmony, melody, form, orchestration, 24+ genres, songwriting, release validation | form vocabulary, genre conventions, section energy curves |
| [jtydhr88/music-composition-skills](https://github.com/jtydhr88/music-composition-skills) (177★, MIT) | 29 agent skills; output is an **ARR-SPEC** (key, tempo, bar-accurate section map, chord letters + roman numerals, entry/exit, energy curve, vocal + mix intent) that compiles to a Suno prompt | the ARR-SPEC idea: one artifact, four uses (handoff, A/B, compile source, acceptance baseline) |
| [kennethreitz/pytheory-skill](https://github.com/kennethreitz/pytheory-skill) (MIT) | six skills over PyTheory: composing, guitar fingerings, chord lab, keys & harmony, scales/modes/tunings, transcription → MIDI/WAV/sheet | the rule "specify key and mode; don't let the model invent them" |
| [BugCreator404/music-mentor](https://github.com/BugCreator404/music-mentor) | theory, TAB/score reading, harmonic analysis, practice plans, composition (ES/EN) | roman-numeral thinking for progressions |
| [esoltys/cadence-music-assistant](https://github.com/esoltys/cadence-music-assistant) | symbolische Theorie-Abfragen: Intervalle, Modi, Skalenstufen, Key-Detection, Read-Only | interval/scale-step math when a progression must be checked |
| [Zachacious/MusicTheoryJS](https://github.com/Zachacious/MusicTheoryJS) (ISC) | 108 chord qualities, 92 scales, 34 tunings, rhythm/Euclidean generation, MIDI + notation I/O, key detection | Euclidean rhythm names (tresillo, bossa clave) as concrete groove words |

**Nothing from these libraries is executed here.** They informed the rules; the pipeline stays
zero-dependency. If a chapter needs machine-checked theory, that is a separate tool, not this repo.

## 5. How this becomes a rule

`locales/<lang>.json → style_rules["Songtext_Matrix"]` carries, in the target language:

1. bracketed structure tags `[Intro] [Verse] [Pre-Chorus] [Chorus] [Bridge] [Outro]`
2. the two control lines (`Style of Music:`, `Mood:`)
3. rhythmic verses, repeating chorus, rhyme or cadence
4. **BPM and key are mandatory** in the style line
5. **energy arc with arrows**, and `[Drop]` / `[Instrumental]` for electronic genres
6. the closing block `**[TRACK: … | CODE: …]**` on its own line (the mechanical end-guard)

Rule 6 exists because `audit_manual_ending` rejects every chapter without a formal closing block —
measured: a Suno-style lyric fails with *"kein struktureller Abschluss am Zeilenanfang"*. Strip that
line before feeding the text to Suno.
