import logging
import waveform as wf
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QPixmap
from constants import WAVEFORM_DEBOUNCE_MS, WAVEFORM_WIDTH
from thread_registry import retain

logger = logging.getLogger(__name__)


def _bytes_to_pixmap(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return pixmap


class EnvelopeThread(QThread):
    """Decodifica il file e calcola l'envelope in background (parte costosa)."""

    envelope_ready = pyqtSignal(object, object, int)  # min_vals, max_vals, seq

    def __init__(self, file_path: str, width: int = WAVEFORM_WIDTH, seq: int = 0):
        super().__init__()
        self._file_path = file_path
        self._width = width
        self._seq = seq
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        try:
            min_vals, max_vals = wf.compute_envelope(self._file_path, self._width)
            if not self._cancelled:
                self.envelope_ready.emit(min_vals, max_vals, self._seq)
        except Exception as e:
            logger.warning(f"Waveform envelope failed for {self._file_path}: {e}")


class WaveformService(QObject):
    """Fornisce la waveform come QPixmap, sempre in modo asincrono.

    - `generate(path)`: avvia decode+envelope in un thread; emette
      `waveform_upgraded` quando pronta. Nel frattempo la progress bar
      mostra il fondo piatto — il main thread non decodifica mai.
    - `refresh(gain)`: il gain è solo un fattore applicato all'envelope già
      in memoria, quindi il re-render è sincrono e costa millisecondi.
      Debounced per assorbire raffiche dello spinbox.
    - `cancel()`: non blocca. Il thread vive nel thread_registry finché
      non ha finito; i risultati superati vengono scartati via `seq`.
    """

    waveform_upgraded = pyqtSignal(QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq = 0
        self._thread: EnvelopeThread | None = None
        self._file_path: str = ''
        self._gain: float = 1.0
        self._envelope: tuple | None = None  # (min_vals, max_vals)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(WAVEFORM_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._render_current)

    def generate(self, file_path: str, gain: float = 1.0) -> None:
        """Avvia il calcolo della waveform; il risultato arriva via
        `waveform_upgraded`."""
        self._file_path = file_path
        self._gain = gain
        self._envelope = None
        if self._thread is not None:
            self._thread.cancel()
        self._seq += 1
        self._thread = EnvelopeThread(file_path, seq=self._seq)
        self._thread.envelope_ready.connect(self._on_envelope_ready)
        retain(self._thread)
        self._thread.start()

    def refresh(self, gain: float) -> None:
        """Debounced: re-renderizza la waveform con il nuovo gain."""
        self._gain = gain
        if self._envelope is None:
            # L'envelope non è ancora arrivato: _on_envelope_ready userà
            # comunque il gain più recente.
            return
        self._debounce.start()  # riavvia il timer ad ogni chiamata

    def _on_envelope_ready(self, min_vals, max_vals, seq: int):
        if seq != self._seq:  # risultato di un generate()/cancel() superato
            return
        self._envelope = (min_vals, max_vals)
        self._render_current()

    def _render_current(self):
        if self._envelope is None:
            return
        data = wf.render_envelope(self._envelope[0], self._envelope[1], gain=self._gain)
        self.waveform_upgraded.emit(_bytes_to_pixmap(data))

    def cancel(self):
        self._debounce.stop()
        self._seq += 1  # invalida qualsiasi risultato in arrivo
        if self._thread is not None:
            self._thread.cancel()
            self._thread = None
