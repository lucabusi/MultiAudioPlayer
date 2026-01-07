import io
from PyQt5.QtCore import QRunnable, QObject, pyqtSignal
from PyQt5.QtGui import QPixmap
from PIL import Image, ImageDraw
import librosa


class WorkerSignals(QObject):
    finished = pyqtSignal(QPixmap, str)  # pixmap, file_path
    error = pyqtSignal(str)


class WaveformWorker(QRunnable):
    """QRunnable worker to generate waveform image and return a QPixmap via signals.

    Args:
        file_path (str): path to audio file
        width (int): width of generated image
        height (int): height of generated image
    """

    def __init__(self, file_path, width=1500, height=75, target_sr=11025):
        super().__init__()
        self.file_path = file_path
        self.width = width
        self.height = height
        self.target_sr = target_sr
        self.signals = WorkerSignals()

    def run(self):
        try:
            samples, _ = librosa.load(self.file_path, sr=self.target_sr, mono=True)
            step = max(1, len(samples) // self.width)
            samples = samples[: step * self.width]
            if len(samples) == 0:
                raise RuntimeError('Empty audio samples')
            samples = samples.reshape(-1, step)
            min_vals = samples.min(axis=1)
            max_vals = samples.max(axis=1)

            img = Image.new("RGBA", (self.width, self.height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)
            center = self.height // 2
            for x, (min_val, max_val) in enumerate(zip(min_vals, max_vals)):
                y1 = int(center + min_val * center)
                y2 = int(center + max_val * center)
                draw.line([(x, y1), (x, y2)], fill=(0, 0, 255, 255))

            buf = io.BytesIO()
            img.convert('RGB').save(buf, format='JPEG')
            data = buf.getvalue()
            pix = QPixmap()
            pix.loadFromData(data)
            self.signals.finished.emit(pix, self.file_path)
        except Exception as e:
            self.signals.error.emit(str(e))
