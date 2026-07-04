# Piano (APPROVATO + IMPLEMENTATO): backend QMediaPlayer — 2026-07-04

> Esito: implementato con curva volume percettiva inclusa (richiesta utente,
> era nel fuori-scope). Suite 28/28. Resta il gate 6: verifica a orecchio.
> Quirk emerso nei test: su DirectShow il seek in PAUSA viene applicato alla
> ripresa; in riproduzione è affidabile (documentato nel docstring).

## Obiettivo

Nuovo backend `_QtBackend` basato su PyQt5.QtMultimedia.QMediaPlayer:
funziona out-of-the-box su Windows (WMF/DirectShow nativi, plugin già nel
wheel PyQt5 — verificato: dsengine.dll + wmfengine.dll presenti, Qt 5.15.2)
e su Linux (via GStreamer di sistema). Volume per-player software →
indipendente by design (niente problemi tipo mmdevice/sessione).

## Verifiche di realtà già fatte

- [x] `from PyQt5.QtMultimedia import QMediaPlayer` OK su questa macchina
- [x] Plugin mediaservice Windows presenti nel wheel PyQt5
- [x] Prototipo esistente in `future/Mp3_Player_qmediaplayer.py` (API base)

## Decisioni di design

1. **Threading (punto critico):** QMediaPlayer è un QObject con affinità di
   thread — NON può essere creato nel `_BackendLoader` (QThread worker che
   poi muore: segnali/timer resterebbero legati a un thread morto).
   Soluzione: flag di classe `REQUIRES_MAIN_THREAD = True`; per questi
   backend `Mp3File.__init__` costruisce sul main thread (l'init
   QMediaPlayer è comunque non bloccante: il media si carica async) ed
   emette `loaded` via `QTimer.singleShot(0, ...)` per preservare il
   contratto asincrono (i connect del widget avvengono prima del segnale).
   Fallback a `_StubBackend` se la costruzione fallisce, come nel loader.

2. **Durata asincrona:** `duration()` è valida solo dopo
   mediaStatus=LoadedMedia (arriva dopo il ready). Fix generale in
   `Mp3File.get_playback_info`: se `mp3_total_duration <= 0`, rileggila dal
   backend (~3 righe, robusto per ogni backend futuro; il poll da 50ms
   propaga il valore alla UI appena disponibile).

3. **Mappatura ABC → QMediaPlayer:**
   - `play/pause/stop` → diretti; play dopo EndOfMedia → `setPosition(0)` + play
   - `get_state` → `state()` + `mediaStatus()==EndOfMedia` → ENDED
   - `get_time_ms/get_duration_ms` → `position()/duration()` (già in ms)
   - `set_position(ratio)` → `setPosition(int(ratio * duration()))`
   - `set_volume` → `setVolume(clamp 0-100)` (lineare; curva percettiva
     logaritmica via `QAudio.convertVolume` = rifinitura opzionale futura)
   - `release` → `stop()` + `setMedia(QMediaContent())` + `deleteLater()`
   - `NEEDS_VOLUME_REAPPLY_ON_PLAY = False`
   - chiave registro: `'qt'`, alias `'qmediaplayer'`

## Step (ognuno con criterio di verifica)

- [x] 1. `_QtBackend` in mp3file.py + registrazione in `_BACKENDS`/alias
       (inclusa curva percettiva QAudio.convertVolume, richiesta utente)
- [x] 2. Percorso `REQUIRES_MAIN_THREAD` in `Mp3File.__init__` (+ fallback
       stub); 'vlc' continua a passare dal loader (suite invariata)
- [x] 3. Fix durata lazy in `get_playback_info` (durata 147768ms propagata
       async a Mp3File e label nel test)
- [x] 4. Test smoke: creazione main-thread, durata async, curva percettiva
       (50→<50, 0→0, 100→100), play/pausa/seek/stop, ENDED+replay,
       2 player volumi indipendenti — 28/28 verdi
- [x] 5. Docs: README, requirements.txt, commento mainapp.py:90, spec
       PyInstaller (hiddenimport PyQt5.QtMultimedia per l'import lazy)
- [x] 6. **Verifica a orecchio dell'utente su Windows**: passata — l'utente
       ha promosso 'qt' a backend di DEFAULT (mainapp.py:90, 2026-07-04)

## Fuori scope (decisioni separate, dopo il gate 6)

- Cambiare il default da 'vlc' a 'qt' su Windows (o catena 'auto' per OS)
- Selezione backend da CLI (`--backend`)
- Curva volume percettiva (QAudio.convertVolume)

## Rischi

- Qt 5.15 su Windows usa DirectShow (dsengine) di default: mp3 ok; se su
  qualche macchina mancassero codec DirectShow si può forzare WMF con
  `QT_MULTIMEDIA_PREFERRED_PLUGINS=windowsmediafoundation` (da testare al
  gate 6, solo se serve)
- Su Linux i wheel PyQt5 richiedono le lib GStreamer di sistema (di norma
  presenti sulle distro desktop); senza → fallback stub, comportamento già
  gestito
- Molti QMediaPlayer simultanei: WMF/DirectShow reggono bene N=10-20 tipici
  dell'app; il test dello step 4 usa più player insieme

---

# Refactor + bugfix da analisi architettura (2026-07-04)

Origine: `docs/architecture_analysis.md` (analisi completa pre-intervento).

## Piano

- [x] `__init__.py` → `constants.py` (S7): import sani, spec PyInstaller aggiornato
- [x] `waveform.py`: fix crash file corti (B1), cache envelope `.npz` con chiave path+mtime+size (B6), API `compute_envelope`/`render_envelope`
- [x] `waveform_service.py`: sempre asincrono (B8), envelope cachato in memoria → re-render gain sincrono senza re-decode (S6), `cancel()` non bloccante (B5)
- [x] `thread_registry.py` nuovo: tiene vivi i QThread in volo senza `wait()` bloccanti (B5/P3)
- [x] `mp3file.py`:
  - stub fallback spostato nel `_BackendLoader`, backend puri senza boilerplate `if self._stub` (S1)
  - `is_playing()` implementato una volta nella ABC (S2)
  - VLC: `stop()` prima di `play()` se stato Ended (P1)
  - fade lifecycle: stop/pausa fermano il fade e riallineano il volume allo slider (B2/S5)
  - reapply volume VLC anche in `fade_in` (P2)
  - `RmsAnalyzerThread` → `PeakAnalyzerThread` + segnale `analysis_failed` (B3/S8)
  - nuovo segnale `normalize_failed`; `cleanup()` non bloccante con flag `_closed` (P3)
  - alias backend (`gst`) separati dai canonici
- [x] `mp3widget.py`: connessi `loaded`/`load_error`/`normalize_failed` (B3/B4), waveform via segnale (niente decode sul main thread), rimossi `Mp3WidgetMimeData` (S3), macchina `_progress_error_count` (S4) e `volume_slider_value`, label tempi unificate
- [x] `mainapp.py`: drop via `event.source()` (S3), `save_project()` ritorna bool e `closeEvent` non chiude se il salvataggio richiesto fallisce/è annullato (B7)
- [x] `project_manager.py`: confronto versioni numerico con `_version_tuple` (P4)
- [x] `requirements.txt`/`README.md`: matplotlib solo bench, normalizzazione = peak, struttura aggiornata
- [x] repo: untrack `multiplayer.log` e `temp` (`git rm --cached`)
- [x] `bench_envelope.py`: adeguato al rename della funzione cache

## Potature post-refactor (2° passaggio)

Decisione: **multi-backend GStreamer/MPV resta** (feature futura; selezione
runtime da implementare, es. arg `--backend`).

- [x] `waveform.py`: rimossa `clear_waveform_cache` (mai chiamata)
- [x] `mp3file.py`: rimossi `Mp3File.is_ready`, `Mp3File.get_state` e
      `PlaybackState.ERROR` (nessun call-site esterno, verificato con grep
      su tutto il repo; VLC Error ora mappa su STOPPED — comportamento
      osservabile identico, i consumatori guardano solo PLAYING/PAUSED)
- [x] `project_manager.py`: `_migrate` inlined nel `load` (era impalcatura
      per zero migrazioni reali; si reintroduce alla prima migrazione vera)
- [x] `mp3widget.py`: reset stretch in `apply_layout` basato su
      `columnCount()`/`rowCount()` invece dei magic numbers 12/8; rimosse
      righe commentate morte in `_apply_compact_v_layout`
- [x] `mainapp.py`: commenti backend morti sostituiti da un commento inline

Verifica: py_compile + smoke test esteso (22 assert, incluso il nuovo check
sul reset dinamico degli stretch al cambio layout) — tutti passati.

## Fix volumi indipendenti (bug report utente) — 2° iterazione

- [x] `mp3file.py` `_VlcBackend.__init__`: su Windows
      `audio_output_set('directsound')` per player, chiamato DOPO
      `set_media()` (set_media resetta la scelta dell'output — il primo
      tentativo era inerte per questo). L'output default `mmdevice` usa il
      volume di sessione Windows, condiviso tra tutti i player del processo.
- [x] Ripristinata la sessione audio Windows (unmute + vol 100) lasciata
      muta dai primi test. Dettagli ed errori commessi in `tasks/lessons.md`.
- [x] Verifica: log VLC confermano "using audio output module directsound";
      A/B test app-level non mutato (A=8 stabile mentre B suona a 12);
      smoke 22/22. DA CONFERMARE A ORECCHIO dall'utente.

## Review

**Verifica eseguita** (`py_compile` su tutti i moduli + smoke test offscreen con
backend stub forzato, 21 assert): tutti passati. Coperti: envelope file
corti/vuoti (B1), invalidazione cache su mtime (B6), loader asincrono,
waveform asincrona al widget (B8), stop/pausa mid-fade con ripristino volume
(B2), normalize ok e fallita con riabilitazione bottone (B3), roundtrip
`apply_state`/`to_state`, save/load/migrazione progetto (P4), shutdown non
bloccante e idempotente (P3/B5), init/close di MainApp.

**Non verificabile in questa macchina:** P1/P2 richiedono libVLC reale con
output audio (replay dopo Ended, burst volume su fade-in). Fix applicati in
base al comportamento documentato di libVLC; da provare al primo uso reale.

**Comportamento intenzionalmente cambiato:**
- La waveform compare con un piccolo ritardo (prima bloccava la UI durante il decode).
- Interrompere un fade (stop/pausa) riallinea subito il volume al valore dello slider.
- Chiudere scegliendo "Salva" e annullando il dialog NON chiude più l'app.
- Il vecchio formato di cache waveform (`.jpg` in temp) è abbandonato; i file
  orfani in `%TEMP%/mp3player_waveforms` vengono semplicemente ignorati.
