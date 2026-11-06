#!/usr/bin/env python3
"""Genre-Profile fuer den Songtext-Stil — Daten, keine Sonderfaelle im Code.

Quelle: Liste des Betreibers (2026-11-05), 20 Genres mit Silbenkorridor, Reim-
anspruch, Tagging und Kernmerkmal. Die Zahlen sind **Vorgaben aus dieser Liste,
nicht gemessen** — kein Korpus wurde dagegen geprueft. Was gemessen ist, steht
in docs/genre-matrix.md unter "Belegstatus".

Auswahl im Band: book.json -> "song_genre": "<id>". Fehlt das Feld, gilt der
Modus ohne Genre-Profil (Verhalten wie vorher).
"""

GENRES = {
    "boom_bap": {
        "label": "Boom-Bap Hip-Hop",
        "style_line": "1990s boom bap hip hop, east coast, gritty vinyl sample, 90 bpm, crisp acoustic drums, deep upright bass, scratch interlude",
        "silben": (12, 16), "reim": 75,
        "tags": "ja, mit Deskriptor ([Hook - Scratches, Boom-Bap Beat])",
        "merkmal": "16-Bars-Strophen, [Scratch-Interlude] oder gesprochenes Intro ueber dem Sample",
    },
    "grime_drill": {
        "label": "UK Grime / Drill",
        "style_line": "uk drill, grime, aggressive sliding 808 bass, rapid-fire hi-hats, dark minor key strings, 140 bpm",
        "silben": (14, 18), "reim": 50,
        "tags": "minimal, aber Ad-lib-Klammern ((Bow!), (Truss mi!))",
        "merkmal": "abrupte Stops, Rapid-Fire-Klammer-Echos am Zeilenende",
    },
    "rnb": {
        "label": "Contemporary R&B",
        "style_line": "contemporary r&b, lush harmonies, late night atmosphere, smooth rhodes piano, slow jam, 85 bpm, male falsetto",
        "silben": (8, 14), "reim": 40,
        "tags": "ja, mit Deskriptor ([Pre-Chorus - lush harmonies])",
        "merkmal": "Melisma bricht Silbengrenzen; Strophe schneller als der Refrain",
    },
    "deutschpunk": {
        "label": "Deutschpunk / Hardcore",
        "style_line": "deutschpunk, fast raw punk rock, distorted garage bass, aggressive group vocals, 180 bpm",
        "silben": (6, 8), "reim": 70,
        "tags": "roh, ohne Schoenklang ([Chorus - Group Shout])",
        "merkmal": "Parole-Stil, [Bass Solo] oder [Stop] vor dem letzten Ausbruch",
    },
    "metalcore": {
        "label": "Modern Metalcore / Djent",
        "style_line": "modern metalcore, djent down-tuned guitars, heavy staccato riffs, aggressive guttural screams, soaring melodic chorus, 130 bpm",
        "silben": (10, 12), "reim": 20,
        "tags": "stilgebend ([Breakdown - heavy down-tuned guitars])",
        "merkmal": "Breakdown ersetzt die Bridge; Stakkato oder langgezogener Scream",
    },
    "emo_mathrock": {
        "label": "Mid-West Emo / Math Rock",
        "style_line": "mid-west emo, math rock, twinkly clean guitars, complex drums, conversational spoken-word delivery, 115 bpm",
        "silben": (9, 13), "reim": 15,
        "tags": "keine",
        "merkmal": "konversationell, Saetze brechen mitten ab, kein klassischer Refrain",
    },
    "synthwave": {
        "label": "Synthwave / Outrun",
        "style_line": "synthwave, outrun, 1980s cinematic electronic, driving retro arpeggiator, gated reverb drums, neon atmosphere, 110 bpm",
        "silben": (7, 9), "reim": 50,
        "tags": "ja ([Instrumental Chorus], [Arpeggiator Interlude])",
        "merkmal": "oekonomisch, lange instrumentale Pausen, 80er-Echoklammern",
    },
    "deephouse": {
        "label": "Deep House / Neo-Soul",
        "style_line": "deep house, soulful vocal chops, driving sub bass, minimalist four-on-the-floor beat, 122 bpm",
        "silben": (4, 7), "reim": 30,
        "tags": "ja ([Vocal Chop Intro], [Drop - driving bassline])",
        "merkmal": "eine Zeile ueber 16 Takte variiert; Loop statt Strophe",
    },
    "eurodance_hyperpop": {
        "label": "Eurodance / Hyperpop",
        "style_line": "hyperpop, eurodance, pitch-shifted high-energy female vocals, extreme bitcrushed synths, massive rave drop, 160 bpm",
        "silben": (10, 12), "reim": 100,
        "tags": "ja ([Build-up], [Drop], [Female Vocals / Male Rap])",
        "merkmal": "Rap-Verse, Pitch-Shift-Bridge, monumentaler Synth-Hook",
    },
    "country": {
        "label": "Classic Country / Americana",
        "style_line": "classic country, americana, acoustic guitar strumming, prominent pedal steel guitar, warm narrative male vocals, 75 bpm",
        "silben": (9, 11), "reim": 80,
        "tags": "kanonisch ([Chorus - Pedal Steel Solo])",
        "merkmal": "narrativ; die letzte Refrainzeile traegt fast immer den Titel",
    },
    "irish_folk": {
        "label": "Irish Folk / Sea Shanty",
        "style_line": "irish folk, traditional sea shanty, stomping boots rhythm, acoustic fiddle, penny whistle, collective ensemble chorus, 6/8 time",
        "silben": (8, 10), "reim": 70,
        "tags": "ja ([Chorus - All Voices / Ensemble])",
        "merkmal": "Solo-Strophe gegen kollektiven Refrain; non-lexikalische Refrains",
    },
    "delta_blues": {
        "label": "Delta Blues",
        "style_line": "delta blues, raw acoustic slide guitar, stamping foot rhythm, gritty worn-out male vocals, call and response style",
        "silben": (10, 14), "reim": 50,
        "tags": "ja ([Turnaround], [Slide Guitar Solo])",
        "merkmal": "AAB-Form: Zeile 1 wird identisch wiederholt, Gitarre antwortet",
    },
    "reggae_dub": {
        "label": "Roots Reggae / Dub",
        "style_line": "roots reggae, dub, heavy skanking offbeat guitar, deep sub-bass drops, spatial tape delay, space echo on drums, 70 bpm",
        "silben": (7, 10), "reim": 40,
        "tags": "ja, mit Effektangabe ([Dub Outro - heavy delay])",
        "merkmal": "Mantra-Wiederholung, bricht mitten im Verse fuer Dub-Effekte auf",
    },
    "dark_ambient": {
        "label": "Cinematic Dark Ambient",
        "style_line": "cinematic dark ambient, deep low-frequency drone, ethereal textures, distant industrial echo, spoken word whisper, 60 bpm",
        "silben": None, "reim": 0,
        "tags": "ja ([Drone Intro], [Vocal Textures - ethereal])",
        "merkmal": "kein Versmass; Text ist phonetisches Material (Spoken Word, Whisper)",
    },
    "bossa_nova": {
        "label": "Bossa Nova",
        "style_line": "bossa nova, smooth nylon guitar chords, jazz piano extensions, classic cuica percussion, whispered portuguese vocals, 90 bpm",
        "silben": (8, 12), "reim": 30,
        "tags": "zurueckhaltend ([Nylon Guitar Solo], [Whispered Vocals])",
        "merkmal": "Understatement; laute Tags zerstoeren das Klima",
    },
    "goth_postpunk": {
        "label": "Goth Rock / Post-Punk",
        "style_line": "goth rock, post-punk, heavy flanger guitar riff, prominent high treble bassline, cold mechanical drum machine, baritone monotone vocals, 125 bpm",
        "silben": (8, 10), "reim": 50,
        "tags": "ja ([Flanger Guitar Riff], [Monotone Vocals])",
        "merkmal": "baritonaler Sprechgesang, Zeilenwiederholung erzeugt Monotonie",
    },
    "mathcore_grind": {
        "label": "Mathcore / Grindcore",
        "style_line": "mathcore, extreme chaotic grindcore, rapid technical tempo changes, dissonant micro-breakdowns, abrupt silence, 240 bpm",
        "silben": (2, 20), "reim": 5,
        "tags": "ja ([Micro-Breakdown], [Abrupt Silence])",
        "merkmal": "Sekunden-Tracks, radikale Tempiwechsel mitten in der Zeile",
    },
    "mathpop_jrock": {
        "label": "Math-Pop / J-Rock",
        "style_line": "j-rock, math pop, technical guitar tapping, intricate rapid-fire drums, modulation to major key, dual language japanese english female vocals, 170 bpm",
        "silben": (12, 16), "reim": 40,
        "tags": "ja ([Technical Guitar Tapping], [Modulation to Major Key])",
        "merkmal": "hohe Silbendichte, mehrere Pre-Choruses, Sprachwechsel moeglich",
    },
    "postrock_spoken": {
        "label": "Post-Rock (Spoken Word)",
        "style_line": "post-rock, epic cinematic crescendo, ambient guitar swells, slow-building dramatic drums, orchestral strings, spoken-word monolog, 80 bpm",
        "silben": None, "reim": 0,
        "tags": "dynamisch ([Crescendo - all instruments climaxing])",
        "merkmal": "ein anschwellender Monolog; Text steuert das instrumentale Crescendo",
    },
    "glitchhop_wonky": {
        "label": "Glitch-Hop / Wonky",
        "style_line": "glitch hop, wonky hip hop beat, bitcrushed vocal chops, laser sound fx, k-p-t consonant heavy textures, unquantized micro-timing, 95 bpm",
        "silben": (10, 14), "reim": 30,
        "tags": "ja ([Bitcrushed Vocal Chop], [Laser Sound FX])",
        "merkmal": "Micro-Timing, lautmalerische Fragmente statt Sinn",
    },
}

# --- Stochastische Stil-Engine (4 Dimensionen) -------------------------------
# Vorgabe des Betreibers: Style-Zeile nie aus einem Einzelgenre bauen, sondern aus
# Epoche/Genre + Textur + Tempo + Produktionsaesthetik. Deterministisch gewuerfelt,
# damit derselbe Band/Kapitel-Slot reproduzierbar bleibt (seed = Band+Kapitel).
STIL_EPOCHEN = [
    "1990s Trip-Hop", "1980s Synthwave", "Baroque Chamber Pop", "Industrial EBM",
    "Desert Blues", "Hyperpop", "Neo-Soul", "Post-Punk Revival", "UK Garage",
    "Afrobeat", "Krautrock", "Lo-Fi Bedroom Pop", "Delta Blues", "Darkwave",
]
STIL_TEXTUREN = [
    "verzerrte Lo-Fi-Gitarren", "massive 808-Subbaesse", "analoge Modular-Synths",
    "trockene Perkussion", "weinende Celli", "gechoppte Amen-Breaks",
    "Rhodes-Akkorde mit Tape-Saturation", "Broken-Beat-Percussion",
    "Nylon-Gitarre und Cuica", "verzerrte Orgel und Slap-Bass",
]
STIL_PRODUKTION = [
    "Raw Analog Mixing", "Intimate Vocal Delivery", "Wall of Sound",
    "Overdriven Preamps", "Tape Saturation, mono gedruckt", "Tunnel-Reverb, weiter Raum",
    "Close-Mic, kaum Kompression", "Sidechain-Pumping, clubtauglich",
]
STIL_TEMPO = [(60, 80), (80, 100), (100, 120), (120, 140), (140, 160), (160, 180)]
# Frequenz-Zonen: je eine Rolle fuer Tiefe, Mitte und Breite (Vorgabe des Betreibers,
# damit im Style keine zwei Instrumente in derselben Zone arbeiten).
STIL_ZONEN = {
    "tiefe": ["808-Sub in Mono", "Upright-Bass, trocken", "Reese-Bass, gefiltert", "Sub-Puls unter 50 Hz"],
    "mitte": ["Lead-Gesang close-mic", "Snare mit Raumanteil", "Rhodes in den Mitten", "Rhythmusgitarre, gedämpft"],
    "breite": ["Pads weit im Stereobild", "Celli und Chöre", "Arpeggios hart links/rechts", "Tape-Echo-Fahnen"],
}


# --- Englische Fassung (Suno-Sprache) ----------------------------------------
# Regel: nur deutsche Bände bekommen deutsche Style-Zeilen. In allen anderen
# Sprachen steht die Zeile auf Englisch — nie gemischt (gemessen 2026-11-05:
# russisches Lied trug "Delta Blues mit verzerrten Lo-Fi-Gitarren").
STIL_TEXTUREN_EN = [
    "distorted lo-fi guitars", "massive 808 subs", "analog modular synths",
    "dry percussion", "weeping cellos", "chopped amen breaks",
    "rhodes chords with tape saturation", "broken-beat percussion",
    "nylon guitar and cuica", "distorted organ and slap bass",
]
STIL_PRODUKTION_EN = [
    "raw analog mixing", "intimate vocal delivery", "wall of sound",
    "overdriven preamps", "tape saturation, printed to mono", "tunnel reverb, wide space",
    "close-mic, barely compressed", "sidechain pumping, club-ready",
]
STIL_ZONEN_EN = {
    "low end": ["808 sub in mono", "dry upright bass", "filtered reese bass", "sub pulse below 50 Hz"],
    "mid": ["close-mic lead vocal", "snare with room", "rhodes in the mids", "muted rhythm guitar"],
    "wide": ["pads spread wide", "cellos and choirs", "arpeggios hard left/right", "tape echo tails"],
}


def stil_engine(seed: str, genre_id: str = "", lang: str = "DE") -> str:
    """Vierdimensionaler Style-String, deterministisch aus `seed`.

    Sprache: nur deutsche Baende bekommen eine deutsche Style-Zeile; alle anderen
    Englisch (Suno-Sprache). Gemischt wird nie.
    """
    import random
    deutsch = (lang or "").upper() == "DE"
    texturen = STIL_TEXTUREN if deutsch else STIL_TEXTUREN_EN
    produktion = STIL_PRODUKTION if deutsch else STIL_PRODUKTION_EN
    zonen_pool = STIL_ZONEN if deutsch else STIL_ZONEN_EN
    rng = random.Random(f"{seed}|{genre_id}")
    epoche = rng.choice(STIL_EPOCHEN)
    textur = rng.choice(texturen)
    prod = rng.choice(produktion)
    lo, hi = rng.choice(STIL_TEMPO)
    bpm = rng.randrange(lo, hi + 1, 2)
    zonen = " · ".join(f"{zone}: {rng.choice(pool)}" for zone, pool in zonen_pool.items())
    return f"{epoche} with {textur}, {bpm} BPM, {prod} · {zonen}"


# Kurzform fuer den Prompt: eine Zeile pro Band, kein Roman.
def profil_text(genre_id: str) -> str:
    g = GENRES.get((genre_id or "").strip().lower())
    if not g:
        return ""
    if g["silben"]:
        lo, hi = g["silben"]
        metrik = f"Zeilen {lo} bis {hi} Silben"
    else:
        metrik = "kein Versmass (Prosa/Spoken Word)"
    reim = "Reim frei" if not g["reim"] else f"Reim etwa {g['reim']} % der Couplets"
    return (f"GENRE-PROFIL {g['label']}: {metrik} · {reim} · "
            f"Sektionstags {g['tags']} · Merkmal: {g['merkmal']}")
