# Automation Agent Backlog

## Kontext
Das Repository besitzt derzeit eine MVP-Orchestrierung mit Platzhalter-Fallback-Code. Ziel ist der Aufbau eines autonomen Entwicklungsagenten, der reale Feature-Anfragen verstehen, umsetzen, testen und ausliefern kann.

## Unmittelbare Aufgaben (0-1 Iterationen)
1. **Fallback ersetzen** – `agent/orchestrator.py:add_example_code` soll ein sinnvolles Artefakt (z. B. Run-Log) erzeugen statt Demo-Code zu überschreiben.
2. **Run-Logging etablieren** – Persistente Protokollierung jedes Agentenlaufs (Zeitstempel, Branch, Kurzbeschreibung der Aktionen).
3. **Prompt-Alignment prüfen** – Sicherstellen, dass System- und User-Prompts konsistent sind und auf die neuen Ziele einzahlen.

## Kurzfristige Ziele (1-3 Iterationen)
- **Task Intake Pipeline**: Mechanismus entwerfen, um externe Anforderungen (Datei, Issue, API) einzulesen und in umsetzbare Arbeitspakete zu überführen.
- **Kontextmodellierung**: Werkzeuge bereitstellen, die Codebasis (Module, Tests, Abhängigkeiten) automatisiert zu kartieren.
- **Qualitätssicherung ausbauen**: Zusätzliche Checks (Coverage, statische Analysen) integrieren und automatisieren.

## Mittelfristige Perspektiven (>3 Iterationen)
- **Integrationen**: Anbindung an externe Systeme (z. B. GitHub, Ticketing, Deployment) vorbereiten.
- **Planungs- und Review-Automatisierung**: Automatisches Erstellen von Design-Dokumenten, PR-Beschreibungen und Reviews.
- **Self-Healing**: Mechanismen, um fehlgeschlagene Läufe zu analysieren und Maßnahmen abzuleiten.

## Offene Fragen
- Welche externen APIs oder Zugangsdaten werden benötigt, um Aufgabenquellen anzubinden?
- Wie soll der Agent langfristig Deployments oder Releases orchestrieren?

> Aktualisiere diesen Backlog nach jeder Iteration: erledigte Punkte abhaken, neue Erkenntnisse ergänzen, Prioritäten justieren.