# TODO — Miglioramenti da implementare

Generato il 2026-04-14. Aggiornato il 2026-04-25.

---

## ✅ Recentemente completati (2026-04-25)

### Sessione 1 — port da `test_claude/`

- **`mp3widget.py:apply_layout` — widget rimossi non nascosti**
  Il loop ora chiama `setParent(None)` su ogni widget rimosso dal layout,
  così quelli non re-aggiunti dal layout successivo spariscono davvero
  invece di restare nella loro posizione precedente.

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
  `on_remove_clicked` e `MainApp.clear_layout` ora lo usano — `clear_layout`
  prima cancellava solo `mp3file.cleanup()` lasciando i thread del
  `WaveformService` orfani (bug latente risolto).

### Sessione 2 — code review

- **B1 — Round-trip save/load del volume non idempotente**
  `Mp3Widget.apply_state()` ora applica `gain` PRIMA di `volume`. Questo
  evita che `set_gain` ricalcoli `actual_volume` collassando lo slider ad
  ogni save/reload quando `gain ≠ 1.0`.

- **B2 — `RmsAnalyzerThread` orfano dopo cleanup**
  `Mp3File.cleanup()` ora disconnette `analysis_done` e attende il thread
  con `wait()`. Prima, una rimozione di widget durante una normalizzazione
  causava emissioni di segnale verso slot su widget già `deleteLater`-ati.

- **B3 — Burst audibile a inizio fade-in + lambda fragile**
  `set_volume(0)` ora avviene PRIMA di `_backend.play()`. La guardia
  `controller is self.fade_controller and (set_volume(0), controller.start())`
  è sostituita dal metodo esplicito `_start_fade_if_current(controller)`.
  Risolve anche il vecchio TODO #1 critico.

- **B5 — `closeEvent` non chiamava `shutdown()` sui widget**
  Ora ferma il poll timer e chiama `widget.shutdown()` su tutti i widget
  prima di accettare l'evento. Il branch Cancel ritorna early.

- **R1 — Drag handle troppo ampio**
  Il drag dei widget parte solo se il click iniziale era sul `filename_label`
  (verificato via `childAt(pos)`). Prima qualunque click + piccolo movimento
  attivava il drag, sottraendo eventi ai pulsanti.

- **R4 — `GridManager` non aggiungeva row stretch sui buchi**
  `update_column_stretches` ora setta anche `setRowStretch(r, 1)` per tutte
  le righe da 0 a `max_occupied_row`. Le righe oltre la max occupata
  vengono lasciate intoccate per non comprimere righe già espanse.

- **R5 — Cache waveform inutilizzata**
  `generate_waveform_mem` ora legge/scrive la cache su disco (chiave
  `<md5>_<width>.jpg`) quando `gain == 1.0`. Per gain ≠ 1.0 la waveform
  viene rigenerata in memoria senza cache (gain è un trasformo visivo
  runtime, non vale la pena cachare per ogni valore distinto). Reload
  del progetto ora riprende le waveform da `/tmp` in microsecondi.

- **R6 — Log spam su errori di poll**
  Il livello di log per i singoli errori in `update_progress_bar` è
  sceso da `error` a `debug`; solo il messaggio finale di disabilitazione
  resta `warning`. Niente più 10 errori al secondo che riempiono lo stderr.

- **Timer globale di poll** (segnato come "implementato, da testare" nel
  TODO precedente): confermato implementato in `MainApp._tick_progress`,
  un singolo `QTimer` itera su tutti i widget invece di un timer per widget.

---

## 🟠 Problemi di robustezza ancora aperti

- **B4 — `WaveformService` può accumulare thread su rapide variazioni di gain**
  `_start_thread` cancella i thread vecchi ma non li attende; threads
  cancellati prima dell'inizio del `run()` non hanno effetto, ma se il
  cancel arriva dopo `wf.generate_waveform_mem` ha già cominciato la
  decodifica, il thread completa comunque. Mitigato dal debounce di 300ms
  e dalla cache disco (R5), ma sotto stress (slider gain mosso veloce)
  può esserci CPU spike. Valutare `QThreadPool.globalInstance()` con
  `setMaxThreadCount(1-2)`.

- **R2 — Workaround volume su play_pause non documentato**
  [mp3file.py:574-575](mp3file.py#L574-L575): il
  `QTimer.singleShot(100, lambda: self.set_volume(self.actual_volume))`
  dopo `play()` è probabilmente un workaround per VLC che reimposta il
  volume al play. Andrebbe almeno commentato e idealmente applicato solo
  a `_VlcBackend`, non agli altri backend.

- **R3 — `ClickableProgressBar.mousePressEvent` divisione per zero**
  Se `total_width == 0` (widget appena creato e non ancora dimensionato)
  → `ZeroDivisionError`. Aggiungere guard `if total_width <= 0: return`.

- **`waveform_service.py` — `generate()` blocca il main thread su cold cache**
  Mitigato dal fix R5 per i reload, ma il primo caricamento di un file
  grande blocca ancora la UI. Valutare esecuzione in background con uno
  stato "loading" nella progress bar (placeholder grigio finché pronto).

---

## 🟡 Qualità e manutenibilità

- **`mp3widget.py:262-308` — duplicazione TOUCH / STANDARD in `apply_layout`**
  I due blocchi sono al ~95% identici. Estrarre la parte comune in un
  metodo privato (es. `_layout_with_fade_presets`).

- **Q7 — Stretch column residuo dopo TOUCH→STANDARD**
  TOUCH setta esplicitamente `setColumnStretch(0..11)` con valori
  specifici. STANDARD non li resetta → eredita il pattern di TOUCH.
  Aggiungere reset esplicito a `apply_layout`.

- **Q2 — `waveform.py` contiene 5 implementazioni**
  `generate_waveform`, `_pillow`, `_rosa`, `_HS`, `_mem`. Solo `_mem` è
  usata in produzione (`_rosa` come fallback raro). Le altre sono
  spike/benchmark — spostare in `bench_render.py` o cancellare.

- **Q3 — Lambda capture pattern fragile**
  Numerosi `lambda w=mp3_widget: ...` per evitare il problema della
  closure tardiva. Funziona ma è anti-pattern: meglio usare il signal
  direttamente con `self.sender()` come riferimento al widget.

- **Q4 — Logger inconsistente**
  Alcune classi usano `self.logger = logging.getLogger(__name__)`,
  altre fanno `logging.getLogger(__name__).debug(...)` inline. Convergere
  su un pattern.

- **Q5 — Documentazione metodi pubblici**
  `Mp3File.fade_in`, `fade_out`, `set_volume`, `set_gain` hanno signature
  complesse senza docstring. Es. `fade_in(duration, end_volume)` —
  l'unità di `duration` (secondi) si scopre solo leggendo `FadeController`.

- **Q6 — `requirements.txt` minimale**
  ~55 byte. Manca `numpy`, `Pillow`, `python-vlc`, `python-mpv`,
  `pygobject` (per gstreamer). Con il fallback stub ora l'app gira senza
  i backend nativi, ma gli utenti che vogliono audio reale devono saperlo.

---

## 🔵 Suggerimenti architetturali

- **A1 — `FadeController` basato sul tempo trascorso**
  Attualmente usa `step_index/steps`: preciso solo se i tick QTimer
  arrivano puntuali. Sotto carico (dragging UI, GC pause) la durata reale
  del fade si dilata. test_claude usa `elapsed += dt` che è robusto a
  tick mancati. Vedere `_Fade` in `test_claude/audio_widget.py:91-107`.

- **A2 — Pool di QThread riutilizzabili**
  Ogni `WaveformThread`, `RmsAnalyzerThread`, `_BackendLoader` crea un
  thread nuovo. Con "Normalize All" su 20 widget, 20 thread paralleli
  saturano l'I/O leggendo lo stesso file. `QThreadPool.globalInstance()`
  con `setMaxThreadCount(4)` darebbe controllo.

- **A5 — Costanti hardcoded sparpagliate**
  `48` (PROGRESS_HEIGHT), `1500` (waveform width), `100` (fade tick ms),
  `50` (poll ms), `300` (debounce ms), `2*1024*1024` (small file). Raccoglierle
  in `constants.py`.

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
