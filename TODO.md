# TODO — Miglioramenti da implementare

Generato il 2026-04-14. Aggiornato il 2026-04-19.

---

## 🔴 Bug critici

- **`mp3file.py` — `fade_in` con lambda fragile**
  La guardia `controller is self.fade_controller and (self.set_volume(0), controller.start())`
  è difficile da leggere e potenzialmente errata. Refactoring in metodo esplicito.

---

## 🟠 Problemi di robustezza


- **`waveform_service.py` — `generate()` blocca il main thread**
  La generazione sincrona in `create_progress_bar()` blocca la UI.
  Per file vicini alla soglia 2MB è percepibile. Valutare esecuzione in background
  con stato "loading" nella progress bar.

---

## 🟡 Qualità e manutenibilità

- **`mp3widget.py:307-351` — duplicazione TOUCH / STANDARD in `apply_layout`**
  I due blocchi sono quasi identici. Estrarre la parte comune in un metodo privato.

- **`mp3widget.py` — `apply_layout` non nasconde i widget rimossi**
  I widget tolti dal layout restano visibili finché non vengono riposizionati (`pass` nel loop).
  Aggiungere `widget.hide()` / `widget.show()` espliciti.



---

## 🔵 Suggerimenti architetturali

implementato, da testare: - **Timer globale invece di un timer per widget**
  Ogni `Mp3Widget` ha il proprio `QTimer` a 50ms. Con molti widget attivi il numero
  di tick/secondo cresce linearmente. Un singolo timer condiviso in `MainApp` è più efficiente.

- **`project_manager.py` — nessun versioning del formato JSON**
  Aggiungere un campo `"version"` al file di progetto per gestire la compatibilità futura.

---

## Note architetturali (refactoring a lungo termine)

- **Testabilità**: nessun componente è testabile in isolamento.
  Introdurre dependency injection per `Mp3File` in `Mp3Widget`.
- **`FadeController`**: non valida che `end_volume > start_volume`,
  e non gestisce `duration=0`. Aggiungere guard clause.
