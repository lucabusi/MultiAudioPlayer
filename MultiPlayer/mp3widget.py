import os
import logging
from enum import Enum
from PySide6.QtWidgets import QAbstractButton, QAbstractSlider, QAbstractSpinBox, QProgressBar, QWidget, QVBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QFrame, QToolButton, QMenu, QHBoxLayout, QSlider, QSizePolicy
from PySide6.QtCore import Qt, Signal, QPoint, QMimeData, QSize
from PySide6.QtGui import QIcon, QDrag, QPixmap, QPainter, QColor, QAction
from mp3file import Mp3File
from waveform_service import WaveformService
from fluid_layout import FluidLayout, LAYOUT_SPECS, MIN_FONT_PT, MAX_FONT_SCALE, QWIDGETSIZE_MAX

logger = logging.getLogger(__name__)

# Controlli sotto i quali il click NON deve avviare un drag: sono loro a
# doverlo ricevere. La progress bar è inclusa perché il click ci fa il seek.
_DRAG_BLOCKERS = (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QProgressBar)

# Sotto questa larghezza oltre il testo le frecce di una spinbox coprirebbero il
# valore: si tolgono, restano rotella e tastiera.
_SPINBOX_ARROWS_WIDTH = 70


class WidgetLayout(Enum):
    COMPACT = 1
    TOUCH = 2
    STANDARD = 3
    COMPACT_V = 4
    DENSE_A = 5
    STRIP_A = 6


def seconds_to_min_sec(seconds: int) -> str:
    return f"{seconds // 60:02}:{seconds % 60:02}"


class ClickableProgressBar(QProgressBar):
    clicked = Signal(float)

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
    remove_requested = Signal(object)  # emette self
    layout_changed = Signal()

    def __init__(self, mp3_audio_file: Mp3File, layout: WidgetLayout = WidgetLayout.TOUCH):
        super().__init__()
        self.mp3file = mp3_audio_file
        self.mp3file.playback_state_changed.connect(self._on_playback_state_changed)
        self.mp3file.fade_in_started.connect(self._on_fade_in_started)
        self.mp3file.fadeInFinished.connect(self._on_fade_in_finished)
        self.mp3file.fade_out_started.connect(self._on_fade_out_started)
        self.mp3file.fadeOutFinished.connect(self._on_fade_out_finished)
        self.mp3file.normalize_ready.connect(self._on_normalize_ready)
        self.mp3file.normalize_failed.connect(self._on_normalize_failed)
        self.mp3file.loaded.connect(self._on_loaded)
        self.mp3file.load_error.connect(self._on_load_error)

        self.fade_time = 5
        self._font_pt = None
        self._base_font_pt = None
        self._elapsed_s = 0
        self._remaining_s = round(self.mp3file.mp3_total_duration / 1000)
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name

        self.drag_start_position = QPoint()
        self._drag_armed = False
        self._waveform_service = WaveformService(self)
        self._waveform_service.waveform_upgraded.connect(self._set_progress_bar_background)

        self.create_ui_elements()
        self.apply_layout()

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.defaultBtnStyle = "border: 1px solid; border-radius: 5px;"
        self.btnChangeLayout.setText(self.current_layout_name)

    def _is_drag_handle(self, pos) -> bool:
        """Tutto il corpo del widget è drag handle, tranne i controlli.

        Limitarlo alla sola label del nome file rendeva il widget di fatto
        inamovibile: si afferra il corpo, non l'etichetta. Restano esclusi i
        controlli interattivi, che devono ricevere il click anche se l'utente
        muove il mouse di qualche pixel mentre preme. Si risale la catena dei
        parent perché `childAt()` torna il figlio più profondo (es. il
        QLineEdit interno di una spinbox)."""
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, _DRAG_BLOCKERS):
                return False
            child = child.parentWidget()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_drag_handle(event.position().toPoint()):
            self.drag_start_position = event.position().toPoint()
            self._drag_armed = True
        else:
            self._drag_armed = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._drag_armed:
            return
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self.drag_start_position).manhattanLength() < self.startDragDistance():
            return
        self._drag_armed = False  # one drag per press

        drag = QDrag(self)
        # Drag interno alla stessa app: il widget sorgente viaggia come
        # event.source(), non serve un QMimeData custom.
        drag.setMimeData(QMimeData())

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
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.MoveAction)

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

        self.widget_file_frame_layout = FluidLayout(self._adapt_to_size)
        self.widget_main_frame.setLayout(self.widget_file_frame_layout)

        self.filename_label = QLabel()
        self.set_filename_text(os.path.basename(self.mp3file.file_name))
        self.filename_label.setToolTip(self._filename_text)
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
        self.slidVolume.setValue(self.mp3file.actual_volume)
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
        self.lblElapsedTime = QLabel("Elapsed Time: 00:00")
        self.lblElapsedTime.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.lblRemainingTime = QLabel()
        self._refresh_time_labels()
        self._default_texts = {w: w.text() for w in (
            self.btnPlay, self.btnStop, self.btnFadeIn, self.btnFadeOut)}
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

        action_dense_a = QAction("Dense A", self)
        action_dense_a.triggered.connect(lambda: self.set_layout(WidgetLayout.DENSE_A))
        layout_menu.addAction(action_dense_a)

        action_strip_a = QAction("Strip A", self)
        action_strip_a.triggered.connect(lambda: self.set_layout(WidgetLayout.STRIP_A))
        layout_menu.addAction(action_strip_a)

        self.btnChangeLayout.setMenu(layout_menu)
        self.layout_menu = layout_menu

        # Solo STRIP_A: le azioni secondarie stanno nel menu "⋯".
        self.btnMore = QToolButton()
        self.btnMore.setText("⋯")
        self.btnMore.setPopupMode(QToolButton.InstantPopup)
        more_menu = QMenu(self)
        more_menu.addMenu(layout_menu)
        more_menu.addAction("Rimuovi", self.on_remove_clicked)
        more_menu.addAction("Norm", self.on_normalize_clicked)
        for secs in (1, 3, 5):
            more_menu.addAction(f"Fade {secs}s", lambda s=secs: self.set_fade_time(s))
        self.btnMore.setMenu(more_menu)

        self.widget_layout = QVBoxLayout()
        self.widget_layout.setContentsMargins(0, 0, 0, 0)
        self.widget_layout.addWidget(self.widget_main_frame)
        self.setLayout(self.widget_layout)

    def set_layout(self, layout: WidgetLayout):
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name
        self.btnChangeLayout.setText(self.current_layout_name)
        self.apply_layout()
        self.layout_changed.emit()

    def apply_layout(self):
        layout = self.widget_file_frame_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        spec = LAYOUT_SPECS[self.widgetLayout.name]
        self.slidVolume.setOrientation(Qt.Vertical if spec['slider_vertical'] else Qt.Horizontal)
        for w, text in self._default_texts.items():
            w.setText(text)
        for name, text in spec['texts'].items():
            getattr(self, name).setText(text)

        self.setMaximumSize(*spec.get('max', (QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)))
        layout.set_sizes(spec['ref'], spec['min'])
        narrow = spec.get('narrow', {})
        for name, rect in spec['items'].items():
            layout.place(getattr(self, name), rect, narrow.get(name))
        self._font_pt = None  # i controlli appena entrati non hanno il font scalato

    def _adapt_to_size(self):
        """Adegua ciò che il layout non può scalare da solo: font e testi."""
        frame = self.widget_main_frame
        spec = LAYOUT_SPECS[self.widgetLayout.name]
        if self._base_font_pt is None:
            size = self.font().pointSizeF()
            self._base_font_pt = size if size > 0 else 9.0  # -1 = font in pixel
        scale = min(frame.width() / spec['ref'][0], frame.height() / spec['ref'][1])
        # Per difetto: un font oltre la proporzione farebbe sforare i testi.
        pt = int(2 * max(MIN_FONT_PT, self._base_font_pt * min(scale, MAX_FONT_SCALE))) / 2
        if pt != self._font_pt:
            self._font_pt = pt
            # Sul singolo figlio: sotto QSS il font del frame non si propaga.
            for child in frame.findChildren(QWidget):
                font = child.font()
                font.setPointSizeF(pt)
                child.setFont(font)
                if isinstance(child, QAbstractButton):
                    side = round(16 * pt / self._base_font_pt)
                    child.setIconSize(QSize(side, side))
        self._elide_filename()
        self._refresh_time_labels()
        for spin in (self.spinboxFadeTime, self.spinboxGain):
            arrows = spin.width() >= spin.fontMetrics().horizontalAdvance(spin.text()) + _SPINBOX_ARROWS_WIDTH
            spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows if arrows else QAbstractSpinBox.NoButtons)

    def set_filename_text(self, text: str) -> None:
        self._filename_text = text
        self._elide_filename()

    def _elide_filename(self):
        label = self.filename_label
        elided = label.fontMetrics().elidedText(self._filename_text, Qt.ElideMiddle, label.width())
        if label.text() != elided:
            label.setText(elided)

    def changeButtonStyle(self, btn, color):
        btn.setStyleSheet(f"QPushButton {{background-color: {color}; {self.defaultBtnStyle} }} ")

    def _on_playback_state_changed(self, state: str):
        if state == 'playing':
            self.changeButtonStyle(self.btnPlay, "green")
        elif state == 'paused':
            # La pausa passa da Mp3File._stop_active_fade: qualsiasi fade in
            # corso è stato annullato, quindi gli indicatori vanno spenti.
            self.changeButtonStyle(self.btnPlay, "red")
            self._clear_fade_indicators()
        elif state == 'stopped':
            self.changeButtonStyle(self.btnPlay, "")
            self._clear_fade_indicators()

    def _clear_fade_indicators(self):
        self.changeButtonStyle(self.btnFadeIn, "")
        self.changeButtonStyle(self.btnFadeOut, "")

    def _on_fade_in_started(self):
        self.changeButtonStyle(self.btnFadeOut, "")
        self.changeButtonStyle(self.btnFadeIn, "green")

    def _on_fade_in_finished(self):
        self.changeButtonStyle(self.btnFadeIn, "")

    def _on_fade_out_started(self):
        self.changeButtonStyle(self.btnFadeIn, "")
        self.changeButtonStyle(self.btnFadeOut, "green")

    def _on_fade_out_finished(self):
        self.changeButtonStyle(self.btnFadeOut, "")

    def _on_loaded(self):
        """Il backend è pronto: la durata reale è ora disponibile."""
        self._remaining_s = round(self.mp3file.mp3_total_duration / 1000)
        self._refresh_time_labels()

    def _on_load_error(self, message: str):
        """Backend non inizializzabile: disabilita i controlli e segnala l'errore."""
        logger.error(f"Load error for {self.mp3file.file_name}: {message}")
        self.set_filename_text(f"⚠ {os.path.basename(self.mp3file.file_name)}")
        self.filename_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        self.filename_label.setToolTip(f"Errore caricamento backend: {message}")
        for w in (self.btnPlay, self.btnStop, self.btnFadeIn, self.btnFadeOut, self.btnNorm):
            w.setEnabled(False)

    def _report_playback_error(self, action: str, exc: Exception) -> None:
        """Segnala nella UI un errore del backend senza propagarlo.

        Un'eccezione che esce da uno slot Qt non deve mai arrivare all'event
        loop: con PyQt5 abortiva il processo (`qFatal()`, exit 0xC0000409);
        PySide6 la stampa e prosegue, ma lascia il widget a metà operazione.
        Un device audio perso a metà spettacolo non deve chiudere l'app, così
        i controlli restano attivi e l'operatore può ritentare."""
        logger.error(f"{action} failed for {self.mp3file.file_name}: {exc}")
        self.set_filename_text(f"⚠ {os.path.basename(self.mp3file.file_name)}")
        self.filename_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        self.filename_label.setToolTip(f"{action} fallito: {exc}")

    def on_play_pause_clicked(self):
        try:
            self.mp3file.play_pause()
        except Exception as e:
            self._report_playback_error("Play/Pause", e)

    def on_stop_clicked(self):
        try:
            self.mp3file.stop()
        except Exception as e:
            self._report_playback_error("Stop", e)

    def on_remove_clicked(self):
        self.shutdown()
        self.remove_requested.emit(self)
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
        """Serialize the widget state to a JSON-friendly dict.

        Il volume viene letto dallo slider, non da `mp3file.actual_volume`:
        durante un fade quest'ultimo è il volume istantaneo della rampa
        (salvando a metà di un fade-in da 0 a 90 si otterrebbe 4). Lo slider
        è la posizione scelta dall'utente e resta allineato ad
        `actual_volume` in tutti gli altri istanti.
        """
        return {
            "file_path": self.mp3file.file_name,
            "volume": int(self.slidVolume.value()),
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

    def _on_normalize_failed(self, message: str):
        logger.error(f"Normalize failed for {self.mp3file.file_name}: {message}")
        self.btnNorm.setEnabled(True)

    def on_fade_in_clicked(self):
        self.mp3file.fade_in(self.fade_time, self.slidVolume.value())

    def on_fade_out_clicked(self):
        # L'indicatore lo accende fade_out_started, non il click: fade_out è un
        # no-op se la traccia non sta suonando e il pulsante resterebbe verde
        # a mentire per sempre.
        self.mp3file.fade_out(self.fade_time, self.slidVolume.value(), 0)

    def update_playback_position(self, new_position):
        self.mp3file.set_position(new_position)

    def update_progress_bar(self):
        info = self.mp3file.get_playback_info()
        if info is not None:
            self.progress_bar.setValue(int(info['position'] * self.progress_bar.maximum()))
            self._set_time_labels(info['current_seconds'], info['remaining_seconds'])
        else:
            self.progress_bar.setValue(0)
            self._set_time_labels(0, round(self.mp3file.mp3_total_duration / 1000))

    def _set_time_labels(self, elapsed_s: int, remaining_s: int):
        """Aggiorna le label SOLO se i secondi sono cambiati: setText con lo
        stesso testo forza comunque re-layout e repaint, e a 20Hz per widget
        il polling teneva la CPU occupata anche ad app ferma."""
        if (elapsed_s, remaining_s) != (self._elapsed_s, self._remaining_s):
            self._elapsed_s, self._remaining_s = elapsed_s, remaining_s
            self._refresh_time_labels()

    def _refresh_time_labels(self):
        """Forma lunga se entra in entrambe le label, altrimenti solo il tempo.

        Si decide insieme: vedere una forma lunga accanto a una breve confonde.
        La label del tempo trascorso conta solo se è nel layout corrente."""
        elapsed = seconds_to_min_sec(self._elapsed_s)
        remaining = seconds_to_min_sec(self._remaining_s)
        rows = ((self.lblElapsedTime, f"Elapsed Time: {elapsed}", elapsed),
                (self.lblRemainingTime, f"Remaining Time: {remaining}", f"-{remaining}"))
        fits = all(label.fontMetrics().horizontalAdvance(long_text) <= label.width()
                   for label, long_text, _ in rows if label.parent() is not None)
        for label, long_text, short_text in rows:
            text = long_text if fits else short_text
            if label.text() != text:
                label.setText(text)

    def _set_progress_bar_background(self, pixmap: QPixmap):
        if self.progress_bar is None:
            return
        self.progress_bar.set_waveform(pixmap)

    def create_progress_bar(self):
        self.progress_bar = ClickableProgressBar()
        self.progress_bar.setMaximum(1000)
        self.progress_bar.clicked.connect(self.update_playback_position)
        # La waveform arriva in background via waveform_upgraded; fino ad
        # allora la barra dipinge il fondo piatto.
        self._waveform_service.generate(self.mp3file.file_name)
        return self.progress_bar
