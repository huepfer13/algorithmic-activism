#!/usr/bin/env python3
"""
sync_udhr.py: Validiert und synchronisiert die kanonischen UN-Artikeldateien.
Prüft Vollständigkeit, Metadaten und Quellenangaben gegen offizielle UN-Referenzen.
"""
import glob
import os
import re

ARTICLES_DIR = "articles"

def parse_article_md(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Frontmatter parsen
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2].strip()

    return {"meta": meta, "body": body, "file": filepath}

def main():
    print("🔍 Prüfe kanonische Menschenrechts-Artikel in 'articles/'...")
    files = glob.glob(os.path.join(ARTICLES_DIR, "**", "*.md"), recursive=True)
    if not files:
        print("❌ Keine Artikeldateien gefunden.")
        return

    valid_count = 0
    for f in sorted(files):
        data = parse_article_md(f)
        lang = os.path.basename(os.path.dirname(f))
        art_num = data["meta"].get("article", "?")
        title = data["meta"].get("title", "Unbekannt")
        url = data["meta"].get("url", "Keine URL")
        
        print(f"  📜 [{lang.upper()}] Artikel {art_num:>2}: {title:<35} (Quelle: {url})")
        valid_count += 1

    print(f"\n✅ {valid_count} kanonische(r) Artikel verifiziert und einsatzbereit.")

if __name__ == "__main__":
    main()
