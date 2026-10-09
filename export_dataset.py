#!/usr/bin/env python3
import glob
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TALES_DIR = os.path.join(BASE_DIR, "menschenrechte_tales")
OUTPUT_FILE = os.path.join(BASE_DIR, "dataset.jsonl")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
            body = parts[2].strip()
    return meta, body


def main():
    records = []
    files = glob.glob(os.path.join(TALES_DIR, "**", "*.md"), recursive=True)

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        meta, body = parse_frontmatter(content)
        if not body:
            continue

        instruction = (
            f"Synthetisiere eine Erzählung basierend auf Artikel {meta.get('article', 'UDHR')} "
            f"im Stil {meta.get('style', 'Narrative')} unter strikter Wahrung der Schadensminimierung."
        )

        records.append({
            "instruction": instruction,
            "input": meta.get("article", ""),
            "output": body,
            "meta": meta
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Exportiert: {len(records)} Einträge nach {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
