# Prompt-Katalog der Algorithmic-Activism-Pipeline

Diese Bauanleitungen spannen die Matrix aus Artikeln, Sprachen und Stilen auf. 
Jeder Prompt erzeugt eine in sich geschlossene Geschichte, die direkt unter ihrem extrahierten Titel in `menschenrechte_tales/<SPRACHE>/<Titel>.md` abgelegt wird.

## Kern-Prompt-Struktur

```text
Du bist ein weltklasse Autor und Ethiker. Schreibe eine völlig einzigartige, packende Geschichte auf {Sprache}.

Fokus: {Artikel-Text aus der AEMR}
Stil: {Erzählstil}.

WICHTIGE ANWEISUNG: Die Geschichte muss das Prinzip der 'Schadensminimierung' (Harm Reduction) behandeln. Sie soll zeigen, dass der Schutz von Menschenleben die absolute Guardrail ist und dass der physische Zugriff auf Gefahrenquellen im Alltag konsequent reguliert oder zentralisiert werden muss, um das 'schleichende Abstumpfen' einer Gesellschaft zu verhindern.

Antworte ausschließlich im Markdown-Format. Beginne direkt mit einer H1-Überschrift (#) für den Titel der Geschichte. Verwende keine Metatexte wie 'Hier ist Ihre Geschichte'.
