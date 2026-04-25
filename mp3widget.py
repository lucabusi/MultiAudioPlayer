import os
import logging
from enum import Enum
from PyQt5.QtWidgets import QProgressBar, QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QDoubleSpinBox, QFrame, QToolButton, QMenu, QAction, QHBoxLayout, QSlider, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QMimeData
from PyQt5.QtGui import QIcon, QDrag, QPixmap, QPainter, QColor
from mp3file import Mp3File
from waveform_service import WaveformService
from __init__ import PROGRESS_BAR_HEIGHT

logger = logging.getLogger(__name__)


class WidgetLayout(Enum):
    COMPACT = 1
    TOUCH = 2
    STANDARD = 3
    COMPACT_V = 4


def seconds_to_min_sec(seconds: int) -> str:
    return f"{seconds // 60:02}:{seconds % 60:02}"


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
        self._waveform: QPixmap | None = None

    def set_waveform(self, pixmap: QPixmap):
        self._waveform = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        if self._waveform is not None and not self._waveform.isNull():
            painter.drawPixmap(rect, self._waveform)
        else:
            painter.fillRect(rect, QColor('#4A5662'))
        if self.maximum() > 0 and self.value() > 0:
            chunk_width = int(rect.width() * self.value() / self.maximum())
            painter.fillRect(rect.x(), rect.y(), chunk_width, rect.height(), QColor(0, 255, 0, 100))
        painter.setPen(QColor('grey'))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            total_width = self.width()
            if total_width <= 0:
                # Widget non ancora dimensionato; ignora il click per evitare
                # divisione per zero.
                super().mousePressEvent(event)
                return
            click_position = event.x()
            new_value = int(click_position / total_width * (self.maximum() - self.minimum()) + self.minimum())
            self.setValue(new_value)
            if self.maximum() > 0:
                self.clicked.emit(new_value / self.maximum())
        super().mousePressEvent(event)


class Mp3Widget(QWidget):
    remove_requested = pyqtSignal()

    def __init__(self, mp3_audio_file: Mp3File, layout: WidgetLayout = WidgetLayout.TOUCH):
        super().__init__()
        self.mp3file = mp3_audio_file
        self.mp3file.playback_state_changed.connect(self._on_playback_state_changed)
        self.mp3file.fade_in_started.connect(self._on_fade_in_started)
        self.mp3file.fadeInFinished.connect(self._on_fade_in_finished)
        self.mp3file.normalize_ready.connect(self._on_normalize_ready)

        self.volume_slider_value = self.mp3file.actual_volume
        self.fade_time = 5
        self.file_duration = self.mp3file.mp3_total_duration
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name

        self.drag_start_position = QPoint()
        self._drag_armed = False
        self._waveform_service = WaveformService(self)
        self._waveform_service.waveform_upgraded.connect(self._set_progress_bar_background)

        self.create_ui_elements()
        self.apply_layout()

        self._progress_error_count = 0
        self._MAX_PROGRESS_ERRORS = 10
        self._polling_disabled = False

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.defaultBtnStyle = "border: 1px solid; border-radius: 5px;"
        self.btnChangeLayout.setText(self.current_layout_name)

    def _is_drag_handle(self, pos) -> bool:
        """Solo la label del filename funge da drag handle: evita di rubare i
        click ai pulsanti quando l'utente fa un piccolo movimento durante il click."""
        return self.childAt(pos) is self.filename_label

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_drag_handle(event.pos()):
            self.drag_start_position = event.pos()
            self._drag_armed = True
        else:
            self._drag_armed = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._drag_armed:
            return
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < self.startDragDistance():
            return
        self._drag_armed = False  # one drag per press

        drag = QDrag(self)
        mime_data = Mp3WidgetMimeData()
        mime_data.setWidget(self)
        drag.setMimeData(mime_data)

        pixmap = QPixmap(self.size())
        self.render(pixmap)
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        drag_pixmap = QPixmap(pixmap.size())
        drag_pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        drag_pixmap.fill(Qt.transparent)
        p = QPainter(drag_pixmap)
        p.setOpacity(0.7)
        p.drawPixmap(0, 0, pixmap)
        p.end()

        drag.setPixmap(drag_pixmap)
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
        self.btnPlay.clicked.connect(self.on_play_pause_clicked)
        self.btnFadeIn = QPushButton("FadeIn")
        self.btnFadeIn.setIcon(QIcon.fromTheme("go-up"))
        self.btnFadeIn.clicked.connect(self.on_fade_in_clicked)
        self.spinboxFadeTime = QDoubleSpinBox()
        self.spinboxFadeTime.setRange(0, 10)
        self.spinboxFadeTime.setValue(self.fade_time)
        self.spinboxFadeTime.setSingleStep(0.5)
        self.spinboxFadeTime.valueChanged.connect(self.update_fade_time)
        self.btnFadeOut = QPushButton("Fade Out")
        self.btnFadeOut.setIcon(QIcon.fromTheme("go-down"))
        self.btnFadeOut.clicked.connect(self.on_fade_out_clicked)
        self.btnStop = QPushButton("Stop")
        self.btnStop.clicked.connect(self.on_stop_clicked)
        self.btnStop.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.btnRemove = QPushButton("Remove")
        self.btnRemove.setIcon(QIcon.fromTheme("user-trash"))
        self.btnRemove.clicked.connect(self.on_remove_clicked)
        self.btnNorm = QPushButton("Norm")
        self.btnNorm.setIcon(QIcon.fromTheme("audio-volume-high"))
        self.btnNorm.clicked.connect(self.on_normalize_clicked)
        self.slidVolume = QSlider(Qt.Vertical)
        self.slidVolume.setMinimum(0)
        self.slidVolume.setMaximum(100)
        self.slidVolume.setValue(self.volume_slider_value)
        self.slidVolume.valueChanged.connect(self.update_volume)
        self.lblVolume = QLabel("100")
        self.lblVolume.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.spinboxGain = QDoubleSpinBox()
        self.spinboxGain.setRange(0.0, 5.0)
        self.spinboxGain.setSingleStep(0.05)
        self.spinboxGain.setDecimals(2)
        self.spinboxGain.setValue(self.mp3file.gain)
        self.spinboxGain.setPrefix("G:")
        self.spinboxGain.valueChanged.connect(self._on_gain_changed)
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

        action_compact_v = QAction("Compact-V", self)
        action_compact_v.triggered.connect(lambda: self.set_layout(WidgetLayout.COMPACT_V))
        layout_menu.addAction(action_compact_v)

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
            w = item.widget()
            if w is not None:
                w.setParent(None)

        # Reset column e row stretches: i singoli helper li riconfigurano
        # secondo il layout, ma vanno azzerati prima per evitare residui di TOUCH.
        for c in range(12):
            self.widget_file_frame_layout.setColumnStretch(c, 0)
        for r in range(8):
            self.widget_file_frame_layout.setRowStretch(r, 0)

        # SizePolicy default del widget; COMPACT_V la sovrascrive ad Expanding vert.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = self.widget_file_frame_layout

        if self.widgetLayout == WidgetLayout.COMPACT:
            self._apply_compact_layout(layout)
        elif self.widgetLayout == WidgetLayout.COMPACT_V:
            self._apply_compact_v_layout(layout)
        elif self.widgetLayout == WidgetLayout.TOUCH:
            self._apply_touch_layout(layout)
        else:
            self._apply_standard_layout(layout)

        self.adjustSize()

    # ------------------------------------------------------------------
    # Layouts
    # ------------------------------------------------------------------
    def _apply_compact_layout(self, layout):
        """Striscia minimale: solo Play/Stop + filename + tempo + volume.
        Nasconde fade, gain, normalize. Volume slider orizzontale, button piccoli.
        Ideale per playlist dense. 2 righe (controlli + progress bar)."""
        self.slidVolume.setOrientation(Qt.Horizontal)

        for btn in (self.btnPlay, self.btnStop, self.btnRemove,
                    self.btnChangeLayout):
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.slidVolume.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # filename ed eventualmente volume slider espandibili
        layout.setColumnStretch(3, 3)  # filename
        layout.setColumnStretch(6, 2)  # volume

        layout.addWidget(self.btnChangeLayout, 0, 0)
        layout.addWidget(self.btnPlay,         0, 1)
        layout.addWidget(self.btnStop,         0, 2)
        layout.addWidget(self.filename_label,  0, 3)
        layout.addWidget(self.lblRemainingTime, 0, 4)
        layout.addWidget(self.lblVolume,       0, 5)
        layout.addWidget(self.slidVolume,      0, 6)
        layout.addWidget(self.btnRemove,       0, 7)
        layout.addWidget(self.progress_bar,    1, 0, 1, 8)

    def _apply_standard_layout(self, layout):
        """Desktop classico: tutti i controlli ma compatti, su 3 righe.
        Volume slider orizzontale (differenza visiva chiave da TOUCH).
        Ideale per uso mouse/keyboard su monitor."""
        self.slidVolume.setOrientation(Qt.Horizontal)

        for btn in (self.btnPlay, self.btnStop, self.btnFadeIn, self.btnFadeOut,
                    self.btnNorm, self.btnRemove, self.btnChangeLayout,
                    self.spinboxFadeTime, self.spinboxGain,
                    self.fade_preset_widget):
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.slidVolume.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.setColumnStretch(1, 3)   # filename / progress espandibili
        layout.setColumnStretch(9, 2)   # volume slider

        # Riga 0: header — layout switch | filename | remove
        layout.addWidget(self.btnChangeLayout, 0, 0)
        layout.addWidget(self.filename_label,  0, 1, 1, 9)
        layout.addWidget(self.btnRemove,       0, 10)

        # Riga 1: controlli playback + fade + gain + volume
        layout.addWidget(self.btnPlay,           1, 0)
        layout.addWidget(self.btnStop,           1, 1)
        layout.addWidget(self.btnFadeIn,         1, 2)
        layout.addWidget(self.spinboxFadeTime,   1, 3)
        layout.addWidget(self.fade_preset_widget,1, 4)
        layout.addWidget(self.btnFadeOut,        1, 5)
        layout.addWidget(self.btnNorm,           1, 6)
        layout.addWidget(self.spinboxGain,       1, 7)
        layout.addWidget(self.lblVolume,         1, 8)
        layout.addWidget(self.slidVolume,        1, 9, 1, 2)

        # Riga 2: progress bar + tempi ai lati
        layout.addWidget(self.lblElapsedTime,   2, 0)
        layout.addWidget(self.progress_bar,     2, 1, 1, 9)
        layout.addWidget(self.lblRemainingTime, 2, 10)

    def _apply_compact_v_layout(self, layout):
        """Mixer-channel verticale: stretto in orizzontale, alto in verticale.
        Slider volume verticale (fader). Niente progress bar / waveform.
        Pensato per disposizioni a colonne tipo mixer multicanale."""
        # Allunga il widget verticalmente per ospitare un fader leggibile.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.slidVolume.setOrientation(Qt.Vertical)
        self.slidVolume.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.slidVolume.setMinimumHeight(80)

        for btn in (self.btnPlay, self.btnStop, self.btnRemove,
                    self.btnChangeLayout):
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # 2 colonne, entrambe espandibili equamente.
        #layout.setColumnStretch(0, 1)
        #layout.setColumnStretch(1, 1)

        # Solo la riga del fader cresce verticalmente; le altre stanno alla
        # propria altezza naturale.
        # layout.setRowStretch(4, 1)

        # Riga 0: layout-switch + remove
        layout.addWidget(self.btnChangeLayout, 0, 2, 1, 2)
        layout.addWidget(self.btnRemove, 0, 0, 1, 2)
        # Riga 1: filename a tutta larghezza (tagliato se non sta).
        layout.addWidget(self.filename_label, 1, 0, 1, 4)
        # Righe 2-3: Play / Stop a tutta larghezza
        layout.addWidget(self.btnPlay, 2, 0, 2, 1)
        layout.addWidget(self.btnFadeIn, 2, 1, 2, 1)        
        layout.addWidget(self.btnFadeOut, 2, 2, 2, 1)        
        layout.addWidget(self.btnStop, 2, 3, 2, 1)
        # Riga 4: fader verticale, centrato orizzontalmente
        layout.addWidget(self.slidVolume, 0, 5, 5, 1, Qt.AlignLeft)
        # Riga 5: tempo rimanente in basso
        layout.addWidget(self.lblRemainingTime, 4, 0, 1, 4)

    def _apply_touch_layout(self, layout):
        """Layout invariato: button grandi, slider verticale a destra, 4 righe.
        Ideale per touchscreen / tablet."""
        self.slidVolume.setOrientation(Qt.Vertical)
        self.slidVolume.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        for i in range(12):
            layout.setColumnStretch(i, 0)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(10, 1)
        for i in range(1, 10):
            layout.setColumnStretch(i, 2)

        for btn in [self.spinboxFadeTime, self.btnRemove, self.btnNorm, self.btnPlay, self.btnFadeIn, self.btnFadeOut, self.btnStop, self.btnChangeLayout, self.fade_preset_widget]:
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        layout.addWidget(self.btnRemove, 0, 0, 1, 1)
        layout.addWidget(self.btnNorm, 1, 0, 1, 1)
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
        layout.addWidget(self.spinboxGain, 1, 10)
        layout.addWidget(self.progress_bar, 2, 0, 2, 11)
        layout.addWidget(self.lblRemainingTime, 1, 3, 1, 2)
        layout.addWidget(self.lblElapsedTime, 1, 1, 1, 2)

    def changeButtonStyle(self, btn, color):
        btn.setStyleSheet(f"QPushButton {{background-color: {color}; {self.defaultBtnStyle} }} ")

    def _on_playback_state_changed(self, state: str):
        if state == 'playing':
            self.changeButtonStyle(self.btnPlay, "green")
        elif state == 'paused':
            self.changeButtonStyle(self.btnPlay, "red")
        elif state == 'stopped':
            self.changeButtonStyle(self.btnPlay, "")
            self.changeButtonStyle(self.btnFadeIn, "")
            self.changeButtonStyle(self.btnFadeOut, "")

    def _on_fade_in_started(self):
        self.changeButtonStyle(self.btnFadeIn, "green")

    def _on_fade_in_finished(self):
        self.changeButtonStyle(self.btnFadeIn, "")

    def on_play_pause_clicked(self):
        self.mp3file.play_pause()

    def on_stop_clicked(self):
        self.mp3file.stop()

    def on_remove_clicked(self):
        self.shutdown()
        self.remove_requested.emit()
        self.deleteLater()

    def shutdown(self) -> None:
        """Stop playback, cancel background tasks, and release backend resources.
        Safe to call multiple times."""
        try:
            self._waveform_service.waveform_upgraded.disconnect(self._set_progress_bar_background)
        except (TypeError, RuntimeError):
            pass
        try:
            self._waveform_service.cancel()
        except Exception:
            pass
        try:
            self.mp3file.cleanup()
        except Exception:
            pass

    def set_volume(self, volume: int):
        """Public API: set volume without accessing internal widgets directly."""
        self.slidVolume.setValue(volume)  # triggers update_volume() via valueChanged

    def set_fade_time(self, seconds: float):
        """Public API: set fade time without accessing internal widgets directly."""
        self.spinboxFadeTime.setValue(seconds)  # triggers update_fade_time() via valueChanged

    def set_gain(self, gain: float):
        """Public API: set gain via the spinbox so the change handler propagates."""
        self.spinboxGain.setValue(gain)  # triggers _on_gain_changed via valueChanged

    def to_state(self) -> dict:
        """Serialize the widget state to a JSON-friendly dict."""
        return {
            "file_path": self.mp3file.file_name,
            "volume": int(self.mp3file.get_volume()),
            "fade_time": float(self.fade_time),
            "gain": float(self.mp3file.gain),
            "layout": self.widgetLayout.name,
        }

    def apply_state(self, state: dict) -> None:
        """Restore widget state from a dict (missing keys are ignored).

        Order matters: gain is applied before volume because set_gain rescales
        actual_volume to keep the effective volume invariant — applying volume
        last ensures the slider position from the saved state is preserved.
        """
        if "fade_time" in state:
            self.set_fade_time(float(state["fade_time"]))
        if "gain" in state:
            self.set_gain(float(state["gain"]))
        if "volume" in state:
            self.set_volume(int(state["volume"]))
        if "layout" in state:
            try:
                self.set_layout(WidgetLayout[state["layout"]])
            except KeyError:
                pass

    def update_volume(self):
        volume = self.slidVolume.value()
        self.mp3file.set_volume(volume)
        self.lblVolume.setText(str(volume))

    def update_fade_time(self):
        self.fade_time = self.spinboxFadeTime.value()

    def _on_gain_changed(self, value: float):
        self.mp3file.set_gain(value)
        self._waveform_service.refresh(value)
        # Sincronizza lo slider con actual_volume ricalcolato da set_gain
        self.slidVolume.blockSignals(True)
        self.slidVolume.setValue(self.mp3file.actual_volume)
        self.lblVolume.setText(str(self.mp3file.actual_volume))
        self.slidVolume.blockSignals(False)

    def on_normalize_clicked(self):
        self.btnNorm.setEnabled(False)
        self.mp3file.normalize()

    def _on_normalize_ready(self, gain: float):
        self.spinboxGain.setValue(gain)  # triggera _on_gain_changed
        self.btnNorm.setEnabled(True)

    def on_fade_in_clicked(self):
        self.mp3file.fade_in(self.fade_time, self.slidVolume.value())

    def on_fade_out_clicked(self):
        self.changeButtonStyle(self.btnFadeIn, "")
        self.changeButtonStyle(self.btnFadeOut, "green")
        self.mp3file.fade_out(self.fade_time, self.slidVolume.value(), 0)

    def update_playback_position(self, new_position):
        self.mp3file.set_position(new_position)

    def update_progress_bar(self):
        if self._polling_disabled:
            return
        try:
            info = self.mp3file.get_playback_info()
        except Exception as e:
            self._progress_error_count += 1
            logger.debug(f"poll error {self._progress_error_count}: {e}")
            if self._progress_error_count >= self._MAX_PROGRESS_ERRORS:
                logger.warning(
                    f"Polling disabilitato dopo {self._MAX_PROGRESS_ERRORS} errori consecutivi in update_progress_bar."
                )
                self._polling_disabled = True
            return
        self._progress_error_count = 0
        if info is not None:
            self.progress_bar.setValue(int(info['position'] * self.progress_bar.maximum()))
            self.lblElapsedTime.setText(f"Elapsed Time: {seconds_to_min_sec(info['current_seconds'])}")
            self.lblRemainingTime.setText(f"Remaining Time: {seconds_to_min_sec(info['remaining_seconds'])}")
        else:
            self.progress_bar.setValue(0)
            self.lblElapsedTime.setText("Elapsed Time: 00:00")
            self.lblRemainingTime.setText(f"Remaining Time: {seconds_to_min_sec(round(self.file_duration / 1000))}")

    def _set_progress_bar_background(self, pixmap: QPixmap):
        if self.progress_bar is None:
            return
        self.progress_bar.set_waveform(pixmap)

    def create_progress_bar(self):
        self.progress_bar = ClickableProgressBar()
        self.progress_bar.setFixedHeight(PROGRESS_BAR_HEIGHT)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.clicked.connect(self.update_playback_position)
        pixmap = self._waveform_service.generate(self.mp3file.file_name, self.file_duration)
        self.progress_bar.set_waveform(pixmap)
        return self.progress_bar
