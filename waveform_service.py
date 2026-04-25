import os
import logging
import waveform as wf
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QPixmap
from __init__ import (
    LARGE_FILE_BYTES,
    WAVEFORM_DEBOUNCE_MS,
    WAVEFORM_PREVIEW_WIDTH,
    WAVEFORM_WIDTH,
)

logger = logging.getLogger(__name__)


def _bytes_to_pixmap(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return pixmap


class WaveformThread(QThread):
    waveform_ready = pyqtSignal(bytes, int)  # data, sequence number

    def __init__(self, file_path: str, width: int = WAVEFORM_WIDTH,
                 gain: float = 1.0, seq: int = 0):
        super().__init__()
        self._file_path = file_path
        self._width = width
        self._gain = gain
        self._seq = seq
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        try:
            data = wf.generate_waveform_mem(self._file_path, width=self._width, gain=self._gain)
            if not self._cancelled:
                self.waveform_ready.emit(data, self._seq)
        except Exception as e:
            logger.debug(f"Background waveform failed: {e}")


class WaveformService(QObject):
    waveform_upgraded = pyqtSignal(QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_threads: set[WaveformThread] = set()
        self._seq = 0
        self._file_path: str = ''
        self._pending_gain: float = 1.0
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(WAVEFORM_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._do_refresh)

    def generate(self, file_path: str, gain: float = 1.0) -> QPixmap:
        """Return initial waveform as QPixmap. Starts background upgrade for large files.
        Cade su `generate_waveform_librosa` se soundfile non gestisce il formato."""
        self._file_path = file_path
        try:
            fsize = os.path.getsize(file_path)
        except OSError:
            fsize = 0

        if fsize <= LARGE_FILE_BYTES:
            try:
                data = wf.generate_waveform_mem(file_path, width=WAVEFORM_WIDTH, gain=gain)
            except Exception:
                data = wf.generate_waveform_librosa(file_path, width=WAVEFORM_WIDTH, gain=gain)
            return _bytes_to_pixmap(data)

        try:
            initial_data = wf.generate_waveform_mem(file_path, width=WAVEFORM_PREVIEW_WIDTH, gain=gain)
        except Exception:
            initial_data = wf.generate_waveform_librosa(file_path, width=WAVEFORM_PREVIEW_WIDTH, gain=gain)

        self._start_thread(file_path, gain)
        return _bytes_to_pixmap(initial_data)

    def refresh(self, gain: float) -> None:
        """Debounced: rigenera la waveform con il nuovo gain."""
        if not self._file_path:
            return
        self._pending_gain = gain
        self._debounce.start()  # riavvia il timer ad ogni chiamata

    def _do_refresh(self):
        self._start_thread(self._file_path, self._pending_gain)

    def _start_thread(self, file_path: str, gain: float = 1.0):
        self._seq += 1
        seq = self._seq
        for t in list(self._active_threads):
            t.cancel()
        thread = WaveformThread(file_path, width=WAVEFORM_WIDTH, gain=gain, seq=seq)
        self._active_threads.add(thread)
        thread.waveform_ready.connect(self._on_waveform_ready)
        thread.finished.connect(lambda t=thread: self._active_threads.discard(t))
        thread.start()

    def _on_waveform_ready(self, data: bytes, seq: int):
        if seq == self._seq:  # scarta risultati di thread obsoleti
            self.waveform_upgraded.emit(_bytes_to_pixmap(data))

    def cancel(self):
        self._debounce.stop()
        for t in list(self._active_threads):
            t.cancel()
        for t in list(self._active_threads):
            t.wait(500)
        self._active_threads.clear()
