import logging
import numpy as np
import soundfile as sf
from abc import ABC, abstractmethod
from enum import Enum, auto
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread


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
            logging.getLogger(__name__).error(f"Peak analysis failed for {self._file_path}: {e}")


class FadeController(QObject):
    update_volume = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, duration, start_volume, end_volume, parent=None):
        super().__init__(parent)
        self.start_volume = start_volume
        self.end_volume = end_volume
        self.duration = duration
        self.steps = int(duration * 10)
        self.step_index = 0
        self.volume_step = (end_volume - start_volume) / self.steps if self.steps > 0 else 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)

    def start(self):
        self.timer.start(100)

    def stop(self):
        self.timer.stop()

    def update(self):
        if self.step_index >= self.steps:
            self.update_volume.emit(int(self.end_volume))
            self.timer.stop()
            self.finished.emit()
            return
        volume = int(self.start_volume + self.volume_step * self.step_index)
        self.update_volume.emit(volume)
        self.step_index += 1


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


class _VlcBackend(_PlaybackBackend):
    def __init__(self, file_name: str):
        import vlc
        self._vlc = vlc
        self._player = vlc.MediaPlayer(file_name)
        media = vlc.Media(file_name)
        self._player.set_media(media)
        media.parse()
        self._duration_ms: int = media.get_duration()

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def is_playing(self) -> bool:
        return self._player.get_state() == self._vlc.State.Playing

    def get_state(self) -> PlaybackState:
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
        return self._player.get_time()

    def get_duration_ms(self) -> int:
        return self._duration_ms

    def set_position(self, position: float) -> None:
        self._player.set_position(position)

    def get_position(self) -> float:
        return self._player.get_position()

    def set_volume(self, volume: int) -> None:
        self._player.audio_set_volume(max(0, min(100, volume)))

    def release(self) -> None:
        self._player.release()


class _GStreamerBackend(_PlaybackBackend):
    def __init__(self, file_name: str):
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
        self._eos = False
        self._player.set_state(self._Gst.State.NULL)
        self._player.set_state(self._Gst.State.PLAYING)

    def pause(self) -> None:
        self._player.set_state(self._Gst.State.PAUSED)

    def stop(self) -> None:
        self._eos = False
        self._player.set_state(self._Gst.State.NULL)
        self._player.set_state(self._Gst.State.READY)

    def is_playing(self) -> bool:
        if self._check_eos():
            return False
        _, state, _ = self._player.get_state(0)
        return state == self._Gst.State.PLAYING

    def get_state(self) -> PlaybackState:
        if self._check_eos():
            return PlaybackState.ENDED
        _, state, _ = self._player.get_state(0)
        if state == self._Gst.State.PLAYING:
            return PlaybackState.PLAYING
        if state == self._Gst.State.PAUSED:
            return PlaybackState.PAUSED
        return PlaybackState.STOPPED

    def get_time_ms(self) -> int:
        ok, pos_ns = self._player.query_position(self._Gst.Format.TIME)
        if not ok or pos_ns < 0:
            return 0
        return pos_ns // 1_000_000

    def get_duration_ms(self) -> int:
        return self._duration_ns // 1_000_000

    def set_position(self, position: float) -> None:
        pos_ns = int(position * self._duration_ns)
        self._player.seek_simple(
            self._Gst.Format.TIME,
            self._Gst.SeekFlags.FLUSH | self._Gst.SeekFlags.KEY_UNIT,
            pos_ns,
        )

    def get_position(self) -> float:
        if self._duration_ns == 0:
            return 0.0
        ok, pos_ns = self._player.query_position(self._Gst.Format.TIME)
        if not ok or pos_ns < 0:
            return 0.0
        return pos_ns / self._duration_ns

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, volume))
        self._player.set_property('volume', self._volume / 100.0)

    def release(self) -> None:
        self._player.set_state(self._Gst.State.NULL)


class _MpvBackend(_PlaybackBackend):
    def __init__(self, file_name: str):
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
            import time
            deadline = time.monotonic() + 5.0
            while self._player.duration is None and time.monotonic() < deadline:
                time.sleep(0.05)
        self._duration_ms = int((self._player.duration or 0.0) * 1000)

    def play(self) -> None:
        if self._player.core_idle and not self._player.pause:
            # File ended — reload from start
            self._player.play(self._file_name)
            try:
                self._player.wait_for_property('duration', lambda d: d is not None and d > 0, timeout=3)
            except Exception:
                import time
                deadline = time.monotonic() + 3.0
                while self._player.duration is None and time.monotonic() < deadline:
                    time.sleep(0.05)
        self._stopped = False
        self._player.pause = False

    def pause(self) -> None:
        self._player.pause = True

    def stop(self) -> None:
        self._stopped = True
        self._player.pause = True
        try:
            self._player.seek(0, reference='absolute')
        except Exception:
            pass

    def is_playing(self) -> bool:
        return not self._stopped and not self._player.pause and not self._player.core_idle

    def get_state(self) -> PlaybackState:
        if self._stopped:
            return PlaybackState.STOPPED
        if self._player.core_idle and not self._player.pause:
            return PlaybackState.ENDED
        if self._player.pause:
            return PlaybackState.PAUSED
        return PlaybackState.PLAYING

    def get_time_ms(self) -> int:
        pos = self._player.time_pos
        return int(pos * 1000) if pos is not None else 0

    def get_duration_ms(self) -> int:
        return self._duration_ms

    def set_position(self, position: float) -> None:
        self._player.seek(position * (self._duration_ms / 1000.0), reference='absolute')

    def get_position(self) -> float:
        if self._duration_ms == 0:
            return 0.0
        return self.get_time_ms() / self._duration_ms

    def set_volume(self, volume: int) -> None:
        self._player.volume = float(max(0, min(100, volume)))

    def release(self) -> None:
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
        self.logger = logging.getLogger(__name__)
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
        self.logger.error(f"Impossibile inizializzare il backend: {message}")
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
                QTimer.singleShot(100, lambda: self.set_volume(self.actual_volume))
                self.playback_state_changed.emit('playing')
        except Exception as e:
            self.logger.error(f"Play/Pause failed: {e}")
            raise

    def stop(self):
        if self._backend is None:
            return
        try:
            self._backend.stop()
            self.playback_state_changed.emit('stopped')
        except Exception as e:
            self.logger.error(f"Stop failed: {e}")
            raise

    def _stop_active_fade(self):
        if self.fade_controller is not None:
            self.fade_controller.stop()
            self.fade_controller = None

    def fade_in(self, duration, end_volume):
        if self._backend is None:
            return
        if not self._backend.is_playing():
            self._stop_active_fade()
            self._backend.play()
            self.fade_in_started.emit()
            self.playback_state_changed.emit('playing')
            self.fade_controller = FadeController(duration, 0, end_volume)
            self.fade_controller.update_volume.connect(self.set_volume)
            self.fade_controller.finished.connect(lambda: self.fadeInFinished.emit())
            controller = self.fade_controller
            QTimer.singleShot(100, lambda: controller is self.fade_controller and (self.set_volume(0), controller.start()))

    def fade_out(self, duration, start_volume, end_volume):
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
        self.actual_volume = max(0, min(100, int(volume)))
        if self._backend is not None:
            self._backend.set_volume(self._effective_volume())
        self.logger.debug(f"set_volume: {self.actual_volume}  gain: {self.gain:.3f}  effective: {self._effective_volume()}")

    def set_gain(self, gain: float) -> None:
        old_effective = self._effective_volume()
        self.gain = max(1e-6, gain)
        # Ricalcola actual_volume per mantenere il volume effettivo invariato dopo il cambio di gain
        self.actual_volume = max(0, min(100, round(old_effective / self.gain)))
        if self._backend is not None:
            self._backend.set_volume(self._effective_volume())
        self.logger.debug(f"set_gain: {self.gain:.3f}  actual: {self.actual_volume}  effective: {self._effective_volume()}")

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
        if self._backend is not None:
            self.stop()
            self._backend.release()
