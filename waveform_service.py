import os
import logging
import waveform as wf
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QPixmap


def _bytes_to_pixmap(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return pixmap


class WaveformThread(QThread):
    waveform_ready = pyqtSignal(bytes, int)  # data, sequence number

    def __init__(self, file_path: str, file_duration: float, width: int = 1500, gain: float = 1.0, seq: int = 0):
        super().__init__()
        self._file_path = file_path
        self._file_duration = file_duration
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
            data = wf.generate_waveform_mem(self._file_path, self._file_duration, width=self._width, gain=self._gain)
            if not self._cancelled:
                self.waveform_ready.emit(data, self._seq)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Background waveform failed: {e}")


class WaveformService(QObject):
    waveform_upgraded = pyqtSignal(QPixmap)

    LARGE_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
    DEBOUNCE_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_threads: set[WaveformThread] = set()
        self._seq = 0
        self._file_path: str = ''
        self._duration: float = 0.0
        self._pending_gain: float = 1.0
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self.DEBOUNCE_MS)
        self._debounce.timeout.connect(self._do_refresh)

    def generate(self, file_path: str, duration: float, gain: float = 1.0) -> QPixmap:
        """Return initial waveform as QPixmap. Starts background upgrade for large files."""
        self._file_path = file_path
        self._duration = duration
        try:
            fsize = os.path.getsize(file_path)
        except OSError:
            fsize = 0

        if fsize <= self.LARGE_FILE_BYTES:
            return _bytes_to_pixmap(wf.generate_waveform_mem(file_path, duration, width=1500, gain=gain))

        try:
            initial_data = wf.generate_waveform_mem(file_path, duration, width=600, gain=gain)
        except Exception:
            rosa_path = wf.generate_waveform_rosa(file_path, duration)
            with open(rosa_path, 'rb') as f:
                initial_data = f.read()

        self._start_thread(file_path, duration, gain)
        return _bytes_to_pixmap(initial_data)

    def refresh(self, gain: float) -> None:
        """Debounced: rigenera la waveform con il nuovo gain."""
        if not self._file_path:
            return
        self._pending_gain = gain
        self._debounce.start()  # riavvia il timer ad ogni chiamata

    def _do_refresh(self):
        self._start_thread(self._file_path, self._duration, self._pending_gain)

    def _start_thread(self, file_path: str, duration: float, gain: float = 1.0):
        self._seq += 1
        seq = self._seq
        for t in list(self._active_threads):
            t.cancel()
        thread = WaveformThread(file_path, duration, width=1500, gain=gain, seq=seq)
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
