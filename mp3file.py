import vlc
import logging
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from fadecontroller import FadeController


class Mp3File(QObject):
    fadeInFinished = pyqtSignal()
    fadeOutFinished = pyqtSignal()

    def __init__(self, file_name):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.fade_controller = None

        try:
            self.player = vlc.MediaPlayer(file_name)
            self.file_name = file_name
            self.media = vlc.Media(file_name)
            self.player.set_media(self.media)
        except Exception as e:
            self.logger.error(f"Failed to initialize player: {e}")
            raise

        self.L_player_obj = self.player.get_media()
        self.L_player_obj.parse()
        self.mp3_total_duration = self.L_player_obj.get_duration()
        self.state = self.get_state()
        self.actual_volume = 100
        self.set_volume(100)

    def get_state(self):
        self.vlcState = self.player.get_state()
        return self.vlcState

    def is_playing(self) -> bool:
        return self.player.get_state() == vlc.State.Playing

    def get_playback_info(self) -> dict | None:
        """Return position data if playing or paused, else None.
        Keeps VLC state logic out of the view layer.
        """
        state = self.player.get_state()
        if state not in (vlc.State.Playing, vlc.State.Paused):
            return None
        current_time_ms = self.player.get_time()
        if current_time_ms < 0:
            return None
        return {
            'position': current_time_ms / self.mp3_total_duration,
            'current_seconds': int(current_time_ms // 1000),
            'remaining_seconds': int((self.mp3_total_duration - current_time_ms) // 1000),
        }

    def play_pause(self):
        try:
            if self.is_playing():
                self.player.pause()
            else:
                self.player.play()
                QTimer.singleShot(100, lambda: self.set_volume(self.actual_volume))
        except Exception as e:
            self.logger.error(f"Play/Pause failed: {e}")
            raise

    def stop(self):
        try:
            self.player.stop()
        except Exception as e:
            self.logger.error(f"Stop failed: {e}")
            raise

    def _stop_active_fade(self):
        """Stop any running fade controller before starting a new one.
        Prevents two controllers acting on volume simultaneously.
        """
        if self.fade_controller is not None:
            self.fade_controller.stop()
            self.fade_controller = None

    def fade_in(self, duration, end_volume):
        if not self.player.is_playing():
            self._stop_active_fade()
            # Set volume to 0 before play so there is no burst at the previous level
            self.set_volume(0)
            self.player.play()
            self.fade_controller = FadeController(duration, 0, end_volume)
            self.fade_controller.update_volume.connect(self.set_volume)
            self.fade_controller.finished.connect(lambda: self.fadeInFinished.emit())
            self.fade_controller.start()

    def fade_out(self, duration, start_volume, end_volume):
        self._stop_active_fade()
        self.fade_controller = FadeController(duration, start_volume, end_volume)
        self.fade_controller.update_volume.connect(self.set_volume)
        self.fade_controller.finished.connect(lambda: self.fadeOutFinished.emit())
        self.fade_controller.finished.connect(self.stop)
        self.fade_controller.finished.connect(lambda: self.set_volume(start_volume))
        self.fade_controller.start()

    def set_volume(self, volume: int):
        self.actual_volume = max(0, min(100, int(volume)))
        self.player.audio_set_volume(self.actual_volume)
        self.logger.debug(f"set_volume method: {self.actual_volume}, mp3file-get_volume: {self.get_volume()}")

    def get_volume(self):
        return self.actual_volume

    def set_position(self, position):
        self.player.set_position(position)

    def get_position(self):
        return self.player.get_position()

    def cleanup(self):
        self.stop()
        self.player.release()
