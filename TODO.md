# TODO — Miglioramenti da implementare

Generato il 2026-04-14. Aggiornato il 2026-04-25.

---

## ✅ Recentemente completati (2026-04-25)

Confronto con il prototipo `test_claude/` e port delle migliorie:

- **`mp3widget.py:apply_layout` — widget rimossi non nascosti**
  Risolto: il loop ora chiama `setParent(None)` su ogni widget rimosso
  dal layout, così quelli non re-aggiunti dal layout successivo
  spariscono davvero invece di restare nella loro posizione precedente.

- **Stub backend fallback in `mp3file.py`**
  Aggiunta classe `_StubBackend` che simula la riproduzione tramite
  `time.monotonic()`. `_VlcBackend`, `_GStreamerBackend`, `_MpvBackend`
  ricadono sullo stub se la libreria nativa manca, invece di sollevare.
  Utile per sviluppo headless e migliora la testabilità del player.

- **`Mp3Widget.to_state()` / `apply_state()` / `set_gain()`**
  Serializzazione dello stato del widget incapsulata. `ProjectManager.save`
  e `MainApp.load_project` non accedono più a `widget.spinboxGain`,
  `widget.mp3file.gain`, `widget.fade_time`, ecc.

- **`Mp3Widget.shutdown()`**
  Cleanup unificato (disconnect waveform, cancel waveform service,
  `mp3file.cleanup()`) ognuno in `try/except` indipendente.
  `on_remove_clicked` e `MainApp.clear_layout` ora lo usano —
  `clear_layout` prima cancellava solo `mp3file.cleanup()` lasciando
  i thread del `WaveformService` orfani (bug latente risolto).

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
