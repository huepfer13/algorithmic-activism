#!/usr/bin/env bash
# sync_corpus.sh — bewusster, manueller Corpus-Publish (GitHub -> Pages + Hugging Face).
#
# WARUM MANUELL:
#   Der Daemon erzeugt ~34 Tales/Stunde. Liesse man ihn automatisch pushen, waeren das
#   ~82 Pushes/Tag — und jeder Push loest den Pages-Build UND den Hugging-Face-Upload
#   aus (dataset.jsonl, derzeit ~6,5 MB und mit jedem Lauf wachsend). Dieses Skript
#   macht daraus einen kontrollierten Batch, den ein Mensch ausloest.
#
# WAS ES TUT:
#   1. prueft, ob AUSSERHALB von menschenrechte_tales/ uncommittete Aenderungen liegen -> Abbruch
#   2. holt den aktuellen Stand von origin/main (git pull --rebase)
#   3. stagt ausschliesslich menschenrechte_tales/  (bewusst KEIN `git add -A`:
#      quarantine/ mit abgelehntem Guardrail-Output bleibt unberuehrt)
#   4. committet und pusht NUR, wenn wirklich etwas ansteht
#
# AUFRUF:
#   scripts/sync_corpus.sh [--dry-run]      # --dry-run zeigt alles, aendert nichts
#
# AUSGABE (Beleg):
#   Anzahl Tales vorher/nachher, Anzahl neu veroeffentlichter Dateien, Commit-Hash,
#   und der Hinweis, dass der Push den Workflow (Pages + HF-Sync) startet.
#
# VORAUSSETZUNGEN: git mit Push-Recht auf origin/main; dieses Skript gehoert in den
#   Repo-Root ausgefuehrt (es wechselt selbst dorthin).
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

# --- 2. Aktuellen Stand holen ------------------------------------------------
say ""
say "-> git pull --rebase origin main"
git pull --rebase origin main || die "pull --rebase fehlgeschlagen (Konflikt?) — bitte manuell klaeren."

# --- 3. Was steht an? --------------------------------------------------------
PENDING="$(git status --porcelain -- "$TALES_DIR/" | wc -l | tr -d ' ')"
BEFORE="$TALES_DIR: $(find "$TALES_DIR" -name '*.md' | wc -l | tr -d ' ') Dateien"
if [[ "$PENDING" -eq 0 ]]; then
  say ""
  say "Nichts zu tun: keine neuen oder geaenderten Tales."
  say "$BEFORE"
  exit 0
fi
say ""
say "Anstehend: $PENDING Datei(en) in $TALES_DIR/"
say "$BEFORE"

# Hinweis (nicht blockierend): enthaelt eine anstehende Datei ein fehlgeschlagenes Audit?
BAD_AUDIT="$(git status --porcelain -- "$TALES_DIR/" | sed 's/^...//' | tr -d '"' | while read -r f; do
  [[ -f "$f" ]] && grep -l 'passed:[[:space:]]*false' "$f" 2>/dev/null
done | wc -l | tr -d ' ')"
if [[ "$BAD_AUDIT" -gt 0 ]]; then
  say ""
  say "WARNUNG: $BAD_AUDIT anstehende Datei(en) mit 'passed: false' im Guardrail-Audit."
  say "         Sie werden MIT veroeffentlicht, wenn Sie fortfahren. Pruefen Sie das bewusst."
fi

if [[ $DRY_RUN -eq 1 ]]; then
  say ""
  say "--dry-run: staging/commit/push uebersprungen."
  say "Beispiel der ersten 10 anstehenden Dateien:"
  git status --porcelain -- "$TALES_DIR/" | head -10
  exit 0
fi

# --- 4. Stagen, committen, pushen -------------------------------------------
git add "$TALES_DIR/"
git diff --cached --quiet && die "Nichts gestaged — unerwarteter Zustand."

COMMIT_MSG="feat(tales): sync batch of $PENDING generated tales"
git commit -q -m "$COMMIT_MSG"
SHA="$(git rev-parse --short HEAD)"
git push origin main

AFTER="$TALES_DIR: $(find "$TALES_DIR" -name '*.md' | wc -l | tr -d ' ') Dateien"
say ""
say "== Veroeffentlicht =="
say "Commit : $SHA ($COMMIT_MSG)"
say "Vorher : $BEFORE"
say "Nachher: $AFTER"
say ""
say "Der Push auf main startet jetzt den Workflow 'Deploy Algorithmic Activism Reader':"
say "  Pages-Deploy + Upload von dataset.jsonl nach hardtoneselector/algorithmic-activism-corpus."
say "Beleg: gh run list -R huepfer13/algorithmic-activism -L 1"
