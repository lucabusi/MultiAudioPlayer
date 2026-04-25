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

### Sessione 3 — qualità e organizzazione

- **Q4 — Logger inconsistente**
  Tutti i moduli ora seguono il pattern Pythonico `logger = logging.getLogger(__name__)`
  a livello modulo. Rimosse tutte le `self.logger = ...` in `__init__` (mainapp,
  mp3widget, mp3file, project_manager) e tutte le chiamate inline
  `logging.getLogger(__name__).X(...)`. `_StubBackend._log` rimosso (il nome del
  backend è già nel messaggio). `ProjectManager.__init__` eliminato (era solo un
  placeholder per il logger).

- **Q7 — Reset column stretches in `apply_layout`**
  `apply_layout` ora azzera `setColumnStretch(c, 0)` per c in 0..11 prima delle
  branche TOUCH/STANDARD/COMPACT — niente più stretch residui ereditati da TOUCH.

- **Q5 — Docstring sui metodi pubblici di `Mp3File`**
  Aggiunte docstring a `fade_in`, `fade_out`, `set_volume`, `set_gain` con unità
  di misura (secondi), range (0..100), e semantica del gain (mantiene effective
  volume invariato).

- **Q6 — `requirements.txt` aggiornato**
  Aggiunto `soundfile` (era mancante!), commenti che separano dipendenze richieste
  da backend audio opzionali (python-mpv, PyGObject), nota sul fallback stub.

- **A5 — Costanti hardcoded centralizzate in `__init__.py`**
  Nuovo file con `POLL_INTERVAL_MS`, `FADE_TICK_MS`, `FADE_STARTUP_DELAY_MS`,
  `PROGRESS_BAR_HEIGHT`, `WAVEFORM_WIDTH`, `WAVEFORM_PREVIEW_WIDTH`,
  `WAVEFORM_DEBOUNCE_MS`, `LARGE_FILE_BYTES`. Importate con `from __init__ import ...`
  da mainapp/mp3file/mp3widget/waveform/waveform_service. Bonus: `FadeController.steps`
  ora deriva da `FADE_TICK_MS` (`int(duration * 1000 / FADE_TICK_MS)`) invece del
  precedente hardcode `int(duration * 10)`.

- **R3 — `ClickableProgressBar.mousePressEvent` divisione per zero**
  Aggiunto guard `if total_width <= 0: return` per gestire il widget non ancora
  dimensionato. Aggiunto anche guard `if self.maximum() > 0` sul successivo
  `clicked.emit(new_value / self.maximum())` per coerenza.

- **R2 — Workaround volume su `play_pause` ora documentato e VLC-only**
  Aggiunto attributo di classe `_PlaybackBackend.NEEDS_VOLUME_REAPPLY_ON_PLAY`
  (default `False`); `_VlcBackend` lo setta a `True` con commento sul perché
  (VLC reimposta il volume al massimo al primo `play()` finché il modulo audio
  output non è pronto). `Mp3File.play_pause` consulta il flag — GStreamer, MPV
  e lo stub non subiscono più il workaround inutile. Hardcode `100` sostituito
  da `FADE_STARTUP_DELAY_MS`.

- **Layout COMPACT/STANDARD ridisegnati come alternative distinte**
  Prima erano molto simili a TOUCH (~95% di duplicazione TOUCH↔STANDARD,
  TODO Q1). Ora:
  - COMPACT = striscia minimale a 2 righe (controlli + progress bar), niente
    fade/gain/normalize, slider volume orizzontale. Button con altezza Fixed.
    Pensato per playlist dense.
  - STANDARD = desktop classico a 3 righe (header / controlli / progress),
    tutti i controlli, slider volume orizzontale, button compatti. Pensato
    per uso mouse/keyboard.
  - TOUCH = invariato (slider verticale a destra, button espandibili).
  Refactor di `apply_layout` in tre helper privati `_apply_compact_layout`,
  `_apply_standard_layout`, `_apply_touch_layout` — risolve anche Q1.

- **Nuovo layout COMPACT_V (mixer-channel verticale)**
  Aggiunto il valore `WidgetLayout.COMPACT_V` con voce nel menu del layout
  switcher. Caratteristiche distintive:
  - sizePolicy verticale `Expanding` (l'unico layout che si allunga in altezza)
  - slider volume verticale (fader, centrato), prende lo spazio principale
  - **niente progress bar / waveform** (per richiesta esplicita)
  - controlli essenziali soli: layout-switch, remove, play, stop, tempo rimanente
  - 2 colonne strette, ~120-150px di larghezza
  Pensato per disposizioni a colonne tipo mixer multicanale.

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

- **`waveform_service.py` — `generate()` blocca il main thread su cold cache**
  Mitigato dal fix R5 per i reload, ma il primo caricamento di un file
  grande blocca ancora la UI. Valutare esecuzione in background con uno
  stato "loading" nella progress bar (placeholder grigio finché pronto).

---

## 🟡 Qualità e manutenibilità

- **Q2 — `waveform.py` contiene 5 implementazioni**
  `generate_waveform`, `_pillow`, `_rosa`, `_HS`, `_mem`. Solo `_mem` è
  usata in produzione (`_rosa` come fallback raro). Le altre sono
  spike/benchmark — spostare in `bench_render.py` o cancellare.

- **Q3 — Lambda capture pattern fragile**
  Numerosi `lambda w=mp3_widget: ...` per evitare il problema della
  closure tardiva. Funziona ma è anti-pattern: meglio usare il signal
  direttamente con `self.sender()` come riferimento al widget.

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
