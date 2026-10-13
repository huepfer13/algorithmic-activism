# Deployment-Vorlage (anonymisiert)

Diese Datei beschreibt das Betriebsmuster für die Generierung — **ohne** Hostnamen, IP-Adressen,
Container-Nummern oder private Benutzernamen. Die echten Units liegen auf dem ausführenden Knoten
unter `~/.config/systemd/user/` und gehören **nicht** ins Repository.

## Wo läuft was

Generierung, Modellaufrufe und `git push` laufen auf dem Rechner, auf dem **Repository,
Git-Zugang und Modell-Endpunkte** liegen. Der Orchestrierungs-Host (Kanban/Board) ist davon
getrennt und führt keine Generierungs- oder Transportlast. Ein Timer gehört immer auf die Seite,
auf der die Daten liegen — nicht dorthin, wo die Aufträge verwaltet werden.

## Taktgeber (systemd User Units)

`algorithmic-chapter.service` — ein Kapitel je Lauf:

```ini
[Unit]
Description=Write one generated chapter (hourly tick)
OnFailure=algorithmic-alert@%n.service

[Service]
Type=oneshot
WorkingDirectory=%h/algorithmic-activism
# flock: derselbe Lock wie im Runner. -w wartet kurz, statt bei Überhang zu scheitern.
ExecStart=/usr/bin/flock -w 300 %h/algorithmic-activism/.rotation.lock \
          /usr/bin/python3 %h/algorithmic-activism/scripts/run_model_rotation.py \
          --kapitel 1 --zufall --push
TimeoutStartSec=7200
StandardOutput=journal
StandardError=journal
SyslogIdentifier=algorithmic-chapter
```

`algorithmic-chapter.timer`:

```ini
[Unit]
Description=Hourly tick for one generated chapter

[Timer]
OnCalendar=*-*-* *:00:00
Persistent=true
AccuracySec=1min
Unit=algorithmic-chapter.service

[Install]
WantedBy=timers.target
```

Ein zweiter Taktgeber nach demselben Muster legt täglich ein neues Buchprojekt an
(`--neues-buch --sprachen <liste>`). Aktivierung:

```bash
systemctl --user daemon-reload
systemctl --user enable --now algorithmic-chapter.timer
loginctl show-user "$USER" | grep Linger   # ohne Linger nur bei aktiver Sitzung
```

## Wächter ohne Tokenkosten

Statt eines Modellaufrufs prüft ein **Skript** den Takt und meldet nur im Fehlerfall. Im
Hermes-Cron ist das ein No-Agent-Job: leere Ausgabe bedeutet „nichts zustellen". Geprüft werden die
Wahrheit, nicht der Zeitplan — das `Result` der Units, Alter und Exit-Code des letzten
Protokolleintrags, frische Alarmzeilen. Alarm nur bei Exit ≠ 0, eine Zeile ins Protokoll, kein Retry.

## Regeln, die sich im Betrieb bewährt haben

- **Ein Kapitel je Lauf mit Deckel** (`--kapitel 1`), damit ein Lauf terminiert und der nächste Takt
  unabhängig bleibt.
- **`flock -w`, nicht `flock -n`:** ein kurzer Überhang darf keinen Fehlalarm auslösen.
- **Push mit Timeout**, sonst blockiert ein hängender Netzaufruf den ganzen Takt.
- **`Persistent=true`:** verpasste Takte (Rechner aus) werden nachgeholt.
- **Alarm nur bei Fehlschlag** — Erfolgsmeldungen im Minutentakt erziehen dazu, sie zu ignorieren.
- **Keine stillen Sprach-Fallbacks:** fehlt die Zielsprachen-Datei, bricht der Lauf mit Klartext ab,
  statt auf die Referenzsprache auszuweichen.
