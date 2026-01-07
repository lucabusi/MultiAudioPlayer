from PyQt5.QtCore import QObject, pyqtSignal, QTimer


class FadeController(QObject):
    update_volume = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, duration, start_volume, end_volume, parent=None):
        super().__init__(parent)
        self.start_volume = start_volume
        self.end_volume = end_volume
        self.duration = duration  # in seconds
        self.steps = int(duration * 10)
        self.step_index = 0
        self.volume_step = (end_volume - start_volume) / self.steps if self.steps > 0 else 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)

    def start(self):
        self.timer.start(100)

    def update(self):
        if self.step_index >= self.steps:
            self.update_volume.emit(int(self.end_volume))
            self.timer.stop()
            self.finished.emit()
            return
        volume = int(self.start_volume + self.volume_step * self.step_index)
        self.update_volume.emit(volume)
        self.step_index += 1
