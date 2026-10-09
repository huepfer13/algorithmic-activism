#!/usr/bin/env python3
"""Dataset-Export: HuggingFace-/Alpaca-kompatibles JSONL aus menschenrechte_tales/.

Provenienz-Regel: Metadaten werden NUR aus dem YAML-Frontmatter uebernommen.
Fehlt der Kopf (Altbestand), wird das ausdruecklich als provenance="none"
vermerkt - es werden keine Audit-Angaben erfunden.
"""
import glob
import json
import os
import re
import sys

try:
    import yaml  # vorhanden in der Pipeline-Venv; Fallback unten deckt Fehlen ab
except Exception:  # pragma: no cover
    yaml = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TALES_DIR = os.path.join(BASE_DIR, "menschenrechte_tales")
OUTPUT_FILE = os.path.join(BASE_DIR, "dataset.jsonl")


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if v.isdigit():
        return int(v)
    return v


def _parse_flat(raw):
    """Ein-Ebenen-YAML ohne PyYAML: 'key: wert' plus eingerueckte Bloecke als Unter-Dict.
    Damit ueberlebt das Guardrail-Audit auch in einem CI-Lauf ohne PyYAML."""
    meta = {}
    current = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = line[:1] in (" ", "\t")
        m = re.match(r"\s*([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if indent:
            if current and isinstance(meta.get(current), dict) and v:
                meta[current][k] = _scalar(v)
            continue
        if v:
            meta[k] = _scalar(v)
            current = None
        else:
            meta[k] = {}
            current = k
    return {k: v for k, v in meta.items() if not (isinstance(v, dict) and not v)}


def split_frontmatter(content):
    """(meta_dict, body, hatte_kopf)."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw, body = parts[1], parts[2]
            meta = {}
            if yaml is not None:
                try:
                    loaded = yaml.safe_load(raw) or {}
                    if isinstance(loaded, dict):
                        meta = loaded
                except Exception:
                    meta = {}
            if not meta:  # Fallback ohne PyYAML (CI-Bild): ein Nesting-Level
                meta = _parse_flat(raw)
            return meta, body.strip(), True
    return {}, content, False


def first_heading(body, fallback):
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def main():
    records = []
    skipped = []
    files = sorted(glob.glob(os.path.join(TALES_DIR, "**", "*.md"), recursive=True))

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        meta, body, had_fm = split_frontmatter(content)
        if not body.strip():
            skipped.append(os.path.relpath(path, BASE_DIR))
            continue

        rel = os.path.relpath(path, BASE_DIR)
        lang = os.path.basename(os.path.dirname(path))
        title = meta.get("title") or first_heading(body, os.path.splitext(os.path.basename(path))[0])

        meta = dict(meta)  # Kopie, Original unangetastet
        meta.setdefault("title", title)
        meta.setdefault("language", lang)
        if not had_fm:
            meta["provenance"] = "none"
            meta["source_file"] = rel
            meta["approx_words"] = len(body.split())
        else:
            meta.setdefault("provenance", "yaml-frontmatter")
            meta.setdefault("source_file", rel)

        article = str(meta.get("article") or "")
        style = str(meta.get("style") or "Narrative")
        instruction = (
            f"Synthetisiere eine Erzählung basierend auf Artikel {article or 'UDHR'} "
            f"im Stil {style} unter strikter Wahrung der Schadensminimierung."
        )

        records.append({
            "instruction": instruction,
            "input": article,
            "output": body,
            "meta": meta,
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with_fm = sum(1 for r in records if r["meta"].get("provenance") == "yaml-frontmatter")
    audited = sum(1 for r in records
                  if (r["meta"].get("guardrail_audit") or {}).get("passed") is True
                  or r["meta"].get("passed") in (True, "true"))
    print(f"Exportiert : {len(records)} Eintraege -> {OUTPUT_FILE}")
    print(f"  mit YAML-Frontmatter : {with_fm}")
    print(f"  Altbestand (ohne)    : {len(records) - with_fm}")
    print(f"  Audit belegt (passed): {audited}")
    if skipped:
        print(f"  uebersprungen (leer) : {len(skipped)} -> {', '.join(skipped[:5])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
