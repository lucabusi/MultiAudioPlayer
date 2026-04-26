# TODO — Miglioramenti da implementare

Generato il 2026-04-14. Aggiornato il 2026-04-26.

> Per i fix già applicati vedere `git log` (commit `8d2b815`, `6b4b8af`,
> `dbd86f2`, `b555898`).

---

## 🟠 Problemi di robustezza ancora aperti

- **B4 — `WaveformService` può accumulare thread su rapide variazioni di gain**
  `_start_thread` cancella i thread vecchi ma non li attende; threads
  cancellati prima dell'inizio del `run()` non hanno effetto, ma se il
  cancel arriva dopo `wf.generate_waveform_mem` ha già cominciato la
  decodifica, il thread completa comunque. Mitigato dal debounce di 300ms
  e dalla cache disco, ma sotto stress (slider gain mosso veloce) può
  esserci CPU spike. Valutare `QThreadPool.globalInstance()` con
  `setMaxThreadCount(1-2)`.

- **`waveform_service.py` — `generate()` blocca il main thread su cold cache**
  Mitigato dalla cache disco per i reload, ma il primo caricamento di un
  file grande blocca ancora la UI. Valutare esecuzione in background con
  uno stato "loading" nella progress bar (placeholder grigio finché pronto).

---

## 🟡 Qualità e manutenibilità

- **Q3 — Lambda capture pattern fragile**
  Numerosi `lambda w=mp3_widget: ...` per evitare il problema della
  closure tardiva. Funziona ma è anti-pattern: meglio usare il signal
  direttamente con `self.sender()` come riferimento al widget.

---

## 🔵 Suggerimenti architetturali

- **A2 — Pool di QThread riutilizzabili**
  Ogni `WaveformThread`, `RmsAnalyzerThread`, `_BackendLoader` crea un
  thread nuovo. Con "Normalize All" su 20 widget, 20 thread paralleli
  saturano l'I/O leggendo lo stesso file. `QThreadPool.globalInstance()`
  con `setMaxThreadCount(4)` darebbe controllo.

- **`project_manager.py` — nessun versioning del formato JSON**
  C'è il campo `"version"` ma non viene usato per migrare progetti
  vecchi. Quando si cambia il formato (es. dopo il fix B1, i file
  pre-fix hanno volume "post-gain" da convertire), serve una migrazione.

---

## Note architetturali (refactoring a lungo termine)

- **A4 — Test**
  Zero test automatizzati. Ora che lo stub backend esiste, si può
  testare `Mp3File` senza VLC/mpv. Coverage minima utile:
  - `set_gain` mantiene effective_volume invariato
  - `apply_state(to_state())` è idempotente
  - `FadeController` raggiunge esattamente `end_volume` dopo `duration` s
  - `cleanup` aspetta tutti i thread

- **Testabilità widget**: nessun componente è testabile in isolamento.
  Introdurre dependency injection per `Mp3File` in `Mp3Widget`.

- **`FadeController`**: non valida `end_volume > start_volume` per
  fade-in né `start_volume > end_volume` per fade-out, e non gestisce
  esplicitamente `duration=0`. Aggiungere guard clause.
