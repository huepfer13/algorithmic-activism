#!/usr/bin/env bash
# sync_corpus.sh — bewusster, manueller Corpus-Publish (GitHub -> Pages + Hugging Face).
#
# WARUM MANUELL:
#   Der Daemon erzeugt ~34 Tales/Stunde. Liesse man ihn automatisch pushen, waeren das
#   ~82 Pushes/Tag — und jeder Push loest den Pages-Build UND den Hugging-Face-Upload
#   aus (dataset.jsonl, derzeit ~6,5 MB und mit jedem Lauf wachsend). Dieses Skript
#   macht daraus einen kontrollierten Batch, den ein Mensch ausloest.
#
# WAS ES TUT (die Reihenfolge ist wichtig, siehe Bugfix unten):
#   1. prueft, ob AUSSERHALB von menschenrechte_tales/ uncommittete Aenderungen liegen -> Abbruch
#   2. prueft, ob ueberhaupt Tales anstehen -> sonst Ende ohne Aenderung
#   3. committet ausschliesslich menschenrechte_tales/  (bewusst KEIN `git add -A`:
#      quarantine/ mit abgelehntem Guardrail-Output bleibt unberuehrt)
#      ERST committen, DANN rebasen: `git pull --rebase` verweigert bei uncommitteten
#      Aenderungen — und die gibt es durch den laufenden Daemon immer.
#   4. holt origin/main und rebast NUR, wenn wir wirklich hinterher sind (--autostash
#      fuer Dateien, die der Daemon waehrenddessen neu schreibt)
#   5. pusht — erst das startet Pages-Build und Hugging-Face-Upload
#
# AUFRUF:
#   scripts/sync_corpus.sh [--dry-run]      # --dry-run: nur fetch + Bericht, keine Aenderung
#
# AUSGABE (Beleg):
#   Anzahl Tales vorher/nachher, Anzahl veroeffentlichter Dateien, Commit-Hash,
#   und der Hinweis, dass der Push den Workflow (Pages + HF-Sync) startet.
#
# VORAUSSETZUNGEN: git mit Push-Recht auf origin/main; Aufruf aus dem Repo (wechselt selbst dorthin).
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
TALES_DIR="menschenrechte_tales"

say() { printf '%s\n' "$*"; }
die() { printf '\n[ABBRUCH] %s\n' "$*" >&2; exit 1; }

say "== Corpus-Sync =="
say "Repo : $REPO_ROOT"
say "Modus: $([[ $DRY_RUN -eq 1 ]] && echo 'DRY-RUN (aendert nichts)' || echo 'ECHT (committet und pusht)')"

# --- 1. Fremde uncommittete Aenderungen? -------------------------------------
# Erlaubt ist nur menschenrechte_tales/ (dort schreibt der Daemon).
FREMD="$(git status --porcelain | grep -Ev '^.. "?menschenrechte_tales/' || true)"
if [[ -n "$FREMD" ]]; then
  say ""
  say "Uncommittete Aenderungen AUSSERHALB von $TALES_DIR/:"
  say "$FREMD"
  die "Erst aufraeumen — dieses Skript veroeffentlicht nur Tales."
fi

# --- 2. Was steht an? --------------------------------------------------------
PENDING="$(git status --porcelain -- "$TALES_DIR/" | wc -l | tr -d ' ')"
BEFORE="$(find "$TALES_DIR" -name '*.md' | wc -l | tr -d ' ')"
say ""
say "Bestand: $BEFORE Tale-Dateien, davon anstehend: $PENDING"
if [[ "$PENDING" -eq 0 ]]; then
  say "Nichts zu veroeffentlichen."
  exit 0
fi

# Hinweis (nicht blockierend): enthaelt eine anstehende Datei ein fehlgeschlagenes Audit?
BAD_AUDIT="$(git status --porcelain -- "$TALES_DIR/" | sed 's/^...//' | tr -d '"' | while read -r f; do
  [[ -f "$f" ]] && grep -l 'passed:[[:space:]]*false' "$f" 2>/dev/null
done | wc -l | tr -d ' ')"
if [[ "$BAD_AUDIT" -gt 0 ]]; then
  say "WARNUNG: $BAD_AUDIT anstehende Datei(en) mit 'passed: false' — sie wuerden MIT veroeffentlicht."
fi

if [[ $DRY_RUN -eq 1 ]]; then
  say ""
  say "--dry-run: kein commit, kein push."
  git fetch -q origin main
  say "Abstand zu origin/main: $(git rev-list --left-right --count origin/main...HEAD | awk '{print $1" hinter uns, "$2" voraus"}')"
  say "Erste 10 anstehende Dateien:"
  git status --porcelain -- "$TALES_DIR/" | head -10
  exit 0
fi

# --- 3. ERST committen (sonst verweigert der Rebase) -------------------------
git add "$TALES_DIR/"
git diff --cached --quiet && die "Nichts gestaged — unerwarteter Zustand."
COMMIT_MSG="feat(tales): sync batch of $PENDING generated tales"
git commit -q -m "$COMMIT_MSG"
say ""
say "Committet: $(git rev-parse --short HEAD) — $COMMIT_MSG"

# --- 4. Nur rebasen, wenn wir hinter origin/main liegen ----------------------
git fetch -q origin main
if [[ "$(git rev-list --count HEAD..origin/main)" -gt 0 ]]; then
  say "origin/main ist voraus -> git rebase --autostash origin/main"
  say "(autostash legt Tales beiseite, die der Daemon WAEHREND des Rebase schreibt)"
  git rebase --autostash origin/main \
    || die "Rebase fehlgeschlagen — es wurde NICHTS gepusht. Manuell klaeren (git rebase --abort), dann erneut aufrufen."
fi

# --- 5. Push (startet Pages + HF-Sync) --------------------------------------
git push origin main

AFTER="$(find "$TALES_DIR" -name '*.md' | wc -l | tr -d ' ')"
say ""
say "== Veroeffentlicht =="
say "Commit : $(git rev-parse --short HEAD)"
say "Tales  : $BEFORE -> $AFTER (in diesem Batch: $PENDING)"
say ""
say "Der Push auf main startet jetzt 'Deploy Algorithmic Activism Reader':"
say "  Pages-Deploy + Upload von dataset.jsonl nach hardtoneselector/algorithmic-activism-corpus."
say "Beleg: gh run list -R huepfer13/algorithmic-activism -L 1"
