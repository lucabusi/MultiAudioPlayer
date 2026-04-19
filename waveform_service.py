import os
import logging
import waveform as wf
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtGui import QPixmap


def _bytes_to_pixmap(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return pixmap


class WaveformThread(QThread):
    waveform_ready = pyqtSignal(bytes)

    def __init__(self, file_path: str, file_duration: float, width: int = 1500):
        super().__init__()
        self._file_path = file_path
        self._file_duration = file_duration
        self._width = width
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        try:
            data = wf.generate_waveform_mem(self._file_path, self._file_duration, width=self._width)
            if not self._cancelled:
                self.waveform_ready.emit(data)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Background high-res waveform failed: {e}")


class WaveformService(QObject):
    waveform_upgraded = pyqtSignal(QPixmap)

    LARGE_FILE_BYTES = 2 * 1024 * 1024  # 2 MB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: WaveformThread | None = None

    def generate(self, file_path: str, duration: float) -> QPixmap:
        """Return initial waveform as QPixmap. Starts background upgrade for large files."""
        try:
            fsize = os.path.getsize(file_path)
        except OSError:
            fsize = 0

        if fsize <= self.LARGE_FILE_BYTES:
            return _bytes_to_pixmap(wf.generate_waveform_mem(file_path, duration, width=1500))

        try:
            initial_data = wf.generate_waveform_mem(file_path, duration, width=600)
        except Exception:
            initial_data = wf.generate_waveform_rosa(file_path, duration)

        self._start_highres_thread(file_path, duration)
        return _bytes_to_pixmap(initial_data)

    def _on_waveform_ready(self, data: bytes):
        self.waveform_upgraded.emit(_bytes_to_pixmap(data))

    def _start_highres_thread(self, file_path: str, duration: float):
        if self._thread is not None and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait(200)
        self._thread = WaveformThread(file_path, duration, width=1500)
        self._thread.waveform_ready.connect(self._on_waveform_ready)
        self._thread.start()

    def cancel(self):
        if self._thread is not None and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait(500)
