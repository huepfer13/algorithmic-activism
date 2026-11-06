#!/usr/bin/env python3
"""Neue Sprachen für die Buch-Pipeline anlegen: Korpus + Locale.

Zwei Schritte je Sprache, beide mit Gate:
  1. Korpus: 30 Artikel der Allgemeinen Erklärung der Menschenrechte aus Wikisource
  2. Locale:  locales/<lang>.json, aus de.json übersetzt (gleiche Schlüssel!)

Es wird nichts geschrieben, was das Gate nicht besteht. Aufruf:
    python3 erweitere_sprachen.py --langs nl,ja --apply
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import generate_pipeline as gp                                          # noqa: E402
QUELLEN = {
    "nl": ("nl.wikisource.org", ["Universele verklaring van de rechten van de mens",
                                 "Universele Verklaring van de Rechten van de Mens"],
           r"[Aa]rtikel\s*(\d{1,2})", "Nederlands", "Niederländisch"),
    "ja": ("ja.wikisource.org", ["世界人権宣言"], r"第\s*([一二三四五六七八九十]+)\s*条", "日本語", "Japanisch"),
    "ko": ("ko.wikisource.org", ["세계인권선언"], r"제\s*(\d{1,2})\s*조", "한국어", "Koreanisch"),
    "sv": ("sv.wikisource.org", ["Allmän förklaring om de mänskliga rättigheterna"],
           r"[Aa]rtikel\s*(\d{1,2})", "Svenska", "Schwedisch"),
    "fa": ("fa.wikisource.org", ["اعلامیه جهانی حقوق بشر"], r"ماده[\u0654\u200c]?\s*([^\s،.:؛]{2,20}(?:\s+و\s+[^\s،.:؛]{2,20})?)", "فارسی", "Persisch"),
    "id": ("id.wikisource.org", ["Pernyataan Umum tentang Hak-Hak Asasi Manusia"],
           r"Pasal\s*(\d{1,2})", "Bahasa Indonesia", "Indonesisch"),
}


FA_ORDINAL = {
    "اول": 1, "دوم": 2, "سوم": 3, "چهارم": 4, "پنجم": 5, "ششم": 6, "هفتم": 7,
    "هشتم": 8, "نهم": 9, "دهم": 10, "یازدهم": 11, "دوازدهم": 12, "سیزدهم": 13,
    "چهاردهم": 14, "پانزدهم": 15, "شانزدهم": 16, "هفدهم": 17, "هجدهم": 18,
    "هیجدهم": 18, "نوزدهم": 19, "بیستم": 20, "بیستویکم": 21, "بیستودوم": 22,
    "بیستوسوم": 23, "بیستوچهارم": 24, "بیستوپنجم": 25, "بیستوششم": 26,
    "بیستوهفتم": 27, "بیستوهشتم": 28, "بیستونهم": 29, "سیام": 30,
}


KANJI = {c: i for i, c in enumerate("一二三四五六七八九", start=1)}


def kanji_zahl(s: str) -> int:
    """一 -> 1, 十 -> 10, 十一 -> 11, 二十一 -> 21, 三十 -> 30."""
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + KANJI.get(s[1:], 0)
    if "十" in s:
        a, b = s.split("十", 1)
        return KANJI.get(a, 0) * 10 + (KANJI.get(b, 0) if b else 0)
    return KANJI.get(s, 0)


def hole(site: str, page: str) -> str:
    url = (f"https://{site}/w/api.php?action=parse&prop=text&format=json"
           f"&formatversion=2&page={urllib.parse.quote(page)}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UDHR-Sync)"})
    d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
    if "error" in d:
        raise RuntimeError(f"{site}: {d['error'].get('code')}")
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", d["parse"]["text"])
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", txt)


def korpus(lang: str) -> list:
    site, pages, splitter, _, _ = QUELLEN[lang]
    txt = ""
    for p in pages:
        try:
            txt = hole(site, p)
        except Exception:                                              # noqa: BLE001
            time.sleep(1.5)
            continue
        if len(txt) > 3000:
            break
    if len(txt) < 3000:
        raise RuntimeError(f"keine brauchbare Quelle ({len(txt)} Zeichen)")
    tr = list(re.finditer(splitter, txt))
    best = {}
    for i, m in enumerate(tr):
        roh = m.group(1).strip()
        if lang == "ja":
            nr = kanji_zahl(roh)
        elif lang == "fa":
            schluessel = re.sub(r"[\s\u200c]+", "", roh)      # "بیست و یکم" -> "بیستویکم"
            nr = FA_ORDINAL.get(schluessel, 0)
        else:
            nr = int(roh)
        if not 1 <= nr <= 30:
            continue
        start, ende = m.end(), (tr[i + 1].start() if i + 1 < len(tr) else m.end() + 1200)
        body = re.sub(r"\[[^\]]{0,60}(?:ред\.|संपादित|עריכה|edit|redigera|sunting|sửa|編集|편집|ویرایش)[^\]]{0,60}\]",
                      " ", txt[start:ende])          # Wikisource/Wikipedia-Editlinks je Sprache
        body = re.sub(r"\s+", " ", body).strip(" :：-—،,.、。[]")
        if len(body) < 25:
            continue
        if nr not in best:
            best[nr] = body
    return [(n, best[n]) for n in sorted(best)]


def locale(lang: str) -> dict:
    _, _, _, eigen, deutsch = QUELLEN[lang]
    vorlage = json.load(open(f"{REPO}/locales/de.json", encoding="utf-8"))
    prompt = f"""Übersetze diese Locale-Datei für ein Buchgenerator-System ins {eigen} ({deutsch}).

REGELN
- Gib NUR gültiges JSON zurück, keinen Fließtext, keine Code-Fences.
- Gleiche Struktur und gleiche Anzahl Einträge wie die Vorlage.
- Übersetze: language_name, alle Schlüssel von "styles", alle Werte von "styles",
  alle Schlüssel von "style_rules", alle Werte von "style_rules", alle Schlüssel von
  "style_flags", alle Werte von "zustaende" und "block_schema", sowie "core_guardrail".
- "language_code" wird "{lang.upper()}", "code_praefix" bleibt EIN Buchstabe (übersetze ihn nicht).
- Fachbegriffe (JSON-Feldnamen wie manual_ending, erlaube_rede, erlaube_emotion) bleiben unverändert.

VORLAGE
{json.dumps(vorlage, ensure_ascii=False)}"""
    roh = erzeuge(prompt)
    daten = json.loads(roh)
    # Der Buchmodus verlangt 'instruction_language' (Eigenname der Sprache), sonst bricht er ab.
    daten.setdefault("instruction_language", daten.get("language_name") or eigen)
    return daten


def erzeuge(prompt: str) -> str:
    txt = gp.erzeuge_text(prompt, "deepseek-chat", "https://api.deepseek.com", "deepseek",
                          json_mode=True)
    txt = txt.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-z]*\s*|\s*```$", "", txt, flags=re.S)
    i, j = txt.find("{"), txt.rfind("}")
    return txt[i:j + 1] if i >= 0 and j > i else txt


def pruefe_locale(lang: str, neu: dict, alt: dict) -> list:
    fehler = []
    if neu.get("language_code") != lang.upper():
        fehler.append(f"language_code={neu.get('language_code')!r}")
    for feld in ("styles", "style_rules", "style_flags"):
        if len(neu.get(feld) or {}) != len(alt[feld]):
            fehler.append(f"{feld}: {len(neu.get(feld) or {})} statt {len(alt[feld])}")
    leer = [k for feld in ("styles", "style_rules", "style_flags")
            for k, v in (neu.get(feld) or {}).items()
            if not v or (isinstance(v, str) and len(v) < 10)]
    if leer:
        fehler.append(f"{len(leer)} leere/kurze Einträge, z.B. {leer[:3]}")
    return fehler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    vorlage = json.load(open(f"{REPO}/locales/de.json", encoding="utf-8"))
    for lang in [x.strip() for x in a.langs.split(",") if x.strip()]:
        print(f"=== {lang.upper()} ===")
        try:
            artikel = korpus(lang)
        except Exception as e:                                          # noqa: BLE001
            print(f"  Korpus: FEHLER {e}")
            continue
        nummern = [n for n, _ in artikel]
        probe = f' · "{artikel[0][1][:50]}"' if artikel else ""
        print(f"  Korpus: {len(artikel)}/30 · {'vollständig' if nummern == list(range(1, 31)) else 'LÜCKEN'}{probe}")
        if nummern != list(range(1, 31)):
            continue
        try:
            loc = locale(lang)
        except Exception as e:                                          # noqa: BLE001
            print(f"  Locale: FEHLER {e!r}"[:160])
            continue
        fehler = pruefe_locale(lang, loc, vorlage)
        print(f"  Locale: {len(loc.get('styles') or {})} Stile · {'OK' if not fehler else fehler}")
        if fehler:
            continue
        if a.apply:
            tgt = f"{REPO}/articles/{lang}"
            os.makedirs(tgt, exist_ok=True)
            for nr, body in artikel:
                open(f"{tgt}/art_{nr:02d}.md", "w", encoding="utf-8").write(
                    f"---\narticle: {nr}\narticle_id: \"art_{nr:02d}\"\n"
                    f"title: \"{body[:60]}\"\nsource: \"Wikisource {QUELLEN[lang][0]}\"\n---\n{body}\n")
            json.dump(loc, open(f"{REPO}/locales/{lang}.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            print(f"  geschrieben: articles/{lang}/ ({len(artikel)}) · locales/{lang}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
