import os
import logging
from waveform import generate_waveform, generate_waveform_pillow, generate_waveform_rosa
import waveform as wf
from PyQt5.QtWidgets import QProgressBar, QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QDoubleSpinBox, QFrame, QToolButton, QMenu, QAction, QHBoxLayout, QSlider, QSizePolicy
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPoint, QMimeData
from PyQt5.QtGui import QIcon, QDrag, QPixmap, QPainter
from utils import WidgetLayout, seconds_to_min_sec
from mp3file import Mp3File


class Mp3WidgetMimeData(QMimeData):
    def __init__(self):
        super().__init__()
        self.widget = None

    def setWidget(self, widget):
        self.widget = widget

    def getWidget(self):
        return self.widget


class ClickableProgressBar(QProgressBar):
    clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            click_position = event.x()
            total_width = self.width()
            new_value = int(click_position / total_width * (self.maximum() - self.minimum()) + self.minimum())
            self.setValue(new_value)
            self.clicked.emit(new_value / self.maximum())
        super().mousePressEvent(event)


class Mp3Widget(QWidget):
    def __init__(self, mp3_audio_file: Mp3File, layout: WidgetLayout = WidgetLayout.TOUCH):
        super().__init__()
        self.mp3file = mp3_audio_file
        self.mp3file.fadeInFinished.connect(lambda: self.changeButtonStyle(self.btnFadeIn, ""))
        self.mp3file.fadeOutFinished.connect(lambda: self.changeButtonStyle(self.btnFadeOut, ""))
        self.mp3file.fadeOutFinished.connect(lambda: self.changeButtonStyle(self.btnPlay, ""))

        self.volume_slider_value = self.mp3file.actual_volume
        self.fade_time = 5
        self.elapsed_time = 0
        self.remaining_time = 0
        self.file_duration = self.mp3file.mp3_total_duration
        self.logger = logging.getLogger(__name__)
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name
        self.playerState = self.mp3file.get_state()

        self.drag_start_position = QPoint()

        self.create_ui_elements()
        self.apply_layout()

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.defaultBtnStyle = "border: 1px solid; border-radius: 5px;"
        self.btnChangeLayout.setText(self.current_layout_name)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < self.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = Mp3WidgetMimeData()
        mime_data.setWidget(self)
        drag.setMimeData(mime_data)

        pixmap = QPixmap(self.size())
        self.render(pixmap)
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        painter = QPixmap(pixmap.size())
        painter.setDevicePixelRatio(self.devicePixelRatioF())
        painter.fill(Qt.transparent)
        p = QPainter(painter)
        p.setOpacity(0.7)
        p.drawPixmap(0, 0, pixmap)
        p.end()

        drag.setPixmap(painter)
        drag.setHotSpot(event.pos())
        drag.exec_(Qt.MoveAction)

    def startDragDistance(self):
        return 10

    def create_ui_elements(self):
        self.widget_main_frame = QFrame()
        widget_main_frame_style = ("""
        QFrame { background-color: #4A5662; border: 1px solid #5D6D7E; border-radius: 5px; }
        QLabel { color: white; font-weight: bold; }
        QDoubleSpinBox { color: black; }
        QPushButton {background-color: #a5adb6; border: 1px solid; border-radius: 5px;}
        QToolButton {background-color: #8c97a5; border: 1px solid; border-radius: 5px;}
        """)

        self.widget_main_frame.setStyleSheet(widget_main_frame_style)

        self.widget_file_frame_layout = QGridLayout()
        self.widget_main_frame.setLayout(self.widget_file_frame_layout)

        self.filename_label = QLabel(f"{os.path.basename(self.mp3file.file_name)}")
        self.progress_bar = self.create_progress_bar()
        self.btnPlay = QPushButton("Play/Pause")
        self.btnPlay.setIcon(QIcon.fromTheme("media-playback-start"))
        self.btnPlay.clicked.connect(self.w_play_pause)
        self.btnFadeIn = QPushButton("FadeIn")
        self.btnFadeIn.setIcon(QIcon.fromTheme("go-up"))
        self.btnFadeIn.clicked.connect(self.w_fade_in)
        self.spinboxFadeTime = QDoubleSpinBox()
        self.spinboxFadeTime.setRange(0, 10)
        self.spinboxFadeTime.setValue(self.fade_time)
        self.spinboxFadeTime.setSingleStep(0.5)
        self.spinboxFadeTime.valueChanged.connect(self.update_fade_time)
        self.btnFadeOut = QPushButton("Fade Out")
        self.btnFadeOut.setIcon(QIcon.fromTheme("go-down"))
        self.btnFadeOut.clicked.connect(self.w_fade_out)
        self.btnStop = QPushButton("Stop")
        self.btnStop.clicked.connect(self.w_stop)
        self.btnStop.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.btnRemove = QPushButton("Remove")
        self.btnRemove.setIcon(QIcon.fromTheme("user-trash"))
        self.btnRemove.clicked.connect(self.w_remove_file)
        self.slidVolume = QSlider(Qt.Vertical)
        self.slidVolume.setMinimum(0)
        self.slidVolume.setMaximum(100)
        self.slidVolume.setValue(self.volume_slider_value)
        self.slidVolume.valueChanged.connect(self.update_volume)
        self.lblVolume = QLabel("100")
        self.lblVolume.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.lblElapsedTime = QLabel("Elapsed time: 00:00")
        self.lblElapsedTime.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.lblRemainingTime = QLabel(f"Remaining time: {seconds_to_min_sec(int(self.file_duration/1000))}")
        self.btnFadePreset1 = QPushButton("1")
        self.btnFadePreset1.clicked.connect(lambda: self.spinboxFadeTime.setValue(1))
        self.btnFadePreset2 = QPushButton("3")
        self.btnFadePreset2.clicked.connect(lambda: self.spinboxFadeTime.setValue(3))
        self.btnFadePreset3 = QPushButton("5")
        self.btnFadePreset3.clicked.connect(lambda: self.spinboxFadeTime.setValue(5))

        fade_preset_layout = QHBoxLayout()
        fade_preset_layout.setContentsMargins(0, 0, 0, 0)
        fade_preset_layout.setSpacing(0)
        fade_preset_layout.addWidget(self.btnFadePreset1)
        fade_preset_layout.addWidget(self.btnFadePreset2)
        fade_preset_layout.addWidget(self.btnFadePreset3)
        self.fade_preset_widget = QWidget()
        self.fade_preset_widget.setLayout(fade_preset_layout)

        self.btnChangeLayout = QToolButton()
        self.btnChangeLayout.setIcon(QIcon.fromTheme("document-properties"))
        self.btnChangeLayout.setPopupMode(QToolButton.InstantPopup)
        layout_menu = QMenu(self)

        action_compact = QAction("Compact", self)
        action_compact.triggered.connect(lambda: self.set_layout(WidgetLayout.COMPACT))
        layout_menu.addAction(action_compact)

        action_touch = QAction("Touch", self)
        action_touch.triggered.connect(lambda: self.set_layout(WidgetLayout.TOUCH))
        layout_menu.addAction(action_touch)

        action_standard = QAction("Standard", self)
        action_standard.triggered.connect(lambda: self.set_layout(WidgetLayout.STANDARD))
        layout_menu.addAction(action_standard)

        self.btnChangeLayout.setMenu(layout_menu)

        self.widget_layout = QVBoxLayout()
        self.widget_layout.setContentsMargins(0, 0, 0, 0)
        self.widget_layout.addWidget(self.widget_main_frame)
        self.setLayout(self.widget_layout)

    def set_layout(self, layout: WidgetLayout):
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name
        self.btnChangeLayout.setText(self.current_layout_name)
        self.apply_layout()

    def apply_layout(self):
        while self.widget_file_frame_layout.count():
            item = self.widget_file_frame_layout.takeAt(0)
            if item.widget():
                pass

        layout = self.widget_file_frame_layout

        if self.widgetLayout == WidgetLayout.COMPACT:
            layout.addWidget(self.btnRemove, 0, 0)
            layout.addWidget(self.btnChangeLayout, 0, 1)
            layout.addWidget(self.filename_label, 0, 2, 1, 3)
            layout.addWidget(self.btnPlay, 0, 5)
            layout.addWidget(self.btnFadeIn, 0, 6)
            layout.addWidget(self.spinboxFadeTime, 0, 7)
            layout.addWidget(self.btnFadeOut, 0, 8)
            layout.addWidget(self.btnStop, 0, 9)
            layout.addWidget(self.slidVolume, 0, 11, 4, 1)
            layout.addWidget(self.lblVolume, 0, 10)
            layout.addWidget(self.progress_bar, 1, 0, 2, 9)
            layout.addWidget(self.lblRemainingTime, 1, 9, 1, 2)
            layout.addWidget(self.lblElapsedTime, 2, 9, 1, 2)

        elif self.widgetLayout == WidgetLayout.TOUCH:
            for i in range(12):
                layout.setColumnStretch(i, 0)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(10, 1)
            for i in range(1, 10):
                layout.setColumnStretch(i, 2)

            for btn in [self.spinboxFadeTime, self.btnRemove, self.btnPlay, self.btnFadeIn, self.btnFadeOut, self.btnStop, self.btnChangeLayout, self.fade_preset_widget]:
                btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

            layout.addWidget(self.btnRemove, 0, 0, 2, 1)
            layout.addWidget(self.btnChangeLayout, 0, 1, 1, 1)
            layout.addWidget(self.filename_label, 0, 2, 1, 3)
            layout.addWidget(self.btnPlay, 0, 5, 2, 1)
            layout.addWidget(self.btnFadeIn, 0, 6, 2, 1)
            layout.addWidget(self.spinboxFadeTime, 0, 7, 1, 1)
            layout.addWidget(self.fade_preset_widget, 1, 7, 1, 1)
            layout.addWidget(self.btnFadeOut, 0, 8, 2, 1)
            layout.addWidget(self.btnStop, 0, 9, 2, 1)
            layout.addWidget(self.slidVolume, 0, 11, 4, 1)
            layout.addWidget(self.lblVolume, 0, 10)
            layout.addWidget(self.progress_bar, 2, 0, 2, 11)
            layout.addWidget(self.lblRemainingTime, 1, 3, 1, 2)
            layout.addWidget(self.lblElapsedTime, 1, 1, 1, 2)

        else:
            for btn in [self.spinboxFadeTime, self.btnRemove, self.btnPlay, self.btnFadeIn, self.btnFadeOut, self.btnStop, self.btnChangeLayout]:
                btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

            layout.addWidget(self.btnRemove, 0, 0, 2, 1)
            layout.addWidget(self.btnChangeLayout, 0, 1, 1, 1)
            layout.addWidget(self.filename_label, 0, 2, 1, 3)
            layout.addWidget(self.btnPlay, 0, 5, 2, 1)
            layout.addWidget(self.btnFadeIn, 0, 6, 2, 1)
            layout.addWidget(self.spinboxFadeTime, 0, 7, 1, 1)
            layout.addWidget(self.fade_preset_widget, 1, 7, 1, 1)
            layout.addWidget(self.btnFadeOut, 0, 8, 2, 1)
            layout.addWidget(self.btnStop, 0, 9, 2, 1)
            layout.addWidget(self.slidVolume, 0, 11, 4, 1)
            layout.addWidget(self.lblVolume, 0, 10)
            layout.addWidget(self.progress_bar, 2, 0, 2, 11)
            layout.addWidget(self.lblRemainingTime, 1, 3, 1, 2)
            layout.addWidget(self.lblElapsedTime, 1, 1, 1, 2)

        self.adjustSize()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress_bar)
        self.timer.start(50)

    def changeButtonStyle(self, btn, color):
        btn.setStyleSheet(f"QPushButton {{background-color: {color}; {self.defaultBtnStyle} }} ")

    def w_play_pause(self):
        if (self.mp3file.get_state() == 3):
            self.changeButtonStyle(self.btnPlay, "red")
        else:
            self.changeButtonStyle(self.btnPlay, "green")
        self.mp3file.play_pause()

    def w_stop(self):
        self.changeButtonStyle(self.btnPlay, "")
        self.mp3file.stop()

    def w_remove_file(self):
        self.mp3file.cleanup()
        self.parent().remove_widget(self)
        self.deleteLater()

    def update_volume(self):
        volume = self.slidVolume.value()
        self.mp3file.set_volume(volume)
        self.lblVolume.setText(str(volume))

    def update_fade_time(self):
        self.fade_time = self.spinboxFadeTime.value()

    def w_fade_in(self):
        self.changeButtonStyle(self.btnPlay, "green")
        self.changeButtonStyle(self.btnFadeIn, "green")
        self.mp3file.fade_in(self.fade_time, self.mp3file.get_volume())

    def w_fade_out(self):
        self.changeButtonStyle(self.btnFadeOut, "green")
        self.mp3file.fade_out(self.fade_time, self.mp3file.get_volume(), 0)

    def update_playback_position(self, new_position):
        self.mp3file.set_position(new_position)

    def update_progress_bar(self):
        if (self.mp3file.get_state() == 3) or (self.mp3file.get_state() == 4):
            try:
                current_time_ms = self.mp3file.player.get_time()
                if current_time_ms >= 0:
                    position = current_time_ms / self.file_duration
                    progress_value = int(position * self.progress_bar.maximum())
                    total_seconds = self.file_duration // 1000
                    current_seconds = current_time_ms // 1000
                    remaining_seconds = total_seconds - current_seconds
                    self.progress_bar.setValue(progress_value)
                    self.lblElapsedTime.setText(f"Elapsed Time: {seconds_to_min_sec(current_seconds)}")
                    self.lblRemainingTime.setText(f"Remaining Time: {seconds_to_min_sec(remaining_seconds)}")
            except Exception as e:
                self.logger.error(f"Error updating progress bar: {e}")
        else:
            self.progress_bar.setValue(0)
            self.lblElapsedTime.setText("Elapsed Time: 00:00")
            self.lblRemainingTime.setText(f"Remaining Time: {seconds_to_min_sec(round(self.file_duration/1000))}")
        return

    def generate_waveform_rosa(self):
        # Delegate waveform creation to waveform module (runs synchronously)
        return wf.generate_waveform_rosa(self.mp3file.file_name, self.file_duration)

    def create_progress_bar(self):
        waveform_image_path = self.generate_waveform_rosa()
        progress_bar_style = f"""
        QProgressBar {{
            border: 1px solid grey;
            background-color: transparent;
            border-image: url({waveform_image_path}) 0 0 0 0 stretch stretch;
            background-repeat: no-repeat;
            background-position: left center;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: rgba(0,255,0,100);
            width: 1px;
        }}
        """

        self.progress_bar = ClickableProgressBar()
        self.progress_bar.setFixedHeight(48)
        self.progress_bar.setStyleSheet(progress_bar_style)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.clicked.connect(self.update_playback_position)
        return self.progress_bar
