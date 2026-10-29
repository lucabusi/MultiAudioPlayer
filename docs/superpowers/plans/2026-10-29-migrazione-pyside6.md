# Migrazione PyQt5 → PySide6 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** sostituire PyQt5 (Qt 5.15) con PySide6 (Qt 6.8) in MultiPlayer senza regressioni funzionali, mantenendo test, build PyInstaller e CI verdi.

**Architecture:** porting diretto, senza layer di compatibilità (niente `qtpy`): i due binding non possono convivere nello stesso processo e i test importano Qt direttamente, quindi lo swap del binding è **un unico task atomico** (Task 1). Le parti con API davvero cambiate in Qt6 — `QMediaPlayer` (backend `qt`) e `QAudioOutput` → `QAudioSink` (warmup) — hanno codice esplicito e test dedicati. Il resto è sostituzione meccanica.

**Tech Stack:** Python 3.11, PySide6 6.8.3 (Qt 6.8 LTS), QtMultimedia con backend FFmpeg (default Qt ≥ 6.5), pytest, PyInstaller 6.x, GitHub Actions `windows-latest`.

## Global Constraints

- Deve girare su **Windows e Linux** (CLAUDE.md di progetto).
- Dipendenza: `PySide6==6.8.3` (pacchetto **completo**). `PySide6-Essentials` NON basta: QtMultimedia sta in `PySide6-Addons` (verificato con lo spike, `ImportError: cannot import name 'QtMultimedia'`).
- Backend predefinito resta `'qt'` (`constants.DEFAULT_BACKEND`, test `test_default_backend_e_quello_documentato`).
- Volumi/gain/comandi indipendenti per ogni file: ogni `QMediaPlayer` ha il **suo** `QAudioOutput`.
- Curva volume invariata: `QAudio.convertVolume(v, LogarithmicVolumeScale, LinearVolumeScale)` dà gli stessi valori in Qt5 e Qt6 (verificato: 10→0.0229, 50→0.1505, 90→0.5, 100→1.0).
- `APP_VERSION` in `MultiPlayer/constants.py` va bumpato (`3.2.0` → `4.0.0`: cambio di toolkit). `project_manager.CURRENT_VERSION` NON cambia (formato `.mpp` invariato).
- Test di regressione: ogni bug trovato durante la migrazione → nuovo test in `tests/test_regressions.py`.
- Ignorare `_old/`, `future/`, `path/`.
- Commit/push solo su richiesta esplicita dell'utente; lavoro su branch `feat/pyside6`, mai direttamente su `main`.

## Fatti verificati con lo spike (PySide6 6.8.3, Windows 11)

| Fatto | Esito |
|---|---|
| Enum "corti" (`Qt.LeftButton`, `Qt.MoveAction`, `QMediaPlayer.EndOfMedia`) | funzionano → nessun rename di massa degli enum |
| `QtAudio` (6.7+) | assente in 6.8.3 → si usa `QAudio` |
| `QMediaPlayer.setAudioOutput` + `QAudioOutput.setVolume(float 0..1)` | ok |
| Segnale errori | `errorOccurred(error, errorString)` (in Qt5 era `error(code)`) |
| Stato riproduzione | `playbackState()` (in Qt5 `state()`) |
| Sorgente | `setSource(QUrl)` / `setSource(QUrl())` (Qt5: `setMedia(QMediaContent(...))`) |
| Plugin multimedia nel wheel | `ffmpegmediaplugin.dll`, `windowsmediaplugin.dll`; default FFmpeg |
| FFmpeg stampa un banner `Input #0, mp3...` su stderr ad ogni file | silenziato da `QT_LOGGING_RULES=qt.multimedia.ffmpeg*=false` |
| `QAudioFormat` 8 kHz mono Int16 su device Realtek | `isFormatSupported` = **False** → serve fallback a `preferredFormat()` (qui: 48 kHz, 2 canali, Float) |
| `QAudioSink(device, fmt, parent)` + `start()` push + `bytesForDuration()` | ok (il parent deve restare vivo: con un `QObject()` temporaneo → `Internal C++ object already deleted`) |
| `QMediaPlayer.Error.ResourceError.name` | `'ResourceError'` |
| `QMouseEvent` costruttore | Qt6 richiede `(type, QPointF local, QPointF global, button, buttons, modifiers)` |
| `app.exec_()` | esiste ancora ma deprecato → usare `exec()` |
| Dimensione `site-packages/PySide6` | ~481 MB (exe atteso più grande dei 151 MB attuali) |

## File Structure

Nessun file nuovo di codice applicativo. File toccati:

| File | Responsabilità / modifica |
|---|---|
| `requirements.txt` | `PyQt5` → `PySide6==6.8.3`; commenti backend aggiornati |
| `MultiPlayer/mp3file.py` | import `Signal`; riscrittura `_QtBackend` per API Qt6 |
| `MultiPlayer/audio_warmup.py` | `QAudioOutput` (Qt5) → `QAudioSink` + fallback formato |
| `MultiPlayer/mainapp.py` | import (`QAction`/`QActionGroup` → `QtGui`), `event.position()`, `exec()`, regola di log FFmpeg |
| `MultiPlayer/mp3widget.py` | import, `Signal`, `event.position()`, `drag.exec()`, docstring qFatal |
| `MultiPlayer/MultiPlayer.py` | `app.exec()` |
| `MultiPlayer/waveform_service.py`, `thread_registry.py`, `grid_manager.py` | solo import |
| `tests/test_regressions.py` | import, `QMouseEvent` Qt6, `exec()`, 2 test nuovi |
| `MultiPlayer.spec` | hiddenimport `PySide6.QtMultimedia` |
| `README.md`, `docs/user_manual.md`, `docs/architecture_analysis.md` | PyQt5 → PySide6, backend FFmpeg, requisiti Linux |
| `MultiPlayer/constants.py` | `APP_VERSION = '4.0.0'` |

---

### Task 1: Swap del binding (codice + test + requirements)

Atomico: dopo questo task l'app gira su PySide6 e `pytest tests/` è verde. Non è divisibile perché PyQt5 e PySide6 non convivono nello stesso processo.

**Files:**
- Modify: `requirements.txt:1-3`
- Modify: `MultiPlayer/mp3file.py:9`, `:36-37`, `:66-67`, `:432-552`, `:560-561`, `:605-613`
- Modify: `MultiPlayer/audio_warmup.py:9` (solo import; il resto in Task 2)
- Modify: `MultiPlayer/mainapp.py:4-6`, `:67`, `:237`, `:448-456`
- Modify: `MultiPlayer/mp3widget.py:4-6`, `:30`, `:71`, `:119-120`, `:131`, `:152-153`, `:474-475`
- Modify: `MultiPlayer/MultiPlayer.py:7`
- Modify: `MultiPlayer/waveform_service.py:3-4`, `:20`, `:56`
- Modify: `MultiPlayer/thread_registry.py:8`
- Modify: `MultiPlayer/grid_manager.py:1`
- Test: `tests/test_regressions.py`

**Interfaces:**
- Consumes: nulla.
- Produces: `_QtBackend` con la stessa interfaccia `_PlaybackBackend` di oggi (`play/pause/stop/get_state/get_time_ms/get_duration_ms/set_position/set_volume/release/set_error_callback`, `REQUIRES_MAIN_THREAD = True`) e in più l'attributo `self._audio_output: QAudioOutput`, che il test nuovo legge via `self._player.audioOutput()`.

- [ ] **Step 1: Branch di lavoro**

```bash
git checkout -b feat/pyside6
```

- [ ] **Step 2: Ambiente PySide6-only**

L'ambiente di test NON deve contenere PyQt5, altrimenti un import residuo passerebbe inosservato.

```bash
python -m venv .venv6
.venv6/Scripts/python -m pip install -r requirements.txt pytest   # dopo lo Step 3
```

(su Linux: `.venv6/bin/python`). `.venv6/` NON è coperto da `.gitignore` (verificato con `git check-ignore`): aggiungere la riga `.venv6/` nella sezione `# python` di `.gitignore`.

- [ ] **Step 3: `requirements.txt`**

Sostituire le prime righe:

```text
# Core (richiesti)
PySide6==6.8.3        # completo: QtMultimedia sta in PySide6-Addons, non in -Essentials
numpy
soundfile
Pillow
```

e la riga di commento del backend:

```text
# Il predefinito è 'qt' (QMediaPlayer) e non richiede nulla: è incluso in PySide6
# (backend FFmpeg incorporato nel wheel, anche su Linux: niente GStreamer di sistema).
```

- [ ] **Step 4: Scrivere il test che fallisce — volume via `QAudioOutput`**

In Qt6 un `QMediaPlayer` senza `QAudioOutput` è **muto in silenzio**: è l'errore di porting più probabile e nessun test esistente lo coglierebbe. Aggiungere in fondo a `tests/test_regressions.py`, prima di `def main():`:

```python
# ---------------------------------------------------------------------------
# migrazione PySide6 — in Qt6 QMediaPlayer non ha più setVolume: senza un
# QAudioOutput collegato resta MUTO senza alcun errore. Il volume per-player
# (requisito: volumi indipendenti) deve passare dal suo QAudioOutput con la
# stessa curva logaritmica di prima.
# ---------------------------------------------------------------------------
def test_backend_qt_volume_passa_da_audio_output():
    from mp3file import Mp3File

    _app()
    f = Mp3File(os.path.join(AUD, 'mitra.mp3'), backend='qt')
    _pump(300)
    try:
        out = f._backend._player.audioOutput()
        assert out is not None, "QMediaPlayer senza QAudioOutput: in Qt6 resta muto"
        f._backend.set_volume(50)
        assert abs(out.volume() - 0.1505) < 0.01, (
            f"volume {out.volume():.4f}: attesa curva log (50 -> 0.1505)")
    finally:
        f.cleanup()
```

- [ ] **Step 5: Verificare che la suite sia rossa**

Run: `.venv6/Scripts/python -m pytest tests/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'PyQt5'` su tutti i test.

- [ ] **Step 6: Import e segnali — `mp3file.py`, `waveform_service.py`, `thread_registry.py`, `grid_manager.py`, `audio_warmup.py`**

`MultiPlayer/mp3file.py:9`:

```python
from PySide6.QtCore import QObject, Signal, QTimer, QThread
```

Poi in `mp3file.py` sostituire **ogni** `pyqtSignal(` con `Signal(` (righe 36, 37, 66, 67, 560, 561, 605-613; firme invariate, es. `analysis_done = Signal(float)`).

`MultiPlayer/waveform_service.py:3-4`:

```python
from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtGui import QPixmap
```

e righe 20 e 56:

```python
    envelope_ready = Signal(object, object, int)  # min_vals, max_vals, seq
```
```python
    waveform_upgraded = Signal(QPixmap)
```

`MultiPlayer/thread_registry.py:8`:

```python
from PySide6.QtCore import QThread
```

`MultiPlayer/grid_manager.py:1`:

```python
from PySide6.QtWidgets import QGridLayout
```

`MultiPlayer/audio_warmup.py:9` (solo l'import di testa; il blocco multimedia è Task 2 — fino ad allora il warmup fallisce nel suo `try` e logga un warning, comportamento già previsto):

```python
from PySide6.QtCore import QObject, QTimer
```

- [ ] **Step 7: Riscrivere `_QtBackend` (`mp3file.py:432-552`) per Qt6**

Sostituire l'intera classe con:

```python
class _QtBackend(_PlaybackBackend):
    """Backend QMediaPlayer (PySide6.QtMultimedia). Nessuna dipendenza oltre
    PySide6: Qt ≥ 6.5 usa il backend FFmpeg incorporato nel wheel, sia su
    Windows sia su Linux (niente GStreamer di sistema).

    A differenza dei backend C (vlc/mpv/gstreamer), QMediaPlayer è un QObject
    con affinità di thread: va creato sul main thread (REQUIRES_MAIN_THREAD).
    L'init non blocca: il media viene caricato in modo asincrono e la durata
    arriva dopo — Mp3File.get_playback_info la rilegge finché non è nota.

    In Qt6 il volume non sta più sul player ma su un QAudioOutput: ogni
    istanza ha il suo, quindi i volumi restano indipendenti per costruzione.
    Senza setAudioOutput il player sarebbe muto senza alcun errore.
    """

    REQUIRES_MAIN_THREAD: bool = True

    def __init__(self, file_name: str):
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudio
        self._QMediaPlayer = QMediaPlayer
        self._QAudio = QAudio
        self._QUrl = QUrl
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput(self._player)
        self._player.setAudioOutput(self._audio_output)
        # Il caricamento è asincrono: un media rifiutato dal backend nativo
        # arriva DOPO l'init come segnale errorOccurred. Senza propagarlo, il
        # widget resterebbe apparentemente sano ma morto (durata 0, play inerte).
        self._error_cb = None
        self._pending_error: str | None = None
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.setSource(QUrl.fromLocalFile(os.path.abspath(file_name)))
        self._volume = 100
        self._audio_output.setVolume(1.0)

    def _on_player_error(self, error, error_string):
        name = error_string or getattr(error, 'name', str(error))
        msg = f"QMediaPlayer: {name} — file non riproducibile dal backend qt"
        if self._error_cb is not None:
            # Consegna al prossimo giro di event loop: il segnale può arrivare
            # SINCRONO dentro play() e rientrare nello stack di QMediaPlayer
            # (verificato in Qt5: crash hard, exit 0xC0000409, senza il defer).
            cb = self._error_cb
            QTimer.singleShot(0, lambda: cb(msg))
        else:
            self._pending_error = msg

    def set_error_callback(self, cb) -> None:
        """Registra il callback per gli errori media asincroni; se un errore
        è già arrivato prima della registrazione, lo consegna subito."""
        self._error_cb = cb
        if self._pending_error is not None:
            pending, self._pending_error = self._pending_error, None
            cb(pending)

    def _at_end(self) -> bool:
        """True se la posizione ha raggiunto la durata nota del media.

        Workaround nato per un bug WMF in Qt5 (Windows): dopo una riproduzione
        naturale completa QMediaPlayer poteva NON emettere mai EndOfMedia e
        restare in PlayingState con la posizione congelata sulla durata.
        Con il backend FFmpeg di Qt6 va riverificato (Task 4); il controllo è
        innocuo se EndOfMedia arriva regolarmente, quindi resta."""
        duration = self._player.duration()
        return duration > 0 and self._player.position() >= duration

    def play(self) -> None:
        # Dopo la fine del brano si riparte dall'inizio. _at_end copre il
        # caso del pipeline stallato in cui EndOfMedia non è mai arrivato.
        if self._player.mediaStatus() == self._QMediaPlayer.EndOfMedia or self._at_end():
            self._player.setPosition(0)
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def get_state(self) -> PlaybackState:
        if self._player.mediaStatus() == self._QMediaPlayer.EndOfMedia:
            return PlaybackState.ENDED
        s = self._player.playbackState()
        if s == self._QMediaPlayer.PlayingState:
            return PlaybackState.ENDED if self._at_end() else PlaybackState.PLAYING
        if s == self._QMediaPlayer.PausedState:
            return PlaybackState.ENDED if self._at_end() else PlaybackState.PAUSED
        return PlaybackState.STOPPED

    def get_time_ms(self) -> int:
        return int(self._player.position())

    def get_duration_ms(self) -> int:
        # 0 finché il media non è caricato (arriva async via durationChanged).
        return max(0, int(self._player.duration()))

    def set_position(self, position: float) -> None:
        duration = self._player.duration()
        if duration > 0:
            self._player.setPosition(int(max(0.0, min(1.0, position)) * duration))

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        # Curva percettiva (pattern raccomandato da Qt): il valore dello
        # slider è trattato come scala logaritmica e convertito in lineare —
        # a metà slider corrisponde metà volume percepito. QAudioOutput
        # vuole un float 0..1 (in Qt5 setVolume prendeva un int 0..100).
        linear = self._QAudio.convertVolume(self._volume / 100.0,
                                            self._QAudio.LogarithmicVolumeScale,
                                            self._QAudio.LinearVolumeScale)
        self._audio_output.setVolume(linear)

    def release(self) -> None:
        self._player.stop()
        self._player.setSource(self._QUrl())
        self._player.deleteLater()
```

Nota: `_ERROR_NAMES` sparisce — in Qt6 il segnale porta già `errorString` e l'enum `QMediaPlayer.Error` ha `.name`.

- [ ] **Step 8: `mainapp.py`**

Righe 4-6:

```python
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QWidget, QGridLayout, QScrollArea, QMessageBox
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QPainter, QColor, QPen, QAction, QActionGroup
```

Riga 67 (`dragMoveEvent`) — in Qt6 `QDragMoveEvent.pos()` non esiste più:

```python
        rect = self._on_get_target_rect(event.position().toPoint())
```

Riga 237 (`_on_container_drop`), stesso motivo per `QDropEvent`:

```python
        target_pos = event.position().toPoint()
```

Righe 448-456 — log FFmpeg silenziato prima di creare la QApplication, `exec()`:

```python
def run_app():
    # Il backend FFmpeg di QtMultimedia stampa su stderr un dump del formato
    # ("Input #0, mp3, ...") per ogni file aperto: rumore puro nei log.
    os.environ.setdefault('QT_LOGGING_RULES', 'qt.multimedia.ffmpeg*=false')
    app = QApplication(sys.argv)
    main_app = MainApp()
    return app, main_app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app, main_app = run_app()
    sys.exit(app.exec())
```

(`os` e `sys` sono già importati in `mainapp.py`, righe 1-2.)

- [ ] **Step 9: `mp3widget.py`**

Righe 4-6:

```python
from PySide6.QtWidgets import QAbstractButton, QAbstractSlider, QAbstractSpinBox, QProgressBar, QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QDoubleSpinBox, QFrame, QToolButton, QMenu, QHBoxLayout, QSlider, QSizePolicy
from PySide6.QtCore import Qt, Signal, QPoint, QMimeData
from PySide6.QtGui import QIcon, QDrag, QPixmap, QPainter, QColor, QAction
```

Righe 30 e 71:

```python
    clicked = Signal(float)
```
```python
    remove_requested = Signal(object)  # emette self
```

Righe 119-120 (`mousePressEvent`; `QMouseEvent.pos()` è deprecato in Qt6):

```python
        if event.button() == Qt.LeftButton and self._is_drag_handle(event.position().toPoint()):
            self.drag_start_position = event.position().toPoint()
```

Riga 131:

```python
        if (event.position().toPoint() - self.drag_start_position).manhattanLength() < self.startDragDistance():
```

Righe 152-153:

```python
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.MoveAction)
```

Righe 474-475 (docstring di `_report_playback_error`) — il motivo del guard cambia, il guard resta:

```python
        Un'eccezione che esce da uno slot Qt non deve mai arrivare all'event
        loop: con PyQt5 abortiva il processo (`qFatal()`, exit 0xC0000409);
        PySide6 la stampa e prosegue, ma lascia il widget a metà operazione.
```

Verificare che non restino altri `event.pos()` nel file: `grep -n "event.pos()" MultiPlayer/*.py` → nessun risultato.

- [ ] **Step 10: `MultiPlayer.py:7`**

```python
    app.exec()
```

- [ ] **Step 11: Porting di `tests/test_regressions.py`**

Sostituzioni puntuali:

- riga 31 (docstring `_app`): `PyQt5` → `PySide6`
- righe 37, 45, 107, 278, 348, 459: `from PyQt5` → `from PySide6` (stessi nomi importati)
- righe 58-60 (commento bug 1): "con PyQt5 un'eccezione che esce da uno slot Qt faceva abortire il processo (`qFatal()`); con PySide6 non aborta più, ma il test resta come guardia: Play/Stop non devono propagare l'errore"
- righe 66-67 nello snippet: `from PySide6.QtWidgets import QApplication` / `from PySide6.QtCore import QTimer`
- riga 86 nello snippet: `app.exec()`
- righe 391-392 e 404-405 (`test_drag_si_arma_da_tutto_il_corpo_del_widget`):

```python
    from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
    from PySide6.QtGui import QMouseEvent
```
```python
        app.sendEvent(w, QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos),
                                     QPointF(w.mapToGlobal(pos)),
                                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
```

Controllo: `grep -n "PyQt5\|exec_(" tests/test_regressions.py` → nessun risultato.

- [ ] **Step 12: Suite verde e compilazione**

Run:
```bash
.venv6/Scripts/python -m pytest tests/ -q
.venv6/Scripts/python -m py_compile MultiPlayer/*.py
grep -rn "PyQt5\|pyqtSignal\|exec_(" MultiPlayer/ tests/
```
Expected: `14 passed` (13 esistenti + quello nuovo; su macchina senza device audio `test_indicatore_fadeout_spento_dalla_pausa` risulta SKIPPED), `py_compile` muto, `grep` senza risultati.

Se un test fallisce: `superpowers:systematic-debugging`, causa radice, e nuovo test di regressione se il bug non era già coperto.

- [ ] **Step 13: Smoke test dell'app reale**

Run: `.venv6/Scripts/python MultiPlayer/MultiPlayer.py`
Expected: finestra aperta; aprire 2 mp3 da `audio_test/`, Play su entrambi, si sentono; volumi indipendenti; nessun `Input #0` su stderr.

- [ ] **Step 14: Commit**

```bash
git add requirements.txt .gitignore MultiPlayer/ tests/test_regressions.py
git commit -m "refactor: migrate GUI and qt audio backend from PyQt5 to PySide6"
```

---

### Task 2: AudioWarmup su `QAudioSink`

**Files:**
- Modify: `MultiPlayer/audio_warmup.py:27-58`
- Test: `tests/test_regressions.py`

**Interfaces:**
- Consumes: import di testa già portato in Task 1.
- Produces: `AudioWarmup` con interfaccia invariata (`__init__(parent=None)`, `stop()`); attributo `_io` non `None` quando lo stream è attivo.

- [ ] **Step 1: Scrivere il test che fallisce**

Prima di `def main():` in `tests/test_regressions.py`:

```python
# ---------------------------------------------------------------------------
# migrazione PySide6 — QAudioOutput di Qt5 (stream PCM) è diventato QAudioSink
# in Qt6, e il formato fisso 8 kHz mono non è supportato da tutti i device
# (Realtek: isFormatSupported False). Il warmup deve restare attivo, non
# degradare in silenzio a "non disponibile" — altrimenti torna il ritardo di
# 1-2 s sul primo play dopo l'idle dell'endpoint.
# ---------------------------------------------------------------------------
def test_audio_warmup_attivo_se_esiste_un_device():
    from PySide6.QtMultimedia import QMediaDevices
    from audio_warmup import AudioWarmup

    _app()
    if QMediaDevices.defaultAudioOutput().isNull():
        raise unittest.SkipTest("nessun device audio di output")
    w = AudioWarmup()
    try:
        _pump(300)
        assert w._io is not None, "warmup non partito: stream di silenzio assente"
    finally:
        w.stop()
```

- [ ] **Step 2: Verificare che fallisca**

Run: `.venv6/Scripts/python -m pytest tests/test_regressions.py::test_audio_warmup_attivo_se_esiste_un_device -v`
Expected: FAIL con `warmup non partito` (il codice cerca ancora `QAudioOutput(fmt, self)` e `setSampleSize`, che in Qt6 non esistono → finisce nell'`except`). Su un runner senza audio: SKIPPED.

- [ ] **Step 3: Implementazione**

Sostituire il blocco `try` di `__init__` (righe 32-54) con:

```python
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                raise RuntimeError('nessun device audio di output')
            # 8 kHz mono: il minimo che tiene aperta la sessione — il mixer
            # di sistema resample, a noi interessa solo che l'endpoint resti
            # attivo. Non tutti i device lo accettano in Qt6 (verificato:
            # Realtek no): in quel caso si usa il formato nativo del device.
            fmt = QAudioFormat()
            fmt.setSampleRate(8000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.Int16)
            if not device.isFormatSupported(fmt):
                fmt = device.preferredFormat()
            self._out = QAudioSink(device, fmt, self)
            self._out.setBufferSize(fmt.bytesForDuration(2_000_000))  # ~2s di margine
            self._io = self._out.start()  # push mode
            if self._io is None:
                raise RuntimeError('QAudioSink.start() ha restituito None')
            # Silenzio = byte a zero per tutti i formati PCM interi/float.
            self._silence = bytes(fmt.bytesForDuration(500_000))  # 0.5 s per feed
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._feed)
            self._timer.start(250)
            self._feed()
            logger.info('audio warmup attivo (stream di silenzio)')
```

(`except`, `_feed` e `stop` restano invariati: `bytesFree()` e `stop()` esistono anche su `QAudioSink`.) Aggiornare anche la docstring di classe: "`QAudioSink` (Qt6)" al posto di nessun riferimento esplicito — la frase sui ~176 KB/s va resa generica: "uno stream PCM di zeri (CPU trascurabile)".

- [ ] **Step 4: Verificare**

Run: `.venv6/Scripts/python -m pytest tests/ -q`
Expected: tutti verdi (15 test; eventuali SKIP solo per assenza di device audio).

Poi a mano: avviare l'app, lasciare idle il device ≥ 1 minuto (cuffie BT/HDMI se disponibili), premere Play: l'inizio della traccia non deve essere tagliato. Il log deve contenere `audio warmup attivo`.

- [ ] **Step 5: Commit**

```bash
git add MultiPlayer/audio_warmup.py tests/test_regressions.py
git commit -m "fix(audio_warmup): port silence stream to QAudioSink with format fallback"
```

---

### Task 3: Packaging PyInstaller + CI

**Files:**
- Modify: `MultiPlayer.spec:33-35`
- Modify: `.github/workflows/build.yml` (solo se serve, vedi Step 4)

**Interfaces:**
- Consumes: `requirements.txt` di Task 1.
- Produces: `dist/MultiPlayer.exe` funzionante con audio; artifact CI `MultiPlayer-windows`.

- [ ] **Step 1: `MultiPlayer.spec`**

```python
extra_hidden = ['PySide6.QtMultimedia']  # import lazy nel backend 'qt' (mp3file._QtBackend) e in audio_warmup
# extra_hidden += collect_submodules('PySide6')    # NON serve: gli hook PyInstaller di PySide6 raccolgono i moduli importati
```

(rimuovere la riga commentata `collect_submodules('PyQt5')`).

- [ ] **Step 2: Build da ambiente pulito**

```bash
.venv6/Scripts/python -m pip install pyinstaller
.venv6/Scripts/pyinstaller --noconfirm MultiPlayer.spec
```
Expected: exit 0, `dist/MultiPlayer.exe` presente.

- [ ] **Step 3: Verifica dell'exe — plugin multimedia inclusi**

Il rischio specifico di Qt6 è che il plugin FFmpeg (`plugins/multimedia/ffmpegmediaplugin.dll` + DLL `av*`) non finisca nel bundle: l'exe si avvia ma ogni file ripiega su `_StubBackend` (UI viva, nessun audio).

```bash
./dist/MultiPlayer.exe
```
Expected: aprire un mp3, Play → **si sente**; il widget non mostra `⚠`; il log (`multiplayer.log`) non contiene `unavailable, using stub`.

Se manca l'audio: aggiungere in `Analysis(... datas=[...])` la cartella dei plugin, ricavata così:

```python
import PySide6, os
_pyside_dir = os.path.dirname(PySide6.__file__)
# datas += [(os.path.join(_pyside_dir, 'plugins', 'multimedia'), 'PySide6/plugins/multimedia')]
```

ricostruire e ripetere lo Step 3, poi registrare il gotcha in memoria.

Annotare la dimensione dell'exe (oggi 151 MB). Se cresce oltre ~250 MB, valutare `excludes=[...]` dei moduli Qt non usati (QtQuick, QtQml, QtPdf, Qt3D, QtWebEngine*) — solo se la dimensione è un problema reale.

- [ ] **Step 4: CI**

Il workflow installa da `requirements.txt`: nessuna modifica attesa. Push del branch e verifica:

```bash
git push -u origin feat/pyside6
```
Expected: run su `pull_request`/push verde (step `pytest tests/` e `pyinstaller` success, artifact `MultiPlayer-windows` presente). Il test del warmup e quello del fade sono SKIPPED sul runner (nessun device audio).

- [ ] **Step 5: Commit**

```bash
git add MultiPlayer.spec
git commit -m "build: bundle PySide6 QtMultimedia in PyInstaller spec"
```

---

### Task 4: Verifica funzionale manuale, Linux, documentazione, versione

I test girano offscreen e non coprono resa grafica né audio udibile (CLAUDE.md). Questo task chiude la migrazione.

**Files:**
- Modify: `MultiPlayer/constants.py:10`
- Modify: `README.md:3`, `:28`, `:36`
- Modify: `docs/user_manual.md:46`, `:53`, `:260`
- Modify: `docs/architecture_analysis.md:19`
- Modify: memoria persistente (`wmf-endofmedia-stall.md`, `wmf-id3-invalidmedia.md`, `pyqt5-slot-exception-aborts.md`)

**Interfaces:**
- Consumes: app completa da Task 1-3.
- Produces: release `4.0.0`.

- [ ] **Step 1: Checklist manuale su Windows (`python MultiPlayer/MultiPlayer.py` da `.venv6`)**

Ogni voce: OK / KO. Un KO = bug → `superpowers:systematic-debugging` + test di regressione.

1. 4+ file in riproduzione simultanea, volumi e gain indipendenti (muovere lo slider di uno non cambia gli altri).
2. Fade in / fade out / pausa durante il fade (indicatore `btnFadeOut` si spegne).
3. Fine naturale della traccia senza seek, poi Play: **riparte dall'inizio** (era il bug WMF di Qt5; con FFmpeg verificare se EndOfMedia arriva — loggare `mediaStatus` una volta).
4. Seek durante pausa, poi Play: parte dalla posizione scelta (in Qt5/DirectShow il seek in pausa era inaffidabile).
5. File con tag ID3v2.4 malformato (vedi memoria `wmf-id3-invalidmedia`): con FFmpeg viene riprodotto? Se sì, aggiornare la memoria; se no, il widget deve mostrare `⚠` e non crashare.
6. Drag & drop dei widget nella griglia (evidenziazione cella, drop, nessuna colonna fantasma).
7. Salva/Carica progetto `.mpp` creato con la versione PyQt5: si apre identico.
8. Menu Configura → Backend audio: cambio backend e persistenza al riavvio.
9. HiDPI: in Qt6 lo scaling è sempre attivo. Con scaling Windows 125%/150% controllare layout Compact/Touch/Standard/Compact-V, waveform nitida, nessun testo tagliato.
10. Primo Play dopo ≥ 1 min di idle del device: nessun taglio iniziale (warmup).

- [ ] **Step 2: Verifica su Linux**

Su una macchina Linux (requisito di progetto):

```bash
python3 -m venv .venv6 && .venv6/bin/pip install -r requirements.txt pytest
QT_QPA_PLATFORM=offscreen .venv6/bin/python -m pytest tests/ -q
.venv6/bin/python MultiPlayer/MultiPlayer.py
```
Expected: suite verde; app avviata con audio. Qt6 su X11 richiede `libxcb-cursor0` (Debian/Ubuntu: `sudo apt install libxcb-cursor0`): se l'avvio fallisce con `Could not load the Qt platform plugin "xcb"`, documentarlo in `docs/user_manual.md` (requisiti Linux). GStreamer non è più necessario per il backend `qt`.

- [ ] **Step 3: Documentazione**

- `README.md:3`: "interfaccia grafica in Python (PySide6)".
- `README.md:28` e `:36`: il backend predefinito è "incluso in PySide6 (QtMultimedia, backend FFmpeg incorporato)".
- `docs/user_manual.md:46`: `| \`PySide6\` | GUI + backend audio predefinito (\`QtMultimedia\`) |`
- `docs/user_manual.md:53`: "il backend predefinito (`qt`) è incluso in PySide6".
- `docs/user_manual.md:260`: `| \`qt\` **(default)** | Nessuno, incluso in PySide6 | \`QMediaPlayer\` con backend FFmpeg incorporato (Windows e Linux). Volume software per-player via \`QAudioOutput\`, curva percettiva logaritmica |`
- `docs/architecture_analysis.md:19`: "Player audio multi-traccia PySide6."
- Requisito Linux `libxcb-cursor0` se confermato allo Step 2.

- [ ] **Step 4: Versione**

`MultiPlayer/constants.py:10`:

```python
APP_VERSION = '4.0.0'
```

- [ ] **Step 5: Memoria persistente**

Aggiornare i tre file in base agli esiti dello Step 1:
- `wmf-endofmedia-stall.md`: valido solo per Qt5/WMF; esito con Qt6/FFmpeg (voce 3).
- `wmf-id3-invalidmedia.md`: esito con FFmpeg (voce 5).
- `pyqt5-slot-exception-aborts.md`: con PySide6 non aborta più; i guard restano per non lasciare widget a metà.
- Nuova memoria: "`PySide6-Essentials` non contiene QtMultimedia: serve `PySide6` completo".

- [ ] **Step 6: Verifica finale e commit**

```bash
.venv6/Scripts/python -m pytest tests/ -q
.venv6/Scripts/python -m py_compile MultiPlayer/*.py
git add MultiPlayer/constants.py README.md docs/
git commit -m "docs: document PySide6 migration and bump version to 4.0.0"
```

Poi `superpowers:finishing-a-development-branch` per merge/PR verso `main`.

---

## Rischi e punti aperti

| Rischio | Dove si scopre | Mitigazione |
|---|---|---|
| Player muto per `QAudioOutput` mancante | Task 1 Step 4 | test dedicato |
| Plugin FFmpeg assente nell'exe → stub silenzioso | Task 3 Step 3 | verifica manuale audio + `datas` esplicito |
| Comportamento EndOfMedia / seek in pausa diverso con FFmpeg | Task 4 Step 1 (voci 3-4) | `_at_end()` resta; nuovo test se emerge bug |
| Layout diversi per HiDPI sempre attivo | Task 4 Step 1 (voce 9) | correzioni mirate in `mp3widget.py` |
| Exe molto più grande | Task 3 Step 3 | `excludes` solo se necessario |
| Licenza | — | PySide6 è LGPL (PyQt5 GPL/commerciale): nessun vincolo nuovo, anzi meno restrittivo |
