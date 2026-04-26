import logging
import os
import time
import numpy as np
import soundfile as sf
from abc import ABC, abstractmethod
from enum import Enum, auto
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread
from __init__ import FADE_TICK_MS, FADE_STARTUP_DELAY_MS

logger = logging.getLogger(__name__)


def compute_peak_gain(file_path: str) -> float:
    """Calcola il gain necessario per portare il picco massimo del file a 1.0."""
    samples, _ = sf.read(file_path, dtype='float32', always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    peak = float(np.max(np.abs(samples)))
    if peak < 1e-9:
        return 1.0
    return 1.0 / peak


class RmsAnalyzerThread(QThread):
    analysis_done = pyqtSignal(float)

    def __init__(self, file_path: str):
        super().__init__()
        self._file_path = file_path

    def run(self):
        try:
            gain = compute_peak_gain(self._file_path)
            self.analysis_done.emit(gain)
        except Exception as e:
            logger.error(f"Peak analysis failed for {self._file_path}: {e}")


class FadeController(QObject):
    """Linear fade da `start_volume` a `end_volume` in `duration` secondi.

    Il progress è calcolato dal tempo reale trascorso (`time.monotonic()`),
    non dal numero di tick QTimer. Questo lo rende robusto a tick mancati
    o ritardati: se il main loop è bloccato per 200ms, il prossimo tick
    salta direttamente al volume corretto invece di "rimanere indietro" e
    dilatare la durata totale del fade.

    Edge case: `duration` <= 0 viene clampata a 1ms così il primo tick
    completa subito il fade senza divisione per zero.
    """

    update_volume = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, duration, start_volume, end_volume, parent=None):
        super().__init__(parent)
        self.start_volume = float(start_volume)
        self.end_volume = float(end_volume)
        self.duration = max(0.001, float(duration))
        self._t_start = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self._t_start = time.monotonic()
        self.timer.start(FADE_TICK_MS)

    def stop(self):
        self.timer.stop()

    def _tick(self):
        elapsed = time.monotonic() - self._t_start
        if elapsed >= self.duration:
            self.update_volume.emit(int(round(self.end_volume)))
            self.timer.stop()
            self.finished.emit()
            return
        ratio = elapsed / self.duration
        volume = int(round(self.start_volume + (self.end_volume - self.start_volume) * ratio))
        self.update_volume.emit(volume)


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------

class PlaybackState(Enum):
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()
    ENDED = auto()
    ERROR = auto()


class _PlaybackBackend(ABC):
    # Se True, dopo `play()` il backend perde il volume corrente e va riapplicato
    # con un piccolo delay. Specifico di VLC (vedi _VlcBackend).
    NEEDS_VOLUME_REAPPLY_ON_PLAY: bool = False

    @abstractmethod
    def play(self) -> None: ...
    @abstractmethod
    def pause(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def is_playing(self) -> bool: ...
    @abstractmethod
    def get_state(self) -> PlaybackState: ...
    @abstractmethod
    def get_time_ms(self) -> int: ...
    @abstractmethod
    def get_duration_ms(self) -> int: ...
    @abstractmethod
    def set_position(self, position: float) -> None: ...
    @abstractmethod
    def get_position(self) -> float: ...
    @abstractmethod
    def set_volume(self, volume: int) -> None: ...
    @abstractmethod
    def release(self) -> None: ...


class _StubBackend(_PlaybackBackend):
    """In-memory backend that simulates playback by advancing a timer.
    Fallback used when a real backend library is unavailable."""

    def __init__(self, name: str, file_name: str):
        self._name = name
        self._file_name = file_name
        self._volume = 100
        self._state = PlaybackState.STOPPED
        self._position_ms = 0
        self._t_anchor = time.monotonic()
        try:
            size = os.path.getsize(file_name)
            self._duration_ms = max(30_000, int(size / (128 * 1024 / 8) * 1000))
        except OSError:
            self._duration_ms = 60_000
        logger.info("stub backend [%s] for %s (~%dms)", name, file_name, self._duration_ms)

    def _tick(self):
        now = time.monotonic()
        if self._state == PlaybackState.PLAYING:
            self._position_ms += int((now - self._t_anchor) * 1000)
            if self._position_ms >= self._duration_ms:
                self._position_ms = self._duration_ms
                self._state = PlaybackState.ENDED
        self._t_anchor = now

    def play(self) -> None:
        self._tick()
        if self._state == PlaybackState.ENDED:
            self._position_ms = 0
        self._state = PlaybackState.PLAYING

    def pause(self) -> None:
        self._tick()
        if self._state == PlaybackState.PLAYING:
            self._state = PlaybackState.PAUSED

    def stop(self) -> None:
        self._tick()
        self._state = PlaybackState.STOPPED
        self._position_ms = 0

    def is_playing(self) -> bool:
        self._tick()
        return self._state == PlaybackState.PLAYING

    def get_state(self) -> PlaybackState:
        self._tick()
        return self._state

    def get_time_ms(self) -> int:
        self._tick()
        return self._position_ms

    def get_duration_ms(self) -> int:
        return self._duration_ms

    def set_position(self, position: float) -> None:
        self._tick()
        self._position_ms = int(max(0.0, min(1.0, position)) * self._duration_ms)

    def get_position(self) -> float:
        if self._duration_ms == 0:
            return 0.0
        return self.get_time_ms() / self._duration_ms

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))

    def release(self) -> None:
        pass


class _VlcBackend(_PlaybackBackend):
    # VLC reimposta il volume al massimo al primo play() finché il modulo
    # audio output non è inizializzato. Con un delay di FADE_STARTUP_DELAY_MS
    # ms (~100ms) il backend ha avuto il tempo di settare l'output e set_volume()
    # ha effetto. Senza questo workaround, l'utente sentirebbe un breve burst
    # a volume massimo all'avvio.
    NEEDS_VOLUME_REAPPLY_ON_PLAY: bool = True

    def __init__(self, file_name: str):
        self._stub: _StubBackend | None = None
        try:
            import vlc
            self._vlc = vlc
            self._player = vlc.MediaPlayer(file_name)
            media = vlc.Media(file_name)
            self._player.set_media(media)
            media.parse()
            self._duration_ms: int = media.get_duration()
        except Exception as exc:
            logger.warning("VLC unavailable, using stub: %s", exc)
            self._stub = _StubBackend("vlc", file_name)

    def play(self) -> None:
        if self._stub: self._stub.play(); return
        self._player.play()

    def pause(self) -> None:
        if self._stub: self._stub.pause(); return
        self._player.pause()

    def stop(self) -> None:
        if self._stub: self._stub.stop(); return
        self._player.stop()

    def is_playing(self) -> bool:
        if self._stub: return self._stub.is_playing()
        return self._player.get_state() == self._vlc.State.Playing

    def get_state(self) -> PlaybackState:
        if self._stub: return self._stub.get_state()
        s = self._player.get_state()
        if s == self._vlc.State.Playing:
            return PlaybackState.PLAYING
        if s == self._vlc.State.Paused:
            return PlaybackState.PAUSED
        if s == self._vlc.State.Ended:
            return PlaybackState.ENDED
        if s == self._vlc.State.Error:
            return PlaybackState.ERROR
        return PlaybackState.STOPPED

    def get_time_ms(self) -> int:
        if self._stub: return self._stub.get_time_ms()
        return self._player.get_time()

    def get_duration_ms(self) -> int:
        if self._stub: return self._stub.get_duration_ms()
        return self._duration_ms

    def set_position(self, position: float) -> None:
        if self._stub: self._stub.set_position(position); return
        self._player.set_position(position)

    def get_position(self) -> float:
        if self._stub: return self._stub.get_position()
        return self._player.get_position()

    def set_volume(self, volume: int) -> None:
        if self._stub: self._stub.set_volume(volume); return
        self._player.audio_set_volume(max(0, min(100, volume)))

    def release(self) -> None:
        if self._stub: return
        self._player.release()


class _GStreamerBackend(_PlaybackBackend):
    def __init__(self, file_name: str):
        self._stub: _StubBackend | None = None
        try:
            import gi  # type: ignore[import]
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst  # type: ignore[import]
            Gst.init(None)
            self._Gst = Gst

            self._player = Gst.ElementFactory.make('playbin', 'player')
            if self._player is None:
                raise RuntimeError(
                    "Impossibile creare l'elemento GStreamer 'playbin'. "
                    "Verifica che gstreamer1.0-plugins-base sia installato."
                )

            import pathlib
            self._player.set_property('uri', pathlib.Path(file_name).as_uri())
            self._volume = 100
            self._player.set_property('volume', 1.0)
            self._eos = False

            # Transition to PAUSED to resolve duration, then back to NULL
            self._player.set_state(Gst.State.PAUSED)
            self._player.get_state(Gst.CLOCK_TIME_NONE)
            ok, self._duration_ns = self._player.query_duration(Gst.Format.TIME)
            if not ok:
                self._duration_ns = 0
            self._player.set_state(Gst.State.NULL)
        except Exception as exc:
            logger.warning("GStreamer unavailable, using stub: %s", exc)
            self._stub = _StubBackend("gstreamer", file_name)

    def _check_eos(self) -> bool:
        bus = self._player.get_bus()
        while True:
            msg = bus.pop_filtered(self._Gst.MessageType.EOS | self._Gst.MessageType.ERROR)
            if msg is None:
                break
            if msg.type == self._Gst.MessageType.EOS:
                self._eos = True
        return self._eos

    def play(self) -> None:
        if self._stub: self._stub.play(); return
        self._eos = False
        self._player.set_state(self._Gst.State.NULL)
        self._player.set_state(self._Gst.State.PLAYING)

    def pause(self) -> None:
        if self._stub: self._stub.pause(); return
        self._player.set_state(self._Gst.State.PAUSED)

    def stop(self) -> None:
        if self._stub: self._stub.stop(); return
        self._eos = False
        self._player.set_state(self._Gst.State.NULL)
        self._player.set_state(self._Gst.State.READY)

    def is_playing(self) -> bool:
        if self._stub: return self._stub.is_playing()
        if self._check_eos():
            return False
        _, state, _ = self._player.get_state(0)
        return state == self._Gst.State.PLAYING

    def get_state(self) -> PlaybackState:
        if self._stub: return self._stub.get_state()
        if self._check_eos():
            return PlaybackState.ENDED
        _, state, _ = self._player.get_state(0)
        if state == self._Gst.State.PLAYING:
            return PlaybackState.PLAYING
        if state == self._Gst.State.PAUSED:
            return PlaybackState.PAUSED
        return PlaybackState.STOPPED

    def get_time_ms(self) -> int:
        if self._stub: return self._stub.get_time_ms()
        ok, pos_ns = self._player.query_position(self._Gst.Format.TIME)
        if not ok or pos_ns < 0:
            return 0
        return pos_ns // 1_000_000

    def get_duration_ms(self) -> int:
        if self._stub: return self._stub.get_duration_ms()
        return self._duration_ns // 1_000_000

    def set_position(self, position: float) -> None:
        if self._stub: self._stub.set_position(position); return
        pos_ns = int(position * self._duration_ns)
        self._player.seek_simple(
            self._Gst.Format.TIME,
            self._Gst.SeekFlags.FLUSH | self._Gst.SeekFlags.KEY_UNIT,
            pos_ns,
        )

    def get_position(self) -> float:
        if self._stub: return self._stub.get_position()
        if self._duration_ns == 0:
            return 0.0
        ok, pos_ns = self._player.query_position(self._Gst.Format.TIME)
        if not ok or pos_ns < 0:
            return 0.0
        return pos_ns / self._duration_ns

    def set_volume(self, volume: int) -> None:
        if self._stub: self._stub.set_volume(volume); return
        self._volume = max(0, min(100, volume))
        self._player.set_property('volume', self._volume / 100.0)

    def release(self) -> None:
        if self._stub: return
        self._player.set_state(self._Gst.State.NULL)


class _MpvBackend(_PlaybackBackend):
    def __init__(self, file_name: str):
        self._stub: _StubBackend | None = None
        try:
            import mpv  # type: ignore[import]
            self._file_name = file_name
            self._stopped = True
            self._player = mpv.MPV()
            self._player.pause = True
            self._player.play(file_name)
            # Block briefly until duration is resolved (mpv runs its own event thread)
            try:
                self._player.wait_for_property('duration', lambda d: d is not None and d > 0, timeout=5)
            except Exception:
                deadline = time.monotonic() + 5.0
                while self._player.duration is None and time.monotonic() < deadline:
                    time.sleep(0.05)
            self._duration_ms = int((self._player.duration or 0.0) * 1000)
        except Exception as exc:
            logger.warning("MPV unavailable, using stub: %s", exc)
            self._stub = _StubBackend("mpv", file_name)

    def play(self) -> None:
        if self._stub: self._stub.play(); return
        if self._player.core_idle and not self._player.pause:
            # File ended — reload from start
            self._player.play(self._file_name)
            try:
                self._player.wait_for_property('duration', lambda d: d is not None and d > 0, timeout=3)
            except Exception:
                deadline = time.monotonic() + 3.0
                while self._player.duration is None and time.monotonic() < deadline:
                    time.sleep(0.05)
        self._stopped = False
        self._player.pause = False

    def pause(self) -> None:
        if self._stub: self._stub.pause(); return
        self._player.pause = True

    def stop(self) -> None:
        if self._stub: self._stub.stop(); return
        self._stopped = True
        self._player.pause = True
        try:
            self._player.seek(0, reference='absolute')
        except Exception:
            pass

    def is_playing(self) -> bool:
        if self._stub: return self._stub.is_playing()
        return not self._stopped and not self._player.pause and not self._player.core_idle

    def get_state(self) -> PlaybackState:
        if self._stub: return self._stub.get_state()
        if self._stopped:
            return PlaybackState.STOPPED
        if self._player.core_idle and not self._player.pause:
            return PlaybackState.ENDED
        if self._player.pause:
            return PlaybackState.PAUSED
        return PlaybackState.PLAYING

    def get_time_ms(self) -> int:
        if self._stub: return self._stub.get_time_ms()
        pos = self._player.time_pos
        return int(pos * 1000) if pos is not None else 0

    def get_duration_ms(self) -> int:
        if self._stub: return self._stub.get_duration_ms()
        return self._duration_ms

    def set_position(self, position: float) -> None:
        if self._stub: self._stub.set_position(position); return
        self._player.seek(position * (self._duration_ms / 1000.0), reference='absolute')

    def get_position(self) -> float:
        if self._stub: return self._stub.get_position()
        if self._duration_ms == 0:
            return 0.0
        return self.get_time_ms() / self._duration_ms

    def set_volume(self, volume: int) -> None:
        if self._stub: self._stub.set_volume(volume); return
        self._player.volume = float(max(0, min(100, volume)))

    def release(self) -> None:
        if self._stub: return
        self._player.terminate()



class _BackendLoader(QThread):
    ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, cls, file_name: str):
        super().__init__()
        self._cls = cls
        self._file_name = file_name

    def run(self):
        try:
            self.ready.emit(self._cls(self._file_name))
        except Exception as e:
            self.error.emit(str(e))


_BACKENDS = {
    'vlc': _VlcBackend,
    'gstreamer': _GStreamerBackend,
    'gst': _GStreamerBackend,
    'mpv': _MpvBackend,

}


def available_backends() -> list[str]:
    """Return the canonical name of each registered backend."""
    return list(_BACKENDS.keys())


# ---------------------------------------------------------------------------
# Mp3File
# ---------------------------------------------------------------------------

class Mp3File(QObject):
    fadeInFinished = pyqtSignal()
    fadeOutFinished = pyqtSignal()
    playback_state_changed = pyqtSignal(str)  # 'playing', 'paused', 'stopped'
    fade_in_started = pyqtSignal()
    loaded = pyqtSignal()
    load_error = pyqtSignal(str)
    normalize_ready = pyqtSignal(float)  # emesso con il gain calcolato

    def __init__(self, file_name: str, backend: str = 'vlc'):
        super().__init__()
        self.fade_controller = None
        self.file_name = file_name
        self._backend: _PlaybackBackend | None = None
        self.mp3_total_duration = 0
        self.actual_volume = 100
        self.gain: float = 1.0
        self._rms_thread: RmsAnalyzerThread | None = None

        backend_key = backend.lower()
        if backend_key not in _BACKENDS:
            raise ValueError(
                f"Backend '{backend}' non riconosciuto. "
                f"Disponibili: {', '.join(available_backends())}"
            )

        self._loader = _BackendLoader(_BACKENDS[backend_key], file_name)
        self._loader.ready.connect(self._on_backend_ready)
        self._loader.error.connect(self._on_backend_error)
        self._loader.start()

    def _on_backend_ready(self, backend: _PlaybackBackend):
        self._backend = backend
        self.mp3_total_duration = self._backend.get_duration_ms()
        self._backend.set_volume(self._effective_volume())
        self._loader = None
        self.loaded.emit()

    def _on_backend_error(self, message: str):
        logger.error(f"Impossibile inizializzare il backend: {message}")
        self._loader = None
        self.load_error.emit(message)

    def is_ready(self) -> bool:
        return self._backend is not None

    def get_state(self) -> PlaybackState:
        if self._backend is None:
            return PlaybackState.STOPPED
        return self._backend.get_state()

    def is_playing(self) -> bool:
        if self._backend is None:
            return False
        return self._backend.is_playing()

    def get_playback_info(self) -> dict | None:
        if self._backend is None:
            return None
        state = self._backend.get_state()
        if state not in (PlaybackState.PLAYING, PlaybackState.PAUSED):
            return None
        if self.mp3_total_duration <= 0:
            return None
        current_time_ms = self._backend.get_time_ms()
        if current_time_ms < 0:
            return None
        return {
            'position': current_time_ms / self.mp3_total_duration,
            'current_seconds': int(current_time_ms // 1000),
            'remaining_seconds': int((self.mp3_total_duration - current_time_ms) // 1000),
        }

    def play_pause(self):
        if self._backend is None:
            return
        try:
            if self.is_playing():
                self._backend.pause()
                self.playback_state_changed.emit('paused')
            else:
                self._backend.play()
                if self._backend.NEEDS_VOLUME_REAPPLY_ON_PLAY:
                    QTimer.singleShot(FADE_STARTUP_DELAY_MS,
                                      lambda: self.set_volume(self.actual_volume))
                self.playback_state_changed.emit('playing')
        except Exception as e:
            logger.error(f"Play/Pause failed: {e}")
            raise

    def stop(self):
        if self._backend is None:
            return
        try:
            self._backend.stop()
            self.playback_state_changed.emit('stopped')
        except Exception as e:
            logger.error(f"Stop failed: {e}")
            raise

    def _stop_active_fade(self):
        if self.fade_controller is not None:
            self.fade_controller.stop()
            self.fade_controller = None

    def fade_in(self, duration, end_volume):
        """Avvia la riproduzione partendo da volume 0 e sale fino a `end_volume`
        in `duration` secondi. No-op se il backend è già in riproduzione.

        :param duration: durata del fade in secondi (float).
        :param end_volume: volume finale 0..100.
        """
        if self._backend is None or self._backend.is_playing():
            return
        self._stop_active_fade()
        # Silenzia PRIMA di play() per evitare un burst audibile iniziale
        # (altrimenti l'audio parte all'actual_volume corrente per qualche ms).
        self.set_volume(0)
        self._backend.play()
        self.fade_in_started.emit()
        self.playback_state_changed.emit('playing')
        self.fade_controller = FadeController(duration, 0, end_volume)
        self.fade_controller.update_volume.connect(self.set_volume)
        self.fade_controller.finished.connect(self.fadeInFinished.emit)
        # Piccolo delay perché il backend abbia tempo di iniziare l'output
        # prima che il fade cominci a salire — altrimenti i primi step del
        # fade vanno sprecati su audio non ancora udibile.
        pending = self.fade_controller
        QTimer.singleShot(FADE_STARTUP_DELAY_MS, lambda c=pending: self._start_fade_if_current(c))

    def _start_fade_if_current(self, controller):
        """Start the fade only if it's still the active one (guards against
        a newer fade superseding this one in the 100ms window)."""
        if controller is self.fade_controller:
            controller.start()

    def fade_out(self, duration, start_volume, end_volume):
        """Scende dal volume corrente `start_volume` a `end_volume` (tipicamente 0)
        in `duration` secondi, poi ferma la riproduzione e ripristina
        `start_volume` come volume "memorizzato" per il prossimo play.

        :param duration: durata del fade in secondi (float).
        :param start_volume: volume di partenza 0..100 (di solito quello dello slider).
        :param end_volume: volume finale 0..100 (di solito 0).
        """
        self._stop_active_fade()
        self.fade_controller = FadeController(duration, start_volume, end_volume)
        self.fade_controller.update_volume.connect(self.set_volume)
        self.fade_controller.finished.connect(lambda: self.fadeOutFinished.emit())
        self.fade_controller.finished.connect(self.stop)
        self.fade_controller.finished.connect(lambda: self.set_volume(start_volume))
        self.fade_controller.start()

    def _effective_volume(self) -> int:
        return max(0, min(100, int(self.actual_volume * self.gain)))

    def set_volume(self, volume: int):
        """Imposta il volume "slider" (post-clamp 0..100). Il backend riceve
        il volume effettivo = `volume * gain` (anch'esso clampato a 0..100).

        :param volume: 0..100. Valori fuori range vengono clampati.
        """
        self.actual_volume = max(0, min(100, int(volume)))
        if self._backend is not None:
            self._backend.set_volume(self._effective_volume())
        logger.debug(f"set_volume: {self.actual_volume}  gain: {self.gain:.3f}  effective: {self._effective_volume()}")

    def set_gain(self, gain: float) -> None:
        """Imposta il gain (moltiplicatore) e ricalcola `actual_volume` in modo
        che il volume effettivo udibile resti invariato. Esempio: se prima
        actual_volume=100, gain=1.0 (effective=100), e l'utente normalizza
        portando gain a 2.0, actual_volume diventa 50 (effective=100).

        :param gain: 0..5.0 circa. Valori <=1e-6 vengono alzati a 1e-6.
        """
        old_effective = self._effective_volume()
        self.gain = max(1e-6, gain)
        self.actual_volume = max(0, min(100, round(old_effective / self.gain)))
        if self._backend is not None:
            self._backend.set_volume(self._effective_volume())
        logger.debug(f"set_gain: {self.gain:.3f}  actual: {self.actual_volume}  effective: {self._effective_volume()}")

    def normalize(self) -> None:
        """Avvia l'analisi peak in background; emette normalize_ready(gain) quando pronta."""
        if self._rms_thread is not None and self._rms_thread.isRunning():
            return
        self._rms_thread = RmsAnalyzerThread(self.file_name)
        self._rms_thread.analysis_done.connect(self.normalize_ready)
        self._rms_thread.finished.connect(lambda: setattr(self, '_rms_thread', None))
        self._rms_thread.start()

    def get_volume(self):
        return self.actual_volume

    def set_position(self, position):
        if self._backend is not None:
            self._backend.set_position(position)

    def get_position(self):
        if self._backend is None:
            return 0.0
        return self._backend.get_position()

    def cleanup(self):
        if self._loader is not None:
            self._loader.quit()
            self._loader.wait()
            self._loader = None
        if self._rms_thread is not None:
            try:
                self._rms_thread.analysis_done.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._rms_thread.quit()
            self._rms_thread.wait()
            self._rms_thread = None
        if self._backend is not None:
            self.stop()
            self._backend.release()
