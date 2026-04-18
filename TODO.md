# TODO — Miglioramenti da implementare

Generato il 2026-04-14. Continuazione dell'analisi e refactoring in corso.

---


## Note architetturali (refactoring a lungo termine)

- **Testabilità**: nessun componente è testabile in isolamento.
  Introdurre dependency injection per `Mp3File` in `Mp3Widget`.
- **`FadeController`**: non valida che `end_volume > start_volume`,
  e non gestisce `duration=0`. Aggiungere guard clause.
